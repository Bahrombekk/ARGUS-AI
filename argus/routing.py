# -*- coding: utf-8 -*-
"""Xabar yo'naltirish qoidalari: poyezd holatiga qarab qaysi buzilish
XABAR hisoblanadi va u kimga boradi. Ovozga taalluqli emas.
"""
from argus.settings import *   # noqa: F401,F403


def gate_for_report(active, gps):
    """Poyezd TO'XTAGAN bo'lsa harakatga bog'liq turlar BUZILISH emas.
    Temir yo'l standarti: hushyorlik nazorati 10 km/soatdan yuqorida
    yoqiladi. Bu faqat xabar va statistikaga taalluqli, ovozga emas."""
    if gps is not None and not gps.is_moving():
        return [a for a in active if a not in GPS_GATED_TAGS]
    return list(active)


def stopped_route(gps):
    """To'xtagan poyezd: qolgan buzilishlar FAQAT adminning botiga, guruhga
    va saytga ketmaydi (depoda kamera oldida turish buzilish emas)."""
    return bool(STOPPED_ADMIN_ONLY and gps is not None and not gps.is_moving())
