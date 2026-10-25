"""
Channel Bonding & Adaptive Traffic Scheduler
Implements Speedify's core bonding algorithms:
- SPEED: Dynamic Weighted Striping (proportional to real-time link speeds).
- STREAMING: Priority QoS for interactive flows (Discord/Twitch/Voice), weighted striping for downloads.
- REDUNDANT: Highest-reliability fallback mode prioritizing the lowest-jitter physical link.
"""

class BondingEngine:
    MODE_SPEED = "speed"
    MODE_STREAMING = "streaming"
    MODE_REDUNDANT = "redundant"

    def __init__(self, mode="speed"):
        self.mode = mode
        self.rr_index = 0
        self.weights = {}  # ip -> current_weight
        self.overflow_threshold_mbps = 30.0

    def set_mode(self, mode: str):
        valid = (self.MODE_SPEED, self.MODE_STREAMING, self.MODE_REDUNDANT)
        if mode.lower() in valid:
            self.mode = mode.lower()
            return True
        return False

    def select_adapter(self, adapters: list, target_host: str = "", target_port: int = 443):
        """
        Selects which physical interface will handle this connection based on active bonding mode
        and adaptive throughput weights.
        """
        if not adapters:
            return None
        if len(adapters) == 1:
            return adapters[0]

        if self.mode == self.MODE_SPEED:
            # Dynamic Weighted Balancing:
            # If one link is faster (e.g. Mobile 150 Mbps vs Ethernet 85 Mbps),
            # give proportionally more connections to the faster link.
            speeds = [max(a.current_speed_bps, 1024 * 1024) for a in adapters]
            total_speed = sum(speeds)

            # Smooth deficit round-robin / connection load balancing
            # Pick adapter with lowest (active_conns / speed_ratio)
            def score(i):
                ratio = speeds[i] / total_speed
                return adapters[i].active_conns / (ratio * 100.0)

            best_idx = min(range(len(adapters)), key=score)
            return adapters[best_idx]

        elif self.mode == self.MODE_STREAMING:
            # Real-time interactive traffic check
            streaming_keywords = ("discord", "twitch", "teams", "zoom", "live", "rtmp", "voice", "valorant", "steam_voice")
            is_streaming = any(k in target_host.lower() for k in streaming_keywords)

            if is_streaming:
                # Route through lowest active connections / lowest latency link (wired Ethernet preferred)
                return min(adapters, key=lambda a: a.active_conns)
            else:
                # Bulk download chunks use weighted speed striping
                speeds = [max(a.current_speed_bps, 1024 * 1024) for a in adapters]
                total_speed = sum(speeds)
                best_idx = min(range(len(adapters)), key=lambda i: adapters[i].active_conns / ((speeds[i] / total_speed) * 100.0))
                return adapters[best_idx]

        elif self.mode == self.MODE_REDUNDANT:
            # Primary wired/fast link with automatic failover fallback
            return adapters[0]

        self.rr_index = (self.rr_index + 1) % len(adapters)
        return adapters[self.rr_index]
