"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _A4PrintMixin
║  Otomatik bölünmüş modül
╚══════════════════════════════════════════════════════════════╝
"""

import sys as _sys


def _inject_parent_globals():
    """yazklinik_v68 modülünün globallerini bu modüle enjekte eder."""
    # Önce "yazklinik_v68" adıyla dene
    parent = _sys.modules.get("yazklinik_v68")

    # Yoksa "__main__" dene (script olarak çalıştırıldığında)
    if parent is None:
        main_mod = _sys.modules.get("__main__")
        if main_mod is not None and hasattr(main_mod, "APP_VERSION"):
            parent = main_mod

    if parent is None:
        for name, mod in _sys.modules.items():
            if mod is None:
                continue
            if hasattr(mod, "APP_VERSION") and hasattr(
                    mod, "PATIENT_FLAGS"):
                parent = mod
                break

    if parent is None:
        raise ImportError(
            "yazklinik_v68 parent modulü bulunamadı.")

    current_globals = globals()
    # Hem public hem private isimleri al, SADECE dunder (__xxx__)
    # olanları hariç tut
    for name in dir(parent):
        if name.startswith("__") and name.endswith("__"):
            continue  # dunder (örn __name__, __file__)
        if name not in current_globals:
            current_globals[name] = getattr(parent, name)


_inject_parent_globals()

class _A4PrintMixin:
    """MainWindow methods related to A4Print. Mixed into MainWindow via MRO."""

    def _quick_action_dispatch(self, slot_name: str) -> None:
        """Fire the slot requested by the Quick Actions row.

        We take the method name as a string (rather than a bound method at
        button-build time) because the Quick Actions row is assembled
        inside _build_summary_tab, which runs before every mixin's
        methods have been mixed in. Looking up the attribute here,
        lazily, means the order of mixin definitions doesn't matter —
        and if a future refactor renames a slot we'll see a clear
        AttributeError rather than a silent failure.

        Also centralises the "patient must be selected" guard so every
        quick action has consistent behaviour.
        """
        if not self.current_patient:
            self.statusBar().showMessage(
                "Önce bir hasta seçin (hasta listesinden tıklayın)", 4000)
            return
        slot = getattr(self, slot_name, None)
        if slot is None or not callable(slot):
            _log_warning(
                f"Quick action: slot '{slot_name}' not found on MainWindow")
            QMessageBox.warning(
                self, "Bu eylem şu an kullanılamıyor",
                f"Hızlı eylem '{slot_name}' çağrılamadı.\n"
                "Kod güncellemesinden sonra yeniden başlatmayı deneyin.")
            return
        try:
            # v68-AI: Log this quick action so BehaviorLearner can
            # learn frequency patterns + suggest top actions later
            try:
                pkey = (self.current_patient.name
                        if self.current_patient else "")
                BehaviorLearner.log_action(
                    "quick_action", slot_name, patient_key=pkey)
            except Exception as _ex:
                _log_warning(f"behavior log: quick_action: {_ex}")
            slot()
        except Exception as ex:
            _log_warning(f"Quick action '{slot_name}' raised", exc=ex)
            QMessageBox.critical(
                self, "Hata",
                f"Eylem çalışırken hata oluştu:\n\n{ex}")

    def _show_gynec_test_sheet(self):
        """Show the infertility / gynecologic workup list for the
        currently-selected patient.

        Unlike the obstetric test sheet (schedule keyed to gestational
        age), this is a one-shot panel covering:
          • Hormonal baseline (AMH, FSH, LH, E2, TSH, prolactin, DHEA)
          • Infection screening (HBV, HCV, HIV, VDRL, rubella)
          • Ovarian reserve (AMH + AFC on USG)
          • Tubal patency (HSG / SIS)
          • Uterine anatomy (USG + saline sonography + MR if needed)
          • Partner workup (spermiogram + DNA fragmentation)
        Designed as a patient handout (printable), so nothing is GA-gated.
        """
        # v68: Patient is OPTIONAL — without one we still show the
        # infertilite workup list as a printable template (header just
        # omits the patient name). Useful when the doctor wants a
        # blank handout to give to a walk-in.
        pname = "—"
        if self.current_patient is not None:
            pname = format_patient_name(self.current_patient.name)
        today = datetime.now().strftime("%d.%m.%Y")

        # Collapsible, organized test groups — a clinical flow
        # that goes from "baseline blood tests" to "partner" to
        # "follow-up after treatment starts". Each item has its
        # menstrual-day timing where relevant (2-5. gün vs 21. gün).
        groups = [
            ("🩸 Bazal Hormon Profili",
             "Adet kanamasının 2-5. günü (foliküler faz)",
             [
                 ("FSH (Folikül Stimülan Hormon)",
                  "Yumurtalık rezervi göstergesi — &lt;10 mIU/mL normal"),
                 ("LH (Lüteinizan Hormon)",
                  "FSH:LH oranı 1:1 normal; &gt;2 PCOS şüphesi"),
                 ("E2 (Estradiol)",
                  "Bazal E2 &lt;60 pg/mL normal — yüksek ise yumurtalık yetmezliği riski"),
                 ("AMH (Anti-Müllerian Hormon)",
                  "Yumurtalık rezervinin en iyi göstergesi — her zaman çekilebilir"),
                 ("Prolaktin (PRL)",
                  "Yüksek prolaktin ovulasyonu baskılar — MRI gerekebilir"),
                 ("TSH + Serbest T4",
                  "Subklinik hipotiroidi bile infertiliteye neden olabilir"),
                 ("DHEA-S + Total Testosteron + 17-OHP",
                  "Androjen yüksekliği + PCOS / adrenal hiperplazi değerlendirmesi"),
             ]),
            ("🧬 İkinci Faz Hormonları",
             "Adet kanamasının 21. günü (luteal faz — ovulasyon olduysa)",
             [
                 ("Progesteron (21. gün)",
                  "&gt;10 ng/mL ovulasyon gerçekleşti göstergesi"),
             ]),
            ("🦠 Enfeksiyon Taraması",
             "Gebelik öncesi zorunlu panel",
             [
                 ("HbsAg (Hepatit B yüzey antijeni)",
                  "Pozitif → bebek için aşı + immünglobulin planı"),
                 ("Anti-HCV (Hepatit C)",
                  "Pozitif → PCR ile viremi değerlendirilir"),
                 ("Anti-HIV",
                  "Gebelik öncesi mutlak tarama — pozitifse tedavi başlar"),
                 ("VDRL / RPR (Sifilis)",
                  "Bebek için zorunlu tarama"),
                 ("Rubella IgG",
                  "Negatif → aşı yap + 1 ay korunma"),
                 ("Toksoplazma IgG + IgM",
                  "IgM pozitif → akut enfeksiyon, 6 ay beklenir"),
                 ("CMV IgG + IgM",
                  "Konjenital CMV önemli — özellikle çocuk bakıcılığı mesleklerinde"),
                 ("Varicella (Suçiçeği) IgG",
                  "Negatif → aşı yap + 1 ay korunma"),
                 ("Tam idrar + idrar kültürü",
                  "Asemptomatik bakteriüri taraması"),
             ]),
            ("🔬 Görüntüleme + Anatomi",
             "Tüm sikluslardan bağımsız, bir kez yapılır",
             [
                 ("Transvaginal USG (bazal)",
                  "Uterus, endometrium, overler + AFC (antral folikül sayısı)"),
                 ("Endometrial kalınlık (siklusun 12-14. günü)",
                  "Ovulasyon öncesi &gt;7 mm olması beklenir"),
                 ("HSG (Histerosalpingografi)",
                  "Tüp açıklığı + uterus şekli — adet bitiminden 3-5 gün sonra"),
                 ("SIS / Hidro sonografi",
                  "HSG alternatifi — intrauterin lezyonlar (polip, miyom, adhezyon)"),
                 ("MR pelvis (endikasyon varsa)",
                  "Endometriosis, adenomyosis, uterin anomaliler"),
                 ("Histeroskopi (endikasyon varsa)",
                  "Tanı + tedavi — özellikle tekrarlayan implantasyon başarısızlığında"),
             ]),
            ("👨 Erkek Faktörü Değerlendirmesi",
             "İnfertilitenin %40-50'si erkek kaynaklı — mutlaka yapılır",
             [
                 ("Spermiyogram (WHO 2021)",
                  "3-5 gün cinsel perhiz sonrası — hacim, konsantrasyon, "
                  "motilite, morfoloji"),
                 ("Sperm DNA fragmantasyon indeksi",
                  "Tekrarlayan düşük / IVF başarısızlığında endike"),
                 ("Hormon panel (erkek)",
                  "FSH, LH, testosteron, prolaktin — azospermi / şiddetli "
                  "oligospermi varsa"),
                 ("Erkek eş enfeksiyon taraması",
                  "HbsAg, anti-HCV, anti-HIV, VDRL"),
                 ("Genetik değerlendirme",
                  "Azospermi + şiddetli oligospermi: karyotip + Y kromozom "
                  "mikrodelesyonu"),
             ]),
            ("🧪 Ek Tetkikler (endikasyona göre)",
             "Klinik gereksinime göre eklenir",
             [
                 ("Oral glukoz tolerans testi (OGTT)",
                  "PCOS şüphesi / insulin direnci değerlendirmesi"),
                 ("Açlık insülin + HOMA-IR",
                  "PCOS'lu hastalarda metformin kararı için"),
                 ("25-OH D vitamini",
                  "&lt;30 ng/mL replasman — üreme sağlığı için önemli"),
                 ("B12 + Folat",
                  "Gebelik öncesi replasman — homosistein artmasını önler"),
                 ("Tiroid antikorları (anti-TPO, anti-Tg)",
                  "Otoimmün tiroidit → tekrarlayan düşük"),
                 ("Karyotip (her iki eş)",
                  "Tekrarlayan düşük, genetik öykü"),
                 ("Trombofili paneli",
                  "Faktör V Leiden, protrombin G20210A, protein C/S, "
                  "antitrombin III — tekrarlayan düşükte"),
                 ("Antifosfolipid antikor paneli",
                  "Lupus antikoagülanı, anti-kardiyolipin, anti-β2GP1"),
             ]),
        ]

        # Build HTML
        items_html = []
        for emoji_title, subtitle, tests in groups:
            items_html.append(
                f'<h3 style="color:#B5368A;margin-top:22px;margin-bottom:6px;">'
                f'{emoji_title}</h3>'
                f'<p style="color:#606060;font-size:11px;font-style:italic;'
                f'margin:0 0 10px 0;">{subtitle}</p>')
            for name, detail in tests:
                items_html.append(
                    f'<div style="margin-bottom:10px;padding:10px 14px;'
                    f'background:#FCF5F9;border-left:4px solid #B5368A;'
                    f'border-radius:3px;">'
                    f'<div style="font-size:13px;font-weight:700;color:#8B2A6D;">'
                    f'{name}</div>'
                    f'<div style="margin-top:3px;color:#505050;font-size:11px;">'
                    f'{detail}</div>'
                    f'</div>')
        body_html = "".join(items_html)

        html = f"""
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px 30px;
          color:#202020; }}
  .header {{ border-bottom: 3px solid #B5368A; padding-bottom: 12px;
             margin-bottom: 20px; }}
  .clinic {{ font-size: 11px; color:#606060; text-align:right; }}
  .doc-title {{ font-size: 20px; font-weight: 800; color:#B5368A;
                margin: 12px 0 6px 0; }}
  .patient {{ font-size: 13px; color:#404040; }}
  .intro {{ background:#FFF0F8; padding:10px 14px; border-radius:4px;
            margin: 14px 0; font-size:12px; color:#6F2256;
            border-left:4px solid #B5368A; }}
  .note {{ font-size:10.5px; color:#606060; margin-top:24px;
           padding-top:10px; border-top:1px solid #D0D0D0;
           font-style:italic; line-height:1.5; }}
</style>
</head>
<body>
  <div class="header">
    <div class="clinic">
      <b>{get_clinic_doctor_name()}</b><br>
      Kadın Hastalıkları ve Doğum<br>
      İnfertilite ve Üreme Endokrinolojisi
    </div>
    <div class="doc-title">🌸 İnfertilite Rutin Tetkik Paneli</div>
    <div class="patient">
      Hasta: <b>{pname}</b> &nbsp;·&nbsp; Hazırlanma: <b>{today}</b>
    </div>
  </div>

  <div class="intro">
    <b>Değerli hastamız,</b> aşağıdaki tetkikler infertilite değerlendirmesi
    için rutin olarak istenen testlerdir. Bazıları adet kanamasının belirli
    günlerinde çekilmelidir — tetkikleri istediğiniz zaman yapamazsınız,
    doğru zamanlamaya dikkat edilmelidir.
    <br><br>
    Eşinizle birlikte gelmeniz (spermiyogram için) değerlendirmeyi
    hızlandırır. Tüm sonuçları ikinci randevunuza getiriniz.
  </div>

  {body_html}

  <div class="note">
    <b>📌 Önemli Notlar:</b>
    <br>• FSH, LH, E2, prolaktin: adet kanamasının 2-5. günü (tercihen 3.)
    <br>• Progesteron: 21. gün (ovulasyon değerlendirmesi)
    <br>• AMH + TSH: her zaman çekilebilir (siklus günü önemsiz)
    <br>• HSG: adet bitiminden 3-5 gün sonra, ovulasyon öncesi
    <br>• Spermiyogram: 3-5 gün cinsel perhiz sonrası
    <br>• Yukarıdaki tetkiklerin tümü bir seferde yapılmaz — siklus
    günlerine göre 2-3 randevuda tamamlanır.
  </div>
</body>
</html>"""

        # Dialog with print
        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle(f"İnfertilite Tetkik Listesi — {pname}")
        dlg.resize(780, 720)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(12, 12, 12, 12)

        info = QLabel(
            f"<i style='color:#606060;font-size:11px;'>"
            f"Bu doküman <b>{pname}</b>'e elden verilebilir. "
            f"Yazdırmak için aşağıdaki butonu kullanın.</i>")
        info.setTextFormat(Qt.RichText)
        v.addWidget(info)

        txt = QTextEdit()
        txt.setReadOnly(True)
        # Force white theme for clean print
        txt.setStyleSheet(
            "QTextEdit{background:#FFFFFF;color:#202020;"
            "border:1px solid #C8C8C8;}")
        txt.setHtml(html)
        v.addWidget(txt, 1)

        btn_row = QHBoxLayout()
        btn_print = QPushButton("🖨 Yazdır")
        btn_print.setStyleSheet(
            "QPushButton{background:#B5368A;color:white;padding:8px 22px;"
            "font:600 12px 'Segoe UI';border:none;border-radius:3px;}"
            "QPushButton:hover{background:#8B2A6D;}")

        def _do_print():
            # v68-UI: Use the central print_text_widget helper
            # for reliable printing across Windows drivers.
            ok, msg = print_text_widget(txt, parent_dialog=dlg,
                                        title="Yazdır")
            try:
                self.statusBar().showMessage(msg, 5000)
            except Exception as _ex:
                _log_warning("_do_print: status", exc=_ex)
            if not ok and "iptal" not in (msg or "").lower():
                QMessageBox.warning(dlg, "Yazdırma", msg)

        btn_print.clicked.connect(_do_print)

        btn_copy = QPushButton("📋 Panoya Kopyala")
        btn_copy.setStyleSheet(
            "QPushButton{background:#F8F8F8;border:1px solid #C8C8C8;"
            "padding:8px 22px;font:500 12px 'Segoe UI';border-radius:3px;}"
            "QPushButton:hover{background:#FCF0F8;border-color:#B5368A;}")
        btn_copy.clicked.connect(
            lambda: safe_copy_to_clipboard(txt.toPlainText()))

        btn_close = QPushButton("Kapat")
        btn_close.setShortcut("Escape")
        btn_close.clicked.connect(dlg.accept)

        btn_row.addWidget(btn_print)
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        v.addLayout(btn_row)
        dlg.exec()

    def _show_blank_pregnancy_schedule_template(self):
        """Print a blank pregnancy schedule handout (no patient bound).
        Used when the doctor opens "Test Listesi" without selecting a
        patient first — we still want the document to be printable as
        a generic handout. Shows the full standard schedule from week
        4 to week 42 in chronological order.
        """
        today = datetime.now().strftime("%d.%m.%Y")
        # Build the full schedule from week 4 onwards (no GA filter)
        try:
            schedule = get_full_pregnancy_schedule(
                lmp_dt=None, current_ga_weeks=None,
                is_rh_negative=False, is_c_section=False,
                upcoming_only=False)
        except Exception as _ex:
            _log_warning("blank schedule build", exc=_ex)
            schedule = []

        items = []
        for m in schedule:
            week_txt = f"{m['week_label']}. hafta"
            # v68: Trimester-aware visual styling — different left
            # border colour per trimester so the doctor can scan
            # the sheet and immediately see which phase each item
            # belongs to. T1 yellow / T2 green / T3 blue.
            try:
                wk_num = int(str(m['week_label']).split('-')[0])
            except Exception:
                wk_num = 0
            if wk_num <= 13:
                border_col = "#E8B800"   # T1 sarı
                bg_col = "#FFF9E6"
                tri_label = "1. trimester"
            elif wk_num <= 27:
                border_col = "#107C10"   # T2 yeşil
                bg_col = "#F0FAF0"
                tri_label = "2. trimester"
            else:
                border_col = "#0078D4"   # T3 mavi
                bg_col = "#E5F1FB"
                tri_label = "3. trimester"
            items.append(
                f'<div style="margin-bottom:14px;padding:12px 16px;'
                f'background:{bg_col};border-left:6px solid {border_col};'
                f'border-radius:3px;">'
                f'<div style="font-size:14px;font-weight:700;color:#005A9E;">'
                f'{m["emoji"]} {m["title"]}</div>'
                f'<div style="margin-top:4px;color:#606060;font-size:11px;">'
                f'<b>{week_txt}</b> <span style="color:#909090;">'
                f'· {tri_label}</span></div>'
                f'<div style="margin-top:6px;color:#404040;font-size:12px;">'
                f'{m.get("detail", "")}</div>'
                f'</div>')
        body_html = "".join(items) if items else (
            "<p style='color:#808080'>Şablon verileri yüklenemedi.</p>")

        html = f"""
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family:'Segoe UI', Arial, sans-serif; margin:20px 30px;
          color:#202020; }}
  .header {{ border-bottom:3px solid #005A9E; padding-bottom:12px;
             margin-bottom:20px; }}
  .clinic {{ font-size:11px; color:#606060; text-align:right; }}
  .doc-title {{ font-size:20px; font-weight:800; color:#005A9E;
                margin:12px 0 6px 0; }}
  .meta {{ font-size:13px; color:#404040; }}
  .note {{ font-size:10.5px; color:#606060; margin-top:24px;
           padding-top:10px; border-top:1px solid #D0D0D0;
           font-style:italic; line-height:1.5; }}
</style>
</head>
<body>
  <div class="header">
    <div class="clinic">
      <b>{get_clinic_doctor_name()}</b><br>
      Kadın Hastalıkları ve Doğum
    </div>
    <div class="doc-title">📋 Gebelik İzlem Programı (Şablon)</div>
    <div class="meta">
      Hasta: <b>—</b> &nbsp;·&nbsp; Tarih: <b>{today}</b>
    </div>
  </div>
  <p style="color:#404040;font-size:12px;font-style:italic;">
    Bu liste gebelikteki tüm rutin tetkik ve takipleri özetler. Doktorunuz
    sizin haftanıza özel kişiselleştirilmiş plan verecektir.
  </p>

  <!-- Trimester legend -->
  <table cellpadding='8' style='border-collapse:collapse;width:100%;
  font-size:11px;margin:12px 0;background:#F8F8F8;border-radius:6px;'>
    <tr>
      <td style='width:33%;text-align:center;border-left:6px solid #E8B800;
      background:#FFF9E6;padding:8px;'>
        <b style='color:#7A5A00;'>1. Trimester</b><br>
        <span style='color:#606060;font-size:10px;'>0 — 13 hafta</span>
      </td>
      <td style='width:33%;text-align:center;border-left:6px solid #107C10;
      background:#F0FAF0;padding:8px;'>
        <b style='color:#0E5F0E;'>2. Trimester</b><br>
        <span style='color:#606060;font-size:10px;'>14 — 27 hafta</span>
      </td>
      <td style='width:33%;text-align:center;border-left:6px solid #0078D4;
      background:#E5F1FB;padding:8px;'>
        <b style='color:#003A66;'>3. Trimester</b><br>
        <span style='color:#606060;font-size:10px;'>28 hafta — doğum</span>
      </td>
    </tr>
  </table>
  {body_html}
  <div class="note">
    Tetkik zamanlamaları gebelik haftanıza ve risk faktörlerinize göre
    değişebilir. Her tetkik için randevu almak üzere kliniği arayınız.
  </div>
</body>
</html>"""

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("Test Listesi — Şablon")
        dlg.resize(820, 740)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)

        # v68: Hero header (gri-mor — şablon teması)
        info = QLabel(
            "<div style='padding:14px 18px;'>"
            "<div style='font-size:18px;font-weight:800;color:#FFFFFF;'>"
            "📋  Test Listesi Şablonu</div>"
            "<div style='color:rgba(255,255,255,0.85);margin-top:4px;"
            "font-size:11.5px;'>"
            "Boş şablon — Tüm hafta milestone'ları (4-42 hf). "
            "Yazdırıp hasta adını sonra doldurabilirsiniz."
            "</div></div>")
        info.setTextFormat(Qt.RichText)
        info.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #4A4A6A, stop:0.5 #5A5A7A, stop:1 #7878A0);"
            "border-radius:10px;color:#FFFFFF;}")
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            shf = QGraphicsDropShadowEffect()
            shf.setBlurRadius(15)
            shf.setColor(QColor(74, 74, 106, 90))
            shf.setOffset(0, 3)
            info.setGraphicsEffect(shf)
        except Exception as _ex:
            _log_warning("template hero shadow", exc=_ex)
        v.addWidget(info)

        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setStyleSheet(
            "QTextEdit{background:#FFFFFF;color:#202020;"
            "border:1px solid #C8C8C8;}")
        txt.setHtml(html)
        v.addWidget(txt, 1)

        btn_row = QHBoxLayout()
        btn_print = QPushButton("🖨 Yazdır")
        btn_print.setStyleSheet(
            "QPushButton{background:#0078D4;color:white;padding:8px 22px;"
            "font:600 12px 'Segoe UI';border:none;border-radius:3px;}"
            "QPushButton:hover{background:#106EBE;}")

        def _do_print():
            # v68-UI: Use the central print_text_widget helper
            # for reliable printing across Windows drivers.
            ok, msg = print_text_widget(txt, parent_dialog=dlg,
                                        title="Yazdır")
            try:
                self.statusBar().showMessage(msg, 5000)
            except Exception as _ex:
                _log_warning("_do_print: status", exc=_ex)
            if not ok and "iptal" not in (msg or "").lower():
                QMessageBox.warning(dlg, "Yazdırma", msg)

        btn_print.clicked.connect(_do_print)

        btn_close = QPushButton("Kapat")
        btn_close.setShortcut("Escape")
        btn_close.clicked.connect(dlg.accept)

        btn_row.addWidget(btn_print)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        v.addLayout(btn_row)
        dlg.exec()

    def _show_patient_test_sheet(self):
        # v68: Route based on mode override first, then PDF detection.
        # If the doctor manually flipped to jinekoloji we go to the
        # gynecologic workup list regardless of patient state.
        try:
            override = getattr(self, "_mode_override", None)
            is_gyn = False
            if override == "gynecologic":
                is_gyn = True
            elif override == "obstetric":
                is_gyn = False
            elif self.current_patient is not None:
                is_gyn = is_gynecologic_patient(self.current_patient)
            if is_gyn:
                self._show_gynec_test_sheet()
                return
        except Exception as _ex:
            _log_warning("_show_patient_test_sheet: gyn check", exc=_ex)
        """Generate a printable document listing the tests/screenings that
        the current patient should get — TODAY's recommendations plus
        everything coming up until delivery.

        This is meant to be handed to the patient at the end of the visit
        so they don't forget what's been recommended. Formatted as an
        A4 handout with a row per milestone showing both the GA week
        range and the calendar date computed from the patient's LMP.
        """
        # v68: Without a patient we show the standard pregnancy
        # schedule as a blank-template handout (no patient name, no
        # GA-aware filtering). Doctor can hand this to a new gebe.
        if not self.current_patient:
            self._show_blank_pregnancy_schedule_template()
            return

        # If the pregnancy has already been closed out, this handout
        # will say things like "42. haftada OGTT yapılmalı" which makes
        # no sense. Confirm before proceeding so a routine keystroke
        # doesn't produce a misleading document.
        _closed = is_pregnancy_closed(self.current_patient.name)
        if _closed:
            reply = QMessageBox.question(
                self, "Gebelik Tamamlanmış",
                "Bu hastanın doğum bayrağı işaretli — gebelik "
                "sonuçlanmış görünüyor.\n\n"
                "Buna rağmen gebelik tetkik listesi yazdırmak "
                "istiyor musunuz?\n\n"
                "(Liste olağan gebelik takibindeki testleri "
                "önerir; doğum sonrası takip için uygun değildir.)",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        # Pull GA + Rh status + LMP
        ga_weeks = None
        edd_str = ""
        edd_dt = None
        if self.current_subfolder:
            try:
                pdf = get_latest_pdf_in_folder(self.current_subfolder)
                if pdf:
                    data = parse_pdf_summary_data(pdf)
                    ga_days = data.get("ga_days")
                    if isinstance(ga_days, (int, float)) and ga_days > 0:
                        ga_weeks = int(ga_days) // 7
                    edd_str = data.get("edd") or ""
                    edd_dt = data.get("edd_dt")
            except Exception as _ex:
                _log_warning("MainWindow._show_patient_test_sheet", exc=_ex)

        # Prefer LMP-derived current GA so the "bugün hangi haftadayız"
        # calculation reflects reality rather than the snapshot from the
        # last scan (which may be weeks old).
        pkey = self.active_patient_key()
        lmp_str = None
        try:
            lmp_str = get_best_lmp_for_patient(self.current_patient)
        except Exception as _ex:
            _log_warning("MainWindow._show_patient_test_sheet", exc=_ex)
        lmp_dt: Optional[datetime] = None
        if lmp_str:
            try:
                lmp_dt = datetime.strptime(lmp_str, "%d.%m.%Y")
            except Exception:
                lmp_dt = None

        current_ga = None
        if lmp_dt is not None:
            days_since_lmp = (datetime.now().date() - lmp_dt.date()).days
            if 0 <= days_since_lmp <= 300:
                current_ga = days_since_lmp // 7
        elif ga_weeks is not None:
            current_ga = ga_weeks

        demo = {}
        try:
            demo = load_patient_demographics(pkey)
        except Exception as _ex:
            _log_warning("MainWindow._show_patient_test_sheet", exc=_ex)
        is_rh_neg = (demo.get("rh_factor") or "").lower() in ("negative", "-")
        is_cs = is_c_section_planned(pkey or "")

        # Upcoming-only schedule for the test list — doctor wants the
        # patient to know what's STILL coming, not what's been done.
        schedule = get_full_pregnancy_schedule(
            lmp_dt=lmp_dt, current_ga_weeks=current_ga,
            is_rh_negative=is_rh_neg, is_c_section=is_cs,
            upcoming_only=True,
        )

        pname = format_patient_name(pkey) if pkey else "Hasta"
        today = datetime.now().strftime("%d.%m.%Y")

        # Header line under the title
        ga_line_parts = []
        if current_ga is not None:
            ga_line_parts.append(f"Mevcut gebelik haftası: <b>{current_ga}. hafta</b>")
        if edd_str:
            ga_line_parts.append(f"Tahmini doğum: <b>{edd_str}</b>")
        if is_cs:
            ga_line_parts.append("<b>🩺 Sezaryen planı mevcut</b>")
        ga_line = " &nbsp;·&nbsp; ".join(ga_line_parts) or "Gebelik haftası bilgisi yok."

        if not schedule:
            body_html = (
                "<p style='color:#808080;text-align:center;padding:40px;'>"
                "Bu hasta için önerilecek yeni tetkik kalmamış görünüyor. "
                "(Gebelik son haftalarında veya LMP bilgisi eksik olabilir.)</p>")
        else:
            items = []
            for m in schedule:
                week_txt = f"{m['week_label']}. hafta"
                date_txt = m["date_label"] or ""
                # v68: When printing the test list for the patient, we
                # do NOT decorate items with "ŞU AN" badges or any
                # past-status styling. The doctor explicitly asked for
                # this: the patient only needs to see what's still to
                # come, as a clean list. "ŞU AN" badges looked jarring
                # on paper and could confuse the patient into thinking
                # the in-progress item was already done or overdue.
                status_tag = ""  # intentionally blank for patient handout
                date_chip = ""
                if date_txt:
                    date_chip = (f"<span style='color:#003A66;background:#E5F1FB;"
                                 f"padding:2px 8px;border-radius:3px;"
                                 f"font-size:11px;font-weight:600;'>"
                                 f"📅 {date_txt}</span>")
                # v68: Trimester-aware visual styling
                try:
                    wk_num = int(str(m['week_label']).split('-')[0])
                except Exception:
                    wk_num = 0
                if wk_num <= 13:
                    border_col = "#E8B800"   # T1 sarı
                    bg_col = "#FFF9E6"
                    tri_label = "T1"
                elif wk_num <= 27:
                    border_col = "#107C10"   # T2 yeşil
                    bg_col = "#F0FAF0"
                    tri_label = "T2"
                else:
                    border_col = "#0078D4"   # T3 mavi
                    bg_col = "#E5F1FB"
                    tri_label = "T3"
                items.append(
                    f"<div style='margin-bottom:14px;padding:12px 16px;"
                    f"background:{bg_col};border-left:6px solid {border_col};"
                    f"border-radius:3px;'>"
                    f"<div style='font-size:14px;font-weight:700;color:#005A9E;'>"
                    f"{m['emoji']} {m['title']}{status_tag}</div>"
                    f"<div style='margin-top:4px;color:#606060;font-size:11px;'>"
                    f"<b>{week_txt}</b> "
                    f"<span style='color:#909090;font-weight:600;'>· "
                    f"{tri_label}</span> &nbsp; {date_chip}</div>"
                    f"<div style='margin-top:6px;font-size:12px;color:#303030;"
                    f"line-height:1.5;'>{m['detail']}</div></div>")
            body_html = "".join(items)

        html = f"""
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px 40px;
          color:#202020; }}
  .header {{ border-bottom: 3px solid #005A9E; padding-bottom: 12px;
             margin-bottom: 20px; }}
  .clinic {{ font-size: 11px; color:#606060; text-align:right; }}
  .doc-title {{ font-size: 20px; font-weight: 800; color:#005A9E;
                margin: 12px 0 6px 0; }}
  .patient {{ font-size: 13px; color:#404040; }}
  .ga-line {{ background:#E5F1FB; padding:10px 14px; border-radius:4px;
              margin: 14px 0; font-size:13px; color:#003A66; }}
  .note {{ font-size:10.5px; color:#606060; margin-top:24px;
           padding-top:10px; border-top:1px solid #D0D0D0;
           font-style:italic; line-height:1.5; }}
</style>
</head>
<body>
  <div class="header">
    <div class="clinic">
      <b>{get_clinic_doctor_name()}</b><br>
      Kadın Hastalıkları ve Doğum
    </div>
    <div class="doc-title">📋 Önerilen Tetkikler ve İzlem Planı</div>
    <div class="patient">
      Hasta: <b>{pname}</b> &nbsp;·&nbsp; Tarih: <b>{today}</b>
    </div>
  </div>

  <div class="ga-line">{ga_line}</div>

  <h3 style="color:#303030;margin-top:20px;">Bundan Sonra Yapılması Önerilen Tetkikler:</h3>
  {body_html}

  <div class="note">
    <b>Sayın hastamız,</b> yukarıda belirtilen tetkikler gebelik haftanıza
    uygun olarak önerilmektedir. Her tetkik için bizimle iletişime geçerek
    randevu alabilirsiniz. Tetkiklerinizi zamanında yaptırmanız, gebeliğinizin
    sağlıklı takibi için çok önemlidir.
    <br><br>
    Acil durumlar (kanama, şiddetli baş ağrısı, görme bozukluğu, bebeğin
    hareketlerinde azalma, kasılma) için lütfen hemen başvurunuz.
  </div>
</body>
</html>"""

        # Dialog with print button
        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle(f"Test Listesi — {pname}")
        dlg.resize(820, 720)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)

        # v68: Hero header
        info = QLabel(
            f"<div style='padding:14px 18px;'>"
            f"<div style='font-size:18px;font-weight:800;color:#FFFFFF;'>"
            f"🧪  Test Listesi</div>"
            f"<div style='color:rgba(255,255,255,0.9);margin-top:4px;"
            f"font-size:12px;'>"
            f"<b>👩 {pname}</b>"
            f"</div>"
            f"<div style='color:rgba(255,255,255,0.78);margin-top:2px;"
            f"font-size:11px;'>"
            f"Yapılacak tetkikler — yazdır ve hastaya elden verin."
            f"</div></div>")
        info.setTextFormat(Qt.RichText)
        info.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #6F2256, stop:0.5 #8B2A6D, stop:1 #B5368A);"
            "border-radius:10px;color:#FFFFFF;}")
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            shf = QGraphicsDropShadowEffect()
            shf.setBlurRadius(15)
            shf.setColor(QColor(139, 42, 109, 90))
            shf.setOffset(0, 3)
            info.setGraphicsEffect(shf)
        except Exception as _ex:
            _log_warning("test sheet hero shadow", exc=_ex)
        v.addWidget(info)

        txt = QTextEdit()
        txt.setReadOnly(True)
        # v68: Force pure-white/black text on the preview widget even
        # when the app is in dark mode. Without this, the doctor sees
        # a dark-grey background and very light text on-screen, and
        # (worse) that same styling can bleed into the printed output
        # — that's the "siyah uest taraf" the doctor reported. A local
        # stylesheet beats the app-wide dark palette for this widget
        # only, without touching the rest of the UI.
        txt.setStyleSheet(
            "QTextEdit{background:#FFFFFF;color:#202020;"
            "border:1px solid #C8C8C8;}")
        txt.setHtml(html)
        v.addWidget(txt, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_print = QPushButton("🖨 Yazdır")
        btn_print.setStyleSheet(
            "QPushButton{background:#0078D4;color:white;padding:8px 22px;"
            "font:600 12px 'Segoe UI';border:none;border-radius:3px;}"
            "QPushButton:hover{background:#106EBE;}")

        def _do_print():
            # v68-UI: Use the central print_text_widget helper
            # for reliable printing across Windows drivers.
            ok, msg = print_text_widget(txt, parent_dialog=dlg,
                                        title="Yazdır")
            try:
                self.statusBar().showMessage(msg, 5000)
            except Exception as _ex:
                _log_warning("_do_print: status", exc=_ex)
            if not ok and "iptal" not in (msg or "").lower():
                QMessageBox.warning(dlg, "Yazdırma", msg)

        btn_print.clicked.connect(_do_print)

        btn_copy = QPushButton("📋 Panoya Kopyala")
        btn_copy.setStyleSheet(
            "QPushButton{background:#F8F8F8;border:1px solid #C8C8C8;"
            "padding:8px 22px;font:500 12px 'Segoe UI';border-radius:3px;}"
            "QPushButton:hover{background:#E5EEF7;border-color:#0078D4;}")
        btn_copy.clicked.connect(lambda: safe_copy_to_clipboard(txt.toPlainText()))

        btn_close = QPushButton("Kapat")
        btn_close.setShortcut("Escape")
        btn_close.clicked.connect(dlg.accept)

        btn_row.addWidget(btn_print)
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        v.addLayout(btn_row)

        dlg.exec()

    def _show_pregnancy_calendar(self):
        """A4 printable calendar showing every milestone of THIS patient's
        pregnancy — week + calendar date + what should be done.

        Unlike the test sheet which lists only UPCOMING tests, this view
        shows the entire timeline (past + current + future), organised as
        a compact table. Past items are greyed out, current is highlighted,
        future items are in normal colour. The doctor hands this to the
        patient as her personal roadmap: "bu haftada şunu yapacağız,
        bu tarihte şu geliş var".
        """
        if not self.current_patient:
            QMessageBox.warning(self, "Hasta Yok", "Önce bir hasta seçin.")
            return

        # Same guard as the test sheet — for a closed pregnancy, the
        # calendar would still list future milestones (36. hafta, 40.
        # hafta, etc.) as if the patient hadn't delivered yet. Ask
        # first so the document isn't produced by accident.
        _closed = is_pregnancy_closed(self.current_patient.name)
        if _closed:
            reply = QMessageBox.question(
                self, "Gebelik Tamamlanmış",
                "Bu hastanın doğum bayrağı işaretli — gebelik "
                "sonuçlanmış görünüyor.\n\n"
                "Buna rağmen gebelik takvimi yazdırmak istiyor "
                "musunuz?\n\n"
                "(Takvim doğum tarihine kadar tüm planlanan "
                "ziyaretleri listeler; kayıt amaçlı olarak "
                "yararlı olabilir.)",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        pkey = self.active_patient_key()

        # Resolve LMP — this is the absolute reference for every date below
        lmp_str = None
        try:
            lmp_str = get_best_lmp_for_patient(self.current_patient)
        except Exception as _ex:
            _log_warning("MainWindow._show_pregnancy_calendar", exc=_ex)
        lmp_dt: Optional[datetime] = None
        if lmp_str:
            try:
                lmp_dt = datetime.strptime(lmp_str, "%d.%m.%Y")
            except Exception:
                lmp_dt = None

        if lmp_dt is None:
            QMessageBox.warning(
                self, "LMP Yok",
                "Son adet tarihi hesaplanamadı. Tarih sütunlarının "
                "doldurulması için hastanın bir USG PDF'inin yüklenmiş "
                "olması gerekir.")
            return

        # Compute current GA so we can tag past/current/upcoming rows
        days_since_lmp = (datetime.now().date() - lmp_dt.date()).days
        current_ga = days_since_lmp // 7 if 0 <= days_since_lmp <= 300 else None

        # Demographics + C-section flag
        demo = {}
        try:
            demo = load_patient_demographics(pkey)
        except Exception as _ex:
            _log_warning("MainWindow._show_pregnancy_calendar", exc=_ex)
        is_rh_neg = (demo.get("rh_factor") or "").lower() in ("negative", "-")
        is_cs = is_c_section_planned(pkey or "")

        # Full schedule: no filtering, show every milestone
        schedule = get_full_pregnancy_schedule(
            lmp_dt=lmp_dt, current_ga_weeks=current_ga,
            is_rh_negative=is_rh_neg, is_c_section=is_cs,
            upcoming_only=False,
        )

        # EDD (and planned delivery date if C/S)
        edd_dt = lmp_dt + timedelta(days=280)
        edd_str = edd_dt.strftime("%d.%m.%Y")
        pdd_str = ""
        if is_cs:
            pdd_dt = planned_delivery_date(pkey or "", edd_dt)
            if pdd_dt is not None:
                pdd_str = pdd_dt.strftime("%d.%m.%Y")

        pname = format_patient_name(pkey) if pkey else "Hasta"
        today = datetime.now().strftime("%d.%m.%Y")

        # Build table rows
        rows_html: List[str] = []
        for m in schedule:
            row_bg = "#FFFFFF"
            text_color = "#202020"
            week_color = "#003A66"
            marker = ""
            if m["status"] == "past":
                row_bg = "#F2F2F2"
                text_color = "#808080"
                week_color = "#A0A0A0"
                marker = "✓"
            elif m["status"] == "current":
                row_bg = "#E8F5E9"
                week_color = "#107C10"
                marker = "▶"

            date_cell = m["date_label"] or "—"
            rows_html.append(
                f"<tr style='background:{row_bg};'>"
                f"<td style='padding:8px 10px;text-align:center;width:32px;"
                f"font-weight:700;font-size:14px;color:{week_color};'>{marker}</td>"
                f"<td style='padding:8px 10px;font-weight:700;font-size:13px;"
                f"color:{week_color};white-space:nowrap;'>"
                f"{m['week_label']}. hf</td>"
                f"<td style='padding:8px 10px;font-size:12px;color:{text_color};"
                f"white-space:nowrap;'>{date_cell}</td>"
                f"<td style='padding:8px 10px;color:{text_color};'>"
                f"<b style='font-size:12.5px;'>{m['emoji']} {m['title']}</b><br>"
                f"<span style='font-size:11px;color:"
                f"{'#808080' if m['status'] == 'past' else '#505050'};"
                f"line-height:1.45;'>{m['detail']}</span>"
                f"</td></tr>"
            )

        delivery_line = f"Tahmini doğum tarihi: <b>{edd_str}</b>"
        if pdd_str:
            delivery_line += (f" &nbsp;·&nbsp; <b>🩺 Planlı sezaryen: "
                              f"{pdd_str}</b>")

        ga_parts = [f"LMP: <b>{lmp_str}</b>"]
        if current_ga is not None:
            ga_parts.append(f"Şu anki hafta: <b>{current_ga}. hafta</b>")
        ga_summary = " &nbsp;·&nbsp; ".join(ga_parts)

        html = f"""
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px 30px;
          color:#202020; }}
  .header {{ border-bottom: 3px solid #005A9E; padding-bottom: 10px;
             margin-bottom: 14px; }}
  .clinic {{ font-size: 11px; color:#606060; text-align:right; }}
  .doc-title {{ font-size: 19px; font-weight: 800; color:#005A9E;
                margin: 10px 0 4px 0; }}
  .patient {{ font-size: 12px; color:#404040; }}
  .info-banner {{ background:#E5F1FB; padding:8px 12px; border-radius:4px;
                  margin: 10px 0; font-size:12px; color:#003A66; }}
  .legend {{ font-size:10px; color:#606060; margin-bottom:8px; }}
  table {{ border-collapse: collapse; width:100%; }}
  th {{ background:#005A9E; color:white; padding:8px 10px; text-align:left;
        font-size:11.5px; font-weight:600; }}
  tr {{ border-bottom:1px solid #E0E0E0; }}
  .note {{ font-size:10px; color:#606060; margin-top:16px;
           padding-top:8px; border-top:1px solid #D0D0D0;
           font-style:italic; line-height:1.5; }}
</style>
</head>
<body>
  <div class="header">
    <div class="clinic">
      <b>{get_clinic_doctor_name()}</b><br>
      Kadın Hastalıkları ve Doğum
    </div>
    <div class="doc-title">📅 Gebelik Takvimi — Kişisel İzlem Planı</div>
    <div class="patient">
      Hasta: <b>{pname}</b> &nbsp;·&nbsp; Hazırlama tarihi: {today}
    </div>
  </div>

  <div class="info-banner">
    {ga_summary}<br>
    {delivery_line}
  </div>

  <div class="legend">
    <b>✓</b> tamamlanan  &nbsp;·&nbsp;  <b style='color:#107C10;'>▶</b>
    şu an  &nbsp;·&nbsp;  (işaretsiz) yaklaşan
  </div>

  <table>
    <thead>
      <tr>
        <th style="width:32px;"></th>
        <th style="width:70px;">Hafta</th>
        <th style="width:120px;">Tarih</th>
        <th>Yapılacaklar</th>
      </tr>
    </thead>
    <tbody>
      {"".join(rows_html)}
    </tbody>
  </table>

  <div class="note">
    Bu takvim sizin son adet tarihinize göre özel olarak hesaplanmıştır.
    Tarihler yaklaşık değerlerdir; USG bulgularına göre değişebilir.
    Her muayenede güncellenir. Soruların için lütfen bizi arayın.
  </div>
</body>
</html>"""

        # Dialog with print button — same pattern as test sheet
        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle(f"Gebelik Takvimi — {pname}")
        dlg.resize(880, 780)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)

        # v68: Hero header (mavi-yeşil arası — gebelik teması)
        info = QLabel(
            f"<div style='padding:14px 18px;'>"
            f"<div style='font-size:18px;font-weight:800;color:#FFFFFF;'>"
            f"📅  Gebelik Takvimi</div>"
            f"<div style='color:rgba(255,255,255,0.9);margin-top:4px;"
            f"font-size:12px;'>"
            f"<b>👩 {pname}</b>"
            f"</div>"
            f"<div style='color:rgba(255,255,255,0.78);margin-top:2px;"
            f"font-size:11px;'>"
            f"LMP'ye göre kişiselleştirilmiş izlem planı."
            f"</div></div>")
        info.setTextFormat(Qt.RichText)
        info.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #003F6F, stop:0.5 #005A9E, stop:1 #0078D4);"
            "border-radius:10px;color:#FFFFFF;}")
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            shf = QGraphicsDropShadowEffect()
            shf.setBlurRadius(15)
            shf.setColor(QColor(0, 90, 158, 90))
            shf.setOffset(0, 3)
            info.setGraphicsEffect(shf)
        except Exception as _ex:
            _log_warning("preg cal hero shadow", exc=_ex)
        v.addWidget(info)

        txt = QTextEdit()
        txt.setReadOnly(True)
        # v68: Force pure-white/black text on the preview widget even
        # when the app is in dark mode. Without this, the doctor sees
        # a dark-grey background and very light text on-screen, and
        # (worse) that same styling can bleed into the printed output
        # — that's the "siyah uest taraf" the doctor reported. A local
        # stylesheet beats the app-wide dark palette for this widget
        # only, without touching the rest of the UI.
        txt.setStyleSheet(
            "QTextEdit{background:#FFFFFF;color:#202020;"
            "border:1px solid #C8C8C8;}")
        txt.setHtml(html)
        v.addWidget(txt, 1)

        btn_row = QHBoxLayout()
        btn_print = QPushButton("🖨 Yazdır")
        btn_print.setStyleSheet(
            "QPushButton{background:#0078D4;color:white;padding:8px 22px;"
            "font:600 12px 'Segoe UI';border:none;border-radius:3px;}"
            "QPushButton:hover{background:#106EBE;}")

        def _do_print():
            # v68-UI: Use the central print_text_widget helper
            # for reliable printing across Windows drivers.
            ok, msg = print_text_widget(txt, parent_dialog=dlg,
                                        title="Yazdır")
            try:
                self.statusBar().showMessage(msg, 5000)
            except Exception as _ex:
                _log_warning("_do_print: status", exc=_ex)
            if not ok and "iptal" not in (msg or "").lower():
                QMessageBox.warning(dlg, "Yazdırma", msg)

        btn_print.clicked.connect(_do_print)

        btn_copy = QPushButton("📋 Panoya Kopyala")
        btn_copy.setStyleSheet(
            "QPushButton{background:#F8F8F8;border:1px solid #C8C8C8;"
            "padding:8px 22px;font:500 12px 'Segoe UI';border-radius:3px;}"
            "QPushButton:hover{background:#E5EEF7;border-color:#0078D4;}")

        def _do_copy():
            # Build a plain-text version for WhatsApp / notes etc.
            lines = [f"📅 GEBELİK TAKVİMİ — {pname}",
                     f"Hazırlama: {today}",
                     f"LMP: {lmp_str}",
                     f"EDD: {edd_str}" + (f"   |   Planlı sezaryen: {pdd_str}"
                                          if pdd_str else ""),
                     ""]
            for m in schedule:
                tag = "✓" if m["status"] == "past" else \
                      "▶" if m["status"] == "current" else " "
                date_part = f"  ({m['date_label']})" if m["date_label"] else ""
                lines.append(
                    f"  {tag}  {m['week_label']}. hf{date_part}")
                lines.append(f"       {m['emoji']} {m['title']}")
                lines.append(f"       {m['detail']}")
                lines.append("")
            safe_copy_to_clipboard("\n".join(lines))
            self.statusBar().showMessage("✓ Takvim panoya kopyalandı", 4000)

        btn_copy.clicked.connect(_do_copy)

        btn_close = QPushButton("Kapat")
        btn_close.setShortcut("Escape")
        btn_close.clicked.connect(dlg.accept)

        btn_row.addWidget(btn_print)
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        v.addLayout(btn_row)

        dlg.exec()

    # ═════════════════════════════════════════════════════════════════════
    # DIET SHEET (patient handout)
    # ═════════════════════════════════════════════════════════════════════
    # Three pre-built diet plans the doctor picks from; each loads into a
    # rich-text editor where the doctor can tweak before printing. The
    # plans come from module-level DIET_PLANS (patient-facing Turkish HTML).

    def _build_clinic_dashboard_widget(self, parent_layout):
        """🎯 Mini Clinic Dashboard widget — three pulse cards above
        the patient list showing live counts of:
          • Bugün (today): visits scheduled or completed today
          • Riskli (risky): patients flagged or computed-high-risk
          • Doğum (delivery): patients ≥36 wk or postterm

        Each card is clickable → filters the patient list to that
        cohort. Refreshes when the patient list refreshes (auto via
        _refresh_dashboard_pulse_cards).

        v68-UI-PREMIUM: This is the doctor's "morning glance" — opens
        the app, sees the day's priorities at the top of the screen.
        """
        dash = QWidget()
        dash.setObjectName("MiniDashboard")
        dash.setStyleSheet(
            "#MiniDashboard{background:transparent;}")
        dash_lay = QHBoxLayout(dash)
        dash_lay.setContentsMargins(0, 4, 0, 6)
        dash_lay.setSpacing(6)

        # Card factory
        def _make_card(emoji, label, color_start, color_end,
                        click_handler, tooltip):
            card = QPushButton()
            card.setCursor(Qt.PointingHandCursor)
            card.setMinimumHeight(56)
            card.setToolTip(tooltip)
            card.setStyleSheet(
                f"QPushButton{{"
                f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                f"stop:0 {color_start},stop:1 {color_end});"
                f"color:white;border:none;border-radius:8px;"
                f"text-align:left;padding:8px 12px;}}"
                f"QPushButton:hover{{"
                f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                f"stop:0 {color_end},stop:1 {color_start});}}")
            # Build inner layout via HTML in text
            count_lbl = QLabel("0")
            count_lbl.setStyleSheet(
                "color:white;font:800 22px 'Segoe UI';background:transparent;")
            text_lbl = QLabel(f"{emoji} {label}")
            text_lbl.setStyleSheet(
                "color:rgba(255,255,255,0.92);font:600 10px 'Segoe UI';"
                "background:transparent;")
            inner = QVBoxLayout(card)
            inner.setContentsMargins(8, 4, 8, 4)
            inner.setSpacing(0)
            inner.addWidget(count_lbl)
            inner.addWidget(text_lbl)
            card.clicked.connect(click_handler)
            return card, count_lbl

        # Three cards
        self._dash_today_card, self._dash_today_count = _make_card(
            "📅", "Bugün", "#0078D4", "#003F6F",
            self._dashboard_filter_today,
            "Bugün geliş yapan veya planlanmış hastalar")
        dash_lay.addWidget(self._dash_today_card, 1)

        self._dash_risk_card, self._dash_risk_count = _make_card(
            "⚠", "Riskli", "#E58E00", "#8C4A00",
            self._dashboard_filter_risky,
            "Yüksek riskli olarak işaretlenmiş hastalar")
        dash_lay.addWidget(self._dash_risk_card, 1)

        self._dash_birth_card, self._dash_birth_count = _make_card(
            "👶", "Doğum", "#107C10", "#0B5D0B",
            self._dashboard_filter_delivery,
            "Doğuma yakın hastalar (≥36 hafta veya postterm)")
        dash_lay.addWidget(self._dash_birth_card, 1)

        # v68-AI: Doğuranlar — patients who already gave birth
        self._dash_delivered_card, self._dash_delivered_count = _make_card(
            "🤱", "Doğuranlar", "#B5368A", "#6F2256",
            self._dashboard_filter_delivered,
            "Doğum yapmış hastalar — kronolojik sırayla "
            "(en yenisi başta). Postpartum takip için.")
        dash_lay.addWidget(self._dash_delivered_card, 1)

        # v68-UI-PREMIUM: Drop shadow on each card for depth/modern feel
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            for card in (self._dash_today_card, self._dash_risk_card,
                          self._dash_birth_card,
                          self._dash_delivered_card):
                shadow = QGraphicsDropShadowEffect()
                shadow.setBlurRadius(10)
                shadow.setOffset(0, 2)
                shadow.setColor(QColor(0, 0, 0, 50))
                card.setGraphicsEffect(shadow)
        except Exception as _ex:
            _log_warning(f"dashboard card shadow: {_ex}")

        parent_layout.addWidget(dash)

        # Schedule first refresh — defer to next tick so patient
        # data is loaded by then
        QTimer.singleShot(800, self._refresh_dashboard_pulse_cards)

    def _refresh_dashboard_pulse_cards(self):
        """Recompute and update the three dashboard counts.
        Called on app start, after sync, and after patient ops.
        Cheap: uses the in-memory patient list, no NAS scan."""
        try:
            # Defaults
            today_n = 0
            risky_n = 0
            birth_n = 0

            today = datetime.now().date()
            today_str = today.strftime("%Y-%m-%d")

            try:
                root = ROOT_FOLDER
                if root and root.exists():
                    for pfolder in root.iterdir():
                        if not pfolder.is_dir():
                            continue
                        if pfolder.name.startswith("_"):
                            continue
                        # Today's visits: any subfolder name starts with today
                        try:
                            for vfolder in pfolder.iterdir():
                                if vfolder.is_dir() and vfolder.name.startswith(today_str):
                                    today_n += 1
                                    break
                        except Exception:
                            _log_warning(f"_refresh_dashboard scan: skip")

                        # Risky: any patient_flags row with
                        # value=1 and key in danger set
                        try:
                            flags = get_patient_flags(pfolder.name) or {}
                            danger_keys = {
                                "kan_uyusmazligi", "akraba_evliligi",
                                "riskli_gebelik", "kotu_obstetrik",
                                "sezaryen_coklu", "habituel_abortus"}
                            if any(flags.get(k, {}).get("value") == 1
                                   for k in danger_keys):
                                risky_n += 1
                        except Exception:
                            _log_warning(f"_refresh_dashboard scan: skip")

                        # Near delivery: latest PDF GA ≥36 wk and not
                        # marked delivered
                        try:
                            flags = flags if 'flags' in dir() else (
                                get_patient_flags(pfolder.name) or {})
                            if (flags.get("dogum_normal", {}).get("value") == 1
                                    or flags.get("dogum_sezaryan", {}).get(
                                        "value") == 1):
                                continue  # already delivered
                            visits = get_subfolders(pfolder)
                            if visits:
                                pdf = get_latest_pdf_in_folder(visits[0])
                                if pdf:
                                    pdf_data = parse_pdf_summary_data(pdf)
                                    ga = pdf_data.get("ga_days")
                                    if ga and ga >= 36 * 7:
                                        birth_n += 1
                        except Exception:
                            _log_warning(f"_refresh_dashboard scan: skip")
            except Exception as _ex:
                _log_warning(f"_refresh_dashboard: scan: {_ex}")

            # Update labels
            if hasattr(self, "_dash_today_count"):
                self._dash_today_count.setText(str(today_n))
            if hasattr(self, "_dash_risk_count"):
                self._dash_risk_count.setText(str(risky_n))
            if hasattr(self, "_dash_birth_count"):
                self._dash_birth_count.setText(str(birth_n))
        except Exception as ex:
            _log_warning("_refresh_dashboard_pulse_cards", exc=ex)

    def _dashboard_filter_today(self):
        """Filter patient list to those with today's visit folder."""
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            count = (int(self._dash_today_count.text())
                     if hasattr(self, "_dash_today_count") else 0)
            if hasattr(self, "search_input"):
                self.search_input.setText(today_str)
                self.statusBar().showMessage(
                    f"📅 Bugün ({today_str}) geliş yapan hastalar listeleniyor",
                    4000)
                show_toast(self,
                           f"Bugün geliş yapan {count} hasta listeleniyor",
                           level="info", duration_ms=3000)
        except Exception as _ex:
            _log_warning(f"_dashboard_filter_today: {_ex}")

    def _dashboard_filter_risky(self):
        """Open the risk filter — show only patients with danger flags."""
        try:
            count = (int(self._dash_risk_count.text())
                     if hasattr(self, "_dash_risk_count") else 0)
            self.statusBar().showMessage(
                "⚠ Yüksek riskli hastalar — Filtreler menüsünden bayrak "
                "filtresi uygulayabilirsiniz", 6000)
            show_toast(self,
                       f"{count} yüksek riskli hasta — Filtreler menüsünü açın",
                       level="warning", duration_ms=4000)
            # Open advanced filter dialog if available
            if hasattr(self, "_show_advanced_filter_dialog"):
                self._show_advanced_filter_dialog()
        except Exception as _ex:
            _log_warning(f"_dashboard_filter_risky: {_ex}")

    def _dashboard_filter_delivery(self):
        """Show patients near delivery via the existing 'doğumu yakın' filter."""
        try:
            count = (int(self._dash_birth_count.text())
                     if hasattr(self, "_dash_birth_count") else 0)
            # Try to invoke the existing delivery-near filter
            for attr in ("_filter_delivery_near", "_show_delivery_near",
                         "_action_filter_doğumu_yakın"):
                fn = getattr(self, attr, None)
                if callable(fn):
                    fn()
                    show_toast(self,
                               f"{count} doğuma yakın hasta listeleniyor",
                               level="success", duration_ms=3000)
                    return
            self.statusBar().showMessage(
                "👶 Doğuma yakın hastalar — Filtreler menüsünden "
                "'Doğumu Yakın Olanlar' filtresini kullanın", 6000)
            show_toast(self,
                       f"{count} doğuma yakın hasta — Filtreler menüsünü açın",
                       level="info", duration_ms=4000)
        except Exception as _ex:
            _log_warning(f"_dashboard_filter_delivery: {_ex}")

    def _dashboard_filter_delivered(self):
        """🤱 Show all delivered patients chronologically.

        v68-AI: Opens a premium dialog listing every delivery the
        doctor has recorded. Sorted by delivery date (newest first).
        Each row shows the patient name, delivery date, type, baby
        info, and a button to open the patient's full record.

        Also displays year-over-year stats (normal vs sezaryen ratio,
        preterm count, twins) for the doctor's audit / dashboard.
        """
        try:
            deliveries = list_deliveries(limit=500, order="desc")
            stats = delivery_stats()
        except Exception as ex:
            _log_warning(f"_dashboard_filter_delivered: load: {ex}")
            QMessageBox.warning(
                self, "Doğuranlar",
                f"Doğum kayıtları yüklenemedi: {ex}")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("🤱 Doğuranlar — Postpartum Takip")
        dlg.setMinimumSize(820, 700)
        dlg.setModal(False)  # Non-modal so doctor can navigate

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Hero with summary stats ──────────────────────────────
        hero = QWidget()
        hero.setFixedHeight(120)
        hero.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #B5368A,stop:1 #6F2256);")
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(28, 12, 28, 12)
        hl.setSpacing(20)

        # Left: title + count
        left = QVBoxLayout()
        left.setSpacing(2)
        title = QLabel("🤱  Doğuranlar")
        title.setStyleSheet(
            "color:white;font:800 24px 'Segoe UI';background:transparent;")
        left.addWidget(title)
        sub = QLabel(
            f"<b>{stats['total']}</b> hasta doğum yapmış — "
            f"kronolojik sıra (en yenisi başta)")
        sub.setStyleSheet(
            "color:rgba(255,255,255,0.94);font:600 12px 'Segoe UI';"
            "background:transparent;")
        sub.setTextFormat(Qt.RichText)
        left.addWidget(sub)
        left.addStretch()
        hl.addLayout(left, 1)

        # Right: 4 mini stat cards
        def _mini_card(value: int, label: str, color: str = "white"):
            w = QWidget()
            w.setStyleSheet(
                f"background:rgba(255,255,255,0.18);"
                f"border-radius:8px;padding:6px 14px;")
            wl = QVBoxLayout(w)
            wl.setContentsMargins(8, 4, 8, 4)
            wl.setSpacing(0)
            v = QLabel(str(value))
            v.setAlignment(Qt.AlignCenter)
            v.setStyleSheet(
                f"color:{color};font:800 22px 'Segoe UI';"
                f"background:transparent;")
            wl.addWidget(v)
            l = QLabel(label)
            l.setAlignment(Qt.AlignCenter)
            l.setStyleSheet(
                f"color:rgba(255,255,255,0.92);"
                f"font:600 10px 'Segoe UI';background:transparent;")
            wl.addWidget(l)
            return w

        hl.addWidget(_mini_card(stats['normal'], "Normal"))
        hl.addWidget(_mini_card(stats['sezaryen'], "Sezaryen"))
        hl.addWidget(_mini_card(stats['preterm'], "Preterm"))
        hl.addWidget(_mini_card(stats['twins'], "İkiz"))

        root.addWidget(hero)

        # ── Body — scrollable list of deliveries ─────────────────
        body = QScrollArea()
        body.setWidgetResizable(True)
        body.setStyleSheet(
            "QScrollArea{background:#FAFAFA;border:none;}")
        content = QWidget()
        content.setStyleSheet("background:#FAFAFA;")
        cl = QVBoxLayout(content)
        cl.setContentsMargins(20, 14, 20, 14)
        cl.setSpacing(8)

        if not deliveries:
            empty = EmptyStateWidget(
                icon="🤱",
                title="Henüz doğum kaydı yok",
                subtitle="Bir hasta doğurduğunda quick action "
                         "barından <b>'🤱 Doğum Kaydet'</b> butonuna "
                         "(Ctrl+Shift+D) tıklayın. Hasta otomatik "
                         "olarak gebelik takibinden çıkacak ve "
                         "burada kronolojik sırayla görünecek.",
                parent=content)
            cl.addWidget(empty)
        else:
            # Group by month for visual structure
            current_month = None
            for d in deliveries:
                # Month header (e.g. "Ekim 2025")
                d_str = d.get("delivery_date", "")[:7]  # YYYY-MM
                if d_str != current_month:
                    current_month = d_str
                    try:
                        from datetime import datetime as _dt
                        dt = _dt.strptime(d_str, "%Y-%m")
                        TR_MONTHS = ["Ocak", "Şubat", "Mart", "Nisan",
                                      "Mayıs", "Haziran", "Temmuz",
                                      "Ağustos", "Eylül", "Ekim",
                                      "Kasım", "Aralık"]
                        month_label = (f"{TR_MONTHS[dt.month - 1]} "
                                       f"{dt.year}")
                    except Exception:
                        month_label = d_str
                    mh = QLabel(f"📅  {month_label}")
                    mh.setStyleSheet(
                        "color:#6F2256;font:700 13px 'Segoe UI';"
                        "padding:8px 4px 4px 4px;border-bottom:"
                        "1px solid #E0D0DA;")
                    cl.addWidget(mh)

                # Delivery card
                card = QWidget()
                card.setStyleSheet(
                    "background:white;border:1px solid #E0D0DA;"
                    "border-radius:8px;padding:0;")
                cardl = QHBoxLayout(card)
                cardl.setContentsMargins(14, 10, 14, 10)
                cardl.setSpacing(12)

                # Type icon (big)
                type_v = d.get("delivery_type", "")
                type_emoji = {
                    "normal": "👶",
                    "sezaryen": "🩺",
                    "vakum": "🔧",
                    "forseps": "🔧",
                }.get(type_v, "🤱")
                type_color = {
                    "normal": "#107C10",
                    "sezaryen": "#0078D4",
                    "vakum": "#E58E00",
                    "forseps": "#9A1B1F",
                }.get(type_v, "#6F2256")
                emoji_lbl = QLabel(type_emoji)
                emoji_lbl.setStyleSheet(
                    f"font-size:30px;color:{type_color};"
                    f"background:transparent;padding:0;")
                emoji_lbl.setFixedWidth(44)
                cardl.addWidget(emoji_lbl)

                # Middle: name + details
                mid = QVBoxLayout()
                mid.setSpacing(2)
                pkey = d.get("patient_key", "")
                try:
                    name = format_patient_name(pkey)
                except Exception:
                    name = pkey
                name_lbl = QLabel(f"<b>{name}</b>")
                name_lbl.setTextFormat(Qt.RichText)
                name_lbl.setStyleSheet(
                    "font:700 14px 'Segoe UI';color:#222;"
                    "background:transparent;")
                mid.addWidget(name_lbl)

                # Build details line
                bits = []
                try:
                    from datetime import datetime as _dt
                    dt = _dt.strptime(d.get("delivery_date", "")[:10],
                                       "%Y-%m-%d")
                    bits.append(f"📅 {dt.strftime('%d.%m.%Y')}")
                except Exception as _ex:
                    _log_warning(f"delivery date fmt: {_ex}")
                bits.append(
                    f"<span style='color:{type_color};font-weight:700;'>"
                    f"{type_v.upper()}</span>")
                if d.get("ga_at_delivery_days"):
                    ga_d = int(d["ga_at_delivery_days"])
                    w = ga_d // 7
                    dd = ga_d % 7
                    bits.append(f"⏰ {w}+{dd} hf")
                if d.get("baby_weight_g"):
                    bits.append(f"⚖ {d['baby_weight_g']} g")
                if d.get("baby_count", 1) >= 2:
                    bits.append(f"👶 {d['baby_count']} bebek")
                if d.get("baby_sex"):
                    bits.append(f"{d['baby_sex']}")
                if d.get("hospital"):
                    bits.append(f"🏥 {d['hospital']}")

                detail_lbl = QLabel(" · ".join(bits))
                detail_lbl.setTextFormat(Qt.RichText)
                detail_lbl.setStyleSheet(
                    "font:500 11px 'Segoe UI';color:#666;"
                    "background:transparent;")
                detail_lbl.setWordWrap(True)
                mid.addWidget(detail_lbl)

                if d.get("notes"):
                    notes_lbl = QLabel(
                        f"<i>📝 {d['notes'][:120]}</i>")
                    notes_lbl.setTextFormat(Qt.RichText)
                    notes_lbl.setStyleSheet(
                        "font:500 11px 'Segoe UI';color:#888;"
                        "background:transparent;")
                    notes_lbl.setWordWrap(True)
                    mid.addWidget(notes_lbl)

                cardl.addLayout(mid, 1)

                # Right: open button
                open_btn = QPushButton("📁 Aç")
                open_btn.setCursor(Qt.PointingHandCursor)
                open_btn.setToolTip(f"{name} hastasını listede seç")
                open_btn.setStyleSheet(
                    "QPushButton{background:#F5F3FA;color:#6F2256;"
                    "border:1px solid #E0D0DA;padding:6px 14px;"
                    "font:600 11px 'Segoe UI';border-radius:4px;}"
                    "QPushButton:hover{background:#E8DDFA;"
                    "border-color:#6F2256;}")
                def _open(_checked=False, k=pkey):
                    try:
                        # Find the patient folder
                        if hasattr(self, "root_folder"):
                            from pathlib import Path
                            target = Path(self.root_folder) / k
                            if target.exists():
                                self._select_patient_by_path(target)
                                dlg.close()
                                return
                        show_toast(self,
                                    f"⚠ Hasta klasörü bulunamadı: {k}",
                                    level="warning")
                    except Exception as _ex:
                        _log_warning(f"open delivered: {_ex}")
                open_btn.clicked.connect(_open)
                cardl.addWidget(open_btn, 0, Qt.AlignVCenter)

                cl.addWidget(card)

        cl.addStretch()
        body.setWidget(content)
        root.addWidget(body, 1)

        # ── Bottom button bar ────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 10, 20, 12)

        # Year filter combo
        from PySide6.QtCore import QDate as _QD
        cur_year = _QD.currentDate().year()
        year_combo = QComboBox()
        year_combo.addItem("Tüm yıllar")
        for y in range(cur_year, cur_year - 10, -1):
            year_combo.addItem(str(y))
        year_combo.setStyleSheet(
            "QComboBox{background:white;color:#222;"
            "padding:6px 10px;border:1px solid #C8C8C8;"
            "font:13px 'Segoe UI';border-radius:4px;min-width:140px;}")
        btn_row.addWidget(year_combo)

        btn_row.addStretch()

        close_btn = QPushButton("Kapat")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #B5368A,stop:1 #6F2256);color:white;"
            "padding:8px 22px;border:none;border-radius:4px;"
            "font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:#6F2256;}")
        close_btn.clicked.connect(dlg.close)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        dlg.exec()

    def _show_pregnancy_timeline_dialog(self):
        """🗓 Patient Pregnancy Timeline Visualizer.

        v68-UI-PREMIUM: Beautiful horizontal timeline showing:
          • Each visit as a circular node positioned by GA week
          • Trimester bands (T1: 0-12, T2: 13-27, T3: 28-40 wk)
          • Key milestones (NIPT, anomaly scan, OGTT, term, delivery)
          • Risk score timeline (color-coded line)
          • Click any node → jumps to that visit

        This is the kind of visualization that makes doctors say
        "wow, why doesn't every program do this?".
        """
        if self.current_patient is None:
            QMessageBox.information(
                self, "Gebelik Timeline",
                "Önce bir hasta seçin.")
            return

        patient_key = self.current_patient.name
        display_name = format_patient_name(patient_key)

        # Gather visit data
        try:
            visits = get_subfolders(self.current_patient) or []
            demo = load_patient_demographics(patient_key) or {}
            flags = get_patient_flags(patient_key) or {}
        except Exception as ex:
            _log_warning("_show_pregnancy_timeline_dialog gather", exc=ex)
            QMessageBox.warning(
                self, "Timeline",
                f"Veri toplanamadı: {ex}")
            return

        if not visits:
            QMessageBox.information(
                self, "Timeline",
                f"{display_name} için henüz geliş kaydı yok.")
            return

        # Parse each visit's date + GA from PDF
        visit_data = []  # list of {date, ga_days, has_pdf, label}
        for v in reversed(visits):  # oldest → newest for timeline
            d = None
            ga = None
            m = re.match(r'(\d{4})-(\d{2})-(\d{2})', v.name)
            if m:
                try:
                    from datetime import date as _date
                    d = _date(int(m.group(1)), int(m.group(2)),
                              int(m.group(3)))
                except Exception as _ex:
                    _log_warning(
                        f"timeline: date parse: {_ex}")
            try:
                pdf = get_latest_pdf_in_folder(v)
                if pdf:
                    pdf_data = parse_pdf_summary_data(pdf)
                    ga = pdf_data.get("ga_days")
            except Exception as _ex:
                _log_warning(
                    f"timeline: GA parse: {_ex}")
            visit_data.append({
                "date": d,
                "ga_days": ga,
                "ga_weeks": ga // 7 if ga else None,
                "label": format_visit_name(v.name),
                "path": v,
            })

        # Build dialog
        dlg = QDialog(self)
        dlg.setWindowTitle(f"🗓 Gebelik Timeline — {display_name}")
        dlg.setMinimumSize(900, 540)
        dlg.setModal(False)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Hero
        hero = QWidget()
        hero.setFixedHeight(80)
        hero.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #0078D4,stop:0.5 #5A1FB8,stop:1 #D13438);")
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(28, 14, 28, 14)
        ht = QLabel(f"🗓  Gebelik Timeline   ·   {display_name}")
        ht.setStyleSheet(
            "color:white;font:800 20px 'Segoe UI';background:transparent;")
        hl.addWidget(ht)
        root.addWidget(hero)

        # Timeline canvas (custom QWidget paintEvent)
        canvas = TimelineCanvas(visit_data, demo, flags)
        canvas.setMinimumHeight(360)
        canvas.visit_clicked.connect(
            lambda path: (self._select_visit_path(path)
                          if hasattr(self, "_select_visit_path") else None))

        scroll = QScrollArea()
        scroll.setWidget(canvas)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea{background:#FAFAFA;border:none;}")
        root.addWidget(scroll, 1)

        # Bottom info / legend
        legend = QLabel(
            "<span style='color:#0078D4;'>● T1 (0-12 hf)</span>  "
            "<span style='color:#5A1FB8;'>● T2 (13-27 hf)</span>  "
            "<span style='color:#D13438;'>● T3 (28+ hf)</span>  &nbsp;&nbsp;"
            "<span style='color:#666;'>Bir noktaya tıklayarak ilgili gelişe gidin</span>")
        legend.setStyleSheet(
            "background:white;padding:10px 20px;color:#444;"
            "font:500 11px 'Segoe UI';border-top:1px solid #DDD;")
        root.addWidget(legend)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 10, 20, 12)
        btn_row.addStretch()
        btn_close = QPushButton("Kapat")
        btn_close.setStyleSheet(
            "QPushButton{background:#0078D4;color:white;padding:8px 22px;"
            "border:none;border-radius:4px;font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:#005A9E;}")
        btn_close.clicked.connect(dlg.close)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        # Track open
        if not hasattr(self, "_open_timeline_dialogs"):
            self._open_timeline_dialogs = []
        self._open_timeline_dialogs.append(dlg)
        dlg.finished.connect(
            lambda _: (self._open_timeline_dialogs.remove(dlg)
                       if dlg in self._open_timeline_dialogs else None))
        dlg.show()

    def _show_smart_search_dialog(self):
        """🔍 Smart Search — Ctrl+K command palette.

        v68-UI-PREMIUM: A modern, fast search dialog inspired by
        VS Code's Ctrl+P / Notion's quick-find. Features:
          • Live fuzzy matching (typo-tolerant)
          • Keyboard-first navigation (↑↓ arrows + Enter)
          • Searches: patient names, TC, phone, demographics
          • Action shortcuts: '>' prefix runs commands
          • Categorized results with icons
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("Hızlı Arama")
        dlg.setMinimumSize(620, 480)
        dlg.setModal(True)
        dlg.setWindowFlags(dlg.windowFlags() | Qt.FramelessWindowHint)

        # Frame with shadow
        outer = QVBoxLayout(dlg)
        outer.setContentsMargins(0, 0, 0, 0)

        frame = QWidget()
        frame.setStyleSheet(
            "background:white;border:1px solid #BBB;border-radius:8px;")
        outer.addWidget(frame)

        root = QVBoxLayout(frame)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Search input — large, prominent
        search_w = QWidget()
        search_w.setStyleSheet(
            "background:#F8F9FA;border-bottom:1px solid #E0E0E0;"
            "border-radius:8px 8px 0 0;")
        search_lay = QHBoxLayout(search_w)
        search_lay.setContentsMargins(20, 14, 20, 14)
        search_lay.setSpacing(10)
        icon_lbl = QLabel("🔍")
        icon_lbl.setStyleSheet(
            "font-size:18px;background:transparent;border:none;")
        search_lay.addWidget(icon_lbl)
        search_input = QLineEdit()
        search_input.setPlaceholderText(
            "Hasta adı, TC, telefon... ('>' ile komut)")
        search_input.setStyleSheet(
            "QLineEdit{background:transparent;border:none;"
            "font:500 16px 'Segoe UI';color:#222;outline:none;}")
        search_lay.addWidget(search_input, 1)
        esc_lbl = QLabel("Esc")
        esc_lbl.setStyleSheet(
            "background:#E5E5E5;color:#666;padding:3px 8px;"
            "border-radius:3px;font:600 10px 'Segoe UI';")
        search_lay.addWidget(esc_lbl)
        root.addWidget(search_w)

        # Results list
        results_list = QListWidget()
        results_list.setStyleSheet(
            "QListWidget{border:none;background:white;"
            "padding:4px;outline:none;}"
            "QListWidget::item{padding:10px 16px;border-radius:4px;"
            "color:#222;}"
            "QListWidget::item:selected{background:#EBF4FB;"
            "color:#005A9E;}"
            "QListWidget::item:hover{background:#F5F5F5;}")
        root.addWidget(results_list, 1)

        # Footer hint
        footer = QLabel(
            "<span style='color:#888;'>↑↓ gez · Enter aç · Esc kapat</span>"
            "<span style='float:right;color:#888;'>"
            "Komut için '<b>></b>' ile başla</span>")
        footer.setStyleSheet(
            "background:#FAFAFA;color:#666;padding:8px 16px;"
            "font:500 10px 'Segoe UI';border-top:1px solid #EEE;"
            "border-radius:0 0 8px 8px;")
        root.addWidget(footer)

        # Build searchable index
        all_items = []  # list of (label, sublabel, action_callable, icon)

        # 1) Patients
        try:
            root_folder = ROOT_FOLDER
            if root_folder and root_folder.exists():
                for pf in root_folder.iterdir():
                    if not pf.is_dir() or pf.name.startswith("_"):
                        continue
                    name = format_patient_name(pf.name)
                    try:
                        manual = get_patient_manual_meta(pf.name) or {}
                        ptype = manual.get("ptype", "obstetric")
                        icon = "🌸" if ptype == "gynecologic" else "👤"
                    except Exception:
                        icon = "👤"
                    all_items.append((
                        name, f"Hasta · {pf.name}",
                        lambda p=pf: self._select_patient_by_path(p),
                        icon))
        except Exception as _ex:
            _log_warning(f"smart_search: patient index: {_ex}")

        # 2) Commands (prefixed with > in search)
        commands = [
            ("Yeni hasta", "Yeni bir hasta klasörü oluştur", "🆕",
             "_show_new_patient_dialog"),
            ("Yeni geliş", "Bu hasta için yeni geliş kaydı", "📅",
             "_show_new_visit_dialog"),
            ("Klinik Akıl", "Risk skoru + akıllı içgörüler", "🧠",
             "_show_clinical_intelligence_dialog"),
            ("Gebelik Timeline", "Görsel gebelik zaman çizgisi", "🗓",
             "_show_pregnancy_timeline_dialog"),
            ("Test Listesi", "Hastaya yapılacak tetkik listesi", "🧪",
             "_show_patient_test_sheet"),
            ("Diyet Listesi", "Gebelik / GDM diyet planı", "🍎",
             "_show_diet_sheet_dialog"),
            ("Büyüme Eğrileri", "Fetal ölçüm trendleri", "📈",
             "_show_growth_trend_dialog"),
            ("Bayraklar", "Hasta klinik bayraklarını düzenle", "🏷",
             "_open_flag_editor_dialog"),
            ("Hasta Bilgileri", "Demografi + kronik + ilaç", "👤",
             "_show_demographics_dialog"),
            ("Sistem Sağlığı", "NAS + DB + Orthanc durumu", "🩺",
             "_show_system_health_panel"),
            ("Veritabanını Yedekle", "VACUUM INTO ile online yedek", "💾",
             "_backup_database_to_file"),
            ("Yazıcı Ayarları", "Kağıt boyutu, kenar boşluğu, yazıcı", "🖨",
             "_show_printer_settings_dialog"),
            ("WhatsApp Ayarları", "Varsayılan numara + ZIP modu", "💬",
             "_show_wa_default_dialog"),
            ("Orthanc Ayarları", "DICOM sunucu URL + kullanıcı", "🩻",
             "_show_orthanc_settings_dialog"),
            ("DICOM Eşleştir", "Hasta-Orthanc bağlantı kur", "🔗",
             "_show_orthanc_match_dialog"),
            ("DICOM Web'de Aç", "Orthanc plugin sayfasını aç", "🌐",
             "_open_patient_in_orthanc_web"),
            ("Sevk Mektubu", "Otomatik konsültasyon mektubu", "📨",
             "_generate_referral_letter"),
            ("Onam Formları", "Onam kütüphanesi (A4 yazdır)", "📋",
             "_show_consent_forms_dialog"),
            ("Hazır Reçeteler", "Reçete şablonları (A5 yazdır)", "💊",
             "_show_prescription_dialog"),
            ("AI Asistan", "Kullanım analizi + kişisel öneriler", "🤖",
             "_show_ai_assistant_dashboard"),
            ("Hata Log Görüntüleyici", "Sistem hatalarını incele", "📋",
             "_show_error_log_viewer"),
            ("Hakkında", "Uygulama bilgisi + sürüm", "ℹ",
             "_show_about"),
        ]
        for label, sub, icon, slot in commands:
            fn = getattr(self, slot, None)
            if callable(fn):
                all_items.append((label, sub, fn, icon))

        def _fuzzy_match(query, text):
            """Returns (score, match_str) — higher = better.
            Uses simple character-ordered fuzzy: every char of query
            must appear in order in text. Bonus for consecutive matches.
            """
            q = query.lower()
            t = text.lower()
            if not q:
                return (0, text)
            if q in t:
                # Exact substring — high score
                return (200 - t.index(q), text)
            # Char-by-char fuzzy
            qi = 0
            ti = 0
            score = 0
            consec = 0
            while qi < len(q) and ti < len(t):
                if q[qi] == t[ti]:
                    consec += 1
                    score += 1 + consec * 2
                    qi += 1
                else:
                    consec = 0
                ti += 1
            if qi < len(q):
                return (-1, text)  # not all chars matched
            return (score, text)

        def _refresh(text=""):
            results_list.clear()
            text = text.strip()
            is_command = text.startswith(">")
            if is_command:
                text = text[1:].strip()
                # Filter only commands (last entries; we know commands
                # are the most recently added)
                source = [it for it in all_items
                          if it[1].startswith(("Hasta ·",)) is False]
            else:
                source = all_items

            if not text:
                # v68-AI: Empty query → show frequently-used items first
                # so the doctor sees what they typically reach for
                try:
                    top_actions = dict(BehaviorLearner.get_top_actions(
                        limit=50, days=30))
                    top_patients = dict(BehaviorLearner.get_top_patients(
                        limit=50, days=30))
                except Exception:
                    top_actions = {}
                    top_patients = {}

                def _usage_score(item):
                    label, sub, fn, icon = item
                    # Patient items have sub starting with "Hasta · {key}"
                    if sub.startswith("Hasta · "):
                        pkey = sub[len("Hasta · "):]
                        return top_patients.get(pkey, 0)
                    # Command items: get freq by slot name (need fn name)
                    fn_name = getattr(fn, "__name__", "") or ""
                    if not fn_name and hasattr(fn, "__func__"):
                        fn_name = fn.__func__.__name__
                    return top_actions.get(fn_name, 0)

                # Sort by usage descending, then by original order
                source_sorted = sorted(
                    enumerate(source),
                    key=lambda x: (-_usage_score(x[1]), x[0]))
                shown = [item for _, item in source_sorted[:50]]
                for label, sub, fn, icon in shown:
                    score = _usage_score((label, sub, fn, icon))
                    suffix = (f" · 🔥 {score}x" if score >= 3 else "")
                    item = QListWidgetItem(
                        f"{icon}  {label}{suffix}\n     {sub}")
                    item.setData(Qt.UserRole, fn)
                    results_list.addItem(item)
            else:
                # Score and sort
                scored = []
                for label, sub, fn, icon in source:
                    s_label, _ = _fuzzy_match(text, label)
                    s_sub, _ = _fuzzy_match(text, sub)
                    best = max(s_label, s_sub)
                    if best > 0:
                        scored.append((best, label, sub, fn, icon))
                scored.sort(key=lambda x: -x[0])
                for _, label, sub, fn, icon in scored[:30]:
                    item = QListWidgetItem(f"{icon}  {label}\n     {sub}")
                    item.setData(Qt.UserRole, fn)
                    results_list.addItem(item)

            if results_list.count() > 0:
                results_list.setCurrentRow(0)

        def _activate_current():
            cur = results_list.currentItem()
            if cur is None:
                return
            fn = cur.data(Qt.UserRole)
            dlg.accept()
            try:
                if callable(fn):
                    fn()
            except Exception as ex:
                _log_warning(f"smart_search action: {ex}")

        # Wire up
        search_input.textChanged.connect(_refresh)
        search_input.returnPressed.connect(_activate_current)
        results_list.itemDoubleClicked.connect(
            lambda _it: _activate_current())

        # ↑↓ arrows handled at dialog level
        def _keyfilter(event):
            from PySide6.QtCore import QEvent
            if event.type() == QEvent.KeyPress:
                k = event.key()
                if k == Qt.Key_Down:
                    cur = results_list.currentRow()
                    if cur < results_list.count() - 1:
                        results_list.setCurrentRow(cur + 1)
                    return True
                elif k == Qt.Key_Up:
                    cur = results_list.currentRow()
                    if cur > 0:
                        results_list.setCurrentRow(cur - 1)
                    return True
            return False
        # Install event filter on the search input only
        class _EF(QObject):
            def eventFilter(self, obj, ev):
                return _keyfilter(ev)
        ef = _EF()
        search_input.installEventFilter(ef)
        dlg._ef = ef  # keep ref

        _refresh("")
        search_input.setFocus()
        dlg.exec()

    def _generate_referral_letter(self):
        """📨 Generate an automatic Turkish referral / consultation
        letter PDF based on the patient's clinical state.

        v68-UI-PREMIUM: Uses risk score + flags + demographics to
        produce a polished, doctor-quality referral letter ready
        to print or send. Saves to the patient's visit folder so
        it's archived alongside other documents.
        """
        if self.current_patient is None:
            QMessageBox.information(
                self, "Sevk Mektubu",
                "Önce bir hasta seçin.")
            return

        patient_key = self.current_patient.name
        display_name = format_patient_name(patient_key)

        # Gather clinical context
        try:
            demo = load_patient_demographics(patient_key) or {}
            manual = get_patient_manual_meta(patient_key) or {}
            if manual.get("age") and not demo.get("age"):
                demo["age"] = manual.get("age")
            flags = get_patient_flags(patient_key) or {}
            visits = get_subfolders(self.current_patient) or []
            ga_days = None
            edd_str = ""
            if visits:
                pdf = get_latest_pdf_in_folder(visits[0])
                if pdf:
                    pdf_data = parse_pdf_summary_data(pdf)
                    ga_days = pdf_data.get("ga_days")
                    edd_str = pdf_data.get("edd", "")
            risk = compute_pregnancy_risk_score(
                patient_key, demo, flags, ga_days)
        except Exception as ex:
            _log_warning("_generate_referral_letter gather", exc=ex)
            QMessageBox.warning(
                self, "Sevk Mektubu",
                f"Veri toplanamadı: {ex}")
            return

        # Ask doctor: who/what for
        from PySide6.QtWidgets import QInputDialog
        target, ok = QInputDialog.getItem(
            self, "Sevk Mektubu",
            "Hangi bölüme sevk?",
            ["Riskli Gebelik", "Genetik Danışma", "Endokrinoloji",
             "Kardiyoloji", "Hematoloji", "Romatoloji", "Üroloji",
             "Diyetisyen", "Psikiyatri", "Diğer"],
            0, False)
        if not ok:
            return

        # Build letter HTML
        try:
            doctor_name = get_clinic_doctor_name() or "Doktor"
        except Exception:
            doctor_name = "Doktor"
        try:
            clinic_name = get_clinic_name() or "Klinik"
        except Exception:
            clinic_name = "Klinik"

        today = datetime.now().strftime("%d.%m.%Y")

        # Build clinical summary
        summary_parts = []
        if demo.get("age"):
            summary_parts.append(f"{demo['age']} yaşında")
        if demo.get("gravida") is not None:
            g = demo.get("gravida")
            p = demo.get("para") or 0
            a = demo.get("abortus") or 0
            summary_parts.append(f"G{g}P{p}A{a}")
        if ga_days:
            summary_parts.append(
                f"{ga_days // 7} hafta {ga_days % 7} gün gebe")
        clin_summary = ", ".join(summary_parts) + " hasta."

        # Build active flags list
        active_flags = []
        for fkey, fdata in flags.items():
            if fdata.get("value") == 1:
                lbl = PATIENT_FLAG_LABELS.get(fkey,
                       GYNEC_FLAG_LABELS.get(fkey, fkey))
                active_flags.append(lbl)

        # Build the letter text
        letter_html = f"""<html><body style='font-family:Segoe UI;font-size:12pt;
        line-height:1.5;color:#222;'>
        <div style='text-align:right;color:#666;font-size:10pt;'>{today}</div>
        <h2 style='color:#005A9E;border-bottom:2px solid #005A9E;
        padding-bottom:6px;'>SEVK / KONSÜLTASYON YAZIsı</h2>

        <p><b>Sayın {target} Hekim Arkadaşım,</b></p>

        <p>{clin_summary} <b>{display_name}</b> isimli hastamız,
        aşağıdaki klinik durum nedeniyle değerlendirmenize sunulmuştur.</p>

        <h3 style='color:#005A9E;margin-top:18px;'>Hasta Bilgileri</h3>
        <table cellpadding='4' style='border-collapse:collapse;'>
        <tr><td style='color:#666;'><b>Ad Soyad:</b></td><td>{display_name}</td></tr>"""

        if demo.get("age"):
            letter_html += f"""<tr><td style='color:#666;'><b>Yaş:</b></td><td>{demo['age']}</td></tr>"""
        if demo.get("gravida") is not None:
            letter_html += f"""<tr><td style='color:#666;'><b>GPAL:</b></td>
            <td>G{demo.get('gravida','-')} P{demo.get('para','-')} A{demo.get('abortus','-')} L{demo.get('living','-')}</td></tr>"""
        if ga_days:
            letter_html += f"""<tr><td style='color:#666;'><b>Gebelik haftası:</b></td>
            <td>{ga_days // 7}+{ga_days % 7} hafta</td></tr>"""
        if edd_str:
            letter_html += f"""<tr><td style='color:#666;'><b>Tahmini doğum:</b></td>
            <td>{edd_str}</td></tr>"""
        if demo.get("blood_type"):
            bt = demo.get("blood_type", "")
            rh = demo.get("rh_factor", "")
            letter_html += f"""<tr><td style='color:#666;'><b>Kan grubu:</b></td>
            <td>{bt} {rh}</td></tr>"""
        letter_html += "</table>"

        if demo.get("chronic_conditions"):
            letter_html += f"""<h3 style='color:#005A9E;'>Kronik Hastalıklar</h3>
            <p>{demo['chronic_conditions']}</p>"""
        if demo.get("medications"):
            letter_html += f"""<h3 style='color:#005A9E;'>Kullandığı İlaçlar</h3>
            <p>{demo['medications']}</p>"""
        if demo.get("allergies"):
            letter_html += f"""<h3 style='color:#005A9E;'>Alerjiler</h3>
            <p>{demo['allergies']}</p>"""

        if active_flags:
            letter_html += "<h3 style='color:#005A9E;'>Klinik Bayraklar</h3><ul>"
            for f in active_flags:
                letter_html += f"<li>{f}</li>"
            letter_html += "</ul>"

        # Risk assessment
        if risk and risk.get("score", 0) > 0:
            letter_html += f"""<h3 style='color:#005A9E;'>Risk Değerlendirmesi</h3>
            <p><b>Klinik Akıl Risk Skoru:</b>
            <span style='color:{risk['color']};font-weight:700;'>
            {risk['score']}/100 ({risk['category_label']})</span></p>"""
            if risk.get("factors"):
                letter_html += "<ul>"
                for name, w, expl in risk["factors"][:6]:
                    letter_html += f"<li><b>{name}:</b> {expl}</li>"
                letter_html += "</ul>"

        letter_html += f"""<h3 style='color:#005A9E;'>Konsültasyon Talebi</h3>
        <p>Yukarıdaki klinik durum ışığında hastanın <b>{target}</b> bölümünüzce
        değerlendirilmesi, gerekli tetkik / takip / tedavi önerilerinizin
        tarafımıza iletilmesi rica olunur.</p>

        <p>Saygı ve teşekkürlerimle,</p>

        <div style='margin-top:30px;'>
        <div style='border-top:1px solid #444;padding-top:6px;
        max-width:280px;'>
        <b>{doctor_name}</b><br>
        <span style='color:#666;'>{clinic_name}</span>
        </div>
        </div>
        </body></html>"""

        # Show preview dialog with print/save buttons
        prev_dlg = QDialog(self)
        prev_dlg.setWindowTitle(f"📨 Sevk Mektubu — {display_name} → {target}")
        prev_dlg.setMinimumSize(720, 720)
        prev_dlg.setModal(True)

        prev_root = QVBoxLayout(prev_dlg)
        prev_root.setContentsMargins(0, 0, 0, 0)
        prev_root.setSpacing(0)

        # Hero
        hero = QWidget()
        hero.setFixedHeight(72)
        hero.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #005A9E,stop:1 #0078D4);")
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(24, 12, 24, 12)
        ht = QLabel(f"📨  Sevk Mektubu  ·  {target}")
        ht.setStyleSheet(
            "color:white;font:800 18px 'Segoe UI';background:transparent;")
        hl.addWidget(ht)
        prev_root.addWidget(hero)

        # Editable preview
        editor = QTextEdit()
        editor.setHtml(letter_html)
        editor.setStyleSheet(
            "QTextEdit{border:none;background:white;padding:30px 40px;}")
        # v68-AI: Smart autocomplete for editing the referral letter
        try:
            SmartAutocomplete.attach(editor)
        except Exception as _ex:
            _log_warning(f"referral editor autocomplete: {_ex}")
        prev_root.addWidget(editor, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 12, 20, 14)

        btn_print = QPushButton("🖨 Yazdır")
        btn_print.setStyleSheet(
            "QPushButton{background:#107C10;color:white;padding:9px 20px;"
            "border:none;border-radius:4px;font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:#0B5D0B;}")
        def _do_print():
            try:
                ok, msg = print_text_widget(
                    editor, prev_dlg, "Sevk Mektubu")
                self.statusBar().showMessage(msg, 5000)
            except Exception as ex:
                _log_warning(f"referral print: {ex}")
        btn_print.clicked.connect(_do_print)
        btn_row.addWidget(btn_print)

        btn_save = QPushButton("💾 Hastaya Kaydet")
        btn_save.setToolTip(
            "Mektubu PDF olarak hastanın güncel geliş klasörüne kaydet")
        btn_save.setStyleSheet(
            "QPushButton{background:#0078D4;color:white;padding:9px 20px;"
            "border:none;border-radius:4px;font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:#005A9E;}")

        def _save_pdf():
            try:
                from PySide6.QtPrintSupport import QPrinter
                from PySide6.QtGui import QPageSize, QPageLayout
                # Pick target visit folder
                target_folder = (self.current_subfolder
                                 if self.current_subfolder is not None
                                 else (visits[0] if visits else None))
                if target_folder is None:
                    QMessageBox.warning(
                        prev_dlg, "Kaydet",
                        "Hedef klasör bulunamadı.")
                    return
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_target = re.sub(r'[^\w-]', '_', target)
                pdf_path = (target_folder
                            / f"sevk_{safe_target}_{ts}.pdf")
                printer = QPrinter(QPrinter.HighResolution)
                printer.setOutputFormat(QPrinter.PdfFormat)
                printer.setOutputFileName(str(pdf_path))
                printer.setPageSize(QPageSize(QPageSize.A4))
                editor.document().print_(printer)
                self.statusBar().showMessage(
                    f"✓ Sevk mektubu kaydedildi: {pdf_path.name}",
                    7000)
                show_toast(self,
                           f"Sevk mektubu kaydedildi: {pdf_path.name}",
                           level="success", duration_ms=5000)
                QMessageBox.information(
                    prev_dlg, "Kaydedildi",
                    f"<b>Sevk mektubu kaydedildi.</b><br><br>"
                    f"📁 <code>{pdf_path}</code>")
            except Exception as ex:
                _log_warning(f"referral save pdf: {ex}")
                QMessageBox.warning(
                    prev_dlg, "Kaydet",
                    f"Kaydedilemedi: {ex}")
        btn_save.clicked.connect(_save_pdf)
        btn_row.addWidget(btn_save)

        btn_row.addStretch()

        btn_close = QPushButton("Kapat")
        btn_close.setStyleSheet(
            "QPushButton{background:#E5EEF7;color:#404040;"
            "padding:9px 20px;border:1px solid #B8D4E8;"
            "border-radius:4px;font:500 11px 'Segoe UI';}"
            "QPushButton:hover{background:#D5E5F5;}")
        btn_close.clicked.connect(prev_dlg.close)
        btn_row.addWidget(btn_close)

        prev_root.addLayout(btn_row)
        prev_dlg.exec()

    def _show_consent_forms_dialog(self):
        """📋 Onam Formları Kütüphanesi.

        Premium tabbed dialog where the doctor can:
          • Browse uploaded consent forms by category
            (Obstetrik / Jinekolojik / Lazer / Medikal Estetik /
             Jinekolojik Estetik / Diğer)
          • Single-click any short name → print to A4
          • Upload new PDF/Word with short name + category
          • Edit / delete existing entries
        """
        self._show_printable_library_dialog(
            table="consent_forms",
            title="📋 Onam Formları",
            subtitle="Hasta onam belgelerinizi yükleyin, "
                     "tek tıkla A4 yazdırın",
            categories=CONSENT_CATEGORIES,
            default_paper="A4",
            hero_gradient_start="#0078D4",
            hero_gradient_end="#003F6F")

    def _show_prescription_dialog(self):
        """💊 Hazır Reçete Şablonları.

        Same as consent forms but for prescription templates,
        defaulting to A5 paper (prescription pad standard).
        """
        self._show_printable_library_dialog(
            table="prescription_templates",
            title="💊 Hazır Reçeteler",
            subtitle="Sık kullandığınız reçeteleri yükleyin, "
                     "tek tıkla A5 yazdırın",
            categories=PRESCRIPTION_CATEGORIES,
            default_paper="A5",
            hero_gradient_start="#107C10",
            hero_gradient_end="#0B5D0B")

    def _show_printable_library_dialog(self, table: str, title: str,
                                        subtitle: str,
                                        categories: list,
                                        default_paper: str = "A4",
                                        hero_gradient_start: str = "#0078D4",
                                        hero_gradient_end: str = "#003F6F"):
        """Generic printable-library dialog used by both consents
        and prescriptions. Builds a tabbed UI with one tab per
        category, plus an upload + manage row."""
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.setMinimumSize(900, 640)
        dlg.setModal(True)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ─── Hero header ─────────────────────────────────────────
        hero = QWidget()
        hero.setFixedHeight(96)
        hero.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 {hero_gradient_start},stop:1 {hero_gradient_end});")
        hero_lay = QVBoxLayout(hero)
        hero_lay.setContentsMargins(28, 18, 28, 18)
        hero_lay.setSpacing(2)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(
            "color:white;font:800 24px 'Segoe UI';background:transparent;")
        hero_lay.addWidget(title_lbl)
        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet(
            "color:rgba(255,255,255,0.92);font:500 12px 'Segoe UI';"
            "background:transparent;")
        hero_lay.addWidget(sub_lbl)
        root.addWidget(hero)

        # ─── Action toolbar (Upload + counts) ────────────────────
        action_bar = QWidget()
        action_bar.setStyleSheet(
            "background:#F8F9FA;border-bottom:1px solid #E0E0E0;")
        action_lay = QHBoxLayout(action_bar)
        action_lay.setContentsMargins(20, 10, 20, 10)
        action_lay.setSpacing(10)

        upload_btn = QPushButton(f"📥 Yeni {('Onam' if table == 'consent_forms' else 'Reçete')} Yükle")
        upload_btn.setCursor(Qt.PointingHandCursor)
        upload_btn.setToolTip(
            "Bilgisayarınızdan PDF veya Word dosyası seçin, kısa isim "
            "verin ve kategoriye yerleştirin")
        upload_btn.setStyleSheet(
            f"QPushButton{{background:qlineargradient("
            f"x1:0,y1:0,x2:0,y2:1,stop:0 {hero_gradient_start},"
            f"stop:1 {hero_gradient_end});color:white;"
            f"padding:9px 18px;border:none;border-radius:5px;"
            f"font:600 11px 'Segoe UI';}}"
            f"QPushButton:hover{{background:{hero_gradient_end};}}")
        action_lay.addWidget(upload_btn)

        action_lay.addStretch()

        info_lbl = QLabel(
            f"<i style='color:#666;'>Tek tık → "
            f"<b>{default_paper}</b> yazdır · Sağ tık → düzenle/sil</i>")
        info_lbl.setStyleSheet(
            "color:#666;font:500 11px 'Segoe UI';background:transparent;")
        action_lay.addWidget(info_lbl)

        root.addWidget(action_bar)

        # ─── Tabs (one per category) ─────────────────────────────
        tabs = QTabWidget()
        tabs.setStyleSheet(
            "QTabWidget::pane{border:none;background:white;}"
            "QTabBar::tab{padding:10px 18px;background:#F0F0F0;"
            "border:none;font:600 11px 'Segoe UI';color:#444;}"
            f"QTabBar::tab:selected{{background:white;"
            f"color:{hero_gradient_start};"
            f"border-bottom:3px solid {hero_gradient_start};}}")

        # We'll build tab content lazily — but for simplicity, build all
        tab_widgets = {}  # category -> (scroll_area, grid_widget, refresh_fn)

        def _make_card_for_item(item: dict, category: str):
            """Return a QPushButton card for a single printable item."""
            short = item.get("short_name", "?")
            fname = item.get("file_name", "")
            ext = item.get("file_ext", "").upper()
            size_kb = (item.get("file_size") or 0) / 1024
            count = item.get("print_count") or 0
            last = item.get("last_printed_at", "") or "Hiç"
            paper = item.get("paper_size", default_paper)

            card = QPushButton()
            card.setCursor(Qt.PointingHandCursor)
            card.setMinimumHeight(96)
            card.setToolTip(
                f"<b>{short}</b><br>"
                f"📄 Dosya: {fname}<br>"
                f"📏 Boyut: {size_kb:.0f} KB · {ext}<br>"
                f"📐 Kağıt: {paper}<br>"
                f"🖨 Yazdırma sayısı: {count}<br>"
                f"⏰ Son yazdırma: {last}<br><br>"
                f"<b>Tek tık → yazıcıya gönder</b>")

            card.setStyleSheet(
                f"QPushButton{{background:white;"
                f"border:2px solid #E0E0E0;border-radius:8px;"
                f"padding:10px 14px;text-align:left;"
                f"font:600 13px 'Segoe UI';color:#222;}}"
                f"QPushButton:hover{{"
                f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                f"stop:0 white,stop:1 #F0F6FC);"
                f"border-color:{hero_gradient_start};color:{hero_gradient_start};}}")

            # Build inner content via layout
            inner = QVBoxLayout(card)
            inner.setContentsMargins(10, 8, 10, 8)
            inner.setSpacing(2)
            sn_lbl = QLabel(short)
            sn_lbl.setStyleSheet(
                f"color:#222;font:700 14px 'Segoe UI';"
                f"background:transparent;border:none;")
            sn_lbl.setWordWrap(True)
            inner.addWidget(sn_lbl)
            meta_lbl = QLabel(
                f"<span style='color:#666;font-size:10px;'>"
                f"{ext} · {size_kb:.0f} KB · {paper}</span>")
            meta_lbl.setStyleSheet(
                "background:transparent;border:none;")
            inner.addWidget(meta_lbl)
            if count > 0:
                count_lbl = QLabel(
                    f"<span style='color:{hero_gradient_start};font:600 9px Segoe UI;'>"
                    f"🖨 {count} kez yazdırıldı</span>")
                count_lbl.setStyleSheet(
                    "background:transparent;border:none;")
                inner.addWidget(count_lbl)
            inner.addStretch()

            # Single-click → print
            def _do_print():
                blob_data = db_get_printable_blob(table, item["id"])
                if not blob_data:
                    show_toast(self, "Dosya okunamadı",
                               level="error")
                    return
                blob, fn, ext_ = blob_data
                ok, msg = print_blob_to_printer(
                    blob, ext_, paper_size=paper,
                    parent_window=dlg,
                    use_default_printer=False)
                if ok:
                    db_record_printable_print(table, item["id"])
                    show_toast(self, f"✓ {short} → yazıcı ({paper})",
                               level="success")
                    # Refresh this tab
                    if category in tab_widgets:
                        _, _, refresh_fn = tab_widgets[category]
                        refresh_fn()
                else:
                    show_toast(self, msg, level="error")

            card.clicked.connect(_do_print)

            # Right-click context menu for edit/delete
            card.setContextMenuPolicy(Qt.CustomContextMenu)

            def _show_ctx(pos, _item=item, _card=card):
                from PySide6.QtWidgets import QMenu
                menu = QMenu(_card)
                edit_action = menu.addAction("✏️ Kısa İsmi Değiştir")
                category_action = menu.addAction("📁 Kategori Değiştir")
                menu.addSeparator()
                delete_action = menu.addAction("🗑 Sil")
                action = menu.exec(_card.mapToGlobal(pos))
                if action == edit_action:
                    new_name, ok = QInputDialog.getText(
                        dlg, "Kısa İsim",
                        f"Yeni kısa isim:",
                        QLineEdit.Normal,
                        _item.get("short_name", ""))
                    if ok and new_name.strip():
                        db_update_printable_meta(
                            table, _item["id"],
                            short_name=new_name.strip())
                        _refresh_all_tabs()
                        show_toast(self, "✓ Güncellendi",
                                   level="success")
                elif action == category_action:
                    cur_cats = get_distinct_printable_categories(table)
                    new_cat, ok = QInputDialog.getItem(
                        dlg, "Kategori Değiştir",
                        "Yeni kategori:",
                        cur_cats, 0, True)
                    if ok and new_cat.strip():
                        db_update_printable_meta(
                            table, _item["id"],
                            category=new_cat.strip())
                        _refresh_all_tabs()
                        show_toast(self, "✓ Kategori değişti",
                                   level="success")
                elif action == delete_action:
                    reply = QMessageBox.question(
                        dlg, "Sil",
                        f"<b>{_item.get('short_name')}</b> silinsin mi?\n"
                        f"Bu işlem geri alınamaz.",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No)
                    if reply == QMessageBox.Yes:
                        if db_delete_printable(table, _item["id"]):
                            _refresh_all_tabs()
                            show_toast(self, "✓ Silindi",
                                       level="success")

            card.customContextMenuRequested.connect(_show_ctx)
            return card

        def _build_tab_for_category(cat: str):
            """Build (or rebuild) the content of a category tab."""
            # Container widget with grid of cards
            container = QWidget()
            container.setStyleSheet("background:#FAFAFA;")
            grid = QGridLayout(container)
            grid.setContentsMargins(20, 16, 20, 16)
            grid.setSpacing(10)

            items = db_list_printables(table, category=cat)
            if not items:
                # Empty state
                empty = EmptyStateWidget(
                    icon="📥",
                    title=f"Henüz {cat} kategorisinde belge yok",
                    subtitle=f"Yukarıdaki '📥 Yeni Yükle' butonuyla "
                             f"PDF veya Word dosyası ekleyin.",
                    parent=container)
                grid.addWidget(empty, 0, 0, 1, 3)
            else:
                # 3-column grid of cards
                cols = 3
                for idx, item in enumerate(items):
                    row = idx // cols
                    col = idx % cols
                    card = _make_card_for_item(item, cat)
                    grid.addWidget(card, row, col)
                # Stretch the last row
                grid.setRowStretch((len(items) // cols) + 1, 1)

            scroll = QScrollArea()
            scroll.setWidget(container)
            scroll.setWidgetResizable(True)
            scroll.setStyleSheet(
                "QScrollArea{background:#FAFAFA;border:none;}")
            return scroll

        # Build all tabs initially
        all_categories = get_distinct_printable_categories(table)

        def _refresh_all_tabs():
            """Rebuild all tabs (call after upload/edit/delete)."""
            current_idx = tabs.currentIndex()
            tabs.clear()
            tab_widgets.clear()
            for cat in get_distinct_printable_categories(table):
                count = len(db_list_printables(table, category=cat))
                tab = _build_tab_for_category(cat)
                label = f"{cat}" + (f"  ({count})" if count else "")
                tabs.addTab(tab, label)
                tab_widgets[cat] = (tab, tab, lambda c=cat: _refresh_all_tabs())
            if 0 <= current_idx < tabs.count():
                tabs.setCurrentIndex(current_idx)

        _refresh_all_tabs()
        root.addWidget(tabs, 1)

        # ─── Bottom button row ────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 12, 20, 14)
        btn_row.addStretch()
        btn_close = QPushButton("Kapat")
        btn_close.setCursor(Qt.PointingHandCursor)
        btn_close.setStyleSheet(
            "QPushButton{background:#E5EEF7;color:#404040;"
            "padding:9px 20px;border:1px solid #B8D4E8;"
            "border-radius:4px;font:500 11px 'Segoe UI';}"
            "QPushButton:hover{background:#D5E5F5;}")
        btn_close.clicked.connect(dlg.close)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        # ─── Upload handler ───────────────────────────────────────
        def _do_upload():
            paths, _ = QFileDialog.getOpenFileNames(
                dlg, f"{('Onam' if table == 'consent_forms' else 'Reçete')} dosyası seç",
                "", "Belgeler (*.pdf *.docx *.doc *.jpg *.jpeg *.png);;"
                    "PDF (*.pdf);;Word (*.docx *.doc);;"
                    "Görüntü (*.jpg *.jpeg *.png);;Tüm dosyalar (*.*)")
            if not paths:
                return
            uploaded_count = 0
            for p_str in paths:
                p = Path(p_str)
                if not p.exists():
                    continue
                # Ask for short name + category
                upload_dlg = QDialog(dlg)
                upload_dlg.setWindowTitle("Belgeyi Yükle")
                upload_dlg.setMinimumSize(440, 280)
                ud_lay = QVBoxLayout(upload_dlg)
                ud_lay.setContentsMargins(20, 18, 20, 18)
                ud_lay.setSpacing(10)

                hdr = QLabel(
                    f"<b>📄 {p.name}</b><br>"
                    f"<span style='color:#666;font-size:10px;'>"
                    f"{p.stat().st_size / 1024:.0f} KB · {p.suffix.upper()}</span>")
                hdr.setStyleSheet("background:transparent;font:12px 'Segoe UI';")
                ud_lay.addWidget(hdr)

                ud_lay.addWidget(QLabel("Kısa isim:"))
                name_input = QLineEdit()
                name_input.setText(p.stem)
                name_input.setPlaceholderText("Örn: Sezaryen onamı")
                ud_lay.addWidget(name_input)

                ud_lay.addWidget(QLabel("Kategori:"))
                cat_combo = QComboBox()
                cat_combo.setEditable(True)
                cat_combo.addItems(get_distinct_printable_categories(table))
                # Default to currently selected tab's category
                cur_tab_idx = tabs.currentIndex()
                if cur_tab_idx >= 0:
                    cur_label = tabs.tabText(cur_tab_idx).split("  (")[0]
                    cur_idx = cat_combo.findText(cur_label)
                    if cur_idx >= 0:
                        cat_combo.setCurrentIndex(cur_idx)
                ud_lay.addWidget(cat_combo)

                ud_lay.addWidget(QLabel("Açıklama (opsiyonel):"))
                desc_input = QLineEdit()
                desc_input.setPlaceholderText("Notlar, kullanım amacı...")
                ud_lay.addWidget(desc_input)

                ud_lay.addStretch()

                btn_lay = QHBoxLayout()
                btn_lay.addStretch()
                cancel = QPushButton("İptal")
                cancel.clicked.connect(upload_dlg.reject)
                btn_lay.addWidget(cancel)
                save = QPushButton("Yükle")
                save.setStyleSheet(
                    f"QPushButton{{background:{hero_gradient_start};"
                    f"color:white;padding:7px 16px;border:none;"
                    f"border-radius:4px;font:600 11px 'Segoe UI';}}")
                save.setDefault(True)
                save.clicked.connect(upload_dlg.accept)
                btn_lay.addWidget(save)
                ud_lay.addLayout(btn_lay)

                if upload_dlg.exec() != QDialog.Accepted:
                    continue
                short = name_input.text().strip() or p.stem
                cat = cat_combo.currentText().strip() or "Diğer"
                desc = desc_input.text().strip()
                new_id = db_add_printable(
                    table, cat, short, p, desc, default_paper)
                if new_id:
                    uploaded_count += 1

            if uploaded_count:
                show_toast(self,
                           f"✓ {uploaded_count} belge yüklendi",
                           level="success")
                _refresh_all_tabs()

        upload_btn.clicked.connect(_do_upload)

        dlg.exec()

    def _show_common_phrases_popup(self):
        """v68-AI: Show popup with the doctor's most-used phrases.
        Clicking a phrase inserts it at the cursor in note_edit.

        Phrases come from SmartTextEngine.common_phrases() — these
        are learned automatically as the doctor writes notes.
        """
        try:
            phrases = SmartTextEngine.common_phrases(min_count=2, limit=30)
        except Exception as ex:
            _log_warning(f"_show_common_phrases_popup gather: {ex}")
            phrases = []

        dlg = QDialog(self)
        dlg.setWindowTitle("💡 Sık Kullandığın İfadeler")
        dlg.setMinimumSize(520, 480)
        dlg.setModal(True)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Hero
        hero = QWidget()
        hero.setFixedHeight(72)
        hero.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #5A1FB8,stop:1 #7C3AED);")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(24, 12, 24, 12)
        ht = QLabel("💡  Sık Kullandığın İfadeler")
        ht.setStyleSheet(
            "color:white;font:800 18px 'Segoe UI';background:transparent;")
        hl.addWidget(ht)
        sub = QLabel("Tıkla → not alanına ekle")
        sub.setStyleSheet(
            "color:rgba(255,255,255,0.9);font:500 11px 'Segoe UI';"
            "background:transparent;")
        hl.addWidget(sub)
        root.addWidget(hero)

        # Body
        body = QScrollArea()
        body.setWidgetResizable(True)
        body.setStyleSheet(
            "QScrollArea{background:white;border:none;}")
        content = QWidget()
        content.setStyleSheet("background:white;")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(16, 12, 16, 12)
        content_lay.setSpacing(6)

        if not phrases:
            empty = EmptyStateWidget(
                icon="💭",
                title="Henüz öğrenilmiş ifade yok",
                subtitle="Not alanlarında yazdıkça AI, en sık "
                         "kullandığın ifadeleri öğrenir ve burada "
                         "tek tıkla eklenebilir hale getirir. "
                         "\n\nİlk birkaç notu yazdıktan sonra "
                         "tekrar deneyebilirsin.",
                parent=content)
            content_lay.addWidget(empty)
        else:
            hdr = QLabel(
                f"<b>{len(phrases)} ifade</b> "
                f"<span style='color:#888;'>(en çok kullanılanlar önce)</span>")
            hdr.setStyleSheet(
                "font:500 11px 'Segoe UI';padding:4px;color:#555;")
            content_lay.addWidget(hdr)

            for phrase, freq in phrases:
                chip = QPushButton(
                    f"{phrase}   ·   {freq}×")
                chip.setCursor(Qt.PointingHandCursor)
                chip.setToolTip(
                    f"<b>{phrase}</b><br>"
                    f"<span style='color:#888;'>"
                    f"{freq} kez kullandın</span><br>"
                    f"<i>Tıkla → not alanına ekle</i>")
                chip.setStyleSheet(
                    "QPushButton{background:#F5F3FA;color:#333;"
                    "border:1px solid #C8B8E0;padding:8px 12px;"
                    "font:500 12px 'Segoe UI';border-radius:4px;"
                    "text-align:left;}"
                    "QPushButton:hover{background:#E8DDFA;"
                    "border-color:#7C3AED;color:#5A1FB8;}")

                def _insert(_checked=False, p=phrase):
                    try:
                        if hasattr(self, "note_edit"):
                            cursor = self.note_edit.textCursor()
                            # Add space if cursor isn't at start / after space
                            pos = cursor.position()
                            if pos > 0:
                                doc_text = self.note_edit.toPlainText()
                                if (pos <= len(doc_text)
                                        and doc_text[pos - 1]
                                        not in (" ", "\n", "\t")):
                                    cursor.insertText(" ")
                            cursor.insertText(p + " ")
                            self.note_edit.setFocus()
                            show_toast(self, f"✓ Eklendi: {p[:40]}",
                                       level="success", duration_ms=2000)
                            dlg.close()
                    except Exception as _ex:
                        _log_warning(f"phrase insert: {_ex}")

                chip.clicked.connect(_insert)
                content_lay.addWidget(chip)

        content_lay.addStretch()
        body.setWidget(content)
        root.addWidget(body, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 10, 16, 12)
        btn_row.addStretch()
        btn_close = QPushButton("Kapat")
        btn_close.setStyleSheet(
            "QPushButton{background:#E5EEF7;color:#404040;"
            "padding:8px 18px;border:1px solid #B8D4E8;"
            "border-radius:4px;font:500 11px 'Segoe UI';}"
            "QPushButton:hover{background:#D5E5F5;}")
        btn_close.clicked.connect(dlg.close)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        dlg.exec()

    def _refresh_ai_status_badge(self):
        """v68-AI: Update the AI badge in the status bar with live counts.
        Shows how much the AI has learned. Cheap — runs every 60s."""
        if not hasattr(self, "ai_status_badge"):
            return
        try:
            stats = BehaviorLearner.get_usage_stats(days=30)
            phrases = SmartTextEngine.common_phrases(min_count=2, limit=1000)
            n_actions = stats.get("total_actions", 0)
            n_patients = stats.get("unique_patients", 0)
            n_phrases = len(phrases)

            if n_actions == 0:
                txt = "🤖 AI: hazır"
                tip = ("AI Asistan henüz veri toplamadı.\n"
                       "Programı kullandıkça öğrenecek.\n"
                       "Tıkla: dashboard aç")
            else:
                # Compact display
                if n_actions >= 1000:
                    a_str = f"{n_actions // 1000}K"
                else:
                    a_str = str(n_actions)
                txt = f"🤖 AI · {a_str} aksiyon · {n_patients} hasta"
                tip = (f"🤖 AI Asistan (son 30 gün)\n"
                       f"  • Toplam aksiyon: {n_actions}\n"
                       f"  • Farklı hasta: {n_patients}\n"
                       f"  • Öğrenilen ifade: {n_phrases}\n"
                       f"\nTıkla: dashboard aç (Ctrl+Shift+A)")
            self.ai_status_badge.setText(txt)
            self.ai_status_badge.setToolTip(tip)
        except Exception as _ex:
            _log_warning(f"_refresh_ai_status_badge: {_ex}")

    def _refresh_welcome_card_personalized(self):
        """v68-AI: Append a personalized footer to the welcome card
        showing the doctor's most-recent activity (last 3 patients +
        time-of-day greeting). Called whenever no patient is selected.
        """
        if not hasattr(self, "welcome_card"):
            return
        try:
            from datetime import datetime as _dt
            now = _dt.now()
            hour = now.hour
            if 5 <= hour < 11:
                greeting = "☀️ Günaydın"
                bg_grad = "#FFF8E0,#FFE6B5"
                accent = "#C46500"
            elif 11 <= hour < 17:
                greeting = "🌤 İyi günler"
                bg_grad = "#E5F1FB,#B8D4E8"
                accent = "#005A9E"
            elif 17 <= hour < 21:
                greeting = "🌅 İyi akşamlar"
                bg_grad = "#FFE0E5,#FFC8D0"
                accent = "#9A1B1F"
            else:
                greeting = "🌙 İyi geceler"
                bg_grad = "#E8DDFA,#C8B8E0"
                accent = "#3F1480"

            # Get recent patients
            recent = BehaviorLearner.get_top_patients(limit=3, days=7)

            # Build personalized HTML footer
            footer_parts = [
                f"<div style='margin-top:24px;padding:14px 18px;"
                f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"stop:0 {bg_grad.split(',')[0]},"
                f"stop:1 {bg_grad.split(',')[1]});"
                f"border-radius:8px;border-left:4px solid {accent};"
                f"text-align:left;'>",
                f"<div style='font:700 14px Segoe UI;color:{accent};"
                f"margin-bottom:8px;'>{greeting}, doktor!</div>",
            ]

            if recent:
                footer_parts.append(
                    "<div style='font:600 11px Segoe UI;color:#444;"
                    "margin-bottom:6px;'>👥 Son 7 günde en çok ziyaret:</div>")
                footer_parts.append("<div style='font:500 11px Segoe UI;color:#555;'>")
                for i, (pkey, count) in enumerate(recent, 1):
                    try:
                        name = format_patient_name(pkey)
                    except Exception:
                        name = pkey
                    footer_parts.append(
                        f"&nbsp;&nbsp;<b>{i}.</b> {name} "
                        f"<span style='color:{accent};'>({count}x)</span><br>")
                footer_parts.append("</div>")
            else:
                footer_parts.append(
                    "<div style='font:500 11px Segoe UI;color:#777;"
                    "font-style:italic;'>"
                    "Hasta seçtikçe ve programı kullandıkça AI senin "
                    "alışkanlıklarını öğrenecek ve burada gösterecek."
                    "</div>")

            footer_parts.append("</div>")
            footer_html = "".join(footer_parts)

            # Get current text and append (or replace existing AI footer)
            cur = self.welcome_card.text() or ""
            # Strip any previous AI footer marker
            marker = "<!-- AI_FOOTER -->"
            if marker in cur:
                cur = cur.split(marker)[0]
            new_html = cur + marker + footer_html
            self.welcome_card.setText(new_html)
        except Exception as ex:
            _log_warning(f"_refresh_welcome_card_personalized: {ex}")

    def _show_ai_assistant_dashboard(self):
        """🤖 AI Asistan — kullanım analizi + kişisel öneriler.

        v68-AI: Shows the doctor's usage patterns:
          • En çok ziyaret ettiği hastalar (son 30 gün)
          • En çok kullandığı quick action'lar / komutlar
          • Saat bazlı aktivite paterni
          • Kişisel öneriler ("Bu hafta NIPT taraması atladığın 3 hasta var")

        Privacy: All data is local. No network calls.
        """
        try:
            stats = BehaviorLearner.get_usage_stats(days=30)
            top_actions = BehaviorLearner.get_top_actions(limit=10, days=30)
            top_patients = BehaviorLearner.get_top_patients(limit=8, days=30)
        except Exception as ex:
            _log_warning("ai_assistant: gather", exc=ex)
            QMessageBox.warning(self, "AI Asistan",
                                f"Veri toplanamadı: {ex}")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("🤖 AI Asistan — Kullanım Analizi")
        dlg.setMinimumSize(820, 600)
        dlg.setModal(False)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Hero
        hero = QWidget()
        hero.setFixedHeight(110)
        hero.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #5A1FB8,stop:0.5 #7C3AED,stop:1 #0078D4);")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(28, 18, 28, 18)
        hl.setSpacing(2)
        ht = QLabel("🤖  AI Asistan")
        ht.setStyleSheet(
            "color:white;font:800 26px 'Segoe UI';background:transparent;")
        hl.addWidget(ht)
        sub = QLabel(
            "Davranışlarını öğrenip yükünü hafifletmek için burada — "
            "tüm veriler bilgisayarında kalır")
        sub.setStyleSheet(
            "color:rgba(255,255,255,0.92);font:500 12px 'Segoe UI';"
            "background:transparent;")
        hl.addWidget(sub)
        root.addWidget(hero)

        # Tabs
        tabs = QTabWidget()
        tabs.setStyleSheet(
            "QTabWidget::pane{border:none;background:white;}"
            "QTabBar::tab{padding:10px 20px;background:#F5F3FA;"
            "border:none;font:600 12px 'Segoe UI';color:#444;}"
            "QTabBar::tab:selected{background:white;color:#5A1FB8;"
            "border-bottom:3px solid #5A1FB8;}")

        # Tab 1: Genel Bakış
        ov = QWidget()
        ov_lay = QVBoxLayout(ov)
        ov_lay.setContentsMargins(20, 16, 20, 16)
        ov_lay.setSpacing(8)

        total = stats.get("total_actions", 0)
        unique_patients = stats.get("unique_patients", 0)
        days = stats.get("days", 30)

        if total == 0:
            empty = EmptyStateWidget(
                icon="🤖",
                title="Henüz veri toplamadım",
                subtitle=f"Son {days} günde herhangi bir AI takip "
                         f"edilmiş aksiyon yok. Programı kullandıkça "
                         f"davranış paternlerini öğreneceğim.",
                parent=ov)
            ov_lay.addWidget(empty)
        else:
            # Big number cards
            big_cards = QHBoxLayout()
            big_cards.setSpacing(12)

            def _make_big_card(label, value, color):
                card = QWidget()
                card.setStyleSheet(
                    f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                    f"stop:0 white,stop:1 #FAFAFA);"
                    f"border:2px solid {color};border-radius:8px;")
                cl = QVBoxLayout(card)
                cl.setContentsMargins(16, 12, 16, 12)
                vl = QLabel(str(value))
                vl.setStyleSheet(
                    f"color:{color};font:800 36px 'Segoe UI';"
                    f"background:transparent;border:none;")
                vl.setAlignment(Qt.AlignCenter)
                cl.addWidget(vl)
                ll = QLabel(label)
                ll.setStyleSheet(
                    "color:#555;font:600 11px 'Segoe UI';"
                    "background:transparent;border:none;")
                ll.setAlignment(Qt.AlignCenter)
                cl.addWidget(ll)
                return card

            big_cards.addWidget(_make_big_card(
                "Toplam Aksiyon", total, "#5A1FB8"))
            big_cards.addWidget(_make_big_card(
                "Farklı Hasta", unique_patients, "#0078D4"))
            big_cards.addWidget(_make_big_card(
                "Gün", days, "#107C10"))
            ov_lay.addLayout(big_cards)

            # By type
            by_type = stats.get("by_type", {})
            if by_type:
                ov_lay.addSpacing(10)
                tlbl = QLabel("📊 Aksiyon Türleri")
                tlbl.setStyleSheet(
                    "font:700 14px 'Segoe UI';color:#5A1FB8;padding:4px 0;")
                ov_lay.addWidget(tlbl)
                for tname, tcount in list(by_type.items())[:5]:
                    bar_w = int(min(100, tcount * 100 / max(by_type.values())))
                    row = QLabel(
                        f"<b>{tname}</b> — {tcount} kez<br>"
                        f"<span style='background:#7C3AED;color:white;"
                        f"padding:2px 8px;display:inline-block;"
                        f"min-width:{bar_w}px;border-radius:3px;"
                        f"font:600 9px Segoe UI;'>{bar_w}%</span>")
                    row.setStyleSheet(
                        "padding:6px 10px;background:#F8F9FA;"
                        "border-radius:4px;margin:2px 0;")
                    ov_lay.addWidget(row)

            # Time of day
            by_hour = stats.get("by_hour", {})
            if by_hour:
                ov_lay.addSpacing(10)
                hlbl = QLabel("⏰ Saat Bazlı Aktivite")
                hlbl.setStyleSheet(
                    "font:700 14px 'Segoe UI';color:#5A1FB8;padding:4px 0;")
                ov_lay.addWidget(hlbl)
                # Find peak hours (top 3)
                sorted_hours = sorted(
                    by_hour.items(), key=lambda x: -x[1])[:3]
                peak_lbl = QLabel(
                    "🔥 En aktif saatlerin: " +
                    " · ".join(f"<b>{h:02d}:00</b> ({c}x)"
                                for h, c in sorted_hours))
                peak_lbl.setStyleSheet(
                    "padding:8px 12px;background:#FFF3E0;"
                    "border-left:4px solid #E58E00;border-radius:4px;"
                    "font:500 12px 'Segoe UI';color:#444;")
                ov_lay.addWidget(peak_lbl)

        ov_lay.addStretch()
        tabs.addTab(ov, "📊 Genel Bakış")

        # Tab 2: Top Patients
        pt = QWidget()
        pt_lay = QVBoxLayout(pt)
        pt_lay.setContentsMargins(20, 16, 20, 16)
        pt_lay.setSpacing(6)
        if top_patients:
            tlbl = QLabel("👥 En Çok Ziyaret Ettiğin Hastalar (son 30 gün)")
            tlbl.setStyleSheet(
                "font:700 14px 'Segoe UI';color:#5A1FB8;padding:4px 0;")
            pt_lay.addWidget(tlbl)
            for i, (pkey, count) in enumerate(top_patients, 1):
                try:
                    name = format_patient_name(pkey)
                except Exception:
                    name = pkey
                row = QLabel(
                    f"<b>{i}.</b>  {name} "
                    f"<span style='color:#5A1FB8;font-weight:700;'>"
                    f"({count} kez)</span>")
                row.setStyleSheet(
                    "padding:8px 12px;background:#F5F3FA;"
                    "border-left:3px solid #7C3AED;border-radius:4px;"
                    "font:500 12px 'Segoe UI';color:#222;margin:1px 0;")
                pt_lay.addWidget(row)
        else:
            pt_lay.addWidget(EmptyStateWidget(
                icon="👥",
                title="Henüz hasta verisi yok",
                subtitle="Hasta seçimleri henüz takip edilmedi.",
                parent=pt))
        pt_lay.addStretch()
        tabs.addTab(pt, f"👥 En Çok Hastalar ({len(top_patients)})")

        # Tab 3: Top Actions
        at = QWidget()
        at_lay = QVBoxLayout(at)
        at_lay.setContentsMargins(20, 16, 20, 16)
        at_lay.setSpacing(6)
        if top_actions:
            albl = QLabel("⚡ En Sık Kullandığın Eylemler (son 30 gün)")
            albl.setStyleSheet(
                "font:700 14px 'Segoe UI';color:#5A1FB8;padding:4px 0;")
            at_lay.addWidget(albl)
            # Friendly names for slot names
            friendly = {
                "_show_clinical_intelligence_dialog": "🧠 Klinik Akıl",
                "_show_pregnancy_timeline_dialog": "🗓 Timeline",
                "_show_smart_search_dialog": "🔍 Smart Search",
                "_generate_referral_letter": "📨 Sevk Mektubu",
                "_show_consent_forms_dialog": "📋 Onam Formları",
                "_show_prescription_dialog": "💊 Hazır Reçeteler",
                "_show_demographics_dialog": "👤 Hasta Bilgileri",
                "_show_diet_sheet_dialog": "🍎 Diyet",
                "_show_growth_trend_dialog": "📈 Büyüme Eğrileri",
                "_show_patient_test_sheet": "🧪 Test Listesi",
                "_open_followup_tab_for_mode": "📋 Planlama",
                "_open_flag_editor_dialog": "🏷 Bayraklar",
                "copy_summary": "📝 Kısa Özet",
                "copy_long_summary": "📋 Uzun Özet",
            }
            for i, (action, count) in enumerate(top_actions, 1):
                fname = friendly.get(action, action)
                row = QLabel(
                    f"<b>{i}.</b>  {fname} "
                    f"<span style='color:#5A1FB8;font-weight:700;'>"
                    f"({count} kez)</span>")
                row.setStyleSheet(
                    "padding:8px 12px;background:#F5F3FA;"
                    "border-left:3px solid #7C3AED;border-radius:4px;"
                    "font:500 12px 'Segoe UI';color:#222;margin:1px 0;")
                at_lay.addWidget(row)
        else:
            at_lay.addWidget(EmptyStateWidget(
                icon="⚡",
                title="Henüz aksiyon verisi yok",
                subtitle="Quick action'ları kullandıkça burada görüneceler.",
                parent=at))
        at_lay.addStretch()
        tabs.addTab(at, f"⚡ Eylemler ({len(top_actions)})")

        # v68-AI: Tab 4 — Öğrenilen İfadeler (top phrases)
        try:
            top_phrases = SmartTextEngine.common_phrases(min_count=2,
                                                          limit=40)
        except Exception:
            top_phrases = []
        ph = QWidget()
        ph_lay = QVBoxLayout(ph)
        ph_lay.setContentsMargins(20, 16, 20, 16)
        ph_lay.setSpacing(6)
        if top_phrases:
            plbl = QLabel(
                "📝 Yazdığın Notlardan Öğrendiğim İfadeler "
                "(autocomplete olarak önerilir)")
            plbl.setStyleSheet(
                "font:700 14px 'Segoe UI';color:#5A1FB8;padding:4px 0;")
            plbl.setWordWrap(True)
            ph_lay.addWidget(plbl)
            for i, (phrase, freq) in enumerate(top_phrases[:30], 1):
                row = QLabel(
                    f"<b>{i}.</b>  \"{phrase}\" "
                    f"<span style='color:#5A1FB8;font-weight:700;'>"
                    f"({freq}x)</span>")
                row.setStyleSheet(
                    "padding:8px 12px;background:#F5F3FA;"
                    "border-left:3px solid #7C3AED;border-radius:4px;"
                    "font:500 11px 'Segoe UI';color:#222;margin:1px 0;")
                row.setWordWrap(True)
                ph_lay.addWidget(row)
        else:
            ph_lay.addWidget(EmptyStateWidget(
                icon="📝",
                title="Henüz öğrenilmiş ifade yok",
                subtitle="Notlar sekmesinde yazı yazdıkça AI sık "
                         "kullandığın ifadeleri öğrenip burada listeler.\n"
                         "Bu ifadeler bir sonraki yazımda otomatik öneri "
                         "olarak çıkacak.",
                parent=ph))
        ph_lay.addStretch()
        tabs.addTab(ph, f"📝 İfadeler ({len(top_phrases)})")

        root.addWidget(tabs, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 12, 20, 14)
        btn_row.addStretch()
        btn_close = QPushButton("Kapat")
        btn_close.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #7C3AED,stop:1 #5A1FB8);color:white;"
            "padding:9px 24px;border:none;border-radius:4px;"
            "font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:#5A1FB8;}")
        btn_close.clicked.connect(dlg.close)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        if not hasattr(self, "_open_ai_dialogs"):
            self._open_ai_dialogs = []
        self._open_ai_dialogs.append(dlg)
        dlg.finished.connect(
            lambda _: (self._open_ai_dialogs.remove(dlg)
                       if dlg in self._open_ai_dialogs else None))
        dlg.show()

    def _show_clinical_intelligence_dialog(self):
        """🧠 Klinik Akıl — premium dialog showing automated risk
        scoring + AI-style insights for the current patient.

        v68-UI-PREMIUM: This is the marquee feature — what makes the
        app feel "smart" and "modern". Doctor opens it once per
        patient and gets a summary of:
          • Numeric risk score (0-100) with category
          • Contributing risk factors with explanations
          • Specific recommended actions (ACOG/RCOG-based)
          • Time-sensitive alerts (NIPT window, OGTT, Tdap, etc.)
          • Visit cadence analysis
          • Missing demographics / completeness check

        Layout:
          ┌─ Hero (gradient mor, score circle) ──────────────────┐
          │  🧠 Klinik Akıl  ·  Hasta Adı                         │
          │                                              [SCORE] │
          ├─ Tabs ───────────────────────────────────────────────┤
          │ [Genel Bakış] [Risk Faktörleri] [Öneriler] [Uyarılar]│
          ├─ Body ───────────────────────────────────────────────┤
          │  ...                                                  │
          └───────────────────────────────────────────────────────┘
        """
        if self.current_patient is None:
            QMessageBox.information(
                self, "Klinik Akıl",
                "Önce bir hasta seçin.")
            return

        patient_key = self.current_patient.name
        display_name = format_patient_name(patient_key)

        # Gather data
        try:
            demo = load_patient_demographics(patient_key) or {}
            manual = get_patient_manual_meta(patient_key) or {}
            # Merge manual into demo (age comes from manual usually)
            if manual.get("age") and not demo.get("age"):
                demo["age"] = manual.get("age")
            flags = get_patient_flags(patient_key) or {}
            visits = get_subfolders(self.current_patient) or []

            # GA from latest PDF
            ga_days = None
            latest_pdf_data = None
            try:
                if visits:
                    pdf = get_latest_pdf_in_folder(visits[0])
                    if pdf:
                        latest_pdf_data = parse_pdf_summary_data(pdf)
                        ga_days = latest_pdf_data.get("ga_days")
            except Exception as _ex:
                _log_warning(f"clinical_ai: GA lookup: {_ex}")

            # Run intelligence engines
            risk = compute_pregnancy_risk_score(
                patient_key, demo, flags, ga_days)
            insights = generate_clinical_insights(
                patient_key, demo, flags, visits, ga_days, latest_pdf_data)
        except Exception as ex:
            _log_warning("_show_clinical_intelligence_dialog", exc=ex)
            QMessageBox.warning(
                self, "Klinik Akıl",
                f"Veri toplanırken hata: {ex}")
            return

        # Build dialog
        dlg = QDialog(self)
        dlg.setWindowTitle(f"🧠 Klinik Akıl — {display_name}")
        dlg.setMinimumSize(820, 660)
        dlg.setModal(False)  # Allow doctor to keep it open while working

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ─── Hero with risk score ──────────────────────────────
        hero = QWidget()
        hero.setFixedHeight(140)
        # Gradient — colour shifts based on risk severity
        risk_color = risk.get("color", "#5A1FB8")
        hero.setStyleSheet(
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"stop:0 #5A1FB8,stop:0.6 #7C3AED,stop:1 {risk_color});")

        hero_lay = QHBoxLayout(hero)
        hero_lay.setContentsMargins(28, 16, 28, 16)
        hero_lay.setSpacing(16)

        # Left: title + name
        left_v = QVBoxLayout()
        left_v.setSpacing(4)
        title_lbl = QLabel("🧠  Klinik Akıl")
        title_lbl.setStyleSheet(
            "color:white;font:800 26px 'Segoe UI';background:transparent;")
        left_v.addWidget(title_lbl)
        sub_lbl = QLabel(display_name)
        sub_lbl.setStyleSheet(
            "color:rgba(255,255,255,0.95);font:600 16px 'Segoe UI';"
            "background:transparent;")
        left_v.addWidget(sub_lbl)

        # Quick stats line
        stats_parts = []
        if demo.get("age"):
            stats_parts.append(f"{demo['age']} yaş")
        if demo.get("gravida") is not None:
            g = demo.get("gravida")
            p = demo.get("para") or 0
            a = demo.get("abortus") or 0
            stats_parts.append(f"G{g} P{p} A{a}")
        if ga_days and ga_days > 0:
            stats_parts.append(f"{ga_days // 7}+{ga_days % 7} hafta")
        if stats_parts:
            stat_lbl = QLabel("  ·  ".join(stats_parts))
            stat_lbl.setStyleSheet(
                "color:rgba(255,255,255,0.85);font:500 12px 'Segoe UI';"
                "background:transparent;padding-top:4px;")
            left_v.addWidget(stat_lbl)
        left_v.addStretch()
        hero_lay.addLayout(left_v, 1)

        # Right: big score circle
        score_w = QWidget()
        score_w.setFixedSize(108, 108)
        score_w.setStyleSheet(
            "background:rgba(255,255,255,0.18);"
            "border:3px solid rgba(255,255,255,0.6);"
            "border-radius:54px;")
        score_inner = QVBoxLayout(score_w)
        score_inner.setContentsMargins(0, 14, 0, 14)
        score_inner.setSpacing(0)
        score_num = QLabel(str(risk["score"]))
        score_num.setAlignment(Qt.AlignCenter)
        score_num.setStyleSheet(
            "color:white;font:900 36px 'Segoe UI';background:transparent;"
            "border:none;")
        score_inner.addWidget(score_num)
        score_lbl = QLabel("/ 100")
        score_lbl.setAlignment(Qt.AlignCenter)
        score_lbl.setStyleSheet(
            "color:rgba(255,255,255,0.85);font:500 11px 'Segoe UI';"
            "background:transparent;border:none;")
        score_inner.addWidget(score_lbl)
        cat_lbl = QLabel(risk["category_label"])
        cat_lbl.setAlignment(Qt.AlignCenter)
        cat_lbl.setStyleSheet(
            "color:white;font:700 10px 'Segoe UI';background:transparent;"
            "border:none;letter-spacing:1px;")
        score_inner.addWidget(cat_lbl)
        hero_lay.addWidget(score_w)
        root.addWidget(hero)

        # ─── Tabs ──────────────────────────────────────────────
        tabs = QTabWidget()
        tabs.setStyleSheet(
            "QTabWidget::pane{border:none;background:white;}"
            "QTabBar::tab{padding:10px 20px;background:#F5F3FA;"
            "border:none;font:600 12px 'Segoe UI';color:#444;}"
            "QTabBar::tab:selected{background:white;color:#5A1FB8;"
            "border-bottom:3px solid #5A1FB8;}")

        # Tab 1: Genel Bakış
        overview = QWidget()
        ov_lay = QVBoxLayout(overview)
        ov_lay.setContentsMargins(20, 16, 20, 16)
        ov_lay.setSpacing(8)

        # Insights cards
        if insights:
            insights_lbl = QLabel("💡 Akıllı İçgörüler")
            insights_lbl.setStyleSheet(
                "font:700 14px 'Segoe UI';color:#5A1FB8;padding:4px 0;")
            ov_lay.addWidget(insights_lbl)

            for icon, sev, msg in insights:
                sev_colors = {
                    "critical": ("#FFEBEB", "#C42B1C"),
                    "warning":  ("#FFF7E6", "#E58E00"),
                    "info":     ("#EBF4FB", "#005A9E"),
                    "good":     ("#EFF9EF", "#107C10"),
                    "tip":      ("#F5F3FA", "#5A1FB8"),
                }.get(sev, ("#F5F5F5", "#666"))
                bg, fg = sev_colors
                card = QLabel(f"<b>{icon}</b>  {msg}")
                card.setWordWrap(True)
                card.setStyleSheet(
                    f"background:{bg};color:{fg};padding:9px 14px;"
                    f"border-left:4px solid {fg};border-radius:4px;"
                    f"font:500 12px 'Segoe UI';")
                ov_lay.addWidget(card)
        else:
            ov_lay.addWidget(QLabel(
                "<i style='color:#888;'>Şu anda öne çıkan klinik içgörü yok. "
                "Hasta düşük riskli grupta ve takip düzenli görünüyor.</i>"))

        ov_lay.addStretch()
        tabs.addTab(overview, "📊 Genel Bakış")

        # Tab 2: Risk Faktörleri
        risk_tab = QWidget()
        rt_lay = QVBoxLayout(risk_tab)
        rt_lay.setContentsMargins(20, 16, 20, 16)
        rt_lay.setSpacing(6)
        rt_browser = QTextBrowser()
        rt_browser.setHtml(get_risk_summary_html(risk))
        rt_browser.setStyleSheet(
            "QTextBrowser{border:none;background:white;font:12px 'Segoe UI';}")
        rt_lay.addWidget(rt_browser, 1)
        tabs.addTab(risk_tab, f"⚖️ Risk ({risk['score']}/100)")

        # Tab 3: Öneriler (recommendations)
        rec_tab = QWidget()
        rec_lay = QVBoxLayout(rec_tab)
        rec_lay.setContentsMargins(20, 16, 20, 16)
        rec_lay.setSpacing(6)
        if risk.get("recommendations"):
            rec_lbl = QLabel(
                f"📋 ACOG / RCOG temelli {len(risk['recommendations'])} öneri:")
            rec_lbl.setStyleSheet(
                "font:700 14px 'Segoe UI';color:#5A1FB8;padding:4px 0;")
            rec_lay.addWidget(rec_lbl)
            for i, rec in enumerate(risk["recommendations"], 1):
                card = QLabel(f"<b>{i}.</b>  {rec}")
                card.setWordWrap(True)
                card.setStyleSheet(
                    "background:#F5F3FA;padding:10px 14px;"
                    "border-left:4px solid #7C3AED;"
                    "font:500 12px 'Segoe UI';color:#333;")
                rec_lay.addWidget(card)
        else:
            rec_lay.addWidget(QLabel(
                "<i style='color:#888;'>Spesifik öneri yok — standart "
                "antenatal takip uygundur.</i>"))
        rec_lay.addStretch()
        tabs.addTab(rec_tab, f"💊 Öneriler ({len(risk.get('recommendations', []))})")

        # Tab 4: Uyarılar (alerts)
        alert_tab = QWidget()
        al_lay = QVBoxLayout(alert_tab)
        al_lay.setContentsMargins(20, 16, 20, 16)
        al_lay.setSpacing(6)
        all_alerts = list(risk.get("alerts", []))
        if all_alerts:
            for sev, msg in all_alerts:
                sev_colors = {
                    "critical": ("#FFEBEB", "#C42B1C"),
                    "warning":  ("#FFF7E6", "#E58E00"),
                    "info":     ("#EBF4FB", "#005A9E"),
                    "good":     ("#EFF9EF", "#107C10"),
                }.get(sev, ("#F5F5F5", "#666"))
                bg, fg = sev_colors
                card = QLabel(msg)
                card.setWordWrap(True)
                card.setStyleSheet(
                    f"background:{bg};color:{fg};padding:12px 14px;"
                    f"border-left:5px solid {fg};border-radius:4px;"
                    f"font:600 12px 'Segoe UI';")
                al_lay.addWidget(card)
        else:
            al_lay.addWidget(QLabel(
                "<i style='color:#888;'>Aktif uyarı yok.</i>"))
        al_lay.addStretch()
        tabs.addTab(alert_tab, f"🚨 Uyarılar ({len(all_alerts)})")

        root.addWidget(tabs, 1)

        # ─── Buttons ───────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 12, 20, 14)

        btn_copy = QPushButton("📋 Tüm Raporu Kopyala")
        btn_copy.setToolTip(
            "Risk değerlendirmesini metin olarak panoya kopyala "
            "— hasta dosyası, konsültasyon, sevk için")
        btn_copy.setStyleSheet(
            "QPushButton{background:#E5EEF7;color:#404040;"
            "padding:9px 18px;border:1px solid #B8D4E8;"
            "border-radius:4px;font:500 11px 'Segoe UI';}"
            "QPushButton:hover{background:#D5E5F5;}")

        def _copy_report():
            try:
                lines = [
                    f"=== KLİNİK AKIL RAPORU ===",
                    f"Hasta: {display_name}",
                    f"Tarih: {datetime.now().strftime('%d.%m.%Y %H:%M')}",
                    f"",
                    f"RİSK SKORU: {risk['score']}/100  ({risk['category_label']})",
                    f"",
                ]
                if risk.get("factors"):
                    lines.append("RİSK FAKTÖRLERİ:")
                    for name, w, expl in risk["factors"]:
                        lines.append(f"  • {name} (+{w}): {expl}")
                    lines.append("")
                if risk.get("recommendations"):
                    lines.append("ÖNERİLER:")
                    for r in risk["recommendations"]:
                        lines.append(f"  • {r}")
                    lines.append("")
                if risk.get("alerts"):
                    lines.append("UYARILAR:")
                    for sev, msg in risk["alerts"]:
                        lines.append(f"  [{sev.upper()}] {msg}")
                    lines.append("")
                if insights:
                    lines.append("AKILLI İÇGÖRÜLER:")
                    for icon, sev, msg in insights:
                        lines.append(f"  {icon} {msg}")
                lines.append("")
                lines.append("⚠ Bu rapor yardımcı niteliktedir. "
                             "Tüm klinik kararlar doktora aittir.")
                cb = QApplication.clipboard()
                cb.setText("\n".join(lines))
                self.statusBar().showMessage(
                    "✓ Klinik Akıl raporu panoya kopyalandı", 4000)
                show_toast(self,
                           "Klinik Akıl raporu panoya kopyalandı",
                           level="success")
            except Exception as ex:
                _log_warning(f"copy clinical report: {ex}")
        btn_copy.clicked.connect(_copy_report)
        btn_row.addWidget(btn_copy)

        btn_row.addStretch()

        btn_close = QPushButton("Kapat")
        btn_close.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #7C3AED,stop:1 #5A1FB8);color:white;"
            "padding:9px 24px;border:none;border-radius:4px;"
            "font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:qlineargradient("
            "x1:0,y1:0,x2:0,y2:1,stop:0 #5A1FB8,stop:1 #3F1480);}")
        btn_close.clicked.connect(dlg.close)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        # Track open dialogs so we don't GC them
        if not hasattr(self, "_open_clinical_dialogs"):
            self._open_clinical_dialogs = []
        self._open_clinical_dialogs.append(dlg)
        dlg.finished.connect(
            lambda _: (self._open_clinical_dialogs.remove(dlg)
                       if dlg in self._open_clinical_dialogs else None))
        dlg.show()

    def _show_diet_sheet_dialog(self):
        """Show diet picker → editable preview → print.

        Flow:
          1. Patient is OPTIONAL — without a patient we still show the
             dialog as a printable template (no name, no date binding).
             This is intentional: the doctor may want to print a blank
             handout to give to a patient who isn't yet in the system.
          2. Show a radio-button selector for the 4 diet types.
          3. Doctor can switch diet type (with confirmation if edited)
             or freely edit the HTML.
          4. Print button dispatches to QPrinter A4.
        """
        # v68: No-patient mode is now allowed — the dialog acts as a
        # blank-template printer. Header just omits the patient name.
        pname = "—"
        if self.current_patient is not None:
            pname = format_patient_name(self.current_patient.name)
        today = datetime.now().strftime("%d.%m.%Y")

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle(f"Diyet Listesi — {pname}")
        dlg.resize(900, 800)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(12, 12, 12, 12)

        # ── Header with patient context (v68 hero) ──────────────────────
        header = QLabel(
            f"<div style='padding:14px 18px;'>"
            f"<div style='font-size:18px;font-weight:800;color:#FFFFFF;'>"
            f"🍎  Diyet Listesi</div>"
            f"<div style='color:rgba(255,255,255,0.9);margin-top:4px;"
            f"font-size:12px;'>"
            f"<b>👩 {pname}</b>  ·  📅 {today}"
            f"</div>"
            f"<div style='color:rgba(255,255,255,0.78);margin-top:2px;"
            f"font-size:11px;'>"
            f"Diyet tipini seçin → Metni gerekirse düzenleyin → Yazdırın."
            f"</div></div>")
        header.setTextFormat(Qt.RichText)
        header.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #2E5F2E, stop:0.5 #107C10, stop:1 #4DA84D);"
            "border-radius:10px;color:#FFFFFF;}")
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            shf = QGraphicsDropShadowEffect()
            shf.setBlurRadius(15)
            shf.setColor(QColor(16, 124, 16, 90))
            shf.setOffset(0, 3)
            header.setGraphicsEffect(shf)
        except Exception as _ex:
            _log_warning("diet hero shadow", exc=_ex)
        v.addWidget(header)

        # ── Diet picker ─────────────────────────────────────────────────
        # v68: added "🌸 İnfertilite" diet option. For gynecologic-only
        # patients we auto-select it — they're not pregnant, so gebelik
        # dietleri default mantıksız. Doktor istediği gibi değiştirebilir.
        picker_row = QHBoxLayout()
        picker_row.addWidget(QLabel("<b>Diyet tipi:</b>"))

        from PySide6.QtWidgets import QRadioButton, QButtonGroup
        group = QButtonGroup(dlg)
        rb_general = QRadioButton("🤰 Gebelik (genel)")
        rb_diabetic = QRadioButton("💉 Diyabetik gebe (GDM)")
        rb_border = QRadioButton("⚖️ Sınırda şeker")
        rb_infert = QRadioButton("🌸 İnfertilite / Gebelik öncesi")

        # Default selection depends on patient type AND manual mode
        # override. If the doctor manually toggled to jinekoloji even
        # without a patient selected, the default is the infertilite
        # plan — they're clearly heading in that direction.
        _default_rb = rb_general
        try:
            override = getattr(self, "_mode_override", None)
            if override == "gynecologic":
                _default_rb = rb_infert
            elif override == "obstetric":
                _default_rb = rb_general
            elif self.current_patient is not None and \
                    is_gynecologic_patient(self.current_patient):
                _default_rb = rb_infert
        except Exception as _ex:
            _log_warning("diet: gyn-default pick", exc=_ex)
        _default_rb.setChecked(True)

        group.addButton(rb_general, 0)
        group.addButton(rb_diabetic, 1)
        group.addButton(rb_border, 2)
        group.addButton(rb_infert, 3)

        picker_row.addWidget(rb_general)
        picker_row.addWidget(rb_diabetic)
        picker_row.addWidget(rb_border)
        picker_row.addWidget(rb_infert)
        picker_row.addStretch()
        v.addLayout(picker_row)

        # ── Editor ──────────────────────────────────────────────────────
        txt = QTextEdit()
        txt.setAcceptRichText(True)
        # Remember which diet is currently loaded + whether the user has
        # edited it. If they switch diet after editing, confirm first so
        # we don't silently discard their work.
        state: dict = {"current_key": None, "edited": False}

        def _key_for_index(idx: int) -> str:
            return ["genel", "diyabetik", "sinir", "infertilite"][idx]

        def _build_full_html(diet_key: str) -> str:
            """Wrap the stock diet plan with a patient-specific header."""
            plan = DIET_PLANS.get(diet_key, {})
            body = plan.get("html", "")
            patient_header = (
                f"<div style='text-align:right;color:#606060;"
                f"font-size:11px;font-style:italic;margin-bottom:8px;'>"
                f"<b>Hasta:</b> {pname} &nbsp;|&nbsp; "
                f"<b>Tarih:</b> {today}</div>"
            )
            return patient_header + body

        def _load_diet(idx: int):
            diet_key = _key_for_index(idx)
            # If the user has edited the current plan, confirm before discarding
            if state["edited"] and state["current_key"] is not None \
                    and state["current_key"] != diet_key:
                reply = QMessageBox.question(
                    dlg, "Değişiklikler Silinsin mi?",
                    "Mevcut diyet listesi üzerinde değişiklik yaptınız.\n\n"
                    "Başka bir diyete geçerseniz bu değişiklikler kaybolur.\n"
                    "Devam edilsin mi?",
                    QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply != QMessageBox.Yes:
                    # Revert the radio selection silently
                    group.blockSignals(True)
                    old_idx = ["genel", "diyabetik", "sinir"].index(
                        state["current_key"])
                    group.button(old_idx).setChecked(True)
                    group.blockSignals(False)
                    return
            # Load new diet
            txt.blockSignals(True)
            txt.setHtml(_build_full_html(diet_key))
            txt.blockSignals(False)
            state["current_key"] = diet_key
            state["edited"] = False

        def _on_text_changed():
            # Mark as edited only after the initial load
            if state["current_key"] is not None:
                state["edited"] = True

        txt.textChanged.connect(_on_text_changed)
        group.idClicked.connect(_load_diet)
        v.addWidget(txt, 1)

        # ── Buttons ─────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_reset = QPushButton("↺ Orijinale Dön")
        btn_reset.setToolTip("Seçili diyetin orijinal (düzenlenmemiş) "
                              "halini tekrar yükle.")
        btn_reset.setStyleSheet(
            "QPushButton{background:#F8F8F8;border:1px solid #C8C8C8;"
            "padding:8px 18px;font:500 12px 'Segoe UI';border-radius:3px;}"
            "QPushButton:hover{background:#E5EEF7;border-color:#0078D4;}")

        def _do_reset():
            if not state["edited"]:
                return
            reply = QMessageBox.question(
                dlg, "Sıfırla?",
                "Değişiklikleriniz silinecek. Emin misiniz?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.Yes:
                key = state["current_key"] or "genel"
                txt.blockSignals(True)
                txt.setHtml(_build_full_html(key))
                txt.blockSignals(False)
                state["edited"] = False

        btn_reset.clicked.connect(_do_reset)

        btn_print = QPushButton("🖨 Yazdır")
        btn_print.setStyleSheet(primary_button_style())

        def _do_print():
            # v68-UI: Use the central print_text_widget helper
            # for reliable printing across Windows drivers.
            ok, msg = print_text_widget(txt, parent_dialog=dlg,
                                        title="Yazdır")
            try:
                self.statusBar().showMessage(msg, 5000)
            except Exception as _ex:
                _log_warning("_do_print: status", exc=_ex)
            if not ok and "iptal" not in (msg or "").lower():
                QMessageBox.warning(dlg, "Yazdırma", msg)

        btn_print.clicked.connect(_do_print)

        btn_copy = QPushButton("📋 Panoya Kopyala")
        btn_copy.setStyleSheet(secondary_button_style())

        def _do_copy():
            # toPlainText() strips HTML — good for WhatsApp / SMS paste
            safe_copy_to_clipboard(txt.toPlainText())
            self.statusBar().showMessage(
                "✓ Diyet listesi panoya kopyalandı", 4000)

        btn_copy.clicked.connect(_do_copy)

        btn_close = QPushButton("Kapat")
        btn_close.setShortcut("Escape")
        btn_close.clicked.connect(dlg.accept)

        btn_row.addWidget(btn_reset)
        btn_row.addWidget(btn_print)
        btn_row.addWidget(btn_copy)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        v.addLayout(btn_row)

        # Load the default diet matching the auto-selected radio button.
        # For gynecologic patients we default to the infertilite plan;
        # otherwise the standard gebelik (genel) plan.
        _default_idx = group.id(_default_rb)
        _load_diet(_default_idx)

        dlg.exec()
