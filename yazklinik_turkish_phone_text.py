"""Turkish text cleanup for YazKlinik phone/STT/TTS flows.

The module keeps source literals ASCII-safe with unicode escapes where needed,
but returns real Turkish text at runtime.
"""
from __future__ import annotations

import re
import unicodedata

try:
    from yazklinik_textfix import fix_mojibake_text
except Exception:  # pragma: no cover - standalone fallback
    def fix_mojibake_text(value):
        return value


_PATTERN_REPLACEMENTS = (
    ("\\brandevu\\s+istiy[ou\\u0131]m\\b", "randevu istiyorum"),
    ("\\bistiy[ou\\u0131]m\\b", "istiyorum"),
    ("\\bistiyord[ou\\u0131]m\\b", "istiyordum"),
    ("\\bgel(?:i)?cem\\b", "gelece\u011fim"),
    ("\\bgid(?:i)?cem\\b", "gidece\u011fim"),
    ("\\byap(?:a|i)?cam\\b", "yapaca\u011f\u0131m"),
    ("\\bol(?:u|a)?cam\\b", "olaca\u011f\u0131m"),
    ("\\bar(?:a|i)?cam\\b", "arayaca\u011f\u0131m"),
    ("\\bver(?:i)?cem\\b", "verece\u011fim"),
    ("\\bal(?:a|i)?cam\\b", "alaca\u011f\u0131m"),
    ("\\bsu\\s+an\\b", "\u015fu an"),
    ("\\byar\\?\\s*n\\b", "yar\u0131n"),
    ("\\bon\\s+randevu\\b", "\u00f6n randevu"),
    ("\\bon\\s+hasta\\b", "\u00f6n hasta"),
    ("\\byardimc[\\u0131i]\\s+olabilirmisiniz\\b",
     "yard\u0131mc\u0131 olabilir misiniz"),
    ("\\bolabilirmiyim\\b", "olabilir miyim"),
    ("\\b(?:unlu|\\u00fcnl\\u00fc)\\s+harf\\b", "sesli harf"),
    ("\\b(?:unsuz|\\u00fcns\\u00fcz)\\s+harf\\b", "sessiz harf"),
    ("\\bvowel\\b", "sesli harf"),
    ("\\bconsonant\\b", "sessiz harf"),
)


_WORD_REPLACEMENTS = (
    ("musait", "m\u00fcsait"),
    ("gorusme", "g\u00f6r\u00fc\u015fme"),
    ("gorusmek", "g\u00f6r\u00fc\u015fmek"),
    ("gorusuruz", "g\u00f6r\u00fc\u015f\u00fcr\u00fcz"),
    ("goruselim", "g\u00f6r\u00fc\u015felim"),
    ("gorunen", "g\u00f6r\u00fcnen"),
    ("gordugunuz", "g\u00f6rd\u00fc\u011f\u00fcn\u00fcz"),
    ("gun", "g\u00fcn"),
    ("bugun", "bug\u00fcn"),
    ("yarin", "yar\u0131n"),
    ("obur", "\u00f6b\u00fcr"),
    ("ogle", "\u00f6\u011fle"),
    ("aksam", "ak\u015fam"),
    ("sabah", "sabah"),
    ("cuma", "cuma"),
    ("cumartesi", "cumartesi"),
    ("carsamba", "\u00e7ar\u015famba"),
    ("persembe", "per\u015fembe"),
    ("pazartesi", "pazartesi"),
    ("sali", "sal\u0131"),
    ("hastane", "hastane"),
    ("hasta", "hasta"),
    ("saglik", "sa\u011fl\u0131k"),
    ("dogum", "do\u011fum"),
    ("cocuk", "\u00e7ocuk"),
    ("ilac", "ila\u00e7"),
    ("recete", "re\u00e7ete"),
    ("sikayet", "\u015fikayet"),
    ("sigortanizin", "sigortan\u0131z\u0131n"),
    ("gecerli", "ge\u00e7erli"),
    ("gecerliligi", "ge\u00e7erlili\u011fi"),
    ("tesekkur", "te\u015fekk\u00fcr"),
    ("lutfen", "l\u00fctfen"),
    ("numarayi", "numaray\u0131"),
    ("numarasi", "numaras\u0131"),
    ("numarasini", "numaras\u0131n\u0131"),
    ("formatinda", "format\u0131nda"),
    ("adim", "ad\u0131m"),
    ("adini", "ad\u0131n\u0131"),
    ("adina", "ad\u0131na"),
    ("hastanin", "hastan\u0131n"),
    ("soyadini", "soyad\u0131n\u0131"),
    ("icin", "i\u00e7in"),
    ("hazirlik", "haz\u0131rl\u0131k"),
    ("hazirligi", "haz\u0131rl\u0131\u011f\u0131"),
    ("hazirligini", "haz\u0131rl\u0131\u011f\u0131n\u0131"),
    ("cevrilecek", "\u00e7evrilecek"),
    ("dosyasina", "dosyas\u0131na"),
    ("onaylarsa", "onaylarsa"),
    ("ulasabilecegimiz", "ula\u015fabilece\u011fimiz"),
    ("soyler", "s\u00f6yler"),
    ("soyleyin", "s\u00f6yleyin"),
    ("soyleyebilir", "s\u00f6yleyebilir"),
    ("soyleyebilirsiniz", "s\u00f6yleyebilirsiniz"),
    ("soyledigi", "s\u00f6yledi\u011fi"),
    ("istedigini", "istedi\u011fini"),
    ("ornek", "\u00f6rnek"),
    ("ayse", "Ay\u015fe"),
    ("yilmaz", "Y\u0131lmaz"),
    ("isterseniz", "\u0130sterseniz"),
    ("birakiyorum", "b\u0131rak\u0131yorum"),
    ("birakildi", "b\u0131rak\u0131ld\u0131"),
    ("baska", "ba\u015fka"),
    ("soyadim", "soyad\u0131m"),
    ("telefonum", "telefonum"),
    ("saatkac", "saat ka\u00e7"),
    ("kacta", "ka\u00e7ta"),
    ("kac", "ka\u00e7"),
    ("kayit", "kay\u0131t"),
    ("kaydet", "kaydet"),
    ("onayliyorum", "onayl\u0131yorum"),
    ("duyamadim", "duyamad\u0131m"),
    ("alamadim", "alamad\u0131m"),
    ("yakin", "yak\u0131n"),
    ("konusup", "konu\u015fup"),
    ("yaniti", "yan\u0131t\u0131"),
    ("isaretliyorum", "i\u015faretliyorum"),
    ("ayirayim", "ay\u0131ray\u0131m"),
    ("asistan", "asistan"),
    ("akilli", "ak\u0131ll\u0131"),
    ("zekaya", "zekaya"),
)


_FOREIGN_WORD_REPLACEMENTS = (
    ("appointment", "randevu"),
    ("reservation", "randevu"),
    ("patient", "hasta"),
    ("phone", "telefon"),
    ("call", "arama"),
    ("doctor", "doktor"),
    ("clinic", "klinik"),
    ("assistant", "asistan"),
    ("message", "mesaj"),
    ("date", "tarih"),
    ("time", "saat"),
    ("name", "ad"),
    ("surname", "soyad"),
    ("okey", "tamam"),
    ("okay", "tamam"),
    ("yes", "evet"),
    ("no", "hay\u0131r"),
    ("confirmed", "onayland\u0131"),
)


_ACRONYM_SPEECH = {
    "AI": "yapay zeka",
    "YZ": "yapay zeka",
    "TTS": "seslendirme",
    "STT": "ses tan\u0131ma",
    "SIP": "telefon",
    "USG": "u se ge",
    "TSH": "te se he",
    "FSH": "fe se he",
    "LH": "le he",
    "HCG": "he ce ge",
    "IVF": "i ve fe",
    "ICSI": "i ce se i",
    "NT": "ne te",
    "BPD": "be pe de",
    "HC": "he ce",
    "AC": "a ce",
    "FL": "fe le",
    "EFW": "e fe ve",
    "MR": "me re",
    "CT": "ce te",
    "EKG": "e ke ge",
    "D700": "de \u00fc\u00e7 y\u00fcz",
}


_LETTER_NAMES = {
    "A": "a",
    "B": "be",
    "C": "ce",
    "\u00c7": "\u00e7e",
    "D": "de",
    "E": "e",
    "F": "fe",
    "G": "ge",
    "\u011e": "yumu\u015fak ge",
    "H": "he",
    "I": "\u0131",
    "\u0130": "i",
    "J": "je",
    "K": "ke",
    "L": "le",
    "M": "me",
    "N": "ne",
    "O": "o",
    "\u00d6": "\u00f6",
    "P": "pe",
    "R": "re",
    "S": "se",
    "\u015e": "\u015fe",
    "T": "te",
    "U": "u",
    "\u00dc": "\u00fc",
    "V": "ve",
    "Y": "ye",
    "Z": "ze",
    "Q": "k\u00fc",
    "W": "\u00e7ift ve",
    "X": "iks",
}


def _case_like(source: str, target: str) -> str:
    source = str(source or "")
    if not source:
        return target
    if source[:1].isupper():
        return target[:1].upper() + target[1:]
    return target


def _replace_literal_word(text: str, source: str, target: str) -> str:
    pattern = r"(?<![\w])" + re.escape(source) + r"(?![\w])"

    def _repl(match):
        return _case_like(match.group(0), target)

    return re.sub(pattern, _repl, text, flags=re.IGNORECASE | re.UNICODE)


def _apply_pattern_replacements(text: str) -> str:
    for pattern, target in _PATTERN_REPLACEMENTS:
        text = re.sub(
            pattern,
            lambda m, t=target: _case_like(m.group(0), t),
            text,
            flags=re.IGNORECASE | re.UNICODE,
        )
    return text


def _apply_word_maps(text: str) -> str:
    for source, target in _FOREIGN_WORD_REPLACEMENTS:
        text = _replace_literal_word(text, source, target)
    for source, target in _WORD_REPLACEMENTS:
        text = _replace_literal_word(text, source, target)
    return text


def _spell_letter_sequence(match) -> str:
    raw = match.group(0)
    letters = re.findall(r"[A-Z\u00c7\u011e\u0130\u00d6\u015e\u00dcQWX]", raw)
    if len(letters) < 2:
        return raw
    return " ".join(_LETTER_NAMES.get(ch, ch.lower()) for ch in letters)


def _apply_tts_speech(text: str) -> str:
    text = re.sub(r"\bChat\s*GPT\b", "ak\u0131ll\u0131 asistan",
                  text, flags=re.IGNORECASE)
    for source, target in _ACRONYM_SPEECH.items():
        text = re.sub(r"(?<![\w])" + re.escape(source) + r"(?![\w])",
                      target, text, flags=re.IGNORECASE)
    # Existing legacy code can expand acronyms as "U S G"; make that Turkish.
    seq = r"\b(?:[A-Z\u00c7\u011e\u0130\u00d6\u015e\u00dcQWX][\s.]+){1,}[A-Z\u00c7\u011e\u0130\u00d6\u015e\u00dcQWX]\b"
    text = re.sub(seq, _spell_letter_sequence, text)
    return text


def normalize_turkish_phone_text(text, *, for_tts=False, max_chars=None,
                                 final_punctuation=False) -> str:
    """Normalize common phone/STT/TTS Turkish glitches."""
    s = str(text or "")
    if not s:
        return ""
    try:
        s = fix_mojibake_text(s)
    except Exception:
        pass
    s = unicodedata.normalize("NFC", s)
    s = (s.replace("\u201c", '"').replace("\u201d", '"')
           .replace("\u2018", "'").replace("\u2019", "'")
           .replace("\u2014", ", ").replace("\u2013", "-")
           .replace("\u2026", "."))
    s = re.sub(r"\s+", " ", s).strip()
    s = _apply_pattern_replacements(s)
    s = _apply_word_maps(s)
    if for_tts:
        s = _apply_tts_speech(s)
    s = re.sub(r"\s+([,.!?;:])", r"\1", s)
    # D700 2026-05-18: Eski regex sayilar arasinda da bosluk ekliyordu
    # ("19.05.2026" -> "19. 05. 2026") ve DD.MM.YYYY tarih parser'ini bozuyordu.
    # Lookahead (?=[^\s\d]) -> arkasinda space veya digit varsa dokunma; sadece
    # cumle aralarinda (harf basliyorsa) bosluk ekle.
    s = re.sub(r"([,.!?;])(?=[^\s\d])", r"\1 ", s)
    s = re.sub(r"(?<!\d):(?!\d)(?=[^\s])", ": ", s)
    s = re.sub(r"\s+", " ", s).strip()
    if max_chars and len(s) > int(max_chars):
        s = s[:int(max_chars)].rsplit(" ", 1)[0].rstrip(" ,;:")
    if final_punctuation and s and s[-1] not in ".!?":
        s += "."
    return s


def normalize_turkish_stt_text(text, **kwargs) -> str:
    return normalize_turkish_phone_text(text, for_tts=False, **kwargs)


def normalize_turkish_tts_text(text, **kwargs) -> str:
    return normalize_turkish_phone_text(text, for_tts=True, **kwargs)

