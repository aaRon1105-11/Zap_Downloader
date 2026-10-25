"""
DualLink CLI Management Utility
Connects to DualLink daemon via local IPC (127.0.0.1:9335) for real-time control
and includes a built-in multi-interface benchmark tool.
"""

import sys
import socket
import json
import time
import threading

IPC_HOST = "127.0.0.1"
IPC_PORT = 9335

def send_cmd(cmd: str, args: dict = None):
    if args is None:
        args = {}
    payload = json.dumps({"cmd": cmd, "args": args}) + "\n"
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(3.0)
    try:
        s.connect((IPC_HOST, IPC_PORT))
        s.sendall(payload.encode('utf-8'))
        resp_data = s.recv(4096)
        s.close()
        return json.loads(resp_data.decode('utf-8'))
    except Exception as e:
        return {"status": "error", "error": f"Failed to connect to DualLink daemon: {e}"}

def run_benchmark():
    print("=" * 65)
    print("         DUALLINK MULTI-INTERFACE SPEED BENCHMARK           ")
    print("=" * 65)
    print("[*] Querying active uplinks from DualLink daemon...")
    adapters_resp = send_cmd("show_adapters")
    
    if adapters_resp.get("status") != "ok" or not adapters_resp.get("data"):
        print("[!] Error: No active adapters detected or daemon is not running.")
        print("    Ensure DualLink is running before benchmarking.")
        return

    adapters = adapters_resp["data"]
    print(f"[+] Found {len(adapters)} active uplink(s). Starting live benchmark...")
    print("-" * 65)

    host = "speed.cloudflare.com"
    try:
        target_ip = socket.gethostbyname(host)
    except Exception as e:
        print(f"[!] DNS resolution failed: {e}")
        return

    results = {}
    threads = []
    t0_all = time.time()

    def test_worker(name, ip):
        total = 0
        t0 = time.time()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1048576)
            s.bind((ip, 0))
            s.settimeout(6.0)
            s.connect((target_ip, 80))
            req = f"GET /__down?bytes=35000000 HTTP/1.1\r\nHost: {host}\r\nUser-Agent: DualLinkBench\r\nConnection: close\r\n\r\n"
            s.sendall(req.encode('utf-8'))
            while True:
                chunk = s.recv(262144)
                if not chunk:
                    break
                total += len(chunk)
            s.close()
            el = time.time() - t0
            mbps = (total * 8) / (el * 1024 * 1024)
            results[name] = (mbps, total, el)
        except Exception as e:
            results[name] = str(e)

    for a in adapters:
        t = threading.Thread(target=test_worker, args=(a["name"], a["ip"]))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    total_bytes = 0
    print(f"{'ADAPTER':<18} {'STATUS':<10} {'THROUGHPUT':<18} {'TRANSFERRED'}")
    print("-" * 65)
    for a in adapters:
        name = a["name"]
        res = results.get(name)
        if isinstance(res, tuple):
            mbps, b, el = res
            total_bytes += b
            mb_s = mbps / 8
            print(f"{name:<18} {'PASS':<10} {mbps:.2f} Mbps ({mb_s:.1f} MB/s) {b/(1024*1024):.1f} MB in {el:.2f}s")
        else:
            print(f"{name:<18} {'FAIL':<10} {str(res):<18}")

    el_all = time.time() - t0_all
    comb_mbps = (total_bytes * 8) / (el_all * 1024 * 1024)
    comb_mb_s = comb_mbps / 8
    print("=" * 65)
    print(f" COMBINED AGGREGATED SPEED: {comb_mbps:.2f} Mbps ({comb_mb_s:.2f} MB/s)")
    print("=" * 65)

def main():
    if len(sys.argv) < 2:
        print("Usage: python duallink_cli.py <command> [args]")
        print("Commands:")
        print("  benchmark                      - Run live multi-link throughput test")
        print("  state                          - Display engine state & active mode")
        print("  mode <speed|streaming|redundant> - Switch bonding algorithm")
        print("  encryption <on|off>            - Toggle tunnel encryption policy")
        print("  show adapters                  - List active uplinks and per-link stats")
        print("  stats                          - View real-time aggregated throughput")
        return

    cmd = sys.argv[1].lower()

    if cmd == "benchmark":
        run_benchmark()

    elif cmd == "state":
        res = send_cmd("state")
        print(json.dumps(res, indent=2))

    elif cmd == "mode":
        if len(sys.argv) < 3:
            print("Error: Specify mode: speed, streaming, or redundant")
            return
        mode = sys.argv[2].lower()
        res = send_cmd("set_mode", {"mode": mode})
        print(json.dumps(res, indent=2))

    elif cmd == "encryption":
        if len(sys.argv) < 3:
            print("Error: Specify 'on' or 'off'")
            return
        enable = sys.argv[2].lower() in ("on", "true", "1")
        res = send_cmd("set_encryption", {"enabled": enable})
        print(json.dumps(res, indent=2))

    elif cmd == "show" and len(sys.argv) > 2 and sys.argv[2].lower() == "adapters":
        res = send_cmd("show_adapters")
        print(json.dumps(res, indent=2))

    elif cmd == "stats":
        res = send_cmd("stats")
        print(json.dumps(res, indent=2))

    else:
        print(f"Unknown command: {' '.join(sys.argv[1:])}")

if __name__ == "__main__":
    main()
