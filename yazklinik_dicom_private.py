"""GE/Voluson private DICOM measurement probe for YazKlinik.

This module does not try to reverse-engineer every proprietary 4DView
structure. It safely reads the text-like GE/Kretz private payloads that
ViewPoint can understand, extracts measurement candidates, and reports when
only an opaque private block exists.
"""

from __future__ import annotations

import io
import json
import re
from typing import Any, Dict, Iterable, List, Tuple


MEASUREMENT_ALIASES = {
    "CRL": "CRL",
    "BPD": "BPD",
    "HC": "HC",
    "AC": "AC",
    "FL": "FL",
    "NT": "NT",
    "GS": "GS",
    "YS": "YS",
    "AFI": "AFI",
    "EFW": "EFW",
    "AOF": "EFW",
    "FHR": "FHR",
    "FKA": "FHR",
    "GA": "GA",
    "AUA": "GA",
    "EDD": "EDD",
    "EDC": "EDD",
}


TEXT_MEASUREMENT_RE = re.compile(
    r"(?<![A-Za-z0-9])"
    r"(CRL|BPD|HC|AC|FL|NT|GS|YS|AFI|EFW|AOF|FHR|FKA)"
    r"(?![A-Za-z0-9])"
    r"[\s:=/-]{0,18}"
    r"([0-9]{1,5}(?:[.,][0-9]+)?)"
    r"\s*(mm|cm|g|gr|gram|bpm|at[iı]m)?",
    re.IGNORECASE,
)


GA_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:GA|AUA|EGA|Gebelik\s*haftasi|Gebelik\s*haftası)"
    r"(?![A-Za-z0-9])[\s:=/-]{0,18}"
    r"([0-9]{1,2}\s*(?:w|hf|\+)\s*[0-9]{0,1})",
    re.IGNORECASE,
)


EDD_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:EDD|EDC|TDT|Tahmini\s*dogum|LMP_EDD_DOC)"
    r"(?![A-Za-z0-9])[\s:=/'\"]{0,24}"
    r"([0-9]{4}[-./][0-9]{1,2}[-./][0-9]{1,2}|"
    r"[0-9]{1,2}[-./][0-9]{1,2}[-./][0-9]{2,4})",
    re.IGNORECASE,
)


VOLUSON_OB_LINE_RE = re.compile(
    r"(?i)(?:^|[\s\r\n])OB_"
    r"(CRL|BPD|HC|AC|FL|NT|GS|YS|AFI|EFW|AOF|FHR|FKA)"
    r"[A-Z0-9_./-]*[\t ]+"
    r"([0-9]{1,5}(?:[.,][0-9]+)?)"
    r"(?::[^\t\r\n ]*)?[\t ]+"
    r"(mm|cm|g|gr|bpm)?\b"
)


PRIVATE_HINT_RE = re.compile(
    r"KRETZ|GEMS|GE\s*MEDICAL|VOLUSON|4DVIEW|PRIVATE_VERSION|OB_",
    re.IGNORECASE,
)


def _clean_text(value: Any, limit: int = 1200) -> str:
    text = str(value or "")
    text = text.replace("\x00", " ")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]+", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()[:limit]


def _tag_group(tag: str) -> int:
    try:
        return int(str(tag).split(",", 1)[0], 16)
    except Exception:
        return 0


def _is_private_tag(tag: str) -> bool:
    group = _tag_group(tag)
    return bool(group and group % 2 == 1)


def _reasonable(name: str, value: str, unit: str) -> bool:
    try:
        number = float(str(value).replace(",", "."))
    except Exception:
        return name in {"GA", "EDD"}
    name = MEASUREMENT_ALIASES.get(str(name).upper(), str(name).upper())
    unit = str(unit or "").lower()
    if name in {"CRL", "BPD", "HC", "AC", "FL", "NT", "GS", "YS", "AFI"}:
        if unit == "cm":
            return 0.05 <= number <= 60
        return 0.5 <= number <= 600
    if name == "EFW":
        return 10 <= number <= 7000
    if name == "FHR":
        return 40 <= number <= 240
    return True


def _candidate(
    name: str,
    value: str,
    unit: str,
    source_type: str,
    source_id: str,
    raw_text: str,
    confidence: float,
) -> Dict[str, Any]:
    label = MEASUREMENT_ALIASES.get(str(name).upper(), str(name).upper())
    clean_value = str(value or "").replace(",", ".").strip()
    clean_unit = str(unit or "").strip().lower()
    if clean_unit == "gr":
        clean_unit = "g"
    if clean_unit == "atim":
        clean_unit = "bpm"
    return {
        "source_type": source_type,
        "source_id": str(source_id or ""),
        "measurement_name": label,
        "measurement_value": clean_value,
        "unit": clean_unit,
        "confidence": float(confidence or 0),
        "raw_text": _clean_text(raw_text, 220),
    }


def extract_measurements_from_text(
    text: str,
    *,
    source_type: str,
    source_id: str,
    confidence: float = 0.55,
) -> List[Dict[str, Any]]:
    """Extract measurement candidates from readable GE/private text."""
    text = str(text or "")
    found: List[Dict[str, Any]] = []

    for match in VOLUSON_OB_LINE_RE.finditer(text):
        raw_name = match.group(1).upper()
        name = raw_name.split("_", 1)[0]
        if name in MEASUREMENT_ALIASES:
            value = match.group(2)
            unit = match.group(3) or "mm"
            if _reasonable(name, value, unit):
                found.append(_candidate(
                    name, value, unit, source_type, source_id,
                    match.group(0), min(confidence + 0.12, 0.86)))

    for match in TEXT_MEASUREMENT_RE.finditer(text):
        name = match.group(1).upper()
        value = match.group(2)
        unit = match.group(3) or ""
        if _reasonable(name, value, unit):
            found.append(_candidate(
                name, value, unit, source_type, source_id,
                match.group(0), confidence))

    for match in GA_RE.finditer(text):
        found.append(_candidate(
            "GA", re.sub(r"\s+", "", match.group(1)), "hf",
            source_type, source_id, match.group(0), confidence))

    for match in EDD_RE.finditer(text):
        found.append(_candidate(
            "EDD", match.group(1), "", source_type, source_id,
            match.group(0), min(confidence + 0.08, 0.82)))

    return _dedupe_candidates(found)


def _dedupe_candidates(items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen = set()
    clean: List[Dict[str, Any]] = []
    for item in items or []:
        key = (
            str(item.get("measurement_name") or "").upper(),
            str(item.get("measurement_value") or ""),
            str(item.get("unit") or "").lower(),
            str(item.get("source_id") or ""),
        )
        if not key[0] or not key[1] or key in seen:
            continue
        seen.add(key)
        clean.append(item)
    return clean


def _value_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " ".join(_value_to_text(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, default=str)
    return _clean_text(value, 1800)


def _walk_orthanc_tags(tags: Dict[str, Any]) -> Iterable[Tuple[str, Dict[str, Any]]]:
    if not isinstance(tags, dict):
        return
    for tag, entry in tags.items():
        if not isinstance(entry, dict):
            continue
        yield str(tag), entry
        value = entry.get("Value")
        if isinstance(value, list):
            for child in value:
                if isinstance(child, dict):
                    yield from _walk_orthanc_tags(child)


def analyze_orthanc_tags(
    tags: Dict[str, Any],
    *,
    source_id: str = "",
) -> Dict[str, Any]:
    """Analyze Orthanc /instances/{id}/tags JSON without downloading pixels."""
    private_creators = []
    private_tag_count = 0
    text_segments = []
    private_text_segments = []

    for tag, entry in _walk_orthanc_tags(tags or {}):
        name = str(entry.get("Name") or "")
        creator = str(entry.get("PrivateCreator") or "")
        value = entry.get("Value")
        is_private = _is_private_tag(tag) or bool(creator)
        if name == "PrivateCreator":
            text = _value_to_text(value)
            if text:
                private_creators.append(text)
        if is_private:
            private_tag_count += 1
        text = _value_to_text(value)
        if not text:
            continue
        segment = f"{tag} {name} {creator} {text}".strip()
        if is_private:
            private_text_segments.append(segment)
        if PRIVATE_HINT_RE.search(segment) or re.search(
                r"\b(CRL|BPD|HC|AC|FL|EFW|GS|YS|NT|AFI|FHR|EDD|GA)\b",
                segment, re.IGNORECASE):
            text_segments.append(segment)

    candidates = []
    for segment in private_text_segments:
        candidates.extend(extract_measurements_from_text(
            segment,
            source_type="dicom-private-tags",
            source_id=source_id,
            confidence=0.58,
        ))
    for segment in text_segments:
        candidates.extend(extract_measurements_from_text(
            segment,
            source_type="dicom-full-tags",
            source_id=source_id,
            confidence=0.44,
        ))

    creators = sorted(set(_clean_text(x, 120) for x in private_creators if x))
    return {
        "source": "orthanc-tags",
        "source_id": source_id,
        "private_creators": creators,
        "private_tag_count": int(private_tag_count),
        "text_probe_count": len(text_segments),
        "has_4dview_payload": any(PRIVATE_HINT_RE.search(x) for x in text_segments),
        "decoded_measurement_count": len(candidates),
        "candidates": _dedupe_candidates(candidates),
        "text_samples": [_clean_text(x, 240) for x in text_segments[:12]],
    }


def _decode_bytes_candidates(blob: bytes) -> List[str]:
    if not blob:
        return []
    samples = []
    for enc in ("utf-8", "latin-1", "utf-16le"):
        try:
            text = blob.decode(enc, errors="ignore")
        except Exception:
            continue
        if PRIVATE_HINT_RE.search(text) or re.search(
                r"\b(CRL|BPD|HC|AC|FL|EFW|EDD|GA)\b", text, re.IGNORECASE):
            samples.append(_clean_text(text, 4000))
    return samples


def analyze_dicom_bytes(
    data: bytes,
    *,
    source_id: str = "",
) -> Dict[str, Any]:
    """Read a DICOM file and decode text-like GE/Kretz private payloads."""
    result = {
        "source": "dicom-file",
        "source_id": source_id,
        "private_creators": [],
        "private_tag_count": 0,
        "text_probe_count": 0,
        "has_4dview_payload": False,
        "decoded_measurement_count": 0,
        "candidates": [],
        "text_samples": [],
        "error": "",
    }
    try:
        import pydicom
    except Exception as exc:
        result["error"] = f"pydicom unavailable: {exc}"
        return result
    try:
        ds = pydicom.dcmread(
            io.BytesIO(data or b""),
            stop_before_pixels=True,
            force=True,
            specific_tags=None,
        )
    except Exception as exc:
        result["error"] = f"dicom read failed: {exc}"
        return result

    creators = []
    text_segments = []
    candidates = []
    private_count = 0
    for elem in ds.iterall():
        try:
            is_private = bool(elem.tag.is_private)
        except Exception:
            is_private = False
        if is_private:
            private_count += 1
        try:
            if elem.name == "Private Creator" and elem.value:
                creators.append(str(elem.value))
        except Exception:
            pass
        if not is_private:
            continue
        texts = []
        value = getattr(elem, "value", None)
        if isinstance(value, bytes):
            texts.extend(_decode_bytes_candidates(value))
        else:
            text = _value_to_text(value)
            if text:
                texts.append(text)
        for text in texts:
            segment = (
                f"{elem.tag} {getattr(elem, 'name', '')} "
                f"{getattr(elem, 'private_creator', '')} {text}"
            )
            if PRIVATE_HINT_RE.search(segment) or re.search(
                    r"\b(CRL|BPD|HC|AC|FL|EFW|GS|YS|NT|AFI|FHR|EDD|GA)\b",
                    segment, re.IGNORECASE):
                text_segments.append(segment)
                candidates.extend(extract_measurements_from_text(
                    segment,
                    source_type="dicom-private-4dview",
                    source_id=source_id,
                    confidence=0.72,
                ))

    result.update({
        "private_creators": sorted(set(_clean_text(x, 120) for x in creators if x)),
        "private_tag_count": int(private_count),
        "text_probe_count": len(text_segments),
        "has_4dview_payload": any(PRIVATE_HINT_RE.search(x) for x in text_segments),
        "decoded_measurement_count": len(_dedupe_candidates(candidates)),
        "candidates": _dedupe_candidates(candidates),
        "text_samples": [_clean_text(x, 260) for x in text_segments[:16]],
    })
    return result


def merge_private_analyses(*items: Dict[str, Any]) -> Dict[str, Any]:
    """Merge tag-only and DICOM-file analyses into one compact report."""
    creators = []
    samples = []
    candidates = []
    private_tag_count = 0
    text_probe_count = 0
    has_payload = False
    errors = []
    source_id = ""
    for item in items:
        if not item:
            continue
        source_id = source_id or str(item.get("source_id") or "")
        creators.extend(item.get("private_creators") or [])
        samples.extend(item.get("text_samples") or [])
        candidates.extend(item.get("candidates") or [])
        private_tag_count = max(private_tag_count, int(item.get("private_tag_count") or 0))
        text_probe_count += int(item.get("text_probe_count") or 0)
        has_payload = has_payload or bool(item.get("has_4dview_payload"))
        if item.get("error"):
            errors.append(str(item.get("error")))
    clean_candidates = _dedupe_candidates(candidates)
    return {
        "source": "merged-private",
        "source_id": source_id,
        "private_creators": sorted(set(_clean_text(x, 120) for x in creators if x)),
        "private_tag_count": int(private_tag_count),
        "text_probe_count": int(text_probe_count),
        "has_4dview_payload": bool(has_payload),
        "decoded_measurement_count": len(clean_candidates),
        "candidates": clean_candidates,
        "text_samples": [_clean_text(x, 260) for x in samples[:20]],
        "errors": errors,
    }
