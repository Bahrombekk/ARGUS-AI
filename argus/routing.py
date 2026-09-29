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


def gps_unknown(gps):
    """Tezlik NOMA'LUM: GPS javob bermagan yoki o'lchov eskirgan (internet
    uzilganda ham shunday bo'ladi)."""
    return gps is not None and (gps.speed is None or not gps.fix_fresh())


def stopped_route(gps):
    """Buzilish xabari FAQAT adminning botiga (guruh va sayt EMAS) boradi:
      - poyezd to'xtagan bo'lsa (depoda kamera oldida turish buzilish emas);
      - tezlik noma'lum bo'lsa (UNKNOWN_ADMIN_ONLY, 2026-09-29): internet
        uzilganda GPS eskirib "harakatda" deb hisoblanadi va to'xtagan lok
        xabarlari guruh/saytga ketib qolardi (28.09 08:35, 23:16)."""
    if gps is None or not STOPPED_ADMIN_ONLY:
        return False
    if not gps.is_moving():
        return True
    return bool(UNKNOWN_ADMIN_ONLY and gps_unknown(gps))
