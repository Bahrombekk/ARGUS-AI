# -*- coding: utf-8 -*-
"""Kadrda odam bor-yo'qligi (YOLOv8n).

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

from config import *



class PersonDetector:
    """Kadrda odam bor-yo'qligi (YOLOv8n, COCO `person` sinfi).

    FAQAT yuz topilmaganda chaqiriladi. Mashinist joyida o'tirib yuzi
    ko'rinib turgan normal holatda bu model umuman ishlamaydi — shuning
    uchun jonli FPS ga ta'sir qilmaydi."""

    def __init__(self, model_path, conf=0.35, every=0.5):
        from ultralytics import YOLO
        self.m = YOLO(model_path)
        self.conf = conf
        self.every = every
        self._last = 0.0
        self.present = True          # boshlanishda "bor" deb hisoblaymiz

    def update(self, frame_bgr, now):
        if now - self._last < self.every:
            return self.present      # oxirgi ma'lum holat (CPU tejash)
        self._last = now
        try:
            r = self.m.predict(source=frame_bgr, conf=self.conf, classes=[0],
                               device="cpu", verbose=False)
            self.present = bool(r and r[0].boxes is not None and len(r[0].boxes))
        except Exception:
            pass                     # xatoda oxirgi holat saqlanadi
        return self.present
