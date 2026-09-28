# -*- coding: utf-8 -*-
"""EpisodeTracker (argus/episodes.py) — soxta Telegram/sayt/yozuvchi bilan.
Tekshiradi: pirpiragan 'yuz' -> 1 epizod (1 matn, 1 rasm, 1 video, 1 tugadi);
to'xtaganda admin_only va saytga yo'q; klip bir UID ga bir marta.
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); os.chdir(ROOT)

from argus.settings import *   # noqa
from argus.context import RunContext
from argus.episodes import EpisodeTracker


class FakeTg:
    ok = True
    def __init__(self): self.text = []; self.photo = []; self.video = []; self.outbox = []
    def send(self, t, admin_only=False): self.text.append((t, admin_only))
    def send_photo(self, p, caption="", admin_only=False): self.photo.append((p, admin_only))
    def send_video(self, p, caption="", admin_only=False): self.video.append((p, admin_only))


class FakeWeb:
    ok = True; outbox = None
    def __init__(self): self.calls = []
    def send_incident(self, tag, label, **kw): self.calls.append((tag, kw.get("uid"), kw.get("detail")))


class FakeRec:
    def __init__(self): self.path = None; self.on_clip = None; self.n = 0
    def snapshot(self, ev): self.n += 1; return "snap_%d.jpg" % self.n


class FakeDay:
    def __init__(self): self.inc = []
    def add_incident(self, t): self.inc.append(t)
    def save(self, force=False): pass


def run(pattern, fps=18.0, stopped=False):
    """pattern: [(davomiylik_s, rep_active_set)]"""
    tg, web, rec, day = FakeTg(), FakeWeb(), FakeRec(), FakeDay()
    ctx = RunContext("Lok-TEST"); ctx.stopped_route = stopped
    ep = EpisodeTracker(tg, web, None, rec, day, ctx)
    describe = lambda tag, now, fr: "\nYuz ko'rinmagan: 4.7 s"
    now = 0.0; clips = []; closed = []
    for dur, rep in pattern:
        for _ in range(int(dur * fps)):
            now += 1.0 / fps
            ep.update(set(rep), now, describe, None)
            # haqiqiy recorder: rep faol bo'lganda klip ochiq; bo'sh bo'lsa (POST dan
            # keyin) yopiladi -> keyingi faollikda YANGI fayl ochiladi
            if rep and rec.path is None:
                rec.path = "rec_%d.mp4" % len(clips); clips.append(rec.path)
            ep.attach_media(lambda: "EV", set(rep), now)
            if not rep and rec.path is not None:
                closed.append(rec.path); rec.path = None
    # yopilgan kliplar -> on_clip (ochiq qolgani ham)
    for p in closed + ([rec.path] if rec.path else []):
        rec.on_clip(p)
    return tg, web, day, ep, clips


# 1) pirpirash: 8 x (6 s yuz yo'q, 2 s bor) + 180 s tinch
pat = [(6, {"yuz"}), (2, set())] * 8 + [(180, set())]
tg, web, day, ep, clips = run(pat)
uids = {u for _, u, _ in web.calls if u}
print("pirpirash: matn=%d rasm=%d video=%d tugadi=%d | sayt=%d | uid=%d | klip=%d (yozilgan)" % (
    sum(1 for t, _ in tg.text if "Buzilish" in t), len(tg.photo), len(tg.video),
    sum(1 for t, _ in tg.text if "Tugadi" in t), len(web.calls), len(uids), len(clips)))
assert sum(1 for t, _ in tg.text if "Buzilish" in t) == 1
assert len(tg.photo) == 1 and len(tg.video) == 1 and len(uids) == 1
assert sum(1 for t, _ in tg.text if "Tugadi" in t) == 1
end = [t for t, _ in tg.text if "Tugadi" in t][0]
assert "1 daq" in end or "62" in end or "1.0" in end, end   # davomiylik ~62 s (8*8-2), ushlab turish oynasisiz
assert day.inc == ["yuz"]
assert len(clips) == 8, len(clips)     # 8 ta klip yozildi, faqat 1 tasi yuborildi

# 2) ikki alohida hodisa (orasi 3 daq) -> 2 epizod, 2 rasm, 2 video
tg, web, day, ep, clips = run([(10, {"yuz"}), (180, set()), (10, {"yuz"}), (180, set())])
assert len(tg.photo) == 2 and len(tg.video) == 2 and day.inc == ["yuz", "yuz"]
print("alohida: rasm=%d video=%d OK" % (len(tg.photo), len(tg.video)))

# 3) to'xtagan: hammasi admin_only, saytga hech narsa
tg, web, day, ep, clips = run([(10, {"uyqu"}), (180, set())], stopped=True)
assert all(a for _, a in tg.text) and all(a for _, a in tg.photo) and all(a for _, a in tg.video)
assert web.calls == []
print("to'xtagan: admin_only=%d xabar, sayt=%d OK" % (len(tg.text) + len(tg.photo) + len(tg.video), len(web.calls)))

# 4) qisqa epizod (< INCIDENT_END_MIN) -> tugadi xabari yo'q
tg, web, day, ep, clips = run([(5, {"esnash"}), (180, set())])
assert not any("Tugadi" in t for t, _ in tg.text)
print("qisqa epizod: tugadi yo'q OK")
print("EPISODES TEST OK")
