"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _DemoFlagsMixin
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

class _DemoFlagsMixin:
    """MainWindow methods related to DemoFlags. Mixed into MainWindow via MRO."""

    def _show_stats_flags(self):
        """Distribution of active clinical flags across the patient population."""
        if not db_has_any_patients():
            reply = QMessageBox.question(
                self, "Bayrak Dağılımı",
                "<b>Bayrak dağılımı için önce NAS senkronize edilmeli.</b>"
                "<p>Şimdi başlatılsın mı?</p>",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self._run_nas_sync()
            return
        with db_conn() as con:
            total_patients = con.execute(
                "SELECT COUNT(*) FROM patients").fetchone()[0]
            rows = con.execute(
                "SELECT flag_name, COUNT(DISTINCT patient_key) "
                "FROM patient_flags WHERE value='1' GROUP BY flag_name "
                "ORDER BY COUNT(DISTINCT patient_key) DESC"
            ).fetchall()

        if not rows:
            QMessageBox.information(
                self, "Bayrak Dağılımı",
                "Hiçbir hastada aktif bayrak yok.")
            return

        max_cnt = max(r[1] for r in rows)
        parts = [f"<h3>🏷️ Bayrak Dağılımı</h3>"
                 f"<p>Toplam <b>{total_patients:,}</b> hasta içinde:</p>"]
        parts.append("<table cellpadding='4' cellspacing='0' style='border-collapse:collapse;font:12px Segoe UI;'>")
        parts.append(
            "<tr style='background:#E5EEF7;'>"
            "<th align='left'>Bayrak</th><th>Sayı</th><th>%</th>"
            "<th align='left'>Grafik</th></tr>")
        for fname, cnt in rows:
            label = PATIENT_FLAG_LABELS.get(fname, fname)
            level = PATIENT_FLAG_LEVELS.get(fname, "info")
            colour = {"danger": "#C42B1C", "warning": "#C46500",
                      "info": "#005A9E", "good": "#107C10"
                      }.get(level, "#0078D4")
            pct = (cnt / total_patients * 100) if total_patients else 0
            width = int(cnt / max_cnt * 100) if max_cnt else 0
            bar = (f"<div style='background:{colour};height:14px;"
                   f"width:{max(width, 1)}%;'></div>")
            parts.append(
                f"<tr><td><b>{label}</b></td><td>{cnt}</td>"
                f"<td>{pct:.1f}%</td>"
                f"<td style='min-width:250px;'>{bar}</td></tr>")
        parts.append("</table>")
        html = "".join(parts)

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("Bayrak Dağılımı")
        dlg.resize(680, 500)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(12, 12, 12, 12)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setHtml(html)
        v.addWidget(txt, 1)
        btn = QPushButton("Kapat")
        btn.clicked.connect(dlg.accept)
        v.addWidget(btn)
        dlg.exec()

    def _show_demographics_dialog(self):
        """Edit patient demographics: blood type, Rh, obstetric history.

        This fills the gap that the Voluson PDFs don't cover — blood
        group, obstetric history (G/P/A/L), chronic conditions, allergies.
        All saved to patient_demographics table.
        """
        if not self.current_patient:
            QMessageBox.warning(self, "Hasta Yok",
                                "Önce bir hasta seçin.")
            return

        from PySide6.QtWidgets import QSpinBox, QComboBox
        pkey = self.active_patient_key()
        current = load_patient_demographics(pkey)

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle(f"Hasta Bilgileri — {format_patient_name(pkey)}")
        dlg.resize(520, 640)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)

        # Title — premium hero card
        title = QLabel(
            f"<div style='padding:14px 18px;'>"
            f"<div style='font-size:18px;font-weight:800;color:#FFFFFF;'>"
            f"👤  {format_patient_name(pkey)}</div>"
            f"<div style='color:rgba(255,255,255,0.85);margin:4px 0 0 0;"
            f"font-size:11.5px;'>"
            f"Kan grubu, obstetrik öykü ve klinik bilgiler</div>"
            f"</div>")
        title.setTextFormat(Qt.RichText)
        title.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #003F6F, stop:0.5 #005A9E, stop:1 #0078D4);"
            "border-radius:10px;color:#FFFFFF;}")
        # Drop shadow
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            tsh = QGraphicsDropShadowEffect()
            tsh.setBlurRadius(15)
            tsh.setColor(QColor(0, 90, 158, 90))
            tsh.setOffset(0, 3)
            title.setGraphicsEffect(tsh)
        except Exception as _ex:
            _log_warning("demographics title shadow", exc=_ex)
        lay.addWidget(title)

        # ── Patient status summary (READ-ONLY, from flags) ─────────────
        # Show active flag details so the doctor can see what was previously
        # recorded (e.g. Clexane dose, Rh incompatibility note, habituel
        # abortus count) without having to go back to the flag panel.
        try:
            active_flags = get_patient_flags(pkey) or {}
            flag_lines = []
            if active_flags.get("kan_uyusmazligi", {}).get("value") == "1":
                flag_lines.append(
                    "🩸 <b>Kan uyuşmazlığı</b> — Anti-D profilaksisi 28-32 hf")
            if active_flags.get("clexane", {}).get("value") == "1":
                dose = active_flags.get("clexane", {}).get("notes", "").strip()
                line = "💉 <b>Clexane kullanıyor</b>"
                if dose:
                    line += f" — <span style='color:#C42B1C'>{dose}</span>"
                flag_lines.append(line)
            if active_flags.get("ecopirin", {}).get("value") == "1":
                flag_lines.append(
                    "💊 <b>Ecopirin kullanıyor</b> — 100 mg/gün (aspirin)")
            if active_flags.get("riskli_gebelik", {}).get("value") == "1":
                det = active_flags.get("riskli_gebelik", {}).get("notes", "").strip()
                line = "⚠️ <b>Riskli gebelik</b>"
                if det:
                    line += f" — {det}"
                flag_lines.append(line)
            if active_flags.get("habituel_abortus", {}).get("value") == "1":
                det = active_flags.get("habituel_abortus", {}).get("notes", "").strip()
                line = "🔄 <b>Habituel abortus</b>"
                if det:
                    line += f" — {det}"
                flag_lines.append(line)
            if active_flags.get("kotu_obstetrik", {}).get("value") == "1":
                det = active_flags.get("kotu_obstetrik", {}).get("notes", "").strip()
                line = "📋 <b>Kötü obstetrik öykü</b>"
                if det:
                    line += f" — {det}"
                flag_lines.append(line)
            if active_flags.get("akraba_evliligi", {}).get("value") == "1":
                det = active_flags.get("akraba_evliligi", {}).get("notes", "").strip()
                line = "👨‍👩 <b>Akraba evliliği</b>"
                if det:
                    line += f" — {det}"
                flag_lines.append(line)
            if active_flags.get("onceki_sezaryan", {}).get("value") == "1":
                flag_lines.append("🏥 <b>Önceki sezaryan</b> mevcut")
            if active_flags.get("ilk_gebelik", {}).get("value") == "1":
                flag_lines.append("👶 <b>İlk gebelik</b> (primigravida)")
            if active_flags.get("nipt", {}).get("value") == "1":
                flag_lines.append("🧬 <b>NIPT</b> testi yapıldı")

            if flag_lines:
                status_box = QFrame()
                status_box.setStyleSheet(
                    "QFrame{background:#FFFBEA;border:1px solid #E8B800;"
                    "border-radius:4px;}")
                sv = QVBoxLayout(status_box)
                sv.setContentsMargins(10, 6, 10, 6)
                sv.setSpacing(2)
                hdr = QLabel("<b>📌 Aktif Klinik Durum</b>")
                hdr.setStyleSheet("color:#7A5A00;font:700 11px 'Segoe UI';"
                                  "background:transparent;border:none;")
                sv.addWidget(hdr)
                for line in flag_lines:
                    l = QLabel(line)
                    l.setTextFormat(Qt.RichText)
                    l.setWordWrap(True)
                    l.setStyleSheet(
                        "color:#333333;font:500 11px 'Segoe UI';"
                        "background:transparent;border:none;"
                        "padding:1px 0;")
                    sv.addWidget(l)
                lay.addWidget(status_box)
        except Exception as _ex:
            _log_warning("MainWindow._show_demographics_dialog", exc=_ex)

        # ── Blood group ────────────────────────────────────────────────
        bg_box = QFrame()
        bg_box.setObjectName("InnerBox")
        bg_box.setStyleSheet(
            "QFrame#InnerBox{background:#FFF0F0;border:1px solid #E8B8B8;"
            "border-radius:4px;}")
        bg_lay = QGridLayout(bg_box)
        bg_lay.setContentsMargins(10, 8, 10, 8)
        bg_lay.addWidget(QLabel("<b>🩸 Kan Grubu ve Rh</b>"), 0, 0, 1, 4)

        bg_lay.addWidget(QLabel("Kan grubu:"), 1, 0)
        bt_combo = QComboBox()
        bt_combo.addItems(["", "A", "B", "AB", "O"])
        bt_combo.setCurrentText(current.get("blood_type") or "")
        bg_lay.addWidget(bt_combo, 1, 1)

        bg_lay.addWidget(QLabel("Rh:"), 1, 2)
        rh_combo = QComboBox()
        # Use (display_text, internal_value) tuples via addItem + userData.
        # This lets us show nice Turkish labels but store canonical "positive"
        # / "negative" values in the DB — matches the convention used by
        # _update_clinical_banner and get_ga_recommendations.
        rh_items = [("", ""), ("+ (Pozitif)", "positive"), ("− (Negatif)", "negative")]
        for display, value in rh_items:
            rh_combo.addItem(display, value)
        # Pre-select based on current value
        cur_rh = current.get("rh_factor") or ""
        for i in range(rh_combo.count()):
            if rh_combo.itemData(i) == cur_rh:
                rh_combo.setCurrentIndex(i)
                break
        bg_lay.addWidget(rh_combo, 1, 3)

        bg_lay.addWidget(QLabel("Partner Rh:"), 2, 0)
        prh_combo = QComboBox()
        prh_items = [
            ("", ""),
            ("+ (Pozitif)", "positive"),
            ("− (Negatif)", "negative"),
            ("Bilinmiyor", "unknown"),
        ]
        for display, value in prh_items:
            prh_combo.addItem(display, value)
        cur_prh = current.get("partner_rh") or ""
        for i in range(prh_combo.count()):
            if prh_combo.itemData(i) == cur_prh:
                prh_combo.setCurrentIndex(i)
                break
        bg_lay.addWidget(prh_combo, 2, 1)

        rh_warning = QLabel("")
        rh_warning.setStyleSheet(error_text_style(font_size=10))
        bg_lay.addWidget(rh_warning, 3, 0, 1, 4)

        def _update_rh_warning():
            # Use itemData (canonical value) not currentText (localized display)
            m = rh_combo.currentData() or ""
            p = prh_combo.currentData() or ""
            if m == "negative" and p == "positive":
                rh_warning.setText(
                    "⚠ Rh uyuşmazlığı riski var — 28-32 hf Anti-D profilaksisi gerekli")
            elif m == "negative" and p == "unknown":
                rh_warning.setText(
                    "⚠ Partner Rh bilinmiyor — Rh uyuşmazlığı ihtimali")
            else:
                rh_warning.setText("")
        rh_combo.currentIndexChanged.connect(_update_rh_warning)
        prh_combo.currentIndexChanged.connect(_update_rh_warning)
        _update_rh_warning()

        lay.addWidget(bg_box)

        # ── Obstetric history (G/P/A/L) ────────────────────────────────
        gpal_box = QFrame()
        gpal_box.setObjectName("InnerBox")
        gpal_box.setStyleSheet(
            "QFrame#InnerBox{background:#F0F8FF;border:1px solid #B8D8E8;"
            "border-radius:4px;}")
        gpal_lay = QGridLayout(gpal_box)
        gpal_lay.setContentsMargins(10, 8, 10, 8)
        gpal_lay.addWidget(QLabel("<b>👶 Obstetrik Öykü (G P A L)</b>"), 0, 0, 1, 8)

        fields = []
        labels_help = [
            ("Gravida", "gravida", "Toplam gebelik sayısı (bu dahil)"),
            ("Para", "para", "Canlı doğum sayısı"),
            ("Abortus", "abortus", "Düşük sayısı"),
            ("Living", "living", "Yaşayan çocuk sayısı"),
        ]
        for col, (lbl, key, tip) in enumerate(labels_help):
            gpal_lay.addWidget(QLabel(f"{lbl[0]}:"), 1, col * 2)
            sp = QSpinBox()
            sp.setRange(0, 20)
            sp.setMinimumWidth(60)
            sp.setToolTip(tip)
            val = current.get(key)
            if val is not None:
                sp.setValue(val)
            gpal_lay.addWidget(sp, 1, col * 2 + 1)
            fields.append((key, sp))

        gpal_hint = QLabel(
            "<i style='color:#606060;font-size:10px;'>"
            "Örnek: G3P1A1L1 — 3. gebelik, 1 canlı doğum, 1 düşük, 1 yaşayan çocuk"
            "</i>")
        gpal_hint.setTextFormat(Qt.RichText)
        gpal_lay.addWidget(gpal_hint, 2, 0, 1, 8)
        lay.addWidget(gpal_box)

        # ── LMP override ───────────────────────────────────────────────
        # Auto-suggest LMP from the earliest PDF if user hasn't set one.
        auto_lmp = None
        try:
            auto_lmp = get_best_lmp_for_patient(self.current_patient)
        except Exception as _ex:
            _log_warning("MainWindow._show_demographics_dialog", exc=_ex)
        lmp_box = QFrame()
        lmp_box.setObjectName("InnerBox")
        lmp_box.setStyleSheet(
            "QFrame#InnerBox{background:#F8F8F8;border:1px solid #C8C8C8;"
            "border-radius:4px;}")
        lmp_v = QVBoxLayout(lmp_box)
        lmp_v.setContentsMargins(10, 8, 10, 8)
        lmp_v.setSpacing(4)

        lmp_row = QHBoxLayout()
        lmp_row.addWidget(QLabel("<b>📅 Son Adet Tarihi (LMP):</b>"))
        lmp_in = QLineEdit()
        lmp_in.setPlaceholderText("GG.AA.YYYY")
        lmp_in.setMaximumWidth(150)
        # Pre-fill: user override takes priority, else auto-computed from PDF
        lmp_in.setText(current.get("lmp_override") or auto_lmp or "")
        lmp_row.addWidget(lmp_in)

        if auto_lmp and not current.get("lmp_override"):
            auto_btn = QPushButton(f"📄 PDF'den al: {auto_lmp}")
            auto_btn.setStyleSheet(
                "QPushButton{background:#E5F1FB;color:#005A9E;border:1px solid #A0C8E8;"
                "padding:4px 10px;border-radius:3px;font:500 11px 'Segoe UI';}"
                "QPushButton:hover{background:#D0E5F5;}")
            auto_btn.setToolTip("İlk USG'deki GA'ya göre geri hesaplandı")
            auto_btn.clicked.connect(lambda: lmp_in.setText(auto_lmp))
            lmp_row.addWidget(auto_btn)
        lmp_row.addStretch()
        lmp_v.addLayout(lmp_row)

        if auto_lmp:
            lmp_hint = QLabel(
                f"<i style='color:#606060;font-size:10px;'>"
                f"USG tarihinden geri hesap: <b>{auto_lmp}</b>. "
                f"Hasta net biliyorsa üstüne yazarak düzeltebilirsiniz.</i>")
            lmp_hint.setTextFormat(Qt.RichText)
            lmp_v.addWidget(lmp_hint)
        lay.addWidget(lmp_box)

        # ── Active clinical flags (read-only notes from flag panel) ────
        # Mirror the flags that were set on the summary tab so the doctor
        # has a full picture here without having to flip back.
        # Reuse `active_flags` fetched earlier in this method — avoid a
        # second DB round-trip (dialog is modal, flags can't change
        # between then and now).
        flags = active_flags or {}
        active_flag_notes = []
        for fkey, data in (flags or {}).items():
            if data.get("value") != "1":
                continue
            label = PATIENT_FLAG_LABELS.get(fkey, fkey)
            note = (data.get("notes") or "").strip()
            if note:
                active_flag_notes.append(f"<b>• {label}:</b> {note}")
            else:
                active_flag_notes.append(f"<b>• {label}</b>")
        if active_flag_notes:
            flags_box = QFrame()
            flags_box.setStyleSheet(
                "QFrame{background:#FFF0F0;border:1px solid #E8B8B8;"
                "border-radius:4px;}")
            flags_v = QVBoxLayout(flags_box)
            flags_v.setContentsMargins(10, 8, 10, 8)
            flags_v.addWidget(QLabel("<b>🏷️ Aktif Bayraklar</b>"))
            flags_lbl = QLabel("<br>".join(active_flag_notes))
            flags_lbl.setTextFormat(Qt.RichText)
            flags_lbl.setWordWrap(True)
            flags_lbl.setStyleSheet(
                "color:#303030;font:500 11px 'Segoe UI';background:transparent;"
                "border:none;")
            flags_v.addWidget(flags_lbl)
            lay.addWidget(flags_box)

        # ── Chronic conditions / medications / allergies ───────────────
        from PySide6.QtWidgets import QTextEdit as _QTE

        cc_lbl = QLabel("<b>🏥 Kronik Hastalıklar:</b>")
        lay.addWidget(cc_lbl)
        cc_edit = _QTE()
        cc_edit.setMaximumHeight(55)
        cc_edit.setPlaceholderText(
            "DM, HT, tiroid, astım, epilepsi vb.")
        cc_edit.setPlainText(current.get("chronic_conditions") or "")
        lay.addWidget(cc_edit)

        med_lbl = QLabel("<b>💊 İlaçlar:</b>")
        lay.addWidget(med_lbl)
        med_edit = _QTE()
        med_edit.setMaximumHeight(55)
        med_edit.setPlaceholderText(
            "Örn: Clexane 4000 IU/gün, Folbiol, Aspirin 100mg")
        # Pre-fill: merge existing text with auto-extracted flags so the doctor
        # doesn't have to re-type Clexane/Ecopirin
        existing_meds = (current.get("medications") or "").strip()
        auto_meds = []
        if flags.get("clexane", {}).get("value") == "1":
            dose = (flags.get("clexane", {}).get("notes") or "").strip()
            auto_meds.append(f"Clexane{' ' + dose if dose else ''}")
        if flags.get("ecopirin", {}).get("value") == "1":
            auto_meds.append("Ecopirin")
        # Only auto-insert if user hasn't already typed these
        existing_lower = existing_meds.lower()
        to_add = [m for m in auto_meds if m.split()[0].lower() not in existing_lower]
        if to_add:
            if existing_meds:
                med_edit.setPlainText(existing_meds + "\n" + "\n".join(to_add))
            else:
                med_edit.setPlainText("\n".join(to_add))
        else:
            med_edit.setPlainText(existing_meds)
        lay.addWidget(med_edit)

        alg_lbl = QLabel("<b>⚠️ Alerjiler:</b>")
        lay.addWidget(alg_lbl)
        alg_edit = _QTE()
        alg_edit.setMaximumHeight(55)
        alg_edit.setPlaceholderText("İlaç, gıda, lateks vb. alerjiler")
        alg_edit.setPlainText(current.get("allergies") or "")
        lay.addWidget(alg_edit)

        # ── Buttons ─────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        save_btn = QPushButton("💾 Kaydet")
        save_btn.setStyleSheet(
            "background:#107C10;color:white;padding:8px 22px;font:600 12px;"
            "border:none;border-radius:3px;")
        cancel_btn = QPushButton("İptal")
        cancel_btn.setShortcut("Escape")
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

        def _save():
            data = {
                "blood_type": bt_combo.currentText(),
                "rh_factor": rh_combo.currentData() or "",
                "partner_rh": prh_combo.currentData() or "",
                "lmp_override": lmp_in.text().strip(),
                "chronic_conditions": cc_edit.toPlainText().strip(),
                "medications": med_edit.toPlainText().strip(),
                "allergies": alg_edit.toPlainText().strip(),
            }
            for key, sp in fields:
                data[key] = sp.value() if sp.value() > 0 else None
            try:
                save_patient_demographics(pkey, data)
                # Refresh the clinical banner immediately — blood/GPAL shown there
                try:
                    self._update_clinical_banner()
                    self._update_ga_recommendations()
                except Exception as _ex:
                    _log_warning("MainWindow._save", exc=_ex)
                self.statusBar().showMessage("✓ Hasta bilgileri kaydedildi", 3000)
                dlg.accept()
            except Exception as ex:
                QMessageBox.critical(
                    self, "Kaydetme Hatası",
                    f"Hasta bilgileri kaydedilirken hata:\n\n{ex}")

        save_btn.clicked.connect(_save)
        cancel_btn.clicked.connect(dlg.reject)
        dlg.exec()

    def _on_flag_toggled(self, flag_name: str, checked: bool):
        """A bayrak checkbox was toggled — persist + refresh ribbon."""
        if self._suppress_flag_signals:
            return
        key = self.active_patient_key()
        if not key:
            # Roll back the toggle if no patient selected. v68: look in
            # BOTH the obstetric and the gynecologic checkbox sets.
            cb = self._flag_checkboxes.get(flag_name) \
                or getattr(self, "_gynec_flag_checkboxes", {}).get(flag_name)
            if cb is not None:
                self._suppress_flag_signals = True
                cb.setChecked(not checked)
                self._suppress_flag_signals = False
            self.statusBar().showMessage(
                "Önce bir hasta seçin", 2500)
            return
        try:
            if checked:
                # For flags that benefit from a free-text detail (akraba
                # evliliği derecesi, kötü obstetrik öykü sebebi) — pop up
                # a small input dialog right after toggling.
                detail_prompts = {
                    "akraba_evliligi":
                        ("Akraba evliliği detayı",
                         "Akraba evliliğinin derecesi / detayı:\n"
                         "(örn: 1. derece kuzen, amca kızı, dayı oğlu)"),
                    "kotu_obstetrik":
                        ("Kötü obstetrik öykü sebebi",
                         "Kötü obstetrik öykünün sebebi:\n"
                         "(örn: 2 düşük + 1 prematür doğum, intrauterin ölüm, vs.)"),
                    "habituel_abortus":
                        ("Habituel abortus detayı",
                         "Habituel abortus geçmişi:\n"
                         "(kaç düşük, hangi haftalarda, sebep biliniyor mu?)"),
                    "riskli_gebelik":
                        ("Riskli gebelik sebebi",
                         "Riskli gebelik sebebi:\n"
                         "(örn: gestasyonel diyabet, preeklampsi öyküsü, ileri yaş)"),
                    "clexane":
                        ("Clexane dozu",
                         "Clexane dozu:\n"
                         "(4000 IU / 6000 IU / diğer — dozu ve sıklığı yazın)"),
                    "onceki_sezaryan":
                        ("Önceki sezaryan sayısı ve detayı",
                         "Kaç önceki sezaryen var?\n"
                         "Örn: '1. sezaryen, 2021, makat prezentasyon'\n"
                         "     '2 sezaryen: 2018 (CPD), 2021 (elektif)'\n\n"
                         "3+ ise üstteki 'sezaryen_coklu' bayrağını da işaretleyin."),
                    "sezaryen_coklu":
                        ("3+ önceki sezaryen — detay",
                         "Toplam sezaryen sayısı ve tarihler:\n"
                         "(örn: '3 sezaryen: 2015, 2018, 2022 — hepsi "
                         "komplikasyonsuz')\n\n"
                         "YÜKSEK RİSK: plasenta akreata, uterus rüptürü"
                         " riski artar."),
                    "sezaryen_istek":
                        ("Sezaryen tercihi",
                         "Hasta sezaryen tercih ediyor — sebep / not:\n"
                         "(örn: 'önceki doğum travması', 'anksiyete', "
                         "'elektif tercih')"),
                    "tarama_red":
                        ("Tarama testi reddi detayı",
                         "Hangi tarama testi reddedildi?\n"
                         "(örn: '11-14 hafta double test reddi', "
                         "'NIPT teklif edildi, kabul etmedi',\n"
                         "'üçlü test, quadruple, amniyosentez dahil reddi')\n\n"
                         "Not: reddi yazılı olarak onaylatmak tavsiye edilir."),
                    "dogum_normal":
                        ("Normal doğum kaydı",
                         "Doğum bilgileri:\n"
                         "(örn: '12.03.2025, 39+2 hf, kız bebek 3250g, "
                         "Apgar 9/10, komplikasyonsuz')\n\n"
                         "Tarih + hafta + bebek cinsiyeti/ağırlığı/durumu."),
                    "dogum_sezaryan":
                        ("Sezaryen doğum kaydı",
                         "Sezaryen bilgileri:\n"
                         "(örn: '12.03.2025, 38+5 hf, elektif C/S, "
                         "erkek bebek 3450g, Apgar 9/10')\n\n"
                         "Tarih + hafta + endikasyon + bebek detayları."),
                    "dogum_postterm":
                        ("Postterm gebelik notu",
                         "42+ haftaya gelen ama henüz doğum yapmamış hasta:\n"
                         "(örn: 'NST normal, indüksiyon önerildi, kabul etmedi',\n"
                         " 'sevk edildi → ... hastanesi', 'iletişim kayboldu')\n\n"
                         "Doğum gerçekleştiğinde 'dogum_normal' veya "
                         "'dogum_sezaryan' bayrağına geçirin."),
                }
                notes = ""
                if flag_name in detail_prompts:
                    title, prompt = detail_prompts[flag_name]
                    text, ok = QInputDialog.getMultiLineText(
                        self, title, prompt, "")
                    if ok and text.strip():
                        notes = text.strip()
                set_patient_flag(key, flag_name, "1", notes)
            else:
                delete_patient_flag(key, flag_name)
        except Exception as e:
            _log_warning(f"flag toggle save failed ({flag_name}): {e}")
        # Refresh both the ribbon AND the checkbox labels (so newly saved
        # notes appear inline next to the checkbox text)
        self._update_flag_ribbon()
        try:
            self._load_patient_flags_into_ui()
        except Exception as _ex:
            _log_warning("MainWindow._on_flag_toggled", exc=_ex)
        # v68: Look up label in BOTH flag sets — jinekolojik bayraklar
        # GYNEC_FLAG_LABELS'ta yer alır.
        label = PATIENT_FLAG_LABELS.get(flag_name) \
            or GYNEC_FLAG_LABELS.get(flag_name, flag_name)
        if checked:
            self.statusBar().showMessage(f"✓ Bayrak işaretlendi: {label}", 2500)
        else:
            self.statusBar().showMessage(f"✓ Bayrak kaldırıldı: {label}", 2500)

    def _load_patient_flags_into_ui(self):
        """Sync the checkbox states from DB for the current patient.
        Also surfaces stored notes as tooltips + inline badges so the
        doctor can see what dose/detail was saved earlier.

        v68: Loads BOTH the obstetric (PATIENT_FLAGS) and the new
        gynecologic (GYNEC_FLAGS) checkbox sets. The two sets coexist
        — the editor dialog shows whichever matches the current mode,
        and the ribbon merges them so any flag the patient has is
        always surfaced.
        """
        key = self.active_patient_key()
        flags = get_patient_flags(key) if key else {}
        self._suppress_flag_signals = True
        try:
            # Obstetric / pregnancy flags
            if hasattr(self, "_flag_checkboxes"):
                for fname, cb in self._flag_checkboxes.items():
                    fdata = flags.get(fname, {})
                    is_on = fdata.get("value") == "1"
                    cb.setChecked(is_on)
                    notes = (fdata.get("notes") or "").strip()
                    base_label = PATIENT_FLAG_LABELS.get(fname, fname)
                    if is_on and notes:
                        cb.setText(f"{base_label}  ·  {notes}")
                        cb.setToolTip(
                            f"{base_label}\n\nKayıtlı bilgi: {notes}\n\n"
                            f"(Detayı değiştirmek için kaldırıp tekrar "
                            f"işaretleyin)")
                    else:
                        cb.setText(base_label)
                        cb.setToolTip(base_label)
            # v68: Gynecologic / infertility flags
            if hasattr(self, "_gynec_flag_checkboxes"):
                for fname, cb in self._gynec_flag_checkboxes.items():
                    fdata = flags.get(fname, {})
                    is_on = fdata.get("value") == "1"
                    cb.setChecked(is_on)
                    notes = (fdata.get("notes") or "").strip()
                    base_label = GYNEC_FLAG_LABELS.get(fname, fname)
                    if is_on and notes:
                        cb.setText(f"{base_label}  ·  {notes}")
                        cb.setToolTip(
                            f"{base_label}\n\nKayıtlı bilgi: {notes}\n\n"
                            f"(Detayı değiştirmek için kaldırıp tekrar "
                            f"işaretleyin)")
                    else:
                        cb.setText(base_label)
                        cb.setToolTip(base_label)
        finally:
            self._suppress_flag_signals = False
        self._update_flag_ribbon()
        # Keep the compact chip bar in sync with the new flag state
        try:
            self._refresh_flag_chips()
        except Exception as _ex:
            _log_warning("_refresh_flag_chips", exc=_ex)

    def _refresh_flag_chips(self):
        """No-op retained for backward compatibility.

        Previously this method populated a chip bar in the summary tab
        showing the patient's active flags. That bar duplicated the
        information already shown in the red "DİKKAT" ribbon at the
        top of the tab, so it was removed per user feedback.

        The method is kept as a no-op so that existing call sites
        (in _load_patient_flags_into_ui, and in _open_flag_editor_dialog)
        keep working without conditionals. If flag-display UI is ever
        re-introduced, wire it up here.
        """
        return

    def _refresh_flags_for_mode(self):
        """Re-render the flag ribbon for the current mode. The ribbon
        itself merges PATIENT_FLAGS + GYNEC_FLAGS so it just needs a
        repaint when the mode flips. Bayrak editor dialog'u açıkken
        zaten doğru set'i seçer."""
        try:
            self._update_flag_ribbon()
        except Exception as _ex:
            _log_warning("_refresh_flags_for_mode: ribbon", exc=_ex)
        # Re-load checkbox states (cheap — DB read)
        try:
            if hasattr(self, "_load_patient_flags_into_ui"):
                self._load_patient_flags_into_ui()
        except Exception as _ex:
            _log_warning("_refresh_flags_for_mode: load", exc=_ex)
        # v68: Also refresh the compact chip bar in case any flags
        # changed in the editor (also cheap).
        try:
            if hasattr(self, "_refresh_flag_chips"):
                self._refresh_flag_chips()
        except Exception as _ex:
            _log_warning("_refresh_flags_for_mode: chips", exc=_ex)

    def _open_flag_editor_dialog(self):
        """Open a popup with the full flag checkbox list so the doctor
        can toggle multiple flags at once. Changes are applied live
        (each toggle calls _on_flag_toggled → persists to DB), so the
        dialog has no "save" button — just "Kapat".

        v68: Mode-aware — shows PATIENT_FLAGS (gebelik bayrakları) in
        obstetric mode and GYNEC_FLAGS (infertilite/jinekoloji) in
        gynecology mode. The per-mode set is kept in separate checkbox
        dicts (_flag_checkboxes vs _gynec_flag_checkboxes).
        """
        # Pick which flag set to show based on mode
        is_gyn = False
        try:
            override = getattr(self, "_mode_override", None)
            if override == "gynecologic":
                is_gyn = True
            elif override == "obstetric":
                is_gyn = False
            elif self.current_patient is not None:
                is_gyn = is_gynecologic_patient(self.current_patient)
        except Exception as _ex:
            _log_warning("_open_flag_editor_dialog: mode detect", exc=_ex)

        if is_gyn:
            active_cbs = self._gynec_flag_checkboxes
            active_flags = GYNEC_FLAGS
            title_text = "🌸  Jinekolojik / İnfertilite Bayrakları"
        else:
            active_cbs = self._flag_checkboxes
            active_flags = PATIENT_FLAGS
            title_text = "🏷️  Hasta Bayrakları (Gebelik)"

        if not active_cbs:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(title_text)
        dlg.setMinimumWidth(600)
        dlg.resize(640, 500)

        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(8)

        # v68: Hero header (mode-aware color)
        if is_gyn:
            # Pink gradient for gynecology
            grad_stops = "stop:0 #6F2256, stop:0.5 #8B2A6D, stop:1 #B5368A"
            shadow_color = (139, 42, 109, 90)
        else:
            # Blue gradient for obstetric
            grad_stops = "stop:0 #003F6F, stop:0.5 #005A9E, stop:1 #0078D4"
            shadow_color = (0, 90, 158, 90)
        hero = QLabel(
            f"<div style='padding:14px 18px;'>"
            f"<div style='font-size:18px;font-weight:800;color:#FFFFFF;'>"
            f"{title_text}</div>"
            f"<div style='color:rgba(255,255,255,0.85);margin-top:4px;"
            f"font-size:11.5px;'>"
            f"Bayrakları işaretleyin — değişiklikler otomatik "
            f"kaydedilir, özet şeridi güncellenir."
            f"</div></div>")
        hero.setTextFormat(Qt.RichText)
        hero.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            f"{grad_stops});"
            "border-radius:10px;color:#FFFFFF;}")
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            shf = QGraphicsDropShadowEffect()
            shf.setBlurRadius(15)
            shf.setColor(QColor(*shadow_color))
            shf.setOffset(0, 3)
            hero.setGraphicsEffect(shf)
        except Exception as _ex:
            _log_warning("flag editor hero shadow", exc=_ex)
        lay.addWidget(hero)

        # Re-parent checkboxes into this dialog's grid. Because Qt
        # widgets have one parent at a time, adding to a new layout
        # detaches them from the hidden host. We restore them on close.
        grid_host = QFrame()
        grid = QGridLayout(grid_host)
        grid.setSpacing(6)
        grid.setContentsMargins(0, 6, 0, 6)

        severity_rank = {"danger": 0, "warning": 1, "good": 2, "info": 3}
        sorted_flags = sorted(
            enumerate(active_flags),
            key=lambda x: (severity_rank.get(x[1][2], 99), x[0]))

        for idx, (_orig_idx, (key, label, level)) in enumerate(sorted_flags):
            cb = active_cbs.get(key)
            if cb is None:
                continue
            # Style the checkbox (may have been hidden without style)
            colour = {"danger": "#C42B1C", "warning": "#C46500",
                      "info": "#005A9E", "good": "#107C10"}.get(level, "#0078D4")
            bg_tint = {"danger": "#FFF0F0", "warning": "#FFF8EC",
                       "info": "transparent", "good": "#F0FAF0"
                       }.get(level, "transparent")
            cb.setStyleSheet(
                f"QCheckBox{{color:{colour};font:600 12px 'Segoe UI';"
                f"background:{bg_tint};padding:4px 8px;border-radius:3px;}}"
                f"QCheckBox:hover{{background:#E5EEF7;}}"
                f"QCheckBox:checked{{font-weight:700;}}")
            cb.setCursor(Qt.PointingHandCursor)
            level_tr = {"danger": "Yüksek risk", "warning": "Orta risk",
                        "info": "Bilgi",
                        "good": "Olumlu / Güvenli"}.get(level, "Bayrak")
            cb.setToolTip(f"{label} — {level_tr}")
            grid.addWidget(cb, idx // 2, idx % 2)

        lay.addWidget(grid_host)
        lay.addStretch()

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Kapat")
        btn_close.setDefault(True)
        btn_close.setStyleSheet(
            "QPushButton{background:#0078D4;color:white;padding:7px 22px;"
            "font:600 11px 'Segoe UI';border:none;border-radius:3px;}"
            "QPushButton:hover{background:#106EBE;}")
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_close)
        lay.addLayout(btn_row)

        # Show
        dlg.exec()

        # Re-home the checkboxes back into the right hidden host —
        # otherwise Qt GCs them when the dialog goes out of scope and
        # next open crashes. v68: pick the host that matches the
        # mode-aware checkbox set we just used.
        if is_gyn:
            host = getattr(self, "_gynec_flag_hidden_host", None)
        else:
            host = getattr(self, "_flag_hidden_host", None)
        if host is not None:
            hidden_layout = host.layout()
            if hidden_layout is not None:
                for idx, (_orig_idx, (key, label, level)) in enumerate(
                        sorted_flags):
                    cb = active_cbs.get(key)
                    if cb is not None:
                        hidden_layout.addWidget(cb, idx // 3, idx % 3)

        # Refresh the compact chip bar to reflect any changes made in
        # the dialog.
        self._refresh_flag_chips()
        try:
            self._update_flag_ribbon()
        except Exception as _ex:
            _log_warning("_open_flag_editor_dialog: ribbon", exc=_ex)

    def _on_compact_phone_changed(self):
        """Bayraklar sekmesindeki kompakt telefon kutusu — focus-out
        veya Enter'da kaydeder. Tüm phone widget'larını sync eder.

        v68 mantığı:
          • Yazılan numara varsayılanla AYNI ise → DB'den sil
            (hasta "özel numara yok" durumuna döner)
          • Varsayılandan FARKLI ise → DB'ye kaydet (özel numara)
          • Her iki durumda da tüm widget'lar güncellenir
        """
        if not hasattr(self, "phone_input_compact"):
            return
        raw = self.phone_input_compact.text().strip()
        number = normalize_phone(raw) if raw else get_default_whatsapp_number()
        default = get_default_whatsapp_number()
        is_custom = (number and number != default)

        # Sync her widget'a (signals kapalıyken)
        for attr in ("phone_input_compact", "phone_input",
                      "phone_input_summary"):
            w = getattr(self, attr, None)
            if w is None:
                continue
            try:
                w.blockSignals(True)
                w.setText(number)
                w.blockSignals(False)
            except RuntimeError as _ex:
                _log_warning(f"compact phone mirror {attr}: {_ex}")

        # Stat card
        try:
            self.stat_wa.set_value(number)
        except Exception as _ex:
            _log_warning(f"compact phone stat: {_ex}")

        # Patient info panel
        if hasattr(self, "pi_phone_lbl"):
            self.pi_phone_lbl.setText(number)

        # DB: özel ise kaydet, varsayılanla aynıysa sil
        key = self.active_patient_key()
        if key:
            try:
                if is_custom:
                    save_phone_db(key, number)
                    self.statusBar().showMessage(
                        f"✓ Özel WhatsApp kaydedildi: {number}", 3000)
                else:
                    # Varsayılanla aynı → özel kaydı kaldır
                    with db_conn() as con:
                        con.execute(
                            "DELETE FROM patient_phones "
                            "WHERE patient_key=?", (key,))
                        con.commit()
                    self.statusBar().showMessage(
                        "WhatsApp: varsayılan numara (özel kayıt silindi)",
                        3000)
                self.update_phone_badges(is_saved=is_custom)
            except Exception as _ex:
                _log_warning("_on_compact_phone_changed: save", exc=_ex)

    def _compute_signature_warning(self, key: str, flags: dict
                                    ) -> Optional[dict]:
        """v68-AI: Return a warning dict if this active pregnancy has
        no signature on file, else None.

        Suppressed for:
          • patients without any visits (nothing to sign yet)
          • patients whose pregnancy has closed (already delivered)
          • gynecologic patients (no pregnancy → no signature needed)
          • postterm/abortion outcome flagged

        Returns: {"label": "...", "notes": "..."} or None
        """
        if not key:
            return None
        try:
            # Skip if pregnancy already closed (delivered/postterm)
            if is_pregnancy_closed(flags):
                return None
            # Skip if delivered (recorded in deliveries table)
            try:
                if is_delivered(key):
                    return None
            except Exception as _ex:
                _log_warning(f"sig warn is_delivered: {_ex}")
            # Skip for gynecologic patients
            try:
                if is_gynecologic_patient(self.current_patient):
                    return None
            except Exception as _ex:
                _log_warning(f"sig warn gyn check: {_ex}")
            # Skip if no visits / no PDF
            visits = self.subfolder_paths or []
            if not visits:
                return None
            # Check if signature already on file
            sig = get_latest_signature_event(key)
            if sig:
                return None  # already signed
            # Must be active pregnancy — check GA from latest PDF
            pdf = get_latest_pdf_in_folder(visits[0])
            if not pdf:
                return None
            data = parse_pdf_summary_data(pdf)
            ga_days = data.get("ga_days")
            if not isinstance(ga_days, (int, float)) or ga_days <= 0:
                return None
            # Active pregnancy + no signature → warn
            ga_w = int(ga_days) // 7
            return {
                "label": "✍ İMZA TAKİBİ YOK",
                "notes": f"Hasta {ga_w} haftada — gebelik takibi "
                          f"için imza alınması gerekiyor. "
                          f"Toolbar'dan 'İmza Alındı' butonuna basın.",
            }
        except Exception as ex:
            _log_warning(f"_compute_signature_warning: {ex}")
            return None

    def _render_flag_ribbon(self, bad_flags, good_flags, info_flags,
                              rhogam_alert):
        """v68-AI: Helper to render the flag ribbon when only synthetic
        warnings exist (no real flags). Rebuilds the bar with given
        flag lists. Currently used for the standalone signature
        warning case.
        """
        if not hasattr(self, "flag_ribbon"):
            return
        # Just delegate to the regular render path by setting flags
        # then calling the bar display logic. Simplest implementation:
        # build a small HTML and show.
        if not bad_flags:
            self.flag_ribbon.hide()
            self.flag_ribbon_container.hide()
            return
        # Pick warning bar style
        bg, fg, border = "#C46500", "#FFFFFF", "#8C4A00"
        bits = []
        for label, d, _level in bad_flags:
            notes = (d.get("notes") or "").strip()
            if notes:
                bits.append(f"<b>{label}</b> · {notes}")
            else:
                bits.append(f"<b>{label}</b>")
        html = (f"<div style='background:{bg};color:{fg};padding:8px 14px;"
                f"border-left:4px solid {border};border-radius:4px;"
                f"font:600 12px Segoe UI;'>"
                f"DİKKAT: " + "  ·  ".join(bits) + "</div>")
        self.flag_ribbon.setText(html)
        self.flag_ribbon.show()
        self.flag_ribbon_container.show()
        if hasattr(self, "flag_ribbon_good"):
            self.flag_ribbon_good.hide()

    def _update_flag_ribbon(self):
        """Show / hide the flag ribbons at the top of the summary tab.

        v68: Two side-by-side ribbons:
          LEFT  — danger (🔴 kırmızı) + warning (🟠 turuncu) + info (🔵 mavi)
          RIGHT — good (🟢 yeşil)

        Each ribbon hides itself when its list is empty. When only
        the good ribbon has content, the left ribbon is hidden so
        the doctor only sees green. When only bad flags exist, only
        the red/orange left ribbon is shown.
        """
        if not hasattr(self, "flag_ribbon"):
            return
        key = self.active_patient_key()
        if not key:
            self.flag_ribbon.hide()
            if hasattr(self, "flag_ribbon_good"):
                self.flag_ribbon_good.hide()
            if hasattr(self, "flag_ribbon_container"):
                self.flag_ribbon_container.hide()
            return

        flags = get_patient_flags(key)
        active = [(f, d) for f, d in flags.items()
                   if d.get("value") == "1"]

        # ── Rhogam special alert ────────────────────────────────────
        rhogam_alert = ""
        try:
            _pregnancy_closed = any(
                (flags.get(k) or {}).get("value") == "1"
                for k in _BIRTH_OUTCOME_FLAG_KEYS)
        except Exception:
            _pregnancy_closed = False
        try:
            has_rh = any(f == "kan_uyusmazligi" for f, _ in active)
            if has_rh and not _pregnancy_closed and self.current_subfolder:
                pdf = get_latest_pdf_in_folder(self.current_subfolder)
                if pdf:
                    data = parse_pdf_summary_data(pdf)
                    ga_days = data.get("ga_days")
                    if isinstance(ga_days, (int, float)):
                        ga_weeks = int(ga_days) // 7
                        if 24 <= ga_weeks <= 32:
                            rhogam_alert = (
                                f"💉 RHOGAM ZAMANI! "
                                f"Kan uyuşmazlığı + {ga_weeks} hafta "
                                f"(24-32 hafta aralığında)")
        except Exception as ex:
            _log_warning(f"rhogam check failed: {ex}")

        # ── Classify flags ──────────────────────────────────────────
        danger_flags = []   # (label, notes)
        warning_flags = []  # (label, notes)
        info_flags = []     # (label, notes)
        good_flags = []     # (label, notes)

        for f, d in active:
            level = (PATIENT_FLAG_LEVELS.get(f)
                     or GYNEC_FLAG_LEVELS.get(f, "info"))
            label = (PATIENT_FLAG_LABELS.get(f)
                     or GYNEC_FLAG_LABELS.get(f, f))
            notes = (d.get("notes") or "").strip()
            entry = (label, notes)
            if level == "danger":
                danger_flags.append(entry)
            elif level == "warning":
                warning_flags.append(entry)
            elif level == "good":
                good_flags.append(entry)
            else:
                info_flags.append(entry)

        # ── Signature warning (synthetic) ───────────────────────────
        try:
            sig_w = self._compute_signature_warning(key, flags)
            if sig_w:
                warning_flags.append(
                    (sig_w["label"], sig_w["notes"]))
        except Exception as _ex:
            _log_warning(f"sig warning inject: {_ex}")

        # ── Nothing to show ─────────────────────────────────────────
        if not any([danger_flags, warning_flags, info_flags,
                     good_flags, rhogam_alert]):
            self.flag_ribbon.hide()
            if hasattr(self, "flag_ribbon_good"):
                self.flag_ribbon_good.hide()
            if hasattr(self, "flag_ribbon_container"):
                self.flag_ribbon_container.hide()
            return

        # ── LEFT ribbon: danger → kırmızı, warning → turuncu,
        #                info → mavi (priority order) ────────────────
        left_parts = []

        # Rhogam always first (emergency level)
        if rhogam_alert:
            left_parts.append(
                f"<span style='font-size:15px;'>💉</span> "
                f"<b style='letter-spacing:0.4px;'>RHOGAM ZAMANI!</b> "
                f"Kan uyuşmazlığı + GA 24-32 hafta")

        # DANGER: deep red
        for label, notes in danger_flags:
            txt = f"<b>❗ {label}</b>"
            if notes:
                txt += f" <span style='opacity:0.9;'>· {notes}</span>"
            left_parts.append(txt)

        # WARNING: orange — gathered separately for colour logic
        warn_parts = []
        for label, notes in warning_flags:
            txt = f"<b>⚠ {label}</b>"
            if notes:
                txt += f" <span style='opacity:0.9;'>· {notes}</span>"
            warn_parts.append(txt)

        # INFO: blue
        info_parts = []
        for label, notes in info_flags:
            txt = f"<b>ℹ {label}</b>"
            if notes:
                txt += f" <span style='opacity:0.9;'>· {notes}</span>"
            info_parts.append(txt)

        # Decide left ribbon colour (highest severity wins)
        has_left = bool(left_parts or warn_parts or info_parts)
        if has_left:
            if rhogam_alert or danger_flags:
                # Deep red gradient
                bg1, bg2 = "#9A1B1F", "#C42B1C"
                prefix_icon = "🔴"
                prefix_text = "DİKKAT"
            elif warning_flags:
                # Orange gradient
                bg1, bg2 = "#8C4A00", "#C46500"
                prefix_icon = "🟠"
                prefix_text = "UYARI"
            else:
                # Blue gradient
                bg1, bg2 = "#003F6F", "#0078D4"
                prefix_icon = "🔵"
                prefix_text = "BİLGİ"

            # Build HTML — all items in one rich pill
            all_left = left_parts + warn_parts + info_parts
            sep = (
                "<span style='opacity:0.6;margin:0 8px;'>·</span>")
            inner = sep.join(all_left)
            html_left = (
                f"<span style='font-size:13px;font-weight:800;"
                f"letter-spacing:0.3px;'>"
                f"{prefix_icon} {prefix_text}: </span>"
                f"{inner}")

            self.flag_ribbon.setTextFormat(Qt.RichText)
            self.flag_ribbon.setText(html_left)
            self.flag_ribbon.setStyleSheet(
                f"QLabel#FlagRibbon{{"
                f"color:#FFFFFF;"
                f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                f"stop:0 {bg1},stop:1 {bg2});"
                f"border:none;border-radius:10px;"
                f"font:600 12.5px 'Segoe UI';"
                f"padding:11px 16px;}}")
            self.flag_ribbon.setWordWrap(True)
            tip = "\n".join(
                f"• {lbl}: {n}" if n else f"• {lbl}"
                for lbl, n in (
                    danger_flags + warning_flags + info_flags))
            self.flag_ribbon.setToolTip(
                tip or "Klinik bayraklar — Bayraklar butonundan düzenleyin.")
            self.flag_ribbon.show()
        else:
            self.flag_ribbon.hide()

        # ── RIGHT ribbon: good → yeşil ──────────────────────────────
        if good_flags:
            good_parts = []
            for label, notes in good_flags:
                txt = f"<b>✅ {label}</b>"
                if notes:
                    txt += (f" <span style='opacity:0.9;'>"
                             f"· {notes}</span>")
                good_parts.append(txt)
            sep = "<span style='opacity:0.6;margin:0 8px;'>·</span>"
            inner_g = sep.join(good_parts)
            html_good = (
                f"<span style='font-size:13px;font-weight:800;"
                f"letter-spacing:0.3px;'>🟢 İYİ: </span>"
                f"{inner_g}")
            self.flag_ribbon_good.setTextFormat(Qt.RichText)
            self.flag_ribbon_good.setText(html_good)
            self.flag_ribbon_good.setStyleSheet(
                "QLabel#FlagRibbonGood{"
                "color:#FFFFFF;"
                "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                "stop:0 #0B5D0B,stop:1 #107C10);"
                "border:none;border-radius:10px;"
                "font:600 12.5px 'Segoe UI';"
                "padding:11px 16px;}")
            self.flag_ribbon_good.setWordWrap(True)
            tip_g = "\n".join(
                f"• {lbl}: {n}" if n else f"• {lbl}"
                for lbl, n in good_flags)
            self.flag_ribbon_good.setToolTip(
                tip_g or "Olumlu / güven verici durumlar.")
            self.flag_ribbon_good.show()
        else:
            self.flag_ribbon_good.hide()

        # ── Container visibility ─────────────────────────────────────
        if has_left or bool(good_flags):
            self.flag_ribbon_container.show()
        else:
            self.flag_ribbon_container.hide()
