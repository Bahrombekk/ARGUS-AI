# -*- coding: utf-8 -*-
"""Kadrda odam bor-yo'qligi (YOLOv8n).

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

from argus.settings import *   # noqa: F401,F403



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
        # 2026-09-29: haydovchi o'rnidan turib qo'l uzatganda boshi kadr tepasidan
        # chiqib ketadi -> "Yuz ko'rinmayapti" yolg'on buzilish bo'lardi (10:56,
        # 47 km/s). Odam qutisi kadr TEPASIGA tegsa va baland bo'lsa -> 'tik turgan'.
        self.standing = False
        self.boxes = []              # (x1, y1, x2, y2) piksel

    def update(self, frame_bgr, now):
        if now - self._last < self.every:
            return self.present      # oxirgi ma'lum holat (CPU tejash)
        self._last = now
        try:
            r = self.m.predict(source=frame_bgr, conf=self.conf, classes=[0],
                               device="cpu", verbose=False)
            h, w = frame_bgr.shape[:2]
            allb = ([tuple(int(v) for v in bx.xyxy[0].tolist()) for bx in r[0].boxes]
                    if (r and r[0].boxes is not None) else [])
            # 2026-09-29 17:34: bo'sh o'rindiqda devordagi kichik rasm (91x100 px, ~1%
            # maydon) "odam" deb topilib, "Yuz ko'rinmayapti" yolg'on ketdi. Haydovchi
            # kadrda kamida PERSON_MIN_H balandlikda va markaziy zonada bo'ladi.
            self.boxes = [(x1, y1, x2, y2) for (x1, y1, x2, y2) in allb
                          if (y2 - y1) >= PERSON_MIN_H * h
                          and PERSON_ZONE_X[0] * w <= (x1 + x2) / 2.0 <= PERSON_ZONE_X[1] * w]
            self.present = bool(self.boxes)
            self.standing = any(y1 <= STAND_TOP_FRAC * h and (y2 - y1) >= STAND_MIN_H * h
                                for (x1, y1, x2, y2) in self.boxes)
        except Exception:
            pass                     # xatoda oxirgi holat saqlanadi
        return self.present
