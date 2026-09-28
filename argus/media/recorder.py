# -*- coding: utf-8 -*-
"""Rasm va ovozli video yozib olish.

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

import os
import time
import wave
import threading
import subprocess
import collections
import cv2
import numpy as np
from config import *
try:
    import sounddevice as sd
except Exception:
    sd = None



def pick_mic():
    """Haqiqiy mikrofonni tanlaydi. AUDIO_DEVICE berilса — o'sha; aks holда nomida
    'microphone' bo'lgan birinchi kirish qurilmasi (standart qurilma ba'zан
    sichqoncha/dummy bo'lиб jimlik yozadi)."""
    if sd is None:
        return None
    if AUDIO_DEVICE is not None:
        return AUDIO_DEVICE
    try:
        for i, d in enumerate(sd.query_devices()):
            if d['max_input_channels'] > 0 and 'microphon' in d['name'].lower():
                return i
    except Exception:
        pass
    return None                                  # topilmasa — standart


class Recorder:
    """Rasm (.jpg) va video (.mp4) yozib olish — MIKROFON OVOZI bilan.
    Video — hodisa atrofidagi klip: PRE_SECONDS oldingi kadrlar (bufer) + hodisa
    + POST_SECONDS keyin. Ovoz alohida oqimda yoziladi, klip yopilганda ffmpeg
    bilan videoga birlashtiriladi (jonli oyna qotmasin — mux fon oqimда)."""
    def __init__(self, out_dir, fps, pre, post, audio=True):
        os.makedirs(out_dir, exist_ok=True)
        self.dir = out_dir; self.fps = fps; self.pre = pre; self.post = post
        self.buf = collections.deque()          # (t, frame) — pre-roll bufer
        self.writer = None; self.path = None; self.active_until = 0.0
        self.clip_start = 0.0; self.wfps = fps
        self.on_clip = None                     # klip tayyor bo'lganda(path) chaqiriladi
        # ── Ovoz (mikrofon) ──
        self.audio_ok = False
        self.abuf = collections.deque()         # (t, int16 ndarray)
        self._astream = None
        if audio and sd is not None:
            try:
                mic = pick_mic()
                self._astream = sd.InputStream(
                    samplerate=AUDIO_RATE, channels=AUDIO_CH, dtype='int16',
                    device=mic, callback=self._acb)
                self._astream.start(); self.audio_ok = True
                nm = sd.query_devices(mic)['name'] if mic is not None else "standart"
                print(f"Ovoz yozish: mikrofon YOQILDI (indeks={mic}, {nm[:35]})")
            except Exception as e:
                print("Ovoz yozish yo'q (mikrofon xatosi):", e)

    def _acb(self, indata, frames, tinfo, status):
        t = time.monotonic()
        self.abuf.append((t, indata.copy()))
        while self.abuf and t - self.abuf[0][0] > self.pre + 45:
            self.abuf.popleft()

    def push(self, frame, now):
        self.buf.append((now, frame))
        while self.buf and now - self.buf[0][0] > self.pre:
            self.buf.popleft()

    def _open(self, w, h):
        ts = time.strftime("%Y%m%d_%H%M%S")
        for fourcc, ext in ((cv2.VideoWriter_fourcc(*'mp4v'), 'mp4'),
                            (cv2.VideoWriter_fourcc(*'MJPG'), 'avi')):
            path = os.path.join(self.dir, f"rec_{ts}.{ext}")
            wr = cv2.VideoWriter(path, fourcc, self.wfps, (w, h))
            if wr.isOpened():
                self.writer = wr; self.path = path
                self.clip_start = self.buf[0][0] if self.buf else time.monotonic()
                for _, f in self.buf:            # pre-roll (oldingi kadrlar)
                    wr.write(f)
                print("Video yozuv boshlandi:", os.path.basename(path))
                return
        print("XATO: video writer ochilmadi")

    def trigger(self, w, h, now, fps=None):
        if self.writer is None:
            self.wfps = max(5.0, min(30.0, float(fps))) if fps else self.fps
            self._open(w, h)
        self.active_until = now + self.post

    def step(self, frame, now):
        if self.writer is not None:
            self.writer.write(frame)
            if now >= self.active_until:
                self.writer.release()
                path, start, end = self.path, self.clip_start, now
                self.writer = None; self.path = None
                print("Video saqlandi:", os.path.basename(path))
                if self.audio_ok and path.endswith(".mp4"):
                    threading.Thread(target=self._mux, args=(path, start, end),
                                     daemon=True).start()
                elif self.on_clip:                # ovozsiz — to'g'ridan yuborish
                    try: self.on_clip(path)
                    except Exception: pass

    def _mux(self, video_path, start_t, end_t):
        """Klip ovozini kesib olib, ffmpeg bilan videoga birlashtiradi. So'ng
        (ovoz bo'lsin-bo'lmasin) on_clip callback — Telegram'ga yuborish uchun."""
        try:
            # OpenCV 'mp4v' (MPEG-4 Part 2) bilan yozadi. Telegram uni qayta
            # kodlab ko'rsatadi, lekin BRAUZER ijro eta olmaydi — saytda video
            # ochilmaydi. Shuning uchun H.264 ga o'tkazamiz.
            #   -pix_fmt yuv420p   keng moslik uchun majburiy
            #   -movflags +faststart  indeks (moov) fayl BOSHIGA ko'chadi,
            #                      shunda brauzer to'liq yuklamasdan boshlaydi
            vargs = (['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23',
                      '-pix_fmt', 'yuv420p', '-movflags', '+faststart']
                     if VIDEO_H264 else ['-c:v', 'copy'])

            blocks = [a for (t, a) in list(self.abuf) if start_t - 0.1 <= t <= end_t + 0.25]
            outp = video_path[:-4] + "_av.mp4"
            wavp = None

            if blocks:
                data = np.concatenate(blocks, axis=0)
                wavp = video_path[:-4] + ".wav"
                with wave.open(wavp, 'wb') as w:
                    w.setnchannels(AUDIO_CH); w.setsampwidth(2); w.setframerate(AUDIO_RATE)
                    w.writeframes(data.tobytes())
                cmd = ['ffmpeg', '-y', '-i', video_path, '-i', wavp,
                       *vargs, '-c:a', 'aac', '-shortest', outp]
                what = "ovoz + H.264" if VIDEO_H264 else "ovoz"
            elif VIDEO_H264:
                # Ovoz yo'q, lekin kodekni baribir almashtiramiz
                cmd = ['ffmpeg', '-y', '-i', video_path, *vargs, outp]
                what = "H.264"
            else:
                cmd = None

            if cmd:
                r = subprocess.run(cmd, capture_output=True)
                if r.returncode == 0 and os.path.exists(outp):
                    os.remove(video_path)
                    if wavp: os.remove(wavp)
                    os.replace(outp, video_path)
                    print(f"  {what} qo'shildi:", os.path.basename(video_path))
                else:
                    err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
                    print("  ffmpeg xatosi:", err[-1][:90] if err else f"kod {r.returncode}")
                    for p in (wavp, outp):
                        if p:
                            try: os.remove(p)
                            except OSError: pass
        except Exception as e:
            print("  ovoz muxlash xatosi:", e)
        finally:
            if self.on_clip:
                try: self.on_clip(video_path)
                except Exception: pass

    def is_recording(self):
        return self.writer is not None

    def snapshot(self, frame):
        """Berilgan kadrni rasm qilib saqlaydi.

        Qaysi kadr olinishini chaqiruvchi hal qiladi — bu yerdagi bufer
        HUD chizilgan kadrlarni saqlaydi va dalil uchun yaramaydi."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self.dir, f"snap_{ts}.jpg")
        cv2.imwrite(path, frame)
        print("Rasm saqlandi:", os.path.basename(path))
        return path

    def close(self):
        if self.writer is not None:
            self.writer.release()
            path, start, end = self.path, self.clip_start, time.monotonic()
            self.writer = None; self.path = None
            print("Video saqlandi:", os.path.basename(path))
            if self.audio_ok and path.endswith(".mp4"):
                self._mux(path, start, end)      # chiqishда — sinxron (thread emas)
            elif self.on_clip:
                try: self.on_clip(path)
                except Exception: pass
        if self._astream is not None:
            try: self._astream.stop(); self._astream.close()
            except Exception: pass
