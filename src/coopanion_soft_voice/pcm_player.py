from collections import deque
import threading,time
import numpy as np
import sounddevice as sd

class PCMPlayer:
    """One continuous output device, fed independently of GPU generation."""
    def __init__(self,rate=24000,volume=1.0,on_start=None):
        self.rate=rate;self.volume=volume;self.on_start=on_start
        self.queue=deque();self.lock=threading.Lock();self.finished=threading.Event()
        self.producer_done=False;self.stream=None;self.underrun_frames=0;self.device_underflows=0
        self.first_audio_at=None;self.samples=0

    def _callback(self,out,frames,timing,status):
        out.fill(0)
        if status.output_underflow:self.device_underflows+=1
        written=0
        with self.lock:
            while written<frames and self.queue:
                a=self.queue[0];n=min(frames-written,len(a))
                out[written:written+n,0]=a[:n]
                if n==len(a):self.queue.popleft()
                else:self.queue[0]=a[n:]
                written+=n
            ended=self.producer_done and not self.queue
        if written and self.first_audio_at is None:self.first_audio_at=time.perf_counter()
        if written<frames and not self.producer_done:self.underrun_frames+=frames-written
        if ended:raise sd.CallbackStop

    def push(self,a,rate):
        if rate!=self.rate:raise ValueError('采样率发生变化')
        a=np.asarray(a,dtype=np.float32)
        if not np.isfinite(a).all():raise ValueError('音频包含无效采样')
        with self.lock:self.queue.append(np.clip(a*self.volume,-1,1));self.samples+=len(a)
        if self.stream is None:
            self.stream=sd.OutputStream(samplerate=self.rate,channels=1,dtype='float32',blocksize=480,latency='low',callback=self._callback,finished_callback=self.finished.set)
            self.stream.start()
            if self.on_start:self.on_start()

    def finish(self):
        self.producer_done=True
        if self.stream:
            if not self.finished.wait(self.samples/self.rate+10):raise TimeoutError('连续播放未结束')
            self.stream.close();self.stream=None

    def abort(self):
        self.producer_done=True
        if self.stream:self.stream.abort();self.stream.close();self.stream=None
