# -*- coding: utf-8 -*-
"""GPS: tezlik, koordinata va mashinist ma'lumoti.

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

import os
import json
import time
import calendar
import threading
from config import *
try:
    import requests
except Exception:
    requests = None



class GpsClient:
    """gps.mydepo.uz dan tezlik, koordinata va mashinist ma'lumotini oladi.

    Alohida oqimda ishlaydi — tarmoq sekin bo'lsa ham aniqlash to'xtamaydi.
    Oxirgi muvaffaqiyatli javob keshda turadi; so'rov yiqilsa eski qiymat
    ishlatiladi, lekin `stale` belgisi qo'yiladi."""

    def __init__(self, base, creds_path, imei, every=12.0, timeout=10.0):
        self.base = base.rstrip("/")
        self.imei = imei
        self.every = every
        self.timeout = timeout
        self.ok = False
        self._token = None
        self._token_exp = 0.0
        self._lock = threading.Lock()
        # Oxirgi ma'lum holat
        self.speed = None          # km/soat yoki None
        self.fix_age = None        # o'lchov necha soniya eski (None = noma'lum)
        self.ignition = None
        self.lat = self.lon = None
        self.machinist = None      # {"fio":..., "phone":..., "emm_id":...}
        self.lok_nomer = self.lok_name = None
        self.updated = 0.0         # oxirgi MUVAFFAQIYATLI so'rov vaqti
        self.last_error = None

        self._email = self._password = None
        try:
            with open(creds_path, encoding="utf-8") as f:
                c = json.load(f)
            self._email, self._password = c.get("email"), c.get("password")
        except Exception as e:
            self.last_error = f"gps_creds.json o'qilmadi: {e}"
            return
        if not (self._email and self._password):
            self.last_error = "gps_creds.json da email yoki password yo'q"
            return
        self.ok = True
        threading.Thread(target=self._loop, daemon=True).start()

    # ── Token ──
    def _login(self):
        r = requests.post(self.base + "/api/auth/login",
                          json={"email": self._email, "password": self._password},
                          timeout=self.timeout)
        r.raise_for_status()
        d = r.json()
        self._token = d["access_token"]
        # 60 s zaxira bilan — muddati tugashiga yaqin qayta olamiz
        self._token_exp = time.time() + float(d.get("expires_in", 1800)) - 60
        return self._token

    def _auth(self):
        if not self._token or time.time() >= self._token_exp:
            self._login()
        return {"Authorization": "Bearer " + self._token}

    # ── Ma'lumot olish ──
    def snapshot(self, when=None):
        """Berilgan vaqt uchun qurilma holatini qaytaradi (xom dict)."""
        t = when or time.time()
        dt = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(t))
        r = requests.get(self.base + "/api/integration/device-snapshot",
                         params={"imei": self.imei, "datetime": dt},
                         headers=self._auth(), timeout=self.timeout)
        if r.status_code == 401:            # token eskirgan — bir marta qayta
            self._token = None
            r = requests.get(self.base + "/api/integration/device-snapshot",
                             params={"imei": self.imei, "datetime": dt},
                             headers=self._auth(), timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _loop(self):
        while True:
            try:
                d = self.snapshot()
                # fixtime — GPS ASLIDA qachon o'lchagan. So'ralgan vaqtdan
                # ancha farq qilishi mumkin, shuning uchun yoshini hisoblaymiz.
                age = None
                ft = d.get("fixtime")
                if ft:
                    try:
                        f = time.strptime(str(ft).replace("Z", ""), "%Y-%m-%dT%H:%M:%S")
                        age = time.time() - calendar.timegm(f)
                    except Exception:
                        age = None
                with self._lock:
                    self.speed = d.get("speed")
                    self.fix_age = age
                    self.ignition = d.get("ignition")
                    self.lat, self.lon = d.get("lat"), d.get("lon")
                    ms = d.get("machinists") or []
                    if ms:
                        m = ms[0]
                        self.machinist = {"fio": m.get("mashinist_fio"),
                                          "phone": m.get("phone"),
                                          "emm_id": m.get("emm_id")}
                        self.lok_nomer = m.get("lok_nomer")
                        self.lok_name = m.get("lok_name")
                    self.updated = time.time()
                    self.last_error = None
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {str(e)[:80]}"
            time.sleep(self.every)

    def set_imei(self, imei):
        """IMEI ni ish vaqtida almashtiradi (Telegram /imei buyrug'i).

        Eski lokomotivning ma'lumoti yangisiniki bilan aralashmasligi
        uchun kesh tozalanadi."""
        imei = str(imei).strip()
        if not imei or imei == self.imei:
            return False
        with self._lock:
            self.imei = imei
            self.speed = self.fix_age = self.ignition = None
            self.lat = self.lon = None
            self.machinist = None
            self.lok_nomer = self.lok_name = None
            self.updated = 0.0
            self.last_error = None
        return True

    # ── Foydalanish ──
    def is_moving(self):
        """Poyezd harakatdami? Noma'lum bo'lsa sozlamaga qarab hal qilinadi.

        ESKI o'lchov ham noma'lum hisoblanadi: lokomotiv endigina jo'nagan
        bo'lsa, 20-30 daqiqalik eski "tezlik 0" ni ishonchli deb bo'lmaydi."""
        with self._lock:
            s, age = self.speed, self.fix_age
        if s is None:
            return GPS_UNKNOWN_IS_MOVING
        if age is not None and age > GPS_FIX_MAX_AGE:
            return GPS_UNKNOWN_IS_MOVING          # o'lchov eskirgan
        try:
            return float(s) >= GPS_MOVING_KMH
        except (TypeError, ValueError):
            return GPS_UNKNOWN_IS_MOVING

    def fix_fresh(self):
        """O'lchov ishonchli yoshdami?"""
        with self._lock:
            age = self.fix_age
        return age is not None and age <= GPS_FIX_MAX_AGE

    def text(self, short=False):
        """Telegram xabari uchun odam o'qiydigan ko'rinish.

        Ikki qoida:
        1) Eski o'lchovni HOZIRGI tezlik deb ko'rsatmaymiz. Ilgari 4 soatlik
           o'lchov "0 km/s (harakatda)" bo'lib chiqardi — o'zaro zid va
           dispetcherni chalg'itadi.
        2) Koordinata HAR DOIM ko'rsatiladi, rasm izohida ham. Buzilish
           qayerda sodir bo'lganini bilish — eng kerakli ma'lumot."""
        with self._lock:
            sp, age, lat, lon = self.speed, self.fix_age, self.lat, self.lon
            m, ign = self.machinist, self.ignition
            nom, nam = self.lok_nomer, self.lok_name
        stale = age is not None and age > GPS_FIX_MAX_AGE
        out = []
        if sp is not None:
            if stale:
                # Dvigatel o'chganda qurilma ma'lumot yubormaydi — o'lchov
                # qotib qoladi. Shuning uchun uni "hozirgi" deb atamaymiz.
                qachon = (f"{age/60:.0f} daq" if age < 5400 else f"{age/3600:.1f} soat")
                sabab = " (dvigatel o'chiq)" if ign is False else ""
                out.append(f"Tezlik: noma'lum — oxirgi o'lchov {qachon} oldin: "
                           f"{float(sp):.0f} km/s{sabab}")
            else:
                holat = "harakatda" if self.is_moving() else "to'xtagan"
                out.append(f"Tezlik: {float(sp):.0f} km/s ({holat})")
        if m and m.get("fio"):
            out.append(f"Mashinist: {m['fio']}")
        if nom or nam:
            out.append(f"Lokomotiv: {nom or '-'} / {nam or '-'}")
        if lat is not None and lon is not None:
            line = f"Joylashuv: {lat:.5f}, {lon:.5f}"
            if stale:
                line += " (oxirgi ma'lum nuqta)"
            out.append(line)
            if not short:          # xaritada ochiladigan havola
                out.append(f"https://maps.google.com/?q={lat:.6f},{lon:.6f}")
        return "\n".join(out)

    def identity(self):
        """Faqat KIM va QAYSI lokomotiv — hisobotlar uchun.

        Tezlik va koordinata bu yerda kerak emas: hisobot bir soat yoki bir
        kunni qamraydi, o'sha paytdagi bitta tezlik ma'nosiz."""
        with self._lock:
            out = {}
            if self.machinist and self.machinist.get("fio"):
                out["machinist"] = self.machinist["fio"]
                if self.machinist.get("emm_id"):
                    out["machinist_id"] = self.machinist["emm_id"]
            if self.lok_nomer: out["lok_nomer"] = self.lok_nomer
            if self.lok_name:  out["lok_name"] = self.lok_name
            return out

    def info(self):
        """Hodisaga biriktiriladigan qisqa ma'lumot."""
        with self._lock:
            out = {}
            if self.speed is not None: out["speed"] = self.speed
            if self.lat is not None:   out["lat"] = self.lat
            if self.lon is not None:   out["lon"] = self.lon
            if self.machinist and self.machinist.get("fio"):
                out["machinist"] = self.machinist["fio"]
                if self.machinist.get("emm_id"):
                    out["machinist_id"] = self.machinist["emm_id"]
                if self.machinist.get("phone"):
                    out["machinist_phone"] = self.machinist["phone"]
            if self.lok_nomer: out["lok_nomer"] = self.lok_nomer
            if self.lok_name:  out["lok_name"] = self.lok_name
            if self.ignition is not None: out["ignition"] = self.ignition
            if self.fix_age is not None:  out["gps_fix_age_sec"] = round(self.fix_age, 0)
            if self.updated:
                out["gps_age_sec"] = round(time.time() - self.updated, 1)
            return out
