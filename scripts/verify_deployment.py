"""Actual muted playback verification; requires RAM and the selected Vulkan GPU."""
import argparse,json,time
from pathlib import Path
import numpy as np,soundfile as sf
from coopanion_soft_voice.native_engine import NativeEngine
from coopanion_soft_voice.playback import speak
from coopanion_soft_voice.memory_metrics import snapshot
from coopanion_soft_voice.config import REFERENCE_SHA256


def verify(runtime,output,playback_mode='auto',device_name=None):
    runtime=Path(runtime).resolve()
    if not runtime.is_dir():raise ValueError('--runtime must be the extracted runtime DIRECTORY, not a file')
    if Path(output).exists() and not Path(output).is_dir():raise ValueError('--output must be a DIRECTORY, not a JSON/WAV file')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
    start=time.perf_counter();model=NativeEngine(runtime,device_name=device_name)
    loaded_ms=round((time.perf_counter()-start)*1000);chunks=[]
    original=model.synthesize_stream
    def capture(text,key,receive,on_complete=None):
        def forwarding(a,rate):chunks.append(a.copy());receive(a,rate)
        original(text,key,forwarding,on_complete)
    model.synthesize_stream=capture
    try:
        text='我在这里陪你呀，慢慢来，不着急。我们一起把今天的事情做好，再安心休息。'
        playback=speak(model,text,'accepted',0,1,'deploy-verification',lambda *a,**k:None,runtime,playback_mode)
        audio=np.concatenate(chunks)
        if not np.isfinite(audio).all() or not len(audio):raise RuntimeError('Invalid generated audio')
        if playback['voiceConditioning']['referenceSha256']!=REFERENCE_SHA256:raise RuntimeError('Unexpected reference voice')
        sf.write(output/'deployment-preview.wav',audio,24000,subtype='PCM_16')
        report={'ok':True,'model':'Qwen3-TTS 0.6B Base Q8_0','device':model.device_name,
                'loadMs':loaded_ms,'playback':playback,'processMemory':snapshot(),
                'audioFile':str(output/'deployment-preview.wav'),'subjectiveVoiceQualityApproved':False,
                'playbackHealth':{'smooth':playback['smoothPlayback'],
                    'streamingRecommended':playback['realTimeFactor']<.8 and playback['smoothPlayback'],
                    'effectiveMode':playback['effectivePlaybackMode'],
                    'note':'Buffered playback trades startup delay for continuity; ok means execution succeeded, not a speed or listening-quality guarantee.'}}
        (output/'deployment-check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False))
        return report
    finally:model.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',required=True);p.add_argument('--output',required=True)
    p.add_argument('--playback-mode',choices=['auto','stream','buffered'],default='auto')
    p.add_argument('--device-name',help='Explicit Vulkan GPU name (integrated or discrete); never chosen automatically')
    a=p.parse_args()
    if not Path(a.runtime).is_dir():p.error('--runtime must be a runtime DIRECTORY')
    if Path(a.output).exists() and not Path(a.output).is_dir():p.error('--output must be a DIRECTORY, not a file')
    verify(a.runtime,a.output,a.playback_mode,a.device_name)
