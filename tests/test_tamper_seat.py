# -*- coding: utf-8 -*-
"""1) TamperJudge: tungi haqiqiy o'lchovlar (yolg'on bo'lmasin) + sun'iy lens yopilishi
   (aniqlansin) — eski qat'iy qoida bilan solishtiriladi.
2) FaceRecover o'rindiq xotirasi: buzilgan fayl rad etiladi, kam namuna saqlanmaydi,
   uzoq siljishda qayta o'rganadi."""
import os, sys, json, tempfile, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import cv2, numpy as np
from argus.settings import *   # noqa
from argus.detect.tamper import TamperJudge
from argus.detect.reverify import FaceRecover

def judge(): return TamperJudge(TAMPER_DETAIL_VAR, TAMPER_DARK_MEAN, TAMPER_DROP, TAMPER_DROP_MIN, TAMPER_DROP_FRAC, TAMPER_DETAIL_REF, TAMPER_EMA_ALPHA)
def old_rule(ema, mean_b, detail):
    sudden = (ema - mean_b) > TAMPER_DROP and mean_b < TAMPER_DARK_MEAN
    return (detail < TAMPER_DETAIL_VAR) or sudden

# --- 1a: tungi HAQIQIY o'lchovlar (lok jurnali 2026-09-29): (yorug'lik, tafsilot) — hammasi kamera OCHIQ
night = [(3, 14), (36, 19), (37, 18), (3, 18), (6, 20), (6, 20), (5, 19), (4, 16), (2, 14), (3, 19), (5, 19), (4, 15), (13.7, 42), (35, 28)]
old_fp = new_fp = 0
for m, d in night:
    j = judge(); j.ema = m                       # barqaror holat (keskin tushish yo'q)
    b, sd, ld = j.update(m, d)
    old_fp += old_rule(m, m, d); new_fp += b
print("tungi ochiq kamera: eski yolg'on=%d/%d  yangi yolg'on=%d/%d" % (old_fp, len(night), new_fp, len(night)))
assert new_fp == 0

# --- 1b: kunduzi haqiqiy yopilish: yorug' kabina (mean 120, detail 300) -> qo'l yopdi (mean 8, detail 3)
j = judge()
for _ in range(60): j.update(120, 300)
hits = sum(j.update(8, 3)[0] for _ in range(20))
print("kunduzgi yopilish (120->8): aniqlandi kadr=%d/20" % hits); assert hits == 20
# --- 1c: xira kabinada yopilish: mean 36 -> 4 (eski qoida uchun 32 < 40 -> o'tkazib yuborardi)
j = judge()
for _ in range(60): j.update(36, 25)
first = j.update(4, 3)
print("xira kabinada yopilish (36->4): birinchi kadr blocked=%s sudden=%s | eski=%s" % (first[0], first[1], old_rule(36, 4, 3)))
assert first[0] and first[1]
# --- 1d: sekin shom (yorug'lik 120 -> 5 asta, 3 daqiqa) — hech qachon blocked bo'lmasin
j = judge(); fp = 0
for k in range(3000):
    m = 120 - 115 * k / 3000; d = max(12, 300 * m / 120)
    fp += j.update(m, d)[0]
print("asta shom: yolg'on kadr=%d" % fp); assert fp == 0
# --- 1e: yorug' kabinada tafsilotsiz (oq devor/qopqoq) detail 10 -> blocked (avvalgidek)
j = judge(); j.ema = 150; assert j.update(150, 10)[0]
print("TAMPER TEST OK")

# --- 2: o'rindiq xotirasi
class FakePipe:
    def _run_mediapipe(self, crop): return {"face_found": False}
tmp = tempfile.mkdtemp(); sf = os.path.join(tmp, "seat.json")
with open(sf, "w") as fh: json.dump({"seat": [102.8, 78.2, 302.3, 284.9], "n": 20}, fh)     # kechagi buzilgan fayl
fr = FaceRecover(FakePipe(), 2.5, 3600.0, 0.15, seat_file=sf)
assert fr.seat is None, "n=20 fayl yuklanmasligi kerak"
with open(sf, "w") as fh: json.dump({"seat": [102.8, 78.2, 302.3, 284.9], "n": 5000}, fh)     # ko'p namuna, lekin chetda
fr = FaceRecover(FakePipe(), 2.5, 3600.0, 0.15, seat_file=sf)
assert fr.seat is not None
fr.retry(np.zeros((720, 1280, 3), np.uint8), 100.0)                              # birinchi kadrda geometriya tekshiruvi
assert fr.seat is None, "chetdagi o'rindiq rad etilishi kerak"
print("buzilgan/chetdagi o'rindiq fayli rad etildi OK")
# o'rganish: 500 ta markaziy quti -> saqlanadi; 20 ta emas
lm = [types.SimpleNamespace(x=0.45, y=0.5), types.SimpleNamespace(x=0.55, y=0.72)]
os.remove(sf)                                                                    # toza boshlash
fr2 = FaceRecover(FakePipe(), 2.5, 3600.0, 0.15, seat_file=sf)
for k in range(30): fr2.note(lm, 1280, 720, 200 + k * 0.05)
assert fr2.seat_n < 400
for k in range(500): fr2.note(lm, 1280, 720, 300 + k * 0.05)
d = json.load(open(sf)); assert d["n"] >= 400 and 500 < d["seat"][0] < 620, d
print("o'rindiq %d namunada saqlandi: %s OK" % (d["n"], [int(v) for v in d["seat"]]))
# chetdagi topilish o'rindiqni buzmasin
edge = [types.SimpleNamespace(x=0.05, y=0.05), types.SimpleNamespace(x=0.15, y=0.25)]
s0 = fr2.seat
for k in range(300): fr2.note(edge, 1280, 720, 400 + k * 0.05)
assert fr2.seat == s0, "chetdagi topilishlar o'rindiqni o'zgartirmasligi kerak"
# haydovchi joyi haqiqatan o'zgardi (markazda, lekin uzoq): 200 dan keyin qayta o'rganadi
moved = [types.SimpleNamespace(x=0.7, y=0.35), types.SimpleNamespace(x=0.78, y=0.55)]
for k in range(250): fr2.note(moved, 1280, 720, 500 + k * 0.05)
assert abs(fr2.seat[0] - 0.7 * 1280) < 30, fr2.seat
print("uzoq siljishda qayta o'rganish OK")
print("SEAT TEST OK")
