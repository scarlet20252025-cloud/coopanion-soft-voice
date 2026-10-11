from .engine import QwenReferenceEngine

class StreamEngine(QwenReferenceEngine):
    def synthesize_stream(self,text,key,on_audio,chunk_frames=8,on_complete=None):
        torch=self.torch
        items=self.frontend.spk2info[key]
        ref=items[0].ref_code
        pending=[];history=ref.to(self.qwen.device)
        first=True
        def codec_hook(codes,final):
            nonlocal history,first
            if codes is not None:pending.append(codes)
            if len(pending)<chunk_frames and not final:return
            if not pending:
                if final and on_complete:on_complete()
                return
            new=torch.cat(pending,dim=0);pending.clear()
            # Retain full causal history to minimize boundary differences.
            context=history
            window=torch.cat([context,new],dim=0)
            wavs,sr=self.qwen.model.speech_tokenizer.decode([{'audio_codes':window}])
            audio=wavs[0][len(context)*1920:]
            if len(audio)!=len(new)*1920:raise RuntimeError('流式解码长度异常')
            on_audio(audio,sr)
            history=torch.cat([history,new],dim=0);first=False
            if final and on_complete:on_complete()
        self.decoder.on_codec=codec_hook
        try:
            torch.manual_seed(self.seed)
            with torch.inference_mode():
                return self.qwen.generate_voice_clone(text=text,language='Chinese',voice_clone_prompt=items,non_streaming_mode=True,max_new_tokens=300)
        finally:self.decoder.on_codec=None
