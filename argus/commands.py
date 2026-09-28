# -*- coding: utf-8 -*-
"""Telegram boshqaruv buyruqlari (headless — klaviatura yo'q) — loop.py dan
ajratilgan. install() hook'larni o'rnatadi va /id matnini tuzadigan
funksiyani qaytaradi (ulanish xabarida ham ishlatiladi)."""
import os
import json
import time

from argus.settings import *   # noqa: F401,F403
from argus.report import build_report, build_daily_report


def install(telegram, ctx, gps, recorder, latest, stop_event, mood_hist, episodes, day,
            mood_ref):
    """mood_ref — [cur_mood] (bitta elementli ro'yxat, loop yangilab turadi)."""
    telegram.cmd_report = lambda: build_report(mood_hist, episodes.incident_hist)
    telegram.cmd_daily = lambda: build_daily_report(day)
    telegram.cmd_status = lambda: (f"[{ctx.device_name}] Ishlayapti | Kayfiyat: {mood_ref[0]} | "
                                   f"Navbatda: {len(telegram.outbox)}")
    telegram.cmd_stop = lambda: stop_event.set()

    def _ident():
        """Qurilma va lokomotiv ma'lumoti - /id buyrug'i uchun."""
        out = [f"Qurilma: {ctx.device_name}"]
        out.append(f"IMEI: {GPS_IMEI}")
        if gps is None:
            out.append("GPS: o'chiq")
        elif not gps.updated:
            out.append("GPS: javob yo'q" + (f" ({gps.last_error})" if gps.last_error else ""))
        else:
            if gps.lok_nomer or gps.lok_name:
                out.append(f"Lokomotiv: {gps.lok_nomer or '-'} / {gps.lok_name or '-'}")
            if gps.machinist and gps.machinist.get("fio"):
                out.append(f"Mashinist: {gps.machinist['fio']}")
            out.append("GPS o'lchovi: " + ("yangi" if gps.fix_fresh() else "eski"))
        out.append(f"Kamera: {ctx.W}x{ctx.H}")
        out.append(f"Navbatda: {len(telegram.outbox)} xabar")
        return "\n".join(out)
    telegram.cmd_ident = _ident

    def _set_imei(v):
        """IMEI ni o'rnatadi va device.json ga yozadi (monitorsiz sozlash)."""
        if gps is None:
            return "GPS o'chiq - IMEI ishlatilmaydi."
        try:
            cfg = {}
            if os.path.exists(DEVICE_FILE):
                with open(DEVICE_FILE, encoding="utf-8") as f:
                    cfg = json.load(f)
            cfg["imei"] = v
            with open(DEVICE_FILE, "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return f"device.json yozilmadi: {e}"
        gps.set_imei(v)
        return (f"IMEI o'rnatildi: {v}\n"
                f"Ma'lumot kelishi uchun {GPS_EVERY:.0f} soniyagacha kuting, "
                f"keyin /id yozing.")
    telegram.cmd_imei = _set_imei

    def _do_snapshot():
        fr = latest[0]
        if fr is not None:
            p = recorder.snapshot(fr.copy())
            telegram.send_photo(p, f"[{ctx.device_name}] Snapshot\n"
                                   f"Vaqt: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    telegram.cmd_snapshot = _do_snapshot
    return _ident
