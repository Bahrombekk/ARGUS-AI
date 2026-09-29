# -*- coding: utf-8 -*-
"""Telegram bot: xabar, rasm, video, buyruqlar.

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

import os
import json
import time
import uuid
import threading
import collections
from config import *
try:
    MEDIA_KEEP_SEC
except NameError:
    MEDIA_KEEP_SEC = 86400.0   # rasm/video internet yo'q bo'lsa shuncha s saqlanadi
from argus.utils import human_delay
try:
    import requests
except Exception:
    requests = None



class Telegram:
    """Telegram bot — obuna/tasdiqlash bilan. Super ADMIN (admin_id) doim oladi.
    Boshqa odam /start bossa → admin'ga id+ism va tasdiqlash tugmalari boradi;
    admin tasdiqlasa, o'sha odam ham hisobot/xabarlarni oladi. Ro'yxat
    subscribers.json da saqlanadi (qayta ishga tushirishда yo'qolmaydi).
    Xabarlar barcha tasdiqlanganlarga tarqatiladi (fon oqimда)."""
    def __init__(self, token, admin_id, enabled=True):
        self.base = f"https://api.telegram.org/bot{token}"
        self.admin = str(admin_id)
        self.ok = bool(enabled and requests is not None and token and admin_id)
        self.approved = set()
        self.pending = {}
        self._lock = threading.Lock()
        self._offset = None
        self.outbox = collections.deque()
        self._olock = threading.Lock()
        # Boshqaruv hooklari (headless — klaviatura o'rniga Telegram buyruqlari)
        self.cmd_report = None; self.cmd_snapshot = None; self.cmd_daily = None
        self.cmd_status = None; self.cmd_stop = None
        self.cmd_imei = None; self.cmd_ident = None
        self._load()
        self._load_outbox()
        if self.admin:
            self.approved.add(self.admin)
        if self.ok:
            if TELEGRAM_POLL:
                threading.Thread(target=self._poll_loop, daemon=True).start()
            else:
                print("Telegram: buyruq qabul qilish O'CHIQ "
                      "(bitta tokenda faqat bitta qurilma o'qiy oladi)")
            threading.Thread(target=self._outbox_loop, daemon=True).start()

    # ── Saqlash ──
    def _load(self):
        try:
            with open(SUBS_FILE, encoding='utf-8') as f:
                d = json.load(f)
            self.approved = set(str(x) for x in d.get("approved", []))
            self.pending = {str(k): v for k, v in d.get("pending", {}).items()}
        except Exception:
            pass

    def _save(self):
        try:
            with open(SUBS_FILE, "w", encoding='utf-8') as f:
                json.dump({"admin": self.admin, "approved": sorted(self.approved),
                           "pending": self.pending}, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("subs saqlash xato:", e)

    # ── Yuborish ──
    def _post(self, method, **kw):
        try:
            return requests.post(self.base + "/" + method, timeout=15, **kw)
        except Exception as e:
            print("Telegram xato:", e); return None

    def _to(self, chat, text):
        self._post("sendMessage", data={"chat_id": chat, "text": text})

    def broadcast_sync(self, text):
        """Darhol, sinxron (chiqishда). Offline bo'lsa jim o'tadi."""
        if not self.ok:
            return
        for chat in list(self.approved):
            self._to(chat, text)

    # ── Navbat (offline'да yo'qolmaydi; internet qaytса yuboriladi) ──
    def _enqueue(self, item):
        # Hodisa vaqtini NAVBATGA QO'YILGANDA yozib qo'yamiz. Internet uzilib
        # xabar ertasiga yetsa ham, u qachon sodir bo'lganini bilib turamiz.
        item.setdefault("ts", time.time())
        with self._olock:
            self.outbox.append(item); self._save_outbox()

    def _late_note(self, item):
        """Xabar sezilarli kechikib yuborilayotgan bo'lsa — ogohlantirish matni."""
        ts = item.get("ts")
        if not ts:
            return ""
        d = time.time() - ts
        if d < LATE_WARN_SEC:
            return ""
        return (f"\n⏱ KECHIKIB yuborildi ({human_delay(d)} oldin sodir bo'lgan) "
                f"— internet uzilgan edi.")

    # admin_only=True -> faqat adminning shaxsiy chatiga (guruhga EMAS).
    # Poyezd to'xtaganda buzilishlar shu yo'l bilan ketadi (2026-09-26).
    def send(self, text, admin_only=False):
        if self.ok:
            it = {"kind": "text", "text": text}
            if admin_only and self.admin:
                it["to"] = [self.admin]
            self._enqueue(it)

    def send_photo(self, path, caption="", admin_only=False):
        if self.ok and os.path.exists(path):
            it = {"kind": "photo", "path": path, "caption": caption}
            if admin_only and self.admin:
                it["to"] = [self.admin]
            self._enqueue(it)

    def send_video(self, path, caption="", admin_only=False):
        if self.ok and os.path.exists(path):
            it = {"kind": "video", "path": path, "caption": caption}
            if admin_only and self.admin:
                it["to"] = [self.admin]
            self._enqueue(it)

    def _check(self, r, chat=None):
        """Telegram javobini tekshiradi.

        Ilgari javob UMUMAN qaralmasdi: 429 (limit oshdi) kelganda ham
        xabar "yuborildi" deb navbatdan o'chirilardi, ya'ni jimgina
        yo'qolardi. 100 qurilma bitta chatga yozganda limit doimiy
        oshadi, shuning uchun bu muhim."""
        if r.status_code == 429:
            wait = 5.0
            try:
                wait = float(r.json().get("parameters", {}).get("retry_after", 5))
            except Exception:
                pass
            wait = min(wait, TELEGRAM_MAX_RETRY_WAIT)
            print("Telegram: limit oshdi, %.0f s kutiladi (xabar saqlanadi)" % wait)
            time.sleep(wait)
            raise RuntimeError("telegram 429")      # navbatda qoladi
        if r.status_code >= 500:
            raise RuntimeError("telegram %d" % r.status_code)
        if r.status_code >= 400:
            try:
                desc = r.json().get("description", "")
            except Exception:
                desc = (r.text or "")[:150]
            # Obunachi botni bloklagan bo'lsa, har xabarda bitta so'rov
            # behuda ketadi va jurnal to'ladi. 100 qurilmada bu 100 barobar.
            # Shuning uchun bunday chat ro'yxatdan chiqariladi (admin emas).
            dead = any(k in desc.lower() for k in
                       ("blocked by the user", "user is deactivated",
                        "chat not found", "bot was kicked"))
            if dead and chat and str(chat) != str(self.admin):
                with self._lock:
                    self.approved.discard(str(chat)); self._save()
                print("Telegram: %s botni bloklagan - ro'yxatdan chiqarildi" % chat)
                self._post("sendMessage", data={
                    "chat_id": self.admin,
                    "text": "ℹ %s botni bloklagan va obunachilar "
                            "ro'yxatidan chiqarildi. Qaytarish uchun u "
                            "/start yozsin." % chat})
            else:
                print("Telegram rad etdi (%d): %s" % (r.status_code, desc[:150]))
        return r

    def _deliver(self, item):
        """Bitta elementni barcha tasdiqlanganlarga yuboradi. Tarmoq xatosida
        istisno ko'taradi (navbatда qoladi, keyin qayta urinadi)."""
        k = item["kind"]
        late = self._late_note(item)          # navbatda uzoq turgan bo'lsa — belgi
        # Chat bo'yicha "yetdi" belgisi: uzuq tarmoqda bitta chatda xato
        # bo'lsa BUTUN xabar qayta urinilar edi -> oldingi chatlar takror
        # olardi, oxirgi chat (guruh) hech qachon yetmasdi. Endi faqat
        # qolgan chatlarga yuboriladi; progress outbox.json da saqlanadi.
        done = item.setdefault("done", [])
        # "to" bo'lsa — faqat shu chatlarga (masalan, faqat admin)
        targets = item.get("to") or list(self.approved)
        for chat in list(targets):
            if str(chat) in done:
                continue
            if k == "text":
                self._check(requests.post(self.base + "/sendMessage",
                            data={"chat_id": chat, "text": item["text"] + late},
                            timeout=15), chat)
            elif k == "photo":
                with open(item["path"], "rb") as f:
                    self._check(requests.post(self.base + "/sendPhoto",
                                data={"chat_id": chat,
                                      "caption": item.get("caption", "") + late},
                                files={"photo": f}, timeout=60), chat)
            elif k == "video":
                with open(item["path"], "rb") as f:
                    self._check(requests.post(self.base + "/sendVideo",
                                data={"chat_id": chat,
                                      "caption": item.get("caption", "") + late},
                                files={"video": f}, timeout=180), chat)
            done.append(str(chat))
            with self._olock:
                self._save_outbox()

    def _outbox_loop(self):
        while True:
            item = None
            with self._olock:
                if self.outbox:
                    # MATN media'dan OLDIN: navbat boshida video (3 chat x 180 s)
                    # tursa, "ulandi"/buzilish matnlari minutlab kutardi.
                    item = next((it for it in self.outbox if it["kind"] == "text"),
                                self.outbox[0])
            if item is None:
                time.sleep(1); continue
            if item["kind"] in ("photo", "video") and not os.path.exists(item.get("path", "")):
                with self._olock:
                    try: self.outbox.remove(item)
                    except ValueError: pass
                    self._save_outbox()
                continue
            try:
                self._deliver(item)
                with self._olock:
                    try: self.outbox.remove(item)
                    except ValueError: pass
                    self._save_outbox()
            except Exception as e:
                # TARMOQ xatosi (internet yo'q, taymaut) — bu Telegram'ning rad etishi
                # emas: media SAQLANADI va internet qaytguncha kutiladi (2026-09-29:
                # lokda internet tez-tez uzilib, rasm/video 6 urinishda tashlanib
                # ketardi, matn esa yetib borardi). Faqat API xatosi (4xx, masalan
                # fayl juda katta) 6 urinishdan keyin tashlanadi. Media 24 soatdan
                # eski bo'lsa ham tashlanadi (dalil endi kech).
                net = (requests is not None and
                       isinstance(e, (requests.ConnectionError, requests.Timeout)))
                if net:
                    item["net_fail"] = item.get("net_fail", 0) + 1
                    age = time.time() - item.get("ts", time.time())
                    if item["kind"] in ("photo", "video") and age > MEDIA_KEEP_SEC:
                        with self._olock:
                            try: self.outbox.remove(item)
                            except ValueError: pass
                            self._save_outbox()
                        print("Telegram: %s %.0f soat kutdi, tashlandi (internet yo'q)"
                              % (item["kind"], age / 3600))
                        continue
                    time.sleep(min(60, 10 * item["net_fail"]))   # internet qaytguncha
                    continue
                item["tries"] = item.get("tries", 0) + 1
                if item["kind"] in ("photo", "video") and item["tries"] >= 6:
                    # Telegram rad etdi (4xx) — 6 urinishdan keyin tashlanadi
                    with self._olock:
                        try: self.outbox.remove(item)
                        except ValueError: pass
                        self._save_outbox()
                    print("Telegram: %s %d urinishdan keyin tashlandi (%s)"
                          % (item["kind"], item["tries"], repr(e)[:80]))
                    continue
                time.sleep(10)

    def _save_outbox(self):
        try:
            with open(OUTBOX_FILE, "w", encoding='utf-8') as f:
                json.dump(list(self.outbox), f, ensure_ascii=False)
        except Exception:
            pass

    def _load_outbox(self):
        try:
            with open(OUTBOX_FILE, encoding='utf-8') as f:
                for it in json.load(f):
                    self.outbox.append(it)
        except Exception:
            pass

    # ── Qabul (long-polling) ──
    def _poll_loop(self):
        while True:
            try:
                params = {"timeout": 50}
                if self._offset is not None:
                    params["offset"] = self._offset
                r = requests.get(self.base + "/getUpdates", params=params, timeout=60)
                if r.status_code == 409:
                    # Boshqa qurilma ham shu tokenni o'qiyapti. Ikkalasi ham
                    # buyruqlarni yo'qotadi, shuning uchun o'zimiz to'xtaymiz.
                    print("Telegram: 409 CONFLICT - bu tokenni boshqa qurilma "
                          "o'qiyapti. Buyruq qabul qilish to'xtatildi.")
                    return
                for up in r.json().get("result", []):
                    self._offset = up["update_id"] + 1
                    self._handle(up)
            except Exception:
                time.sleep(3)

    def _handle(self, up):
        if "callback_query" in up:
            self._on_callback(up["callback_query"]); return
        msg = up.get("message") or {}
        frm = msg.get("from", {})
        cid = str((msg.get("chat") or {}).get("id"))
        text = (msg.get("text") or "").strip()
        nm = frm.get("first_name", "") or "-"
        if frm.get("username"):
            nm += f" (@{frm['username']})"
        if text == "/start":
            self._on_start(cid, nm)
        elif cid == self.admin and text.startswith("/approve"):
            p = text.split()
            if len(p) >= 2: self._approve(p[1])
        elif cid == self.admin and text.startswith("/deny"):
            p = text.split()
            if len(p) >= 2: self._deny(p[1])
        elif cid == self.admin and text.startswith("/list"):
            a = "\n".join(sorted(self.approved)) or "-"
            pd = "\n".join(f"{k} — {v}" for k, v in self.pending.items()) or "-"
            self._to(self.admin, f"Tasdiqlangan:\n{a}\n\nKutayotgan:\n{pd}")
        elif cid == self.admin and text.startswith("/report"):
            if self.cmd_report:
                self.send(self.cmd_report())
        elif cid == self.admin and text.startswith("/kun"):
            if self.cmd_daily:
                self.send(self.cmd_daily())
        elif cid == self.admin and text.startswith("/snapshot"):
            if self.cmd_snapshot:
                self.cmd_snapshot()
        elif cid == self.admin and text.startswith("/imei"):
            # Maydonda monitor yo'q - IMEI shu buyruq bilan o'rnatiladi
            p = text.split()
            if len(p) < 2 or not p[1].strip().isdigit():
                self._to(self.admin, "Ishlatish: /imei 350612076914389")
            elif self.cmd_imei:
                self._to(self.admin, self.cmd_imei(p[1].strip()))
        elif cid == self.admin and text.startswith("/id"):
            self._to(self.admin, self.cmd_ident() if self.cmd_ident else "-")
        elif cid == self.admin and text.startswith("/status"):
            self._to(self.admin, self.cmd_status() if self.cmd_status else "ishlayapti")
        elif cid == self.admin and text.startswith("/stop"):
            self._to(self.admin, "ARGUS AI to'xtatilmoqda...")
            if self.cmd_stop:
                self.cmd_stop()
        elif cid == self.admin and text.startswith("/help"):
            self._to(self.admin, "Buyruqlar:\n"
                                 "/id — qurilma va lokomotiv ma'lumoti\n"
                                 "/imei <raqam> — lokomotiv GPS IMEI sini o'rnatish\n"
                                 "/status — qisqa holat\n"
                                 "/snapshot — hozirgi kadr\n"
                                 "/report — soatlik, /kun — kunlik hisobot\n"
                                 "/stop — to'xtatish\n"
                                 "/list /approve <id> /deny <id>")

    def _on_start(self, cid, name):
        if cid in self.approved:
            self._to(cid, "Siz allaqachon ulangansiz. ARGUS AI hisobotlari sizga keladi.")
            return
        with self._lock:
            self.pending[cid] = name; self._save()
        self._to(cid, "So'rovingiz yuborildi. Admin tasdiqlashini kuting.")
        kb = {"inline_keyboard": [[
            {"text": "✅ Tasdiqlash", "callback_data": f"approve:{cid}"},
            {"text": "❌ Rad etish", "callback_data": f"deny:{cid}"}]]}
        self._post("sendMessage", data={"chat_id": self.admin,
                   "text": f"\U0001F195 Yangi foydalanuvchi:\n{name}\nID: {cid}",
                   "reply_markup": json.dumps(kb)})

    def _on_callback(self, cq):
        frm = str((cq.get("from") or {}).get("id"))
        data = cq.get("data", "")
        if frm != self.admin:
            self._post("answerCallbackQuery",
                       data={"callback_query_id": cq["id"], "text": "Faqat admin"})
            return
        if data.startswith("approve:"):
            self._approve(data.split(":", 1)[1]); res = "Tasdiqlandi"
        elif data.startswith("deny:"):
            self._deny(data.split(":", 1)[1]); res = "Rad etildi"
        else:
            res = "?"
        self._post("answerCallbackQuery",
                   data={"callback_query_id": cq["id"], "text": res})

    def _approve(self, cid):
        cid = str(cid)
        with self._lock:
            name = self.pending.pop(cid, cid); self.approved.add(cid); self._save()
        self._to(cid, "✅ Tasdiqlandingiz! Endi ARGUS AI hisobotlari sizga ham keladi.")
        self._to(self.admin, f"✅ Tasdiqlandi: {name} ({cid})")

    def _deny(self, cid):
        cid = str(cid)
        with self._lock:
            name = self.pending.pop(cid, cid); self._save()
        self._to(cid, "❌ So'rovingiz rad etildi.")
        self._to(self.admin, f"❌ Rad etildi: {name} ({cid})")
