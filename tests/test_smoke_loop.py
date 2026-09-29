# -*- coding: utf-8 -*-
"""Uchdan-uchiga tekshiruv: argus.loop.main() ni haqiqiy kod bilan, lekin
kamera o'rniga KLIP, Telegram/sayt/GPS o'chirilgan holda ishga tushiradi.
Xabarlar yuborilmaydi — Telegram.send/send_photo/send_video ushlab olinadi
va sanaladi. Klip tugagach KeyboardInterrupt bilan chiqiladi.

python tests/test_smoke_loop.py <clip.mp4>
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

import config
config.ENABLE_TELEGRAM = False
config.ENABLE_WEBHOOK = False
config.ENABLE_GPS = False
config.HEADLESS = True
config.ENABLE_DATASET = False
config.RECORD_AUDIO = False
config.ENABLE_SEATBELT = False
config.ENABLE_SMOKING = False
config.DAY_FILE = os.path.join(config.HERE, "tests", "_day_stats_test.json")
config.SEAT_ROI_FILE = os.path.join(config.HERE, "tests", "_seat_test.json")
config.DEPLOY_NOTE_FILE = os.path.join(config.HERE, "tests", "_deploy_note_test.txt")
config.RECORD_DIR = os.path.join(config.HERE, "tests", "_records")
os.makedirs(config.RECORD_DIR, exist_ok=True)
with open(config.DEPLOY_NOTE_FILE, "w", encoding="utf-8") as fh:
    fh.write("test deploy note")

import cv2
import argus.media.camera as camera
import argus.net.telegram as tgmod

CLIP = sys.argv[1]
sent = {"text": [], "photo": [], "video": []}


class FakeCap:
    def __init__(self, path):
        self.cap = cv2.VideoCapture(path)
    def read(self):
        ok, fr = self.cap.read()
        if not ok:
            raise KeyboardInterrupt      # klip tugadi -> main dan chiqamiz
        return True, fr
    def release(self):
        self.cap.release()


camera.open_any_camera = lambda: (FakeCap(CLIP), 0)

# Telegram: ok=True qilib xabarlarni ushlab olamiz (tarmoqqa chiqmaydi)
def _init(self, token, admin_id, enabled=True):
    self.admin = "0"; self.approved = {"0"}; self.ok = True; self.outbox = []
tgmod.Telegram.__init__ = _init
tgmod.Telegram.send = lambda self, text, admin_only=False: sent["text"].append((text, admin_only))
tgmod.Telegram.send_photo = lambda self, p, caption="", admin_only=False: sent["photo"].append((p, caption))
tgmod.Telegram.send_video = lambda self, p, caption="", admin_only=False: sent["video"].append((p, caption))
tgmod.Telegram.broadcast_sync = lambda self, text: sent["text"].append((text, "sync"))

import argus.loop as loop   # config o'zgartirilgandan KEYIN import qilinadi
t0 = time.time()
try:
    rc = loop.main()
except KeyboardInterrupt:
    rc = "interrupt(klip tugadi)"
dt = time.time() - t0
print("SMOKE: rc=%s | %.1f s | matn=%d rasm=%d video=%d" % (rc, dt, len(sent["text"]), len(sent["photo"]), len(sent["video"])))
for t, a in sent["text"][:8]:
    print("  MATN:", t.split("\n")[0][:80], "| admin_only=%s" % a)
for p, c in sent["photo"][:4]:
    print("  RASM:", os.path.basename(p), "|", c.split("\n")[0][:60])
hello = any("ARGUS AI ulandi" in t for t, _ in sent["text"])
note = any("YANGILANDI (deploy)" in t for t, _ in sent["text"])
print("ulanish xabari:", hello, "| deploy xabari:", note, "| deploy fayli o'chirildi:", not os.path.exists(config.DEPLOY_NOTE_FILE))
print("SMOKE TEST", "OK" if (hello and note) else "FAIL")
