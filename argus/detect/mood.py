# -*- coding: utf-8 -*-
"""Kayfiyat aniqlash (FER+ ONNX).

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

import collections
import cv2
import numpy as np
from config import *



class MoodDetector:
    """Kayfiyat — FER+ emotion CNN (ONNX, 8 hissiyot). Yuz MediaPipe bilan topiladi,
    kesib olinib 64x64 kulrang qilinади va modelга beriladi. CPU tejash uchun har
    `every` s da bir marta; natija oxirgi bir necha o'lchov medianasi (barqaror)."""
    FER = ['neutral', 'happiness', 'surprise', 'sadness', 'anger', 'disgust', 'fear', 'contempt']
    UZ = {'neutral': 'betaraf', 'happiness': 'xursand', 'surprise': 'hayrat',
          'sadness': 'xafa', 'anger': 'asabiy', 'disgust': 'jirkanish',
          'fear': "qo'rquv", 'contempt': 'nafrat'}

    def __init__(self, task_path, onnx_path, every=0.4):
        import mediapipe as mp
        from mediapipe.tasks.python import vision
        from mediapipe.tasks.python.core.base_options import BaseOptions
        import onnxruntime as ort
        self._mp = mp
        opt = vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(task_path)),
            running_mode=vision.RunningMode.IMAGE, num_faces=1)
        self.lm = vision.FaceLandmarker.create_from_options(opt)
        self.sess = ort.InferenceSession(str(onnx_path), providers=['CPUExecutionProvider'])
        self.inp = self.sess.get_inputs()[0].name
        self.every = every; self._last = 0.0
        self.mood = "-"; self._recent = collections.deque(maxlen=6)

    def update(self, frame_bgr, now):
        if now - self._last < self.every:
            return self.mood
        self._last = now
        try:
            h, w = frame_bgr.shape[:2]
            mpimg = self._mp.Image(image_format=self._mp.ImageFormat.SRGB,
                                   data=cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB))
            res = self.lm.detect(mpimg)
            if not res.face_landmarks:
                return self.mood
            xs = [p.x for p in res.face_landmarks[0]]
            ys = [p.y for p in res.face_landmarks[0]]
            x1, x2 = int(min(xs)*w), int(max(xs)*w)
            y1, y2 = int(min(ys)*h), int(max(ys)*h)
            mx, my = int((x2-x1)*0.15), int((y2-y1)*0.15)
            x1, y1 = max(0, x1-mx), max(0, y1-my)
            x2, y2 = min(w, x2+mx), min(h, y2+my)
            crop = frame_bgr[y1:y2, x1:x2]
            if crop.size == 0:
                return self.mood
            gray = cv2.equalizeHist(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY))
            face = cv2.resize(gray, (64, 64)).astype(np.float32).reshape(1, 1, 64, 64)
            out = self.sess.run(None, {self.inp: face})[0][0]
            emo = self.FER[int(np.argmax(out))]
            self._recent.append(self.UZ.get(emo, 'betaraf'))
            self.mood = max(set(self._recent), key=self._recent.count)
        except Exception:
            pass
        return self.mood
