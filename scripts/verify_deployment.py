"""Actual muted playback verification; requires RAM and the selected integrated GPU."""
import argparse,json,time
from pathlib import Path
import numpy as np,soundfile as sf
from coopanion_soft_voice.native_engine import NativeEngine
from coopanion_soft_voice.playback import speak
from coopanion_soft_voice.memory_metrics import snapshot
from coopanion_soft_voice.config import REFERENCE_SHA256


def verify(runtime,output):
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter();model=NativeEngine(runtime)
    loaded_ms=round((time.perf_counter()-start)*1000);chunks=[]
    original=model.synthesize_stream
    def capture(text,key,receive,on_complete=None):
        def forwarding(a,rate):chunks.append(a.copy());receive(a,rate)
        original(text,key,forwarding,on_complete)
    model.synthesize_stream=capture
    try:
        text='我在这里陪你呀，慢慢来，不着急。我们一起把今天的事情做好，再安心休息。'
        playback=speak(model,text,'accepted',0,1,'deploy-verification',lambda *a,**k:None,runtime)
        audio=np.concatenate(chunks)
        if not np.isfinite(audio).all() or not len(audio):raise RuntimeError('Invalid generated audio')
        if playback['voiceConditioning']['referenceSha256']!=REFERENCE_SHA256:raise RuntimeError('Unexpected reference voice')
        sf.write(output/'deployment-preview.wav',audio,24000,subtype='PCM_16')
        report={'ok':True,'model':'Qwen3-TTS 0.6B Base Q8_0','device':model.device_name,
                'loadMs':loaded_ms,'playback':playback,'processMemory':snapshot(),
                'audioFile':str(output/'deployment-preview.wav'),'subjectiveVoiceQualityApproved':False}
        (output/'deployment-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
        return report
    finally:model.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();verify(a.runtime,a.output)
