# Webhook `500` — xato hisoboti

**Endpoint:** `POST https://ai-project.das-uty.uz/api/argos/webhook`
**Sana:** 2026-09-18
**Xulosa:** Har qanday **to'g'ri** so'rov `500 Ichki server xatosi` qaytaradi.
Muammo payload da emas — so'rov autentifikatsiya va validatsiyadan **o'tadi**,
keyin handler ichida yiqiladi.

---

## 1. Qisqacha

| Bosqich | Holat |
|---|---|
| Sayt ishlayapti (`GET /`) | ✅ `200` |
| Endpoint mavjud | ✅ (`GET` → `404 Cannot GET` — to'g'ri, faqat POST) |
| Avtorizatsiya | ✅ noto'g'ri token → `401` |
| Validatsiya | ✅ noto'g'ri payload → `400` to'g'ri xabar bilan |
| **Saqlash** | ❌ **`500` — har doim** |

---

## 2. Nima ishlayapti

Bular **to'g'ri** javob berdi, ya'ni controller, guard va DTO validatsiyasi soz:

```
POST  (noto'g'ri token)          -> 401
POST  {"msg_id":"v1","kind":"incident"}   (uid yo'q)
                                 -> 400  ['uid is required for incident messages']
POST  '{buzilgan'                -> 400  ["Expected property name or '}' in JSON at position 1"]
POST  {}                         -> 400  ['msg_id should not be empty',
                                          'msg_id must be a string',
                                          'msg_id must be shorter than or equal to 64 characters']
GET   /api/argos/incidents       -> 401  Avtorizatsiya talab qilinadi
GET   /                          -> 200  (sayt ochiladi)
```

---

## 3. Nima ishlamayapti

`INSTRUCTION.md` dagi barcha to'rt turdagi so'rov sinaldi. **Hammasi `500`:**

| # | So'rov turi | Javob |
|---|---|---|
| 1 | Incident (matn, `application/json`) | `500` |
| 2 | Takror `msg_id` (o'sha so'rov ikkinchi marta) | `500` |
| 3 | Photo (`multipart`, `data` + `photo`) | `500` |
| 4 | Video (`multipart`, `data` + `video`, 1.5 MB) | `500` |
| 5 | Report (`kind: report`, `hourly`) | `500` |

Javob tanasi har doim bir xil:

```json
{
  "statusCode": 500,
  "message": "Ichki server xatosi",
  "path": "/api/argos/webhook",
  "timestamp": "2026-09-18T10:35:39.760Z"
}
```

---

## 4. Payload sabab EMAS — isbot

Buni ishonch bilan aytish mumkin, chunki:

**a) `INSTRUCTION.md` dagi aynan namuna ham `500` beradi.** 4.1-bo'limdagi
`test001` / `evt001` so'rovi nusxa ko'chirib yuborildi — natija `500`.

**b) Eng sodda so'rov ham `500` beradi.** Faqat uchta majburiy maydon:

```json
{"msg_id": "m1a2b3c4d5", "uid": "e1a2b3c4d5", "kind": "incident"}
```
→ `500`

**c) Maydonlar bittalab qo'shib sinaldi** — birortasi ham holatni o'zgartirmadi:

```
msg_id+uid+kind                          -> 500
  + device, type, label                  -> 500
  + time (matn)                          -> 500
  + ts (float)                           -> 500
  + ts (int)   <- turni almashtirish ham yordam bermadi
                                         -> 500
  + delayed_sec                          -> 500
  + detail                               -> 500
```

**d) Noto'g'ri so'rovlar esa to'g'ri `400` qaytaradi** (2-bo'limga qarang).

Ya'ni: validatsiya bosqichi **o'tadi**, undan keyingi bosqich yiqiladi.

---

## 5. Xato qayerda bo'lishi mumkin

So'rov zanjiri:

```
1. Controller                ✅ (404 emas, POST qabul qilinadi)
2. Auth guard                ✅ (noto'g'ri token -> 401)
3. DTO / ValidationPipe      ✅ (uid yo'q -> 400)
4. Service / saqlash         ❌ SHU YERDA
```

Eng ehtimolli ikkita sabab:

| Sabab | Qanday tekshirish |
|---|---|
| **Migratsiya bajarilmagan** — jadvallar yo'q | `argos_incidents`, `argos_incident_files`, `argos_reports`, `argos_webhook_messages` bazada bormi? |
| **Fayl papkasi yo'q yoki yozib bo'lmaydi** | `config.yaml` → `argos.folder` (`uploads/argos`) mavjudmi, huquqi bormi? |

Birinchisi ehtimoli yuqoriroq, chunki **matnli** so'rov ham yiqilyapti — u
umuman fayl bilan ishlamaydi, faqat bazaga yozadi.

---

## 6. Aniq sababni topish

`500` ning stack trace'i server logida bo'ladi:

```bash
pm2 logs --lines 50
# yoki
docker logs --tail 50 <konteyner-nomi>
# yoki
journalctl -u <servis-nomi> -n 50
```

Oxirgi so'rovlar vaqti (UTC): `2026-09-18T10:35:39` — `10:35:40`.

---

## 7. Tuzatilganini tekshirish

Bitta buyruq. Tokenni o'rniga qo'ying:

```bash
curl -i -X POST https://ai-project.das-uty.uz/api/argos/webhook \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"msg_id":"fixcheck001","uid":"fixevt001","kind":"incident","device":"Lokomotiv-01","type":"telefon","label":"Telefon","time":"2026-09-18 15:00:00","ts":1789700000,"detail":"Ishonch: 0.61","delayed_sec":0.4}'
```

Kutilayotgan javob:

```json
{"accepted":true,"duplicate":false,"kind":"incident","uid":"fixevt001","savedFiles":0}
```

So'ng **o'sha buyruqni ikkinchi marta** ishga tushiring — `200` va
`"duplicate": true` bo'lishi kerak, bazada yangi yozuv paydo bo'lmasligi kerak.

---

## 8. ARGUS tomonida holat

Hozircha hech narsa yo'qolmayapti:

- `500` "vaqtinchalik xato" deb qabul qilinadi
- Xabar `web_outbox.json` da **diskda** saqlanadi
- Har 10 soniyada qayta uriniladi
- Tok uzilsa ham navbat saqlanib qoladi

Sayt tuzalgan daqiqada navbatdagi hamma narsa avtomatik yetkaziladi.
ARGUS tomonida hech qanday o'zgarish kerak emas.

`INSTRUCTION.md` dagi talablar tekshirildi va bajarilgan:

- [x] `Authorization: Bearer <token>`
- [x] Har yuborishda `msg_id` yangi, qayta urinishda o'zgarmaydi
- [x] `incident` da `uid` bor
- [x] Matn / rasm / video bir xil `uid` bilan
- [x] Multipart da JSON `data` maydonida matn ko'rinishida
- [x] Fayl maydonlari `photo` va `video`
- [x] Video 1 GB dan kichik (kliplar 2–5 MB)
- [x] `400`/`401` da qayta urinilmaydi, `5xx` da urinilaveradi
- [x] Hisobotda `kind: report` va `report: hourly|daily`
