# -*- coding: utf-8 -*-
"""Ishonchli navbat — internet uzilsa yo'qolmaydi.

Bu fayl app.py dan ajratilgan — kod o'zgartirilmagan.
"""

import os
import json
import time
import uuid
import threading
import collections



class Outbox:
    """Ishonchli navbat: diskda saqlanadi, internet uzilsa yo'qolmaydi,
    tarmoq qaytganda qayta yuboriladi.

    Telegram'dagi mantiqning umumlashtirilgani — `deliver(item)` xato
    ko'tarsa element navbatda QOLADI va biroz kutib qayta urinadi."""

    def __init__(self, path, deliver, retry_sec=10.0):
        self.path = path
        self.deliver = deliver
        self.retry_sec = retry_sec
        self.q = collections.deque()
        self._lock = threading.Lock()
        self._load()
        threading.Thread(target=self._loop, daemon=True).start()

    def __len__(self):
        return len(self.q)

    def put(self, item):
        item.setdefault("ts", time.time())     # hodisa vaqti — kechikishni bilish uchun
        # Tarmoq xatosida element QAYTA yuboriladi. msg_id o'zgarmaydi,
        # shuning uchun sayt takroriy yozuvni shu bo'yicha tashlab yuboradi.
        item.setdefault("msg_id", uuid.uuid4().hex[:16])
        with self._lock:
            self.q.append(item); self._save()

    def _loop(self):
        while True:
            item = None
            with self._lock:
                if self.q:
                    item = self.q[0]
            if item is None:
                time.sleep(1); continue
            # Fayl o'chirilgan bo'lsa — bu elementni tashlab ketamiz
            miss = [k for k in ("photo", "video") if item.get(k) and not os.path.exists(item[k])]
            if miss:
                for k in miss:
                    item[k] = None
            try:
                self.deliver(item)
                with self._lock:
                    if self.q and self.q[0] is item:
                        self.q.popleft(); self._save()
            except Exception:
                time.sleep(self.retry_sec)      # offline — keyin qayta urinadi

    def _save(self):
        try:
            with open(self.path, "w", encoding='utf-8') as f:
                json.dump(list(self.q), f, ensure_ascii=False)
        except Exception:
            pass

    def _load(self):
        try:
            with open(self.path, encoding='utf-8') as f:
                for it in json.load(f):
                    self.q.append(it)
        except Exception:
            pass
