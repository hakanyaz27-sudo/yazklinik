from __future__ import annotations

import re
from typing import Any, Callable


_MOJIBAKE_MARKERS = tuple(
    chr(codepoint) for codepoint in (
        0x00C2,  # Â
        0x00C3,  # Ã
        0x00C4,  # Ä
        0x00C5,  # Å
        0x00D0,  # Ð
        0x00D1,  # Ñ
        0x00E2,  # â
        0x00F0,  # ð
        0x0153,  # œ
        0x0161,  # š
        0x0178,  # Ÿ
        0x017E,  # ž
        0x20AC,  # €
        0x2122,  # ™
    )
)

_MOJIBAKE_SEQUENCES = (
    "\u011f\u0178",  # emoji bytes decoded as Windows-1254, e.g. ğŸ“Š
    "\u00e2\u0161",  # warning/check symbols decoded as Windows-1254
    "\u00ef\u00b8",  # emoji variation selector tail decoded as Windows-1254
)

_BROKEN_ICON_PREFIX_RE = re.compile(
    r"(?<![\w])(?:"
    r"[Â-ÆâðœšŸž€™ƒ]"
    r"|[ğış -¿]"
    r"|Y"
    r"){2,30}\s+(?=("
    r"Dashboard|Sesli|Mikrofon|Kayda|Kayıt|Kayit|Çevir|Cevir|Hasta|"
    r"Entegrasyon|Komuta|Randevu|Ayar|DICOM|PDF|HD Studio|Reçete|Recete|"
    r"YZ\s|Klinik|Önemli|Onemli|Yaşam|Yasam|"
    r"Bugünün|Bugunun|Hızlı|Hizli|Telefon|"
    r"İletişim|Iletisim|Tüm|Tum|Canlı|Canli|"
    r"Görüntüleme|Goruntuleme|"
    r"Çalışma|Calisma|Doğum|Dogum|Akıllı|Akilli|"
    r"Görev|Gorev|Onam|Imza|İmza|Bayrak|Tetkik|Manuel|Takip|Rapor|"
    r"Obstetrik|Jinekoloji|Medikal|Gebelik|Riskli|Guvenlik|Guvenlik|Otomatik|Kural|Tabanli|Kontroller|Istatistikler|Oncelik|Uyari|Sistem|Parametreleri|Islem"
    r"))",
    re.IGNORECASE,
)

_BROKEN_ARROW_PREFIX_RE = re.compile(
    r"(?<![\w])(?:"
    r"[Â-ÆâðœšŸž€™ƒ]"
    r"|[ğış -¿]"
    r"|Y"
    r"){2,30}\s+(?=(Dashboard|Hasta listesi|Hasta Listesi|Geri|Geliş|Gelis|Anasayfa|Ana sayfa))",
    re.IGNORECASE,
)

def _mojibake_score(text: str) -> int:
    return (
        sum(text.count(marker) for marker in _MOJIBAKE_MARKERS)
        + (4 * sum(text.count(seq) for seq in _MOJIBAKE_SEQUENCES))
    )


def _encode_with_byte_fallback(text: str, encoding: str) -> bytes | None:
    raw = bytearray()
    for ch in text:
        codepoint = ord(ch)
        if codepoint <= 0xFF:
            raw.append(codepoint)
            continue
        try:
            raw.extend(ch.encode(encoding))
        except UnicodeEncodeError:
            return None
    return bytes(raw)


def _repair_piece(value: str) -> str:
    """B406: cycle 4 -> 8 (triple/quad encoded mojibake icin).

    Score 'iyilesiyor mu' kuralina dayanir; sabitlendiginde durur.
    Legitimate Turkce karakterler (c, s, g, u, o, i, etc.) markers
    listesinde olmadigi icin score'a katilmaz, dolayisiyla onlara
    decode uygulanmaz.
    """
    current = value
    best_score = _mojibake_score(current)
    for _ in range(8):
        improved = False
        for encoding in ("cp1254", "cp1252", "latin-1"):
            try:
                encoded = _encode_with_byte_fallback(current, encoding)
                if encoded is None:
                    continue
                candidate = encoded.decode("utf-8")
            except UnicodeDecodeError:
                continue
            candidate_score = _mojibake_score(candidate)
            if candidate_score < best_score or (
                candidate_score == best_score
                and candidate != current
                and len(candidate) < len(current)
            ):
                current = candidate
                best_score = candidate_score
                improved = True
                break
        if not improved:
            break

    return current


def fix_mojibake_text(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value

    if _mojibake_score(value) == 0:
        return _final_cleanup(value)

    repaired = _repair_piece(value)
    repaired = _repair_segments(repaired)
    if repaired != value:
        return _final_cleanup(repaired)

    parts = re.split(r"(\s+)", value)
    changed = False
    for index, part in enumerate(parts):
        if not part or part.isspace() or _mojibake_score(part) == 0:
            continue
        repaired_part = _repair_piece(part)
        if repaired_part != part:
            parts[index] = repaired_part
            changed = True

    if changed:
        return _final_cleanup(_repair_segments("".join(parts)))
    return _final_cleanup(value)


def _repair_segments(value: str) -> str:
    """Repair remaining broken words inside mixed HTML / rich text strings."""
    current = value
    for _ in range(3):
        if _mojibake_score(current) == 0:
            break
        parts = re.split(r"(\s+|<[^>]*>)", current)
        changed = False
        for index, part in enumerate(parts):
            if not part or part.isspace():
                continue
            if part.startswith("<") and part.endswith(">"):
                repaired_tag = _repair_html_attributes(part)
                if repaired_tag != part:
                    parts[index] = repaired_tag
                    changed = True
                continue
            if _mojibake_score(part) == 0:
                continue
            repaired_part = _repair_piece(part)
            if repaired_part != part:
                parts[index] = repaired_part
                changed = True
        if not changed:
            break
        current = "".join(parts)
    return current


def _repair_html_attributes(tag: str) -> str:
    if not isinstance(tag, str) or _mojibake_score(tag) == 0:
        return tag

    def repl(match: re.Match) -> str:
        prefix, quote, body = match.group(1), match.group(2), match.group(3)
        if _mojibake_score(body) == 0:
            return match.group(0)
        return prefix + quote + _final_cleanup(_repair_piece(body)) + quote

    return re.sub(
        r"([A-Za-z_:][-A-Za-z0-9_:.]*\s*=\s*)([\"'])(.*?)\2",
        repl,
        tag,
    )


def _final_cleanup(value: str) -> str:
    """Clean common one-off fragments left after partial mojibake repair."""
    if not isinstance(value, str) or not value:
        return value
    replacements = {
        "\u00e2\u20ac\u2122": "'",
        "\u00e2\u20ac\u0153": '"',
        "\u00e2\u20ac\ufffd": '"',
        "\u00e2\u20ac\u201d": "-",
        "\u00e2\u20ac\u201c": "-",
        "\u00e2\u2020\u2019": "->",
        "\u00e2\u2020\u0090": "<-",
        "\u00e2\u2022\u0090": "",
        "\u00e2\u2022\u0091": "",
        "\u00e2\u2022\u0094": "",
        "\u00e2\u2022\u0097": "",
        "\u00e2\u2022\u009a": "",
        "\u00e2\u2022\u009d": "",
        "\u00e2\u20ac\u00a2": "-",
        "\u00e2\u0153\u201c": "OK",
        "\u00e2\u0153\u2026": "OK",
        "\u00e2\u0161": "UYARI",
        "\u00e2\u20ac ": "- ",
        "\u00c2\u0152\u201e": "Ac",
        "\u00c2\u0152": "Ac",
        "\u0152\u201e": "Ac",
        "\u008c": "Ac",
        "\u00c3\u201a\u00c2\u0152": "Ac",
        "\u00e2\u20ac\u201c": "-",
        "\u00e2\u2013\u00b8": ">",
        "\u2199": "->",
        "\u2192": "->",
        "\u2190": "<-",
        "\u00c2\u00a0": " ",
        "\u00c4\u00a2\u2022": "<-",
        "\u00c4\u00a2\u00e2\u20ac": "<-",
        "\u00c3\u00a2\u00e2\u20ac\u00a0\u00c2\u0090": "<-",
        "\u00c3\u00a2\u00e2\u20ac\u00a0\u00c2\u2122": "->",
        "\u00c3\u00a2\u00e2\u20ac\u00a0\u00e2\u20ac\u2122": "->",
        "\u00c4\u0178Y\u0178\u00a5": "",
        "\u011fY\u0178\u00a5": "",
        "\u011f\u0178\u017d\u00a4": "",
        "\u00c4\u0178\u00c5\u00b8\u00c2\u017d\u00c2\u00a4": "",
        "\u00c4\u0178\u00c5\u00b8\u00c2\u00a5": "",
        "\u00c4\u0178\u00c5\u00b8": "",
        "\u011f\u0178\u201d\u008d": "",
        "\u00e2\u20ac\u009d\u00c2\u008d": "",
        "\u201d\u008d": "",
        "\u00c3\u00a2\u00e2\u201a\u00ac\u00e2\u20ac\u009d": "-",
        "\u2014": "-",
        "\u00e2\u20ac\u00a0\u2022": "+",
        "\u00c3\u201e\u00c5\u00b8": "ğ",
        "\u00c3\u201e\u00c2\u00b1": "ı",
        "\u00c3\u0192\u00c2\u00bc": "ü",
        "\u00c3\u0192\u00c2\u00b6": "ö",
        "\u00c3\u0192\u00c2\u00a7": "ç",
        "\u00c3\u0192\u00c2\u015e": "Ş",
        "\u00c3\u0192\u00c2\u015f": "ş",
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    extra_replacements = {
        "CanlÃ„Â± Muayene KaydÃ„Â± (YZ Destekli)": "Canli Muayene Kaydi (YZ Destekli)",
        "baÃ…Å¸lat": "baslat",
        "konuÃ…Å¸": "konus",
        "iÃ…Å¸ler": "isler",
        "Kayıtlı değil": "Kayitli degil",
        "Kayıt": "Kayit",
        "tıkla": "tikla",
        "çıkarır": "cikarir",
        "yapılandırılmış": "yapilandirilmis",
    }
    for old, new in extra_replacements.items():
        value = value.replace(old, new)
    # Common UI mojibake fragments seen in live pages
    value = value.replace("GeliÃ…Å¸ler", "Gelisler")
    value = value.replace("GeliÃƒâ€¦Ã…Â¸ler", "Gelisler")
    value = value.replace("GeliÃ…Å¸", "Gelis")
    value = value.replace("geliÃ…Å¸", "gelis")
    value = value.replace("HastanÃ„Â±n", "Hastanin")
    value = value.replace("hatasÃ„Â±", "hatasi")
    value = value.replace("AÃƒÂ§", "Ac")
    value = value.replace("GÃƒÂ¶r", "Gor")
    value = value.replace("gÃƒÂ¶rÃƒÂ¼ntÃƒÂ¼", "goruntu")
    value = value.replace("HenÃƒÂ¼z", "Henuz")
    value = value.replace("KlasÃƒÂ¶r", "Klasor")
    value = value.replace("klasÃƒÂ¶r", "klasor")
    value = re.sub(r"\u011f\u0178[\u0080-\uffff]{0,4}", "", value)
    value = re.sub(
        r"(?m)^[^\w<]{0,14}Canl(?:Ã„Â±|ı)\s+Muayene\s+Kayd(?:Ã„Â±|ı)\s*\(YZ Destekli\)",
        "Canli Muayene Kaydi (YZ Destekli)",
        value,
    )
    value = re.sub(r"([\">])[^<>\n]{0,28}Doktor Sesi:", r"\1Doktor Sesi:", value)
    value = re.sub(r"([\">])[^<>\n]{0,28}Hasta Sesi:", r"\1Hasta Sesi:", value)
    value = re.sub(r"(?m)^[^\w<]{0,18}Doktor Sesi:", "Doktor Sesi:", value)
    value = re.sub(r"(?m)^[^\w<]{0,18}Hasta Sesi:", "Hasta Sesi:", value)
    value = re.sub(
        r"(?<![\w])[\u00a0-\u00bf]{1,5}\s+(?=(Doğuranlar|Dashboard|Hasta|"
        r"Yeni|Ara|Sesli|Mikrofon|Kayda|Kayıt|Çevir)\b)",
        "",
        value,
    )
    value = _BROKEN_ARROW_PREFIX_RE.sub("<- ", value)
    value = _BROKEN_ICON_PREFIX_RE.sub("", value)
    value = re.sub(
        r"(?m)^\s+(?=(Dashboard|Sesli|Mikrofon|Kayda|Kayıt|Kayit|Çevir|Cevir)\b)",
        "",
        value,
    )
    value = re.sub(r"(?m)^\s*[-•]\s*([-•])\s*", r"\1 ", value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    return value


def _fix_value(value: Any) -> Any:
    if isinstance(value, str):
        return fix_mojibake_text(value)
    if isinstance(value, list):
        return [_fix_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_fix_value(item) for item in value)
    return value


def _fix_all_string_args(args: tuple[Any, ...], kwargs: dict[str, Any]) -> tuple[tuple[Any, ...], dict[str, Any]]:
    new_args = tuple(_fix_value(arg) for arg in args)
    new_kwargs = {key: _fix_value(val) for key, val in kwargs.items()}
    return new_args, new_kwargs


def _wrap_method(
    cls: type,
    method_name: str,
    transformer: Callable[[tuple[Any, ...], dict[str, Any]], tuple[tuple[Any, ...], dict[str, Any]]],
) -> None:
    original = getattr(cls, method_name, None)
    if original is None or getattr(original, "_yazklinik_textfix_wrapped", False):
        return

    def wrapped(self, *args, **kwargs):
        new_args, new_kwargs = transformer(args, kwargs)
        return original(self, *new_args, **new_kwargs)

    wrapped._yazklinik_textfix_wrapped = True  # type: ignore[attr-defined]
    setattr(cls, method_name, wrapped)


def _wrap_init(cls: type | None) -> None:
    if cls is None:
        return
    original = getattr(cls, "__init__", None)
    if original is None or getattr(original, "_yazklinik_textfix_wrapped", False):
        return

    def wrapped(self, *args, **kwargs):
        new_args, new_kwargs = _fix_all_string_args(args, kwargs)
        return original(self, *new_args, **new_kwargs)

    wrapped._yazklinik_textfix_wrapped = True  # type: ignore[attr-defined]
    setattr(cls, "__init__", wrapped)


def _fix_arg(args: tuple[Any, ...], index: int) -> tuple[Any, ...]:
    if index >= len(args):
        return args
    mutable = list(args)
    mutable[index] = fix_mojibake_text(mutable[index])
    return tuple(mutable)


def patch_qt_text_apis(namespace: dict[str, Any]) -> None:
    if not namespace:
        return

    QWidget = namespace.get("QWidget")
    QLabel = namespace.get("QLabel")
    QAbstractButton = namespace.get("QAbstractButton")
    QPushButton = namespace.get("QPushButton")
    QToolButton = namespace.get("QToolButton")
    QCheckBox = namespace.get("QCheckBox")
    QRadioButton = namespace.get("QRadioButton")
    QGroupBox = namespace.get("QGroupBox")
    QMenu = namespace.get("QMenu")
    QToolBar = namespace.get("QToolBar")
    QAction = namespace.get("QAction")
    QStatusBar = namespace.get("QStatusBar")
    QComboBox = namespace.get("QComboBox")
    QListWidget = namespace.get("QListWidget")
    QListWidgetItem = namespace.get("QListWidgetItem")
    QTreeWidget = namespace.get("QTreeWidget")
    QTreeWidgetItem = namespace.get("QTreeWidgetItem")
    QTableWidget = namespace.get("QTableWidget")
    QTableWidgetItem = namespace.get("QTableWidgetItem")
    QTabWidget = namespace.get("QTabWidget")
    QLineEdit = namespace.get("QLineEdit")
    QTextEdit = namespace.get("QTextEdit")
    QPlainTextEdit = namespace.get("QPlainTextEdit")
    QTextBrowser = namespace.get("QTextBrowser")
    QMessageBox = namespace.get("QMessageBox")
    QInputDialog = namespace.get("QInputDialog")

    for cls in (
        QLabel,
        QPushButton,
        QToolButton,
        QCheckBox,
        QRadioButton,
        QGroupBox,
        QMenu,
        QAction,
        QComboBox,
        QListWidgetItem,
        QTreeWidgetItem,
        QTableWidgetItem,
        QLineEdit,
        QTextEdit,
        QPlainTextEdit,
        QTextBrowser,
    ):
        _wrap_init(cls)

    for cls, method_name in (
        (QWidget, "setWindowTitle"),
        (QWidget, "setToolTip"),
        (QLabel, "setText"),
        (QAbstractButton, "setText"),
        (QPushButton, "setText"),
        (QToolButton, "setText"),
        (QCheckBox, "setText"),
        (QRadioButton, "setText"),
        (QGroupBox, "setTitle"),
        (QMenu, "setTitle"),
        (QAction, "setText"),
        (QListWidgetItem, "setText"),
        (QTableWidgetItem, "setText"),
        (QLineEdit, "setText"),
        (QLineEdit, "setPlaceholderText"),
        (QTextEdit, "setText"),
        (QTextEdit, "setPlainText"),
        (QTextEdit, "setHtml"),
        (QTextEdit, "append"),
        (QTextEdit, "insertPlainText"),
        (QTextEdit, "setPlaceholderText"),
        (QPlainTextEdit, "setPlainText"),
        (QPlainTextEdit, "appendPlainText"),
        (QPlainTextEdit, "insertPlainText"),
        (QPlainTextEdit, "setPlaceholderText"),
        (QTextBrowser, "setText"),
        (QTextBrowser, "setPlainText"),
        (QTextBrowser, "setHtml"),
        (QTextBrowser, "append"),
        (QTextBrowser, "setPlaceholderText"),
    ):
        if cls is None:
            continue
        _wrap_method(cls, method_name, lambda args, kwargs: (_fix_arg(args, 0), kwargs))

    if QStatusBar is not None:
        _wrap_method(
            QStatusBar,
            "showMessage",
            lambda args, kwargs: (_fix_arg(args, 0), kwargs),
        )

    if QTreeWidgetItem is not None:
        _wrap_method(
            QTreeWidgetItem,
            "setText",
            lambda args, kwargs: (_fix_arg(args, 1), kwargs),
        )

    if QTabWidget is not None:
        _wrap_method(
            QTabWidget,
            "setTabText",
            lambda args, kwargs: (_fix_arg(args, 1), kwargs),
        )
        _wrap_method(QTabWidget, "addTab", _fix_all_string_args)
        _wrap_method(QTabWidget, "insertTab", _fix_all_string_args)

    for cls in (QMenu, QToolBar):
        if cls is not None:
            for method_name in ("addAction", "insertAction", "addMenu"):
                _wrap_method(cls, method_name, _fix_all_string_args)

    if QListWidget is not None:
        _wrap_method(QListWidget, "addItem", _fix_all_string_args)
        _wrap_method(QListWidget, "insertItem", _fix_all_string_args)
        _wrap_method(QListWidget, "addItems", _fix_all_string_args)

    if QTreeWidget is not None:
        _wrap_method(QTreeWidget, "setHeaderLabels", _fix_all_string_args)

    if QTableWidget is not None:
        _wrap_method(QTableWidget, "setHorizontalHeaderLabels", _fix_all_string_args)
        _wrap_method(QTableWidget, "setVerticalHeaderLabels", _fix_all_string_args)

    if QComboBox is not None:
        def _combo_add_item(args, kwargs):
            if len(args) >= 1 and isinstance(args[0], str):
                return _fix_arg(args, 0), kwargs
            if len(args) >= 2 and isinstance(args[1], str):
                return _fix_arg(args, 1), kwargs
            return args, kwargs

        def _combo_insert_item(args, kwargs):
            if len(args) >= 2 and isinstance(args[1], str):
                return _fix_arg(args, 1), kwargs
            if len(args) >= 3 and isinstance(args[2], str):
                return _fix_arg(args, 2), kwargs
            return args, kwargs

        _wrap_method(QComboBox, "addItem", _combo_add_item)
        _wrap_method(QComboBox, "insertItem", _combo_insert_item)
        _wrap_method(
            QComboBox,
            "setItemText",
            lambda args, kwargs: (_fix_arg(args, 1), kwargs),
        )
        _wrap_method(QComboBox, "addItems", _fix_all_string_args)

    if QMessageBox is not None:
        for method_name in ("setText", "setInformativeText", "setDetailedText", "setWindowTitle"):
            _wrap_method(
                QMessageBox,
                method_name,
                lambda args, kwargs: (_fix_arg(args, 0), kwargs),
            )

        for method_name in ("information", "warning", "critical", "question"):
            original = getattr(QMessageBox, method_name, None)
            if original is None or getattr(original, "_yazklinik_textfix_wrapped", False):
                continue

            def _make_box_wrapper(func):
                def wrapped(*args, **kwargs):
                    mutable = list(args)
                    if len(mutable) > 1:
                        mutable[1] = fix_mojibake_text(mutable[1])
                    if len(mutable) > 2:
                        mutable[2] = fix_mojibake_text(mutable[2])
                    return func(*tuple(mutable), **kwargs)

                wrapped._yazklinik_textfix_wrapped = True  # type: ignore[attr-defined]
                return wrapped

            setattr(QMessageBox, method_name, staticmethod(_make_box_wrapper(original)))

    if QInputDialog is not None:
        original_get_text = getattr(QInputDialog, "getText", None)
        if original_get_text is not None and not getattr(original_get_text, "_yazklinik_textfix_wrapped", False):
            def wrapped_get_text(*args, **kwargs):
                mutable = list(args)
                if len(mutable) > 1:
                    mutable[1] = fix_mojibake_text(mutable[1])
                if len(mutable) > 2:
                    mutable[2] = fix_mojibake_text(mutable[2])
                return original_get_text(*tuple(mutable), **kwargs)

            wrapped_get_text._yazklinik_textfix_wrapped = True  # type: ignore[attr-defined]
            setattr(QInputDialog, "getText", staticmethod(wrapped_get_text))
