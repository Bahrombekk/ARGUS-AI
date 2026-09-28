# -*- coding: utf-8 -*-
"""Epizod hisobi: buzilish qachon boshlanadi/tugaydi, ID, matnli xabar,
dalil rasmi va video — loop.py dan ajratilgan (2026-09-28).

Oqim (har kadrda):
    held = tracker.update(rep_active, now, describe, fr)   # matn/tugadi/ID
    ... loop HUD chizadi ...
    tracker.attach_media(build_evidence, rep_active, now)  # rasm + klip ID
"""
import os
import time
import uuid
import collections

from argus.settings import *   # noqa: F401,F403
from argus.detect.windows import EpisodeHold
from argus.utils import ts_from_name, human_dur


class EpisodeTracker:
    def __init__(self, telegram, web, gps, recorder, day, ctx):
        self.telegram = telegram
        self.web = web
        self.gps = gps
        self.recorder = recorder
        self.day = day
        self.ctx = ctx

        self.tg_last = {}
        self.tg_repeat = {}    # tur -> necha marta xabar berilgan (davomli holat uchun)
        self.tg_since = {}     # tur -> holat qachon boshlangan
        self.tg_uid = {}       # tur -> epizod UID (tugash xabari shu UID bilan ketadi)
        self.prev_tags = set()      # oldingi kadrdagi faol buzilishlar (EPIZODni sanash uchun)
        self.prev_active = False
        self.episode_started = False
        self.held_active = set()
        self.cur_uid = None         # joriy hodisaning yagona ID si
        self.cur_detail = ""        # joriy epizodning o'lchangan qiymati (rasm/videoga ham)
        self.clip_uids = {}         # klip yo'li -> UID (video keyinroq yopiladi)
        self.clip_det = {}          # klip yo'li -> o'sha epizodning qiymati
        self.clip_sent = set()      # video yuborilgan UID lar (bir epizodga bitta klip)
        self.pending_uid = None     # klip fayli hali ochilmagan bo'lsa — navbatda turadi
        self.pending_det = ""
        self.incident_hist = collections.deque()   # (t, tag) — oxirgi 1 soat
        self.ep_hold = EpisodeHold(INCIDENT_REJOIN_SEC)
        # Klip tayyor bo'lganda → Telegram'ga video yuborish
        recorder.on_clip = self._on_clip

    # ------------------------------------------------------------------
    def _gps_info(self):
        return self.gps.info() if self.gps else None

    def _on_clip(self, p):
        """Klip vaqti fayl NOMIDAN olinadi — klip hodisadan bir necha soniya
        keyin yopiladi, yuborish esa internet uzilsa yana ham kechikishi mumkin.
        Klip o'sha hodisaning UID si bilan ketadi (hodisa boshlanganda yozib
        qo'yilgan edi). Topilmasa - yangi id beriladi."""
        uid = self.clip_uids.pop(p, None)
        # Bir epizodga (UID) faqat BITTA video: epizod ichida yuz qayta
        # yo'qolib klip yana yozilsa, u diskda qoladi, lekin yuborilmaydi.
        if uid and uid in self.clip_sent:
            print("Klip yuborilmadi (epizod davom etyapti, video allaqachon ketgan):",
                  os.path.basename(p), uid)
            self.clip_det.pop(p, None)
            return
        if uid:
            self.clip_sent.add(uid)
            if len(self.clip_sent) > 500:
                self.clip_sent.clear()
        self.telegram.send_video(p, f"\U0001F3A5 [{self.ctx.device_name}] hodisa yozuvi\n"
                                    f"Vaqt: {ts_from_name(p)}"
                                    + (f"\nID: {uid}" if uid else ""),
                                 admin_only=self.ctx.stopped_route)
        det_c = self.clip_det.pop(p, None) or None
        if not self.ctx.stopped_route:
            self.web.send_incident("klip", "Hodisa yozuvi", video=p, uid=uid,
                                   detail=det_c, extra=self._gps_info())

    # ------------------------------------------------------------------
    def update(self, rep_active, now, describe, fr):
        """Statistika, tugash xabari, yangi epizod ID si, matnli xabarlar.
        Qaytadi: held_active (ushlab turilgan ro'yxat)."""
        tg = self.telegram; web = self.web; gps = self.gps
        stopped = self.ctx.stopped_route
        dev = self.ctx.device_name
        # Epizod hisobi uchun "ushlab turilgan" ro'yxat: tur REJOIN oynasida
        # qaytsa yangi epizod ochilmaydi (yozuv/ovoz esa rep_active bo'yicha).
        held_active = self.ep_hold.update(rep_active, now)
        self.held_active = held_active

        # Faqat YANGI boshlangan buzilish sanaladi. `active` hodisa davom
        # etguncha to'la turadi — har kadrda sanalsa, 4 soniyalik bitta uyqu
        # "Uyqu×53" bo'lib ko'rinardi.
        new_tags = set(held_active) - self.prev_tags
        for tag in new_tags:
            self.incident_hist.append((now, tag))
            self.day.add_incident(tag)
        self.prev_tags = set(held_active)
        while self.incident_hist and now - self.incident_hist[0][0] > REPORT_INTERVAL:
            self.incident_hist.popleft()
        self.day.save()                      # o'zi 30 s da bir marta yozadi

        # Holat tugagan turlarning hisoblagichi nolga tushadi — keyingi
        # safar yana darhol xabar beriladi.
        for t in list(self.tg_repeat):
            if t in held_active:
                continue
            # Davomiylik — oxirgi FAOL vaqtgacha (ushlab turish oynasi kirmaydi)
            dur = self.ep_hold.seen(t, now) - self.tg_since.get(t, now)
            # Uzoq davom etgan holat tugadi — buni bir marta bildiramiz.
            # Qisqa epizodda bu ortiqcha: boshlanish xabarining o'zi yetarli.
            if INCIDENT_END_MSG and dur >= INCIDENT_END_MIN:
                lab = TG_MSG.get(t, t)
                tg.send(TXT_END.format(
                    dev=dev, label=lab, dur=human_dur(dur),
                    vaqt=time.strftime('%Y-%m-%d %H:%M:%S'),
                    uid=self.tg_uid.get(t) or "-"), admin_only=stopped)
                ex = dict(gps.info()) if gps else {}
                ex["phase"] = "end"
                ex["duration_sec"] = round(dur, 1)
                if not stopped:
                    web.send_incident(t, lab, uid=self.tg_uid.get(t),
                                      detail="tugadi", extra=ex)
            self.tg_repeat.pop(t, None)
            self.tg_since.pop(t, None)
            self.tg_uid.pop(t, None)

        # Yangi epizod boshlandi - UID SHU YERDA beriladi, xabardan OLDIN
        # (rasm, video va matn shu bitta ID bilan ketadi).
        self.episode_started = bool(held_active) and not self.prev_active
        if self.episode_started:
            self.cur_uid = uuid.uuid4().hex[:12]
            self.cur_detail = ""

        for tag in rep_active:
            n = self.tg_repeat.get(tag, 0)
            # INCIDENT_REPEAT=False → epizodga faqat BITTA xabar
            if n and not INCIDENT_REPEAT:
                continue
            gap = INCIDENT_BACKOFF[min(n, len(INCIDENT_BACKOFF) - 1)]
            if now - self.tg_last.get(tag, -1e9) >= gap:
                self.tg_last[tag] = now
                self.tg_repeat[tag] = n + 1
                self.tg_since.setdefault(tag, now)
                self.tg_uid.setdefault(tag, self.cur_uid)
                label = TG_MSG.get(tag, tag)
                det = describe(tag, now, fr)
                # Takroriy xabar bo'lsa — nechanchisi va qancha vaqtdan beri
                rep = ""
                if n:
                    dur = now - self.tg_since.get(tag, now)
                    rep = (f"\n↻ {n+1}-xabar, "
                           + (f"{dur/60:.0f} daqiqadan" if dur < 3600 else f"{dur/3600:.1f} soatdan")
                           + " beri davom etyapti")
                gtxt = gps.text() if gps else ""
                tg.send(f"⚠️ [{dev}] Buzilish: {label}\n"
                        f"Vaqt: {time.strftime('%Y-%m-%d %H:%M:%S')}{det}{rep}"
                        + (f"\n{gtxt}" if gtxt else "")
                        + (f"\nID: {self.cur_uid}" if self.cur_uid else ""),
                        admin_only=stopped)
                one = det.strip().replace("\n", "; ")
                # Qiymat rasm va videoga ham biriktiriladi: ular alohida
                # so'rov bo'lib ketadi va sayt oxirgisini ustiga yozsa,
                # o'lchangan qiymat yo'qolib qolmasin.
                if one:
                    self.cur_detail = (self.cur_detail + " | " + one) if self.cur_detail else one
                if not stopped:
                    web.send_incident(tag, label, uid=self.cur_uid,
                                      detail=one or None, extra=self._gps_info())
        return held_active

    # ------------------------------------------------------------------
    def attach_media(self, build_evidence, rep_active, now):
        """Yangi epizodda dalil rasmi (Telegram + sayt) va klipni UID ga
        bog'lash. HAR kadrda chaqiriladi (prev_active shu yerda yangilanadi)."""
        tg = self.telegram; web = self.web; gps = self.gps
        stopped = self.ctx.stopped_route
        rec = self.recorder
        if SNAPSHOT_ON_EVENT and self.episode_started:
            ev = build_evidence()
            snap = rec.snapshot(ev)
            capt = ", ".join(TG_MSG.get(a, a) for a in rep_active)
            if tg.ok:                     # rasmni ham Telegram'ga
                tg.send_photo(snap, f"⚠️ [{self.ctx.device_name}] {capt}\n"
                                    f"Vaqt: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                                    + (f"\n{gps.text(short=True)}" if gps else "")
                                    + f"\nID: {self.cur_uid}",
                              admin_only=stopped)
            # Saytga — rasm biriktirilgan holda (to'xtaganda yuborilmaydi)
            if not stopped:
                web.send_incident(",".join(sorted(rep_active)), capt, photo=snap,
                                  uid=self.cur_uid, detail=self.cur_detail or None,
                                  extra=self._gps_info())
            # Klip keyinroq yopiladi — uning yo'lini UID ga bog'lab qo'yamiz.
            # Fayl shu kadrda hali ochilmagan bo'lishi mumkin, u holda UID
            # navbatda turadi va fayl ochilishi bilan bog'lanadi. Aks holda
            # video YANGI uid bilan ketib, saytda alohida hodisa bo'lib qolardi.
            if rec.path:
                self.clip_uids[rec.path] = self.cur_uid
                self.clip_det[rec.path] = self.cur_detail
            else:
                self.pending_uid = self.cur_uid
                self.pending_det = self.cur_detail
        # Ushlab turilgan epizod ichida yuz qayta yo'qolib YANGI klip ochilsa,
        # u ham joriy ID ga bog'lanadi — aks holda ID'siz ketib, "bir epizodga
        # bitta video" filtri uni tanimasdi (2026-09-28 18:19-18:22: 5 ta ID'siz video).
        if (self.held_active and self.cur_uid and rec.path
                and rec.path not in self.clip_uids and self.pending_uid is None):
            self.clip_uids[rec.path] = self.cur_uid
            self.clip_det[rec.path] = self.cur_detail
        self.prev_active = bool(self.held_active)
        self.episode_started = False

        # Kutayotgan UID bor va klip fayli endi ochildi — bog'laymiz
        if self.pending_uid and rec.path and rec.path not in self.clip_uids:
            self.clip_uids[rec.path] = self.pending_uid
            self.clip_det[rec.path] = self.pending_det
            self.pending_uid = None
