# -*- coding: utf-8 -*-
"""ARGUS AI — jonli haydovchi nazorati (lokomotiv mashinisti uchun).

Ishga tushirish:  run.bat   yoki   C:/sdv/Scripts/python.exe app.py
Chiqish:          Ctrl+C  (HEADLESS=False bo'lsa oynada 'q' / ESC)

Kod modullarga bo'lingan:
    config.py          barcha sozlamalar
    argus/detect/      aniqlash (uyqu, telefon, odam, kayfiyat)
    argus/media/       kamera, yozuv, ovoz, dataset
    argus/net/         Telegram, sayt, GPS, navbat
    argus/report.py    hisobotlar
    argus/hud.py       ekranga chizish
    argus/loop.py      asosiy tsikl
"""
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')   # emoji/UTF-8 konsol xatosi
except Exception:
    pass

from argus.loop import _supervisor

if __name__ == "__main__":
    raise SystemExit(_supervisor())
