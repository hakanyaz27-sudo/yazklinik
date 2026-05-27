# -*- coding: utf-8 -*-
"""Tek seferlik: _TR_MONTH_NAMES / _TR_WEEKDAY_NAMES icindeki mojibake'yi
ASCII-guvenli \\u kacis dizileriyle dogru Turkceye cevirir. Kaynak ASCII kalir,
calisma aninda dogru Turkce uretir (telefon TTS dogru okur)."""
import re

P = r"D:\YazKlinik_Final_D500\yazklinik_web.py"
s = open(P, encoding="utf-8").read()

months = (
    '_TR_MONTH_NAMES = [\n'
    '    "", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",\n'
    '    "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık",\n'
    ']'
)
weekdays = (
    '_TR_WEEKDAY_NAMES = [\n'
    '    "Pazartesi", "Salı", "Çarşamba", "Perşembe",\n'
    '    "Cuma", "Cumartesi", "Pazar",\n'
    ']'
)

s, n1 = re.subn(r'_TR_MONTH_NAMES\s*=\s*\[[^\]]*\]', lambda m: months, s, count=1)
s, n2 = re.subn(r'_TR_WEEKDAY_NAMES\s*=\s*\[[^\]]*\]', lambda m: weekdays, s, count=1)

open(P, "w", encoding="utf-8").write(s)
print("months_replaced=", n1, "weekdays_replaced=", n2)
