"""
Network Adapter Discovery & Health Monitoring
Handles multi-interface enumeration, gateway deduplication, and real-time bandwidth metrics.
"""

import subprocess
import json
import time
from collections import deque

class AdapterInfo:
    def __init__(self, name: str, description: str, ip: str, gateway: str, priority: str = "always"):
        self.name = name
        self.description = description
        self.ip = ip
        self.gateway = gateway
        self.priority = priority  # 'always', 'secondary', 'backup'
        self.active_conns = 0
        self.total_bytes_in = 0
        self.total_bytes_out = 0
        self.history = deque(maxlen=10)
        self.current_speed_bps = 0.0

    def add_bytes_in(self, count: int):
        self.total_bytes_in += count

    def add_bytes_out(self, count: int):
        self.total_bytes_out += count

    def update_speed(self, now: float):
        total = self.total_bytes_in + self.total_bytes_out
        self.history.append((now, total))
        if len(self.history) >= 2:
            dt = self.history[-1][0] - self.history[0][0]
            db = self.history[-1][1] - self.history[0][1]
            if dt > 0.05:
                self.current_speed_bps = db / dt
            else:
                self.current_speed_bps = 0.0
        else:
            self.current_speed_bps = 0.0

class AdapterManager:
    def __init__(self):
        self.adapters = {}  # ip -> AdapterInfo

    def scan(self) -> list:
        """
        Enumerates all active physical network adapters on Windows with an active default gateway.
        Eliminates duplicate adapters on the same gateway (e.g. Wi-Fi + Ethernet on 192.168.1.1).
        """
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

            # Deduplicate by Gateway: if both Ethernet and Wi-Fi share the same gateway, prefer Ethernet
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
                    existing = gateway_map[gw]
                    if "Wi-Fi" in existing.get("Name", "") and "Ethernet" in name:
                        gateway_map[gw] = item

            # Update internal registry
            current_active = []
            for item in gateway_map.values():
                ip = item["IP"]
                if ip not in self.adapters:
                    self.adapters[ip] = AdapterInfo(
                        name=item["Name"],
                        description=item["Description"],
                        ip=ip,
                        gateway=item["Gateway"]
                    )
                current_active.append(self.adapters[ip])

            return current_active
        except Exception:
            return list(self.adapters.values())

    def update_metrics(self):
        now = time.time()
        for a in self.adapters.values():
            a.update_speed(now)
