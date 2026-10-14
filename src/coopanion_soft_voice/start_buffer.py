"""Adapt the initial PCM reserve to measured production cadence, without changing samples."""
class StartBuffer:
    def __init__(self, rate=24000, fixed=False):
        self.rate = rate; self.fixed = fixed
        self.first = None; self.previous = None; self.first_samples = 0
        self.samples = 0; self.chunks = 0; self.max_gap = 0
        self.target_seconds = 1.2
        self.production_rtf = None

    def feed(self, count, now):
        self.samples += count; self.chunks += 1
        if self.first is None:
            self.first = now; self.first_samples = count
        else:
            self.max_gap = max(self.max_gap, now-self.previous)
        self.previous = now
        produced = (self.samples-self.first_samples)/self.rate
        if not self.fixed and self.chunks >= 3 and produced > 0:
            # Exclude prefill: only inter-chunk production competes with playback.
            rtf = (now-self.first)/produced
            self.production_rtf = rtf
            self.target_seconds = min(1.2, max(.32, .16+2*self.max_gap+2*max(0, rtf-.75)))
        return self.samples/self.rate >= self.target_seconds
