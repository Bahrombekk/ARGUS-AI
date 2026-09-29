# -*- coding: utf-8 -*-
"""'Tik turgan' qoidasi:
1) PersonDetector: tik turgan kadrda standing=True, o'tirgan kadrlarda False.
2) FrameAnalyzer (soxta persondet, yuz yo'q): tik turgan -> 'yuz' chiqmaydi, STAND_SEC
   dan keyin 'turgan'; o'tirgan (to'sgan) -> avvalgidek 4 s da 'yuz'."""
import os, sys, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import cv2, numpy as np
from argus.settings import *   # noqa
from argus.detect.person import PersonDetector
import argus.frame_state as fs

# 1) haqiqiy detektor, etalon kadrlar
pd = PersonDetector(PERSON_MODEL, PERSON_CONF, 0.0)
cases = [("tests/frames/standing_loco_20260929_105628.jpg", True),
         ("tests/frames/day_face_cut_20260928_083521.jpg", False),
         ("tests/frames/day_camera_open_20260926_003301.jpg", False)]
for path, exp in cases:
    img = cv2.imread(path); pres = pd.update(img, 100.0 + cases.index((path, exp)))
    print("%-48s odam=%s tik=%s qutilar=%s" % (os.path.basename(path), pres, pd.standing, pd.boxes[:2]))
    assert pd.standing == exp, path
img = cv2.imread("tests/frames/empty_seat_loco_20260929_173441.jpg")
pd.update(img, 200.0); print("bo'sh o'rindiq (devorda rasm): odam=%s qutilar=%s" % (pd.present, pd.boxes))
assert pd.present is False, "bo'sh o'rindiqda odam bo'lmasligi kerak"
img = cv2.imread("tests/frames/empty_seat_clean_loco_20260929_172314.jpg")
pd.update(img, 201.0); print("bo'sh o'rindiq (toza probe kadr): odam=%s qutilar=%s" % (pd.present, pd.boxes))
assert pd.present is False
print("PERSON STANDING OK")

# 2) analyzer mantiqi (soxta persondet)
class FakePD:
    def __init__(self, standing): self.present = True; self.standing = standing
    def update(self, frame, now): return True
class FakePipe:
    def _run_mediapipe(self, crop): return {"face_found": False}
# tekisturali kadr — bir xil rang tamper 'to'silgan' deb hisoblanadi (tafsilot 0)
frame = np.random.default_rng(0).integers(0, 255, (720, 1280, 3), dtype=np.uint8)
def run(standing, seconds, fps=18.0):
    fs.EYE_ZOOM = False
    an = fs.FrameAnalyzer(FakePipe(), None, None, FakePD(standing), None)
    first = {}
    for i in range(int(seconds * fps)):
        now = i / fps
        r = an.analyze(frame, {"face_found": False, "eye_state": "unknown"}, now)
        for t in r.active:
            first.setdefault(t, now)
    return first
f = run(True, 70)
print("tik turgan 70 s:", {k: round(v, 1) for k, v in f.items()})
assert "yuz" not in f, "tik turganda 'yuz' chiqmasligi kerak"
assert "turgan" in f and 59.5 <= f["turgan"] <= 62.0, f
f = run(False, 10)
print("o'tirgan, yuz to'silgan 10 s:", {k: round(v, 1) for k, v in f.items()})
assert "yuz" in f and 3.9 <= f["yuz"] <= 5.5 and "turgan" not in f, f
print("STANDING TEST OK")
