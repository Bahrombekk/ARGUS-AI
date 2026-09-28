# -*- coding: utf-8 -*-
"""Kamerani topish, kutish va holat ekrani.

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

import cv2
import numpy as np
import time
from config import *
from argus.hud import text



def open_any_camera():
    """Ulangan HAR QANDAY kamerani topadi (0..CAMERA_SCAN-1 skanlanadi, USB ham).
    Topib, birinchi kadrni ham o'qib tekshiradi. Topilmasa (None, -1)."""
    for idx in range(CAMERA_SCAN):
        for be in (cv2.CAP_DSHOW, cv2.CAP_MSMF, 0):
            try:
                cap = cv2.VideoCapture(idx, be)
            except Exception:
                continue
            if cap.isOpened():
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAM_WIDTH)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAM_HEIGHT)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                ok, _ = cap.read()
                if ok:
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    print(f"Kamera topildi: indeks {idx} ({w}x{h})")
                    return cap, idx
                cap.release()
    return None, -1


def status_screen(win, w, h, title, sub=""):
    """Kamera yo'q/uzilган paytда ko'rsatiladigan ekran."""
    img = np.full((h, w, 3), 26, dtype=np.uint8)
    cv2.putText(img, "ARGUS AI", (int(w/2)-90, int(h/2)-60),
                cv2.FONT_HERSHEY_SIMPLEX, 1.1, (235,190,70), 2, cv2.LINE_AA)
    cv2.putText(img, title, (int(w/2)-len(title)*8, int(h/2)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (60,70,240), 2, cv2.LINE_AA)
    if sub:
        cv2.putText(img, sub, (int(w/2)-len(sub)*5, int(h/2)+40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (170,170,175), 1, cv2.LINE_AA)
    cv2.imshow(win, img)


def wait_for_camera(win, telegram=None, stop_event=None, notify=True):
    """Kamera ulanmaguncha kutadi. Topilsa (cap, idx). Headless'да cheksiz kutadi
    (faqat stop_event to'xtatadi); ekranli rejimда 'q'/oyna yopilsa (None, -1)."""
    if telegram is not None and notify:
        telegram.send(f"⚠️ [{DEVICE_NAME}] Kamera uzildi — qayta ulanish kutilmoqda.")
    print("Kamera kutilmoqda (USB kamerani ulang)...")
    while stop_event is None or not stop_event.is_set():
        cap, idx = open_any_camera()
        if cap is not None:
            if telegram is not None and notify:
                telegram.send(f"✅ [{DEVICE_NAME}] Kamera ulandi — nazorat davom etmoqda.")
            print(f"Kamera ulandi (indeks {idx}).")
            return cap, idx
        if HEADLESS:
            time.sleep(1.0)
        else:
            status_screen(win, 900, 520, "Kamera topilmadi",
                          "USB kamerani ulang — avtomatik davom etadi")
            k = cv2.waitKey(500) & 0xFF
            if k in (ord('q'), 27) or cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                return None, -1
    return None, -1
