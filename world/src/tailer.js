import { closeSync, existsSync, openSync, readFileSync, readSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';
const RUN_ID = /^r-\d{8}-\d{6}-[0-9a-f]{4}$/;

export function currentRun(dataDir, pid = process.pid) {
  const root = join(dataDir, 'runs'), index = join(root, 'index.jsonl');
  if (existsSync(index)) {
    let current = null;
    for (const line of readFileSync(index, 'utf8').split(/\r?\n/)) {
      try {
        const e = JSON.parse(line);
        if (e.pid === pid && e.startedAt && RUN_ID.test(e.run)) current = e.run;
      } catch { /* A partially appended index line is retried on the next poll. */ }
    }
    return current; // Never choose another process's run.
  }
  if (!existsSync(root)) return null;
  return readdirSync(root).filter(name => RUN_ID.test(name)).sort().at(-1) ?? null;
}

export class ToolCallTailer {
  constructor(dataDir, onEntry, log, options = {}) {
    Object.assign(this, { dataDir, onEntry, log, pid: options.pid ?? process.pid,
      checkpoint: options.checkpoint });
    this.file = null;
    this.run = null;
    this.offset = 0;
    this.skipPartial = false;
    this.initialized = false;
  }

  poll() {
    const run = currentRun(this.dataDir, this.pid);
    if (!run) return;
    const file = join(this.dataDir, 'runs', run, 'toolcalls.jsonl');
    if (this.run !== run) {
      const first = !this.initialized;
      this.run = run;
      this.file = file;
      // Skip pre-enable history once. A file that appears later starts at zero.
      this.offset = first && existsSync(file) ? statSync(file).size : 0;
      this.skipPartial = false;
      if (first && this.offset > 0) {
        const fd = openSync(file, 'r'), byte = Buffer.alloc(1);
        try { readSync(fd, byte, 0, 1, this.offset - 1); } finally { closeSync(fd); }
        this.skipPartial = byte[0] !== 10;
      }
      this.initialized = true;
      this.log?.info?.('轻核语音 · Qwen3-TTS 超轻量高速语音引擎 正在监听 ' + file);
      this.save();
    }
    if (!existsSync(file)) return;
    const size = statSync(file).size;
    if (size < this.offset) { this.offset = 0; this.skipPartial = false; }
    if (size === this.offset) return;
    const fd = openSync(file, 'r');
    try {
      // Decode complete byte lines only, preserving UTF-8 across filesystem reads.
      const buf = Buffer.alloc(Math.min(size - this.offset, 256 * 1024));
      const count = readSync(fd, buf, 0, buf.length, this.offset);
      let start = 0;
      for (let end = 0; end < count; end++) {
        if (buf[end] !== 10) continue;
        if (this.skipPartial) {
          this.skipPartial = false;
          this.offset += end + 1 - start;
          start = end + 1;
          this.save();
          continue;
        }
        const raw = buf.subarray(start, end).toString('utf8').trim();
        let entry;
        try { entry = raw ? JSON.parse(raw) : null; }
        catch (err) { this.log?.warn?.('略过损坏的 toolcall: ' + err.message); }
        // Backpressure leaves this line unread until there is queue capacity.
        if (entry && entry.run === run && this.onEntry(entry) === false) break;
        this.offset += end + 1 - start;
        start = end + 1;
        this.save();
      }
      if (start === 0 && count === 256 * 1024 && !buf.includes(10)) {
        this.log?.warn?.('toolcall 超过 256 KiB，略过超长记录。');
        this.offset += count;
        this.skipPartial = true;
        this.save();
      }
    } finally { closeSync(fd); }
  }
  skipHistory() {
    this.run = null;
    this.initialized = false;
    this.poll();
  }
  save() { this.checkpoint?.({ run: this.run, offset: this.offset }); }
}
