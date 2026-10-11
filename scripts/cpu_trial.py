"""Isolated CPU INT8 experiment; does not change the installed plugin."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import time


class MemoryStatus(ctypes.Structure):
    _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
        (name, ctypes.c_ulonglong) for name in
        ('total_physical', 'available_physical', 'total_page', 'available_page',
         'total_virtual', 'available_virtual', 'extended')]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--precision', choices=['int8', 'fp32'], default='fp32',
                        help='int8 is a rejected diagnostic configuration, not a usable voice backend')
    args = parser.parse_args()
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        raise OSError('Cannot check available RAM')
    minimum = 7 if args.precision == 'int8' else 6
    report = {'backend': 'pytorch-cpu-' + args.precision, 'threads': 2,
              'available_ram_gib': round(status.available_physical / 2**30, 2),
              'minimum_free_ram_gib': minimum, 'gpu_enabled': False}
    def save():
        (output / 'cpu-trial.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=False), flush=True)
    # FP32 loading and INT8 conversion have a much larger peak than final INT8 weights.
    if status.available_physical < minimum * 2**30:
        report['status'] = 'blocked_insufficient_free_ram'
        save()
        return
    os.environ.update(CUDA_VISIBLE_DEVICES='', HF_HUB_OFFLINE='1', TOKENIZERS_PARALLELISM='false',
                      OMP_NUM_THREADS='2', MKL_NUM_THREADS='2')
    kernel = ctypes.windll.kernel32
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.SetPriorityClass.argtypes = (ctypes.c_void_p, ctypes.c_ulong)
    if not kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x4000):
        raise OSError('Cannot set BelowNormal process priority')
    try:
        import torch
        import soundfile as sf
        import numpy as np
        from qwen_tts import Qwen3TTSModel
        from coopanion_soft_voice.config import reference, REFERENCE_TEXT
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        started = time.perf_counter()
        model = Qwen3TTSModel.from_pretrained(args.model, device_map='cpu',
                    dtype=torch.float32, attn_implementation='sdpa')
        model.model.eval()
        # Keep codec/speaker encoder unchanged; quantize the autoregressive talker only.
        if args.precision == 'int8':
            torch.ao.quantization.quantize_dynamic(model.model.talker, {torch.nn.Linear},
                                               dtype=torch.qint8, inplace=True)
        report['load_seconds'] = round(time.perf_counter()-started, 3)
        print(json.dumps({'stage': 'loaded', 'seconds': report['load_seconds']}), flush=True)
        with torch.inference_mode():
            prompt = model.create_voice_clone_prompt(ref_audio=str(reference()),
                        ref_text=REFERENCE_TEXT, x_vector_only_mode=False)
            torch.manual_seed(44)
            started = time.perf_counter()
            wavs, rate = model.generate_voice_clone(text='我会乖乖等你。', language='Chinese',
                        voice_clone_prompt=prompt, non_streaming_mode=True, max_new_tokens=90)
        seconds = time.perf_counter()-started
        audio = wavs[0]
        if not len(audio) or not np.isfinite(audio).all():
            raise ValueError('Invalid generated audio')
        sf.write(str(output/('cpu-' + args.precision + '.wav')), audio, rate, subtype='PCM_16')
        report.update(status='quarantined_pending_content_and_voice_review', generation_seconds=round(seconds, 3),
                      audio_seconds=len(audio)/rate, rtf=seconds/(len(audio)/rate))
    except Exception as exc:
        report.update(status='failed', error=str(exc))
    save()


if __name__ == '__main__':
    main()
