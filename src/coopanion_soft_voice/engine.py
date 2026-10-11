"""Fixed, user-approved reference voice using Qwen Base and CUDA graphs."""
import os, sys, re
from pathlib import Path
from types import SimpleNamespace

class QwenReferenceEngine:
    def __init__(self, profile):
        import torch
        self.torch=torch
        torch.set_num_threads(4)
        if not torch.cuda.is_available():
            raise RuntimeError('已确认童声音色需要 CUDA GPU')
        runtime=Path(profile['qwenRuntime'])
        os.environ['HF_HUB_OFFLINE']='1'
        os.environ['TOKENIZERS_PARALLELISM']='false'
        from qwen_tts import Qwen3TTSModel
        from .decoder import CUDAGraphDecoder
        self.qwen=Qwen3TTSModel.from_pretrained(str(runtime/'clone-model'),device_map='cuda:0',dtype=torch.bfloat16,attn_implementation='sdpa')
        self.decoder=CUDAGraphDecoder(self.qwen.model,max_seq_len=512)
        self.qwen.model.talker.generate=self.decoder.custom_generate
        self.sample_rate=24000
        self.model=SimpleNamespace(token_hop_len=25)
        self.frontend=SimpleNamespace(spk2info={})
        self.reference=Path(profile['referenceAudio']).resolve()
        self.reference_text=profile['referenceText']
        self.seed=44

    def add_zero_shot_spk(self, text, path, key):
        if Path(path).resolve()!=self.reference:
            raise ValueError('当前声线固定为用户已确认的软糯童声，请使用该参考音频')
        with self.torch.inference_mode():
            self.frontend.spk2info[key]=self.qwen.create_voice_clone_prompt(ref_audio=str(self.reference),ref_text=self.reference_text,x_vector_only_mode=False)

    def inference_cross_lingual(self,text,prompt,zero_shot_spk_id,stream=False,speed=1):
        if speed!=1:
            raise ValueError('已确认童声使用原速 1.0，以免改变语调')
        text=text.split('<|endofprompt|>')[-1].strip()
        # Keep every request within the static cache, including reference tokens.
        pieces=[];current=''
        for sentence in re.split(r'(?<=[。！？!?；;])',text):
            if len(current)+len(sentence)>60 and current:
                pieces.append(current);current=''
            while len(sentence)>60:
                pieces.append(sentence[:60]);sentence=sentence[60:]
            current+=sentence
        if current:pieces.append(current)
        for piece in pieces:
            self.torch.manual_seed(self.seed)
            with self.torch.inference_mode():
                wavs,sr=self.qwen.generate_voice_clone(text=piece,language='Chinese',voice_clone_prompt=self.frontend.spk2info[zero_shot_spk_id],non_streaming_mode=True,max_new_tokens=300)
            if sr!=self.sample_rate:raise RuntimeError('音频采样率不符合播放配置')
            samples=self.torch.from_numpy(wavs[0]).float()
            if not samples.numel() or not self.torch.isfinite(samples).all():
                raise RuntimeError('音频生成失败')
            yield {'tts_speech':samples.unsqueeze(0)}
