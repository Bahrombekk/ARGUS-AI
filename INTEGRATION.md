# ARGUS AI — saytga ulash (integratsiya)

ARGUS AI aniqlagan har bir buzilishni sizning saytingizga yuboradi.
Bu hujjat sayt tomonida nima qilish kerakligini tushuntiradi.

---

## 1. Sozlash

`app.py` boshidagi to'rt qator:

```python
ENABLE_WEBHOOK     = True
WEBHOOK_URL        = "https://sayt.uz/api/incidents"   # sizning manzilingiz
WEBHOOK_TOKEN      = "maxfiy-token"                    # bo'sh qoldirilsa sarlavha yuborilmaydi
WEBHOOK_SEND_PHOTO = True     # hodisa rasmini ham yuborish
WEBHOOK_SEND_VIDEO = False    # videoni ham yuborish (og'ir — sekin kanalda o'chiring)
WEBHOOK_TIMEOUT    = 30.0     # bitta so'rov uchun soniya (video uchun 3x olinadi)
```

`WEBHOOK_URL` bo'sh bo'lsa hech narsa yuborilmaydi va dastur logga
`Sayt: WEBHOOK_URL bo'sh - yuborilmaydi.` deb yozadi.

---

## 2. So'rov

Barcha ma'lumot **bitta manzilga** `POST` bilan yuboriladi.

| Sarlavha | Qiymat |
|---|---|
| `Authorization` | `Bearer <WEBHOOK_TOKEN>` — token qo'yilgan bo'lsa |

So'rov ikki ko'rinishda keladi:

### 2.1. Faqat matn

```
Content-Type: application/json
```

JSON to'g'ridan-to'g'ri so'rov tanasida.

### 2.2. Rasm yoki video bilan

```
Content-Type: multipart/form-data
```

| Maydon | Ichida |
|---|---|
| `data` | JSON **matn ko'rinishida** (yuqoridagi bilan bir xil tuzilma) |
| `photo` | `.jpg` fayl — rasm biriktirilgan bo'lsa |
| `video` | `.mp4` fayl — video biriktirilgan bo'lsa |

> Diqqat: multipart holatda JSON **tanada emas**, `data` maydonining
> ichida keladi. Serverda uni alohida `json.loads` qilish kerak.

---

## 3. Maydonlar

```json
{
  "msg_id":      "e2b2c4d67abe4be8",
  "uid":         "2710416188e6",
  "kind":        "incident",
  "device":      "Lokomotiv-01",
  "type":        "telefon",
  "label":       "Telefon",
  "time":        "2026-09-17 14:31:08",
  "ts":          1789648268.5,
  "detail":      "Ishonch: 0.61",
  "delayed_sec": 0.4
}
```

| Maydon | Turi | Ma'nosi |
|---|---|---|
| `msg_id` | matn | **Har bir yuborish uchun yagona.** Qayta urinishda **o'zgarmaydi** — takrorni shu bo'yicha aniqlang |
| `uid` | matn | **Hodisa ID si.** Bitta hodisaning matni, rasmi va videosi bir xil `uid` oladi |
| `kind` | matn | `incident` yoki `report` |
| `device` | matn | Lokomotiv nomi (`DEVICE_NAME` sozlamasidan) |
| `type` | matn | Buzilish turi — 4-bo'limga qarang |
| `label` | matn | O'zbekcha nomi (ko'rsatish uchun) |
| `time` | matn | **Hodisa vaqti**, `YYYY-MM-DD HH:MM:SS`, qurilmaning mahalliy vaqti |
| `ts` | son | O'sha vaqt Unix formatida |
| `delayed_sec` | son | Hodisa bilan yuborish orasidagi kechikish (soniya) |
| `detail` | matn | O'lchangan qiymat. Bo'lmasa maydon **umuman kelmaydi** |

> Bo'sh (`null`) maydonlar so'rovga **qo'shilmaydi**. Server ularning
> yo'qligiga tayyor bo'lsin.

---

## 3a. GPS va mashinist maydonlari (YANGI)

ARGUS endi `gps.mydepo.uz` dan lokomotivning tezligi, koordinatasi va
**mashinist ma'lumotini** oladi va har bir hodisaga qo'shib yuboradi.

> **Diqqat:** bu maydonlar **hozir yuborilyapti**. Sayt tomonida ular hali
> qabul qilinmasa, hujjatga ko'ra "noma'lum maydon" sifatida **jimgina
> tashlab yuboriladi** — xato chiqmaydi, lekin ma'lumot ham saqlanmaydi.

```json
{
  "msg_id": "...", "uid": "...", "kind": "incident",
  "type": "yoq", "label": "Haydovchi o'rnida yo'q",
  "time": "2026-09-23 14:31:08", "ts": 1789648268.5,

  "speed":            0.0,
  "lat":              37.83734,
  "lon":              67.5938933,
  "ignition":         true,
  "gps_fix_age_sec":  11,

  "machinist":        "Сафаров Зариф Нармуминович",
  "machinist_id":     518764,
  "machinist_phone":  "+998994243664",
  "lok_nomer":        "007",
  "lok_name":         "UZTE-16M2"
}
```

| Maydon | Turi | Ma'nosi |
|---|---|---|
| `speed` | son | Tezlik, km/soat |
| `lat` / `lon` | son | Koordinata — xaritada ko'rsatish uchun |
| `ignition` | bool | Dvigatel yoqiqmi |
| `gps_fix_age_sec` | son | **GPS o'lchovi necha soniya eski.** Katta bo'lsa tezlik va koordinataga ishonmang |
| `machinist` | matn | Mashinist F.I.O. |
| `machinist_id` | son | `emm_id` — kadrlar tizimidagi raqami |
| `machinist_phone` | matn | Telefon |
| `lok_nomer` | matn | Lokomotiv raqami (`007`) |
| `lok_name` | matn | Modeli (`UZTE-16M2`) |

**Barcha maydonlar ixtiyoriy.** GPS ulanmagan yoki javob bermagan bo'lsa
ular umuman kelmaydi — server ularning yo'qligiga tayyor bo'lsin.

### `gps_fix_age_sec` nima uchun muhim

GPS qurilmasi doim yangi ma'lumot bermaydi. O'lchaganimizda:

| Holat | O'lchov yoshi |
|---|---|
| Dvigatel yoqiq | 4–18 soniya |
| Dvigatel o'chiq | 30 daqiqagacha |

Ya'ni `speed: 0` degani "hozir turibdi" degani emas — 30 daqiqa oldin
turgan bo'lishi mumkin. Saytda tezlik yoki koordinatani ko'rsatganda
`gps_fix_age_sec` katta bo'lsa, buni foydalanuvchiga bildirish kerak.

ARGUS o'z tomonida 120 soniyadan eski o'lchovni ishonchsiz deb biladi.

### Hisobotlarda

Soatlik va kunlik hisobotlarga **faqat shaxs va lokomotiv** qo'shiladi
(tezlik va koordinata emas — hisobot bir soat/kunni qamraydi):

```json
{ "kind": "report", "report": "daily", "...": "...",
  "machinist": "Сафаров Зариф Нармуминович", "machinist_id": 518764,
  "lok_nomer": "007", "lok_name": "UZTE-16M2" }
```

Shunda hisobotni **mashinist bo'yicha** filtrlash va ko'rsatish mumkin.

---

### `delayed_sec` nima uchun kerak

Internet uzilganda xabarlar navbatda turadi. Tarmoq qaytganda ular
yuboriladi, lekin `time` va `ts` — **hodisa sodir bo'lgan vaqt**, yuborilgan
vaqt emas. `delayed_sec` katta bo'lsa (masalan 3600), demak bu xabar bir
soat kechikkan. Saytda buni ko'rsatish foydali.

---

## 4. Buzilish turlari

| `type` | `label` | `detail` ichida nima keladi |
|---|---|---|
| `uyqu` | Uyqu | `Ko'z yumuq: 1.4 s` |
| `mikrouyqu` | Mikrouyqu | `Ko'z yumuq: 0.7 s` |
| `uyquchan` | Uyquchanlik belgilari | `PERCLOS: 24% (ostona 20/35%)` |
| `uyquchan_kr` | KRITIK uyquchanlik | `PERCLOS: 41% (ostona 20/35%)` |
| `pirpirash` | Sekin pirpirash (charchoq) | `Pirpirash: 553 ms (ostona 400 ms)` |
| `esnash` | Charchoq/esnash | — |
| `chalgish` | Chalg'ish | — |
| `telefon` | Telefon | `Ishonch: 0.61` |
| `sigaret` | Sigaret | — |
| `kamar` | Kamar yo'q | — |
| `kamera` | Kamera to'silgan | `Yorug'lik: 12 tafsilot: 8` |
| `yuz` | Yuz ko'rinmayapti | — |
| `yoq` | Haydovchi o'rnida yo'q | — |
| `klip` | Hodisa yozuvi | — (video biriktirilgan bo'ladi) |

Bir vaqtda bir nechta buzilish bo'lsa, rasm bilan kelgan so'rovda `type`
vergul bilan ajratiladi: `"chalgish,telefon"`.

---

## 5. Bitta hodisa — uch so'rov

Bu eng muhim qism. Bitta buzilish sayti uchun **uch marta** keladi:

```
1-so'rov   uid=2710416188e6   matn        "Buzilish: Telefon", detail bilan
2-so'rov   uid=2710416188e6   + photo     snap_20260917_143108.jpg
3-so'rov   uid=2710416188e6   + video     rec_20260917_143108.mp4
```

Uchalasida `uid` **bir xil**. Sayt ularni **bitta yozuvga** yig'ishi kerak.

**Video kechikib keladi** — klip hodisadan taxminan 5 soniya keyin yopiladi
va ovoz qo'shilgandan so'ng yuboriladi. Ya'ni 3-so'rov 1-so'rovdan 10–20
soniya keyin kelishi normal. Internet sekin bo'lsa yana ham kechroq.

Tavsiya etiladigan sxema:

```
incidents          (uid birlamchi kalit)
  uid, device, type, label, time, ts, detail
incident_files     (uid ga bog'langan)
  uid, kind ('photo'|'video'), fayl yo'li, msg_id
```

---

## 5a. Holat tugadi — `phase=end` (YANGI, 2026-09-24)

Ilgari davom etayotgan buzilish haqida takroriy so'rov kelardi (soatiga
30 tagacha). Endi **epizodga bitta** so'rov ketadi, tugaganda esa yana
bitta — yakuniy. Ortiqcha yuk yo'qoladi, ma'lumot esa to'liqroq bo'ladi.

```
1-so'rov   uid=2710416188e6   matn        "Buzilish: Haydovchi o'rnida yo'q"
2-so'rov   uid=2710416188e6   + photo
3-so'rov   uid=2710416188e6   + video
4-so'rov   uid=2710416188e6   detail="tugadi"   phase="end"   duration_sec=707.4
```

Yakuniy so'rovda ikkita qo'shimcha maydon bo'ladi:

| maydon | tur | ma'nosi |
|---|---|---|
| `phase` | string | doim `"end"`. Boshlanish so'rovlarida bu maydon **yo'q** |
| `duration_sec` | number | buzilish necha soniya davom etgani |

`uid` boshlanish so'rovi bilan **bir xil** — ya'ni bu yangi hodisa emas,
mavjud yozuvni yopish. Sayt tomonida:

```sql
UPDATE incidents
   SET ended_at = :ts, duration_sec = :duration_sec
 WHERE uid = :uid
```

### Muhim nozikliklar

**Yakuniy so'rov kelmasligi mumkin.** U faqat 30 soniyadan uzoq davom
etgan buzilishlarga yuboriladi (`INCIDENT_END_MIN`). Qisqa epizodlarda
boshlanish so'rovining o'zi yakuniy hisoblanadi — `ended_at` bo'sh
qolgani xato emas.

**Qurilma o'chib qolsa ham kelmaydi.** Tok uzilsa yoki dastur to'xtasa,
ochiq qolgan yozuvning yakunlovchisi hech qachon yetib bormaydi. Sayt
uzoq vaqt yopilmagan yozuvlarni o'zi yopishi kerak (masalan, oxirgi
hisobot vaqti bo'yicha) — aks holda ular abadiy "davom etyapti" bo'lib
qoladi.

**Yakuniy so'rov boshlanishdan oldin kelishi mumkin.** Internet uzilganda
so'rovlar navbatda turadi va tartibi o'zgarishi mumkin emas, lekin
boshlanish so'rovi 4xx xato bilan tashlab yuborilgan bo'lsa, yakuniy
so'rov "yo'q" uid bilan keladi. Bu holda uni yangi yozuv sifatida
saqlash kerak, tashlab yuborish emas.

---

## 5b. Buzilish QACHON yuborilmaydi (2026-09-24)

Bu bo'lim sayt tomonida "nega ba'zi buzilishlar kelmayapti" degan savol
chiqmasligi uchun. Quyidagi hollarda qurilma hech narsa yubormaydi —
bu nosozlik emas, ataylab shunday.

**1. Telefon 3 daqiqagacha.** Haydovchi telefonni olganda ovozli
ogohlantirish darhol ishlaydi, lekin buzilish sifatida qayd etilmaydi.
Faqat 3 daqiqadan oshgandagina so'rov yuboriladi. Qisqa qo'ng'iroqlar
saytga umuman tushmaydi.

Vaqt UZLUKSIZ emas, **oxirgi 10 daqiqadagi JAMI** hisoblanadi. Ya'ni
1 daqiqa + tanaffus + 2 daqiqa = 3 daqiqa deb sanaladi. Ilgari har
tanaffus hisoblagichni nolga tushirar va haydovchi qisqa tanaffuslar
bilan cheksiz foydalanishi mumkin edi.

**2. Poyezd to'xtaganda.** Tezlik 10 km/soatdan past bo'lsa, quyidagi
turlar buzilish hisoblanmaydi: `yoq` (o'rindan turish), `yuz`,
`chalgish`, `telefon`, `kamar`. Temir yo'l standarti shunday: hushyorlik
nazorati harakat paytida talab qilinadi. Uyquga oid turlar bu qoidaga
KIRMAYDI — ular to'xtab turganda ham yuboriladi.

GPS o'lchovi eskirgan bo'lsa (`gps_fix_age_sec` katta) poyezd
HARAKATDA deb hisoblanadi — ya'ni nazorat o'chib qolmaydi.

**3. Tasdiqlanmagan qisqa sakrash.** Yangi buzilish 0.6 soniya saqlanib
turishi kerak. Bir kadrlik aniqlash xatosi saytga chiqmaydi.

**4. Ko'z o'lchovi ishonchsiz bo'lganda.** Haydovchi qo'li bilan yuzini
bekitsa, ko'z nuqtalari qo'l ustiga tushadi va o'lchov ma'nosini
yo'qotadi. Bunday paytda uyquga oid turlar yuborilmaydi.

### Rasm qaysi paytdan olinadi

Hodisa rasmi signal chiqqan paytdagi kadr EMAS — buzilishning
o'rtasidan, taxminan 0.6 soniya oldingi kadr olinadi. Sabab: signal
buzilish bir necha soniya davom etgandan keyin chiqadi va o'sha
paytdagi kadrda buzilish ko'rinmasligi mumkin. Shuning uchun rasmdagi
vaqt belgisi `time` maydonidan bir oz oldinroq bo'lishi normal.

---

## 5v. `detail` maydonini USTIGA YOZMANG (2026-09-24)

Bitta hodisa bir necha so'rov bo'lib keladi va ularning hammasida
`detail` bo'lmaydi. Qurilma jurnalidan olingan haqiqiy misol:

```
uid=d2dae5a67203  type=mikrouyqu  detail="Ko'z yumuq: 1.0 s"   (matn)
uid=d2dae5a67203  type=mikrouyqu  detail YO'Q                  (rasm)
uid=d2dae5a67203  type=uyqu       detail="Ko'z yumuq: 2.1 s"   (matn)
```

Agar sayt `uid` bo'yicha yozuvni yangilaganda `detail` ni har safar
qayta yozsa, rasmli so'rov kelgach qiymat **yo'qoladi** va jadvalda
`-` bo'lib qoladi. Aynan shu holat kuzatildi.

**To'g'ri xatti-harakat:** so'rovda maydon YO'Q bo'lsa, bazadagi eski
qiymat saqlanib qolsin. Umuman olganda bu barcha maydonlarga tegishli
(`detail`, GPS maydonlari, `machinist` va h.k.) - qurilma faqat o'zida
bor ma'lumotni yuboradi, yo'q maydonni `null` deb tushunmang.

Qurilma tomonidan 2026-09-24 dan boshlab `detail` rasm va video
so'rovlariga ham biriktiriladi, ya'ni bu muammo ikki tomondan ham
yopilgan. Lekin qoida baribir kerak: boshqa maydonlar uchun ham amal
qiladi.

---

## 6. Takrorni aniqlash

Tarmoq xatosida biz **o'sha so'rovni qayta yuboramiz**. `msg_id` o'zgarmaydi.

```
if (bazada msg_id bor) -> 200 qaytaring, qayta yozmang
else                   -> yozing
```

Busiz internet beqaror bo'lganda bazada takroriy yozuvlar to'planadi.

---

## 7. Javob kodlari

| Kod | ARGUS nima qiladi |
|---|---|
| `2xx` | Yozuv navbatdan o'chiriladi — ish tugadi |
| `4xx` | **Tashlab yuboriladi.** Qayta urinish foydasiz deb hisoblanadi |
| `5xx` | Navbatda qoladi, 10 soniyada qayta urinadi |
| Tarmoq xatosi / timeout | Navbatda qoladi, qayta urinadi |

> `4xx` ni ehtiyotkorlik bilan qaytaring. Masalan token noto'g'ri bo'lsa
> `401` qaytarsangiz, o'sha xabar **butunlay yo'qoladi**. Vaqtinchalik
> muammolarda `5xx` qaytargan ma'qul.

---

## 8. Offline rejimi

Navbat `web_outbox.json` faylida saqlanadi. Bu degani:

- Internet uzilsa xabarlar **yo'qolmaydi**
- Tok uzilib kompyuter o'chsa ham navbat saqlanib qoladi
- Dastur qayta ishga tushganda navbat davom etadi
- Har 10 soniyada qayta urinadi, tarmoq qaytguncha

Fayl o'chirilgan rasm/video uchun avtomatik tozalanadi — mavjud bo'lmagan
faylni cheksiz yuborishga urinmaydi.

---

## 9. Hisobotlar

Buzilishlardan tashqari soatlik va kunlik hisobotlar ham keladi.
Bular **strukturali maydonlar** ko'rinishida — tayyor matn emas, shuning
uchun to'g'ridan-to'g'ri bazaga yozish va grafik chizish mumkin.

```json
{
  "msg_id":     "a1b2c3d4e5f60718",
  "kind":       "report",
  "report":     "hourly",
  "device":     "Lokomotiv-01",
  "time":       "2026-09-17 15:00:00",
  "ts":         1789640786.85,
  "period_sec": 3600.0,
  "mood": {
    "dominant": "betaraf",
    "samples":  1000,
    "counts":   { "betaraf": 820, "xursand": 140, "asabiy": 40 },
    "percent":  { "betaraf": 82.0, "xursand": 14.0, "asabiy": 4.0 }
  },
  "incidents": {
    "total":  4,
    "counts": { "telefon": 2, "uyqu": 1, "uyquchan_kr": 1 },
    "labels": { "telefon": "Telefon", "uyqu": "Uyqu",
                "uyquchan_kr": "KRITIK uyquchanlik" }
  }
}
```

| Maydon | Ma'nosi |
|---|---|
| `report` | `hourly` — har soatda (`REPORT_INTERVAL`)<br>`daily` — kuniga bir marta, `DAILY_REPORT_AT` vaqtida (standart 23:00) |
| `period_sec` | Hisobot qamragan davr (soniya). Kunlik hisobotda o'rniga `date` keladi |
| `mood.dominant` | Eng ko'p uchragan kayfiyat. Namuna bo'lmasa `null` |
| `mood.samples` | Nechta o'lchov asosida. Kam bo'lsa foizlarga ishonmang |
| `mood.counts` | Xom sanoq — o'zingiz qayta hisoblashingiz mumkin |
| `mood.percent` | Tayyor foiz, bir kasrgacha |
| `incidents.counts` | Tur bo'yicha **epizod** soni (kadr soni emas) |
| `incidents.labels` | O'sha turlarning o'zbekcha nomi — ko'rsatish uchun |

Kayfiyat qiymatlari: `betaraf`, `xursand`, `hayrat`, `xafa`, `asabiy`,
`jirkanish`, `qo'rquv`, `nafrat`. Yuz topilmagan kadrlar `-` bilan keladi.

Kunlik hisobotda `period_sec` o'rniga `date` bo'ladi:

```json
{ "kind": "report", "report": "daily", "date": "2026-09-17", "mood": {...}, "incidents": {...} }
```

> Telegram'ga baribir odam o'qiy oladigan matn yuboriladi — u alohida
> yo'l, saytga ta'sir qilmaydi.

---

## 10. Sinov uchun namuna

### curl — matnli xabar

```bash
curl -X POST https://sayt.uz/api/incidents \
  -H "Authorization: Bearer maxfiy-token" \
  -H "Content-Type: application/json" \
  -d '{"msg_id":"test001","uid":"evt001","kind":"incident","device":"Lokomotiv-01","type":"telefon","label":"Telefon","time":"2026-09-17 14:31:08","ts":1789648268.5,"detail":"Ishonch: 0.61","delayed_sec":0.4}'
```

### curl — rasm bilan

```bash
curl -X POST https://sayt.uz/api/incidents \
  -H "Authorization: Bearer maxfiy-token" \
  -F 'data={"msg_id":"test002","uid":"evt001","kind":"incident","device":"Lokomotiv-01","type":"telefon","label":"Telefon","time":"2026-09-17 14:31:08","ts":1789648268.5}' \
  -F "photo=@snap_20260917_143108.jpg"
```

### Eng sodda qabul qiluvchi (Flask)

```python
import json
from flask import Flask, request

app = Flask(__name__)
seen = set()                      # amalda — baza

@app.post("/api/incidents")
def incidents():
    if request.content_type.startswith("multipart/"):
        meta = json.loads(request.form["data"])
        photo = request.files.get("photo")
        video = request.files.get("video")
    else:
        meta = request.get_json()
        photo = video = None

    if meta["msg_id"] in seen:    # takror — jim qabul qilamiz
        return "", 200
    seen.add(meta["msg_id"])

    # ... uid bo'yicha guruhlab bazaga yozing ...
    if photo:
        photo.save(f"media/{meta['uid']}_{photo.filename}")
    if video:
        video.save(f"media/{meta['uid']}_{video.filename}")
    return "", 200
```

---

## 11. Tekshirish ro'yxati

Sayt tayyor bo'lganda quyidagilarni sinab ko'ring:

- [ ] Matnli xabar qabul qilinadi, `200` qaytadi
- [ ] Multipart so'rovda `data` maydonidan JSON o'qiladi
- [ ] Bir xil `msg_id` ikki marta kelsa **ikkinchisi yozilmaydi**
- [ ] Bir xil `uid` li uchta so'rov **bitta hodisaga** birikadi
- [ ] Video 20 soniya kechikib kelsa ham o'sha hodisaga qo'shiladi
- [ ] Katta `delayed_sec` bilan kelgan xabar ham qabul qilinadi
- [ ] Vaqtinchalik xatoda `5xx` qaytariladi (`4xx` emas)

Shundan keyin `app.py` da `WEBHOOK_URL` ni qo'yamiz va jonli sinaymiz.
