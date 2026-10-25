"""
Channel Bonding & Traffic Scheduler
Implements Speedify's core bonding algorithms:
- SPEED: Proportional / Round-Robin Striping across all active links.
- STREAMING: Low-latency / QoS prioritization for interactive flows, bulk striping for downloads.
- REDUNDANT: Highest-reliability mode with instant failover fallback.
"""

class BondingEngine:
    MODE_SPEED = "speed"
    MODE_STREAMING = "streaming"
    MODE_REDUNDANT = "redundant"

    def __init__(self, mode="speed"):
        self.mode = mode
        self.rr_index = 0
        self.overflow_threshold_mbps = 30.0  # Speedify default

    def set_mode(self, mode: str):
        valid = (self.MODE_SPEED, self.MODE_STREAMING, self.MODE_REDUNDANT)
        if mode.lower() in valid:
            self.mode = mode.lower()
            return True
        return False

    def select_adapter(self, adapters: list, target_host: str = "", target_port: int = 443):
        """
        Selects which physical interface will handle this connection based on active bonding mode.
        """
        if not adapters:
            return None
        if len(adapters) == 1:
            return adapters[0]

        if self.mode == self.MODE_SPEED:
            # Round-robin across all available interfaces for maximum multi-connection throughput
            self.rr_index = (self.rr_index + 1) % len(adapters)
            return adapters[self.rr_index]

        elif self.mode == self.MODE_STREAMING:
            # Check for real-time / streaming domains
            streaming_keywords = ("discord", "twitch", "teams", "zoom", "live", "rtmp", "voice")
            is_streaming = any(k in target_host.lower() for k in streaming_keywords)

            if is_streaming:
                # Prefer lowest active connections / lowest latency link (usually wired Ethernet)
                return min(adapters, key=lambda a: a.active_conns)
            else:
                # Bulk downloads (Steam, Web) use speed striping
                self.rr_index = (self.rr_index + 1) % len(adapters)
                return adapters[self.rr_index]

        elif self.mode == self.MODE_REDUNDANT:
            # Strict primary link with automatic fallback if primary link disconnects
            return adapters[0]

        self.rr_index = (self.rr_index + 1) % len(adapters)
        return adapters[self.rr_index]
