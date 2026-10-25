"""
DualLink CLI Management Utility
Connects to DualLink daemon via local IPC (127.0.0.1:9335) for real-time control.
"""

import sys
import socket
import json

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

def main():
    if len(sys.argv) < 2:
        print("Usage: python duallink_cli.py <command> [args]")
        print("Commands:")
        print("  state                          - Display engine state & active mode")
        print("  mode <speed|streaming|redundant> - Switch bonding algorithm")
        print("  encryption <on|off>            - Toggle tunnel encryption policy")
        print("  show adapters                  - List active uplinks and per-link stats")
        print("  stats                          - View real-time aggregated throughput")
        return

    cmd = sys.argv[1].lower()

    if cmd == "state":
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
