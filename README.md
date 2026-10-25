# DualLink (Speedify-Grade Channel Bonding Architecture)

**DualLink** implements **Speedify's core architectural design principles** directly on your Windows PC with **zero remote server fees**, **zero kernel drivers**, and **zero double-encryption CPU overhead**.

---

## 1. Architectural Highlights (How It Mirrors Speedify)

1. **Daemon & Control Interface:**
   - Runs an asynchronous multi-path engine on `127.0.0.1:8080` (WinINet hook for Steam and system apps).
   - Exposes a dedicated local IPC control channel on `127.0.0.1:9335` for real-time querying and control via `duallink_cli.py`.
2. **Three Speedify Bonding Algorithms:**
   - **`SPEED` (Default):** Bandwidth-weighted striping across all active uplinks (Home Ethernet + Mobile USB-C Tethering) to maximize throughput.
   - **`STREAMING`:** Priority QoS scheduling for real-time interactive traffic (voice/video/gaming), with bulk download chunks striped across both links.
   - **`REDUNDANT`:** High-reliability fallback mode prioritizing the lowest-jitter physical link.
3. **Gateway Deduplication Engine:**
   - Automatically detects when multiple local adapters (e.g. Wi-Fi and Wired Ethernet) share the exact same router gateway (`192.168.1.1`), prioritizing Gigabit Ethernet and ignoring the duplicate Wi-Fi.
4. **CPU-Optimized Cryptography Engine:**
   - **TLS Pass-Through (0% CPU Overhead):** Detects already-encrypted TLS 1.3 / HTTPS streams (Steam CDN chunks, browser HTTPS). Rather than burning CPU re-encrypting encrypted payloads in user space, it streams directly.
   - **Hardware AES-NI:** When encryption is requested for plaintext data, uses Windows CNG (`bcrypt.dll`) executing directly on Intel/AMD hardware AES-NI instructions.
   - **Dynamic Encryption Toggle:** Switchable on/off live via `python duallink_cli.py encryption <on|off>`.

---

## 2. Speedify-Style CLI Commands (`duallink_cli.py`)

While DualLink is running, open a second terminal to manage the engine in real time:

```bash
# View engine state, active mode, and active uplinks
python duallink_cli.py state

# Change bonding mode on the fly (speed, streaming, redundant)
python duallink_cli.py mode speed
python duallink_cli.py mode streaming
python duallink_cli.py mode redundant

# Toggle encryption policy
python duallink_cli.py encryption off
python duallink_cli.py encryption on

# Display per-adapter active connections and bandwidth
python duallink_cli.py show adapters

# Display aggregate download throughput and data quota
python duallink_cli.py stats
```

---

## 3. How to Run

1. Connect your Android phone via USB-C and turn on **USB Tethering**.
2. Run **`Start_DualLink.bat`** (or `python duallink.py`).
3. Start your game download in Steam.
4. Watch the live console dashboard display bonded speeds and connection metrics!
