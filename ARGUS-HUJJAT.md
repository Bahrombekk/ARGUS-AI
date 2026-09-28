# ARGUS AI — to'liq hujjat

Lokomotiv mashinistini real vaqtda kuzatish tizimi. Uyquchanlik, chalg'ish,
telefon, kamar va o'rindan turishni aniqlaydi; Telegram'ga va saytga xabar
beradi; rasm va video dalil saqlaydi.

Hujjat 2026-09-24 holatiga to'g'ri keladi.

---

## 1. Qurilma va joylashuv

| | |
|---|---|
| Qurilma | mini PC, Intel i5-7500T, Windows 11 Pro (ruscha) |
| Lokal IP | 192.168.136.114 |
| Tailscale IP | **100.105.120.21** (`win-4n4ald0jndp`) |
| AnyDesk ID | 1199946835 |
| Loyiha yo'li | `C:\ARGUS AI` |
| Python | `C:\sdv\Scripts\python.exe` |
| FPS | ~18 (kamera 1280x720) |

Nega mini PC: Raspberry Pi 4/5 va Jetson Nano bilan solishtirilganda i5-7500T
sezilarli tezroq va qo'shimcha xarajat talab qilmaydi — qurilma allaqachon bor edi.

### Masofadan kirish

Desktop → **ARGUS-kirish** papkasida tayyor fayllar:

| fayl | nima qiladi |
|---|---|
| `Masofadan-RDP.bat` | Tailscale orqali ish stoli (istalgan joydan) |
| `Lokal-RDP.bat` | shu tarmoqdan ish stoli |
| `AnyDesk-parol.bat` | SSH orqali kirib, AnyDesk parolini o'rnatish |
| `minipc_key` | SSH kaliti |

RDP allaqachon yoqilgan (`fDenyTSConnections = 0`, firewall qoidalari faol).
Kirish: foydalanuvchi `user`, paroli — netplwiz da avto-kirish uchun kiritilgan.

**Diqqat:** RDP ulangan paytda FPS 18 dan 12–17 gacha tushadi (ekran kodlash
protsessorni oladi). Ish tugagach uziling. Kamera va mikrofon RDP dan keyin
ishlashda davom etadi — tekshirilgan.

---

## 2. Avtomatik ishga tushish

Tok uzilib qayta kelganda qurilma o'zi ishga tushadi. Zanjir:

1. **BIOS** — `AcPwrRcvry = On` (Dell Command Configure orqali masofadan o'rnatilgan)
2. **Windows avto-kirish** — `user` hisobi bilan, 1-seansga
3. **Vazifalar rejalashtiruvchisi** — "ARGUS AI" vazifasi, `C:\ARGUS AI\run.bat`

Vazifa **SYSTEM emas, `user` nomidan va Interactive** rejimda ishlaydi. Bu shart:
SYSTEM 0-seansda ishlaydi, u yerda ovoz chiqmaydi va USB kamera/mikrofonga
kirish yo'q. Bu xato bir marta yo'l qo'yilgan va to'liq qayta yuklash bilan
tekshirilgan (avto-kirish 12:47 → ARGUS 12:48:48, 1-seans).

---

## 3. Aniqlash turlari va ostonalar

Barcha qiymatlar `config.py` da. Quyidagi jadvaldagi sabablar **o'lchovga**
asoslangan — haqiqiy yozuvlarda sinalgan, taxmin emas.

### 3.1 Ko'z va uyqu

| sozlama | qiymat | nega shunday |
|---|---|---|
| `MICROSLEEP_SEC` | 1.0 s | 0.5 → 0.8 → 1.0. Odatiy pirpirash 0.1–0.4 s, charchaganda 0.8 s gacha. 1.0 s har qandayidan yuqorida |
| `EYE_CLOSED_SEC` | 2.0 s | 1.2 s edi — mikrouyqudan atigi 0.2 s narida, bitta yumilish ketma-ket IKKI xabar berardi. Xavfsizlik pasaymaydi: birinchi ovoz baribir 1.0 s da chiqadi |
| `EYE_SMOOTH_N` | 3 | EAR medianasi. 88 kadrlik yozuvda 2 ta yakka chetlanish topilgan (EAR 0.30→0.198→0.305, ~54 ms). Bular ko'z yumish emas, landmark chayqalishi edi |
| `EAR_ADAPTIVE` | True | Qat'iy ostona bilan telefonga pastga qaragan haydovchida 34 s yozuvda 57 kadr "yumuq", eng uzuni 1.51 s — UYQU signali chiqardi. Moslashuvchan bilan 4 kadr, 0.15 s |
| `EAR_BASE_FLOOR` | 0.22 | Xavfsizlik chegarasi: haydovchi butun oyna davomida uxlasa baza pasayib signalni o'chirib qo'yardi. Sinalgan — bu holatda ham uyqu aniqlanadi |
| `EYE_VOLATILE_MAX` | 0.030 | Qo'l ko'zni bekitganda EAR sakraydi, haqiqiy yumilishda barqaror past turadi. `|ΔEAR|` medianasi: qo'l 0.0347, telefonga qarash 0.0109, haqiqiy yumilish 0.0100, ochiq ko'z 0.0072 |

Moslashuvchan ostona: oxirgi 180 s ning 85-protsentili = odamning ochiq ko'z
darajasi. Ostonalar shundan nisbat bilan (`0.78` / `0.62`). Yuz qisqa yo'qolsa
baza saqlanadi, faqat 60 s dan uzun yo'qlikdan keyin tozalanadi.

### 3.2 PERCLOS va pirpirash

| sozlama | qiymat | nega |
|---|---|---|
| `PERCLOS_WARN` | 35% | 20% edi. O'lchandi: UYG'OQ odam klaviaturada ishlaganda jonli tizimda 32% gacha chiqdi |
| `PERCLOS_CRIT` | 50% | |
| `PERCLOS_HOLD` | 10 s | 3 s edi — qiymat chegara atrofida tebranganda signal yonib-o'chardi |
| `BLINK_SLOW_MS` | 700 ms | O'lchandi (6 ta pirpirash): mediana 196 ms, 90% 331 ms, eng uzuni 552 ms. Eski ostona 550 ms aynan shu chegarada edi |
| `BLINK_MIN_SAMPLES` | 15 | |

Pirpirash **medianasi** olinadi, o'rtachasi emas: bitta uzun yumilish o'rtachani
surib yuborardi. `MAX_BLINK` 1.0 s — undan uzuni pirpirash emas, uyqu.

### 3.3 Telefon

| sozlama | qiymat | izoh |
|---|---|---|
| model | `phone_v1.pt` | alohida o'qitilgan, 1 sinf |
| `PHONE_MODEL_CONF` | 0.40 | 0.25 edi — qorong'i kiyimda yolg'on berardi. Sinovda yolg'on aniqlashlar 0.27 va 0.32 bilan chiqdi, ostona ularni to'sdi |
| ruxsat | 3 daqiqa | `GRACE_SEC` |
| oyna | 10 daqiqa | `GRACE_WINDOW` — jami vaqt shu oynada hisoblanadi |
| ko'prik | 30 s | `GRACE_BRIDGE` — qisqa aniqlash uzilishi foydalanish deb sanaladi |

**Qoida:** har 10 daqiqada 3 daqiqadan ko'p telefon ishlatilsa — buzilish.
Vaqt **jami** hisoblanadi, uzluksiz emas. Ovozli ogohlantirish birinchi
soniyadan ishlaydi, xabar esa faqat chegaradan oshganda.

Nega ko'prik kerak: model telefonni bir necha soniyaga ko'rmay qolishi mumkin
(qo'l pastga tushgan, burchak o'zgargan), odam esa gaplashishda davom etadi.
Busiz har uzilish hisoblagichni nolga tushirar va 20 soniyalik tanaffus bilan
cheksiz foydalanish mumkin edi.

### 3.4 Boshqalar

| tur | sozlama |
|---|---|
| Yuz ko'rinmayapti | `NOFACE_SEC = 4 s` (odam kadrda bor bo'lsa) |
| O'rinda yo'q | `ABSENT_SEC = 12 s` (YOLOv8n odam detektori, faqat yuz yo'qolganda ishlaydi) |
| Chalg'ish | bazadan `TILT_MARGIN = 16°` yoki `NOD_MARGIN = 18°` chetlanish |
| Esnash | `YAWN_SEC = 1 s` |
| Kamera to'silgan | yorug'lik va tafsilot pasayishi |

---

## 4. Xabar berish qoidalari

### 4.1 Qachon yuboriladi

1. **Tasdiqlash** — yangi buzilish `CONFIRM_SEC = 0.6 s` saqlanib turishi kerak.
   Bir kadrlik sakrash shu yerda to'xtaydi. Uyquga oid turlar bundan ozod
   (ular allaqachon uzluksiz vaqt bilan o'lchanadi).
2. **Tezlik filtri** — poyezd 10 km/s dan sekin bo'lsa `yoq`, `yuz`,
   `chalgish`, `telefon`, `kamar` buzilish hisoblanmaydi (temir yo'l standarti:
   hushyorlik nazorati harakatda talab qilinadi). Uyqu turlari bundan **kirmaydi**.
   GPS o'lchovi eskirgan bo'lsa poyezd harakatda deb hisoblanadi.
3. **Ishonchsiz o'lchov** — qo'l ko'zni bekitgan bo'lsa uyqu turlari yuborilmaydi.

### 4.2 Necha marta

`INCIDENT_REPEAT = False` — epizodga **bitta** xabar. Holat 30 soniyadan uzoq
davom etgan bo'lsa, tugaganda yana bitta xabar (davomiyligi bilan).

1 soat uzluksiz buzilishda: **1 ta matn + 1 rasm + 1 video**. Ilgari 31 ta
xabar bo'lardi.

### 4.3 Dalil rasmi

Rasm signal chiqqan paytdagi kadr **emas** — hodisaning o'rtasidan, 0.6 s
oldingi **toza** kadrdan olinadi, ustiga hozirgi holat chiziladi.

Sabab: signal buzilish bir necha soniya davom etgandan keyin chiqadi, o'sha
paytdagi kadrda haydovchi ko'zini allaqachon ochgan bo'lishi mumkin. O'lchangan
misol: rasmda EAR 0.274 (ochiq), HUD esa "YUMUQ" deb turardi.

---

## 5. GPS integratsiyasi

`gps.mydepo.uz` API, `device-snapshot?imei=...&datetime=...`.

Beradi: tezlik, koordinata, dvigatel holati, **mashinist ismi**, lokomotiv
raqami va nomi.

| sozlama | qiymat |
|---|---|
| `GPS_EVERY` | 12 s |
| `GPS_MOVING_KMH` | 10 km/s |
| `GPS_FIX_MAX_AGE` | 120 s |

**Muhim:** GPS qurilmasi dvigatel o'chganda ma'lumot yubormaydi. O'lchangan:
dvigatel yoniq — o'lchov 1 soniya yangi; o'chiq — 275 daqiqagacha eski.
Shuning uchun eski o'lchov "hozirgi tezlik" deb ko'rsatilmaydi.

Login/parol `gps_creds.json` da (`{"email":..., "password":...}`).

---

## 6. Saytga integratsiya

To'liq spetsifikatsiya alohida faylda: **`INTEGRATION.md`**.

Qisqacha: `POST https://ai-project.das-uty.uz/api/argos/webhook`, Bearer token.
Bitta hodisa bir necha so'rov bo'lib keladi, hammasida bir xil `uid`.

Bekend uchun muhim bo'limlar:
- **5a** — holat tugadi: `phase=end`, `duration_sec`
- **5b** — buzilish qachon yuborilmaydi
- **5v** — `detail` maydonini ustiga yozmang (so'rovda maydon yo'q bo'lsa,
  eski qiymat saqlansin)

Internet uzilsa so'rovlar navbatda turadi va ulanishi bilan yuboriladi.
Hodisa vaqti navbatga qo'yilganda yoziladi, shuning uchun kechikkan xabarda ham
haqiqiy vaqt ko'rinadi (`delayed_sec`).

---

## 7. Maydonga chiqish (lokomotivga o'rnatish)

### 7.1 device.json

Monitorsiz sozlash uchun. `C:\ARGUS AI\device.json`:

```json
{
  "imei": "350612076914389",
  "telegram_poll": true
}
```

| kalit | nima |
|---|---|
| `imei` | lokomotiv GPS qurilmasining IMEI si |
| `device_name` | qurilma nomi (berilmasa GPS dagi lokomotiv raqamidan olinadi) |
| `telegram_poll` | bot buyruqlarini qabul qilish (pastga qarang) |

Fayl bo'lmasa `config.py` dagi qiymatlar ishlatiladi.

### 7.2 Ulanish xabari

Ishga tushganda qurilma o'zini tanitadigan xabar yuboradi. Internet bo'lmasa
navbatda turadi va **ulanishi bilan** yetib boradi:

```
🟢 [Lokomotiv-007] ARGUS AI ulandi
Vaqt: 2026-09-24 16:20:11
Qurilma: Lokomotiv-007
IMEI: 350612076914389
Lokomotiv: 007 / UZTE-16M2
Mashinist: Сафаров Зариф Нармуминович
GPS o'lchovi: yangi
Kamera: 1280x720
Navbatda: 0 xabar
```

GPS javobi kutiladi (`HELLO_MAX_WAIT = 45 s`), keyin baribir yuboriladi.

### 7.3 100 qurilma — BITTA bot tokeni

**Telegram bitta tokenda faqat BITTA `getUpdates` iste'molchisiga ruxsat
beradi.** Ikkinchisi so'rasa `409 Conflict` qaytadi va yangilanishlar tasodifiy
bo'linadi: bitta qurilmaga yozilgan buyruq boshqasiga tushib yo'qoladi.

Shuning uchun:

- `TELEGRAM_POLL = False` (default) — qurilmalar buyruq **qabul qilmaydi**,
  faqat yuboradi. Yuborishda to'qnashuv yo'q.
- 409 kelsa qurilma o'zi to'xtaydi va jurnalga yozadi.
- Sinov uchun bitta qurilmada `device.json` orqali yoqiladi.

**Buyruqlar bitta joydan berilishi kerak:** sayt botni o'zi o'qib, qurilmalarga
uzatadi. Bu bekend tomonidagi ish, hali qilinmagan.

**Ikkinchi cheklov:** bitta chatga Telegram limiti ~20 xabar/daqiqa. 100 qurilma
bitta chatga yozsa limit doim oshadi. Har lokomotivga alohida chat yoki guruh
kerak bo'ladi. Kod tomonidan `429` to'g'ri qayta ishlanadi — xabar navbatda
qoladi va yo'qolmaydi.

### 7.4 Bot buyruqlari

Faqat `telegram_poll: true` bo'lgan qurilmada:

| buyruq | nima |
|---|---|
| `/id` | qurilma, IMEI, lokomotiv, mashinist, kamera, navbat |
| `/imei <raqam>` | IMEI ni o'rnatadi va `device.json` ga yozadi |
| `/status` | qisqa holat |
| `/snapshot` | hozirgi kadr |
| `/report`, `/kun` | soatlik va kunlik hisobot |
| `/stop` | to'xtatish |
| `/list`, `/approve <id>`, `/deny <id>` | obunachilarni boshqarish |

Botni bloklagan obunachi avtomatik ro'yxatdan chiqariladi (aks holda har
xabarda bitta so'rov behuda ketadi).

---

## 8. Fayl strukturasi

```
C:\ARGUS AI\
├── app.py              ishga tushirish nuqtasi
├── config.py           BARCHA sozlamalar
├── device.json         maydon sozlamasi (IMEI, nom)
├── gps_creds.json      GPS API login/parol
├── run.bat             ishga tushirish skripti
├── argus\
│   ├── loop.py         asosiy tsikl
│   ├── hud.py          ekranga chizish (Pillow + TrueType)
│   ├── report.py       hisobotlar
│   ├── utils.py        yordamchilar
│   ├── detect\         drowsy, mood, phone, person, reverify, windows
│   ├── media\          camera, recorder, voice, dataset
│   └── net\            telegram, web, gps, outbox
├── models\             safedrive.pt, phone_v1.pt, yolov8n.pt,
│                       face_landmarker.task, emotion-ferplus-8.onnx
├── audio\              o'zbekcha ovozlar (.wav)
├── records\            rasm va videolar
└── logs\               jurnallar
```

Jurnalga har 60 soniyada FPS yoziladi (`FPS_LOG_EVERY`) — sekinlashuvni
o'lchash uchun. Har bir saytga so'rov ham yoziladi (`SAYT -> ...`).

---

## 9. Ochiq masalalar

| masala | holat |
|---|---|
| **Buyruqlarni bekend orqali uzatish** | 100 qurilma uchun shart. Bekendda endpoint kerak |
| **Har lokomotivga alohida Telegram chat** | limit tufayli kerak, hali hal qilinmagan |
| **IMEI ni maydonda kiritish** | hozir RDP yoki `device.json` orqali. Bekend bersa qo'l ishi kerak emas |
| **5 ta ovoz fayli yetishmaydi** | `mikrouyqu`, `uyquchan`, `uyquchan_kr`, `pirpirash`, `yuz`. Mashinada o'zbek TTS yo'q |
| **Pastga qaraganda EAR pasayishi** | moslashuvchan ostona kamaytirdi, lekin tubdan hal qilmadi. To'g'ri yechim — MediaPipe blendshapes yoki qarash yo'nalishi |
| **Telefon modeli qorong'i kiyimda** | ostona 0.40 bilan to'silgan. Tub yechim — kabinada turli kiyim va yorug'likda ma'lumot yig'ib qayta o'qitish |
| **PERCLOS ni jurnalga yozish** | ostonani bir kunlik ma'lumotga qarab aniqlash uchun |

---

## 10. Maxfiy ma'lumotlar qayerda

Hujjatda **hech qanday parol yoki token yo'q**. Ular:

| nima | qayerda |
|---|---|
| Telegram bot tokeni | `config.py` → `TELEGRAM_TOKEN` |
| Sayt tokeni | `config.py` → `WEBHOOK_TOKEN` |
| GPS login/parol | `gps_creds.json` |
| AnyDesk paroli | AnyDesk sozlamasida (hash) |
| Windows paroli | netplwiz da |
| SSH kaliti | `Desktop\ARGUS-kirish\minipc_key` |
