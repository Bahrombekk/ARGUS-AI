# -*- coding: utf-8 -*-
"""Model o'rgatish uchun toza kadr yig'ish.

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

import os
import time
import cv2
from config import *



class DatasetCollector:
    """Toza (chizilmagan) kadrlarni model o'rgatish uchun saqlaydi.

    Fayl nomi oldiga qo'yiladigan belgi:
      bg_  — oddiy fon kadri (odatda buzilishsiz) → QIYIN NEGATIV manbai
      ev_  — hodisa paytidagi kadr               → pozitiv misol nomzodi
    """

    def __init__(self, dirpath, every, max_files):
        self.dir = dirpath
        self.every = every
        self.max = max_files
        self._last = 0.0
        os.makedirs(dirpath, exist_ok=True)
        self.n = len([f for f in os.listdir(dirpath) if f.endswith(".jpg")])

    def maybe(self, frame, now, event=False):
        if self.n >= self.max:
            return False
        # Hodisa kadrlari ham cheklanadi: aks holda bitta 5 soniyalik hodisa
        # 100+ deyarli bir xil kadr beradi — o'rgatishga foydasi yo'q, faqat
        # chegarani to'ldiradi. Hodisada tezroq (1 s), fonda sekinroq.
        gap = EVENT_EVERY if event else self.every
        if now - self._last < gap:
            return False
        self._last = now
        tag = "ev" if event else "bg"
        p = os.path.join(self.dir,
                         f"{tag}_{time.strftime('%Y%m%d_%H%M%S')}_{self.n:05d}.jpg")
        try:
            cv2.imwrite(p, frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            self.n += 1
            return True
        except Exception:
            return False
