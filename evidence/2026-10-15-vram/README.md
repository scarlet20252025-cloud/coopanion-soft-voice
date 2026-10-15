# VRAM candidate evidence

Author: Asryto. Release validation on the listed devices; other hardware remains unverified.

- `control-*.json` and `progressive-*.json`: same DLL and corpus, separate processes. Per-process GPU PDH counts, 100 ms sampling. Both devices match all 8 baseline PCM hashes.
- `fp16-nvidia.json`: rejected because generated sample counts and PCM changed. This is not included in the production patch.
- `final-nvidia.json`: final capability-enabled DLL integration check.
- `growth-unit-*.json`: real GPU copy tests at every capacity boundary, exact live FP32 values, zero new tails, context limit enforcement. The first test exposed an undersized graph node budget; it was corrected before these passing runs.
- `guard-nvidia-2.5-boundary.json`: failed safety test; 2.5 GiB is not adopted.
- `guard-nvidia-2.75-repeat.json`: two genuine pre-load pressure checkpoints at 2.7941 / 2.7850 GiB. No safety bailout; observed available RAM floor 2.0850 GiB. Test process counters include its own pressure buffers.
- `qwentts-progressive-kv.patch`: applied after the previously documented native patches; optional native test included.

See `docs/VRAM_OPTIMIZATION.md` for scope, Windows memory accounting, reproduction and limitations. The 100 ms observed peak is not an absolute peak guarantee. No model/chat/account data is in this evidence.
