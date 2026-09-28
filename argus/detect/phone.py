# -*- coding: utf-8 -*-
"""Telefon uchun alohida o'rgatilgan model.

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

from config import *



class PhoneDetector:
    """Telefon uchun alohida o'rgatilgan model (yolov8n, 1 sinf).

    safedrive.pt ning telefon sinfi o'rniga ishlatiladi. Har kadrda emas,
    `every` soniyada bir marta chaqiriladi — oxirgi natija keshda turadi."""

    def __init__(self, model_path, conf=0.25, every=0.25):
        from ultralytics import YOLO
        self.m = YOLO(model_path)
        self.conf = conf
        self.every = every
        self._last = 0.0
        self.found = False
        self.score = 0.0
        self.boxes = []          # HUD da chizish uchun

    def update(self, frame_bgr, now):
        if now - self._last < self.every:
            return self.found    # kesh (CPU tejash)
        self._last = now
        try:
            r = self.m.predict(source=frame_bgr, conf=self.conf,
                               device="cpu", verbose=False)[0]
            self.boxes = [([int(v) for v in b.xyxy[0].tolist()], float(b.conf[0]))
                          for b in r.boxes]
            self.found = bool(self.boxes)
            self.score = max((c for _, c in self.boxes), default=0.0)
        except Exception:
            pass                 # xatoda oxirgi holat saqlanadi
        return self.found
