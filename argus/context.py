# -*- coding: utf-8 -*-
"""Ish vaqtida O'ZGARADIGAN umumiy holat — modullar orasida bitta obyekt.

Nega kerak: DEVICE_NAME GPS kelgach "Lokomotiv-2417" ga o'zgaradi. Har modul
`from config import *` bilan o'z NUSXASINI olgani uchun global o'zgaruvchi
orqali buni tarqatib bo'lmaydi — shuning uchun xabar tuzadigan barcha
joylar `ctx.device_name` dan o'qiydi.
"""


class RunContext:
    def __init__(self, device_name):
        self.device_name = device_name
        self.stopped_route = False   # True -> xabarlar faqat adminga, saytga yo'q
        self.W = 0                   # kadr o'lchami (birinchi kadrda to'ldiriladi)
        self.H = 0
