"""
DualLink — Speedify-Grade Channel Bonding Accelerator
Main Application Entry Point
"""

import asyncio
import signal
import sys
import atexit
from core.daemon import DualLinkDaemon
from core.dashboard import Dashboard

daemon = None

def cleanup():
    global daemon
    if daemon:
        daemon.set_system_proxy(False)

atexit.register(cleanup)

def sig_handler(sig, frame):
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGINT, sig_handler)
signal.signal(signal.SIGTERM, sig_handler)

async def main():
    global daemon
    daemon = DualLinkDaemon(bonding_mode="speed", encryption_enabled=False)
    await daemon.start()

    dashboard = Dashboard(daemon)
    dash_task = asyncio.create_task(dashboard.run())

    try:
        while daemon.running:
            await asyncio.sleep(1)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        dash_task.cancel()
        await daemon.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        cleanup()
        print("\n[+] Exited cleanly. System proxy restored.")
