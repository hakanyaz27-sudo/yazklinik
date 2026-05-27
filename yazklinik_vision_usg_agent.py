"""USG Vision Ajani - llama3.2-vision:11b ile resimde otomatik biyometri yorumu.

Doktor USG resmini yukler veya path verir; llama3.2-vision modeli inceler:
    - Anatomik gorunum (fetal yuz, profil, ekstremite, kalp)
    - Goruntu kalitesi (1-5)
    - Tahmini BPD/HC/AC/FL (eger olcum cizgisi gorunuyorsa)
    - Klinik dikkat noktasi
    - Hatira potansiyeli (Instagram icin)

Asla:
    - Tani vermez (sadece tarif + oneri)
    - Hasta dosyasina otomatik yazmaz
    - Resmi dis sisteme yollamaz (yerel llama3.2-vision)
"""
from __future__ import annotations

import base64
import json
import os
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-vision-usg"
DEFAULT_MODEL = os.environ.get("YAZKLINIK_VISION_MODEL", "llama3.2-vision:11b")
DEFAULT_OLLAMA_URL = (os.environ.get("YAZKLINIK_OLLAMA_URL")
                      or "http://localhost:11434")


VISION_PROMPT = """Sen 25 yillik OB-GYN uzmanisin. Asagidaki USG resmini incele.
SADECE JSON cevap ver, baska metin yok:
{
  "modality": "2D" | "3D" | "4D" | "doppler" | "diger",
  "view": "kafa" | "abdomen" | "ekstremite" | "yuz" | "kalp" | "diger",
  "image_quality": 1-5 (1=cok kotu, 5=mukemmel),
  "estimated_ga_weeks": int | null,
  "visible_measurements": ["BPD: x mm", "HC: y mm"] (varsa),
  "anatomic_findings": ["fetal yuz net", "el 5 parmak gorunur"],
  "clinical_attention": ["dikkat eder bir bulgu var mi"],
  "ig_potential": 1-5 (Instagram hatira icin gorsel uygunluk),
  "doctor_note_suggestion": "1 cumle taslak rapor notu"
}
"""


@dataclass
class VisionResult:
    source_path: str
    model: str
    modality: str = ""
    view: str = ""
    image_quality: int = 0
    estimated_ga_weeks: Optional[int] = None
    visible_measurements: List[str] = field(default_factory=list)
    anatomic_findings: List[str] = field(default_factory=list)
    clinical_attention: List[str] = field(default_factory=list)
    ig_potential: int = 0
    doctor_note_suggestion: str = ""
    requires_doctor_review: bool = True
    error: Optional[str] = None
    raw_response: str = ""
    agent_version: str = AGENT_VERSION


def _read_image_base64(path: str) -> Optional[str]:
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("ascii")
    except Exception:
        return None


def analyze_image(image_path: str, model: Optional[str] = None) -> VisionResult:
    """USG goruntusunu llama3.2-vision'a yollayip yapilandirilmis sonuc dondur."""
    out = VisionResult(source_path=image_path, model=model or DEFAULT_MODEL)
    if not Path(image_path).is_file():
        out.error = "Dosya yok"
        return out
    b64 = _read_image_base64(image_path)
    if not b64:
        out.error = "Resim okunamadi"
        return out
    body = {
        "model": model or DEFAULT_MODEL,
        "prompt": VISION_PROMPT,
        "images": [b64],
        "stream": False,
        "options": {"temperature": 0.1, "num_ctx": 4096},
    }
    try:
        req = urllib.request.Request(
            DEFAULT_OLLAMA_URL.rstrip("/") + "/api/generate",
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req, timeout=180) as resp:
            j = json.loads(resp.read().decode("utf-8", errors="replace"))
        text = j.get("response", "")
        out.raw_response = text[:500]
        # JSON parse
        import re
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                data = json.loads(m.group(0))
                out.modality = str(data.get("modality") or "")
                out.view = str(data.get("view") or "")
                out.image_quality = int(data.get("image_quality") or 0)
                ga = data.get("estimated_ga_weeks")
                out.estimated_ga_weeks = int(ga) if isinstance(ga, (int, float)) and ga > 0 else None
                out.visible_measurements = [str(x) for x in (data.get("visible_measurements") or [])]
                out.anatomic_findings = [str(x) for x in (data.get("anatomic_findings") or [])]
                out.clinical_attention = [str(x) for x in (data.get("clinical_attention") or [])]
                out.ig_potential = int(data.get("ig_potential") or 0)
                out.doctor_note_suggestion = str(data.get("doctor_note_suggestion") or "")
            except Exception as e:
                out.error = f"JSON parse: {e}"
    except urllib.error.URLError as e:
        out.error = f"Ollama: {e}"
    except Exception as e:
        out.error = f"{type(e).__name__}: {e}"
    return out


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "model": DEFAULT_MODEL, "ollama_url": DEFAULT_OLLAMA_URL}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
