"""
Terminal Dashboard & Metrics Display
Real-time console dashboard inspired by Speedify's live connection gauges.
"""

import os
import asyncio

class Dashboard:
    def __init__(self, daemon):
        self.daemon = daemon

    async def run(self):
        while self.daemon.running:
            await asyncio.sleep(1.0)
            self.daemon.adapters_mgr.update_metrics()
            adapters = self.daemon.active_adapters

            os.system('cls' if os.name == 'nt' else 'clear')
            print("=" * 80)
            print("            DUALLINK — SPEEDIFY-GRADE CHANNEL BONDING ENGINE            ")
            print("=" * 80)
            crypto_status = "ON (Hardware AES-NI)" if self.daemon.crypto.enabled else "OFF (0% CPU TLS Pass-Through)"
            print(f" Engine Status:     ACTIVE (WinINet System Hook: 127.0.0.1:8080)")
            print(f" Bonding Mode:      {self.daemon.bonding.mode.upper():<12} | Encryption: {crypto_status}")
            print(f" IPC Control API:   127.0.0.1:9335 | Active Uplinks: {len(adapters)}")
            print("-" * 80)

            if not adapters:
                print("  [!] WAITING FOR ADAPTERS... Connect Phone via USB-C & Turn on Tethering.")
            else:
                header = f"{'ADAPTER NAME':<16} {'GATEWAY':<15} {'IP ADDRESS':<15} {'CONNS':<7} {'SPEED':<14} {'DATA'}"
                print(header)
                print("-" * 80)
                tot_bps = 0
                tot_bytes = 0
                tot_conns = 0

                for a in adapters:
                    mb_s = a.current_speed_bps / (1024 * 1024)
                    speed_str = f"{mb_s:.2f} MB/s" if mb_s < 1000 else f"{mb_s/1024:.2f} GB/s"
                    total = a.total_bytes_in + a.total_bytes_out
                    data_str = f"{total / (1024*1024):.1f} MB" if total < 1024**3 else f"{total / (1024**3):.2f} GB"

                    print(f"{a.name[:15]:<16} {a.gateway:<15} {a.ip:<15} {a.active_conns:<7} {speed_str:<14} {data_str}")
                    tot_bps += a.current_speed_bps
                    tot_bytes += total
                    tot_conns += a.active_conns

                print("-" * 80)
                tot_mb_s = tot_bps / (1024 * 1024)
                tot_mbps = (tot_bps * 8) / (1024 * 1024)
                tot_data = f"{tot_bytes / (1024*1024):.1f} MB" if tot_bytes < 1024**3 else f"{tot_bytes / (1024**3):.2f} GB"
                print(f"{'BONDED TOTAL':<16} {'--':<15} {'--':<15} {tot_conns:<7} {tot_mb_s:.2f} MB/s ({tot_mbps:.1f} Mbps) {tot_data}")

            print("=" * 80)
            print(" Commands: duallink_cli.py mode <speed|streaming|redundant> | encryption <on|off>")
            print(" Press Ctrl+C to terminate cleanly and restore normal system networking.")
