"""Byte-bounded, process-local cache of completed, exact reference-conditioned PCM.

No text or sound is written to disk. Model shutdown clears all entries.
"""
from collections import OrderedDict


class PCMCache:
    def __init__(self, maximum=4 * 1024**2):
        self.maximum = maximum
        self.entries = OrderedDict()
        self.bytes = self.hits = self.misses = 0

    def get(self, key):
        blocks = self.entries.get(key)
        if blocks is None:
            self.misses += 1
            return None
        self.entries.move_to_end(key)
        self.hits += 1
        return blocks

    def put(self, key, blocks):
        blocks = tuple(blocks)
        size = sum(block.nbytes for block in blocks)
        if not size or size > self.maximum:
            return
        old = self.entries.pop(key, ())
        self.bytes -= sum(block.nbytes for block in old)
        while self.entries and self.bytes + size > self.maximum:
            _, removed = self.entries.popitem(last=False)
            self.bytes -= sum(block.nbytes for block in removed)
        for block in blocks:
            block.setflags(write=False)
        self.entries[key] = blocks
        self.bytes += size

    def clear(self):
        self.entries.clear()
        self.bytes = 0

    def status(self):
        return dict(bytes=self.bytes, maximumBytes=self.maximum, entries=len(self.entries),
                    hits=self.hits, misses=self.misses)
