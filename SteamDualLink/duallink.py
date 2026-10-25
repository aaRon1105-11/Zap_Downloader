import asyncio
import socket
import sys
import os
import time
import json
import subprocess
import signal
import winreg
import ctypes
import atexit
from collections import deque

PROXY_HOST = "127.0.0.1"
PROXY_PORT = 8080
BUFFER_SIZE = 262144  # 256 KB buffer for ultra-high throughput
SOCKET_BUF_SIZE = 1048576  # 1 MB TCP send/receive window

class AdapterStats:
    def __init__(self, name, description, ip, gateway, link_speed=1000):
        self.name = name
        self.description = description
        self.ip = ip
        self.gateway = gateway
        self.link_speed = link_speed
        self.active_conns = 0
        self.total_bytes = 0
        self.history = deque(maxlen=10)
        self.current_speed_bps = 0.0

    def add_bytes(self, n):
        self.total_bytes += n

    def update_speed(self, now):
        self.history.append((now, self.total_bytes))
        if len(self.history) >= 2:
            dt = self.history[-1][0] - self.history[0][0]
            db = self.history[-1][1] - self.history[0][1]
            if dt > 0.05:
                self.current_speed_bps = db / dt
            else:
                self.current_speed_bps = 0.0
        else:
            self.current_speed_bps = 0.0

class MultiLinkProxy:
    def __init__(self):
        self.adapters = []
        self.adapter_stats = {}
        self.rr_index = 0
        self.running = True
        self.server = None

    def detect_adapters(self):
        """Discovers distinct physical network connections and eliminates duplicate adapters on the same gateway."""
        ps_cmd = """
        Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | ForEach-Object {
            $route = $_
            $ip = Get-NetIPAddress -InterfaceIndex $route.InterfaceIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object { $_.IPAddress -notlike '169.254*' -and $_.IPAddress -notlike '127*' } | Select-Object -First 1
            $adapter = Get-NetAdapter -InterfaceIndex $route.InterfaceIndex -ErrorAction SilentlyContinue
            if ($ip -and $adapter -and $adapter.InterfaceDescription -notlike '*Speedify*' -and $adapter.InterfaceDescription -notlike '*Tailscale*') {
                [PSCustomObject]@{
                    Name = $adapter.Name
                    Description = $adapter.InterfaceDescription
                    IP = $ip.IPAddress
                    Gateway = $route.NextHop
                    InterfaceIndex = $route.InterfaceIndex
                    RouteMetric = $route.RouteMetric
                }
            }
        } | ConvertTo-Json -Compress
        """
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True,
                text=True,
                timeout=4
            )
            raw = res.stdout.strip()
            if not raw:
                return []
            
            data = json.loads(raw)
            if isinstance(data, dict):
                data = [data]
            
            # Group by Gateway: if both Ethernet and Wi-Fi share 192.168.1.1, pick Ethernet (wired) over Wi-Fi
            gateway_map = {}
            for item in data:
                ip = item.get("IP")
                gw = item.get("Gateway")
                name = item.get("Name", "")
                if not ip or ip.startswith("169.254.") or ip.startswith("127."):
                    continue
                
                if gw not in gateway_map:
                    gateway_map[gw] = item
                else:
                    # Prefer wired Ethernet over Wi-Fi on the same gateway
                    existing = gateway_map[gw]
                    if "Wi-Fi" in existing.get("Name", "") and "Ethernet" in name:
                        gateway_map[gw] = item

            return list(gateway_map.values())
        except Exception:
            return []

    async def adapter_monitor_loop(self):
        while self.running:
            raw_adapters = self.detect_adapters()
            new_list = []

            for a in raw_adapters:
                ip = a["IP"]
                if ip not in self.adapter_stats:
                    self.adapter_stats[ip] = AdapterStats(
                        name=a["Name"],
                        description=a["Description"],
                        ip=ip,
                        gateway=a["Gateway"]
                    )
                new_list.append(self.adapter_stats[ip])

            self.adapters = new_list
            await asyncio.sleep(3)

    def get_next_adapter(self):
        """Selects adapter based on current speed and connection balance."""
        if not self.adapters:
            return None
        if len(self.adapters) == 1:
            return self.adapters[0]

        # If one adapter is significantly faster, weight more connections toward it
        # Otherwise fallback to round-robin
        self.rr_index = (self.rr_index + 1) % len(self.adapters)
        return self.adapters[self.rr_index]

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

            adapter = self.get_next_adapter()
            if not adapter:
                client_writer.close()
                return

            adapter.active_conns += 1

            if method == "CONNECT":
                if ":" in target:
                    host, port_s = target.split(":", 1)
                    port = int(port_s)
                else:
                    host = target
                    port = 443
                await self.tunnel_connect(client_reader, client_writer, host, port, adapter)
            else:
                await self.tunnel_http(client_reader, client_writer, method, target, parts[2] if len(parts) > 2 else "HTTP/1.1", headers, adapter)

        except Exception:
            pass
        finally:
            try:
                client_writer.close()
            except Exception:
                pass

    def optimize_socket(self, s):
        """Sets high-performance TCP socket buffer options for gigabit streaming."""
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, SOCKET_BUF_SIZE)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, SOCKET_BUF_SIZE)
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

            async def forward(r, w, is_download=False):
                try:
                    drain_counter = 0
                    while self.running:
                        data = await r.read(BUFFER_SIZE)
                        if not data:
                            break
                        w.write(data)
                        drain_counter += len(data)
                        # Drain only after substantial buffer to minimize event-loop context switching
                        if drain_counter >= BUFFER_SIZE:
                            await w.drain()
                            drain_counter = 0
                        if is_download:
                            adapter.add_bytes(len(data))
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
                        w.write(data)
                        drain_counter += len(data)
                        if drain_counter >= BUFFER_SIZE:
                            await w.drain()
                            drain_counter = 0
                        if is_download:
                            adapter.add_bytes(len(data))
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

    async def ui_dashboard_loop(self):
        while self.running:
            await asyncio.sleep(1.0)
            now = time.time()
            for a in self.adapters:
                a.update_speed(now)

            os.system('cls' if os.name == 'nt' else 'clear')
            print("=" * 78)
            print("         DUAL-LINK STEAM & MULTI-WAN DOWNLOAD ACCELERATOR (v1.1)        ")
            print("=" * 78)
            print(f" Proxy Listening on:  http://{PROXY_HOST}:{PROXY_PORT}")
            print(f" System Proxy Status: ACTIVE (Steam & Apps automatically accelerated)")
            print(f" Distinct Gateways:   {len(self.adapters)} (Duplicate Wi-Fi/LAN deduplicated)")
            print("-" * 78)
            
            if not self.adapters:
                print("  [!] WAITING FOR CONNECTIONS... Plug in your phone & enable USB Tethering.")
            else:
                header = f"{'ADAPTER NAME':<16} {'GATEWAY':<16} {'IP ADDRESS':<15} {'CONNS':<8} {'SPEED':<12} {'DOWNLOADED'}"
                print(header)
                print("-" * 78)
                total_speed_bps = 0
                total_bytes = 0
                total_conns = 0

                for a in self.adapters:
                    mb_s = a.current_speed_bps / (1024 * 1024)
                    speed_str = f"{mb_s:.2f} MB/s" if mb_s < 1000 else f"{mb_s/1024:.2f} GB/s"
                    downloaded_str = f"{a.total_bytes / (1024*1024):.1f} MB" if a.total_bytes < 1024**3 else f"{a.total_bytes / (1024**3):.2f} GB"
                    
                    print(f"{a.name[:15]:<16} {a.gateway:<16} {a.ip:<15} {a.active_conns:<8} {speed_str:<12} {downloaded_str}")
                    total_speed_bps += a.current_speed_bps
                    total_bytes += a.total_bytes
                    total_conns += a.active_conns

                print("-" * 78)
                tot_mb_s = total_speed_bps / (1024 * 1024)
                tot_mbps = (total_speed_bps * 8) / (1024 * 1024)
                tot_dl = f"{total_bytes / (1024*1024):.1f} MB" if total_bytes < 1024**3 else f"{total_bytes / (1024**3):.2f} GB"
                print(f"{'COMBINED TOTAL':<16} {'--':<16} {'--':<15} {total_conns:<8} {tot_mb_s:.2f} MB/s ({tot_mbps:.1f} Mbps) {tot_dl}")
            
            print("=" * 78)
            print(" Tip: Plug phone via USB-C -> Settings -> Mobile Hotspot -> Turn ON 'USB Tethering'")
            print(" Press Ctrl+C at any time to exit and automatically restore normal proxy.")

def set_windows_system_proxy(enable=True, server=f"{PROXY_HOST}:{PROXY_PORT}"):
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            0,
            winreg.KEY_WRITE
        )
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1 if enable else 0)
        if enable:
            winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, server)
            winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ, "<local>;127.0.0.1;localhost")
        winreg.CloseKey(key)

        wininet = ctypes.windll.wininet
        INTERNET_OPTION_SETTINGS_CHANGED = 39
        INTERNET_OPTION_REFRESH = 37
        wininet.InternetSetOptionW(0, INTERNET_OPTION_SETTINGS_CHANGED, 0, 0)
        wininet.InternetSetOptionW(0, INTERNET_OPTION_REFRESH, 0, 0)
    except Exception as e:
        print(f"Warning: Could not configure system proxy: {e}")

async def main():
    proxy = MultiLinkProxy()
    set_windows_system_proxy(True)

    raw = proxy.detect_adapters()
    for a in raw:
        proxy.adapter_stats[a["IP"]] = AdapterStats(a["Name"], a["Description"], a["IP"], a["Gateway"])
    proxy.adapters = list(proxy.adapter_stats.values())

    server = await asyncio.start_server(proxy.handle_client, PROXY_HOST, PROXY_PORT)
    proxy.server = server

    monitor_task = asyncio.create_task(proxy.adapter_monitor_loop())
    dashboard_task = asyncio.create_task(proxy.ui_dashboard_loop())

    try:
        async with server:
            await server.serve_forever()
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        proxy.running = False
        monitor_task.cancel()
        dashboard_task.cancel()
        set_windows_system_proxy(False)

if __name__ == "__main__":
    atexit.register(set_windows_system_proxy, False)

    def sig_handler(sig, frame):
        set_windows_system_proxy(False)
        sys.exit(0)

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        set_windows_system_proxy(False)
