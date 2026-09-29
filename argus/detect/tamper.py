# -*- coding: utf-8 -*-
"""Kamera to'silishi (tamper) qarori — yorug'likka moslashuvchan.

Ikki belgi:
  1) TAFSILOT past (Laplacian dispersiyasi) — lekin faqat kadr yetarlicha
     yorug' bo'lganda hukm chiqariladi. Qorong'ida tafsilot tabiiy ravishda
     kamayadi: 2026-09-29 tunda yorug'lik 2-6 da tafsilot 14-20 (kabina
     shunchaki qorong'i, kamera ochiq) va yorug'lik 36 da tafsilot 18-19
     (haydovchi ko'rinib turibdi) — qat'iy 20 ostonasi 17 ta yolg'on
     "to'silgan" berdi. Endi ostona yorug'likka proporsional:
         ostona = TAMPER_DETAIL_VAR * min(1, yorug'lik / TAMPER_DETAIL_REF)
     va yorug'lik < TAMPER_DARK_MEAN bo'lsa tafsilot bo'yicha hukm YO'Q.
  2) KESKIN qorong'ilashish — yorug'lik EMA'dan birdan tushsa (qo'l/qopqoq
     lensni yopdi). Tushish ostonasi ham nisbiy: xira kabinada (EMA 36)
     40 birlik tushish bo'lishi mumkin emas, shuning uchun
         ostona = min(TAMPER_DROP, max(TAMPER_DROP_MIN, TAMPER_DROP_FRAC * EMA)).
     Yorug' kabinada bu avvalgidek 40.
"""


class TamperJudge:
    def __init__(self, detail_var, dark_mean, drop, drop_min, drop_frac,
                 detail_ref, ema_alpha):
        self.detail_var = float(detail_var)
        self.dark_mean = float(dark_mean)
        self.drop = float(drop)
        self.drop_min = float(drop_min)
        self.drop_frac = float(drop_frac)
        self.detail_ref = float(detail_ref)
        self.alpha = float(ema_alpha)
        self.ema = None           # yorug'lik EMA (~3 s @18 FPS)
        self.last_thr = None      # oxirgi tafsilot ostonasi (diagnostika)

    def update(self, mean_b, detail):
        """(blocked, sudden_dark, low_detail) — va EMA yangilanadi."""
        if self.ema is None:
            self.ema = mean_b
        drop_thr = min(self.drop, max(self.drop_min, self.drop_frac * self.ema))
        sudden_dark = ((self.ema - mean_b) > drop_thr) and (mean_b < self.dark_mean)
        if mean_b < self.dark_mean:
            low_detail = False           # qorong'i kabina — tafsilot ma'nosiz
            self.last_thr = 0.0
        else:
            thr = self.detail_var * min(1.0, mean_b / self.detail_ref)
            self.last_thr = thr
            low_detail = detail < thr
        blocked = low_detail or sudden_dark
        # sekin EMA: asta qorong'ilashish drop hisoblanmaydi
        self.ema += (mean_b - self.ema) * self.alpha
        return blocked, sudden_dark, low_detail
