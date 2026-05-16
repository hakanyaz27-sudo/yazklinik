"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — Mixins paketi                               ║
║  ─────────────────────────────                               ║
║  Eskiden tek dosyada (yazklinik_v68.py) olan 16 mixin sınıfı ║
║  artık burada — her biri kendi modülünde.                    ║
╚══════════════════════════════════════════════════════════════╝
"""

from yazklinik.mixins.pdf_editor import _PdfEditorMixin
from yazklinik.mixins.video import _VideoMixin
from yazklinik.mixins.dicom import _DicomMixin
from yazklinik.mixins.whatsapp import _WhatsAppMixin
from yazklinik.mixins.clinical_banner import _ClinicalBannerMixin
from yazklinik.mixins.filter_search import _FilterSearchMixin
from yazklinik.mixins.demo_flags import _DemoFlagsMixin
from yazklinik.mixins.nas_sync import _NasSyncMixin
from yazklinik.mixins.preview_thumb import _PreviewThumbMixin
from yazklinik.mixins.ui_construction import _UiConstructionMixin
from yazklinik.mixins.pdf_generation import _PdfGenerationMixin
from yazklinik.mixins.stats import _StatsMixin
from yazklinik.mixins.a4_print import _A4PrintMixin
from yazklinik.mixins.patient_nav import _PatientNavMixin
from yazklinik.mixins.notes_summary import _NotesSummaryMixin
from yazklinik.mixins.settings_help import _SettingsHelpMixin

__all__ = [
    "_PdfEditorMixin", "_VideoMixin", "_DicomMixin",
    "_WhatsAppMixin", "_ClinicalBannerMixin",
    "_FilterSearchMixin", "_DemoFlagsMixin",
    "_NasSyncMixin", "_PreviewThumbMixin",
    "_UiConstructionMixin", "_PdfGenerationMixin",
    "_StatsMixin", "_A4PrintMixin", "_PatientNavMixin",
    "_NotesSummaryMixin", "_SettingsHelpMixin",
]
