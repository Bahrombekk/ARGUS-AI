# -*- coding: utf-8 -*-
"""Ko'z yumuqligini TASDIQLASH — EAR yolg'on "yumuq" bergan holatlarga qarshi.

Nega kerak (o'lchov 2026-09-26, lokomotiv, 00:31-00:55, 42 ta xabar):
  Haydovchi (yoki kabinadagi boshqa odam) kameraga yaqin turib PASTGA qarasa,
  yuqori qovoq ko'z qorachig'i bilan birga tushadi va EAR 0.09-0.18 gacha
  pasayadi — bu qat'iy/moslashuvchan ostonada "yumuq" hisoblanadi. Natijada
  mikrouyqu (1 s), uyqu (2 s) va PERCLOS 43-67% xabarlari ketdi, lekin
  ko'z OCHIQ edi (rasmlarda ko'rinadi).

  MediaPipe FaceLandmarker blendshape'lari bu ikki holatni ajratadi:
    HAQIQIY yumuq (stol yozuvi rec_20260910_164113): eyeBlink med 0.77, EAR 0.10
    Pastga qarash (lok, 4 ta klip):                 eyeBlink 0.36-0.55, EAR 0.09-0.18
  eyeLookDown IKKALASIDA ham yuqori (0.5-0.83) — u ajratmaydi, faqat eyeBlink.

Qanday ishlaydi:
  BlendTap pipeline'ning FaceLandmarker'ini blendshape'lar YOQILGAN nusxaga
  almashtiradi va har detect() natijasini saqlab qoladi. Pipeline'ning o'z
  kodi o'zgarmaydi (u faqat landmark'larni o'qiydi). Blendshape hisoblash
  ~1 ms — FPS ga sezilarli ta'sir yo'q.

  Agar blendshape'lar ishlamasa (eski mediapipe, xato) — cues() bo'sh dict
  qaytaradi va uyqu mantig'i ESKI usulda davom etadi (xavfsizlik: nazorat
  o'chib qolmasin).
"""
import collections


class BlendTap:
    """FaceLandmarker o'rniga qo'yiladigan proksi: oxirgi natijani saqlaydi."""

    def __init__(self, inner):
        self._inner = inner
        self.last = None

    def detect(self, img):
        r = self._inner.detect(img)
        self.last = r
        return r

    def close(self):
        try:
            self._inner.close()
        except Exception:
            pass

    # ------------------------------------------------------------------
    @classmethod
    def attach(cls, pipe):
        """pipe.start() dan KEYIN chaqiriladi. Muvaffaqiyatsiz bo'lsa None."""
        try:
            import mediapipe as mp  # noqa: F401
            from mediapipe.tasks import python as mpp
            from mediapipe.tasks.python import vision as mpv
            from safedrive.model_manager import get_model_path
            old = getattr(pipe, "_mp_landmarker", None)
            if old is None:
                return None
            opts = mpv.FaceLandmarkerOptions(
                base_options=mpp.BaseOptions(
                    model_asset_path=get_model_path("face_landmarker")),
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_face_presence_confidence=0.5,
                min_tracking_confidence=0.5,
                output_face_blendshapes=True,
            )
            new = mpv.FaceLandmarker.create_from_options(opts)
            tap = cls(new)
            pipe._mp_landmarker = tap
            try:
                old.close()
            except Exception:
                pass
            print("Ko'z tasdiqlash: blendshape'lar YOQILDI (eyeBlink)")
            return tap
        except Exception as e:
            print("Ko'z tasdiqlash: blendshape'lar ishlamadi (eski usul):", repr(e))
            return None

    def cues(self):
        """Oxirgi kadr uchun {'blink': 0..1, 'down': 0..1, 'cut': bool}.
        Yuz yo'q yoki blendshape yo'q bo'lsa — {} (mantiq eski usulga o'tadi)."""
        r = self.last
        if r is None or not getattr(r, "face_landmarks", None):
            return {}
        out = {}
        bs = getattr(r, "face_blendshapes", None)
        if bs:
            d = {b.category_name: b.score for b in bs[0]}
            if "eyeBlinkLeft" in d and "eyeBlinkRight" in d:
                out["blink"] = (d["eyeBlinkLeft"] + d["eyeBlinkRight"]) / 2.0
                out["down"] = (d.get("eyeLookDownLeft", 0.0) +
                               d.get("eyeLookDownRight", 0.0)) / 2.0
        # Yuz kadr chetida kesilgan bo'lsa landmark'lar taxminiy — ishonchsiz
        # (lok 00:33 klipi: yuz 12 kadrda chetda, EAR 0.05 "yumuq" chiqdi).
        lm = r.face_landmarks[0]
        xs = [p.x for p in lm]
        ys = [p.y for p in lm]
        out["cut"] = (min(xs) < 0.01 or max(xs) > 0.99 or
                      min(ys) < 0.01 or max(ys) > 0.99)
        return out


class BlinkConfirm:
    """eyeBlink ballini EAR kabi 3 kadr medianasi bilan silliqlaydi va
    "yumuq ISHONCHLI" degan javob beradi.

    Bitta kadrda ball tushib ketsa (haqiqiy yumuqda 15 kadrdan 1 tasi 0.7 dan
    past chiqdi) Sustain hisoblagichi noldan boshlanmasin — shuning uchun
    mediana."""

    def __init__(self, min_score=0.6, smooth_n=3):
        self.min_score = float(min_score)
        self.hist = collections.deque(maxlen=max(1, int(smooth_n)))

    def reset(self):
        self.hist.clear()

    def update(self, blink):
        """blink None -> ma'lumot yo'q -> True (eski usul, cheklamaydi)."""
        if blink is None:
            self.hist.clear()
            return True, None
        self.hist.append(float(blink))
        v = sorted(self.hist)
        n = len(v)
        med = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2.0
        return med >= self.min_score, med
