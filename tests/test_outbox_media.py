# -*- coding: utf-8 -*-
"""Telegram navbati: tarmoq xatosida rasm/video TASHLANMAYDI (24 soatgacha),
API xatosida 6 urinishdan keyin tashlanadi; matn hech qachon tashlanmaydi."""
import os, sys, threading, time, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); os.chdir(ROOT)
import argus.net.telegram as T
import requests
def _fake_sleep(s):
    # kutishlarni o'chiramiz; navbat bo'sh bo'lsa sikldan chiqamiz
    if not tg.outbox:
        raise KeyboardInterrupt
time.sleep = _fake_sleep
tg = T.Telegram("0:x", "1", enabled=False)
tg.ok = True; tg.base = "http://x"; tg.approved = {"1"}; tg._olock = threading.Lock(); tg.outbox = []; tg._save_outbox = lambda: None
open("tests/_p.jpg", "wb").write(b"x")
def loop_once():
    # _outbox_loop ning bitta iteratsiyasi (while True ni sindirish uchun istisno bilan)
    calls = {"n": 0}
    def deliver(item):
        calls["n"] += 1
        if calls["n"] > 40: raise KeyboardInterrupt
        raise mode["exc"]
    tg._deliver = deliver
    try: tg._outbox_loop()
    except KeyboardInterrupt: pass
    return calls["n"]
# 1) tarmoq xatosi: 40 urinishdan keyin ham rasm navbatda
mode = {"exc": requests.ConnectionError("no net")}
tg.outbox = [{"kind": "photo", "path": "tests/_p.jpg", "caption": "", "ts": time.time()}]
loop_once(); print("tarmoq xatosi 40 urinish: navbatda=%d net_fail=%s" % (len(tg.outbox), tg.outbox[0].get("net_fail") if tg.outbox else None))
assert len(tg.outbox) == 1
# 2) 24 soatdan eski media tarmoq xatosida tashlanadi
tg.outbox = [{"kind": "photo", "path": "tests/_p.jpg", "caption": "", "ts": time.time() - 90000}]
loop_once(); print("eski (25 soat) media: navbatda=%d" % len(tg.outbox)); assert len(tg.outbox) == 0
# 3) API xatosi: 6 urinishdan keyin media tashlanadi
mode = {"exc": RuntimeError("telegram 400")}
tg.outbox = [{"kind": "video", "path": "tests/_p.jpg", "caption": "", "ts": time.time()}]
loop_once(); print("API xatosi: navbatda=%d" % len(tg.outbox)); assert len(tg.outbox) == 0
# 4) matn tarmoq xatosida ham, API xatosida ham tashlanmaydi
for exc in (requests.Timeout("t"), RuntimeError("telegram 500")):
    mode = {"exc": exc}; tg.outbox = [{"kind": "text", "text": "hi", "ts": time.time()}]
    loop_once(); assert len(tg.outbox) == 1
print("matn saqlanadi OK"); os.remove("tests/_p.jpg")
print("OUTBOX MEDIA TEST OK")
