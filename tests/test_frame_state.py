# -*- coding: utf-8 -*-
"""Refaktor tekshiruvi: FrameAnalyzer (yangi) vs eski monolit loop.py dagi
kadr-tahlil bloki (tests/loop_legacy_20260928.py dan AVTOMATIK kesib olinadi).
Ikkalasi alohida pipeline/FaceRecover bilan bir xil kliplarni o'qiydi;
har kadrda active/eye_state/face_found/... bir xil bo'lishi shart.

python tests/test_frame_state.py <clip.mp4> [...]
"""
import os
import sys
import types
import textwrap
import collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import cv2
from argus.settings import *   # noqa
from argus.detect.windows import PresenceWindow, Sustain
from argus.detect.drowsy import Perclos, BlinkTracker, EarBaseline
from argus.detect.eyes import BlendTap, BlinkConfirm
from argus.detect.reverify import FaceRecover, Confirm, Grace
from argus.detect.person import PersonDetector
from argus.frame_state import FrameAnalyzer
from safedrive.pipelines.yolo_pipeline import YoloPipeline

LEGACY = os.path.join(ROOT, "tests", "loop_legacy_20260928.py")
STATE_NAMES = ["facerec", "blend", "ear_hist", "ear_raw", "ear_base", "last_face_t",
               "phonedet", "tilt_hist", "nod_hist", "tilt_base", "nod_base", "blink_cf",
               "tamper_bright_ema", "eye_sus", "micro_sus", "yawn_sus", "perclos",
               "blinks", "pc_crit_sus", "pc_warn_sus", "distract_sus", "tamper_sus",
               "persondet", "noface_sus", "absent_sus", "phone_pw", "smoke_pw",
               "belt_pw", "confirm"]
OUT_NAMES = ["active", "face_found", "eye_state", "eye_reliable", "eye_shaky",
             "blink_sure", "blink_bs", "blocked", "person_present", "drowsy_al",
             "micro_al", "yawn_al", "noface_al", "absent_al", "looking_away",
             "distract_al", "tamper_al", "perclos_val", "blink_ms", "phone_al"]


def build_legacy():
    """Eski loop.py dan kadr-tahlil blokini kesib, funksiya qilib qaytaradi."""
    src = open(LEGACY, encoding="utf-8").read().split("\n")
    a = next(i for i, l in enumerate(src) if l.strip() == 'eye_state = res.get("eye_state", "unknown")')
    b = next(i for i, l in enumerate(src) if l.strip() == "active = confirm.update(active, now)")
    block = textwrap.dedent("\n".join(src[a:b + 1]))
    fn = ["def analyze_legacy(S, frame, res, now):"]
    fn += ["    %s = S.%s" % (n, n) for n in STATE_NAMES]
    fn += ["    mean_b = -1.0; detail = 0.0"]
    fn += textwrap.indent(block, "    ").split("\n")
    fn += ["    S.%s = %s" % (n, n) for n in ("last_face_t", "tilt_base", "nod_base", "tamper_bright_ema")]
    fn += ["    return dict(" + ", ".join("%s=%s" % (n, n) for n in OUT_NAMES) + ")"]
    ns = dict(globals())
    exec("\n".join(fn), ns)
    return ns["analyze_legacy"]


def legacy_state(pipe, blend, facerec, persondet):
    S = types.SimpleNamespace()
    S.facerec = facerec; S.blend = blend; S.persondet = persondet; S.phonedet = None
    S.ear_hist = collections.deque(maxlen=max(1, EYE_SMOOTH_N))
    S.ear_raw = collections.deque(maxlen=max(4, EYE_VOLATILE_WIN))
    S.ear_base = (EarBaseline(EAR_BASE_WINDOW, EAR_BASE_PCT, EAR_BASE_MIN_SAMPLES,
                              EAR_BASE_FLOOR, EAR_BASE_CAP, EAR_OPEN_RATIO, EAR_HALF_RATIO)
                  if EAR_ADAPTIVE else None)
    S.last_face_t = None
    S.tilt_hist = collections.deque(maxlen=300); S.nod_hist = collections.deque(maxlen=300)
    S.tilt_base = S.nod_base = 0.0
    S.blink_cf = BlinkConfirm(EYE_BLINK_BS_MIN, EYE_SMOOTH_N)
    S.tamper_bright_ema = None
    S.eye_sus = Sustain(EYE_CLOSED_SEC); S.micro_sus = Sustain(MICROSLEEP_SEC)
    S.yawn_sus = Sustain(YAWN_SEC); S.perclos = Perclos(PERCLOS_WINDOW, PERCLOS_MIN_SAMPLES)
    S.blinks = BlinkTracker(BLINK_WINDOW, BLINK_MIN_SAMPLES)
    S.pc_crit_sus = Sustain(PERCLOS_HOLD); S.pc_warn_sus = Sustain(PERCLOS_HOLD)
    S.distract_sus = Sustain(DISTRACT_SEC); S.tamper_sus = Sustain(TAMPER_SEC)
    S.noface_sus = Sustain(NOFACE_SEC); S.absent_sus = Sustain(ABSENT_SEC)
    S.phone_pw = PresenceWindow(PHONE_WINDOW, PHONE_RATIO, PHONE_MIN)
    S.smoke_pw = PresenceWindow(SMOKE_WINDOW, SMOKE_RATIO, SMOKE_MIN)
    S.belt_pw = PresenceWindow(BELT_WINDOW, BELT_RATIO, BELT_MIN)
    S.confirm = Confirm(CONFIRM_SEC, CONFIRM_TAGS) if CONFIRM_SEC > 0 else None
    return S


def make_stack():
    pipe = YoloPipeline(model_path=MODEL_PATH, device="cpu", conf=CONF, detect_yawn=True)
    pipe.start()
    blend = BlendTap.attach(pipe)
    facerec = FaceRecover(pipe, FACE_RECOVER_MARGIN, FACE_RECOVER_MEMORY, FACE_RECOVER_EVERY,
                          seat_file=None)
    persondet = PersonDetector(PERSON_MODEL, PERSON_CONF, PERSON_EVERY) if os.path.exists(PERSON_MODEL) else None
    return pipe, blend, facerec, persondet


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        if a is None or b is None:
            return a is b
        return abs(float(a) - float(b)) < 1e-6
    if isinstance(a, list):
        return list(a) == list(b)
    return a == b


def main(clips):
    analyze_legacy = build_legacy()
    p1, b1, f1, d1 = make_stack()      # eski
    p2, b2, f2, d2 = make_stack()      # yangi
    S = legacy_state(p1, b1, f1, d1)
    an = FrameAnalyzer(p2, b2, f2, d1 if d2 is None else d2, None)
    total = 0; bad = 0; act_frames = 0
    for clip in clips:
        cap = cv2.VideoCapture(clip); fps = cap.get(cv2.CAP_PROP_FPS) or 15.0; i = 0
        while True:
            ok, frame = cap.read()
            if not ok: break
            i += 1
            if i % 2: continue
            now = i / fps
            r1 = p1.process_frame(frame); r2 = p2.process_frame(frame)
            o1 = analyze_legacy(S, frame, r1, now)
            fr = an.analyze(frame, r2, now)
            o2 = {k: getattr(fr, k) for k in OUT_NAMES}
            total += 1
            if o1["active"]: act_frames += 1
            diff = [k for k in OUT_NAMES if not same(o1[k], o2[k])]
            if diff:
                bad += 1
                if bad <= 8:
                    print("  FARQ %s kadr %d: %s" % (os.path.basename(clip), i,
                          ", ".join("%s: %r != %r" % (k, o1[k], o2[k]) for k in diff)))
        cap.release()
        print("%s: solishtirildi (jami %d kadr, farq %d)" % (os.path.basename(clip), total, bad))
    print("JAMI kadr=%d | faol-kadr=%d | FARQ=%d" % (total, act_frames, bad))
    print("FRAME-STATE TEST", "OK" if bad == 0 else "FAIL")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
