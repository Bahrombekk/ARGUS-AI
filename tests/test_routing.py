# -*- coding: utf-8 -*-
"""routing.stopped_route: to'xtagan / noma'lum -> faqat admin; harakatda -> guruh+sayt."""
import os, sys, types
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT); os.chdir(ROOT)
from argus import routing
def gps(speed, fresh, moving):
    g = types.SimpleNamespace(speed=speed); g.fix_fresh = lambda: fresh; g.is_moving = lambda: moving; return g
assert routing.stopped_route(None) is False                              # GPS o'chiq
assert routing.stopped_route(gps(60.0, True, True)) is False             # harakatda, yangi o'lchov -> guruh+sayt
assert routing.stopped_route(gps(0.0, True, False)) is True              # to'xtagan
assert routing.stopped_route(gps(None, False, True)) is True             # GPS javob yo'q (noma'lum=harakatda) -> faqat admin
assert routing.stopped_route(gps(0.0, False, True)) is True              # eski o'lchov (internet uzilgan) -> faqat admin
assert routing.gate_for_report(["yuz", "uyqu"], gps(0.0, False, True)) == ["yuz", "uyqu"]   # noma'lum: gate o'zgarmaydi (xavfsizlik)
assert routing.gate_for_report(["yuz", "uyqu"], gps(0.0, True, False)) == ["uyqu"]          # to'xtagan: yuz chiqariladi
print("ROUTING TEST OK")
