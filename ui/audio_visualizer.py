"""
ui/audio_visualizer.py
Reactive audio visualizer for JarvisX — FFT bar animation.
"""
from __future__ import annotations
import threading, time, math, logging
from typing import Optional
import numpy as np

log = logging.getLogger("audio_visualizer")

_BG="_020D14"; _C_CYAN="#00DCFF"; _C_DIM="#0A2030"
_BARS=32; _W,_H=400,80


class AudioVisualizer:
    def __init__(self):
        self._root=None; self._canvas=None; self._running=False
        self._thread:Optional[threading.Thread]=None
        self._audio_thread:Optional[threading.Thread]=None
        self._magnitudes=np.zeros(_BARS); self._lock=threading.Lock()
        self._anim_tick=0; self._speaking=False

    def start(self):
        self._running=True
        self._thread=threading.Thread(target=self._run,daemon=True,name="audio-viz")
        self._thread.start()
        self._audio_thread=threading.Thread(target=self._capture_audio,daemon=True,name="audio-cap")
        self._audio_thread.start()

    def stop(self): self._running=False
    def set_speaking(self,speaking:bool): self._speaking=speaking

    def push_audio_chunk(self,chunk:np.ndarray,sample_rate:int=22050):
        if chunk is None or len(chunk)==0: return
        try:
            fft=np.abs(np.fft.rfft(chunk,n=_BARS*2))[:_BARS]
            fft_norm=fft/(np.max(fft)+1e-8)
            with self._lock:
                self._magnitudes=0.4*fft_norm+0.6*self._magnitudes
        except Exception: pass

    def _capture_audio(self):
        try:
            import sounddevice as sd
            sr=22050; block=int(sr*0.05)
            def cb(indata,frames,t,status):
                if indata is not None: self.push_audio_chunk(indata[:,0],sr)
            with sd.InputStream(samplerate=sr,channels=1,blocksize=block,callback=cb):
                while self._running: time.sleep(0.1)
        except Exception:
            while self._running:
                time.sleep(0.05); self._anim_tick+=1
                if self._speaking:
                    t=self._anim_tick*0.15
                    syn=np.array([abs(math.sin(t+i*0.5)*0.7+0.3*abs(math.sin(t*2+i))) for i in range(_BARS)])
                    with self._lock: self._magnitudes=0.35*syn+0.65*self._magnitudes
                else:
                    with self._lock: self._magnitudes*=0.88

    def _run(self):
        import tkinter as tk
        self._root=tk.Tk()
        self._root.title("JarvisX Audio"); self._root.overrideredirect(True)
        self._root.attributes("-topmost",True,"-alpha",0.90)
        self._root.configure(bg="#020D14")
        sw=self._root.winfo_screenwidth(); sh=self._root.winfo_screenheight()
        x=(sw-_W)//2; y=sh-_H-240
        self._root.geometry(f"{_W}x{_H}+{x}+{y}")
        self._canvas=tk.Canvas(self._root,width=_W,height=_H,bg="#020D14",highlightthickness=0)
        self._canvas.pack(); self._root.after(50,self._update); self._root.mainloop()

    def _update(self):
        if not self._running: return
        try: self._draw()
        except Exception as e: log.debug(f"AudioVisualizer draw error: {e}")
        if self._root: self._root.after(50,self._update)

    def _draw(self):
        c=self._canvas; c.delete("all")
        with self._lock: mags=self._magnitudes.copy()
        bar_w=_W/_BARS; cy=_H//2; self._anim_tick+=1
        for i,mag in enumerate(mags):
            x=i*bar_w; h=max(2,int(mag*(_H-10)))
            cd=abs(i-_BARS//2)/(_BARS//2)
            r=int(255*cd); g=int(220*(1-cd*0.5)); b=int(255*(1-cd))
            color=f"#{r:02x}{g:02x}{b:02x}"
            c.create_rectangle(x+1,cy-h,x+bar_w-1,cy+h,fill=color,outline="")
        c.create_line(0,cy,_W,cy,fill=_C_DIM,width=1)
        c.create_rectangle(0,0,_W-1,_H-1,outline=_C_DIM,width=1)
