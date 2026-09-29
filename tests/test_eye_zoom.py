# -*- coding: utf-8 -*-
"""Ko'z ZOOM (ikkinchi fikr): haqiqiy FrameAnalyzer bilan kliplarni ikki marta
o'tkazamiz — zoom O'CHIQ va YOQIQ. Haqiqiy yumuq kliplarda uyqu/mikrouyqu
saqlanib qolishi, yolg'on (pastga qarash) kliplarda ko'paymasligi kerak.

python tests/test_eye_zoom.py real:<clip> false:<clip> ...
"""
import os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)
import cv2
from argus.settings import *   # noqa
import argus.frame_state as fs
from argus.detect.eyes import BlendTap
from argus.detect.reverify import FaceRecover
from safedrive.pipelines.yolo_pipeline import YoloPipeline

pipe = YoloPipeline(model_path=MODEL_PATH, device="cpu", conf=CONF, detect_yawn=True); pipe.start()
blend = BlendTap.attach(pipe)

def run(clip, zoom):
    fs.EYE_ZOOM = zoom
    facerec = FaceRecover(pipe, FACE_RECOVER_MARGIN, FACE_RECOVER_MEMORY, FACE_RECOVER_EVERY, seat_file=None)
    an = fs.FrameAnalyzer(pipe, blend, facerec, None, None)
    cap = cv2.VideoCapture(clip); fps = cap.get(cv2.CAP_PROP_FPS) or 15.0; i = 0
    uyqu = micro = closed = 0; zvals = []
    while True:
        ok, fr = cap.read()
        if not ok: break
        i += 1
        if i % 2: continue
        res = pipe.process_frame(fr)
        r = an.analyze(fr, res, i / fps)
        closed += bool(r.eye_closed and r.eye_reliable and r.blink_sure)
        uyqu += ("uyqu" in r.active); micro += ("mikrouyqu" in r.active)
        if r.zoom_bs is not None: zvals.append((r.zoom_ear, r.zoom_bs, r.zoom_veto))
    cap.release()
    return dict(uyqu=uyqu, micro=micro, closed=closed, nzoom=an.n_zoom, veto=an.n_zoom_veto, z=zvals)

ok = True
for arg in sys.argv[1:]:
    kind, clip = arg.split(":", 1)
    a = run(clip, False); b = run(clip, True)
    zb = [v[1] for v in b["z"]]; ze = [v[0] for v in b["z"]]
    print("%-6s %-26s | zoom OFF: uyqu=%3d mikro=%3d | zoom ON: uyqu=%3d mikro=%3d | zoom=%d veto=%d | zoom eyeBlink med=%s EAR med=%s" % (
        kind, os.path.basename(clip)[:26], a["uyqu"], a["micro"], b["uyqu"], b["micro"], b["nzoom"], b["veto"],
        ("%.2f" % sorted(zb)[len(zb)//2]) if zb else "-", ("%.3f" % sorted(ze)[len(ze)//2]) if ze else "-"))
    if kind == "real" and (a["uyqu"] > 0) and b["uyqu"] == 0:
        print("   XATO: haqiqiy uyqu zoom bilan yo'qoldi"); ok = False
    if kind == "false" and (b["uyqu"] + b["micro"]) > (a["uyqu"] + a["micro"]):
        print("   XATO: yolg'on signal ko'paydi"); ok = False
print("EYE ZOOM TEST", "OK" if ok else "FAIL")
sys.exit(0 if ok else 1)
