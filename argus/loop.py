# -*- coding: utf-8 -*-
"""ARGUS AI — asosiy tsikl (2026-09-28 refaktor: qismlarga bo'lingan).

    kamera → pipeline → FrameAnalyzer (argus/frame_state.py)
           → yo'naltirish (argus/routing.py) → ovoz
           → EpisodeTracker (argus/episodes.py: ID, matn, rasm, video)
           → Periodic (argus/periodic.py: hello, deploy, tozalash, hisobot)
           → HUD (argus/hud_rows.py + argus/hud.py) → yozuv (recorder)

Telegram buyruqlari: argus/commands.py. Umumiy o'zgaruvchan holat
(qurilma nomi, to'xtagan yo'nalish, kadr o'lchami): argus/context.py.
Mantiq avvalgi monolit bilan bir xil; oflayn test: tests/.
"""
import os
import time
import threading
import collections

import cv2

from argus.settings import *   # noqa: F401,F403
from safedrive.pipelines.yolo_pipeline import YoloPipeline

from argus.context import RunContext
from argus.hud import (draw_box, info_panel, alert_banner,
                       chips, frame_decor, face_reticle, text)
from argus.hud_rows import build_rows, banner
from argus.frame_state import FrameAnalyzer
from argus.episodes import EpisodeTracker
from argus.periodic import Periodic
from argus import commands, routing
from argus.detect.eyes import BlendTap
from argus.detect.reverify import FaceRecover
from argus.detect.mood import MoodDetector
from argus.detect.phone import PhoneDetector
from argus.detect.person import PersonDetector
from argus.media.voice import Voice
from argus.media.recorder import Recorder
from argus.media.camera import open_any_camera, wait_for_camera
from argus.media.dataset import DatasetCollector
from argus.net.telegram import Telegram
from argus.net.web import WebClient
from argus.net.gps import GpsClient
from argus.report import build_report, DayStats


def _build_detectors(pipe):
    """Ixtiyoriy detektorlar (model bo'lmasa None)."""
    mooddet = None
    if ENABLE_MOOD and os.path.exists(MOOD_MODEL) and os.path.exists(MOOD_ONNX):
        try:
            mooddet = MoodDetector(MOOD_MODEL, MOOD_ONNX, MOOD_EVERY)
            print("Kayfiyat aniqlash: YOQILDI (FER+ emotion CNN)")
        except Exception as e:
            print("Kayfiyat yuklanmadi:", e)

    # Odam aniqlash — yuz yo'q bo'lganda "to'sgan" va "chiqib ketgan"ni ajratadi.
    # Odam-detektor 'yoq' UCHUN HAM, 'yuz' darvozasi UCHUN HAM kerak: odam yo'q
    # bo'lsa 'Yuz ko'rinmayapti' yuborilmaydi (bo'sh o'rindiq = yuz yo'q, bu
    # ortiqcha xabar). ENABLE_PERSON faqat 'yoq' XABARINI boshqaradi.
    persondet = None
    if (ENABLE_PERSON or ENABLE_NOFACE) and os.path.exists(PERSON_MODEL):
        try:
            persondet = PersonDetector(PERSON_MODEL, PERSON_CONF, PERSON_EVERY)
            print("Odam aniqlash: YOQILDI (YOLOv8n, faqat yuz yo'qolganda)")
        except Exception as e:
            print("Odam aniqlash yuklanmadi:", e)
    elif (ENABLE_PERSON or ENABLE_NOFACE):
        print(f"Odam aniqlash: model yo'q ({PERSON_MODEL}) — "
              f"yuz yo'qolsa 'to'sgan' deb hisoblanadi")

    # GPS — tezlik, koordinata, mashinist
    gps = None
    if ENABLE_GPS:
        gps = GpsClient(GPS_BASE, GPS_CREDS, GPS_IMEI, GPS_EVERY, GPS_TIMEOUT)
        if gps.ok:
            print(f"GPS: YOQILDI (imei={GPS_IMEI}, har {GPS_EVERY:.0f}s, "
                  f"harakat ostonasi {GPS_MOVING_KMH:.0f} km/s)")
        else:
            print(f"GPS: o'chiq — {gps.last_error}")
            gps = None

    # Telefon uchun alohida model (safedrive.pt ning telefon sinfi o'rniga)
    phonedet = None
    if ENABLE_PHONE_MODEL and os.path.exists(PHONE_MODEL):
        try:
            phonedet = PhoneDetector(PHONE_MODEL, PHONE_MODEL_CONF, PHONE_MODEL_EVERY)
            print(f"Telefon modeli: YOQILDI (conf={PHONE_MODEL_CONF}, "
                  f"{1/PHONE_MODEL_EVERY:.0f} Hz)")
        except Exception as e:
            print("Telefon modeli yuklanmadi:", e)
    elif ENABLE_PHONE_MODEL:
        print(f"Telefon modeli: yo'q ({PHONE_MODEL}) — safedrive.pt ishlatiladi")

    # Yuz yo'qolganda ROI dan qayta qidiruv (qo'l ko'tarilganda, tunda)
    facerec = FaceRecover(pipe, FACE_RECOVER_MARGIN, FACE_RECOVER_MEMORY,
                          FACE_RECOVER_EVERY,
                          seat_file=SEAT_ROI_FILE) if ENABLE_FACE_RECOVER else None
    return mooddet, persondet, gps, phonedet, facerec


def main():
    if not os.path.exists(MODEL_PATH):
        print("XATO: model topilmadi:", MODEL_PATH); return 1
    print("SafeDrive pipeline yuklanmoqda (CPU)...")
    pipe = YoloPipeline(model_path=MODEL_PATH, device="cpu", conf=CONF,
                        detect_phone=ENABLE_PHONE, detect_seatbelt=ENABLE_SEATBELT,
                        detect_smoking=ENABLE_SMOKING, detect_yawn=ENABLE_YAWN)
    pipe.start()
    # safedrive.pt YOLO faqat kamar / sigaret / telefon (zaxira) uchun kerak.
    # Ular o'chiq bo'lsa har kadrda ~42 ms (4 yadro) bekorga ketardi
    # (lok o'lchovi 2026-09-29) — model chaqiruvi bo'sh natija bilan almashtiriladi.
    _phone_via_yolo = ENABLE_PHONE and not (ENABLE_PHONE_MODEL and os.path.exists(PHONE_MODEL))
    if not (ENABLE_SMOKING or ENABLE_SEATBELT or _phone_via_yolo):
        class _NoYolo:
            def predict(self, *a, **k):
                return []
        pipe._model = _NoYolo()
        print("YOLO safedrive.pt: O'CHIRILDI (kamar/sigaret/telefon-zaxira kerak emas) — ~40 ms/kadr tejaladi")
    # eyeBlink blendshape — EAR ning "pastga qarash" xatosini ajratadi
    blend = BlendTap.attach(pipe) if EYE_BLINK_CONFIRM else None

    ctx = RunContext(DEVICE_NAME)
    voice = Voice(ALERT_COOLDOWN)
    recorder = Recorder(RECORD_DIR, REC_FPS, PRE_SECONDS, POST_SECONDS, RECORD_AUDIO)
    manual_rec = False

    mooddet, persondet, gps, phonedet, facerec = _build_detectors(pipe)
    analyzer = FrameAnalyzer(pipe, blend, facerec, persondet, phonedet)

    # Dataset yig'ish (o'rgatish uchun toza kadrlar)
    dscol = None
    if ENABLE_DATASET:
        dscol = DatasetCollector(DATASET_DIR, DATASET_EVERY, DATASET_MAX)
        print(f"Dataset yig'ish: YOQILDI -> {DATASET_DIR} "
              f"(hozir {dscol.n} fayl, chegara {DATASET_MAX})")
    mood_ref = ["-"]                     # joriy kayfiyat (buyruqlar uchun)
    mood_hist = collections.deque()      # (t, mood) — oxirgi 1 soat
    day = DayStats(DAY_FILE)             # kun bo'yicha — diskda, restartga chidamli
    if day.moods or day.incidents:
        print(f"Kunlik statistika tiklandi ({day.date}): "
              f"{sum(day.incidents.values())} buzilish")

    # Telegram
    telegram = Telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ENABLE_TELEGRAM)
    if telegram.ok:
        print(f"Telegram: YOQILDI (chat_id={TELEGRAM_CHAT_ID})")
        # Ulanish xabari GPS ma'lumoti kelgandan keyin yuboriladi (Periodic).
    elif ENABLE_TELEGRAM:
        print("Telegram: chat_id yo'q — botga /start yozing (keyin TELEGRAM_CHAT_ID ga qo'ying).")
    # Sayt (veb-server) — Telegram bilan yonma-yon, o'z navbati bilan
    web = WebClient(WEBHOOK_URL, WEBHOOK_TOKEN, ENABLE_WEBHOOK)
    if web.ok:
        print(f"Sayt: YOQILDI ({WEBHOOK_URL})")
    elif ENABLE_WEBHOOK:
        print("Sayt: WEBHOOK_URL bo'sh — yuborilmaydi.")

    episodes = EpisodeTracker(telegram, web, gps, recorder, day, ctx)

    win = "Argus AI"
    stop_event = threading.Event()
    latest = [None]                          # oxirgi kadr (Telegram /snapshot uchun)
    ident = commands.install(telegram, ctx, gps, recorder, latest, stop_event,
                             mood_hist, episodes, day, mood_ref)
    periodic = Periodic(telegram, web, gps, day, ctx, ident, episodes, facerec, mood_hist)

    snap_buf = collections.deque()      # (vaqt, TOZA kadr) — dalil uchun
    snap_last = -1e9

    if not HEADLESS:
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, 1180, 680)
    print(f"[{ctx.device_name}] Ishga tushdi." + ("" if HEADLESS else " Chiqish: 'q'/ESC."))

    # Kamera — ulanmagan bo'lsa kutadi (mini PC'da USB kamera keyin ulanishi mumkin)
    cap, cam_idx = open_any_camera()
    if cap is None:
        cap, cam_idx = wait_for_camera(win, telegram, stop_event, notify=False)

    while not stop_event.is_set():
        if cap is None:
            break
        try:
            ok, frame = cap.read()
        except Exception:
            ok = False
        if not ok:                            # kamera uzildi → qayta ulanish (hot-plug)
            try: cap.release()
            except Exception: pass
            cap, cam_idx = wait_for_camera(win, telegram, stop_event, notify=True)
            continue

        frame = cv2.flip(frame, 1)
        H, W = frame.shape[:2]
        ctx.H, ctx.W = H, W
        now = time.monotonic()

        # SafeDrive'ning O'Z pipeline'i — kadr toza qoladi (u nusxaga chizadi)
        try:
            res = pipe.process_frame(frame)
        except Exception as e:
            print("Pipeline xatosi (o'tkazildi):", repr(e))
            if not HEADLESS:
                cv2.waitKey(1)
            continue
        # Toza kadr nusxasi — pastda chizish boshlanguncha olib qolamiz
        clean = frame.copy() if dscol is not None else None
        # Dalil buferi: hodisa signali kechikib chiqadi, shuning uchun
        # undan oldingi kadrlarni TOZA holda saqlab turamiz.
        # Har kadrni nusxalash shart emas — 0.6 s oldingi kadrni topish uchun
        # sekundiga 10 ta yetarli. Har kadrda nusxalash FPS ni 1.5 ga
        # tushirgan edi (2.7 MB lik nusxa, sekundiga 18 marta).
        if now - snap_last >= SNAPSHOT_BUF_EVERY:
            snap_last = now
            snap_buf.append((now, frame.copy()))
            while snap_buf and now - snap_buf[0][0] > SNAPSHOT_BUF_SEC:
                snap_buf.popleft()

        # ── Bir kadr qarorlari ──
        fr = analyzer.analyze(frame, res, now)
        active = fr.active

        # OVOZ darhol ishlaydi va GPS filtridan OZOD: poyezd to'xtagan
        # bo'lsa ham haydovchi ogohlantirishni eshitadi.
        voice.play(set(active), now)

        # Xabar uchun: to'xtaganda harakatga bog'liq turlar chiqariladi,
        # qolganlari faqat adminga (guruh va sayt EMAS).
        active = routing.gate_for_report(active, gps)
        ctx.stopped_route = routing.stopped_route(gps)
        rep_active = analyzer.report_set(active, now)

        # Dataset: toza kadrni saqlash (chizishdan OLDIN)
        if dscol is not None:
            dscol.maybe(clean, now, event=bool(active) and DATASET_ON_EVENT)

        # ── Kayfiyat (yuz ifodasi) ──
        if mooddet is not None:
            mood_ref[0] = mooddet.update(frame, now)
            if fr.face_found:
                mood_hist.append((now, mood_ref[0]))
                while mood_hist and now - mood_hist[0][0] > REPORT_INTERVAL:
                    mood_hist.popleft()
                day.add_mood(mood_ref[0])

        # ── Epizodlar: statistika, tugash, ID, matnli xabarlar ──
        episodes.update(rep_active, now, analyzer.describe, fr)

        # ── Davriy ishlar ──
        periodic.step(now, fr, frame)

        # ── Chizish: qutilar (faqat yoqilgan funksiyalar) ──
        allowed = set()
        # Alohida telefon modeli ishlayotgan bo'lsa, safedrive.pt ning telefon
        # qutilari chizilmaydi — ular aynan biz tuzatgan yolg'on signallar.
        if ENABLE_PHONE and phonedet is None:
            allowed.add(5)
        if ENABLE_SMOKING:  allowed.add(6)
        if ENABLE_SEATBELT: allowed.update((7, 8))
        for d in res.get("detections", []):
            cid = d.get("class_id")
            if cid in allowed and cid in BOX_COL:
                draw_box(frame, d["bbox"], BOX_COL[cid], f"{d['class_name']} {d['conf']:.2f}")

        # ── HUD panel — faqat yoqilgan qatorlar (dinamik balandlik) ──
        rows = build_rows(fr, analyzer, active, gps, mood_ref[0], now)
        # Kadr bezaklari — burchak ramkalari va o'lchov chiziqchalari
        frame_decor(frame)
        # Aniqlangan yuz atrofida vizir (qayerga qarayotgani ko'rinsin)
        if fr.face_found and facerec is not None and facerec.box:
            face_reticle(frame, facerec.box, now)
        # Panel — o'lchami mazmunga qarab hisoblanadi
        ph = 33*len(rows) + 72
        stamp = (time.strftime('%Y-%m-%d'), time.strftime('%H:%M:%S'))
        info_panel(frame, 16, H - ph - 16, "ARGUS AI", ctx.device_name, rows, stamp=stamp)

        # ── Xavf banneri ──
        banner_txt, banner_crit = banner(active)
        if banner_txt:
            alert_banner(frame, 30, 26, banner_txt, now, crit=banner_crit)

        # ── Rasm / video yozib olish ──
        if (RECORD_ON_EVENT and rep_active) or manual_rec:
            recorder.trigger(W, H, now, fr.fps)    # hodisa yoki qo'lda → yozuvni ushlab tur
        # Yuqori o'ng burchak: yozuv holati va FPS
        chips(frame, W, fr.fps, recorder.is_recording(), now)
        recorder.step(frame, now)               # joriy kadrni yoz (kerak bo'lsa yop)
        recorder.push(frame, now)               # pre-roll bufer (keyingi klip uchun)

        def _build_evidence():
            """Dalil rasmi: kadr hodisaning O'RTASIDAN olinadi (signal kechikib
            chiqadi), ustiga esa HOZIRGI holat chiziladi. Ikkalasi ham kerak:
            eski kadrdagi eski HUD "hammasi joyida" deb ko'rsatib qo'yardi."""
            ev = None
            if snap_buf:
                bt, bf = min(snap_buf, key=lambda it: abs(it[0] - (now - SNAPSHOT_BACK_SEC)))
                if abs(bt - (now - SNAPSHOT_BACK_SEC)) <= 0.5:
                    ev = bf.copy()
            if ev is None:
                return frame                    # bufer bo'sh — joriy kadr
            frame_decor(ev)
            if fr.face_found and facerec is not None and facerec.box:
                face_reticle(ev, facerec.box, now)
            info_panel(ev, 16, H - ph - 16, "ARGUS AI", ctx.device_name, rows, stamp=stamp)
            chips(ev, W, fr.fps, True, now)
            if banner_txt:
                alert_banner(ev, 30, 26, banner_txt, now, crit=banner_crit)
            return ev
        episodes.attach_media(_build_evidence, rep_active, now)

        latest[0] = frame                     # Telegram /snapshot uchun (oxirgi kadr)

        if not HEADLESS:
            text(frame, "s:rasm r:yozuv t:hisobot q:chiqish", (W-320, H-16), 0.45, C_DIM, 1)
            cv2.imshow(win, frame)
            k = cv2.waitKey(1) & 0xFF
            if k == ord('s'):
                recorder.snapshot(frame)
            elif k == ord('r'):
                manual_rec = not manual_rec
                print("Qo'lda yozuv:", "YOQILDI" if manual_rec else "O'CHDI")
            elif k == ord('t') and telegram.ok:
                telegram.send(build_report(mood_hist, episodes.incident_hist))
            if k in (ord('q'), 27) or cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                stop_event.set()

    if telegram.ok:
        try:
            telegram.broadcast_sync(f"\U0001F534 [{ctx.device_name}] ARGUS AI to'xtatildi.")
        except Exception:
            pass
    try: recorder.close()
    except Exception: pass
    if cap is not None:
        try: cap.release()
        except Exception: pass
    if not HEADLESS:
        cv2.destroyAllWindows()
    try:
        pipe.stop()
    except Exception:
        pass
    print("Tugadi.")
    return 0


def _supervisor():
    """Har qanday kutilmagan xatoda dastur QULAB TUSHMAYDI — biroz kutib qayta
    ishga tushadi (mini PC'da avtonom ishlashi uchun)."""
    while True:
        try:
            return main()
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            import traceback
            print("ASOSIY XATO — 5s dan keyin qayta ishga tushadi:", repr(e))
            traceback.print_exc()
            time.sleep(5)
