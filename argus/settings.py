# -*- coding: utf-8 -*-
"""Sozlamalar + config'da bo'lmasa ishlaydigan standart qiymatlar.

Barcha modullar `from argus.settings import *` qiladi. Lokdagi config.py
stoldagidan farq qilishi mumkin (unga faqat blok qo'shib boriladi), shuning
uchun yangi kalitlar shu yerda standart qiymat bilan ta'minlanadi.
"""
import os

from config import *   # noqa: F401,F403

# Tamper: yorug'lik EMA'dan shuncha keskin tushsa (va qorong'i bo'lsa) -> yopilish
try:
    TAMPER_DROP
except NameError:
    TAMPER_DROP = 40.0
try:
    TAMPER_EMA_ALPHA
except NameError:
    TAMPER_EMA_ALPHA = 0.02   # ~3 s vaqt doimiysi @18 FPS
try:
    TAMPER_DROP_MIN
except NameError:
    TAMPER_DROP_MIN = 15.0    # keskin tushish: eng kam birlik (xira kabina)
try:
    TAMPER_DROP_FRAC
except NameError:
    TAMPER_DROP_FRAC = 0.5    # keskin tushish: EMA ning ulushi
try:
    TAMPER_DETAIL_REF
except NameError:
    TAMPER_DETAIL_REF = 60.0  # shu yorug'likdan past bo'lsa tafsilot ostonasi proporsional kamayadi
# Ko'z yumuqligini blendshape bilan tasdiqlash (argus/detect/eyes.py)
try:
    EYE_BLINK_CONFIRM
except NameError:
    EYE_BLINK_CONFIRM = True
try:
    EYE_BLINK_BS_MIN
except NameError:
    EYE_BLINK_BS_MIN = 0.7    # eyeBlink (3 kadr mediana) shundan past -> "yumuq" EMAS
try:
    EYE_FACE_CUT_UNRELIABLE
except NameError:
    EYE_FACE_CUT_UNRELIABLE = True   # yuz kadr chetida kesilgan -> ko'z o'lchovi ishonchsiz
try:
    PERCLOS_MIN_SAMPLES
except NameError:
    PERCLOS_MIN_SAMPLES = 300  # oynada kamida shuncha yuzli kadr bo'lmasa PERCLOS jim
# To'xtagan poyezdda buzilishlar FAQAT adminning botiga boradi (guruh va sayt EMAS)
try:
    STOPPED_ADMIN_ONLY
except NameError:
    STOPPED_ADMIN_ONLY = True
# Deploy'dan keyin bir marta yuboriladigan xabar fayli (deploy skripti yozadi)
try:
    DEPLOY_NOTE_FILE
except NameError:
    DEPLOY_NOTE_FILE = os.path.join(HERE, "deploy_note.txt")
# O'rganilgan o'rindiq ROI fayli (tunda yuzni topish uchun, reverify.FaceRecover)
try:
    SEAT_ROI_FILE
except NameError:
    SEAT_ROI_FILE = os.path.join(HERE, "seat_roi.json")
# Bir turdagi buzilish shu s ichida qaytsa — o'sha epizod davom etadi
try:
    INCIDENT_REJOIN_SEC
except NameError:
    INCIDENT_REJOIN_SEC = 120.0
