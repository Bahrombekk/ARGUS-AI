# -*- coding: utf-8 -*-
"""Soatlik va kunlik hisobotlar, kunlik statistika.

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

import os
import json
import time
import collections
from config import *



def build_report(mood_hist, incident_hist):
    """1 soatlik yig'ilган kayfiyat + buzilishlardan matnli hisobot."""
    mc = collections.Counter(m for _, m in mood_hist)
    total = sum(mc.values()) or 1
    dom = mc.most_common(1)[0][0] if mc else "-"
    mood_line = ", ".join(f"{m} {round(100*c/total)}%" for m, c in mc.most_common())
    ic = collections.Counter(t for _, t in incident_hist)
    inc_line = ", ".join(f"{TG_MSG.get(t, t)}×{c}" for t, c in ic.most_common()) or "yo'q"
    return (f"\U0001F552 [{DEVICE_NAME}] soatlik hisobot ({time.strftime('%H:%M')})\n"
            f"Kayfiyat: asosan {dom}\n  {mood_line}\n"
            f"Buzilishlar: {inc_line}")


def report_data(mood_hist, incident_hist, period_sec):
    """Soatlik hisobotning STRUKTURALI ko'rinishi — sayt uchun.

    Matnli variant (`build_report`) Telegram'da odam o'qishi uchun.
    Saytga matn yuborilsa, u foizlarni regex bilan ajratishga majbur
    bo'lardi va matn formatini o'zgartirsak darhol buzilardi."""
    mc = collections.Counter(m for _, m in mood_hist)
    total = sum(mc.values())
    ic = collections.Counter(t for _, t in incident_hist)
    return {
        "period_sec": period_sec,
        "mood": {
            "dominant": mc.most_common(1)[0][0] if mc else None,
            "samples": total,
            "counts": dict(mc),
            "percent": ({m: round(100.0 * c / total, 1) for m, c in mc.items()}
                        if total else {}),
        },
        "incidents": {
            "total": sum(ic.values()),
            "counts": dict(ic),
            "labels": {t: TG_MSG.get(t, t) for t in ic},
        },
    }


def day_report_data(day):
    """Kunlik hisobotning strukturali ko'rinishi."""
    total = sum(day.moods.values())
    return {
        "date": day.date,
        "mood": {
            "dominant": day.moods.most_common(1)[0][0] if day.moods else None,
            "samples": total,
            "counts": dict(day.moods),
            "percent": ({m: round(100.0 * c / total, 1) for m, c in day.moods.items()}
                        if total else {}),
        },
        "incidents": {
            "total": sum(day.incidents.values()),
            "counts": dict(day.incidents),
            "labels": {t: TG_MSG.get(t, t) for t in day.incidents},
        },
    }


class DayStats:
    """Kunlik statistika — DISKDA saqlanadi, restartda yo'qolmaydi.

    Soatlik hisobotdagi deque'lar 1 soatdan keyin tozalanadi va dastur
    qayta ishga tushsa butunlay yo'qoladi. Kun bo'yicha xulosa uchun bu
    yaramaydi, shuning uchun bu yerda oddiy hisoblagichlar faylga yoziladi."""

    def __init__(self, path):
        self.path = path
        self.date = time.strftime('%Y-%m-%d')
        self.moods = collections.Counter()
        self.incidents = collections.Counter()
        self.sent_for = None          # qaysi kun uchun hisobot yuborilgan
        self._dirty = False
        self._last_save = 0.0
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding='utf-8') as f:
                d = json.load(f)
            self.sent_for = d.get("sent_for")
            if d.get("date") == self.date:        # faqat BUGUNGI ma'lumot tiklanadi
                self.moods = collections.Counter(d.get("moods", {}))
                self.incidents = collections.Counter(d.get("incidents", {}))
        except Exception:
            pass

    def save(self, force=False):
        now = time.time()
        if not force and (not self._dirty or now - self._last_save < 30):
            return                                 # diskni bekorga charchatmaymiz
        try:
            with open(self.path, "w", encoding='utf-8') as f:
                json.dump({"date": self.date, "moods": dict(self.moods),
                           "incidents": dict(self.incidents),
                           "sent_for": self.sent_for}, f, ensure_ascii=False)
            self._dirty = False
            self._last_save = now
        except Exception:
            pass

    def _roll(self):
        """Yarim tunda hisoblagichlar nolga tushadi."""
        today = time.strftime('%Y-%m-%d')
        if today != self.date:
            self.date = today
            self.moods.clear()
            self.incidents.clear()
            self._dirty = True

    def add_mood(self, m):
        self._roll(); self.moods[m] += 1; self._dirty = True

    def add_incident(self, t):
        self._roll(); self.incidents[t] += 1; self._dirty = True


def build_daily_report(day):
    """Kun bo'yicha yakuniy xulosa."""
    total = sum(day.moods.values()) or 1
    dom = day.moods.most_common(1)[0][0] if day.moods else "-"
    mood_line = ", ".join(f"{m} {round(100*c/total)}%"
                          for m, c in day.moods.most_common()) or "-"
    inc_line = ", ".join(f"{TG_MSG.get(t, t)}×{c}"
                         for t, c in day.incidents.most_common()) or "yo'q"
    return (f"\U0001F4C5 [{DEVICE_NAME}] KUNLIK hisobot — {day.date}\n"
            f"Kayfiyat: asosan {dom}\n  {mood_line}\n"
            f"Buzilishlar (jami {sum(day.incidents.values())}): {inc_line}")
