# -*- coding: utf-8 -*-
"""Kichik yordamchilar.

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

import os
import time



def ts_from_name(path):
    """`rec_20260917_100617.mp4` → `2026-09-17 10:06:17`.

    Klip fayli hodisadan bir necha soniya KEYIN yopiladi, shuning uchun
    yuborish paytidagi vaqt emas, fayl nomidagi HODISA vaqti olinadi."""
    import re
    m = re.search(r"(\d{8})_(\d{6})", os.path.basename(path))
    if not m:
        return time.strftime('%Y-%m-%d %H:%M:%S')
    d, t = m.group(1), m.group(2)
    return f"{d[:4]}-{d[4:6]}-{d[6:]} {t[:2]}:{t[2:4]}:{t[4:]}"


def human_delay(sec):
    """120 → '2 daqiqa', 7200 → '2.0 soat', 90000 → '1.0 kun'."""
    if sec < 3600:
        return f"{int(sec // 60)} daqiqa"
    if sec < 86400:
        return f"{sec / 3600:.1f} soat"
    return f"{sec / 86400:.1f} kun"


def human_dur(sec):
    """Davomiylik: 45 -> '45 soniya', 130 -> '2 daq 10 s', 7200 -> '2 soat 0 daq'.

    human_delay() dan farqi — bu qisqa oraliqni ham to'g'ri ko'rsatadi.
    U 45 soniyani "0 daqiqa" deb chiqarardi."""
    sec = max(0.0, float(sec))
    if sec < 60:
        return f"{sec:.0f} soniya"
    if sec < 3600:
        m, r = divmod(int(sec), 60)
        return f"{m} daq {r} s"
    h, r = divmod(int(sec), 3600)
    return f"{h} soat {r // 60} daq"
