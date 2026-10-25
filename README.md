DualLink: Steam & Multi-WAN Download Accelerator
DualLink allows you to combine your Home Wi-Fi and your Phone's Mobile Data (via USB-C Tethering) simultaneously to double your download speed in Steam, Epic Games, browsers, and download managers without needing any paid VPN or remote server.

Why Steam Works Perfectly With This
Steam's content delivery network (CDN) downloads game assets in dozens of parallel chunk connections. Standard Windows only routes traffic through one network adapter at a time.

DualLink runs a local, high-performance asynchronous multi-path proxy on 127.0.0.1:8080. For every chunk Steam requests, DualLink alternates between your Wi-Fi adapter and your USB-C tethered phone:

Connection 1: Wi-Fi (e.g. 15 MB/s)
Connection 2: Mobile Data (e.g. 15 MB/s)
Result: 30 MB/s combined throughput!
How to Use (Step-by-Step)
Step 1: Connect your Phone via USB-C
Connect your Android phone to your PC using a USB-C cable.
On your phone, go to Settings -> Connections (or Network & Internet).
Tap Mobile Hotspot and Tethering.
Turn ON "USB Tethering".
Wait 3 seconds. Windows will recognize your phone as a second network connection (e.g., Ethernet 2 or Samsung NDIS).
Step 2: Launch DualLink
Double-click Start_DualLink.bat (or run python duallink.py).
You will see a live dashboard showing both your Wi-Fi and USB Tethering adapters detected with their IP addresses.
DualLink automatically activates the Windows System Proxy so Steam starts routing through both pipes.
Step 3: Start your Steam Download
Open Steam and start or resume your game download.
Watch the live dashboard in the DualLink window:
You will see the Active Connections count rise.
You will see real-time download speeds for both Wi-Fi and Mobile Data.
The Combined Total will reflect your aggregated bandwidth.
Step 4: Stop DualLink When Finished
Simply press Ctrl + C in the DualLink window.
The app automatically cleans up and restores your normal Windows Internet settings.
If you ever close the window abruptly, simply double-click Restore_Normal_Internet.bat.
Technical Specifications
Proxy Port: 127.0.0.1:8080 (HTTP & HTTPS CONNECT Tunneling)
Engine: Python 3.11 asyncio non-blocking socket multiplexer
Buffer: 64 KB zero-copy bidirectional socket streaming
Link Balancing: Dynamic multi-socket round-robin with automatic link hot-plugging
