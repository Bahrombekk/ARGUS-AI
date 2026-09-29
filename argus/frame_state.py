# -*- coding: utf-8 -*-
"""Bir kadr bo'yicha BARCHA aniqlash qarorlari — loop.py dan ajratilgan.

FrameAnalyzer.analyze(frame, res, now) -> FrameResult
    res — SafeDrive pipeline'ning process_frame() natijasi (yuz/ko'z/bosh).
    Bu yerda: yuz qayta qidiruvi (ROI), EAR silliqlash + moslashuvchan ostona,
    eyeBlink tasdiqi, chalg'ish bazasi, tamper, uyqu/mikrouyqu/PERCLOS/
    pirpirash, odam bor/yo'q, telefon/sigaret/kamar oynalari, `active`
    ro'yxati (odam-darvoza va qayta tasdiqlash bilan).

FrameAnalyzer.describe(tag, now, fr) -> str
    Xabar uchun o'lchangan qiymat matni ("Ko'z yumuq: 2.1 s (eyeBlink 0.78)").

Mantiq loop.py dagi bilan AYNAN bir xil (2026-09-28 refaktor); oflayn test:
tests/test_frame_state.py — eski kod nusxasi bilan kadrma-kadr solishtiradi.
"""
import collections

import cv2

from argus.settings import *   # noqa: F401,F403
from argus.detect.windows import PresenceWindow, Sustain
from argus.detect.drowsy import Perclos, BlinkTracker, EarBaseline
from argus.detect.eyes import BlinkConfirm
from argus.detect.reverify import Confirm, Grace
from argus.detect.tamper import TamperJudge
from argus.utils import human_dur


class FrameResult:
    """Bir kadr natijasi — oddiy maydonlar to'plami."""
    __slots__ = ("res", "face_found", "eye_state", "eye_closed", "eye_reliable",
                 "eye_shaky", "blink_sure", "blink_bs", "cues", "yawn", "phone",
                 "smoke", "belt", "head_tilt", "head_nod", "fps", "looking_away",
                 "blocked", "mean_b", "detail", "drowsy_al", "micro_al", "yawn_al",
                 "perclos_val", "perclos_warn", "perclos_crit", "blink_ms",
                 "blink_slow", "distract_al", "tamper_al", "person_present",
                 "noface_al", "absent_al", "phone_al", "smoke_al", "belt_al",
                 "active", "zoom_ear", "zoom_bs", "zoom_veto", "standing", "stand_al")

    def __init__(self):
        for k in self.__slots__:
            setattr(self, k, None)


class FrameAnalyzer:
    def __init__(self, pipe, blend, facerec, persondet, phonedet):
        self.pipe = pipe
        self.blend = blend          # BlendTap yoki None
        self.facerec = facerec      # FaceRecover yoki None
        self.persondet = persondet
        self.phonedet = phonedet

        self.phone_pw = PresenceWindow(PHONE_WINDOW, PHONE_RATIO, PHONE_MIN)
        self.smoke_pw = PresenceWindow(SMOKE_WINDOW, SMOKE_RATIO, SMOKE_MIN)
        self.belt_pw = PresenceWindow(BELT_WINDOW, BELT_RATIO, BELT_MIN)
        self.eye_sus = Sustain(EYE_CLOSED_SEC)
        self.yawn_sus = Sustain(YAWN_SEC)
        self.distract_sus = Sustain(DISTRACT_SEC)
        self.tamper_sus = Sustain(TAMPER_SEC)
        self.tamper = TamperJudge(TAMPER_DETAIL_VAR, TAMPER_DARK_MEAN, TAMPER_DROP,
                                  TAMPER_DROP_MIN, TAMPER_DROP_FRAC, TAMPER_DETAIL_REF,
                                  TAMPER_EMA_ALPHA)
        self.noface_sus = Sustain(NOFACE_SEC)
        self.stand_sus = Sustain(STAND_SEC)     # tik turgan: uzoqroq ostona
        # Yangi buzilishni e'lon qilishdan oldin qayta tasdiqlash
        self.confirm = Confirm(CONFIRM_SEC, CONFIRM_TAGS) if CONFIRM_SEC > 0 else None
        # Ruxsat etilgan vaqt (telefon 3 daqiqa) — ovoz ishlaydi, xabar kutadi
        self.grace = Grace(GRACE_SEC, GRACE_WINDOW, GRACE_BRIDGE)
        self.absent_sus = Sustain(ABSENT_SEC)
        self.micro_sus = Sustain(MICROSLEEP_SEC)
        self.perclos = Perclos(PERCLOS_WINDOW, PERCLOS_MIN_SAMPLES)
        self.blinks = BlinkTracker(BLINK_WINDOW, BLINK_MIN_SAMPLES)
        self.pc_warn_sus = Sustain(PERCLOS_HOLD)      # qisqa sakrashga qarshi
        self.pc_crit_sus = Sustain(PERCLOS_HOLD)
        self.last_face_t = None                       # yuz oxirgi marta ko'ringan vaqt
        self.ear_raw = collections.deque(maxlen=max(4, EYE_VOLATILE_WIN))
        self.blink_cf = BlinkConfirm(EYE_BLINK_BS_MIN, EYE_SMOOTH_N)   # eyeBlink tasdiqi
        self.ear_hist = collections.deque(maxlen=max(1, EYE_SMOOTH_N))
        self.ear_base = (EarBaseline(EAR_BASE_WINDOW, EAR_BASE_PCT, EAR_BASE_MIN_SAMPLES,
                                     EAR_BASE_FLOOR, EAR_BASE_CAP,
                                     EAR_OPEN_RATIO, EAR_HALF_RATIO)
                         if EAR_ADAPTIVE else None)
        self.tilt_base = self.nod_base = 0.0          # baza to'lmaguncha ishlatilmaydi
        self._closed_since = None                     # ko'z yumuq nomzodi boshlangan vaqt (zoom uchun)
        self._zoom_hist = collections.deque(maxlen=3) # oxirgi zoom qarorlari (True = yumuqni tasdiqladi)
        self.n_zoom = 0; self.n_zoom_veto = 0         # diagnostika
        self.tilt_hist = collections.deque(maxlen=300)
        self.nod_hist = collections.deque(maxlen=300)
        self.last = None                              # oxirgi FrameResult

    # ------------------------------------------------------------------
    def analyze(self, frame, res, now):
        fr = FrameResult()
        fr.res = res
        eye_state = res.get("eye_state", "unknown")
        face_found = bool(res.get("face_found"))
        t_open, t_half = EAR_OPEN, EAR_HALF
        # Yuz topilmadi deyilsa — DARHOL ishonmaymiz. Oxirgi ma'lum joy
        # atrofidan kesib qayta qidiramiz: qo'l boshdan yuqori ko'tarilganda
        # detektor butun kadrda yuzni yo'qotadi, parchada esa topadi.
        if self.facerec is not None:
            if face_found:
                self.facerec.note(res.get("landmarks"),
                                  frame.shape[1], frame.shape[0], now)
            else:
                again = self.facerec.retry(frame, now)
                if again:
                    res.update(again)
                    face_found = True
                    eye_state = res.get("eye_state", "unknown")
        # blink/down/cut — qayta qidiruvdan KEYIN (ROI natijasi ham shu yerda)
        cues = self.blend.cues() if self.blend is not None else {}

        # EAR ni silliqlaymiz va ko'z holatini QAYTA hisoblaymiz. Bitta
        # kadrlik chetlanish (landmark chayqalishi) shu yerda to'xtaydi.
        if not face_found:
            self.ear_hist.clear(); self.ear_raw.clear()
            # Baza qisqa uzilishda SAQLANADI — pastga qarab turgan haydovchi
            # bir kadrga yo'qolsa, moslashuv nolga tushib ketmasin.
            if (self.ear_base is not None and self.last_face_t is not None
                    and now - self.last_face_t > EAR_BASE_RESET_SEC):
                self.ear_base.reset()
        else:
            self.last_face_t = now
            self.ear_raw.append(float(res.get("ear") or 0.0))
            self.ear_hist.append(float(res.get("ear") or 0.0))
            v = sorted(self.ear_hist)
            med = v[len(v) // 2] if len(v) % 2 else (v[len(v)//2 - 1] + v[len(v)//2]) / 2.0
            # Ostonalar odamga moslashadi: ochiq ko'z darajasi har kimda
            # boshqacha, kameraning burchagi ham ta'sir qiladi.
            if self.ear_base is not None:
                self.ear_base.update(med, now)
                t_open, t_half = self.ear_base.thresholds(EAR_OPEN, EAR_HALF)
            eye_state = ("open" if med >= t_open
                         else "half" if med >= t_half else "closed")
        yawn = bool(res.get("yawn_detected"))
        phone = bool(res.get("phone_detected"))
        # Alohida model bor bo'lsa — safedrive.pt ning javobini ALMASHTIRAMIZ
        if self.phonedet is not None:
            phone = self.phonedet.update(frame, now)
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
            self.tilt_hist.append(head_tilt); self.nod_hist.append(head_nod)
            if len(self.tilt_hist) >= BASE_MIN:
                ts = sorted(self.tilt_hist); ns = sorted(self.nod_hist)
                self.tilt_base = ts[len(ts)//2]; self.nod_base = ns[len(ns)//2]
                looking_away = (head_tilt > self.tilt_base + TILT_MARGIN or
                                head_nod > self.nod_base + NOD_MARGIN)
                # Bosh juda pastga egilgan -> EAR yolg'on "yumuq" beradi
                eye_reliable = (head_nod <= self.nod_base + EYE_NOD_LIMIT)
        # EAR kadrdan kadrga sakrayotgan bo'lsa — ko'z nuqtalari yuzda emas
        # (qo'l, telefon yoki boshqa narsa bekitgan). Bunday o'lchovga
        # uyqu qarori qurib bo'lmaydi.
        eye_shaky = False
        if len(self.ear_raw) >= 4:
            er = self.ear_raw
            d = sorted(abs(er[k] - er[k-1]) for k in range(1, len(er)))
            eye_shaky = d[len(d)//2] > EYE_VOLATILE_MAX
            if eye_shaky:
                eye_reliable = False
        # Yuz kadr chetida kesilgan — landmark'lar taxminiy (00:33 klipi)
        if EYE_FACE_CUT_UNRELIABLE and cues.get("cut"):
            eye_reliable = False
        # eyeBlink tasdiqi: pastga qarashda EAR "yumuq" beradi, blendshape
        # esa 0.36-0.55 da qoladi; haqiqiy yumuqda 0.77. Ma'lumot bo'lmasa True.
        blink_sure, blink_bs = self.blink_cf.update(cues.get("blink") if face_found else None)

        # Kamera to'silishi (tamper) — tafsilot (Laplacian) + KESKIN qorong'ilashish.
        # Mutlaq qorong'ilik tamper belgisi EMAS: tunda yoritilmagan kabina 15 dan
        # past tushadi, lekin tuzilish saqlanadi (o'lchov 2026-09-25 18:40: yorug'lik
        # 13.7, tafsilot 42). Yopilgan lens tafsilotni yo'qotadi VA yorug'likni bir
        # lahzada tushiradi. Shom asta keladi -> EMA'dan drop bo'lmaydi.
        blocked = False
        mean_b, detail = -1.0, 0.0
        if ENABLE_TAMPER:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            mean_b = float(gray.mean())
            # Tafsilot YARIM o'lchamda, float32: 9.2 ms -> ~1.5 ms (lok o'lchovi
            # 2026-09-29). Qiymat to'liq o'lchamdagidan ~1.1-1.4x yuqori chiqadi —
            # bu to'silishga sezgirlikni biroz PASAYTIRADI (yopiq lens ~0-5,
            # ostona 12-20 — zaxira katta), ochiq kamerada yolg'onni kamaytiradi.
            small = cv2.resize(gray, (gray.shape[1] // 2, gray.shape[0] // 2),
                               interpolation=cv2.INTER_AREA)
            detail = float(cv2.Laplacian(small, cv2.CV_32F).var())
            # Yorug'likka moslashuvchan qaror — argus/detect/tamper.py
            blocked, _sd, _ld = self.tamper.update(mean_b, detail)

        # Debounce / sustain (SafeDrive aniqlashi ustida)
        # Bosh pastga egilgan bo'lsa ko'z o'lchovi ishonchsiz — uyqu o'lchanmaydi
        eye_ok = eye_closed and eye_reliable and blink_sure
        # ZOOM — ikkinchi fikr: nomzod EYE_ZOOM_AFTER s davom etgach yuz atrofi
        # kesib kattalashtiriladi va o'sha kesimda EAR + eyeBlink qayta o'lchanadi.
        zoom_ear = zoom_bs = None; zoom_veto = False
        if eye_ok:
            if self._closed_since is None:
                self._closed_since = now
            if EYE_ZOOM and now - self._closed_since >= EYE_ZOOM_AFTER:
                zoom_ear, zoom_bs = self._zoom_eyes(frame, res)
                if zoom_ear is not None:
                    self.n_zoom += 1
                    z_closed = zoom_ear < t_half
                    z_sure = (zoom_bs is None) or (zoom_bs >= EYE_BLINK_BS_MIN)
                    self._zoom_hist.append(bool(z_closed and z_sure))
                    # Bitta kadrlik kelishmovchilik uzluksiz hisoblagichni
                    # buzmasin (haqiqiy yumuqda 10-47 zoomdan 1-2 tasi 0.6 dan
                    # pastga tushdi): oxirgi 3 zoomdan kamida 2 tasi rad etsa — veto.
                    if len(self._zoom_hist) >= 2 and sum(1 for v in self._zoom_hist if not v) >= 2:
                        zoom_veto = True
                        self.n_zoom_veto += 1
                        eye_ok = False
        else:
            self._closed_since = None
            self._zoom_hist.clear()
        drowsy_al = self.eye_sus.update(eye_ok, now)
        micro_al = self.micro_sus.update(eye_ok, now)
        yawn_al = self.yawn_sus.update(yawn, now)

        # PERCLOS va pirpirash — faqat yuz ko'rinib turganda o'lchanadi,
        # aks holda "ko'z ochiq" deb noto'g'ri hisoblanib ketardi.
        perclos_val, blink_ms = 0.0, None
        perclos_warn = perclos_crit = blink_slow = False
        if face_found and eye_reliable:
            # Tasdiqlanmagan "yumuq" (pastga qarash) PERCLOS'da yarim hisoblanadi
            perclos_val = self.perclos.update(
                eye_state if (eye_state != "closed" or blink_sure) else "half", now)
            self.blinks.update(eye_closed and blink_sure, now)
        else:
            perclos_val = self.perclos.decay(now)       # oyna baribir tozalanadi
        blink_ms = self.blinks.mean_ms()
        if ENABLE_PERCLOS and self.perclos.ready():
            # Qisqa sakrash signal bermasin — qiymat PERCLOS_HOLD soniya
            # UZLUKSIZ ostonadan yuqori turishi kerak.
            perclos_crit = self.pc_crit_sus.update(perclos_val > PERCLOS_CRIT, now)
            perclos_warn = (not perclos_crit) and \
                           self.pc_warn_sus.update(perclos_val > PERCLOS_WARN, now)
        if ENABLE_BLINK and blink_ms is not None:
            blink_slow = blink_ms > BLINK_SLOW_MS
        distract_al = self.distract_sus.update(looking_away, now)
        tamper_al = self.tamper_sus.update(blocked, now)

        # Kamera soz, lekin yuz yo'q — odam bormi yoki chiqib ketganmi?
        # persondet FAQAT shu holatda ishlaydi (yuz bor bo'lsa chaqirilmaydi).
        standing = False
        if face_found:
            person_present = True
            if self.persondet is not None:
                self.persondet.present = True        # holat yangilanib turadi
                self.persondet.standing = False
        elif self.persondet is not None and not blocked:
            person_present = self.persondet.update(frame, now)
            # Odam bor, boshi kadr tepasidan chiqqan -> o'rnidan turgan (qo'l uzatish,
            # tugma) — bu yuzni to'sish emas; alohida, uzoq ostonali tur.
            standing = bool(person_present and getattr(self.persondet, "standing", False))
        else:
            person_present = True               # model yo'q → eski xatti-harakat

        gap = (not face_found) and (not blocked)
        noface_al = self.noface_sus.update(gap and person_present and not standing, now)   # to'sgan
        stand_al = self.stand_sus.update(gap and person_present and standing, now)         # tik turgan
        absent_al = self.absent_sus.update(gap and not person_present, now)  # chiqib ketgan
        phone_al = self.phone_pw.update(phone, now)
        smoke_al = self.smoke_pw.update(smoke, now)
        belt_al = self.belt_pw.update(belt is False, now)

        # Faol xavflar → ovoz NAVBAT bilan (faqat YOQILGAN funksiyalar).
        # Kamera to'silgan bo'lsa — boshqa aniqlash ishonchsiz, faqat "kamera".
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
            if ENABLE_NOFACE   and stand_al:    active.append("turgan")
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
        if self.confirm is not None:
            active = self.confirm.update(active, now)

        fr.face_found = face_found; fr.eye_state = eye_state; fr.eye_closed = eye_closed
        fr.eye_reliable = eye_reliable; fr.eye_shaky = eye_shaky
        fr.blink_sure = blink_sure; fr.blink_bs = blink_bs; fr.cues = cues
        fr.yawn = yawn; fr.phone = phone; fr.smoke = smoke; fr.belt = belt
        fr.head_tilt = head_tilt; fr.head_nod = head_nod; fr.fps = fps
        fr.looking_away = looking_away; fr.blocked = blocked
        fr.mean_b = mean_b; fr.detail = detail
        fr.drowsy_al = drowsy_al; fr.micro_al = micro_al; fr.yawn_al = yawn_al
        fr.perclos_val = perclos_val; fr.perclos_warn = perclos_warn
        fr.perclos_crit = perclos_crit; fr.blink_ms = blink_ms; fr.blink_slow = blink_slow
        fr.distract_al = distract_al; fr.tamper_al = tamper_al
        fr.person_present = person_present; fr.noface_al = noface_al
        fr.absent_al = absent_al; fr.phone_al = phone_al; fr.smoke_al = smoke_al
        fr.belt_al = belt_al; fr.active = active
        fr.zoom_ear = zoom_ear; fr.zoom_bs = zoom_bs; fr.zoom_veto = zoom_veto
        fr.standing = standing; fr.stand_al = stand_al
        self.last = fr
        return fr

    # ------------------------------------------------------------------
    def _zoom_eyes(self, frame, res):
        """Yuz atrofini kesib kattalashtirib landmarker'ni qayta ishga tushiradi.
        Qaytadi: (ear, eyeBlink) yoki (None, None) — yuz topilmasa/xato bo'lsa."""
        try:
            box = None
            if self.facerec is not None and self.facerec.box is not None:
                box = self.facerec.box
            else:
                lm = res.get("landmarks")
                if lm:
                    h0, w0 = frame.shape[:2]
                    xs = [p.x * w0 for p in lm]; ys = [p.y * h0 for p in lm]
                    box = (min(xs), min(ys), max(xs), max(ys))
            if box is None:
                return None, None
            h, w = frame.shape[:2]
            x1, y1, x2, y2 = box
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            bw, bh = (x2 - x1) * EYE_ZOOM_MARGIN, (y2 - y1) * EYE_ZOOM_MARGIN
            a = max(0, int(cx - bw / 2)); b_ = max(0, int(cy - bh / 2))
            c = min(w, int(cx + bw / 2)); d = min(h, int(cy + bh / 2))
            if c - a < 40 or d - b_ < 40:
                return None, None
            crop = frame[b_:d, a:c]
            if crop.shape[0] < EYE_ZOOM_MIN_PX:
                s = float(EYE_ZOOM_MIN_PX) / crop.shape[0]
                crop = cv2.resize(crop, None, fx=s, fy=s, interpolation=cv2.INTER_CUBIC)
            r = self.pipe._run_mediapipe(crop)
            if not r.get("face_found"):
                return None, None
            zb = None
            if self.blend is not None:
                zb = self.blend.cues().get("blink")
            return float(r.get("ear") or 0.0), zb
        except Exception:
            return None, None

    # ------------------------------------------------------------------
    def report_set(self, active, now):
        """XABAR uchun alohida ro'yxat: ruxsat etilgan vaqtdan oshganlar.
        Telefon 3 daqiqagacha bu ro'yxatga tushmaydi."""
        return self.grace.update(active, now)

    # ------------------------------------------------------------------
    def describe(self, tag, now, fr):
        """O'lchangan qiymat — quruq "buzilish" o'rniga nima asosda qaror
        qilinganini ko'rsatadi. Matn '\\n' bilan boshlanadi (yoki bo'sh)."""
        det = ""
        if tag in ("uyquchan", "uyquchan_kr"):
            det = f"\nPERCLOS: {fr.perclos_val*100:.0f}%  (ostona {PERCLOS_WARN*100:.0f}/{PERCLOS_CRIT*100:.0f}%)"
        elif tag == "pirpirash" and fr.blink_ms:
            det = f"\nPirpirash: {fr.blink_ms:.0f} ms  (ostona {BLINK_SLOW_MS:.0f} ms)"
        elif tag in ("uyqu", "mikrouyqu") and self.eye_sus.since:
            det = f"\nKo'z yumuq: {now - self.eye_sus.since:.1f} s"
            if fr.blink_bs is not None:
                det += f"  (eyeBlink {fr.blink_bs:.2f}"
                if fr.zoom_bs is not None:
                    det += f", zoom {fr.zoom_bs:.2f}"
                det += ")"
        elif tag == "telefon" and self.phonedet is not None:
            el = self.grace.elapsed("telefon", now)
            det = f"\nIshonch: {self.phonedet.score:.2f}"
            if el:
                det += (f"  |  {human_dur(el)} davom etdi"
                        f"  (ruxsat {human_dur(GRACE_SEC['telefon'])})")
        elif tag == "kamera":
            det = f"\nYorug'lik: {fr.mean_b:.0f}  tafsilot: {fr.detail:.0f}"
        elif tag == "yuz":
            # Yuz qancha vaqt ko'rinmayapti va odam kadrdami
            d0 = self.noface_sus.since
            det = ("\nYuz ko'rinmagan: %.1f s  (ostona %.0f s)"
                   % ((now - d0) if d0 else 0.0, NOFACE_SEC))
            det += ("  |  odam kadrda: bor" if fr.person_present
                    else "  |  odam kadrda: yo'q")
            if self.facerec is not None:
                det += "  |  " + self.facerec.stats()
        elif tag == "turgan":
            d0 = self.stand_sus.since
            det = ("\nTik turibdi (bosh kadrdan yuqorida): %.0f s  (ostona %.0f s)"
                   % ((now - d0) if d0 else 0.0, STAND_SEC))
        elif tag == "yoq":
            d0 = self.absent_sus.since
            det = ("\nO'rinda yo'q: %.0f s  (ostona %.0f s)"
                   % ((now - d0) if d0 else 0.0, ABSENT_SEC))
        elif tag == "chalgish":
            # Bazadan qancha chetlashgani - qaror shu asosda chiqadi
            det = ("\nBurilish: %.0f° (baza %.0f°, ostona +%.0f°)"
                   % (fr.head_tilt, self.tilt_base, TILT_MARGIN))
            det += ("  |  egilish: %.0f° (baza %.0f°, ostona +%.0f°)"
                    % (fr.head_nod, self.nod_base, NOD_MARGIN))
        elif tag == "kamar":
            det = "\nKamar: taqilmagan"
        elif tag == "sigaret":
            cf = float(fr.res.get("smoking_confidence") or 0.0)
            det = "\nIshonch: %.2f" % cf if cf else ""
        elif tag == "esnash":
            d0 = self.yawn_sus.since
            det = ("\nOg'iz ochiq: %.1f s  (ostona %.0f s)"
                   % ((now - d0) if d0 else 0.0, YAWN_SEC))
        return det
