# -*- coding: utf-8 -*-
"""Uyquchanlik ko'rsatkichlari: PERCLOS va pirpirash davomiyligi.

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

import collections



class Perclos:
    """PERCLOS — ko'z yumuqligi ulushi, sirpanuvchi VAQT oynasi bo'yicha.

    SafeDrive ichida ham PERCLOSTracker bor, lekin u KADR soniga tayanadi
    (fps=30 deb faraz qiladi — bizda 24-26 va o'zgaruvchan), va pipeline
    unga faqat 0/2 uzatgani uchun "yarim yumuq" holat yo'qoladi.
    Shuning uchun bu yerda vaqt bo'yicha va uch bosqichli."""

    # Standart ta'rif: ko'z KAMIDA 80% yumuq bo'lgan vaqt ulushi.
    # "half" ~50% yumuq, ya'ni ta'rifga ko'ra hisoblanmasligi kerak edi.
    # Avval 0.5 qo'ygandim va PERCLOS sun'iy shishib ketdi - oddiy o'tirgan
    # odamda ham 19-24% chiqardi, ya'ni ogohlantirish chegarasida turardi.
    SCORE = {"closed": 1.0, "half": 0.2}           # qolgani (open/unknown) = 0.0

    def __init__(self, window=60.0, min_samples=0):
        self.window = window
        # Oynada kamida shuncha namuna bo'lsin: yuz 60 s dan faqat 12 s
        # ko'ringan bo'lsa (lok 00:33), 12 s dagi "yumuq" 60 s ga umumlashmasin.
        self.min_samples = int(min_samples)
        self.buf = collections.deque()             # (t, ball)

    def _trim(self, now):
        while self.buf and now - self.buf[0][0] > self.window:
            self.buf.popleft()

    def decay(self, now):
        """Namuna QO'SHMASDAN oynani tozalaydi.

        Bosh egilganda o'lchov ishonchsiz va update() chaqirilmaydi. Agar
        oyna ham tozalanmasa, eski "yumuq" namunalar qotib qoladi va
        PERCLOS asossiz yuqori turadi — aynan shu xato bo'lgan edi."""
        self._trim(now)
        return self.value()

    def update(self, eye_state, now):
        self.buf.append((now, self.SCORE.get(eye_state, 0.0)))
        self._trim(now)
        return self.value()

    def value(self):
        if not self.buf:
            return 0.0
        return sum(s for _, s in self.buf) / len(self.buf)

    def ready(self):
        """Oyna yarmi to'lmaguncha natija ishonchsiz — signal berilmaydi."""
        return (len(self.buf) > 1 and len(self.buf) >= self.min_samples
                and (self.buf[-1][0] - self.buf[0][0]) >= self.window * 0.5)

    def reset(self):
        self.buf.clear()


class BlinkTracker:
    """Pirpirash davomiyligi — charchoqning erta belgisi.

    Tinch odamda o'rtacha <200 ms, uyqusizlikda >500 ms ga cho'ziladi.
    Yumilish boshlanishi va tugashi orasidagi vaqt o'lchanadi."""

    MIN_BLINK = 0.05        # bundan qisqasi — shovqin
    MAX_BLINK = 1.0         # bundan uzuni pirpirash emas, uyqu

    def __init__(self, window=120.0, min_samples=5):
        self.window = window
        self.min_samples = min_samples
        self.blinks = collections.deque()          # (tugagan_vaqt, davomiylik)
        self._start = None

    def update(self, closed, now):
        if closed:
            if self._start is None:
                self._start = now                  # yumilish boshlandi
        elif self._start is not None:
            d = now - self._start                  # yumilish tugadi
            self._start = None
            if self.MIN_BLINK <= d <= self.MAX_BLINK:
                self.blinks.append((now, d))
        while self.blinks and now - self.blinks[0][0] > self.window:
            self.blinks.popleft()

    def mean_ms(self):
        """MEDIANA davomiylik (ms). Namuna kam bo'lsa None.

        Ilgari o'rtacha olinardi, lekin u bitta chetlagan qiymatga juda
        sezgir: 5 ta namunadan bittasi 2 s bo'lsa, o'rtacha 400 ms ga
        ko'tarilib yolg'on "sekin pirpirash" beradi. Mediana bunga
        berilmaydi."""
        if len(self.blinks) < self.min_samples:
            return None
        d = sorted(v for _, v in self.blinks)
        n = len(d)
        mid = d[n // 2] if n % 2 else (d[n // 2 - 1] + d[n // 2]) / 2.0
        return 1000.0 * mid

    def rate_per_min(self):
        if not self.blinks:
            return 0.0
        span = max(self.blinks[-1][0] - self.blinks[0][0], 1e-6)
        return 60.0 * len(self.blinks) / span


class EarBaseline:
    """Har odamning O'Z ochiq-ko'z EAR darajasiga moslashadigan ostona.

    Nega kerak: EAR ko'zning shakliga, kameraning burchagiga va qarash
    yo'nalishiga bog'liq. 2026-09-24 da 34 soniyalik yozuvda o'lchandi —
    haydovchi telefonga pastga qarab turganda EAR 0.19-0.25 oralig'ida
    yurdi. Qat'iy ostona (ochiq 0.25 / yarim 0.20) bilan 451 kadrdan 57
    tasi "yumuq" bo'lib chiqdi, eng uzun uzluksiz yumilish 1.51 s —
    ya'ni tizim TO'LIQ UYQU signalini berardi. Moslashuvchan ostona bilan
    o'sha yozuvda yumuq kadrlar 4 ta, eng uzuni 0.15 s.

    Qanday ishlaydi: oxirgi `window` soniyadagi EAR qiymatlarining yuqori
    protsentili (default 85%) olinadi — bu odamning OCHIQ ko'z darajasi.
    Ostonalar shundan nisbat bilan olinadi.

    XAVFSIZLIK: agar haydovchi butun oyna davomida ko'zini yumib yotsa,
    protsentil ham pasayib ketishi va signalni o'chirib qo'yishi mumkin
    edi. Shuning uchun baza `floor` dan pastga TUSHMAYDI — bu holda
    ostonalar qat'iy qiymatga yaqin qoladi va uyqu baribir aniqlanadi."""

    def __init__(self, window=180.0, pct=0.85, min_samples=60,
                 floor=0.22, cap=0.45, open_ratio=0.78, half_ratio=0.62):
        self.window = window
        self.pct = pct
        self.min_samples = min_samples
        self.floor, self.cap = floor, cap
        self.open_ratio, self.half_ratio = open_ratio, half_ratio
        self.buf = collections.deque()      # (vaqt, ear)
        self.base = None

    def update(self, ear, now):
        self.buf.append((now, float(ear)))
        while self.buf and now - self.buf[0][0] > self.window:
            self.buf.popleft()
        if len(self.buf) < self.min_samples:
            self.base = None
            return
        v = sorted(e for _, e in self.buf)
        b = v[int(self.pct * (len(v) - 1))]
        self.base = min(self.cap, max(self.floor, b))

    def reset(self):
        """Yuz yo'qolganda chaqiriladi — eski qiymatlar aralashmasin."""
        self.buf.clear()
        self.base = None

    def thresholds(self, fallback_open, fallback_half):
        """(ochiq_ostona, yarim_ostona). Baza yig'ilmagan bo'lsa qat'iy qiymat."""
        if self.base is None:
            return fallback_open, fallback_half
        return self.base * self.open_ratio, self.base * self.half_ratio

    def ready(self):
        return self.base is not None
