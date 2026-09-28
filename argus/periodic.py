# -*- coding: utf-8 -*-
"""Davriy ishlar: ulanish xabari, deploy xabari, eski yozuvlarni tozalash,
FPS/yuz statistikasi, soatlik va kunlik hisobot — loop.py dan ajratilgan."""
import os
import time
import collections

import cv2

from argus.settings import *   # noqa: F401,F403
from argus.report import (build_report, report_data, day_report_data,
                          build_daily_report)


class Periodic:
    def __init__(self, telegram, web, gps, day, ctx, ident_fn, episodes, facerec,
                 mood_hist):
        self.telegram = telegram; self.web = web; self.gps = gps; self.day = day
        self.ctx = ctx; self.ident = ident_fn; self.episodes = episodes
        self.facerec = facerec; self.mood_hist = mood_hist
        t0 = time.monotonic()
        self.last_clean = t0
        self.hello_sent = False
        self.hello_t0 = t0
        self.deploy_note_done = False
        self.fps_hist = collections.deque(maxlen=2000)
        self.last_fps_log = t0
        self.probe_last = -1e9      # yuz topilmagan daqiqa: toza kadr saqlash vaqti
        self.last_report = t0

    # ------------------------------------------------------------------
    def step(self, now, fr, frame):
        tg = self.telegram; web = self.web; gps = self.gps; ctx = self.ctx
        # ── Ulanish xabari (bir marta) ──
        # Internet bo'lmasa navbatda turadi va ulanishi bilan yetib boradi.
        # GPS javobini kutamiz: shunda xabar lokomotiv raqami va mashinist
        # bilan birga boradi, ya'ni qurilma o'zini tanitadi.
        if not self.hello_sent and tg.ok:
            ready = (gps is None) or bool(gps.updated)
            if ready or (now - self.hello_t0) >= HELLO_MAX_WAIT:
                self.hello_sent = True
                if (DEVICE_NAME_FROM_GPS and gps is not None
                        and gps.lok_nomer and not DEVICE_NAME_FIXED):
                    ctx.device_name = f"Lokomotiv-{gps.lok_nomer}"
                tg.send("\U0001F7E2 [%s] ARGUS AI ulandi\nVaqt: %s\n%s"
                        % (ctx.device_name, time.strftime('%Y-%m-%d %H:%M:%S'),
                           self.ident()))
        # ── Deploy xabari (bir marta): deploy skripti deploy_note.txt yozadi,
        # dastur qayta ishga tushgach uni admin + guruhga yuborib, o'chiradi.
        if self.hello_sent and not self.deploy_note_done:
            self.deploy_note_done = True
            try:
                if DEPLOY_NOTE_FILE and os.path.exists(DEPLOY_NOTE_FILE):
                    with open(DEPLOY_NOTE_FILE, encoding="utf-8") as fh:
                        note = fh.read().strip()
                    os.remove(DEPLOY_NOTE_FILE)
                    if note:
                        tg.send("\U0001F6E0 [%s] YANGILANDI (deploy)\nVaqt: %s\n%s"
                                % (ctx.device_name,
                                   time.strftime('%Y-%m-%d %H:%M:%S'), note))
                        print("Deploy xabari navbatga qo'yildi")
            except Exception as e:
                print("Deploy xabari yuborilmadi:", repr(e))

        # ── Eski yozuvlarni tozalash ──
        if now - self.last_clean >= RECORD_CLEAN_EVERY:
            self.last_clean = now
            self._cleanup()

        # Davriy FPS yozuvi — sekinlashuvni sezish uchun
        if fr.fps:
            self.fps_hist.append(fr.fps)
        if now - self.last_fps_log >= FPS_LOG_EVERY:
            self.last_fps_log = now
            if self.fps_hist:
                v = sorted(self.fps_hist)
                print("FPS: o'rtacha %.1f  |  eng past %.1f  |  eng yuqori %.1f  (%.0f s)"
                      % (sum(self.fps_hist)/len(self.fps_hist), v[0], v[-1], FPS_LOG_EVERY))
                self.fps_hist.clear()
                if self.facerec is not None:
                    self._face_stat(now, fr, frame)

        # Soatlik kayfiyat hisoboti
        if now - self.last_report >= REPORT_INTERVAL:
            self.last_report = now
            ih = self.episodes.incident_hist
            tg.send(build_report(self.mood_hist, ih))                 # odamga — matn
            web.send_report("hourly",                                 # saytga — maydonlar
                            report_data(self.mood_hist, ih, REPORT_INTERVAL),
                            extra=gps.identity() if gps else None)

        # Kunlik yakuniy hisobot — belgilangan vaqtdan keyin, kuniga 1 marta
        if DAILY_REPORT:
            today = time.strftime('%Y-%m-%d')
            if time.strftime('%H:%M') >= DAILY_REPORT_AT and self.day.sent_for != today:
                self.day.sent_for = today
                tg.send(build_daily_report(self.day))             # odamga — matn
                web.send_report("daily", day_report_data(self.day),     # saytga — maydonlar
                                extra=gps.identity() if gps else None)
                self.day.save(force=True)

    # ------------------------------------------------------------------
    def _face_stat(self, now, fr, frame):
        fc = self.facerec
        n_seen = fc.n_full + sum(fc.n_ok.values())
        print("YUZ-STAT (%.0f s): %s | odam=%s | to'siq=%s | yorug'lik=%.0f"
              % (FPS_LOG_EVERY, fc.stats(reset=True),
                 "bor" if fr.person_present else "yo'q",
                 "ha" if fr.blocked else "yo'q",
                 (fr.mean_b if ENABLE_TAMPER else -1.0)))
        # Butun daqiqa yuz topilmagan va poyezd harakatda -> nima
        # ko'rinayotganini bilish uchun toza kadr saqlanadi.
        gps = self.gps
        if (n_seen == 0 and (gps is None or gps.is_moving())
                and now - self.probe_last >= 600.0):
            self.probe_last = now
            try:
                pp = os.path.join(RECORD_DIR, "probe_%s.jpg"
                                  % time.strftime('%Y%m%d_%H%M%S'))
                cv2.imwrite(pp, frame)
                print("YUZ-PROBE saqlandi:", os.path.basename(pp))
            except Exception as e:
                print("YUZ-PROBE saqlanmadi:", repr(e))

    # ------------------------------------------------------------------
    def _cleanup(self):
        tg = self.telegram; web = self.web
        try:
            # Navbatda turgan fayllar himoyalanadi: ular hali
            # yuborilmagan, o'chirilsa dalil butunlay yo'qoladi.
            keep = set()
            for it in list(tg.outbox):
                if it.get("path"):
                    keep.add(os.path.normcase(os.path.abspath(it["path"])))
            if web.ok and web.outbox is not None:
                for it in list(web.outbox.q):
                    for k in ("photo", "video"):
                        if it.get(k):
                            keep.add(os.path.normcase(os.path.abspath(it[k])))
            # Klipi hali yopilmagan hodisalar ham himoyalanadi
            for pth in list(self.episodes.clip_uids):
                keep.add(os.path.normcase(os.path.abspath(pth)))

            cut = time.time() - RECORD_KEEP_DAYS * 86400
            n = 0; freed = 0
            for fn in os.listdir(RECORD_DIR):
                fp = os.path.join(RECORD_DIR, fn)
                if not os.path.isfile(fp):
                    continue
                if os.path.normcase(os.path.abspath(fp)) in keep:
                    continue
                try:
                    if os.path.getmtime(fp) < cut:
                        sz = os.path.getsize(fp)
                        os.remove(fp); n += 1; freed += sz
                except Exception:
                    pass          # fayl band bo'lsa keyingi safar
            if n:
                print("Tozalandi: %d fayl, %.0f MB bo'shadi (%d kundan eski)"
                      % (n, freed / 1e6, RECORD_KEEP_DAYS))
        except Exception as e:
            print("Tozalash xatosi (o'tkazildi):", repr(e))
