# -*- coding: utf-8 -*-
"""Buzilishni E'LON QILISHDAN OLDIN qayta tekshirish.

Ikki xil qayta tekshiruv bor:

FaceRecover — MediaPipe yuzni topa olmaganda, oxirgi ma'lum joy atrofidan
    KESIB olib qayta urinadi. Sabab: haydovchi qo'lini boshi ustiga ko'tarib
    cho'zilganda detektor butun kadrda yuzni yo'qotadi, lekin yuz atrofidan
    kesib olingan parchada bemalol topadi. 2026-09-24 da olingan uchta
    muammoli kadrda tekshirildi: to'liq kadrda 0/3, kesilgan parchada 3/3.
    To'liq kadrni kattalashtirish ham, kontrastni oshirish ham yordam
    bermagan — demak sabab yorug'lik emas, atrofdagi qo'llar.

Confirm — yangi buzilish darhol e'lon qilinmaydi. U belgilangan qisqa vaqt
    davomida saqlanib turishi kerak. Bir kadrlik sakrash shu yerda to'xtaydi
    va Telegram'ga, saytga, ovozga chiqmaydi.
"""

import collections
import json
import os
import cv2


class FaceRecover:
    """Yuz yo'qolganda oxirgi ma'lum joy atrofidan qayta qidiradi."""

    # O'RINDIQ ROI (2026-09-26): tunda kabina qorong'i (yorug'lik 35-38),
    # to'liq 1280x720 kadrda detektor yuzni topmaydi — 3 ta tungi klipda
    # 3% kadr. O'rindiq atrofidan kesib olinganda 90-99% kadr (detektor
    # kichik kirish o'lchamiga siqqanda yuz piksellari ko'proq qoladi).
    # Eski usul faqat 30 s xotira bilan ishlardi: tunda yuz 30 s dan ko'p
    # yo'qolsa qayta qidiruv umuman to'xtardi. Endi:
    #   1) oxirgi ma'lum joy (xotira uzoq),
    #   2) o'rganilgan O'RINDIQ qutisi (topilgan yuzlarning sekin EMA'si,
    #      faylga saqlanadi — qayta ishga tushganda ham bor),
    #   3) hech narsa bo'lmasa kadr markazi.
    SEAT_ALPHA = 0.02             # sekin o'rganish (~50 kadr = 3 s @18 FPS)
    SEAT_SAVE_EVERY = 60.0        # faylga necha s da bir yoziladi (elektr tez-tez uziladi)
    # 2026-09-29: elektr har 30-60 daq uzilgani uchun o'rindiq 20 kadrdan keyin
    # saqlanib, chap yuqori burchakdagi noto'g'ri joy (102,78,302,285) keyingi
    # sessiyalarga o'tib ketdi. Endi: kamida SEAT_MIN_N namuna, joy kadr
    # markaziy qismida bo'lishi shart, uzoq vaqt boshqa joyda topilsa qayta o'rganiladi.
    SEAT_MIN_N = 400              # saqlash/yuklash uchun eng kam namuna (~25 s yuz)
    SEAT_FAR_N = 200              # shuncha ketma-ket "uzoq" topilish -> qayta o'rganish
    # Yuz shuncha s dan ko'p yo'qolgan bo'lsa qayta qidiruv HAR kadrda:
    # 0.15 s cheklovi tunda topishni 50% ga bog'lab qo'ygan edi (klip
    # o'lchovi). Qo'shimcha xarajat faqat yuz yo'q paytida (~10 ms/kadr).
    GAP_SEC = 1.0
    # QORONG'I kesim silliqlanadi (Gauss 7x7). Sabab (2026-09-26 19:35, jonli
    # YUZ-STAT): yozuvdan olingan kadrlarda ROI 100% topadi, jonli xom kadrda
    # esa 285 urinishdan 145 tasi topilmadi. Farq — tungi yuqori gain shovqini
    # (yozuv H.264 bilan silliqlangan). Stol o'lchovi: sigma 18 shovqinda xom
    # 11/29, Gauss 7x7 bilan 29/29; yorug' kadrda ta'sir yo'q (29/29).
    DARK_MEAN = 80.0
    BLUR_K = 7

    def __init__(self, pipe, margin=2.5, memory=30.0, every=0.15,
                 seat_file=None):
        self.pipe = pipe
        self.margin = margin      # yuz qutisidan necha barobar keng kesamiz
        self.memory = memory      # oxirgi joy shuncha s dan keyin eskiradi
        self.every = every        # qayta urinishlar orasidagi eng kam vaqt
        self.box = None           # (x1, y1, x2, y2) — to'liq kadr koordinatasi
        self.box_t = 0.0
        self.last_try = 0.0
        self.saved = 0            # nechta yolg'on "yuz yo'q" to'xtatildi
        self.seat = None          # o'rganilgan o'rindiq qutisi (to'liq kadr)
        self.seat_n = 0
        self.seat_file = seat_file
        self._seat_saved_t = 0.0
        self.seat_hits = 0        # o'rindiq ROI necha marta yordam berdi
        self.full_t = -1e9        # yuz TO'LIQ kadrda oxirgi marta ko'ringan vaqt
        self._far_n = 0           # o'rindiqdan uzoq topilishlar ketma-ketligi
        self._seat_checked = False
        # Diagnostika hisoblagichlari (jurnaldagi FPS satrida chiqadi)
        self.n_full = 0           # yuz to'liq kadrda topilgan kadrlar
        self.n_try = 0            # qayta qidiruv urinishlari (kadr)
        self.n_skip = 0           # cheklov tufayli o'tkazib yuborilgan
        self.n_ok = {"last": 0, "seat": 0, "wide": 0, "center": 0}
        self.n_fail = 0
        # Asosiy fayl, bo'lmasa/buzilgan bo'lsa zaxira (.bak) — elektr uzilishi
        # yozish paytiga to'g'ri kelsa fayl yo'qolib/NUL bo'lib qolgan (19:45).
        if seat_file:
            for cand in (seat_file, seat_file + ".bak"):
                if not os.path.exists(cand):
                    continue
                try:
                    with open(cand, encoding="utf-8") as fh:
                        d = json.load(fh)
                    s = d.get("seat")
                    if (s and len(s) == 4 and 40 <= s[2] - s[0] <= 600
                            and 40 <= s[3] - s[1] <= 600
                            and int(d.get("n", 0)) >= self.SEAT_MIN_N):
                        self.seat = tuple(float(v) for v in s)
                        self.seat_n = int(d.get("n", 0))
                        print("O'rindiq ROI yuklandi: %s (n=%d) <- %s"
                              % (tuple(int(v) for v in self.seat), self.seat_n,
                                 os.path.basename(cand)))
                        break
                    print("O'rindiq ROI rad etildi (shubhali):", os.path.basename(cand), s)
                except Exception as e:
                    print("O'rindiq ROI o'qilmadi:", os.path.basename(cand), repr(e))
            if self.seat is None:
                print("O'rindiq ROI yo'q — yangidan o'rganiladi")

    def stats(self, reset=False):
        s = ("yuz: to'liq %d | ROI urinish %d, o'tkazildi %d | topildi last %d seat %d wide %d center %d | topilmadi %d"
             % (self.n_full, self.n_try, self.n_skip, self.n_ok["last"],
                self.n_ok["seat"], self.n_ok["wide"], self.n_ok["center"], self.n_fail))
        if reset:
            self.n_full = self.n_try = self.n_skip = self.n_fail = 0
            self.n_ok = {k: 0 for k in self.n_ok}
        return s

    def _seat_plausible(self, box, w, h):
        """O'rindiq qutisi kadrning markaziy qismida bo'lishi kerak (kamera
        haydovchiga qaratilgan). Chetdagi 'yuz' — poster, aks yoki xato."""
        x1, y1, x2, y2 = box
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        return (0.2 * w <= cx <= 0.8 * w and 0.2 * h <= cy <= 0.9 * h
                and 40 <= x2 - x1 <= 600 and 40 <= y2 - y1 <= 600)

    def _learn_seat(self, box, now, w=None, h=None):
        if w and h and not self._seat_plausible(box, w, h):
            return                       # chetdagi topilish o'rindiqni buzmasin
        if self.seat is None:
            self.seat = tuple(box)
            self._far_n = 0
        else:
            # Uzoq vaqt boshqa joyda topilsa — haydovchi joyi o'zgargan yoki
            # eski qiymat noto'g'ri: qayta o'rganamiz
            sx = (self.seat[0] + self.seat[2]) / 2.0; sy = (self.seat[1] + self.seat[3]) / 2.0
            bx = (box[0] + box[2]) / 2.0; by = (box[1] + box[3]) / 2.0
            far = (abs(sx - bx) > 0.25 * (w or 1280)) or (abs(sy - by) > 0.25 * (h or 720))
            self._far_n = (self._far_n + 1) if far else 0
            if self._far_n >= self.SEAT_FAR_N:
                print("O'rindiq ROI qayta o'rganildi: %s -> %s"
                      % (tuple(int(v) for v in self.seat), tuple(int(v) for v in box)))
                self.seat = tuple(box); self.seat_n = 0; self._far_n = 0
            else:
                a = self.SEAT_ALPHA
                self.seat = tuple(s * (1 - a) + v * a for s, v in zip(self.seat, box))
        self.seat_n += 1
        if (self.seat_file and self.seat_n >= self.SEAT_MIN_N
                and now - self._seat_saved_t >= self.SEAT_SAVE_EVERY):
            self._seat_saved_t = now
            try:
                tmp = self.seat_file + ".tmp"
                with open(tmp, "w", encoding="utf-8") as fh:
                    json.dump({"seat": [round(v, 1) for v in self.seat],
                               "n": self.seat_n}, fh)
                    fh.flush()
                    os.fsync(fh.fileno())
                # Avvalgi yaxshi nusxa zaxiraga: ikkalasi bir vaqtda buzilmaydi
                if os.path.exists(self.seat_file):
                    try:
                        os.replace(self.seat_file, self.seat_file + ".bak")
                    except Exception:
                        pass
                os.replace(tmp, self.seat_file)
            except Exception as e:
                print("O'rindiq ROI saqlanmadi:", repr(e))

    def note(self, lm, w, h, now):
        """Yuz topilganda joyini eslab qolamiz."""
        if not lm:
            return
        xs = [p.x * w for p in lm]
        ys = [p.y * h for p in lm]
        self.box = (min(xs), min(ys), max(xs), max(ys))
        self.box_t = now
        self.full_t = now
        self.n_full += 1
        self._learn_seat(self.box, now, w, h)

    def _note_box(self, box, now):
        self.box = box
        self.box_t = now

    def retry(self, frame, now):
        """Yuz yo'qolgan kadrda ROI dan qayta qidiradi.

        Topilsa yuzga oid maydonlar dict qilib qaytariladi, aks holda None.
        Odam haqiqatan chiqib ketgan bo'lsa parchada ham yuz bo'lmaydi —
        shuning uchun bu usul haqiqiy "yuz yo'q" signalini to'smaydi."""
        # Bo'shliq TO'LIQ kadrdagi oxirgi ko'rinishdan o'lchanadi: ROI'da
        # topilgani bo'shliqni yopmaydi (aks holda har ikkinchi kadr o'tib
        # ketardi va tunda topish 50% da qolardi — klip o'lchovi).
        gap = now - self.full_t
        every = self.every if gap < self.GAP_SEC else 0.0
        if now - self.last_try < every:
            self.n_skip += 1
            return None                       # protsessorni ayaymiz
        self.last_try = now
        self.n_try += 1

        h, w = frame.shape[:2]
        if not self._seat_checked:
            self._seat_checked = True
            if self.seat is not None and not self._seat_plausible(self.seat, w, h):
                print("O'rindiq ROI rad etildi (kadr chetida): %s — yangidan o'rganiladi"
                      % (tuple(int(v) for v in self.seat),))
                self.seat = None; self.seat_n = 0
        # Nomzod qutilar: oxirgi joy -> o'rindiq -> keng o'rindiq -> markaz.
        # Har biri sinaladi (bir xil kesim ikki marta emas); xarajat faqat
        # yuz topilmagan kadrda (~7 ms har nomzod).
        cands = []
        if self.box is not None and now - self.box_t <= self.memory:
            cands.append(("last", self.box, 1.0))
        if self.seat is not None:
            cands.append(("seat", self.seat, 1.0))
            cands.append(("wide", self.seat, 1.7))
        cands.append(("center", (0.40 * w, 0.40 * h, 0.60 * w, 0.75 * h), 1.0))

        r = None; a = b = 0; crop = None; done_rects = set()
        for name, box, mult in cands:
            x1, y1, x2, y2 = box
            cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
            bw, bh = (x2 - x1) * self.margin * mult, (y2 - y1) * self.margin * mult
            a = max(0, int(cx - bw / 2.0))
            b = max(0, int(cy - bh / 2.0))
            c = min(w, int(cx + bw / 2.0))
            d = min(h, int(cy + bh / 2.0))
            if c - a < 40 or d - b < 40:
                continue
            key = (a // 16, b // 16, c // 16, d // 16)
            if key in done_rects:
                continue                      # deyarli bir xil kesim
            done_rects.add(key)
            crop = frame[b:d, a:c]
            try:
                probe = crop
                if self.BLUR_K and float(crop.mean()) < self.DARK_MEAN:
                    probe = cv2.GaussianBlur(crop, (self.BLUR_K, self.BLUR_K), 0)
                rr = self.pipe._run_mediapipe(probe)
            except Exception:
                continue
            if rr.get("face_found"):
                r = rr
                self.n_ok[name] = self.n_ok.get(name, 0) + 1
                if name == "seat":
                    self.seat_hits += 1
                break
        if r is None:
            self.n_fail += 1
            return None

        # Yangi joyni TO'LIQ kadr koordinatasiga qaytarib eslab qolamiz,
        # aks holda ROI bir joyda qotib qoladi va yuz undan chiqib ketadi.
        lm = r.get("landmarks")
        if lm:
            ch, cw = crop.shape[:2]
            xs = [a + p.x * cw for p in lm]
            ys = [b + p.y * ch for p in lm]
            self._note_box((min(xs), min(ys), max(xs), max(ys)), now)
            self._learn_seat(self.box, now, w, h)

        self.saved += 1
        return {"eye_state": r.get("eye_state", "unknown"),
                "ear": r.get("ear", 0.0),
                "mar": r.get("mar", 0.0),
                "head_tilt": r.get("head_tilt", 0.0),
                "head_nod": r.get("head_nod", 0.0),
                "face_found": True}


class Confirm:
    """Yangi buzilish tasdiqlanmaguncha e'lon qilinmaydi.

    Buzilish `delay` soniya davomida saqlanib tursa — tasdiqlangan hisoblanadi
    va shundan keyin uzilmagunicha qayta tasdiq talab qilinmaydi. Bu qo'shimcha
    kechikish bir martalik: uzoq davom etgan buzilishga ta'sir qilmaydi."""

    def __init__(self, delay, tags=None):
        self.delay = delay
        self.tags = tags            # None → hammasi; to'plam → faqat shular
        self.first = {}             # tur -> birinchi ko'rilgan vaqt
        self.ok = set()             # tasdiqlangan turlar
        self.blocked = 0            # nechta tasdiqlanmagan sakrash to'xtatildi

    def update(self, active, now):
        cur = set(active)
        for t in list(self.first):
            if t not in cur:
                self.first.pop(t, None)
        self.ok &= cur

        out = []
        for t in active:                      # tartib saqlanadi
            if self.tags is not None and t not in self.tags:
                out.append(t)                 # bu tur tasdiqdan ozod
                continue
            if t in self.ok:
                out.append(t)
                continue
            t0 = self.first.setdefault(t, now)
            if now - t0 >= self.delay:
                self.ok.add(t)
                out.append(t)
            else:
                self.blocked += 1
        return out


class Grace:
    """Ba'zi holatlar belgilangan vaqtgacha BUZILISH hisoblanmaydi.

    Telefon misolida: oynadagi JAMI vaqt 3 daqiqadan oshmasa ruxsat.
    Shu vaqt ichida ovozli ogohlantirish ishlaydi - haydovchi nazoratda
    ekanini biladi va o'zi to'xtatishi mumkin. Telegram'ga va saytga esa
    xabar ketmaydi.

    NEGA JAMI, uzluksiz emas: ilgari hisoblagich har uzilishda nolga
    tushardi. O'lchandi - 60 s telefon, 20 s tanaffus, 120 s telefon
    (jami 180 s) qilinganda tizim HECH QACHON xabar bermasdi. Ya'ni har
    2.5 daqiqada 20 soniya to'xtab tursa, telefonni cheksiz ishlatish
    mumkin edi.

    Endi oxirgi `window` soniyadagi jami vaqt sanaladi va u eskirgani
    sari o'z-o'zidan kamayib boradi.
    """

    def __init__(self, limits, window=None, bridge=0.0):
        self.limits = dict(limits or {})
        self.window = window          # None -> uzluksiz sanash (eski usul)
        self.bridge = bridge          # qisqa uzilish - foydalanish deb sanaladi
        self.since = {}               # tur -> uzluksiz boshlangan vaqt
        self.used = {}                # tur -> [[vaqt, soniya], ...]
        self._seen = {}               # tur -> oxirgi ANIQLANGAN vaqt

    def _acc(self, tag, now):
        """Oynadagi jami vaqtni yangilaydi va qaytaradi.

        Qisqa uzilish (`bridge` dan kam) FOYDALANISH deb sanaladi. Sabab:
        model telefonni bir necha soniyaga ko'rmay qolishi mumkin - qo'l
        pastga tushgan, burchak o'zgargan, yorug'lik boshqacha. Odam esa
        gaplashishda davom etadi. Busiz har aniqlash uzilishi haydovchiga
        bepul vaqt berib qo'yardi."""
        d = self.used.setdefault(tag, collections.deque())
        prev = self._seen.get(tag)
        self._seen[tag] = now
        if prev is not None:
            step = now - prev
            if step > max(self.bridge, 1.0):
                step = 0.0                   # haqiqiy tanaffus - sanalmaydi
            if step > 0:
                if d and now - d[-1][0] < 1.0:
                    d[-1][1] += step
                else:
                    d.append([now, step])
        while d and now - d[0][0] > self.window:
            d.popleft()
        return sum(x[1] for x in d)

    def _trim(self, tag, now):
        d = self.used.get(tag)
        if not d:
            return 0.0
        while d and now - d[0][0] > self.window:
            d.popleft()
        return sum(x[1] for x in d)

    def update(self, active, now):
        cur = set(active)
        for t in list(self.since):
            if t not in cur:
                self.since.pop(t, None)
        # _seen ATAYLAB tozalanmaydi - qisqa uzilishni ko'prik bilan
        # bog'lash uchun oxirgi aniqlangan vaqt kerak.
        # Faol bo'lmagan turlarning yig'indisi ham eskirib boradi
        if self.window:
            for t in list(self.used):
                if t not in cur:
                    self._trim(t, now)

        out = []
        for t in active:
            lim = self.limits.get(t)
            if lim is None:
                out.append(t)                 # chegarasiz - darhol buzilish
                continue
            self.since.setdefault(t, now)
            if self.window:
                if self._acc(t, now) >= lim:
                    out.append(t)
            else:
                if now - self.since[t] >= lim:
                    out.append(t)
        return out

    def elapsed(self, tag, now=None):
        """Chegaraga nisbatan sarflangan vaqt (jami yoki uzluksiz)."""
        if self.window:
            return self._trim(tag, now) if now is not None else None
        t0 = self.since.get(tag)
        return None if (t0 is None or now is None) else now - t0

    def left(self, tag, now):
        """Chegaragacha qancha qolgani (yoki None)."""
        lim = self.limits.get(tag)
        el = self.elapsed(tag, now)
        return None if (lim is None or el is None) else max(0.0, lim - el)
