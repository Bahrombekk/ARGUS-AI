# -*- coding: utf-8 -*-
"""ARGUS AI sozlamalari.

MUNDARIJA (bo'limlar shu tartibda):
  1. Yo'llar va qurilma identifikatori
  2. Funksiyalarni yoqish/o'chirish (ENABLE_*)
  3. Odam aniqlash, telefon modeli
  4. Uyqu: ko'z (EAR, eyeBlink), mikrouyqu, PERCLOS, pirpirash, silliqlash
  5. Esnash, chalg'ish, kamera to'silishi (tamper)
  6. Rasm/video yozuv, dataset
  7. GPS / lokomotiv, harakat qoidalari (GPS_GATED_TAGS, STOPPED_ADMIN_ONLY)
  8. Kayfiyat, Telegram (secrets.json), hisobotlar, sayt (webhook)
  9. Qayta tekshirish (CONFIRM), ruxsat vaqti (GRACE), epizod (REJOIN)
 10. device.json (IMEI, qurilma nomi), ko'p qurilma, tozalash
 11. config_local.py — QURILMAGA XOS qiymatlar (fayl oxirida yuklanadi)

QOIDA: bu fayl barcha qurilmalarda BIR XIL. Qurilmaga xos farqlar (masalan
lokda telefon/odam aniqlash o'chiq) `config_local.py` ga yoziladi — u
git'ga kirmaydi, namuna: config_local.example.py. Tokenlar: secrets.json.
"""
"""ARGUS AI — barcha sozlamalar shu yerda.

Modullar bu fayldan `from config import *` bilan o'qiydi.
"""
import io
import os
import json
import sys


if getattr(sys, "frozen", False):            # PyInstaller .exe — fayllar exe yonida
    HERE = os.path.dirname(sys.executable)
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(HERE, "audio")
MODEL_PATH = os.path.join(HERE, "models", "safedrive.pt")

CONF = 0.35                 # YOLO eng kam ishonch (sigaret qutisi ko'rinishi uchun past)
ALERT_COOLDOWN = 4.0        # bir hodisa qayta aytilishi orasidagi vaqt (s)

# ── Qurilma identifikatori (har lokomotiv/kabina uchun boshqacha) ──
DEVICE_NAME = "Lokomotiv-01"   # keyin har qurilmaga alohida nom beriladi
CAMERA_SCAN = 6             # ulangan kamerani topish uchun 0..CAMERA_SCAN-1 skanlanadi
HEADLESS = True            # monitor YO'Q (mini PC) — oynasiz, Telegram orqali boshqariladi.
                           # Lokal ekranli test uchun False qiling (oyna + s/r/t/q klaviatura).

# ── Funksiyalarni yoqish/o'chirish (ba'zi kontekstда ba'zilari kerak emas) ──
ENABLE_DROWSY   = True      # uyqu (ko'z yumilishi)
ENABLE_YAWN     = True      # esnash / charchoq
ENABLE_DISTRACT = True      # chalg'ish (boshqa yoqqa qarash)
ENABLE_PHONE    = True      # telefon
ENABLE_SMOKING  = False     # sigaret — ba'zilarga ruxsat, hozir O'CHIRILGAN
ENABLE_SEATBELT = True      # xavfsizlik kamari
ENABLE_TAMPER   = True      # kamera to'silishi (qorong'i / tafsilotsiz kadr)
# Yuz ko'rinmasligi. Kamera SOZ, kadr yorug', lekin yuz topilmayapti —
# demak haydovchi yuzini to'sgan, teskari burilgan yoki o'rinda yo'q.
# Bu MUHIM: yuz topilmasa uyqu va chalg'ish nazorati KO'R bo'lib qoladi,
# ya'ni yuzni to'sib uxlash bilan tizimni aldash mumkin edi.
ENABLE_NOFACE   = True
NOFACE_SEC      = 4.0       # shuncha s uzluksiz yuz yo'q → signal

# ── Odam bor-yo'qligi (person detection) ──
# Yuz topilmaganda IKKI xil holat bo'ladi va ularni ajratmasak bo'lmaydi:
#   odam BOR, yuzi yo'q → to'sgan/burilgan  → BUZILISH
#   odam YO'Q           → o'rnidan turgan   → bu RUXSAT ETILGAN, boshqa muddat
# Ajratmasak, qonuniy turib ketish ham "buzilish" bo'lib yolg'on signal berardi.
#
# TEZLIK: bu model FAQAT yuz topilmaganda ishlaydi. Mashinist joyida o'tirib,
# yuzi ko'rinib turgan normal holatda umuman chaqirilmaydi → FPS ga ta'siri yo'q.
ENABLE_PERSON   = True
PERSON_MODEL    = os.path.join(HERE, "models", "yolov8n.pt")

# ── Telefon uchun ALOHIDA model ──
# safedrive.pt qora stul suyanchig'ini telefon deb adashardi (o'z rasmlarimizda
# 31 ta telefonsiz kadrdan 5 tasida yolg'on signal - 16%). Alohida o'rgatilgan
# model o'sha kadrlarda conf=0.05 da ham hech narsa ko'rmaydi.
#
# TEZLIK: model har kadrda emas, sekundiga PHONE_MODEL_EVERY bo'yicha
# ishlaydi. PHONE_WINDOW=2.0 va PHONE_MIN=2 uchun 4 Hz yetarlidan ortiq
# (2 soniyada 8 namuna), lekin narxi har kadrda ishlatishdan ~4 barobar arzon.
ENABLE_PHONE_MODEL = True
PHONE_MODEL        = os.path.join(HERE, "models", "phone_v1.pt")   # eski (v1) — endi ishlatilmaydi
# v2 (2026-09-26): o'zimiz o'qitgan phone_argus.pt (Open Images "Mobile phone" +
# COCO "cell phone" ijobiy; krujka/pult/quloqchin/stasionar telefon qattiq negativ;
# o'z kadrlarimiz). O'LCHANDI (1616 kadr): haqiqiy telefon 0.73-0.89, 878 negativ
# kadrda eng yuqori ball < 0.30 -> ostona 0.50. Fayl bo'lmasa COCO yolov8n
# "cell phone" (klass 67, ostona PHONE_MODEL_CONF). imgsz 480 — 640 dan ~1.8x tez.
PHONE_MODEL_CUSTOM = os.path.join(HERE, "models", "phone_argus.pt")
PHONE_CUSTOM_CONF  = 0.50
PHONE_COCO_CLASS   = 67
PHONE_IMGSZ        = 480
# 0.25 sinov to'plamida 0 yolg'on signal bergan edi, lekin amalda QORA
# kiyimdagi odamda adashdi — o'rgatish ma'lumotida odam oq futbolkada edi.
# 0.40 ga ko'tarildi. Bu VAQTINCHALIK chora: ildiz sabab — model qorong'i
# shakllarni yetarli ko'rmagan. To'g'ri yechim kabinadan turli kiyim va
# yorug'likda kadr yig'ib qayta o'rgatish.
PHONE_MODEL_CONF   = 0.40
PHONE_MODEL_EVERY  = 0.5     # sekundiga 2 marta (telefon qo'lda uzoq ushlanadi; CPU tejash)
PERSON_CONF     = 0.35
PERSON_EVERY    = 0.5       # yuz yo'q paytida sekundiga ~2 marta tekshiriladi
ABSENT_SEC      = 12.0      # odam yo'q — shuncha s dan keyin xabar

# Debounce (yolg'on signalga qarshi) — sirpanuvchi oyna + minimal aniqlash soni
PHONE_WINDOW, PHONE_RATIO, PHONE_MIN = 2.0, 0.30, 2
SMOKE_WINDOW, SMOKE_RATIO, SMOKE_MIN = 2.0, 0.40, 3
BELT_WINDOW,  BELT_RATIO,  BELT_MIN  = 3.0, 0.50, 4
EYE_CLOSED_SEC = 2.0        # shuncha s uzluksiz yumuq -> TO'LIQ UYQU
# 1.2 s edi, MICROSLEEP_SEC esa 1.0 - orasi atigi 0.2 soniya. Natijada
# bitta yumilish ketma-ket IKKI xabar berardi (15:29:33 Mikrouyqu,
# 15:29:34 Uyqu). Endi 1.0 s da ogohlantirish, 2.0 s da kuchaytirilgan
# signal - haqiqiy zina. Xavfsizlik pasaymaydi: birinchi ovozli
# ogohlantirish baribir 1.0 soniyada chiqadi.

# ── Mikrouyqu ──
# Ilmiy ta'rif: 500 ms dan uzun ko'z yumilishi mikrouyqu hisoblanadi.
# EYE_CLOSED_SEC=1.2 bo'lgani uchun 0.5-1.2 s oralig'i SEZILMAY qolardi —
# aynan eng xavfli oraliq. 80 km/soatda 0.5 s = ~11 metr ko'r harakat.
ENABLE_MICROSLEEP = True
# Ilmiy ta'rif 0.5 s, lekin amalda juda sezgir chiqdi: pastga qaraganda
# EAR tushib, 3.5 daqiqada 11 ta yolg'on signal bergan edi. 0.8 s ga
# ko'tarildi — uyqu ostonasidan (1.2 s) hali ham past, ya'ni mikrouyqu
# alohida bosqich bo'lib qoladi, lekin qisqa tushishlar o'tkazib yuboriladi.
MICROSLEEP_SEC = 1.0        # shuncha s uzluksiz yumuq -> mikrouyqu
# 0.8 s hali ham sezgir edi: odam ko'zini bir ochib yumganda ham berardi.
# Odatiy pirpirash 0.1-0.4 s, charchagan odamda 0.8 s gacha cho'ziladi.
# 1.0 s har qanday pirpirashdan yuqorida turadi va tibbiy ta'rifga ham
# mos keladi (mikrouyqu odatda 1 s dan boshlanadi).

# ── Ko'z o'lchovining ishonchli burchagi ──
# Bosh pastga kuchli egilganda (masalan telefonga qarayotganda) kamera
# ko'zni yon/ustki tomondan ko'radi va EAR yolg'on "yumuq" qiymat beradi.
# Amalda bu jiddiy muammo bo'ldi: 10 daqiqada 35 ta "mikrouyqu" va 21 ta
# "uyqu" yozildi - odam shunchaki telefon ko'rib o'tirgan edi.
#
# Shunday paytda uyqu/mikrouyqu/PERCLOS O'LCHANMAYDI. Buning o'rniga
# "chalg'ish" signali ishlaydi - pastga qarash o'zi ham buzilish.
# Haqiqiy uyquchanlikda ko'z bosh egilishidan OLDIN yumiladi, shuning
# uchun asosiy holat baribir ushlanadi.
EYE_NOD_LIMIT = 22.0        # bazadan shuncha daraja pastga egilsa - ishonchsiz
# Ko'z yumuqligini MediaPipe eyeBlink blendshape bilan TASDIQLASH.
# O'lchov 2026-09-26 (lok, 42 ta yolg'on uyqu/mikrouyqu/PERCLOS xabari):
# kameraga yaqin turib pastga qaraganda EAR 0.09-0.18 ("yumuq"), lekin
# eyeBlink 0.36-0.55. Haqiqiy yumuqda (stol yozuvi) eyeBlink 0.77.
EYE_BLINK_CONFIRM = True
# 2026-09-26 kunduzgi o'lchov: stolga pastga qarab o'tirgan haydovchida (0 km/s)
# eyeBlink 0.60-0.69 bilan 20+ mikrouyqu/uyqu ketdi; haqiqiy yumuqda 0.77-0.80.
EYE_BLINK_BS_MIN = 0.6      # 3 kadr medianasi shundan past bo'lsa "yumuq" hisoblanmaydi (0.7 haqiqiy yumuqni 0.66-0.69 da o'tkazib yubordi; pastga qarash <= 0.54, zoom tekshiruvi qo'shildi)
EYE_FACE_CUT_UNRELIABLE = True   # yuz kadr chetida kesilgan -> ko'z o'lchovi ishonchsiz
# Ko'z ZOOM — "ikkinchi fikr" (2026-09-29): ko'z EYE_ZOOM_AFTER s yumuq deb
# topilgach yuz atrofi kesib olinib (EYE_ZOOM_MARGIN), kamida EYE_ZOOM_MIN_PX
# balandlikka kattalashtirilib landmarker qayta ishga tushiriladi. Uyqu faqat
# ikkala o'lchov (to'liq kadr + zoom) "yumuq" desa hisoblanadi. Uzoq/xira
# yuzda ko'z 15-20 piksel bo'lib EAR shovqinli — zoom shuni tuzatadi.
# Xarajat faqat nomzod kadrlarda (~8 ms). Zoomda yuz topilmasa — veto yo'q.
EYE_ZOOM = True
EYE_ZOOM_AFTER = 0.5
EYE_ZOOM_MARGIN = 1.6
EYE_ZOOM_MIN_PX = 256

# ── PERCLOS — uyquchanlikning jahon standarti ──
# 1994-yildan beri qo'llaniladi, FHWA/NHTSA uni real vaqtdagi eng ishonchli
# ko'rsatkich deb tan oladi. Ta'rifi: oynadagi vaqtning necha ulushida ko'z
# yumuq turgani (yarim yumuq = 0.5 ball).
#
# Nega UZLUKSIZ yumilish yetarli emas: charchagan odam ko'pincha uzoq
# yummaydi, balki TEZ-TEZ va uzunroq pirpiraydi. Har biri 600 ms dan 20 ta
# yumilish - aniq uyquchanlik, lekin uzluksiz osona buni sezmaydi.
ENABLE_PERCLOS = True
PERCLOS_WINDOW = 60.0       # sirpanuvchi oyna (s)
PERCLOS_WARN = 0.35         # uyquchanlik belgisi
# 0.20 edi - juda past. O'lchandi: UYG'OQ odam klaviaturada ishlaganda
# jonli tizimda 32% gacha chiqdi (60 s oyna). Qisqa kliplarda 12-14%.
# Sabab: pastga qaraganda qovoq tushadi va 'yarim' holat yig'iladi.
# Haqiqiy uyquchanlikda qiymat 50%% dan oshadi, shuning uchun 0.35
# xavfsizlikni pasaytirmaydi.
PERCLOS_CRIT = 0.50         # kritik uyquchanlik
PERCLOS_HOLD = 10.0         # ostona shuncha s saqlanib tursin
PERCLOS_MIN_SAMPLES = 300   # oynada kamida shuncha yuzli kadr (60 s @15 FPS = 900); kam bo'lsa jim
# 3 s edi: qiymat chegara atrofida tebranganda signal yonib-o'chardi.
                            # — aks holda bir lahzalik sakrash ham signal berardi

# ── Pirpirash davomiyligi ──
# Tinch odamda <200 ms, uyqusizlikda >500 ms ga cho'ziladi. PERCLOS bilan
# birga mikrouyquni oldindan bashorat qiluvchi eng yaxshi ikki ko'rsatkich.
ENABLE_BLINK = True
# ── Ko'z holatini silliqlash ───────────────────────────────────────────
# 2026-09-24, 4.7 s lik yozuvda o'lchandi: 88 kadrdan 2 tasi chetlagan
# (EAR 0.30 -> 0.198 -> 0.305 va 0.34 -> 0.233 -> 0.30). Ikkalasi ham
# BITTA kadr, ya'ni ~54 ms. Haqiqiy pirpirash 100-400 ms = 2-7 kadr.
# Demak bu ko'z yumish emas, landmark chayqalishi edi — lekin PERCLOS ga,
# pirpirash o'lchoviga va mikrouyquga to'liq kirib borardi.
# 3 kadrlik MEDIANA bunday yakka sakrashni o'tkazmaydi, ketma-ket 2+ kadr
# davom etgan haqiqiy yumilishni esa saqlaydi.
# ── Ko'z o'lchovi ishonchsiz bo'lgan holat ────────────────────────────
# 2026-09-24: haydovchi qo'li bilan yuzini ishqalaganda MediaPipe ko'z
# nuqtalarini QO'L ustiga qo'yadi va EAR 0.32 dan 0.08 ga qulaydi —
# tizim buni uyqu deb o'qidi. Ajratish belgisi topildi: haqiqiy uzoq
# yumilishda EAR barqaror past turadi, qo'l bekitganda esa sakrab turadi.
# Qo'shni kadrlar farqining MEDIANASI o'lchandi:
#     qo'l bekitgan        0.0347
#     telefonga past qarash 0.0109
#     haqiqiy 1.5 s yumilish 0.0100
#     ochiq ko'z            0.0072
# Medianа olinadi, o'rtacha emas: yumilish boshidagi yakka katta sakrash
# natijani surib yuborib, haqiqiy uyquni o'chirib qo'yardi.
EYE_VOLATILE_WIN = 9        # nechta oxirgi kadr (taxminan 0.5 s)
EYE_VOLATILE_MAX = 0.030    # shundan yuqori bo'lsa o'lchov ishonchsiz
# Ostona o'lchab tanlandi. Shu qiymatda belgilangan kadrlar ulushi:
#   qo'l bekitgan 62%  |  telefonga qarash 8%  |  normal 7%
#   HAQIQIY 2 s yumilish 0% — ya'ni chin uyquni hech qachon to'smaydi

EYE_SMOOTH_N = 3            # 1 = silliqlash yo'q (eski xatti-harakat)
# Ostona qiymatlari pipeline ichidagi bilan bir xil — bu yerda ular
# ko'rinadigan va sozlanadigan bo'lsin uchun takrorlangan.
# Moslashuvchan ostona — har odamning o'z EAR darajasiga qarab.
# O'lchov (34 s yozuv, telefonga pastga qarab turgan haydovchi):
#   qat'iy ostona  -> 57 kadr "yumuq", eng uzuni 1.51 s  => UYQU signali
#   moslashuvchan  ->  4 kadr "yumuq", eng uzuni 0.15 s  => signal yo'q
EAR_ADAPTIVE = True
EAR_BASE_WINDOW = 180.0      # baza shuncha soniyalik tarixdan olinadi
EAR_BASE_PCT = 0.85          # yuqori protsentil = ochiq ko'z darajasi
EAR_BASE_MIN_SAMPLES = 60    # shundan kam namunada qat'iy ostona ishlatiladi
EAR_BASE_FLOOR = 0.22        # bazaning ENG PAST chegarasi — xavfsizlik uchun:
                             # uzoq uyquda baza pasayib signalni o'chirmasin
EAR_BASE_CAP = 0.45          # eng yuqori chegara
# Yuz bir-ikki kadrga yo'qolsa baza SAQLANADI — odam o'zgargani yo'q.
# Faqat uzoq yo'qlikdan keyin tozalanadi (boshqa mashinist kelgan bo'lishi
# mumkin). Busiz har qisqa uzilish bazani nolga tushirar va tizim qat'iy
# ostonaga qaytib qolardi.
EAR_BASE_RESET_SEC = 60.0
EAR_OPEN_RATIO = 0.78        # ochiq ostonasi = baza * shu
EAR_HALF_RATIO = 0.62        # yarim ostonasi = baza * shu

EAR_OPEN = 0.25             # shundan yuqori - ochiq
EAR_HALF = 0.20             # shundan yuqori - yarim, pasti - yumuq

BLINK_WINDOW = 120.0        # oxirgi shuncha s ichidagi pirpirashlar
BLINK_MIN_SAMPLES = 15      # shundan kam namunada xulosa chiqarilmaydi
# 10 dan 15 ga oshirildi: bir nechta uzun pirpirash medianani surib
# yubormasin. Odatiy tezlik 15-20/daqiqa, ya'ni 120 s oynada yetarli.
BLINK_SLOW_MS = 700.0       # MEDIANA shundan oshsa -> charchoq belgisi
# O'lchandi (55 s yozuv, 6 ta pirpirash): mediana 196 ms, 90% 331 ms,
# eng uzuni 552 ms. Eski ostona 550 ms aynan shu chegarada turardi.
# 700 ms kuzatilgan eng uzunidan ham yuqorida va charchoq adabiyotiga
# mos (uyqusizlikda pirpirash 500 ms dan oshadi).
# 400 ms juda sezgir edi: tinch odamda 100-200 ms, uyqusizlikda 500+ ms.
# Endi mediana o'lchanadi — bitta uzun yumilish natijani surib yubormaydi.
YAWN_SEC       = 1.0        # esnash shuncha s uzluksiz → CHARCHOQ
# Chalg'ish — MOSLASHUVCHAN baza: har odam/kameraning "old qarash" bosh holati
# o'lchanadi (mediana), undan SEZILARLI chetlashsagina yonadi. (Sobit ostona
# old qarashda ham yolg'on yonardi — head_nod old qarashда ~30° chiqadi.)
TILT_MARGIN = 16.0          # bosh yon egilishi bazadan shuncha daraja oshsa → chetga
NOD_MARGIN  = 18.0          # bosh pastga egilishi bazadan shuncha daraja oshsa → past
DISTRACT_SEC = 3.0          # shuncha s uzluksiz → CHALG'ISH
BASE_MIN = 45               # baza mediana uchun kamida shuncha namuna (isinish)
# Kamera to'silishi (tamper) — kadr o'rtacha yorug'ligi past YOKI tafsiloti (Laplacian
# dispersiyasi) past bo'lса → to'silган (qo'l/lenta bilan yopilган, qorong'i).
TAMPER_DARK_MEAN = 15.0     # o'rtacha yorug'lik shundan past → qorong'i (lok 2026-09-25: tunda 13.7 normal)
TAMPER_DETAIL_VAR = 20.0    # Laplacian dispersiyasi shundan past → tafsilotsiz (lok tunda 27-42 normal)
TAMPER_SEC = 8.0            # shuncha s uzluksiz to'silgan → signal (qisqa qorong'ilashish emas)
# Yorug'likka moslashuvchan qaror (argus/detect/tamper.py, 2026-09-29):
#  - tafsilot ostonasi = TAMPER_DETAIL_VAR * min(1, yorug'lik/TAMPER_DETAIL_REF);
#    yorug'lik < TAMPER_DARK_MEAN bo'lsa tafsilot bo'yicha hukm chiqarilmaydi
#    (tunda yorug'lik 2-6 da tafsilot 14-20 normal — 17 yolg'on xabar bo'lgan edi).
#  - keskin tushish ostonasi = min(TAMPER_DROP, max(TAMPER_DROP_MIN, TAMPER_DROP_FRAC*EMA)).
TAMPER_DROP = 40.0          # yorug' kabinada: EMA'dan shuncha keskin tushsa → yopilish
TAMPER_DROP_MIN = 15.0      # xira kabinada eng kam tushish
TAMPER_DROP_FRAC = 0.5      # EMA ning ulushi
TAMPER_DETAIL_REF = 60.0    # shu yorug'likdan past bo'lsa tafsilot ostonasi proporsional
TAMPER_EMA_ALPHA = 0.02     # yorug'lik EMA (~3 s @18 FPS)

# ── Rasm va video yozib olish ──
RECORD_DIR = os.path.join(HERE, "records")

# ── Dataset yig'ish (model o'rgatish uchun) ──
# MUHIM: records/ dagi rasm va videolarda HUD paneli va aniqlash qutilari
# kadrga KUYDIRILGAN. Ularda model o'rgatilsa, model panelning o'zini ham
# "belgi" deb o'rganib oladi va natija buziladi. Shuning uchun bu rejim
# kadrni pipeline'dan KEYIN, chizishdan OLDIN — toza holda saqlaydi.
#
# Asosiy maqsad: "qiyin negativ" yig'ish. Telefonsiz kabinada ishlatilsa,
# qora stul suyanchig'i kabi telefonga o'xshab ko'rinadigan narsalarning
# minglab kadri to'planadi — model aynan shularda adashayapti.
ENABLE_DATASET = False       # yig'ish kerak bo'lganda True qiling
DATASET_DIR = os.path.join(HERE, "dataset")
DATASET_EVERY = 3.0          # har shuncha s da bitta fon kadri
EVENT_EVERY = 1.0            # hodisa paytida — tezroq, lekin har kadrda emas
DATASET_ON_EVENT = True      # hodisa kadrlarini ham saqlash
DATASET_MAX = 5000           # shundan keyin to'xtaydi (disk himoyasi)
# Dalil rasmi QAYSI paytdan olinadi. Signal buzilish bir necha soniya
# davom etgandan keyin chiqadi — o'sha paytda haydovchi ko'zini allaqachon
# ochgan bo'lishi mumkin va rasm buzilishni ko'rsatmaydi. Shuning uchun
# rasm pre-roll buferdan, hodisa o'RTASIDAN olinadi.
SNAPSHOT_BACK_SEC = 0.6
# Dalil uchun TOZA (HUD chizilmagan) kadrlar alohida buferda saqlanadi.
# Yozuv buferidagi kadrlarga HUD allaqachon chizilgan — ular hodisadan
# OLDINGI holatni ko'rsatadi (panel yashil, banner yo'q), ya'ni rasm
# "hammasi joyida" degan taassurot qoldiradi. Toza kadrga esa hodisa
# paytidagi haqiqiy holatni chizib qo'yamiz.
SNAPSHOT_BUF_SEC = 1.2
SNAPSHOT_BUF_EVERY = 0.1

# Jurnalga davriy FPS yozuvi — tezlikni bitta kadrdan emas,
# o'lchov bilan baholash uchun.
FPS_LOG_EVERY = 60.0     # sekundiga 10 kadr — nusxalash narxini yarmiga tushiradi
SNAPSHOT_ON_EVENT = True     # har yangi hodisada avto .jpg
RECORD_ON_EVENT   = True     # har hodisada avto video klip (pre/post bufer bilan)
PRE_SECONDS  = 4.0           # hodisadan OLDINGI shuncha s ham yoziladi
POST_SECONDS = 5.0           # oxirgi hodisadan keyin yana shuncha s
REC_FPS = 12                 # yozuv fayli FPS (zaxira; jonli FPS o'lchanadi)
RECORD_AUDIO = True          # video bilan mikrofon ovozini ham yozish (ffmpeg bilan birlashadi)
# OpenCV videoni 'mp4v' (MPEG-4 Part 2) bilan yozadi — BRAUZERLAR uni ijro
# eta olmaydi, ya'ni saytda video ochilmaydi. Telegram qayta kodlagani uchun
# u yerda ko'rinadi va muammo sezilmay qoladi. Shuning uchun klip yopilgach
# H.264 ga o'tkaziladi. Alohida oqimda bajariladi, FPS ga ta'sir qilmaydi.
VIDEO_H264 = True

# ── GPS / lokomotiv ma'lumoti (gps.mydepo.uz) ──
# IMEI + vaqt yuborilsa: tezlik, koordinata va MASHINIST ma'lumoti qaytadi.
# Bu uch narsani ochadi:
#   1. Tezlikka bog'lash — temir yo'l standarti bo'yicha hushyorlik nazorati
#      10 km/soatdan yuqorida yoqiladi. To'xtagan poyezdda o'rnidan turish
#      normal, harakatda esa jiddiy buzilish. Ilgari buni faqat vaqt bilan
#      (ABSENT_SEC) taxmin qilardik.
#   2. Mashinistni tanish — hodisa "kimdir" emas, aniq shaxs nomi bilan.
#   3. DEVICE_NAME avtomatik — lok_nomer/lok_name dan olinadi.
ENABLE_GPS   = True
GPS_BASE     = "https://gps.mydepo.uz"
GPS_CREDS    = os.path.join(HERE, "gps_creds.json")   # {"email": "...", "password": "..."}
GPS_IMEI     = "350612076914389"      # lokomotiv GPS qurilmasi
GPS_EVERY    = 12.0                   # necha soniyada bir marta so'raladi
GPS_TIMEOUT  = 10.0

# Tezlik ostonasi — shundan yuqori bo'lsa "harakatda" hisoblanadi.
GPS_MOVING_KMH = 10.0
# Tezlik NOMA'LUM bo'lganda (GPS yo'q, tarmoq uzilgan) nima deb hisoblash.
# Xavfsizlik tizimi uchun "harakatda" to'g'ri: nazorat o'chib qolgandan
# ko'ra ortiqcha ogohlantirish afzal.
GPS_UNKNOWN_IS_MOVING = True

# GPS o'lchovi qancha vaqtgacha ishonchli hisoblanadi.
# API so'ralgan vaqtdagi emas, ENG YAQIN o'lchovni qaytaradi va u ancha
# eski bo'lishi mumkin (o'lchovda: lokomotiv turganda 28 daqiqagacha).
# Xavf: lokomotiv jo'nadi, yangi o'lchov hali kelmadi -> eski "tezlik 0"
# qaytadi -> tizim "to'xtagan" deb o'ylab, harakatdagi nazoratni o'chiradi.
# Shuning uchun eski o'lchov NOMA'LUM deb qabul qilinadi (ya'ni harakatda).
#
# O'LCHANGAN (2026-09-23, imei 350612079635775, 10 ta namuna):
#   dvigatel YOQIQ  -> o'lchov yoshi 4-18 s, mediana 11 s
#   dvigatel O'CHIQ -> 30 daqiqagacha (qurilma uyquga o'tadi)
# Ya'ni bog'lash kerak bo'lgan paytda (lokomotiv ishlayotganda) o'lchov
# doim yangi. 120 s - o'lchangan maksimumdan 6 barobar ko'p zaxira, lekin
# 300 s dan xavfsizroq: tunnelda aloqa uzilsa, 5 daqiqalik eski "tezlik 0"
# ga ishonish 60 km/soatda 5 km ko'r masofa degani.
GPS_FIX_MAX_AGE = 120.0      # soniya

# Poyezd TO'XTAGANDA o'chiriladigan signallar. To'xtab turganda o'rnidan
# turish, yon tomonga qarash yoki yuzni to'sish normal — bular faqat
# harakatda buzilish hisoblanadi.
#
# Uyqu va mikrouyqu ATAYLAB ro'yxatda YO'Q: to'xtagan poyezdda uxlab qolish
# ham qayd etilishi kerak (jo'nash vaqti kelganda mashinist uyg'oq bo'lsin).
GPS_GATED_TAGS = {"yoq", "yuz", "chalgish", "telefon", "kamar"}
# To'xtagan poyezdda (GPS < 10 km/s) ro'yxatdan tashqari buzilishlar FAQAT
# adminning shaxsiy botiga boradi — guruhga va saytga EMAS (2026-09-26,
# depoda 0 km/s da 30+ yolg'on uyqu xabari guruh va saytga ketgan edi).
STOPPED_ADMIN_ONLY = True
# Tezlik NOMA'LUM bo'lsa (GPS javob bermagan yoki o'lchov eskirgan — internet
# uzilganda) xabarlar ham FAQAT adminga. Nazorat o'chmaydi: buzilish
# aniqlanadi, ovoz chiqadi, admin oladi; faqat guruh va saytga ketmaydi.
# 2026-09-29 (user qarori): 28.09 08:35 va 23:16 da internet yo'qligida
# to'xtagan lok xabarlari guruh/saytga ketgan edi.
UNKNOWN_ADMIN_ONLY = True
# Bu turlar HAR DOIM faqat adminning botiga (guruh va sayt EMAS) — sinov davri.
# 2026-09-29: telefon modeli (v2) endigina ulandi, avval admin kuzatadi.
ADMIN_ONLY_TAGS = {"telefon"}
# Deploy skripti shu faylga qisqa izoh yozadi; dastur qayta ishga tushgach
# uni admin + guruhga "YANGILANDI (deploy)" xabari sifatida yuborib o'chiradi.
DEPLOY_NOTE_FILE = os.path.join(HERE, "deploy_note.txt")
AUDIO_RATE = 44100
AUDIO_CH = 1
# Mikrofon qurilmasi: None = AVTO (nomida "microphone" bo'lgan qurilma; standart
# qurilma ba'zан sichqoncha/dummy bo'lиб jimlik yozadi). Yoki aniq indeks (masalan 2).
AUDIO_DEVICE = None
# Qo'lда: 's' = hozir rasm, 'r' = yozuvni yoqish/o'chirish

# ── Kayfiyat (mood) — yuz ifodasidan (MediaPipe blendshapes) ──
ENABLE_MOOD = True
MOOD_MODEL = os.path.join(HERE, "models", "face_landmarker.task")     # yuzni topish
MOOD_ONNX = os.path.join(HERE, "models", "emotion-ferplus-8.onnx")   # FER+ emotion CNN
MOOD_EVERY = 0.4             # har shuncha s da bir marta kayfiyat baholanadi (CPU tejash)

# ── Maxfiy qiymatlar (token/parol) KODDA EMAS — secrets.json (git'ga kirmaydi)
# yoki ARGUS_<NOM> muhit o'zgaruvchisidan o'qiladi. Namuna: secrets.example.json
def _secret(name, default=""):
    v = os.environ.get("ARGUS_" + name)
    if v:
        return v
    try:
        with open(os.path.join(HERE, "secrets.json"), encoding="utf-8") as _fh:
            return str(json.load(_fh).get(name, default) or default)
    except Exception:
        return default

# ── Telegram bot — soatlik kayfiyat hisoboti + buzilish (hodisa) xabari ──
ENABLE_TELEGRAM = True
TELEGRAM_TOKEN = _secret("TELEGRAM_TOKEN")      # secrets.json -> "TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = _secret("TELEGRAM_CHAT_ID")  # SUPER ADMIN chat id (secrets.json) — boshqalarni tasdiqlaydi
REPORT_INTERVAL = 3600.0     # har shuncha s da (1 soat) kayfiyat hisoboti yuboriladi
INCIDENT_COOLDOWN = 120.0    # bir turdagi buzilish Telegram'ga shu s da bir marta

# DAVOMLI buzilishda takroriy xabar oralig'i ORTIB boradi.
# Haydovchi o'rnida bo'lmasa yoki kamera to'silgan bo'lsa, holat soatlab
# davom etishi mumkin. Qat'iy 120 s bilan bir soatda 30 ta bir xil xabar
# kelardi — bu spam va haqiqiy yangi hodisalarni ko'mib yuboradi.
#
# Holat tugasa hisoblagich nolga tushadi, ya'ni keyingi safar yana darhol
# xabar beriladi.
INCIDENT_BACKOFF = [120, 300, 900, 1800, 3600]
# Bir epizodda NECHA MARTA xabar berilsin.
# False → faqat BOSHIDA 1 marta (INCIDENT_BACKOFF umuman ishlatilmaydi).
# Sabab: davom etayotgan holat uchun takroriy so'rov ortiqcha yuk.
INCIDENT_REPEAT = False
# Holat TUGAGANDA 1 ta xabar — davomiyligi bilan. Busiz 3 soatlik buzilish
# 30 soniyalikdan farq qilmay qolardi: dispetcher tugaganini bilmaydi.
INCIDENT_END_MSG = True
# Qisqa epizodga "tugadi" xabari ortiqcha — boshlanish xabari yetarli.
INCIDENT_END_MIN = 30.0     # shundan uzoq davom etgan holatgagina yuboriladi
# Bir turdagi buzilish shu s ichida QAYTSA — o'sha epizod davom etadi: bitta
# ID, yangi rasm/video yo'q; epizod shu s tinch turgandan keyin yopiladi va
# "tugadi" xabari (davomiylik oxirgi faol vaqtgacha) ketadi. 2026-09-28:
# yuz pirpiraganda 4 daqiqada 8 epizod (16 ta media) ketgan edi.
INCIDENT_REJOIN_SEC = 120.0
TXT_END = ("\u2705 [{dev}] Tugadi: {label}\n"
           "Davomiyligi: {dur}\n"
           "Vaqt: {vaqt}\n"
           "ID: {uid}")

# DIQQAT: 1-xabar darhol ketadi, shuning uchun ro'yxatning BIRINCHI
# qiymati (120) ishlatilmaydi. Haqiqiy zina: 5 -> 15 -> 30 -> 60 daq.
# 1 soat uzluksiz buzilishda jami 4 ta matnli xabar chiqadi.

# ── Kunlik yakuniy hisobot ──
# Soatlik hisobot faqat oxirgi 1 soatni ko'rsatadi va qayta ishga tushganda
# yo'qoladi. Kunlik hisobot statistikani DISKDA saqlaydi (day_stats.json),
# shuning uchun restart yoki tok uzilishi uni buzmaydi.
DAILY_REPORT = True
DAILY_REPORT_AT = "23:00"    # mahalliy vaqt, HH:MM (shu vaqtdan keyin bir marta)

# ── Saytga (veb-server) yuborish ──
# Telegram bilan BIR XIL ishonchlilik: xabar diskdagi navbatga tushadi,
# internet uzilsa yo'qolmaydi, tarmoq qaytganda qayta yuboriladi.
ENABLE_WEBHOOK = True
# Sayt tomoni: ARGOS moduli, manzil oxiri /api/argos/webhook
WEBHOOK_URL = "https://ai-project.das-uty.uz/api/argos/webhook"
WEBHOOK_TOKEN = _secret("WEBHOOK_TOKEN")        # secrets.json -> "WEBHOOK_TOKEN"
WEBHOOK_SEND_PHOTO = True    # hodisa rasmini ham yuborish (multipart)
WEBHOOK_SEND_VIDEO = True    # videoni ham yuborish (multipart)
# 2026-09-24 da o'lchandi: bekend qabul qiladi (HTTP 200, savedFiles=1),
# tezlik 1660 KB/s. Odatiy klip 0.3-3.8 MB, ya'ni 0.2-2.3 soniya.
# Kanal sekin bo'lsa False qiling - klip Telegram'ga baribir ketadi.
WEBHOOK_TIMEOUT = 30.0       # bitta so'rov uchun (video uchun 3x olinadi)

# Internet uzilganda xabarlar navbatda (outbox) turadi va keyin yuboriladi.
# Shunda xabar KECHIKIB yetadi — hodisa qachon bo'lganini aniq bilish uchun
# har xabarga to'liq sana qo'yiladi, kechikkani esa alohida belgilanadi.
LATE_WARN_SEC = 120.0        # xabar shuncha s dan ko'p kechiksa — belgi qo'yiladi

# Ranglar (BGR)
C_BG=(28,28,30); C_TEXT=(240,240,240); C_DIM=(150,150,155)
C_OK=(120,205,95); C_WARN=(60,70,240); C_ACCENT=(235,190,70)
C_PHONE=(40,160,250); C_CIG=(60,70,240); C_BELT_OK=(120,205,95); C_BELT_NO=(60,70,240)
BOX_COL = {5:C_PHONE, 6:C_CIG, 7:C_BELT_OK, 8:C_BELT_NO}

VOICE_PRIORITY = ["kamera", "uyqu", "mikrouyqu", "uyquchan_kr", "yuz", "sigaret",
                  "telefon", "chalgish", "uyquchan", "kamar", "pirpirash", "esnash"]

TG_MSG = {"uyqu": "Uyqu", "telefon": "Telefon", "sigaret": "Sigaret",
          "chalgish": "Chalg'ish", "kamar": "Kamar yo'q", "yuz": "Yuz ko'rinmayapti",
          "yoq": "Haydovchi o'rnida yo'q", "mikrouyqu": "Mikrouyqu",
          "uyquchan": "Uyquchanlik belgilari", "uyquchan_kr": "KRITIK uyquchanlik",
          "pirpirash": "Sekin pirpirash (charchoq)",
          "kamera": "Kamera to'silgan", "esnash": "Charchoq/esnash"}

SUBS_FILE = os.path.join(HERE, "subscribers.json")

OUTBOX_FILE = os.path.join(HERE, "outbox.json")

DAY_FILE = os.path.join(HERE, "day_stats.json")

WEBHOOK_FILE = os.path.join(HERE, "web_outbox.json")

# Kamera o'lchami
CAM_WIDTH, CAM_HEIGHT = 1280, 720     # yuqori o'lcham — telefon kichik obyekt, piksel muhim

# ── Qayta tekshirish (yolg'on signallarni kamaytirish) ──────────────────
# Yuz yo'qolganda oxirgi ma'lum joy atrofidan kesib qayta qidiriladi.
# 2026-09-24: haydovchi qo'lini boshi ustiga ko'targanda MediaPipe butun
# kadrda yuzni yo'qotardi. Uchta muammoli kadrda o'lchandi —
# to'liq kadr: 0/3 topildi, kesilgan parcha: 3/3 topildi.
ENABLE_FACE_RECOVER = True
FACE_RECOVER_MARGIN = 2.5      # yuz qutisidan necha barobar keng kesamiz
FACE_RECOVER_MEMORY = 3600.0   # oxirgi joy shuncha s dan keyin eskiradi (tunda yuz uzoq yo'qoladi)
# O'rganilgan o'rindiq ROI (topilgan yuzlarning sekin EMA'si) — tunda to'liq
# kadrda yuz topilmaganda shu joydan kesib qayta qidiriladi. O'lchov
# 2026-09-26: tungi kliplarda to'liq kadr 3%, o'rindiq ROI 90-99% kadr.
SEAT_ROI_FILE = os.path.join(HERE, "seat_roi.json")
FACE_RECOVER_EVERY  = 0.15     # qayta urinishlar orasidagi eng kam vaqt (s)

# Yangi buzilish darhol e'lon qilinmaydi — shuncha s saqlanib tursin.
# Bir kadrlik sakrash shu yerda to'xtaydi.
# ── Ruxsat etilgan vaqt ────────────────────────────────────────────────
# Bu turlar chegaradan OSHGANDAGINA buzilish hisoblanadi. Chegaragacha
# ovozli ogohlantirish ishlaydi (haydovchi biladi va o'zi to'xtatadi),
# lekin Telegram'ga, saytga, kunlik statistikaga tushmaydi va video ham
# yozilmaydi. Holat uzilsa vaqt boshidan sanaladi.
GRACE_SEC = {"telefon": 180.0}     # telefon: 3 daqiqa
# Vaqt UZLUKSIZ emas, oynadagi JAMI hisoblanadi. Busiz qisqa
# tanaffus hisoblagichni nolga tushirar va chegara hech qachon
# to'lmasdi (o'lchandi: 60+20+120 s -> xabar yo'q).
GRACE_WINDOW = 600.0               # 10 daqiqalik oyna
# Qisqa uzilish foydalanish deb sanaladi: model telefonni bir necha
# soniyaga ko'rmay qolishi mumkin (qo'l pastga tushgan, burchak o'zgargan),
# odam esa gaplashishda davom etadi. Shundan uzun tanaffus haqiqiy deb
# hisoblanadi va sanalmaydi.
GRACE_BRIDGE = 30.0                # 30 soniyagacha uzilish - ko'prik

CONFIRM_SEC = 0.6
# Uyquga oid turlar RO'YXATGA KIRMAYDI: ular allaqachon uzluksiz vaqt
# bilan o'lchanadi (EYE_CLOSED_SEC, MICROSLEEP_SEC, PERCLOS_HOLD), ustiga
# yana kechikish qo'shsak xavfsizlik chegarasi sezdirmay siljib ketadi.
CONFIRM_TAGS = {"yuz", "yoq", "telefon", "chalgish", "kamar", "sigaret", "esnash"}


# ── Maydon sozlamasi: device.json ─────────────────────────────────────
# Qurilma lokomotivda MONITORSIZ ishlaydi. IMEI har lokomotivda boshqacha,
# lekin uni o'zgartirish uchun config.py ni tahrirlash kerak bo'lardi —
# monitorsiz buni qilib bo'lmaydi. Shuning uchun IMEI va nom shu kichik
# faylda saqlanadi va Telegram'dagi /imei buyrug'i orqali o'rnatiladi.
# Fayl bo'lmasa yuqoridagi qiymatlar ishlatiladi.
DEVICE_FILE = os.path.join(HERE, "device.json")
try:
    import json as _json
    with io.open(DEVICE_FILE, encoding="utf-8") as _f:
        _dev = _json.load(_f)
except Exception:
    _dev = {}
if _dev.get("imei"):
    GPS_IMEI = str(_dev["imei"]).strip()
if _dev.get("device_name"):
    DEVICE_NAME = str(_dev["device_name"]).strip()

# Lokomotiv nomi GPS dan avtomatik olinsin (IMEI -> lok_nomer).
# Shunda maydonda faqat IMEI kiritiladi, qolgani o'zi to'ldiriladi.
DEVICE_NAME_FROM_GPS = True
# Nom device.json da QO'LDA berilgan bo'lsa, GPS uni ustidan yozmaydi.
DEVICE_NAME_FIXED = bool(_dev.get("device_name"))

# Ulanish xabari: GPS ma'lumoti kelishini shuncha kutamiz, keyin
# baribir yuboramiz (internet bo'lmasa navbatda turadi va ulanishi
# bilan yetib boradi).
HELLO_MAX_WAIT = 45.0


# ── Ko'p qurilma, BITTA bot tokeni ────────────────────────────────────
# Telegram bitta tokenda FAQAT BITTA getUpdates iste'molchisiga ruxsat
# beradi. Ikkinchisi so'rasa 409 "Conflict" qaytadi va yangilanishlar
# tasodifiy bo'linadi: bitta qurilmaga yozilgan buyruq boshqasiga tushib
# yo'qoladi. Shuning uchun parkda qurilmalar buyruq QABUL QILMAYDI -
# faqat yuboradi. Yuborishda to'qnashuv yo'q.
#
# Buyruqlarni bitta joydan berish kerak: sayt (bekend) botni o'zi
# o'qiydi va qurilmalarga o'zi uzatadi. Sinov uchun BITTA qurilmada
# device.json ichida {"telegram_poll": true} qilib yoqish mumkin.
TELEGRAM_POLL = bool(_dev.get("telegram_poll", False))

# Bitta chatga Telegram limiti ~20 xabar/daqiqa. 100 qurilma bitta chatga
# yozsa limit doim oshadi, shuning uchun 429 javobi to'g'ri qayta ishlanadi
# (xabar navbatda qoladi va keyin yuboriladi, yo'qolmaydi).
TELEGRAM_MAX_RETRY_WAIT = 300.0


# ── Eski yozuvlarni tozalash ──────────────────────────────────────────
# Rasm va videolar diskda to'planib boradi (kuniga ~200 rasm, ~170 klip).
# Shuncha kundan eski fayllar o'chiriladi.
#
# MUHIM: navbatda turgan fayl HECH QACHON o'chirilmaydi. Internet bir
# necha kun uzilib qolsa, yuborilmagan dalil yo'qolib ketmasligi kerak.
RECORD_KEEP_DAYS = 5
RECORD_CLEAN_EVERY = 3600.0    # tekshirish oralig'i (s)

# ── 11. QURILMAGA XOS qiymatlar: config_local.py (git'da YO'Q) ──────────────
# Faqat ODDIY qiymatlar (True/False, son, matn). Boshqa qiymatdan hisoblangan
# sozlamalar (yo'llar, HERE) bu yerda qayta hisoblanmaydi.
# Namuna: config_local.example.py. Lokda: ENABLE_PHONE=False, ENABLE_PERSON=False.
try:
    from config_local import *   # noqa: F401,F403
    _LOCAL_CONFIG = True
except ImportError:
    _LOCAL_CONFIG = False
