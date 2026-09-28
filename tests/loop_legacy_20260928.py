# -*- coding: utf-8 -*-
"""ARGUS AI — asosiy tsikl.

Kod app.py dan ajratilgan, mantiq o'zgartirilmagan.
"""
import os
import sys
import time
import json
import uuid
import threading
import collections

import cv2
import numpy as np

from config import *
try:
    TAMPER_DROP
except NameError:
    TAMPER_DROP = 40.0        # yorug'lik EMA'dan shuncha keskin tushsa (va qorong'i bo'lsa) -> yopilish
try:
    TAMPER_EMA_ALPHA
except NameError:
    TAMPER_EMA_ALPHA = 0.02   # ~3 s vaqt doimiysi @18 FPS
# Ko'z yumuqligini blendshape bilan tasdiqlash (argus/detect/eyes.py) —
# config'da bo'lmasa shu qiymatlar ishlaydi.
try:
    EYE_BLINK_CONFIRM
except NameError:
    EYE_BLINK_CONFIRM = True
try:
    EYE_BLINK_BS_MIN
except NameError:
    EYE_BLINK_BS_MIN = 0.6    # eyeBlink (3 kadr mediana) shundan past -> "yumuq" EMAS (pastga qarash)
try:
    EYE_FACE_CUT_UNRELIABLE
except NameError:
    EYE_FACE_CUT_UNRELIABLE = True   # yuz kadr chetida kesilgan -> ko'z o'lchovi ishonchsiz
try:
    PERCLOS_MIN_SAMPLES
except NameError:
    PERCLOS_MIN_SAMPLES = 300  # oynada kamida shuncha yuzli kadr bo'lmasa PERCLOS xabar bermaydi
# To'xtagan poyezdda buzilishlar FAQAT adminning botiga boradi (guruh va sayt EMAS)
try:
    STOPPED_ADMIN_ONLY
except NameError:
    STOPPED_ADMIN_ONLY = True
# Deploy'dan keyin bir marta yuboriladigan xabar fayli (deploy skripti yozadi)
try:
    DEPLOY_NOTE_FILE
except NameError:
    DEPLOY_NOTE_FILE = os.path.join(HERE, "deploy_note.txt")
# O'rganilgan o'rindiq ROI fayli (tunda yuzni topish uchun, reverify.FaceRecover)
try:
    SEAT_ROI_FILE
except NameError:
    SEAT_ROI_FILE = os.path.join(HERE, "seat_roi.json")
# Bir turdagi buzilish shu s ichida qaytsa — o'sha epizod davom etadi
# (bitta ID, yangi rasm/video yo'q). Epizod shu s tinch turgach yopiladi.
try:
    INCIDENT_REJOIN_SEC
except NameError:
    INCIDENT_REJOIN_SEC = 120.0
from safedrive.pipelines.yolo_pipeline import YoloPipeline

from argus.utils import ts_from_name, human_delay, human_dur
from argus.hud import (draw_box, info_panel, alert_banner,
                       chips, frame_decor, face_reticle, text)
from argus.detect.windows import PresenceWindow, Sustain, EpisodeHold
from argus.detect.drowsy import Perclos, BlinkTracker, EarBaseline
from argus.detect.eyes import BlendTap, BlinkConfirm
from argus.detect.reverify import FaceRecover, Confirm, Grace
from argus.detect.mood import MoodDetector
from argus.detect.phone import PhoneDetector
from argus.detect.person import PersonDetector
from argus.media.voice import Voice
from argus.media.recorder import Recorder
from argus.media.camera import open_any_camera, wait_for_camera, status_screen
from argus.media.dataset import DatasetCollector
from argus.net.telegram import Telegram
from argus.net.web import WebClient
from argus.net.gps import GpsClient
from argus.report import (build_report, report_data, day_report_data,
                          DayStats, build_daily_report)


def main():
    global DEVICE_NAME
    if not os.path.exists(MODEL_PATH):
        print("XATO: model topilmadi:", MODEL_PATH); return 1
    print("SafeDrive pipeline yuklanmoqda (CPU)...")
    pipe = YoloPipeline(model_path=MODEL_PATH, device="cpu", conf=CONF,
                        detect_phone=ENABLE_PHONE, detect_seatbelt=ENABLE_SEATBELT,
                        detect_smoking=ENABLE_SMOKING, detect_yawn=ENABLE_YAWN)
    pipe.start()
    # eyeBlink blendshape — EAR ning "pastga qarash" xatosini ajratadi
    blend = BlendTap.attach(pipe) if EYE_BLINK_CONFIRM else None

    voice = Voice(ALERT_COOLDOWN)
    recorder = Recorder(RECORD_DIR, REC_FPS, PRE_SECONDS, POST_SECONDS, RECORD_AUDIO)
    manual_rec = False
    banner_txt, banner_crit = "", False
    cur_detail = ""     # joriy epizodning o'lchangan qiymati (rasm/videoga ham)
    clip_det = {}       # klip yo'li -> o'sha epizodning qiymati
    prev_active = False
    prev_tags = set()      # oldingi kadrdagi faol buzilishlar (EPIZODni sanash uchun)
    cur_uid = None         # joriy hodisaning yagona ID si
    clip_uids = {}         # klip yo'li -> UID (video keyinroq yopiladi)
    clip_sent = set()      # video yuborilgan UID lar (bir epizodga bitta klip)
    ep_hold = EpisodeHold(INCIDENT_REJOIN_SEC)   # epizodni ushlab turish
    pending_uid = None     # klip fayli hali ochilmagan bo'lsa — navbatda turadi
    pending_det = ""     # o'sha klipga tegishli o'lchangan qiymat

    # Kayfiyat aniqlash
    mooddet = None
    if ENABLE_MOOD and os.path.exists(MOOD_MODEL) and os.path.exists(MOOD_ONNX):
        try:
            mooddet = MoodDetector(MOOD_MODEL, MOOD_ONNX, MOOD_EVERY)
            print("Kayfiyat aniqlash: YOQILDI (FER+ emotion CNN)")
        except Exception as e:
            print("Kayfiyat yuklanmadi:", e)

    # Odam aniqlash — yuz yo'q bo'lganda "to'sgan" va "chiqib ketgan"ni ajratadi
    persondet = None
    # Odam-detektor 'yoq' UCHUN HAM, 'yuz' darvozasi UCHUN HAM kerak: odam yo'q
    # bo'lsa 'Yuz ko'rinmayapti' yuborilmaydi (bo'sh o'rindiq = yuz yo'q, bu
    # ortiqcha xabar). ENABLE_PERSON faqat 'yoq' XABARINI boshqaradi (444-445).
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

    # Dataset yig'ish (o'rgatish uchun toza kadrlar)
    dscol = None
    if ENABLE_DATASET:
        dscol = DatasetCollector(DATASET_DIR, DATASET_EVERY, DATASET_MAX)
        print(f"Dataset yig'ish: YOQILDI -> {DATASET_DIR} "
              f"(hozir {dscol.n} fayl, chegara {DATASET_MAX})")
    cur_mood = "-"
    mood_hist = collections.deque()      # (t, mood) — oxirgi 1 soat
    incident_hist = collections.deque()  # (t, tag) — oxirgi 1 soat
    day = DayStats(DAY_FILE)             # kun bo'yicha — diskda, restartga chidamli
    if day.moods or day.incidents:
        print(f"Kunlik statistika tiklandi ({day.date}): "
              f"{sum(day.incidents.values())} buzilish")

    # Telegram
    telegram = Telegram(TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, ENABLE_TELEGRAM)
    if telegram.ok:
        print(f"Telegram: YOQILDI (chat_id={TELEGRAM_CHAT_ID})")
        # Ulanish xabari pastda, GPS ma'lumoti kelgandan keyin yuboriladi -
        # shunda u lokomotiv raqami va mashinist bilan birga boradi.
    elif ENABLE_TELEGRAM:
        print("Telegram: chat_id yo'q — botga /start yozing (keyin TELEGRAM_CHAT_ID ga qo'ying).")
    # Sayt (veb-server) — Telegram bilan yonma-yon, o'z navbati bilan
    web = WebClient(WEBHOOK_URL, WEBHOOK_TOKEN, ENABLE_WEBHOOK)
    if web.ok:
        print(f"Sayt: YOQILDI ({WEBHOOK_URL})")
    elif ENABLE_WEBHOOK:
        print("Sayt: WEBHOOK_URL bo'sh — yuborilmaydi.")

    tg_last = {}
    tg_repeat = {}      # tur -> necha marta xabar berilgan (davomli holat uchun)
    tg_since = {}       # tur -> holat qachon boshlangan
    tg_uid = {}         # tur -> epizod UID (tugash xabari shu UID bilan ketadi)
    last_report = time.monotonic()
    # Klip tayyor bo'lganda → Telegram'ga video yuborish
    # Klip vaqti fayl NOMIDAN olinadi — klip hodisadan bir necha soniya keyin
    # yopiladi, yuborish esa internet uzilsa yana ham kechikishi mumkin.
    def _on_clip(p):
        # Klip o'sha hodisaning UID si bilan ketadi (hodisa boshlanganda
        # yozib qo'yilgan edi). Topilmasa - yangi id beriladi.
        uid = clip_uids.pop(p, None)
        # Bir epizodga (UID) faqat BITTA video: epizod ichida yuz qayta
        # yo'qolib klip yana yozilsa, u diskda qoladi, lekin yuborilmaydi.
        if uid and uid in clip_sent:
            print("Klip yuborilmadi (epizod davom etyapti, video allaqachon ketgan):",
                  os.path.basename(p), uid)
            clip_det.pop(p, None)
            return
        if uid:
            clip_sent.add(uid)
            if len(clip_sent) > 500:
                clip_sent.clear()
        telegram.send_video(p, f"\U0001F3A5 [{DEVICE_NAME}] hodisa yozuvi\n"
                               f"Vaqt: {ts_from_name(p)}"
                               + (f"\nID: {uid}" if uid else ""),
                            admin_only=stopped_route)
        det_c = clip_det.pop(p, None) or None
        if not stopped_route:
            web.send_incident("klip", "Hodisa yozuvi", video=p, uid=uid,
                              detail=det_c,
                              extra=gps.info() if gps else None)
    recorder.on_clip = _on_clip
    phone_pw = PresenceWindow(PHONE_WINDOW, PHONE_RATIO, PHONE_MIN)
    smoke_pw = PresenceWindow(SMOKE_WINDOW, SMOKE_RATIO, SMOKE_MIN)
    belt_pw  = PresenceWindow(BELT_WINDOW,  BELT_RATIO,  BELT_MIN)
    eye_sus  = Sustain(EYE_CLOSED_SEC)
    yawn_sus = Sustain(YAWN_SEC)
    distract_sus = Sustain(DISTRACT_SEC)
    tamper_sus = Sustain(TAMPER_SEC)
    tamper_bright_ema = None      # tamper: yorug'lik EMA (keskin tushishni aniqlash)
    noface_sus = Sustain(NOFACE_SEC)
    # Yuz yo'qolganda ROI dan qayta qidiruv (qo'l ko'tarilganda yordam beradi)
    facerec = FaceRecover(pipe, FACE_RECOVER_MARGIN, FACE_RECOVER_MEMORY,
                          FACE_RECOVER_EVERY,
                          seat_file=SEAT_ROI_FILE) if ENABLE_FACE_RECOVER else None
    # Yangi buzilishni e'lon qilishdan oldin qayta tasdiqlash
    confirm = Confirm(CONFIRM_SEC, CONFIRM_TAGS) if CONFIRM_SEC > 0 else None
    # Ruxsat etilgan vaqt (telefon 3 daqiqa) — ovoz ishlaydi, xabar kutadi
    grace = Grace(GRACE_SEC, GRACE_WINDOW, GRACE_BRIDGE)
    absent_sus = Sustain(ABSENT_SEC)
    micro_sus  = Sustain(MICROSLEEP_SEC)          # 0.5 s — mikrouyqu
    perclos    = Perclos(PERCLOS_WINDOW, PERCLOS_MIN_SAMPLES)
    blinks     = BlinkTracker(BLINK_WINDOW, BLINK_MIN_SAMPLES)
    pc_warn_sus = Sustain(PERCLOS_HOLD)           # qisqa sakrashga qarshi
    pc_crit_sus = Sustain(PERCLOS_HOLD)
    W = H = 0                   # birinchi kadrda to'ldiriladi
    last_clean = time.monotonic()
    hello_sent = False
    hello_t0 = time.monotonic()
    deploy_note_done = False
    stopped_route = False       # True -> xabarlar faqat adminga, saytga yo'q
    last_face_t = None          # yuz oxirgi marta ko'ringan vaqt
    ear_raw = collections.deque(maxlen=max(4, EYE_VOLATILE_WIN))
    blink_cf = BlinkConfirm(EYE_BLINK_BS_MIN, EYE_SMOOTH_N)   # eyeBlink tasdiqi
    blink_bs = None
    snap_buf = collections.deque()      # (vaqt, TOZA kadr) — dalil uchun
    snap_last = -1e9
    fps_hist = collections.deque(maxlen=2000)
    last_fps_log = time.monotonic()
    probe_last = -1e9           # yuz topilmagan daqiqa: toza kadr saqlash vaqti
    ear_hist = collections.deque(maxlen=max(1, EYE_SMOOTH_N))
    ear_base = (EarBaseline(EAR_BASE_WINDOW, EAR_BASE_PCT, EAR_BASE_MIN_SAMPLES,
                            EAR_BASE_FLOOR, EAR_BASE_CAP,
                            EAR_OPEN_RATIO, EAR_HALF_RATIO)
                if EAR_ADAPTIVE else None)
    tilt_base = nod_base = 0.0   # baza to'lmaguncha ishlatilmaydi
    tilt_hist = collections.deque(maxlen=300)   # "old qarash" bazasi uchun tarix
    nod_hist  = collections.deque(maxlen=300)

    win = "Argus AI"
    stop_event = threading.Event()
    latest = [None]                          # oxirgi kadr (Telegram /snapshot uchun)

    # Telegram boshqaruv hooklari (headless — klaviatura yo'q, buyruqlar orqali)
    telegram.cmd_report = lambda: build_report(mood_hist, incident_hist)
    telegram.cmd_daily = lambda: build_daily_report(day)
    telegram.cmd_status = lambda: (f"[{DEVICE_NAME}] Ishlayapti | Kayfiyat: {cur_mood} | "
                                   f"Navbatda: {len(telegram.outbox)}")
    telegram.cmd_stop = lambda: stop_event.set()

    def _ident():
        """Qurilma va lokomotiv ma'lumoti - /id buyrug'i uchun."""
        out = [f"Qurilma: {DEVICE_NAME}"]
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
        out.append(f"Kamera: {W}x{H}")
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
            telegram.send_photo(p, f"[{DEVICE_NAME}] Snapshot\n"
                                   f"Vaqt: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    telegram.cmd_snapshot = _do_snapshot

    if not HEADLESS:
        cv2.namedWindow(win, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(win, 1180, 680)
    print(f"[{DEVICE_NAME}] Ishga tushdi." + ("" if HEADLESS else " Chiqish: 'q'/ESC."))

    # Kamera — ulanmagan bo'lsa kutadi (mini PC'да USB kamera keyin ulanishi mumkin)
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

        eye_state = res.get("eye_state", "unknown")
        face_found = bool(res.get("face_found"))
        # Yuz topilmadi deyilsa — DARHOL ishonmaymiz. Oxirgi ma'lum joy
        # atrofidan kesib qayta qidiramiz: qo'l boshdan yuqori ko'tarilganda
        # detektor butun kadrda yuzni yo'qotadi, parchada esa topadi.
        if facerec is not None:
            if face_found:
                facerec.note(res.get("landmarks"),
                             frame.shape[1], frame.shape[0], now)
            else:
                again = facerec.retry(frame, now)
                if again:
                    res.update(again)
                    face_found = True
                    eye_state = res.get("eye_state", "unknown")
        # blink/down/cut — qayta qidiruvdan KEYIN (ROI natijasi ham shu yerda)
        cues = blend.cues() if blend is not None else {}

        # EAR ni silliqlaymiz va ko'z holatini QAYTA hisoblaymiz. Bitta
        # kadrlik chetlanish (landmark chayqalishi) shu yerda to'xtaydi.
        if not face_found:
            ear_hist.clear(); ear_raw.clear()
            # Baza qisqa uzilishda SAQLANADI — pastga qarab turgan haydovchi
            # bir kadrga yo'qolsa, moslashuv nolga tushib ketmasin.
            if (ear_base is not None and last_face_t is not None
                    and now - last_face_t > EAR_BASE_RESET_SEC):
                ear_base.reset()
        else:
            last_face_t = now
            ear_raw.append(float(res.get("ear") or 0.0))
            ear_hist.append(float(res.get("ear") or 0.0))
            v = sorted(ear_hist)
            med = v[len(v) // 2] if len(v) % 2 else (v[len(v)//2 - 1] + v[len(v)//2]) / 2.0
            # Ostonalar odamga moslashadi: ochiq ko'z darajasi har kimda
            # boshqacha, kameraning burchagi ham ta'sir qiladi.
            t_open, t_half = EAR_OPEN, EAR_HALF
            if ear_base is not None:
                ear_base.update(med, now)
                t_open, t_half = ear_base.thresholds(EAR_OPEN, EAR_HALF)
            eye_state = ("open" if med >= t_open
                         else "half" if med >= t_half else "closed")
        yawn = bool(res.get("yawn_detected"))
        phone = bool(res.get("phone_detected"))
        # Alohida model bor bo'lsa — safedrive.pt ning javobini ALMASHTIRAMIZ
        if phonedet is not None:
            phone = phonedet.update(frame, now)
        smoke = bool(res.get("smoking_detected"))
        belt = res.get("seatbelt_present", None)     # True/False/None
        head_tilt = float(res.get("head_tilt", 0.0))
        head_nod = float(res.get("head_nod", 0.0))
        fps = float(res.get("fps", 0.0))

        eye_closed = (eye_state == "closed")

        # Chalg'ish — moslashuvchan baza (medianadan chetlanish)
        looking_away = False
        eye_reliable = True          # bosh kuchli egilmagan bo'lsa - ishonchli
        if face_found:
            tilt_hist.append(head_tilt); nod_hist.append(head_nod)
            if len(tilt_hist) >= BASE_MIN:
                ts = sorted(tilt_hist); ns = sorted(nod_hist)
                tilt_base = ts[len(ts)//2]; nod_base = ns[len(ns)//2]
                looking_away = (head_tilt > tilt_base + TILT_MARGIN or
                                head_nod > nod_base + NOD_MARGIN)
                # Bosh juda pastga egilgan -> EAR yolg'on "yumuq" beradi
                eye_reliable = (head_nod <= nod_base + EYE_NOD_LIMIT)
        # EAR kadrdan kadrga sakrayotgan bo'lsa — ko'z nuqtalari yuzda emas
        # (qo'l, telefon yoki boshqa narsa bekitgan). Bunday o'lchovga
        # uyqu qarori qurib bo'lmaydi.
        eye_shaky = False
        if len(ear_raw) >= 4:
            d = sorted(abs(ear_raw[k] - ear_raw[k-1]) for k in range(1, len(ear_raw)))
            eye_shaky = d[len(d)//2] > EYE_VOLATILE_MAX
            if eye_shaky:
                eye_reliable = False
        # Yuz kadr chetida kesilgan — landmark'lar taxminiy (00:33 klipi)
        if EYE_FACE_CUT_UNRELIABLE and cues.get("cut"):
            eye_reliable = False
        # eyeBlink tasdiqi: pastga qarashda EAR "yumuq" beradi, blendshape
        # esa 0.36-0.55 da qoladi; haqiqiy yumuqda 0.77. Ma'lumot bo'lmasa True.
        blink_sure, blink_bs = blink_cf.update(cues.get("blink") if face_found else None)

        # Kamera to'silishi (tamper) — tafsilot (Laplacian) + KESKIN qorong'ilashish.
        # Mutlaq qorong'ilik tamper belgisi EMAS: tunda yoritilmagan kabina 15 dan
        # past tushadi, lekin tuzilish saqlanadi (o'lchov 2026-09-25 18:40: yorug'lik
        # 13.7, tafsilot 42). Yopilgan lens tafsilotni yo'qotadi VA yorug'likni bir
        # lahzada tushiradi. Shom asta keladi -> EMA'dan drop bo'lmaydi.
        blocked = False
        if ENABLE_TAMPER:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_b = float(gray.mean())
            detail = float(cv2.Laplacian(gray, cv2.CV_64F).var())
            if tamper_bright_ema is None:
                tamper_bright_ema = mean_b
            sudden_dark = ((tamper_bright_ema - mean_b) > TAMPER_DROP
                           and mean_b < TAMPER_DARK_MEAN)
            blocked = (detail < TAMPER_DETAIL_VAR) or sudden_dark
            # sekin EMA (~3 s @18 FPS): asta qorong'ilashish drop hisoblanmaydi
            tamper_bright_ema += (mean_b - tamper_bright_ema) * TAMPER_EMA_ALPHA

        # Debounce / sustain (SafeDrive aniqlashi ustida)
        # Bosh pastga egilgan bo'lsa ko'z o'lchovi ishonchsiz — uyqu o'lchanmaydi
        eye_ok = eye_closed and eye_reliable and blink_sure
        drowsy_al = eye_sus.update(eye_ok, now)
        micro_al  = micro_sus.update(eye_ok, now)         # 0.5 s — mikrouyqu
        yawn_al   = yawn_sus.update(yawn, now)

        # PERCLOS va pirpirash — faqat yuz ko'rinib turganda o'lchanadi,
        # aks holda "ko'z ochiq" deb noto'g'ri hisoblanib ketardi.
        perclos_val, blink_ms = 0.0, None
        perclos_warn = perclos_crit = blink_slow = False
        if face_found and eye_reliable:
            # Tasdiqlanmagan "yumuq" (pastga qarash) PERCLOS'da yarim hisoblanadi
            perclos_val = perclos.update(
                eye_state if (eye_state != "closed" or blink_sure) else "half", now)
            blinks.update(eye_closed and blink_sure, now)
        else:
            perclos_val = perclos.decay(now)       # oyna baribir tozalanadi
        blink_ms = blinks.mean_ms()
        if ENABLE_PERCLOS and perclos.ready():
            # Qisqa sakrash signal bermasin — qiymat PERCLOS_HOLD soniya
            # UZLUKSIZ ostonadan yuqori turishi kerak.
            perclos_crit = pc_crit_sus.update(perclos_val > PERCLOS_CRIT, now)
            perclos_warn = (not perclos_crit) and \
                           pc_warn_sus.update(perclos_val > PERCLOS_WARN, now)
        if ENABLE_BLINK and blink_ms is not None:
            blink_slow = blink_ms > BLINK_SLOW_MS
        distract_al = distract_sus.update(looking_away, now)
        tamper_al = tamper_sus.update(blocked, now)

        # Kamera soz, lekin yuz yo'q — odam bormi yoki chiqib ketganmi?
        # persondet FAQAT shu holatda ishlaydi (yuz bor bo'lsa chaqirilmaydi).
        if face_found:
            person_present = True
            if persondet is not None:
                persondet.present = True        # holat yangilanib turadi
        elif persondet is not None and not blocked:
            person_present = persondet.update(frame, now)
        else:
            person_present = True               # model yo'q → eski xatti-harakat

        gap = (not face_found) and (not blocked)
        noface_al = noface_sus.update(gap and person_present, now)      # to'sgan
        absent_al = absent_sus.update(gap and not person_present, now)  # chiqib ketgan
        phone_al  = phone_pw.update(phone, now)
        smoke_al  = smoke_pw.update(smoke, now)
        belt_al   = belt_pw.update(belt is False, now)

        # Faol xavflar → ovoz NAVBAT bilan (faqat YOQILGAN funksiyalar).
        # Kamera to'silган bo'lса — boshqa aniqlash ishonchsiz, faqat "kamera".
        if ENABLE_TAMPER and tamper_al:
            active = ["kamera"]
        else:
            active = []
            # Uyqu bosqichlari: to'liq uyqu mikrouyquni YUTADI (elif) — aks
            # holda bitta uzun yumilish ikkala hisoblagichga ham tushardi.
            if ENABLE_DROWSY and drowsy_al:
                active.append("uyqu")
            elif ENABLE_MICROSLEEP and micro_al:
                active.append("mikrouyqu")
            # PERCLOS — uzluksiz yumilish bo'lmasa ham charchoqni ko'rsatadi
            if perclos_crit: active.append("uyquchan_kr")
            elif perclos_warn: active.append("uyquchan")
            if blink_slow:  active.append("pirpirash")
            if ENABLE_NOFACE   and noface_al:   active.append("yuz")
            if ENABLE_PERSON   and absent_al:   active.append("yoq")
            if ENABLE_SMOKING  and smoke_al:    active.append("sigaret")
            if ENABLE_PHONE    and phone_al:    active.append("telefon")
            if ENABLE_DISTRACT and distract_al: active.append("chalgish")
            if ENABLE_SEATBELT and belt_al:     active.append("kamar")
            if ENABLE_YAWN     and yawn_al:      active.append("esnash")
        # Odam o'rindiqda bo'lmasa — hech qanday buzilish yuborilmaydi
        # (uyqu/esnash/chalg'ish/kamar/telefon/sigaret bo'sh o'rindiqda ma'nosiz).
        # Istisno: 'kamera' (yopilgan lens odamni ham ko'rsatmaydi — darvozalansa
        # to'silish hech qachon xabar bermaydi) va 'yoq' (aynan odam yo'qligi).
        if not person_present:
            active = [a for a in active if a in ("kamera", "yoq")]
        # Qayta tasdiqlash: yangi buzilish qisqa vaqt saqlanib tursin.
        # Bir kadrlik sakrash shu yerda to'xtaydi va ovozga, Telegram'ga,
        # saytga chiqmaydi. Uyquga oid turlar bundan ozod (CONFIRM_TAGS).
        if confirm is not None:
            active = confirm.update(active, now)

        # OVOZ darhol ishlaydi va GPS filtridan OZOD: poyezd to'xtagan
        # bo'lsa ham haydovchi ogohlantirishni eshitadi. Ilgari filtr
        # ovozni ham o'chirib qo'yardi — to'xtagan poyezdda telefon
        # aniqlansa ham hech qanday signal chiqmasdi.
        voice.play(set(active), now)

        # Poyezd TO'XTAGAN bo'lsa harakatga bog'liq turlar BUZILISH emas.
        # Temir yo'l standarti: hushyorlik nazorati 10 km/soatdan yuqorida
        # yoqiladi. Bu faqat xabar va statistikaga taalluqli, ovozga emas.
        if gps is not None and not gps.is_moving():
            active = [a for a in active if a not in GPS_GATED_TAGS]
        # To'xtagan poyezd: qolgan buzilishlar FAQAT adminning botiga,
        # guruhga va saytga ketmaydi (depoda kamera oldida turish buzilish emas).
        stopped_route = bool(STOPPED_ADMIN_ONLY and gps is not None
                             and not gps.is_moving())

        # XABAR uchun alohida ro'yxat: ruxsat etilgan vaqtdan oshganlar.
        # Telefon 3 daqiqagacha bu ro'yxatga tushmaydi.
        rep_active = grace.update(active, now)
        # Epizod hisobi uchun "ushlab turilgan" ro'yxat: tur REJOIN oynasida
        # qaytsa yangi epizod ochilmaydi (yozuv/ovoz esa rep_active bo'yicha).
        held_active = ep_hold.update(rep_active, now)

        # Dataset: toza kadrni saqlash (chizishdan OLDIN)
        if dscol is not None:
            dscol.maybe(clean, now, event=bool(active) and DATASET_ON_EVENT)

        # ── Kayfiyat (yuz ifodasi) ──
        if mooddet is not None:
            cur_mood = mooddet.update(frame, now)
            if face_found:
                mood_hist.append((now, cur_mood))
                while mood_hist and now - mood_hist[0][0] > REPORT_INTERVAL:
                    mood_hist.popleft()
                day.add_mood(cur_mood)

        # ── Buzilish tarixi + Telegram (yangi hodisada, turi bo'yicha cooldown) ──
        # Faqat YANGI boshlangan buzilish sanaladi. `active` hodisa davom
        # etguncha to'la turadi — har kadrda sanalsa, 4 soniyalik bitta uyqu
        # "Uyqu×53" bo'lib ko'rinardi.
        new_tags = set(held_active) - prev_tags
        for tag in new_tags:
            incident_hist.append((now, tag))
            day.add_incident(tag)
        prev_tags = set(held_active)
        while incident_hist and now - incident_hist[0][0] > REPORT_INTERVAL:
            incident_hist.popleft()
        day.save()                      # o'zi 30 s da bir marta yozadi
        # Buzilish xabari — Telegram'ga HAM, saytga HAM (ikkalasi mustaqil;
        # biri o'chiq/ishlamayotgan bo'lsa ikkinchisi baribir yuboradi).
        # Holat tugagan turlarning hisoblagichi nolga tushadi — keyingi
        # safar yana darhol xabar beriladi.
        for t in list(tg_repeat):
            if t in held_active:
                continue
            # Davomiylik — oxirgi FAOL vaqtgacha (ushlab turish oynasi kirmaydi)
            dur = ep_hold.seen(t, now) - tg_since.get(t, now)
            # Uzoq davom etgan holat tugadi — buni bir marta bildiramiz.
            # Qisqa epizodda bu ortiqcha: boshlanish xabarining o'zi yetarli.
            if INCIDENT_END_MSG and dur >= INCIDENT_END_MIN:
                lab = TG_MSG.get(t, t)
                telegram.send(TXT_END.format(
                    dev=DEVICE_NAME, label=lab, dur=human_dur(dur),
                    vaqt=time.strftime('%Y-%m-%d %H:%M:%S'),
                    uid=tg_uid.get(t) or "-"), admin_only=stopped_route)
                ex = dict(gps.info()) if gps else {}
                ex["phase"] = "end"
                ex["duration_sec"] = round(dur, 1)
                if not stopped_route:
                    web.send_incident(t, lab, uid=tg_uid.get(t),
                                      detail="tugadi", extra=ex)
            tg_repeat.pop(t, None)
            tg_since.pop(t, None)
            tg_uid.pop(t, None)

        # Yangi epizod boshlandi - UID SHU YERDA beriladi, xabardan OLDIN.
        # Ilgari u rasm blokida berilardi, u esa 200 satr pastda ishlaydi:
        # natijada epizodning BIRINCHI matnli xabari oldingi epizodning ID
        # sini olib ketardi va sayt uni rasm bilan bog'lay olmasdi.
        if held_active and not prev_active:
            cur_uid = uuid.uuid4().hex[:12]
            cur_detail = ""

        for tag in rep_active:
            n = tg_repeat.get(tag, 0)
            # INCIDENT_REPEAT=False → epizodga faqat BITTA xabar
            if n and not INCIDENT_REPEAT:
                continue
            gap = INCIDENT_BACKOFF[min(n, len(INCIDENT_BACKOFF) - 1)]
            if now - tg_last.get(tag, -1e9) >= gap:
                tg_last[tag] = now
                tg_repeat[tag] = n + 1
                tg_since.setdefault(tag, now)
                tg_uid.setdefault(tag, cur_uid)
                label = TG_MSG.get(tag, tag)
                # O'lchangan qiymatni ham qo'shamiz — quruq "buzilish" o'rniga
                # nima asosda qaror qilinganini ko'rsatadi.
                det = ""
                if tag in ("uyquchan", "uyquchan_kr"):
                    det = f"\nPERCLOS: {perclos_val*100:.0f}%  (ostona {PERCLOS_WARN*100:.0f}/{PERCLOS_CRIT*100:.0f}%)"
                elif tag == "pirpirash" and blink_ms:
                    det = f"\nPirpirash: {blink_ms:.0f} ms  (ostona {BLINK_SLOW_MS:.0f} ms)"
                elif tag in ("uyqu", "mikrouyqu") and eye_sus.since:
                    det = f"\nKo'z yumuq: {now - eye_sus.since:.1f} s"
                    if blink_bs is not None:
                        det += f"  (eyeBlink {blink_bs:.2f})"
                elif tag == "telefon" and phonedet is not None:
                    el = grace.elapsed("telefon", now)
                    det = f"\nIshonch: {phonedet.score:.2f}"
                    if el:
                        det += (f"  |  {human_dur(el)} davom etdi"
                                f"  (ruxsat {human_dur(GRACE_SEC['telefon'])})")
                elif tag == "kamera":
                    det = f"\nYorug'lik: {mean_b:.0f}  tafsilot: {detail:.0f}"
                elif tag == "yuz":
                    # Yuz qancha vaqt ko'rinmayapti va odam kadrdami
                    d0 = noface_sus.since
                    det = ("\nYuz ko'rinmagan: %.1f s  (ostona %.0f s)"
                           % ((now - d0) if d0 else 0.0, NOFACE_SEC))
                    det += ("  |  odam kadrda: bor" if person_present
                            else "  |  odam kadrda: yo'q")
                    if facerec is not None:
                        det += "  |  " + facerec.stats()
                elif tag == "yoq":
                    d0 = absent_sus.since
                    det = ("\nO'rinda yo'q: %.0f s  (ostona %.0f s)"
                           % ((now - d0) if d0 else 0.0, ABSENT_SEC))
                elif tag == "chalgish":
                    # Bazadan qancha chetlashgani - qaror shu asosda chiqadi
                    det = ("\nBurilish: %.0f\u00b0 (baza %.0f\u00b0, ostona +%.0f\u00b0)"
                           % (head_tilt, tilt_base, TILT_MARGIN))
                    det += ("  |  egilish: %.0f\u00b0 (baza %.0f\u00b0, ostona +%.0f\u00b0)"
                            % (head_nod, nod_base, NOD_MARGIN))
                elif tag == "kamar":
                    det = "\nKamar: taqilmagan"
                elif tag == "sigaret":
                    cf = float(res.get("smoking_confidence") or 0.0)
                    det = "\nIshonch: %.2f" % cf if cf else ""
                elif tag == "esnash":
                    d0 = yawn_sus.since
                    det = ("\nOg'iz ochiq: %.1f s  (ostona %.0f s)"
                           % ((now - d0) if d0 else 0.0, YAWN_SEC))
                # Takroriy xabar bo'lsa — nechanchisi va qancha vaqtdan beri
                rep = ""
                if n:
                    dur = now - tg_since.get(tag, now)
                    rep = (f"\n↻ {n+1}-xabar, "
                           + (f"{dur/60:.0f} daqiqadan" if dur < 3600 else f"{dur/3600:.1f} soatdan")
                           + " beri davom etyapti")
                gtxt = gps.text() if gps else ""
                telegram.send(f"⚠️ [{DEVICE_NAME}] Buzilish: {label}\n"
                              f"Vaqt: {time.strftime('%Y-%m-%d %H:%M:%S')}{det}{rep}"
                              + (f"\n{gtxt}" if gtxt else "")
                              + (f"\nID: {cur_uid}" if cur_uid else ""),
                              admin_only=stopped_route)
                one = det.strip().replace("\n", "; ")
                # Qiymat rasm va videoga ham biriktiriladi: ular alohida
                # so'rov bo'lib ketadi va sayt oxirgisini ustiga yozsa,
                # o'lchangan qiymat yo'qolib qolmasin.
                if one:
                    cur_detail = (cur_detail + " | " + one) if cur_detail else one
                if not stopped_route:
                    web.send_incident(tag, label, uid=cur_uid,
                                      detail=one or None,
                                      extra=gps.info() if gps else None)

        # ── Ulanish xabari (bir marta) ──
        # Internet bo'lmasa navbatda turadi va ulanishi bilan yetib boradi.
        # GPS javobini kutamiz: shunda xabar lokomotiv raqami va mashinist
        # bilan birga boradi, ya'ni qurilma o'zini tanitadi.
        if not hello_sent and telegram.ok:
            ready = (gps is None) or bool(gps.updated)
            if ready or (now - hello_t0) >= HELLO_MAX_WAIT:
                hello_sent = True
                if (DEVICE_NAME_FROM_GPS and gps is not None
                        and gps.lok_nomer and not DEVICE_NAME_FIXED):
                    DEVICE_NAME = f"Lokomotiv-{gps.lok_nomer}"
                telegram.send("\U0001F7E2 [%s] ARGUS AI ulandi\nVaqt: %s\n%s"
                              % (DEVICE_NAME,
                                 time.strftime('%Y-%m-%d %H:%M:%S'),
                                 _ident()))
        # ── Deploy xabari (bir marta): deploy skripti deploy_note.txt yozadi,
        # dastur qayta ishga tushgach uni admin + guruhga yuborib, o'chiradi.
        if hello_sent and not deploy_note_done:
            deploy_note_done = True
            try:
                if DEPLOY_NOTE_FILE and os.path.exists(DEPLOY_NOTE_FILE):
                    with open(DEPLOY_NOTE_FILE, encoding="utf-8") as fh:
                        note = fh.read().strip()
                    os.remove(DEPLOY_NOTE_FILE)
                    if note:
                        telegram.send("\U0001F6E0 [%s] YANGILANDI (deploy)\nVaqt: %s\n%s"
                                      % (DEVICE_NAME,
                                         time.strftime('%Y-%m-%d %H:%M:%S'), note))
                        print("Deploy xabari navbatga qo'yildi")
            except Exception as e:
                print("Deploy xabari yuborilmadi:", repr(e))

        # ── Eski yozuvlarni tozalash ──
        if now - last_clean >= RECORD_CLEAN_EVERY:
            last_clean = now
            try:
                # Navbatda turgan fayllar himoyalanadi: ular hali
                # yuborilmagan, o'chirilsa dalil butunlay yo'qoladi.
                keep = set()
                for it in list(telegram.outbox):
                    if it.get("path"):
                        keep.add(os.path.normcase(os.path.abspath(it["path"])))
                if web.ok and web.outbox is not None:
                    for it in list(web.outbox.q):
                        for k in ("photo", "video"):
                            if it.get(k):
                                keep.add(os.path.normcase(os.path.abspath(it[k])))
                # Klipi hali yopilmagan hodisalar ham himoyalanadi
                for pth in list(clip_uids):
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

        # Davriy FPS yozuvi — sekinlashuvni sezish uchun
        if fps:
            fps_hist.append(fps)
        if now - last_fps_log >= FPS_LOG_EVERY:
            last_fps_log = now
            if fps_hist:
                v = sorted(fps_hist)
                print("FPS: o'rtacha %.1f  |  eng past %.1f  |  eng yuqori %.1f  (%.0f s)"
                      % (sum(fps_hist)/len(fps_hist), v[0], v[-1], FPS_LOG_EVERY))
                fps_hist.clear()
                if facerec is not None:
                    n_seen = facerec.n_full + sum(facerec.n_ok.values())
                    print("YUZ-STAT (%.0f s): %s | odam=%s | to'siq=%s | yorug'lik=%.0f"
                          % (FPS_LOG_EVERY, facerec.stats(reset=True),
                             "bor" if person_present else "yo'q",
                             "ha" if blocked else "yo'q",
                             (mean_b if ENABLE_TAMPER else -1.0)))
                    # Butun daqiqa yuz topilmagan va poyezd harakatda -> nima
                    # ko'rinayotganini bilish uchun toza kadr saqlanadi.
                    if (n_seen == 0 and (gps is None or gps.is_moving())
                            and now - probe_last >= 600.0):
                        probe_last = now
                        try:
                            pp = os.path.join(RECORD_DIR, "probe_%s.jpg"
                                              % time.strftime('%Y%m%d_%H%M%S'))
                            cv2.imwrite(pp, frame)
                            print("YUZ-PROBE saqlandi:", os.path.basename(pp))
                        except Exception as e:
                            print("YUZ-PROBE saqlanmadi:", repr(e))

        # Soatlik kayfiyat hisoboti
        if now - last_report >= REPORT_INTERVAL:
            last_report = now
            telegram.send(build_report(mood_hist, incident_hist))     # odamga — matn
            web.send_report("hourly",                                 # saytga — maydonlar
                            report_data(mood_hist, incident_hist, REPORT_INTERVAL),
                            extra=gps.identity() if gps else None)

        # Kunlik yakuniy hisobot — belgilangan vaqtdan keyin, kuniga 1 marta
        if DAILY_REPORT:
            today = time.strftime('%Y-%m-%d')
            if time.strftime('%H:%M') >= DAILY_REPORT_AT and day.sent_for != today:
                day.sent_for = today
                telegram.send(build_daily_report(day))             # odamga — matn
                web.send_report("daily", day_report_data(day),     # saytga — maydonlar
                                extra=gps.identity() if gps else None)
                day.save(force=True)

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
        eye_txt = ({"open":"OCHIQ","half":"YARIM","closed":"YUMUQ"}.get(eye_state, "-")
                   if face_found else "-")
        belt_txt = "TAQILGAN" if belt is True else ("YO'Q" if belt is False else "-")
        rows = []
        if ENABLE_DROWSY:
            # Bosh egilgan bo'lsa o'lchov ishonchsizligini OCHIQ ko'rsatamiz
            txt = (eye_txt if eye_reliable
                   else ("BEKILGAN" if eye_shaky else "BOSH PAST"))
            rows.append(("Ko'z", txt, not (drowsy_al or micro_al), not face_found))
        if ENABLE_PERCLOS:
            # Oyna to'lmaguncha "..." — natija hali ishonchsiz
            rd = perclos.ready()
            p_txt = (f"{perclos_val*100:.0f}%" if rd else "yig'ilmoqda")
            rows.append(("PERCLOS", p_txt, not (perclos_warn or perclos_crit), not rd))
        if ENABLE_BLINK:
            b_txt = (f"{blink_ms:.0f} ms" if blink_ms is not None else "yig'ilmoqda")
            rows.append(("Pirpirash", b_txt, not blink_slow, blink_ms is None))
        if gps is not None:
            # Tezlik + ma'lumot eskirganini ham ko'rsatamiz
            if gps.speed is None:
                s_txt, s_ok = ("GPS yo'q", False)
            elif not gps.fix_fresh():
                # O'lchov eskirgan — tezlikka ishonib bo'lmaydi, shuning
                # uchun "harakatda" deb hisoblanadi. Buni ochiq yozamiz,
                # aks holda "0 km/s harakatda" ziddiyatli ko'rinadi.
                age = gps.fix_age
                qachon = ((f"{age/60:.0f} daq" if age < 5400 else f"{age/3600:.1f} soat")
                          if age else "?")
                s_txt = f"noma'lum ({qachon} oldin {float(gps.speed):.0f} km/s)"
                s_ok = False
            else:
                mov = gps.is_moving()
                s_txt = f"{float(gps.speed):.0f} km/s" + (" harakatda" if mov else " to'xtagan")
                s_ok = True
            rows.append(("Tezlik", s_txt, s_ok))
        if ENABLE_YAWN:
            rows.append(("Og'iz", "ESNASH" if yawn_al else ("OCHIQ" if yawn else "YOPIQ"),
                         not yawn_al))
        if ENABLE_DISTRACT:
            rows.append(("Qarash", "CHETGA" if looking_away else ("OLD" if face_found else "-"),
                         not distract_al, not face_found))
        # Yuz yo'q, lekin signal chiqmagan bo'lsa (poyezd to'xtagan yoki
        # vaqt hali to'lmagan) — kulrang. Qizil faqat haqiqiy buzilishda.
        _fa = ("yuz" in active) or ("yoq" in active)
        rows.append(("Yuz", "BOR" if face_found else "YO'Q",
                     face_found or not _fa, not face_found and not _fa))
        if ENABLE_MOOD:
            rows.append(("Kayfiyat", cur_mood.upper() if cur_mood else "-", True))
        if ENABLE_PHONE:
            if not phone_al:
                rows.append(("Telefon", "-", True))
            elif "telefon" not in active:
                # Poyezd to'xtagan — GPS filtri buni buzilish deb hisoblamaydi.
                # Ekranda ham qizil ko'rsatmaymiz, aks holda panel tizim
                # aslida qilmayotgan narsani da'vo qilgan bo'lardi.
                rows.append(("Telefon", "aniqlandi (to'xtagan)", True))
            else:
                # Ruxsat etilgan vaqt ichida — hisoblagich ko'rsatiladi,
                # lekin bu hali buzilish emas (yashil).
                lim = GRACE_SEC.get("telefon")
                el = grace.elapsed("telefon", now)
                if lim and el is not None and el < lim:
                    rows.append(("Telefon", f"{human_dur(lim - el)} qoldi", True))
                else:
                    rows.append(("Telefon", "ANIQLANDI", False))
        if ENABLE_SMOKING:
            rows.append(("Sigaret", "ANIQLANDI" if smoke_al else "-", not smoke_al))
        if ENABLE_SEATBELT:
            rows.append(("Kamar", belt_txt, not belt_al))
        if ENABLE_TAMPER:
            rows.append(("Kamera", "TO'SILGAN" if tamper_al else "OCHIQ", not tamper_al))

        # Kadr bezaklari — burchak ramkalari va o'lchov chiziqchalari
        frame_decor(frame)
        # Aniqlangan yuz atrofida vizir (qayerga qarayotgani ko'rinsin)
        if face_found and facerec is not None and facerec.box:
            face_reticle(frame, facerec.box, now)
        # Panel — o'lchami mazmunga qarab hisoblanadi
        ph = 33*len(rows) + 72
        info_panel(frame, 16, H - ph - 16, "ARGUS AI", DEVICE_NAME, rows,
                   stamp=(time.strftime('%Y-%m-%d'), time.strftime('%H:%M:%S')))

        # ── Xavf banneri ──
        if active:
            msg = {"uyqu":"UYQU! Uyg'oning", "mikrouyqu":"MIKROUYQU aniqlandi",
                   "uyquchan":"Uyquchanlik belgilari", "uyquchan_kr":"KRITIK uyquchanlik",
                   "pirpirash":"Sekin pirpirash", "sigaret":"SIGARET aniqlandi",
                   "telefon":"TELEFON aniqlandi", "esnash":"CHARCHOQ / esnash",
                   "chalgish":"CHALG'ISH! Old tomonga qarang",
                   "kamar":"Xavfsizlik KAMARI yo'q", "kamera":"KAMERA TO'SILGAN!",
                   "yuz":"YUZ KO'RINMAYAPTI!", "yoq":"HAYDOVCHI O'RNIDA YO'Q"}
            crit = bool({"uyqu", "mikrouyqu", "uyquchan_kr", "kamera"} & set(active))
            banner_txt = "   \u2022   ".join(msg.get(a, a.upper()) for a in active)
            banner_crit = crit
            alert_banner(frame, 30, 26, banner_txt, now, crit=crit)

        # ── Rasm / video yozib olish ──
        if (RECORD_ON_EVENT and rep_active) or manual_rec:
            recorder.trigger(W, H, now, fps)    # hodisa yoki qo'lда → yozuvni ushlab tur
        # Yuqori o'ng burchak: yozuv holati va FPS
        chips(frame, W, fps, recorder.is_recording(), now)
        recorder.step(frame, now)               # joriy kadrni yoz (kerak bo'lsa yop)
        recorder.push(frame, now)               # pre-roll bufer (keyingi klip uchun)
        if SNAPSHOT_ON_EVENT and held_active and not prev_active:
            # UID yuqorida, xabar yuborilishidan oldin berilgan - rasm,
            # video va matn shu bitta ID bilan ketadi.
            # ── Dalil rasmi ──
            # Kadr hodisaning O'RTASIDAN olinadi (signal kechikib chiqadi),
            # ustiga esa HOZIRGI holat chiziladi. Ikkalasi ham kerak: eski
            # kadrdagi eski HUD "hammasi joyida" deb ko'rsatib qo'yardi.
            ev = None
            if snap_buf:
                bt, bf = min(snap_buf, key=lambda it: abs(it[0] - (now - SNAPSHOT_BACK_SEC)))
                if abs(bt - (now - SNAPSHOT_BACK_SEC)) <= 0.5:
                    ev = bf.copy()
            if ev is None:
                ev = frame                      # bufer bo'sh — joriy kadr
            else:
                frame_decor(ev)
                if face_found and facerec is not None and facerec.box:
                    face_reticle(ev, facerec.box, now)
                info_panel(ev, 16, H - ph - 16, "ARGUS AI", DEVICE_NAME, rows,
                           stamp=(time.strftime('%Y-%m-%d'), time.strftime('%H:%M:%S')))
                chips(ev, W, fps, True, now)
                if banner_txt:
                    alert_banner(ev, 30, 26, banner_txt, now, crit=banner_crit)
            snap = recorder.snapshot(ev)
            capt = ", ".join(TG_MSG.get(a, a) for a in rep_active)
            if telegram.ok:                     # rasmni ham Telegram'ga
                telegram.send_photo(snap, f"⚠️ [{DEVICE_NAME}] {capt}\n"
                                          f"Vaqt: {time.strftime('%Y-%m-%d %H:%M:%S')}"
                                          + (f"\n{gps.text(short=True)}" if gps else "")
                                          + f"\nID: {cur_uid}",
                                    admin_only=stopped_route)
            # Saytga — rasm biriktirilgan holda (to'xtaganda yuborilmaydi)
            if not stopped_route:
                web.send_incident(",".join(sorted(rep_active)), capt, photo=snap, uid=cur_uid,
                                  detail=cur_detail or None,
                                  extra=gps.info() if gps else None)
            # Klip keyinroq yopiladi — uning yo'lini UID ga bog'lab qo'yamiz.
            # Fayl shu kadrda hali ochilmagan bo'lishi mumkin, u holda UID
            # navbatda turadi va fayl ochilishi bilan bog'lanadi. Aks holda
            # video YANGI uid bilan ketib, saytda alohida hodisa bo'lib qolardi.
            if recorder.path:
                clip_uids[recorder.path] = cur_uid
                clip_det[recorder.path] = cur_detail
            else:
                pending_uid = cur_uid
                pending_det = cur_detail
        prev_active = bool(held_active)

        # Kutayotgan UID bor va klip fayli endi ochildi — bog'laymiz
        if pending_uid and recorder.path and recorder.path not in clip_uids:
            clip_uids[recorder.path] = pending_uid
            clip_det[recorder.path] = pending_det
            pending_uid = None

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
                telegram.send(build_report(mood_hist, incident_hist))
            if k in (ord('q'), 27) or cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                stop_event.set()

    if telegram.ok:
        try:
            telegram.broadcast_sync(f"\U0001F534 [{DEVICE_NAME}] ARGUS AI to'xtatildi.")
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
    """Har qanday kutilmagan xatoда dastur QULAB TUSHMAYDI — biroz kutib qayta
    ishga tushadi (mini PC'да avtonom ishlashi uchun)."""
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
