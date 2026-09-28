# -*- coding: utf-8 -*-
"""Ekranga chizish — HUD.

Matn OpenCV ning Hershey shriftlari bilan emas, Pillow orqali haqiqiy
TrueType shrift bilan chiziladi. Sabab:
  * Hershey shriftida apostrof ("Ko'z", "YO'Q") va o'zbek harflari qo'pol
    chiqadi, harf oralig'i notekis;
  * qalinlik faqat butun piksel bo'ladi, shuning uchun ilgari matnni ikki
    marta (qora kontur 3 px + rangli 1 px) chizishga to'g'ri kelardi —
    qora versiya kengroq bo'lgani uchun chetidan chiqib, "ustma-ust
    chizilgandek" ko'rinardi.

Tezligi o'lchangan: butun panel ~0.5 ms, ya'ni 19 FPS dagi 53 ms lik
kadr byudjetining 1% i.
"""

import os
import math
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from config import *


# ── Ranglar (RGBA) ────────────────────────────────────────────────────
BG        = (16, 17, 20, 214)      # panel foni
BG_HEAD   = (24, 26, 30, 230)
LINE      = (255, 255, 255, 26)    # qatorlar orasidagi ajratgich
BORDER    = (255, 255, 255, 46)
LABEL     = (176, 180, 190, 255)
VALUE     = (240, 242, 246, 255)
ACCENT    = (86, 190, 255, 255)    # ko'k — sarlavha
OK        = (72, 214, 128, 255)    # yashil — normal
BAD       = (255, 74, 74, 255)     # qizil — buzilish
IDLE      = (120, 124, 132, 255)   # kulrang — o'lchanmayapti
WHITE     = (255, 255, 255, 255)
DECOR     = (255, 255, 255, 64)    # burchak ramkalari, o'lchov chiziqchalari


_FDIR = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
_CACHE = {}


def _font(size, bold=False, semi=False):
    key = (size, bold, semi)
    if key not in _CACHE:
        name = "segoeuib.ttf" if bold else ("seguisb.ttf" if semi else "segoeui.ttf")
        path = os.path.join(_FDIR, name)
        try:
            _CACHE[key] = ImageFont.truetype(path, size)
        except Exception:
            _CACHE[key] = ImageFont.load_default()
    return _CACHE[key]


def _tw(d, s, f):
    return d.textlength(s, font=f)


# Chizilgan qismlar KESHLANADI. Panel mazmuni deyarli o'zgarmaydi, uni
# har kadrda qaytadan chizish mini PC da 16.5 ms turardi — kadr byudjetining
# uchdan biri. Endi faqat mazmun o'zgarganda qayta chiziladi.
_RCACHE = {}
_RMAX = 32


def _prep(im):
    """PIL rasmni tayyor ikki qismga ajratadi: oldindan ko'paytirilgan rang
    va teskari alfa. Shundan keyin har kadrda faqat ko'paytirish+qo'shish
    qoladi va u OpenCV ning SIMD yo'li bilan bajariladi."""
    a = np.array(im)
    alpha = a[:, :, 3:4].astype(np.float32) / 255.0
    bgr = a[:, :, 2::-1].astype(np.float32)
    pre = (bgr * alpha).astype(np.uint8)
    inv = np.ascontiguousarray(np.repeat(1.0 - alpha, 3, axis=2).astype(np.float32))
    return pre, inv


def _cached(key, build):
    c = _RCACHE.get(key)
    if c is None:
        if len(_RCACHE) > _RMAX:
            _RCACHE.clear()
        c = _prep(build())
        _RCACHE[key] = c
    return c


def _paste(frame, cached, x, y):
    pre, inv = cached
    h, w = pre.shape[:2]
    H, W = frame.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sp = pre[y0 - y:y1 - y, x0 - x:x1 - x]
    si = inv[y0 - y:y1 - y, x0 - x:x1 - x]
    roi = frame[y0:y1, x0:x1]
    cv2.add(sp, cv2.multiply(roi, si, dtype=cv2.CV_8U), dst=roi)


def _blit(frame, rgba, x, y):
    """RGBA rasmni BGR kadrga alfa bilan qo'yadi (chetidan chiqsa kesadi)."""
    h, w = rgba.shape[:2]
    H, W = frame.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(W, x + w), min(H, y + h)
    if x1 <= x0 or y1 <= y0:
        return
    sub = rgba[y0 - y:y1 - y, x0 - x:x1 - x]
    roi = frame[y0:y1, x0:x1]
    a = sub[:, :, 3:4].astype(np.float32) / 255.0
    rgb = sub[:, :, 2::-1].astype(np.float32)          # RGB -> BGR
    roi[:] = (rgb * a + roi.astype(np.float32) * (1.0 - a)).astype(np.uint8)


# ── Belgilar (20x20 katakda chiziladi) ────────────────────────────────
def _icon(d, name, x, y, col, s=18):
    """Oddiy vektor belgilar. x,y — katakning chap-yuqori burchagi."""
    cx, cy = x + s / 2, y + s / 2
    w = 1.6
    if name == "eye":
        d.ellipse([x, cy - s*0.28, x + s, cy + s*0.28], outline=col, width=2)
        d.ellipse([cx - s*0.13, cy - s*0.13, cx + s*0.13, cy + s*0.13], fill=col)
    elif name == "eye_closed":
        d.arc([x, cy - s*0.34, x + s, cy + s*0.30], 200, 340, fill=col, width=2)
        for k in (-0.34, 0.0, 0.34):
            d.line([cx + s*k, cy + s*0.10, cx + s*k*1.25, cy + s*0.30], fill=col, width=2)
    elif name == "pulse":
        p = [(x, cy), (x+s*0.25, cy), (x+s*0.38, cy-s*0.32), (x+s*0.52, cy+s*0.30),
             (x+s*0.66, cy), (x+s, cy)]
        d.line(p, fill=col, width=2, joint="curve")
    elif name == "gauge":
        d.arc([x, y + s*0.10, x + s, y + s*1.05], 180, 360, fill=col, width=2)
        d.line([cx, cy + s*0.22, cx + s*0.28, cy - s*0.14], fill=col, width=2)
    elif name == "mouth":
        d.arc([x, cy - s*0.36, x + s, cy + s*0.16], 180, 360, fill=col, width=2)
        d.arc([x, cy - s*0.16, x + s, cy + s*0.36], 0, 180, fill=col, width=2)
    elif name == "target":
        d.ellipse([x + s*0.22, y + s*0.22, x + s*0.78, y + s*0.78], outline=col, width=2)
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            d.line([cx + dx*s*0.42, cy + dy*s*0.42, cx + dx*s*0.58, cy + dy*s*0.58],
                   fill=col, width=2)
    elif name == "face":
        r = s*0.30
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            d.line([cx + sx*s*0.5, cy + sy*s*0.28, cx + sx*s*0.5, cy + sy*s*0.5],
                   fill=col, width=2)
            d.line([cx + sx*s*0.28, cy + sy*s*0.5, cx + sx*s*0.5, cy + sy*s*0.5],
                   fill=col, width=2)
        d.ellipse([cx - r*0.6, cy - r*0.6, cx + r*0.6, cy + r*0.6], outline=col, width=2)
    elif name == "smile":
        d.ellipse([x, y, x + s, y + s], outline=col, width=2)
        d.ellipse([cx - s*0.24, cy - s*0.18, cx - s*0.10, cy - s*0.04], fill=col)
        d.ellipse([cx + s*0.10, cy - s*0.18, cx + s*0.24, cy - s*0.04], fill=col)
        d.arc([cx - s*0.28, cy - s*0.06, cx + s*0.28, cy + s*0.30], 0, 180, fill=col, width=2)
    elif name == "phone":
        d.rounded_rectangle([cx - s*0.28, y + s*0.04, cx + s*0.28, y + s*0.96],
                            radius=3, outline=col, width=2)
        d.line([cx - s*0.08, y + s*0.84, cx + s*0.08, y + s*0.84], fill=col, width=2)
    elif name == "belt":
        d.line([x + s*0.14, y + s*0.06, x + s*0.86, y + s*0.94], fill=col, width=2)
        d.rounded_rectangle([cx - s*0.16, cy - s*0.10, cx + s*0.22, cy + s*0.26],
                            radius=2, outline=col, width=2)
    elif name == "camera":
        d.rounded_rectangle([x, y + s*0.22, x + s*0.72, y + s*0.82], radius=3,
                            outline=col, width=2)
        d.polygon([(x + s*0.78, y + s*0.36), (x + s, y + s*0.22),
                   (x + s, y + s*0.82), (x + s*0.78, y + s*0.68)], outline=col)
    elif name == "clock":
        d.ellipse([x, y, x + s, y + s], outline=col, width=2)
        d.line([cx, cy, cx, cy - s*0.28], fill=col, width=2)
        d.line([cx, cy, cx + s*0.20, cy], fill=col, width=2)
    else:
        d.ellipse([x + s*0.3, y + s*0.3, x + s*0.7, y + s*0.7], outline=col, width=2)


ICON = {"Ko'z": "eye", "PERCLOS": "eye_closed", "Pirpirash": "pulse",
        "Tezlik": "gauge", "Og'iz": "mouth", "Qarash": "target",
        "Yuz": "face", "Kayfiyat": "smile", "Telefon": "phone",
        "Kamar": "belt", "Kamera": "camera"}


# ── Asosiy panel ──────────────────────────────────────────────────────
def _build_panel(title, device, rows, stamp):
    fl, fv = _font(15), _font(15, semi=True)
    ft, fd = _font(19, semi=True), _font(12)

    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    lab_w = max([_tw(probe, r[0], fl) for r in rows] + [0])
    val_w = max([_tw(probe, str(r[1]), fv) for r in rows] + [0])
    head_w = _tw(probe, title, ft) + _tw(probe, "  |  " + device, ft) + 110

    pad, rh = 18, 33
    icon_x, lab_x = pad + 4, pad + 4 + 26
    dot_x = lab_x + lab_w + 20
    val_x = dot_x + 20
    w = int(max(val_x + val_w + pad, head_w + pad, 330))
    h = int(60 + rh * len(rows) + 12)

    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=16, fill=BG, outline=BORDER, width=1)
    d.rounded_rectangle([0, 0, w - 1, 52], radius=16, fill=BG_HEAD)
    d.rectangle([0, 36, w - 1, 52], fill=BG_HEAD)
    d.line([pad, 52, w - pad, 52], fill=LINE, width=1)

    d.text((pad + 2, 16), title, font=ft, fill=ACCENT)
    tx = pad + 2 + _tw(d, title, ft)
    d.line([tx + 10, 17, tx + 10, 35], fill=(255, 255, 255, 60), width=1)
    d.text((tx + 20, 16), device, font=ft, fill=(214, 218, 226, 255))

    if stamp:
        _icon(d, "clock", w - pad - 84, 17, (150, 154, 164, 255), 15)
        for i, s in enumerate(stamp):
            d.text((w - pad - 62, 13 + i * 15), s, font=fd, fill=(158, 162, 172, 255))

    for i, r in enumerate(rows):
        label, value, ok = r[0], r[1], r[2]
        idle = r[3] if len(r) > 3 else False
        ry = 60 + i * rh
        if not ok and not idle:                      # buzilgan qator ajratiladi
            d.rounded_rectangle([pad - 10, ry - 2, w - pad + 6, ry + rh - 8],
                                radius=8, fill=(255, 48, 48, 30),
                                outline=(255, 90, 90, 150), width=1)
        elif i:
            d.line([pad + 2, ry - 3, w - pad - 2, ry - 3], fill=LINE, width=1)

        col = IDLE if idle else (OK if ok else BAD)
        lab_col = (236, 206, 206, 255) if (not ok and not idle) else LABEL
        _icon(d, ICON.get(label, "dot"), icon_x, ry + 3,
              (255, 150, 150, 255) if (not ok and not idle) else (168, 172, 182, 255))
        d.text((lab_x, ry + 3), label, font=fl, fill=lab_col)
        cy = ry + 12
        d.ellipse([dot_x, cy - 4, dot_x + 8, cy + 4], fill=col)
        txt = str(value)
        if txt == "-" and ok:
            txt = "Normal"
        d.text((val_x, ry + 3), txt, font=fv,
               fill=VALUE if (ok or idle) else (255, 138, 138, 255))

    return im


def info_panel(frame, x, y, title, device, rows, stamp=None):
    """Sarlavha + qatorlar. rows: (yorliq, qiymat, ok[, idle])."""
    key = ("panel", title, device, tuple(tuple(r) for r in rows), stamp)
    c = _cached(key, lambda: _build_panel(title, device, rows, stamp))
    _paste(frame, c, x, y)
    return c[0].shape[1], c[0].shape[0]


# ── Yuqoridagi ogohlantirish ──────────────────────────────────────────
def alert_banner(frame, x, y, msg, now, crit=False):
    """Qizil yumaloq quti + ogohlantirish belgisi. Pulsatsiya qiladi.

    Pulsatsiya 8 bosqichga bo'lingan — shunda har bosqich bir marta
    chizilib keshga tushadi, ko'z esa farqni sezmaydi."""
    step = int((0.5 + 0.5 * math.sin(now * 5.0)) * 7.999)
    c = _cached(("alert", msg, crit, step), lambda: _build_alert(msg, step, crit))
    _paste(frame, c, x, y)


def _build_alert(msg, step, crit):
    f = _font(24, bold=True)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w = int(_tw(probe, msg, f) + 104)
    h = 62
    im = Image.new("RGBA", (w + 14, h + 14), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    p = 0.55 + 0.45 * (step / 7.0)
    base = (214, 26, 32) if crit else (196, 40, 40)
    d.rounded_rectangle([7, 7, w, h], radius=12,
                        fill=base + (int(214 * p),),
                        outline=(255, 120, 120, int(210 * p)), width=2)
    # ogohlantirish uchburchagi
    d.rounded_rectangle([20, 18, 62, 52], radius=8, fill=(255, 255, 255, 34))
    d.polygon([(41, 22), (59, 49), (23, 49)], outline=WHITE, width=2)
    d.line([41, 30, 41, 40], fill=WHITE, width=2)
    d.ellipse([39.5, 43, 42.5, 46], fill=WHITE)
    d.text((80, 17), msg, font=f, fill=WHITE)
    return im


# ── Yuqori o'ngdagi belgilar ──────────────────────────────────────────
def chips(frame, W, fps, recording, now):
    # FPS ni 0.5 gacha yaxlitlaymiz — har kichik o'zgarishda qayta
    # chizilmasin (ekranda farqi bilinmaydi, keshga foydasi katta).
    step = int((0.5 + 0.5 * math.sin(now * 4.0)) * 7.999) if recording else 0
    c = _cached(("chips", round(fps * 2) / 2.0, recording, step),
                lambda: _build_chips(fps, recording, step))
    _paste(frame, c, W - c[0].shape[1] - 18, 14)


def _build_chips(fps, recording, step):
    f = _font(15, semi=True)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    items = []
    if recording:
        items.append(("REC", True))
    items.append((f"FPS {fps:.1f}", False))
    total = sum(int(_tw(probe, s, f)) + (46 if r else 30) for s, r in items) + 10 * (len(items) - 1)
    im = Image.new("RGBA", (total + 4, 44), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cx = 0
    for s, rec in items:
        cw = int(_tw(d, s, f)) + (46 if rec else 30)
        d.rounded_rectangle([cx, 6, cx + cw, 40], radius=10,
                            fill=(18, 19, 23, 210), outline=BORDER, width=1)
        tx = cx + 15
        if rec:
            p = 0.4 + 0.6 * (step / 7.0)
            d.ellipse([tx, 18, tx + 11, 29], fill=(255, 60, 60, int(255 * p)))
            tx += 20
        d.text((tx, 13), s, font=f, fill=(228, 232, 240, 255))
        cx += cw + 10
    return im


# ── Kadr bezaklari ────────────────────────────────────────────────────
def frame_decor(frame):
    """Burchak ramkalari va chekkadagi o'lchov chiziqchalari."""
    H, W = frame.shape[:2]
    # Ilgari butun kadr nusxalanib addWeighted qilinardi (3.2 ms). Chiziqlar
    # kam, shuning uchun to'g'ridan-to'g'ri o'rtacha rang bilan chizamiz.
    ov = frame
    c, L, m = (168, 168, 170), 46, 14
    for sx, sy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
        x = m if sx > 0 else W - m
        y = m if sy > 0 else H - m
        cv2.line(ov, (x, y), (x + sx * L, y), c, 2, cv2.LINE_AA)
        cv2.line(ov, (x, y), (x, y + sy * L), c, 2, cv2.LINE_AA)
    for i in range(10):                       # chap chekka
        yy = int(H * (0.14 + i * 0.075))
        cv2.line(ov, (8, yy), (8 + (16 if i % 5 == 0 else 9), yy), c, 1, cv2.LINE_AA)
    for i in range(22):                       # past chekka
        xx = int(W * (0.34 + i * 0.014))
        cv2.line(ov, (xx, H - 9), (xx, H - 9 - (12 if i % 5 == 0 else 6)), c, 1, cv2.LINE_AA)


def _bracket(d, w, h, m, L, R, col, width):
    """To'rtta burchak - to'g'ri chiziq + yumaloq egri. (m - nur uchun chekka)"""
    x1, y1, x2, y2 = m, m, m + w, m + h
    for (px, py, sx, sy, a0) in ((x1, y1, 1, 1, 180), (x2, y1, -1, 1, 270),
                                 (x2, y2, -1, -1, 0), (x1, y2, 1, -1, 90)):
        d.line([px + sx*R, py, px + sx*L, py], fill=col, width=width)
        d.line([px, py + sy*R, px, py + sy*L], fill=col, width=width)
        bx = sorted([px, px + sx*2*R]); by = sorted([py, py + sy*2*R])
        d.arc([bx[0], by[0], bx[1], by[1]], a0, a0 + 90, fill=col, width=width)


def _build_reticle(w, h, step):
    """Vizir tasviri. Faqat O'LCHAMGA bog'liq — shuning uchun keshlanadi."""
    m = 14                                   # nur uchun chekka
    im = Image.new("RGBA", (w + 2*m, h + 2*m), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    L = max(16, int(0.24 * min(w, h)))
    R = max(6, int(0.05 * min(w, h)))
    g = 0.55 + 0.45 * (step / 7.0)           # yumshoq "nafas"

    # Uch qatlam: keng va shaffof (nur) -> ingichka va yorqin (asosiy)
    _bracket(d, w, h, m, L, R, (72, 214, 128, int(26 * g)), 9)
    _bracket(d, w, h, m, L, R, (72, 214, 128, int(70 * g)), 5)
    _bracket(d, w, h, m, L, R, (150, 255, 190, 240), 2)

    # Markaz nishoni: to'rtta kichik chiziqcha, o'rtasi bo'sh
    cx, cy = m + w // 2, m + h // 2
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        d.line([cx + dx*5, cy + dy*5, cx + dx*11, cy + dy*11 if dy else cy],
               fill=(150, 255, 190, 150), width=1)
    d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(150, 255, 190, 200))
    return im


def face_reticle(frame, box, now=0.0):
    """Aniqlangan yuz atrofida vizir.

    Tasvir faqat qutining O'LCHAMIGA bog'liq, joyiga emas — shuning uchun
    o'lcham 8 pikselgacha yaxlitlanib keshlanadi va har kadrda qaytadan
    chizilmaydi."""
    if not box:
        return
    x1, y1, x2, y2 = [int(v) for v in box]
    pad = int(0.18 * max(1, x2 - x1))
    x1, y1, x2, y2 = x1 - pad, y1 - pad, x2 + pad, y2 + pad
    w, h = max(24, x2 - x1), max(24, y2 - y1)
    wq, hq = (w // 8) * 8, (h // 8) * 8       # kesh uchun yaxlitlash
    step = int((0.5 + 0.5 * math.sin(now * 2.2)) * 7.999)
    c = _cached(("ret", wq, hq, step), lambda: _build_reticle(wq, hq, step))
    _paste(frame, c, x1 - 14, y1 - 14)


# ── Aniqlangan obyekt qutisi ──────────────────────────────────────────
def draw_box(frame, bbox, color, label):
    x1, y1, x2, y2 = [int(v) for v in bbox]
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2, cv2.LINE_AA)
    f = _font(13, semi=True)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w = int(_tw(probe, label, f)) + 16
    im = Image.new("RGBA", (w, 24), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, w - 1, 23], radius=6,
                        fill=(color[2], color[1], color[0], 235))
    d.text((8, 3), label, font=f, fill=WHITE)
    _blit(frame, np.array(im), x1, max(0, y1 - 26))


# ── Eski nomlar (boshqa joyda ishlatilsa buzilmasin) ──────────────────
def text(frame, s, org, scale=0.6, color=(240, 240, 240), thick=1, shadow=False):
    cv2.putText(frame, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thick, cv2.LINE_AA)
