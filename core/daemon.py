"""
Core Daemon Engine
Asynchronous proxy pipeline managing multi-link sockets, WinINet integration, and telemetry.
"""

import asyncio
import socket
import winreg
import ctypes
from .adapters import AdapterManager
from .bonding import BondingEngine
from .crypto import CryptoEngine
from .ipc import IPCServer

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080
BUFFER_SIZE = 262144        # 256 KB buffer for zero-copy high throughput
SOCKET_BUF_SIZE = 1048576    # 1 MB TCP send/receive window

class DualLinkDaemon:
    def __init__(self, bonding_mode="speed", encryption_enabled=False):
        self.running = True
        self.adapters_mgr = AdapterManager()
        self.bonding = BondingEngine(mode=bonding_mode)
        self.crypto = CryptoEngine(enabled=encryption_enabled)
        self.ipc = IPCServer(self)
        self.active_adapters = []
        self.proxy_server = None

    def optimize_socket(self, s: socket.socket):
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCKET_BUF_SIZE)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SOCKET_BUF_SIZE)
        except Exception:
            pass

    async def handle_client(self, client_reader, client_writer):
        try:
            line = await client_reader.readline()
            if not line:
                client_writer.close()
                return

            req_str = line.decode('latin1', errors='ignore').strip()
            parts = req_str.split()
            if len(parts) < 2:
                client_writer.close()
                return

            method = parts[0].upper()
            target = parts[1]

            headers = []
            while True:
                h = await client_reader.readline()
                if not h or h == b'\r\n' or h == b'\n':
                    break
                headers.append(h)

            if ":" in target:
                host, port_s = target.split(":", 1)
                try:
                    port = int(port_s)
                except ValueError:
                    port = 443 if method == "CONNECT" else 80
            else:
                host = target
                port = 443 if method == "CONNECT" else 80

            adapter = self.bonding.select_adapter(self.active_adapters, target_host=host, target_port=port)
            if not adapter:
                client_writer.close()
                return

            adapter.active_conns += 1

            if method == "CONNECT":
                await self.tunnel_connect(client_reader, client_writer, host, port, adapter)
            else:
                proto = parts[2] if len(parts) > 2 else "HTTP/1.1"
                await self.tunnel_http(client_reader, client_writer, method, target, proto, headers, adapter)

        except Exception:
            pass
        finally:
            try:
                client_writer.close()
            except Exception:
                pass

    async def tunnel_connect(self, client_reader, client_writer, host, port, adapter):
        loop = asyncio.get_running_loop()
        remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.optimize_socket(remote_sock)

        try:
            remote_sock.bind((adapter.ip, 0))
            remote_sock.setblocking(False)

            addrinfo = await loop.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
            dest_ip, dest_port = addrinfo[0][4][:2]

            await asyncio.wait_for(loop.sock_connect(remote_sock, (dest_ip, dest_port)), timeout=6.0)

            client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await client_writer.drain()

            remote_reader, remote_writer = await asyncio.open_connection(sock=remote_sock)

            # Bidirectional streaming with CPU-optimized crypto handling
            async def forward(r, w, is_download=False):
                try:
                    drain_counter = 0
                    while self.running:
                        data = await r.read(BUFFER_SIZE)
                        if not data:
                            break

                        # Process via CryptoEngine: automatically bypasses double-encryption for TLS
                        processed = self.crypto.process_inbound(data, is_tls=True) if is_download else self.crypto.process_outbound(data, is_tls=True)
                        w.write(processed)
                        drain_counter += len(data)

                        if drain_counter >= BUFFER_SIZE:
                            await w.drain()
                            drain_counter = 0

                        if is_download:
                            adapter.add_bytes_in(len(data))
                        else:
                            adapter.add_bytes_out(len(data))

                    await w.drain()
                except Exception:
                    pass
                finally:
                    try:
                        w.close()
                    except Exception:
                        pass

            await asyncio.gather(
                forward(client_reader, remote_writer, is_download=False),
                forward(remote_reader, client_writer, is_download=True)
            )

        except Exception:
            pass
        finally:
            adapter.active_conns = max(0, adapter.active_conns - 1)
            try:
                remote_sock.close()
            except Exception:
                pass

    async def tunnel_http(self, client_reader, client_writer, method, url, proto, headers, adapter):
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = parsed.hostname
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        loop = asyncio.get_running_loop()
        remote_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.optimize_socket(remote_sock)

        try:
            remote_sock.bind((adapter.ip, 0))
            remote_sock.setblocking(False)

            addrinfo = await loop.getaddrinfo(host, port, family=socket.AF_INET, type=socket.SOCK_STREAM)
            dest_ip, dest_port = addrinfo[0][4][:2]

            await asyncio.wait_for(loop.sock_connect(remote_sock, (dest_ip, dest_port)), timeout=6.0)
            remote_reader, remote_writer = await asyncio.open_connection(sock=remote_sock)

            req_line = f"{method} {path} {proto}\r\n".encode('latin1')
            remote_writer.write(req_line)
            for h in headers:
                remote_writer.write(h)
            remote_writer.write(b"\r\n")
            await remote_writer.drain()

            async def forward(r, w, is_download=False):
                try:
                    drain_counter = 0
                    while self.running:
                        data = await r.read(BUFFER_SIZE)
                        if not data:
                            break
                        processed = self.crypto.process_inbound(data, is_tls=False) if is_download else self.crypto.process_outbound(data, is_tls=False)
                        w.write(processed)
                        drain_counter += len(data)
                        if drain_counter >= BUFFER_SIZE:
                            await w.drain()
                            drain_counter = 0
                        if is_download:
                            adapter.add_bytes_in(len(data))
                        else:
                            adapter.add_bytes_out(len(data))
                    await w.drain()
                except Exception:
                    pass
                finally:
                    try:
                        w.close()
                    except Exception:
                        pass

            await asyncio.gather(
                forward(client_reader, remote_writer, is_download=False),
                forward(remote_reader, client_writer, is_download=True)
            )

        except Exception:
            pass
        finally:
            adapter.active_conns = max(0, adapter.active_conns - 1)
            try:
                remote_sock.close()
            except Exception:
                pass

    async def adapter_monitor_task(self):
        while self.running:
            self.active_adapters = self.adapters_mgr.scan()
            self.adapters_mgr.update_metrics()
            await asyncio.sleep(2.0)

    def set_system_proxy(self, enable=True):
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                0,
                winreg.KEY_WRITE
            )
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1 if enable else 0)
            if enable:
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, f"{PROXY_HOST}:{PROXY_PORT}")
                winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, "<local>;127.0.0.1;localhost")
            winreg.CloseKey(key)

            wininet = ctypes.windll.wininet
            wininet.InternetSetOptionW(0, 39, 0, 0)
            wininet.InternetSetOptionW(0, 37, 0, 0)
        except Exception:
            pass

    async def start(self):
        self.set_system_proxy(True)
        self.active_adapters = self.adapters_mgr.scan()
        self.proxy_server = await asyncio.start_server(self.handle_client, PROXY_HOST, PROXY_PORT)
        await self.ipc.start()
        asyncio.create_task(self.adapter_monitor_task())

    async def stop(self):
        self.running = False
        if self.proxy_server:
            self.proxy_server.close()
            await self.proxy_server.wait_closed()
        await self.ipc.stop()
        self.set_system_proxy(False)
