# -*- coding: utf-8 -*-
"""ARGUS AI — barcha tekshiruvlar bitta buyruqda (har deploy'dan OLDIN):

    C:\\sdv\\Scripts\\python.exe tests\\run_all.py            # hammasi
    C:\\sdv\\Scripts\\python.exe tests\\run_all.py --quick    # faqat birlik testlar (kliplarsiz)

1) Birlik testlar (soxta obyektlar, tez): epizod, yo'naltirish, tamper, o'rindiq.
2) Etalon kliplar (tests/clips.json): har klip HAQIQIY FrameAnalyzer orqali
   o'tkaziladi va kutilgan natija bilan solishtiriladi (uyqu bor/yo'q, yuz
   topilish ulushi). Kliplar tests/clips/ da (git'da yo'q, md5 clips.json da).
3) Etalon kadrlar (tests/frames/): kamera OCHIQ bo'lgan tungi rasmlar —
   tamper "to'silgan" demasligi kerak.
4) Uchdan-uchiga sinov: main() kamera o'rniga klip bilan (test_smoke_loop.py).
"""
import os
import sys
import json
import time
import hashlib
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT); sys.path.insert(0, ROOT)
PY = sys.executable
QUICK = "--quick" in sys.argv
results = []          # (nom, holat, izoh)


def note(name, ok, info=""):
    results.append((name, "OK" if ok else "FAIL", info))
    print("  [%s] %-42s %s" % ("OK " if ok else "XATO", name, info), flush=True)


def run_unit(script):
    t0 = time.time()
    r = subprocess.run([PY, os.path.join("tests", script)], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    tail = (r.stdout.strip().splitlines() or [""])[-1]
    note(script, r.returncode == 0 and "OK" in tail, "%s (%.0f s)" % (tail[:60], time.time() - t0))


def md5(p):
    return hashlib.md5(open(p, "rb").read()).hexdigest()


print("=== 1. Birlik testlar ===")
for s in ("test_episodes.py", "test_routing.py", "test_tamper_seat.py"):
    run_unit(s)

if not QUICK:
    spec = json.load(open(os.path.join("tests", "clips.json"), encoding="utf-8"))
    print("=== 2. Etalon kliplar (%d) ===" % len(spec["clips"]))
    import cv2
    from argus.settings import *   # noqa
    import argus.frame_state as fs
    from argus.detect.eyes import BlendTap
    from argus.detect.reverify import FaceRecover
    from argus.detect.tamper import TamperJudge
    from safedrive.pipelines.yolo_pipeline import YoloPipeline
    pipe = YoloPipeline(model_path=MODEL_PATH, device="cpu", conf=CONF, detect_yawn=True)
    pipe.start()
    blend = BlendTap.attach(pipe)

    for c in spec["clips"]:
        p = os.path.join("tests", "clips", c["file"])
        if not os.path.exists(p):
            note(c["file"], True, "O'TKAZILDI (klip yo'q)"); continue
        if c.get("md5") and md5(p) != c["md5"]:
            note(c["file"], False, "md5 mos emas — klip o'zgargan"); continue
        facerec = FaceRecover(pipe, FACE_RECOVER_MARGIN, FACE_RECOVER_MEMORY, FACE_RECOVER_EVERY, seat_file=None)
        an = fs.FrameAnalyzer(pipe, blend, facerec, None, None)
        cap = cv2.VideoCapture(p); fps = cap.get(cv2.CAP_PROP_FPS) or 15.0
        i = n = faces = uyqu = micro = kamera = 0; t0 = time.time()
        while True:
            ok, fr = cap.read()
            if not ok: break
            i += 1
            if i % 2: continue
            n += 1
            r = an.analyze(fr, pipe.process_frame(fr), i / fps)
            faces += bool(r.face_found); uyqu += ("uyqu" in r.active); micro += ("mikrouyqu" in r.active)
            kamera += ("kamera" in r.active)
        cap.release()
        rate = 100.0 * faces / max(1, n)
        e = c["expect"]; ok = True; why = []
        if "uyqu_min" in e and uyqu < e["uyqu_min"]: ok = False; why.append("uyqu %d < %d" % (uyqu, e["uyqu_min"]))
        if "sleep_max" in e and uyqu + micro > e["sleep_max"]: ok = False; why.append("uyqu+mikro %d > %d" % (uyqu + micro, e["sleep_max"]))
        if "face_min_pct" in e and rate < e["face_min_pct"]: ok = False; why.append("yuz %.0f%% < %d%%" % (rate, e["face_min_pct"]))
        if "kamera_max" in e and kamera > e["kamera_max"]: ok = False; why.append("kamera %d > %d" % (kamera, e["kamera_max"]))
        note(c["file"][:42], ok, "uyqu=%d mikro=%d yuz=%.0f%% kamera=%d (%.0f s)%s"
             % (uyqu, micro, rate, kamera, time.time() - t0, ("  <- " + ", ".join(why)) if why else ""))

    print("=== 3. Etalon kadrlar — tamper (%d) ===" % len(spec.get("frames", [])))
    for f in spec.get("frames", []):
        p = os.path.join("tests", "frames", f["file"])
        if not os.path.exists(p):
            note(f["file"], True, "O'TKAZILDI (rasm yo'q)"); continue
        img = cv2.imread(p)
        # HUD paneli va banner chap tomonda (x < 32%) — ular tafsilotni sun'iy oshiradi, kesib tashlaymiz
        img = img[:, int(img.shape[1] * 0.32):]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean_b = float(gray.mean())
        # ishlab chiqarish bilan bir xil: YARIM o'lcham, float32 (frame_state.py)
        small = cv2.resize(gray, (gray.shape[1] // 2, gray.shape[0] // 2), interpolation=cv2.INTER_AREA)
        detail = float(cv2.Laplacian(small, cv2.CV_32F).var())
        j = TamperJudge(TAMPER_DETAIL_VAR, TAMPER_DARK_MEAN, TAMPER_DROP, TAMPER_DROP_MIN, TAMPER_DROP_FRAC, TAMPER_DETAIL_REF, TAMPER_EMA_ALPHA)
        j.ema = mean_b                      # barqaror holat
        blocked = j.update(mean_b, detail)[0]
        exp = f["expect"].get("blocked", False)
        note(f["file"][:42], blocked == exp, "yorug'lik=%.0f tafsilot=%.0f blocked=%s" % (mean_b, detail, blocked))

    print("=== 4. Uchdan-uchiga (smoke) ===")
    smoke_clip = os.path.join("tests", "clips", spec.get("smoke_clip", ""))
    if os.path.exists(smoke_clip):
        t0 = time.time()
        r = subprocess.run([PY, os.path.join("tests", "test_smoke_loop.py"), smoke_clip], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        line = [l for l in r.stdout.splitlines() if l.startswith("SMOKE:")]
        note("test_smoke_loop.py", "SMOKE TEST OK" in r.stdout and "Buzilish: Uyqu" in r.stdout,
             "%s (%.0f s)" % (line[0][7:60] if line else "?", time.time() - t0))
    else:
        note("test_smoke_loop.py", True, "O'TKAZILDI (klip yo'q)")

fails = [r for r in results if r[1] != "OK"]
print("=== JAMI: %d tekshiruv, %d xato ===" % (len(results), len(fails)))
for name, st, info in fails:
    print("  XATO:", name, info)
print("RUN_ALL", "OK" if not fails else "FAIL")
sys.exit(1 if fails else 0)
