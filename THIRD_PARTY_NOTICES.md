# Third-party provenance

- CUDA Graph decoder: [fonty37/qwen3-tts-cudagraph](https://github.com/fonty37/qwen3-tts-cudagraph), commit `09ebe1af7f2b59e9491972570e8a035461dcd4f8`, MIT. Copied decoder with incremental codec callbacks added; upstream notice is in `src/coopanion_soft_voice/licenses/fonty37-MIT.txt` and included in the wheel.
- Qwen3-TTS: [QwenLM/Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS), installed from PyPI `qwen-tts==0.1.1`. Model: [Qwen/Qwen3-TTS-12Hz-0.6B-Base](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base), pinned revision in the manifest. Models are downloaded separately; consult their upstream license and model card.
- Streaming design reference: [andimarafioti/faster-qwen3-tts](https://github.com/andimarafioti/faster-qwen3-tts). Its hardware benchmark is not this project's benchmark. The package is not installed or vendored here.
- Coopanion: [Pal-AI-Lab/Coopanion](https://github.com/Pal-AI-Lab/Coopanion), external desktop application, not redistributed here.
- Coopanion adapter targets [cortico-world-cosyvoice-tts 0.1.11](https://www.npmjs.com/package/cortico-world-cosyvoice-tts), MIT. The plugin itself is installed separately; the integration script applies an explicit, reversible patch. Its upstream MIT notice is retained alongside the integration fixture.
- `soft-child-design-2.wav`: synthetic Qwen VoiceDesign output selected by the user. Prompt: 中文普通话，稚嫩的小女孩声音，音色小巧、软糯、干净，像轻轻和好朋友说话。自然清晰地咬字，语调平缓柔和，句尾轻轻落下，轻松亲切。 Seed 44. Reference text is included in `config.py`. This is not a recording of a real actor.

The project MIT license covers original glue code. It does not relicense upstream dependencies, model weights, or external desktop-pet character assets.
