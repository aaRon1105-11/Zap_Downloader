# DualLink (Speedify-Grade Channel Bonding Accelerator v1.2)

**DualLink** implements **Speedify's core architectural design principles** directly on your Windows PC with **zero remote server fees**, **zero kernel drivers**, and **zero double-encryption CPU overhead**.

---

## 1. Architectural Highlights (v1.2 Improvements)

1. **Dynamic Adaptive Bandwidth Weighting (Proportional Load-Balancing):**
   - Automatically tracks real-time speeds across all active uplinks.
   - If Mobile Tethering is faster (e.g. 150 Mbps) than Home Ethernet (85 Mbps), DualLink dynamically allocates ~64% of requests to Mobile and ~36% to Ethernet, eliminating bottlenecks and extracting maximum combined bandwidth.
2. **In-Memory Asynchronous DNS Cache:**
   - Caches resolved CDN IP endpoints for 5 minutes in memory, cutting chunk connection setup latency from ~30ms down to ~0.05ms for instant Steam burst speeds.
3. **Smart Port Conflict Recovery:**
   - Automatically detects and clears stale ports (`8080` / `9335`) from any previous crashed sessions, ensuring clean startup every time.
4. **Three Speedify Bonding Algorithms:**
   - **`SPEED` (Default):** Bandwidth-weighted striping across all active uplinks.
   - **`STREAMING`:** Priority QoS scheduling for real-time interactive traffic (voice/Discord/Twitch).
   - **`REDUNDANT`:** High-reliability fallback mode prioritizing the lowest-jitter link.
5. **Gateway Deduplication Engine:**
   - Detects when multiple local adapters (e.g. Wi-Fi and Wired Ethernet) share the exact same router gateway (`192.168.1.1`), prioritizing Gigabit Ethernet and ignoring the duplicate Wi-Fi.
6. **CPU-Optimized Cryptography Engine:**
   - **TLS Pass-Through (0% CPU Overhead):** Detects already-encrypted TLS 1.3 / HTTPS streams (Steam CDN chunks, browser HTTPS). Rather than burning CPU re-encrypting encrypted payloads in user space, it streams directly.
   - **Hardware AES-NI:** When encryption is requested for plaintext data, uses Windows CNG (`bcrypt.dll`) executing directly on Intel/AMD hardware AES-NI instructions.
   - **Dynamic Encryption Toggle:** Switchable on/off live via `python duallink_cli.py encryption <on|off>`.
7. **Real-time ASCII Meters & Built-in Benchmark:**
   - Live visual bandwidth meters in the console dashboard.
   - Built-in multi-interface benchmark utility via `python duallink_cli.py benchmark`.

---

## 2. CLI Management Commands (`duallink_cli.py`)

While DualLink is running, open a second terminal to manage the engine in real time:

```bash
# Run a live multi-interface benchmark (tests each link + combined throughput)
python duallink_cli.py benchmark

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
4. Watch the live console dashboard display bonded speeds and visual activity meters!
