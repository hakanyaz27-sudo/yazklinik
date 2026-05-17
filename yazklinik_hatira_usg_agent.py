"""Hatira USG Ajani - guzel USG goruntusunu anneye WhatsApp ile sablon.

instagram_agent skoru kullanir; en iyi adayi otomatik anonimleştirir + tatli
sablonla hasta telefonuna WhatsApp gonderir (consent_messaging=True ise).

Sablon ornek:
    "Sevgili [ad], bugünkü ultrasonunuzdan tatlı bir kare ❤️
     Bebeginiz [gebelik haftasi]. Saglikli gunler!
     - Op. Dr. Hakan Yaz"
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-hatira-usg"


HATIRA_TEMPLATES = [
    ("Sevgili {name}, bugünkü ultrasonunuzdan tatlı bir kare. "
     "Bebeğiniz harika görünüyor.\nSağlıklı günler dilerim.\n- Op. Dr. Hakan Yaz"),
    ("Merhaba {name}, ultrasondan küçük bir hatıra. "
     "Bebeğiniz {ga_text}.\nKendinize iyi bakın.\n- Op. Dr. Hakan Yaz"),
    ("Sayın {name}, bugünkü USG'den size özel bir kare. "
     "Kontrolünüz iyi geçti, devam.\nİyi haftalar.\n- Op. Dr. Hakan Yaz"),
]


@dataclass
class HatiraJob:
    patient_id: str
    patient_name: str
    patient_phone: str
    image_path: str        # anonimleştirilmis draft path
    template_text: str
    consent_acknowledged: bool = False
    queued_at: str = ""
    sent_at: Optional[str] = None
    delivery_status: str = "pending"  # pending | sent | failed | skipped
    agent_version: str = AGENT_VERSION


def prepare(patient_id: str, patient_name: str, patient_phone: str,
             usg_pdf_or_image: str, ga_text: str = "",
             template_index: int = 0,
             consent_acknowledged: bool = False) -> HatiraJob:
    """Anonim draft + sablon yazi olustur (henuz gondermez)."""
    try:
        import yazklinik_instagram_agent as ig
        opts = ig.EnhanceOptions(
            header_crop_ratio=0.15, sharpen=1.2, contrast=1.1,
            saturation=1.05, add_watermark=True,
            watermark_text="Op. Dr. Hakan Yaz", output_format="square")
        out_dir = r"D:\YazKlinik_Final_D300\hatira_drafts"
        result = ig.enhance_image(usg_pdf_or_image, out_dir, opts)
        draft_path = result.draft_path
    except Exception as exc:
        return HatiraJob(
            patient_id=patient_id, patient_name=patient_name,
            patient_phone=patient_phone, image_path="",
            template_text=f"Hatıra hazırlamada hata: {exc}",
            consent_acknowledged=False, delivery_status="failed",
            queued_at=datetime.now().isoformat(timespec="seconds"))

    tmpl = HATIRA_TEMPLATES[template_index % len(HATIRA_TEMPLATES)]
    text = tmpl.format(name=patient_name.split()[0] if patient_name else "Hasta",
                        ga_text=ga_text or "güzel hatları ile burada")
    return HatiraJob(
        patient_id=patient_id, patient_name=patient_name,
        patient_phone=patient_phone, image_path=draft_path,
        template_text=text, consent_acknowledged=consent_acknowledged,
        queued_at=datetime.now().isoformat(timespec="seconds"),
        delivery_status="pending")


def send(job: HatiraJob) -> HatiraJob:
    """Hazir job'i WhatsApp ile gonder.
    KVKK consent ZORUNLU."""
    if not job.consent_acknowledged:
        job.delivery_status = "skipped"
        return job
    try:
        from yazklinik_whatsapp_local_helper import send_whatsapp_message_with_image
        send_whatsapp_message_with_image(
            phone=job.patient_phone, text=job.template_text,
            image_path=job.image_path)
        job.delivery_status = "sent"
        job.sent_at = datetime.now().isoformat(timespec="seconds")
    except ImportError:
        # Fallback: sadece tekst
        try:
            from yazklinik_whatsapp_local_helper import send_whatsapp_message
            send_whatsapp_message(job.patient_phone,
                                    job.template_text + "\n(Resim aşağıda)")
            job.delivery_status = "sent_text_only"
            job.sent_at = datetime.now().isoformat(timespec="seconds")
        except Exception as e:
            job.delivery_status = "failed"
            job.template_text += f"\n[ERR: {e}]"
    except Exception as e:
        job.delivery_status = "failed"
        job.template_text += f"\n[ERR: {e}]"
    return job


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "templates": len(HATIRA_TEMPLATES)}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
