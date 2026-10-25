"""
Terminal Dashboard & Metrics Display
Real-time console dashboard with visual ASCII meters and link utilization gauges.
"""

import os
import asyncio

def make_meter(bps: float, max_mbps: float = 200.0, width: int = 14) -> str:
    mbps = (bps * 8) / (1024 * 1024)
    ratio = min(1.0, max(0.0, mbps / max_mbps))
    filled = int(round(ratio * width))
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}]"

class Dashboard:
    def __init__(self, daemon):
        self.daemon = daemon

    async def run(self):
        while self.daemon.running:
            await asyncio.sleep(1.0)
            self.daemon.adapters_mgr.update_metrics()
            adapters = self.daemon.active_adapters

            os.system('cls' if os.name == 'nt' else 'clear')
            print("=" * 82)
            print("         DUALLINK (v1.2) — SPEEDIFY-GRADE CHANNEL BONDING ENGINE          ")
            print("=" * 82)
            crypto_status = "ON (Hardware AES-NI)" if self.daemon.crypto.enabled else "OFF (0% CPU TLS Pass-Through)"
            print(f" Engine Status:     ACTIVE (WinINet Hook: 127.0.0.1:8080 | DNS Cache: Active)")
            print(f" Bonding Mode:      {self.daemon.bonding.mode.upper():<10} (Dynamic Weighted) | Encryption: {crypto_status}")
            print(f" IPC Control API:   127.0.0.1:9335 | Active Uplinks: {len(adapters)}")
            print("-" * 82)

            if not adapters:
                print("  [!] WAITING FOR ADAPTERS... Connect Phone via USB-C & Turn on Tethering.")
            else:
                header = f"{'ADAPTER NAME':<14} {'GATEWAY':<14} {'CONNS':<6} {'METER':<16} {'SPEED':<14} {'DATA'}"
                print(header)
                print("-" * 82)
                tot_bps = 0
                tot_bytes = 0
                tot_conns = 0

                for a in adapters:
                    mb_s = a.current_speed_bps / (1024 * 1024)
                    speed_str = f"{mb_s:.2f} MB/s" if mb_s < 1000 else f"{mb_s/1024:.2f} GB/s"
                    meter = make_meter(a.current_speed_bps)
                    total = a.total_bytes_in + a.total_bytes_out
                    data_str = f"{total / (1024*1024):.1f} MB" if total < 1024**3 else f"{total / (1024**3):.2f} GB"

                    print(f"{a.name[:13]:<14} {a.gateway:<14} {a.active_conns:<6} {meter:<16} {speed_str:<14} {data_str}")
                    tot_bps += a.current_speed_bps
                    tot_bytes += total
                    tot_conns += a.active_conns

                print("-" * 82)
                tot_mb_s = tot_bps / (1024 * 1024)
                tot_mbps = (tot_bps * 8) / (1024 * 1024)
                tot_meter = make_meter(tot_bps, max_mbps=350.0)
                tot_data = f"{tot_bytes / (1024*1024):.1f} MB" if tot_bytes < 1024**3 else f"{tot_bytes / (1024**3):.2f} GB"
                print(f"{'BONDED TOTAL':<14} {'--':<14} {tot_conns:<6} {tot_meter:<16} {tot_mb_s:.2f} MB/s ({tot_mbps:.1f} Mbps) {tot_data}")

            print("=" * 82)
            print(" Commands: duallink_cli.py benchmark | mode <speed|streaming> | encryption <on|off>")
            print(" Press Ctrl+C to terminate cleanly and restore normal system networking.")
