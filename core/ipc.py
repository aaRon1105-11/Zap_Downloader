"""
Local IPC Control Server
Enables live queries and configuration changes (mode, stats, encryption) without daemon restart.
"""

import asyncio
import json

IPC_HOST = "127.0.0.1"
IPC_PORT = 9335  # Local IPC control port

class IPCServer:
    def __init__(self, daemon):
        self.daemon = daemon
        self.server = None

    async def start(self):
        self.server = await asyncio.start_server(self.handle_client, IPC_HOST, IPC_PORT)

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def handle_client(self, reader, writer):
        try:
            line = await reader.readline()
            if not line:
                return

            req = json.loads(line.decode('utf-8'))
            cmd = req.get("cmd", "")
            args = req.get("args", {})

            resp = {"status": "ok"}

            if cmd == "state":
                resp["data"] = {
                    "running": self.daemon.running,
                    "mode": self.daemon.bonding.mode,
                    "encryption": self.daemon.crypto.enabled,
                    "adapters_count": len(self.daemon.active_adapters)
                }

            elif cmd == "set_mode":
                new_mode = args.get("mode", "")
                if self.daemon.bonding.set_mode(new_mode):
                    resp["data"] = f"Mode changed to {new_mode}"
                else:
                    resp["status"] = "error"
                    resp["error"] = "Invalid mode"

            elif cmd == "set_encryption":
                enable = bool(args.get("enabled", False))
                self.daemon.crypto.set_encryption(enable)
                resp["data"] = f"Encryption set to {enable}"

            elif cmd == "show_adapters":
                resp["data"] = [
                    {
                        "name": a.name,
                        "ip": a.ip,
                        "gateway": a.gateway,
                        "active_conns": a.active_conns,
                        "speed_mbps": round((a.current_speed_bps * 8) / (1024 * 1024), 2),
                        "total_mb": round((a.total_bytes_in + a.total_bytes_out) / (1024 * 1024), 1)
                    }
                    for a in self.daemon.active_adapters
                ]

            elif cmd == "stats":
                tot_speed_bps = sum(a.current_speed_bps for a in self.daemon.active_adapters)
                tot_bytes = sum(a.total_bytes_in + a.total_bytes_out for a in self.daemon.active_adapters)
                resp["data"] = {
                    "total_speed_mbps": round((tot_speed_bps * 8) / (1024 * 1024), 2),
                    "total_downloaded_mb": round(tot_bytes / (1024 * 1024), 1),
                    "active_connections": sum(a.active_conns for a in self.daemon.active_adapters)
                }

            else:
                resp["status"] = "error"
                resp["error"] = "Unknown command"

            writer.write(json.dumps(resp).encode('utf-8') + b"\n")
            await writer.drain()

        except Exception as e:
            err = {"status": "error", "error": str(e)}
            try:
                writer.write(json.dumps(err).encode('utf-8') + b"\n")
                await writer.drain()
            except Exception:
                pass
        finally:
            writer.close()
