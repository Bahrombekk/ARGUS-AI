# -*- coding: utf-8 -*-
"""Saytga (ARGOS) hodisa va hisobot yuborish.

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

import os
import json
import time
import uuid
from config import *
from argus.utils import human_delay
from argus.net.outbox import Outbox
try:
    import requests
except Exception:
    requests = None



class WebClient:
    """Hodisalarni SAYTGA yuboradi. Telegram bilan bir xil ishonchlilik —
    ichida o'sha `Outbox` ishlatiladi."""

    def __init__(self, url, token, enabled):
        self.url = (url or "").strip()
        self.token = (token or "").strip()
        self.ok = bool(enabled and self.url and requests)
        self.outbox = Outbox(WEBHOOK_FILE, self._deliver) if self.ok else None

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def send_incident(self, tag, label, when=None, photo=None, video=None,
                      uid=None, detail=None, extra=None):
        """uid — bitta hodisaning xabari, rasmi va videosi SHU id bilan
        bog'lanadi. Sayt tomonida ular bitta yozuvga yig'iladi."""
        if not self.ok:
            return
        t = when or time.time()
        item = {
            "kind": "incident", "ts": t,
            "uid": uid or uuid.uuid4().hex[:12],
            "device": DEVICE_NAME, "type": tag, "label": label,
            "time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t)),
            "detail": detail,
            "photo": photo if (photo and WEBHOOK_SEND_PHOTO) else None,
            "video": video if (video and WEBHOOK_SEND_VIDEO) else None,
        }
        if extra:                      # GPS: speed, lat, lon, machinist
            item.update(extra)
        self.outbox.put(item)

    def send_report(self, kind, data, extra=None):
        """kind: 'hourly' | 'daily'; data — strukturali dict (matn EMAS).

        Saytga tayyor matn emas, maydonlar yuboriladi — shunda sayt uni
        to'g'ridan-to'g'ri bazaga yozadi va grafik chiza oladi."""
        if not self.ok:
            return
        t = time.time()
        item = {"kind": "report", "report": kind, "device": DEVICE_NAME,
                "ts": t, "time": time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(t))}
        item.update(data)
        if extra:                      # mashinist va lokomotiv
            item.update(extra)
        self.outbox.put(item)

    def _deliver(self, item):
        """Xato ko'tarilsa — Outbox elementni saqlab qoladi va qayta uradi."""
        meta = {k: v for k, v in item.items()
                if k not in ("photo", "video") and v is not None}
        meta["delayed_sec"] = round(time.time() - item.get("ts", time.time()), 1)
        # Diagnostika: saytga aynan nima ketayotgani jurnalga yoziladi.
        # Saytda "O'lchangan qiymat" bo'sh chiqqanda, muammo qurilmadami
        # yoki bekenddami - shu satr ajratib beradi.
        print("SAYT -> %s | uid=%s | type=%s | detail=%s | fayl=%s"
              % (meta.get("kind"), meta.get("uid"), meta.get("type"),
                 (meta.get("detail") or "-")[:60].replace(chr(10), " "),
                 ",".join(k for k in ("photo", "video") if item.get(k)) or "-"))
        files, opened = {}, []
        try:
            for key in ("photo", "video"):
                p = item.get(key)
                if p and os.path.exists(p):
                    fh = open(p, "rb"); opened.append(fh)
                    files[key] = (os.path.basename(p), fh)
            tmo = WEBHOOK_TIMEOUT * (3 if files.get("video") else 1)
            if files:
                # multipart: fayllar + `data` maydonida JSON
                r = requests.post(self.url, headers=self._headers(),
                                  data={"data": json.dumps(meta, ensure_ascii=False)},
                                  files=files, timeout=tmo)
            else:
                r = requests.post(self.url, headers=self._headers(),
                                  json=meta, timeout=tmo)
            # 4xx — sayt qabul qilmadi; qayta urinish foydasiz, tashlab ketamiz
            if 400 <= r.status_code < 500:
                print(f"Sayt rad etdi ({r.status_code}) — element tashlandi")
                return
            r.raise_for_status()
        finally:
            for fh in opened:
                try: fh.close()
                except Exception: pass
