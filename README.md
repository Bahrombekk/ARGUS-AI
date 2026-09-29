# ARGUS AI — jonli haydovchi nazorati

Lokomotiv mashinisti (yoki haydovchi) uchun real vaqt xavfsizlik nazorati.
Bitta kamera orqali quyidagilarni aniqlaydi va **o'zbekcha ovoz** bilan ogohlantiradi:

| Funksiya | Nima aniqlaydi | Ovoz |
|---|---|---|
| Uyqu | ko'z uzoq yumuq | "Uyg'oning, uxlab qolmang!" |
| Charchoq | esnash | "Siz charchayapsiz!" |
| Chalg'ish | boshqa yoqqa/pastga qarash | "Old tomonga qarang!" |
| Telefon | qo'lда telefon | "Telefonni qo'ying!" |
| Sigaret | chekish *(hozir o'chirilgan)* | "Chekish mumkin emas!" |
| Kamar | xavfsizlik kamari yo'q | "Xavfsizlik kamarini taqing!" |
| Kamera | kamera to'silган/qorong'i | "Kamera to'sib qo'yilgan!" |
| Kayfiyat | yuz ifodasi (xursand/betaraf/asabiy/xafa/hayrat) | — (kuzatiladi) |

## Telegram bot (@ArgusAITbot)

- **Buzilish** (uyqu/telefon/chalg'ish/kamar/kamera) → darhol **xabar + rasm + video**
  yuboriladi (bir turdagi xabar `INCIDENT_COOLDOWN` = 120s da bir marta).
- **Har soatda** — yig'ilган kayfiyat + buzilishlar bo'yicha xulosa.
- Oynada **`t`** = hozir hisobotni yuborish (kutmasdan).

### Obuna / tasdiqlash

- `TELEGRAM_CHAT_ID` = **super admin** (hozir Bahrombek). Doim xabar oladi.
- Boshqa odam botga **/start** bossa → admin'ga uning ismi+ID va **[✅ Tasdiqlash] [❌ Rad etish]**
  tugmalari keladi. Admin tasdiqlasa — o'sha odam ham barcha xabar/hisobotlarni oladi.
- Admin buyruqlari: `/approve <id>`, `/deny <id>`, `/list`.
- Ro'yxat `subscribers.json` da saqlanadi (qayta ishga tushirishда yo'qolmaydi).

## Ishga tushirish

**`run.bat`** faylini ikki marta bosing. Kamera oynasi ochiladi.
Chiqish: oynada **`q`** yoki **ESC**.

## Yozib olish

- **Avto:** har hodisada `records/` ga rasm (.jpg) + video klip (.mp4) — hodisadan
  4s oldin va 5s keyin, **mikrofon ovozi bilan**.
- **Qo'lда:** oynada `s` = hozir rasm, `r` = yozuvni yoqish/o'chirish.
- Ovoz `ffmpeg` bilan videoga birlashtiriladi (`RECORD_AUDIO = False` — o'chirish).

## Sozlash

Barcha sozlamalar **`app.py`** boshida:

- **Funksiyani yoqish/o'chirish** — `ENABLE_*` (True/False). Masalan sigaretni
  yoqish: `ENABLE_SMOKING = True`; kamarni o'chirish: `ENABLE_SEATBELT = False`.
- **Sezgirlik** — `EYE_CLOSED_SEC`, `DISTRACT_SEC`, `TILT_MARGIN`, `TAMPER_*` va h.k.
- **Ovoz oralig'i** — `ALERT_COOLDOWN` (bir hodisa necha soniyada qayta aytiladi).

## Tuzilishi

```
ARGUS AI/
  app.py              — asosiy dastur
  models/safedrive.pt — YOLO modeli (ko'z, telefon, sigaret, kamar)
  audio/*.wav         — o'zbekcha ovozlar (Yulduz)
  run.bat             — ishga tushirish
```

## Dvigatel

Aniqlash **SafeDrive** pipeline'i ustida ishlaydi (MediaPipe ko'z/bosh + YOLO
obyekt + CNN uyqu). Uning ustiga: o'zbekcha ovoz, dizayn, yolg'on-signalga qarshi
debounce va kamera-to'silish qo'shilgan.

## Eslatma (muhim)

Hozir dastur **`C:\sdv`** dagi Python muhitidan foydalanadi (torch, ultralytics,
mediapipe, safedrive shu yerda). Boshqa kompyuterga ko'chirishда shu muhit ham
kerak bo'ladi — kerak bo'lsa, muhitni papka ichiga to'liq joylashtiramiz.

## Sozlash (maxfiy qiymatlar)

Token va parollar kodda emas. `secrets.example.json` ni `secrets.json` nomi bilan nusxalab, o'z qiymatlaringizni yozing:

```json
{ "TELEGRAM_TOKEN": "...", "TELEGRAM_CHAT_ID": "...", "WEBHOOK_TOKEN": "..." }
```

GPS API uchun `gps_creds.json` (`{"email": "...", "password": "..."}`), qurilma uchun `device.json` (`{"imei": "...", "telegram_poll": true}`) kerak. Bu fayllar `.gitignore` da.

## Testlar

Har deploy'dan oldin:

```bash
C:\sdv\Scripts\python.exe tests\run_all.py
```

`--quick` — faqat birlik testlar. To'liq rejim etalon kliplarni (`tests/clips/`, ~36 MB, git'da yo'q; ro'yxat va md5 — `tests/clips.json`) haqiqiy `FrameAnalyzer` orqali o'tkazadi: haqiqiy yumuq → uyqu bo'lishi shart, pastga qarash → uyqu bo'lmasligi shart, tungi kliplar → yuz topilishi, tungi kadrlar → "kamera to'silgan" bo'lmasligi. Yangi holat qo'shish uchun klipni `tests/clips/` ga nusxalab `clips.json` ga kutilgan natija bilan yozish kifoya.
