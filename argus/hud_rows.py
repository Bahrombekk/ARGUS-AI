# -*- coding: utf-8 -*-
"""HUD panel qatorlari va xavf banneri matni — loop.py dan ajratilgan."""
from argus.settings import *   # noqa: F401,F403
from argus.utils import human_dur

BANNER_MSG = {"uyqu": "UYQU! Uyg'oning", "mikrouyqu": "MIKROUYQU aniqlandi",
              "uyquchan": "Uyquchanlik belgilari", "uyquchan_kr": "KRITIK uyquchanlik",
              "pirpirash": "Sekin pirpirash", "sigaret": "SIGARET aniqlandi",
              "telefon": "TELEFON aniqlandi", "esnash": "CHARCHOQ / esnash",
              "chalgish": "CHALG'ISH! Old tomonga qarang",
              "kamar": "Xavfsizlik KAMARI yo'q", "kamera": "KAMERA TO'SILGAN!",
              "yuz": "YUZ KO'RINMAYAPTI!", "yoq": "HAYDOVCHI O'RNIDA YO'Q"}
CRIT_TAGS = {"uyqu", "mikrouyqu", "uyquchan_kr", "kamera"}


def banner(active):
    """(matn, kritikmi) yoki (\"\", False)."""
    if not active:
        return "", False
    crit = bool(CRIT_TAGS & set(active))
    return "   •   ".join(BANNER_MSG.get(a, a.upper()) for a in active), crit


def build_rows(fr, an, active, gps, cur_mood, now):
    """Panel qatorlari — faqat yoqilgan funksiyalar (dinamik balandlik).
    fr — FrameResult, an — FrameAnalyzer (perclos.ready, grace uchun)."""
    face_found = fr.face_found
    eye_txt = ({"open": "OCHIQ", "half": "YARIM", "closed": "YUMUQ"}.get(fr.eye_state, "-")
               if face_found else "-")
    belt = fr.belt
    belt_txt = "TAQILGAN" if belt is True else ("YO'Q" if belt is False else "-")
    rows = []
    if ENABLE_DROWSY:
        # Bosh egilgan bo'lsa o'lchov ishonchsizligini OCHIQ ko'rsatamiz
        txt = (eye_txt if fr.eye_reliable
               else ("BEKILGAN" if fr.eye_shaky else "BOSH PAST"))
        rows.append(("Ko'z", txt, not (fr.drowsy_al or fr.micro_al), not face_found))
    if ENABLE_PERCLOS:
        # Oyna to'lmaguncha "..." — natija hali ishonchsiz
        rd = an.perclos.ready()
        p_txt = (f"{fr.perclos_val*100:.0f}%" if rd else "yig'ilmoqda")
        rows.append(("PERCLOS", p_txt, not (fr.perclos_warn or fr.perclos_crit), not rd))
    if ENABLE_BLINK:
        b_txt = (f"{fr.blink_ms:.0f} ms" if fr.blink_ms is not None else "yig'ilmoqda")
        rows.append(("Pirpirash", b_txt, not fr.blink_slow, fr.blink_ms is None))
    if gps is not None:
        # Tezlik + ma'lumot eskirganini ham ko'rsatamiz
        if gps.speed is None:
            s_txt, s_ok = ("GPS yo'q", False)
        elif not gps.fix_fresh():
            # O'lchov eskirgan — tezlikka ishonib bo'lmaydi, shuning
            # uchun "harakatda" deb hisoblanadi. Buni ochiq yozamiz,
            # aks holda "0 km/s harakatda" ziddiyatli ko'rinadi.
            age = gps.fix_age
            qachon = ((f"{age/60:.0f} daq" if age < 5400 else f"{age/3600:.1f} soat")
                      if age else "?")
            s_txt = f"noma'lum ({qachon} oldin {float(gps.speed):.0f} km/s)"
            s_ok = False
        else:
            mov = gps.is_moving()
            s_txt = f"{float(gps.speed):.0f} km/s" + (" harakatda" if mov else " to'xtagan")
            s_ok = True
        rows.append(("Tezlik", s_txt, s_ok))
    if ENABLE_YAWN:
        rows.append(("Og'iz", "ESNASH" if fr.yawn_al else ("OCHIQ" if fr.yawn else "YOPIQ"),
                     not fr.yawn_al))
    if ENABLE_DISTRACT:
        rows.append(("Qarash", "CHETGA" if fr.looking_away else ("OLD" if face_found else "-"),
                     not fr.distract_al, not face_found))
    # Yuz yo'q, lekin signal chiqmagan bo'lsa (poyezd to'xtagan yoki
    # vaqt hali to'lmagan) — kulrang. Qizil faqat haqiqiy buzilishda.
    _fa = ("yuz" in active) or ("yoq" in active)
    rows.append(("Yuz", "BOR" if face_found else "YO'Q",
                 face_found or not _fa, not face_found and not _fa))
    if ENABLE_MOOD:
        rows.append(("Kayfiyat", cur_mood.upper() if cur_mood else "-", True))
    if ENABLE_PHONE:
        if not fr.phone_al:
            rows.append(("Telefon", "-", True))
        elif "telefon" not in active:
            # Poyezd to'xtagan — GPS filtri buni buzilish deb hisoblamaydi.
            # Ekranda ham qizil ko'rsatmaymiz, aks holda panel tizim
            # aslida qilmayotgan narsani da'vo qilgan bo'lardi.
            rows.append(("Telefon", "aniqlandi (to'xtagan)", True))
        else:
            # Ruxsat etilgan vaqt ichida — hisoblagich ko'rsatiladi,
            # lekin bu hali buzilish emas (yashil).
            lim = GRACE_SEC.get("telefon")
            el = an.grace.elapsed("telefon", now)
            if lim and el is not None and el < lim:
                rows.append(("Telefon", f"{human_dur(lim - el)} qoldi", True))
            else:
                rows.append(("Telefon", "ANIQLANDI", False))
    if ENABLE_SMOKING:
        rows.append(("Sigaret", "ANIQLANDI" if fr.smoke_al else "-", not fr.smoke_al))
    if ENABLE_SEATBELT:
        rows.append(("Kamar", belt_txt, not fr.belt_al))
    if ENABLE_TAMPER:
        rows.append(("Kamera", "TO'SILGAN" if fr.tamper_al else "OCHIQ", not fr.tamper_al))
    return rows
