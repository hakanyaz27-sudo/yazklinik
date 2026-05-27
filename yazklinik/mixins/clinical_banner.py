"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _ClinicalBannerMixin
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

class _ClinicalBannerMixin:
    """MainWindow methods related to ClinicalBanner. Mixed into MainWindow via MRO."""

    def _refresh_themed_widgets(self):
        """Re-style inline-styled widgets after a theme change.

        Problem: Qt stylesheet cascade — a widget's OWN setStyleSheet()
        always wins over the app-wide stylesheet. So flipping dark mode
        via `_apply_app_palette()` alone leaves all our custom-styled
        frames (grey flag box, yellow recs box, Patient Info, Notes,
        etc.) stuck in their build-time colours.

        This method walks the known theme-sensitive widgets and rebuilds
        their inline stylesheet from the current _theme() palette.
        Brand-coloured widgets (the blue banner, the red DİKKAT ribbon,
        the green/yellow/red severity chips) intentionally keep their
        colour in both themes — they're clinical signals, not chrome.

        Called from the dark-mode toggle in the Ayarlar menu. Safe to
        call when widgets haven't been built yet (uses hasattr guards).
        """
        t = _theme()
        bg_card   = t["bg_card"]
        bg_alt    = t["bg_alt"]
        bg_muted  = t["bg_muted"]
        border    = t["border_strong"]
        text      = t["text"]
        text_dim  = t["text_faint"]
        text_mute = t["text_dim"]

        # ── Yellow "Bu Hafta Yapılabilecekler" recommendations box ──
        # Keep yellow hint in LIGHT mode, switch to muted warm-dark in DARK.
        if hasattr(self, "ga_recommendations_box"):
            try:
                if t is THEME_DARK:
                    self.ga_recommendations_box.setStyleSheet(
                        "QFrame#GARecBox{background:#2E2A1F;"
                        "border:1px solid #6B5A2F;border-radius:4px;}")
                    if hasattr(self, "ga_recommendations_title"):
                        self.ga_recommendations_title.setStyleSheet(
                            "color:#E8C870;font:700 12px 'Segoe UI';"
                            "background:transparent;border:none;")
                    if hasattr(self, "ga_recommendations_content"):
                        self.ga_recommendations_content.setStyleSheet(
                            "color:#D8D8D8;font:500 11px 'Segoe UI';"
                            "background:transparent;border:none;")
                else:
                    self.ga_recommendations_box.setStyleSheet(
                        "QFrame#GARecBox{background:#FFF9E6;"
                        "border:1px solid #E8B800;border-radius:4px;}")
                    if hasattr(self, "ga_recommendations_title"):
                        self.ga_recommendations_title.setStyleSheet(
                            "color:#7A5A00;font:700 12px 'Segoe UI';"
                            "background:transparent;border:none;")
                    if hasattr(self, "ga_recommendations_content"):
                        self.ga_recommendations_content.setStyleSheet(
                            "color:#333333;font:500 11px 'Segoe UI';"
                            "background:transparent;border:none;")
            except Exception as _ex:
                _log_warning("_refresh_themed_widgets: recs box", exc=_ex)

        # ── Patient Info panel (sol üstteki kutu) ──
        for attr in ("pi_name_lbl", "pi_visit_count_lbl",
                     "pi_phone_lbl", "pi_last_visit_lbl",
                     "pi_signature_lbl"):
            w = getattr(self, attr, None)
            if w is None:
                continue
            try:
                # These are Q_PILabel / PIValue objectNames — let
                # object-name based selectors in the app stylesheet
                # drive them. We just clear any ad-hoc inline style.
                w.setStyleSheet(
                    f"color:{text};background:transparent;border:none;")
            except Exception as _ex:
                _log_warning(f"_refresh_themed_widgets: {attr}", exc=_ex)

        # ── Stat bar cards (right side of status bar) ──
        for attr in ("stat_patients", "stat_visits", "stat_files",
                     "stat_visit", "stat_wa", "stat_signature"):
            w = getattr(self, attr, None)
            if w is None:
                continue
            try:
                # StatCard is a composite widget — re-apply its own
                # stylesheet by calling its refresh hook if it has one
                if hasattr(w, "apply_theme"):
                    w.apply_theme()
                else:
                    # Fallback: clear any inline style so app-wide wins
                    w.setStyleSheet("")
            except Exception as _ex:
                _log_warning(f"_refresh_themed_widgets: {attr}", exc=_ex)

        # ── Note editor backgrounds ──
        for attr in ("note_edit", "summary_text"):
            w = getattr(self, attr, None)
            if w is None:
                continue
            try:
                w.setStyleSheet(
                    f"background:{t['bg']};color:{text};"
                    f"border:1px solid {border};padding:4px;")
            except Exception as _ex:
                _log_warning(f"_refresh_themed_widgets: {attr}", exc=_ex)

        # ── Phone input compact (flag bar) ──
        if hasattr(self, "phone_input_compact"):
            try:
                self.phone_input_compact.setStyleSheet(
                    f"QLineEdit#PhoneBox{{background:{t['bg']};"
                    f"border:1px solid {border};border-radius:3px;"
                    f"padding:3px 6px;font:500 11px 'Segoe UI';"
                    f"color:{text};}}")
            except Exception as _ex:
                _log_warning(
                    "_refresh_themed_widgets: phone_input_compact",
                    exc=_ex)

    def _render_gynecologic_banner(self):
        """Render a simplified pink banner for gynecologic patients
        (no obstetric data, no GA/EDD). Shows patient name + optional
        age + visit date chip + "🌸 Jinekolojik Takip" label.
        """
        if not hasattr(self, "clinical_banner") or not self.current_patient:
            return

        # v68: Show the "🌸 Jinekolojik Takip" tab (top bar, next to
        # Notlar) and load the saved form data so the doctor sees a
        # pre-filled form when they click the tab. Obstetric form tab
        # hidden here (wrong mode).
        try:
            if hasattr(self, "tabs") and hasattr(self, "_gynec_tab_index"):
                self.tabs.setTabVisible(self._gynec_tab_index, True)
            if hasattr(self, "tabs") and hasattr(self, "_obs_tab_index"):
                self.tabs.setTabVisible(self._obs_tab_index, False)
            if hasattr(self, "_load_gynec_form"):
                self._load_gynec_form()
            # v68: Update the F6 quick-action button label
            if hasattr(self, "_refresh_quick_action_labels"):
                self._refresh_quick_action_labels()
            # v68: Hide the GA recommendations panel — gyn patients
            # have no GA-keyed recommendations
            if hasattr(self, "_update_ga_recommendations"):
                self._update_ga_recommendations()
            # v68: Surface the DİKKAT flag ribbon with GYNEC_FLAGS
            # so the doctor's checked jinekolojik bayraklar are
            # actually visible on the patient-summary tab.
            if hasattr(self, "_load_patient_flags_into_ui"):
                self._load_patient_flags_into_ui()
            if hasattr(self, "_update_flag_ribbon"):
                self._update_flag_ribbon()
        except Exception as _ex:
            _log_warning("_render_gynecologic_banner: tab/load", exc=_ex)

        parts = []

        # Visit date chip (same as obstetric banner)
        try:
            if getattr(self, "current_subfolder", None) is not None:
                _visit_name = format_visit_name(self.current_subfolder.name)
                if _visit_name:
                    parts.append(
                        f"<span style='font-size:11px;font-weight:500;"
                        f"opacity:0.88;'>📅 {_visit_name}</span>"
                        f"  <span style='opacity:0.5;'>•</span>  ")
        except Exception as _ex:
            _log_warning("gyn banner: visit chip", exc=_ex)

        # Patient name
        try:
            pname = format_patient_name(self.current_patient.name)
            if pname:
                parts.append(
                    f"<span style='font-size:18px;font-weight:700;'>"
                    f"{pname}</span>"
                    f"  <span style='opacity:0.6;'>|</span>  ")
        except Exception as _ex:
            _log_warning("gyn banner: name", exc=_ex)

        # Age if we can find it
        try:
            age = None
            if self.current_subfolder:
                pdf = get_latest_pdf_in_folder(self.current_subfolder)
                if pdf:
                    data = parse_pdf_summary_data(pdf)
                    age_str = data.get("Yaş")
                    if age_str and age_str != "-":
                        age = age_str
            if age is not None:
                parts.append(
                    f"<span style='font-size:14px;'>"
                    f"<b>{age}</b> yaş</span>"
                    f"  <span style='opacity:0.5;'>•</span>  ")
        except Exception as _ex:
            _log_warning("gyn banner: age", exc=_ex)

        # Big chip — Jinekolojik Takip
        parts.append(
            "<span style='background:rgba(255,255,255,0.22);"
            "padding:4px 14px;border-radius:14px;font-weight:700;"
            "font-size:13px;letter-spacing:0.3px;'>"
            "🌸 Jinekolojik Takip</span>")

        # Pink gradient instead of blue
        self.clinical_banner.setStyleSheet(
            "QLabel#ClinicalBanner{"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #8B2A6D, stop:1 #B5368A);"
            "color:#FFFFFF;"
            "border:none;"
            "border-radius:6px;"
            "padding:14px 20px;"
            "font:600 14px 'Segoe UI';}"
            "QLabel#ClinicalBanner:hover{"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #6F2256, stop:1 #9A2E78);}")

        self.clinical_banner.setText("".join(parts))
        self.clinical_banner.setToolTip(
            "Jinekolojik hasta — PDF'lerde 'Obstetrics Report' bulunmuyor. "
            "Tıkla → demografi düzenle.")
        self.clinical_banner.show()

    def _apply_obstetric_banner_style(self):
        """Reset the clinical banner to the default blue obstetric style.
        Called at the start of the obstetric render path so that if the
        patient was previously viewed as gynecologic (pink), switching
        back restores the blue gradient properly.
        """
        if not hasattr(self, "clinical_banner"):
            return
        # v68: Also flip the "🌸 Jinekolojik Takip" tab visibility.
        # Hidden in obstetric mode, visible in gynecologic.
        # The "📋 Gebelik Takibi" tab is visible in obstetric mode.
        try:
            if hasattr(self, "tabs") and hasattr(self, "_gynec_tab_index"):
                self.tabs.setTabVisible(self._gynec_tab_index, False)
            if hasattr(self, "tabs") and hasattr(self, "_obs_tab_index"):
                self.tabs.setTabVisible(self._obs_tab_index, True)
            if hasattr(self, "_load_obs_form"):
                self._load_obs_form()
            # v68: Update the F6 quick-action button label
            if hasattr(self, "_refresh_quick_action_labels"):
                self._refresh_quick_action_labels()
            # v68: Refresh the GA recommendations panel — it might
            # need to come back if we're switching from gyn to obs
            if hasattr(self, "_update_ga_recommendations"):
                self._update_ga_recommendations()
        except Exception as _ex:
            _log_warning("_apply_obstetric_banner_style: tab", exc=_ex)
        self.clinical_banner.setStyleSheet(
            "QLabel#ClinicalBanner{"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #005A9E, stop:1 #0078D4);"
            "color:#FFFFFF;"
            "border:none;"
            "border-radius:6px;"
            "padding:14px 20px;"
            "font:600 14px 'Segoe UI';}"
            "QLabel#ClinicalBanner:hover{"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #004578, stop:1 #005A9E);}")
        self.clinical_banner.setToolTip(
            "Tıkla → kan grubu, Rh, obstetrik öykü, ilaçlar düzenle")

    def _show_planlama_menu(self):
        """v68-AI: Planlama buton → alt menü aç.

        Planlama artık bir menü. Altında iki seçenek:
          • 📅 Gebelik Takibi — LMP'den doğuma tüm milestone'lar
            (eski Planlama içeriği — `_open_followup_tab_for_mode`)
          • 📋 Test Listesi — tahlil PDF'i yükle + tarihli arşiv
            (`_show_lab_tracker_dialog`)

        Jinekoloji modunda sadece jinekolojik takip açılır.
        """
        if self.current_patient is None:
            QMessageBox.warning(self, "Hasta Yok",
                                  "Önce bir hasta seçin.")
            return

        # Gynecology mode: skip the menu, open jinekolojik takip
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
                # v68-AI: Jinekoloji modunda Planlama →
                # infertilite/tedavi planlaması yazılabilir not.
                self._show_infertility_plan_dialog()
                return
        except Exception as _ex:
            _log_warning(f"planlama menu gyn detect: {_ex}")

        # Build popup menu
        menu = QMenu(self)
        menu.setStyleSheet(
            "QMenu{background:#FFFFFF;border:1px solid #CCC;"
            "padding:6px;font:600 13px 'Segoe UI';}"
            "QMenu::item{padding:10px 18px;border-radius:6px;"
            "margin:2px;}"
            "QMenu::item:selected{background:#E3F2FD;"
            "color:#003F6F;}")

        # ── Gebelik Takibi (eski Planlama içeriği) ──────────────────
        gt_act = QAction("📅  Gebelik Takibi", self)
        gt_act.setToolTip(
            "LMP'den doğuma tüm milestone'ları gösteren gebelik "
            "takvimi handout'u (A4 yazdırılır)")
        gt_act.triggered.connect(self._open_followup_tab_for_mode)
        menu.addAction(gt_act)

        # ── Tetkik Listesi (yapılması gereken tetkikler + A5) ──────
        tl_act = QAction("🧾  Tetkik Listesi", self)
        tl_act.setToolTip(
            "Bu gebelik haftasında yapılması gereken tetkikleri "
            "listele. Yapılmış tahliller hariç tutulur. "
            "A5 yazdırılabilir.")
        tl_act.triggered.connect(self._show_test_order_dialog)
        menu.addAction(tl_act)

        # Show under the clicked button
        btn = None
        if hasattr(self, "_qa_buttons"):
            btn = self._qa_buttons.get("followup")
        if btn is not None:
            # Anchor to the bottom-left corner of the button
            global_pos = btn.mapToGlobal(btn.rect().bottomLeft())
            menu.exec(global_pos)
        else:
            # Fallback: show at cursor
            menu.exec(QCursor.pos())

    def _open_followup_tab_for_mode(self):
        """Slot for the F6 quick-action button ("📋 Planlama" in
        obstetric mode, "🌸 Jinekolojik Takip" in gynecology mode).

        v68: In OBSTETRIC mode this now opens the printable
        "Gebelik Takvimi" handout — the milestone schedule table that
        lists every prenatal visit the patient should attend from
        LMP through delivery. This is what the doctor wants to hand
        to the gebe on first visit.

        The "📋 Gebelik Takibi" form tab (the per-visit workup form)
        is still accessible — it lives as a top-level tab and the
        doctor clicks that tab to open it.

        In GYNECOLOGY mode it still opens the jinekolojik takip form
        tab (infertility workup has no equivalent handout).
        """
        try:
            override = getattr(self, "_mode_override", None)
            is_gyn = False
            if override == "gynecologic":
                is_gyn = True
            elif override == "obstetric":
                is_gyn = False
            elif self.current_patient is not None:
                is_gyn = is_gynecologic_patient(self.current_patient)
        except Exception as _ex:
            _log_warning("_open_followup_tab_for_mode: detect", exc=_ex)
            is_gyn = False
        if is_gyn:
            self._open_gynec_followup_tab()
        else:
            # v68: Obstetric mode → printable pregnancy calendar
            # handout (F6 original behaviour restored per doctor's
            # request).
            try:
                self._show_pregnancy_calendar()
            except Exception as _ex:
                _log_warning("_open_followup_tab_for_mode: calendar",
                             exc=_ex)

    def _refresh_quick_action_labels(self):
        """Update the F6 quick-action button label to reflect the
        current mode. Called whenever the effective mode changes
        (patient select, mode toggle, manual override)."""
        if not hasattr(self, "_qa_buttons"):
            return
        try:
            override = getattr(self, "_mode_override", None)
            is_gyn = False
            if override == "gynecologic":
                is_gyn = True
            elif override == "obstetric":
                is_gyn = False
            elif self.current_patient is not None:
                is_gyn = is_gynecologic_patient(self.current_patient)
        except Exception as _ex:
            _log_warning("_refresh_quick_action_labels", exc=_ex)
            is_gyn = False
        # Find the F6 button and re-label it
        btn = self._qa_buttons.get("followup")
        if btn is not None:
            if is_gyn:
                # v68: In gynecology mode the "🌸 Jinekolojik Takip"
                # tab is already at the top (next to Notlar), so the
                # F6 button is redundant. Hide it so the quick-action
                # row stays clean.
                btn.setVisible(False)
            else:
                btn.setVisible(True)
                btn.setText("📋  Planlama")
                btn.setToolTip(
                    "Gebelik Takvimi — izlem planı (A4 yazdırılır). "
                    "Hastanın LMP'den doğuma kadar tüm gebelik "
                    "milestone'larını (tetkikler, USG, aşılar) gösterir. "
                    "\n\nGebelik Takibi formunu açmak için yukardaki "
                    "\"📋 Gebelik Takibi\" sekmesini kullanın.\n\nKısayol: F6")

        # v68: F8 Büyüme Eğrileri — only meaningful for obstetric
        # follow-up (fetal biometry graph). Hide the button entirely
        # in gynecologic mode so the quick-action row stays clean.
        growth_btn = self._qa_buttons.get("growth")
        if growth_btn is not None:
            growth_btn.setVisible(not is_gyn)

    def _open_obs_followup_tab(self):
        """Switch to the "🤰 Obstetrik Takip" tab. If the tab is hidden
        (because the app is in jinekoloji mode), force-show it first.
        Used by the F6 quick-action button which previously opened
        the printable pregnancy calendar — now opens the form instead.
        """
        if not hasattr(self, "tabs") or not hasattr(self, "_obs_tab_index"):
            QMessageBox.information(
                self, "Sekme Yok",
                "Obstetrik Takip sekmesi henüz hazır değil.")
            return
        try:
            self.tabs.setTabVisible(self._obs_tab_index, True)
            self.tabs.setCurrentIndex(self._obs_tab_index)
            # Make sure the form has the current patient's saved values
            if hasattr(self, "_load_obs_form"):
                self._load_obs_form()
        except Exception as _ex:
            _log_warning("_open_obs_followup_tab", exc=_ex)

    def _open_gynec_followup_tab(self):
        """Switch to the "🌸 Jinekolojik Takip" tab. Mirror of
        _open_obs_followup_tab."""
        if not hasattr(self, "tabs") or \
                not hasattr(self, "_gynec_tab_index"):
            QMessageBox.information(
                self, "Sekme Yok",
                "Jinekolojik Takip sekmesi henüz hazır değil.")
            return
        try:
            self.tabs.setTabVisible(self._gynec_tab_index, True)
            self.tabs.setCurrentIndex(self._gynec_tab_index)
            if hasattr(self, "_load_gynec_form"):
                self._load_gynec_form()
        except Exception as _ex:
            _log_warning("_open_gynec_followup_tab", exc=_ex)

    def _delete_current_patient(self):
        """Permanently delete the currently-selected patient. Two-step
        confirmation, then folder + DB cleanup. Returns the patient
        list to its previous state (no-selection)."""
        if not self.current_patient:
            QMessageBox.information(
                self, "Hasta Seçilmedi",
                "Silmek için önce bir hasta seçin.")
            return

        pname = format_patient_name(self.current_patient.name)
        ppath = self.current_patient

        # Count visits + DB rows so the user knows what will be lost
        visit_count = 0
        try:
            visit_count = len(get_subfolders(ppath))
        except Exception as _ex:
            _log_warning("delete patient: count visits", exc=_ex)

        # First confirm
        msg1 = QMessageBox(self)
        msg1.setIcon(QMessageBox.Warning)
        msg1.setWindowTitle("Hastayı Sil")
        msg1.setText(
            f"<b>{pname}</b> hastasını silmek üzeresiniz.")
        msg1.setInformativeText(
            f"<b>Silinecek olanlar:</b>"
            f"<ul>"
            f"<li>Hasta klasörü: <code>{ppath}</code></li>"
            f"<li>Tüm gelişler ({visit_count} klasör + içindekiler)</li>"
            f"<li>Tüm görüntüler, DICOM, video, PDF dosyaları</li>"
            f"<li>Tüm not, demografi, formlar (obstetrik + jinekolojik)</li>"
            f"<li>İmza geçmişi, telefon, bayraklar</li>"
            f"</ul>"
            f"<b style='color:#C42B1C;'>Bu işlem GERİ ALINAMAZ.</b><br><br>"
            f"Devam etmek istiyor musunuz?")
        msg1.setStandardButtons(QMessageBox.Yes | QMessageBox.Cancel)
        msg1.setDefaultButton(QMessageBox.Cancel)
        msg1.button(QMessageBox.Yes).setText("Evet, devam et")
        if msg1.exec() != QMessageBox.Yes:
            return

        # Second confirm — type the name
        from PySide6.QtWidgets import QInputDialog
        confirm_text, ok = QInputDialog.getText(
            self, "Silmeyi Onayla",
            f"Onay için hastanın adını yazın:\n\n<b>{pname}</b>",
            QLineEdit.Normal)
        if not ok:
            return
        if confirm_text.strip().lower() != pname.strip().lower():
            QMessageBox.warning(
                self, "Onay Başarısız",
                "Yazılan ad eşleşmedi. Silme iptal edildi.")
            return

        # Do it
        try:
            summary = delete_patient_completely(
                ppath.name,
                also_delete_folder=True,
                folder_path=ppath)
        except Exception as ex:
            QMessageBox.critical(
                self, "Silme Hatası",
                f"Hasta klasörü silinirken hata oluştu:\n\n{ex}\n\n"
                f"DB kayıtları kısmen silinmiş olabilir. NAS klasörünü "
                f"manuel olarak kontrol edin.")
            _log_warning("_delete_current_patient", exc=ex)
            return

        # Report
        rows_total = sum(summary["rows_deleted"].values())
        folder_msg = "✓ Klasör silindi." if summary["folder_deleted"] \
            else "(Klasör zaten yoktu.)"
        QMessageBox.information(
            self, "Silindi",
            f"<b>{pname}</b> başarıyla silindi.<br><br>"
            f"• {rows_total} veritabanı kaydı silindi<br>"
            f"• {folder_msg}")

        # Clear current selection + refresh
        try:
            self.current_patient = None
            if hasattr(self, "_clear_current_patient_view"):
                self._clear_current_patient_view(
                    preserve_mode_override=False)
            self.refresh_all()
        except Exception as _ex:
            _log_warning("_delete_current_patient: refresh", exc=_ex)

        self.statusBar().showMessage(
            f"✓ Hasta silindi: {pname}", 6000)

    def _open_new_visit_dialog(self):
        """Open the manual visit creation dialog for the currently
        selected patient. Creates a YYYY-MM-DD_HHMM folder under the
        patient's root and persists the note to visit_notes.
        """
        if not self.current_patient:
            QMessageBox.information(
                self, "Hasta Seçilmedi",
                "Yeni geliş eklemek için önce bir hasta seçin "
                "(veya Ctrl+N ile yeni hasta oluşturun).")
            return
        if not self.current_patient.exists():
            QMessageBox.critical(
                self, "Klasör Yok",
                f"Hasta klasörü bulunamıyor:\n{self.current_patient}")
            return

        try:
            dlg = NewVisitDialog(self.current_patient, self)
            if dlg.exec() != QDialog.Accepted:
                return
            new_visit = dlg.created_visit_path
            if new_visit is None:
                return

            # Refresh visits list for this patient
            try:
                self.subfolder_paths = get_subfolders(self.current_patient)
            except Exception as _ex:
                _log_warning("new visit: refresh visits", exc=_ex)

            # Update the visits list widget so the new entry appears
            try:
                self._refresh_visits_list_for_current_patient()
            except Exception as _ex:
                _log_warning("new visit: refresh list", exc=_ex)

            # Auto-select the new visit so the doctor lands on it
            try:
                self._select_visit_by_path(new_visit)
            except Exception as _ex:
                _log_warning("new visit: select", exc=_ex)

            self.statusBar().showMessage(
                f"✓ Yeni geliş eklendi: {new_visit.name}", 6000)
        except Exception as ex:
            _log_warning("_open_new_visit_dialog", exc=ex)
            QMessageBox.critical(
                self, "Geliş Eklenemedi",
                f"Yeni geliş kaydı yapılamadı:\n\n{ex}")

    def _refresh_visits_list_for_current_patient(self):
        """Rebuild the left-panel visits list from current
        self.subfolder_paths. Equivalent to what _select_patient_by_path
        does internally — extracted so we can call it from outside
        the patient-change flow (eg. after creating a new visit)."""
        try:
            if not hasattr(self, "visits_list_widget"):
                return
            self.visits_list.blockSignals(True)
            self.visits_list.clear()
            from datetime import date as _date_today
            today_iso = _date_today.today().isoformat()
            for v in self.subfolder_paths:
                vname = v.name
                # v68: Decorate today's visit with 📍 prefix so it
                # stands out — doctor frequently looks at "today"
                # context first.
                display = format_visit_name(vname)
                if vname[:10] == today_iso:
                    display = "📍 " + display + "  ·  Bugün"
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, ("visit", str(v)))
                # Tooltip with raw folder name for traceability
                item.setToolTip(vname)
                self.visits_list.addItem(item)
            self.visits_list.blockSignals(False)
            # Update the patient-info side panel last visit label
            try:
                if hasattr(self, "pi_visit_count_lbl"):
                    self.pi_visit_count_lbl.setText(
                        str(len(self.subfolder_paths)))
                if hasattr(self, "pi_last_visit_lbl") and \
                        self.subfolder_paths:
                    self.pi_last_visit_lbl.setText(
                        format_visit_name(self.subfolder_paths[0].name))
            except Exception as _ex:
                _log_warning("refresh visits list: side panel", exc=_ex)
        except Exception as _ex:
            _log_warning("_refresh_visits_list_for_current_patient",
                         exc=_ex)

    def _open_new_patient_dialog(self):
        """Open the manual patient registration dialog. On success,
        adds the patient to the list, selects them, switches the app
        to the matching obstetric/gynecologic mode, and refreshes
        the UI (banner, gynec tab, etc).
        """
        try:
            dlg = NewPatientDialog(getattr(self, "root_folder", None), self)
            if dlg.exec() != QDialog.Accepted:
                return
            new_path = dlg.created_path
            new_type = dlg.created_type
            if new_path is None:
                return

            # 1) Refresh the patient list so the new folder appears
            try:
                self.refresh_all()
            except Exception as _ex:
                _log_warning("new patient: refresh", exc=_ex)

            # 2) Select the new patient first — _select_patient_by_path
            #    calls _reset_mode_override(), so we can't set the override
            #    BEFORE selection (it would be cleared immediately). The
            #    auto-detected mode for this patient will already be
            #    correct because set_patient_type() persisted it to DB
            #    where is_gynecologic_patient() looks first.
            try:
                self._select_patient_by_path(new_path)
            except Exception as _ex:
                _log_warning("new patient: select", exc=_ex)

            # 3) Set the manual mode override AFTER selection — this is
            #    a defensive belt-and-braces step in case the DB
            #    lookup fails or the cache is stale.
            if new_type == "gynecologic":
                self._mode_override = "gynecologic"
            else:
                self._mode_override = "obstetric"

            # 4) Re-trigger the banner refresh now that the override
            #    is in place
            try:
                self._update_clinical_banner()
            except Exception as _ex:
                _log_warning("new patient: refresh banner", exc=_ex)

            # 5) Refresh the toggle button label to reflect the new mode
            try:
                self._refresh_mode_toggle_label()
            except Exception as _ex:
                _log_warning("new patient: refresh label", exc=_ex)

            # 6) Confirmation message
            mode_lbl = ("🌸 Jinekoloji"
                        if new_type == "gynecologic"
                        else "🤰 Obstetrik")
            self.statusBar().showMessage(
                f"✓ Hasta kaydedildi: {new_path.name} ({mode_lbl} modu)",
                6000)
        except Exception as ex:
            _log_warning("_open_new_patient_dialog", exc=ex)
            QMessageBox.critical(
                self, "Hasta Kaydı Hatası",
                f"Yeni hasta kaydı yapılamadı:\n\n{ex}")

    def _toggle_patient_mode(self):
        """Manually toggle between obstetric (pregnancy follow-up) and
        gynecologic (infertility) modes for the currently-selected
        patient. Invoked from the toolbar button.

        Sets `self._mode_override` to "obstetric" or "gynecologic" so
        the banner, test-sheet and diet dialogs all use the chosen
        mode regardless of PDF content. The override clears whenever
        a different patient is selected (see `_reset_mode_override`).

        If no patient is selected we still toggle a "default-mode"
        hint — though the banner stays hidden until a patient is
        picked, the next patient will inherit the choice.
        """
        # Determine current effective mode
        current_is_gyn = False
        try:
            override = getattr(self, "_mode_override", None)
            if override == "gynecologic":
                current_is_gyn = True
            elif override == "obstetric":
                current_is_gyn = False
            elif self.current_patient is not None:
                current_is_gyn = is_gynecologic_patient(self.current_patient)
        except Exception as _ex:
            _log_warning("_toggle_patient_mode: detect current", exc=_ex)

        # Flip it
        new_mode = "obstetric" if current_is_gyn else "gynecologic"
        self._mode_override = new_mode

        # v68: When the doctor manually flips the mode, the currently-
        # displayed patient is by definition NOT the right type for
        # the new mode (otherwise auto-detection would already have
        # matched). Showing their data on the new mode's UI is
        # confusing — the obstetric banner would still list a non-gyn
        # patient's GA, the test sheet would suggest infertility tests
        # for an obviously pregnant patient, etc. So we clear the
        # current selection and present a clean empty page in the
        # newly-chosen mode. The doctor then picks a fresh patient
        # whose data is actually relevant.
        try:
            self._clear_current_patient_view(preserve_mode_override=True)
        except Exception as _ex:
            _log_warning("_toggle_patient_mode: clear view", exc=_ex)

        # Refresh UI — banner + any open dialogs by triggering
        # the standard patient-change callbacks
        try:
            self._update_clinical_banner()
        except Exception as _ex:
            _log_warning("_toggle_patient_mode: refresh banner", exc=_ex)

        # Update toolbar button label to match new mode
        self._refresh_mode_toggle_label()

        # v68: Show/hide the Jinekolojik Takip tab based on mode
        try:
            self._refresh_gynec_tab_visibility()
        except Exception as _ex:
            _log_warning("_toggle_patient_mode: tab vis", exc=_ex)

        # Visual confirmation in the status bar
        mode_label = ("🌸 Jinekoloji Modu" if new_mode == "gynecologic"
                      else "🤰 Obstetrik (Gebelik) Modu")
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(
                f"✓ {mode_label} aktif — uygun bir hasta seçin "
                f"(yeni hasta otomatik algılamaya döner)", 6000)

    def _clear_current_patient_view(self,
                                    preserve_mode_override: bool = False):
        """Drop the currently-selected patient from the UI without
        touching the patient list itself. Used when the doctor toggles
        between obstetric and gynecologic modes — the previous patient
        is no longer relevant for the new view, so we clear all
        per-patient widgets and show an empty placeholder.

        preserve_mode_override:
            When True, keep self._mode_override intact (so the next
            patient still inherits the doctor's manual choice — no,
            actually the next patient triggers _select_patient_by_path
            which calls _reset_mode_override; preserve_mode_override
            only matters for clearing the *current* widgets without
            ALSO resetting the override here).
        """
        # 1) Detach selection from the patients list (without firing
        #    the change handler, which would re-select something)
        try:
            if hasattr(self, "patient_list_widget"):
                self.patient_list.blockSignals(True)
                self.patient_list.clearSelection()
                self.patient_list.setCurrentItem(None)
                self.patient_list.blockSignals(False)
        except Exception as _ex:
            _log_warning("_clear_current_patient_view: list", exc=_ex)

        # 2) Clear core state
        self.current_patient = None
        if hasattr(self, "current_subfolder"):
            self.current_subfolder = None
        if hasattr(self, "subfolder_paths"):
            self.subfolder_paths = []
        if hasattr(self, "current_files"):
            self.current_files = []
        if hasattr(self, "_pdf_canvas_items"):
            self._pdf_canvas_items = []

        # 3) Clear the visits list on the left
        try:
            if hasattr(self, "visits_list_widget"):
                self.visits_list.blockSignals(True)
                self.visits_list.clear()
                self.visits_list.blockSignals(False)
        except Exception as _ex:
            _log_warning("_clear_current_patient_view: visits", exc=_ex)

        # 4) Reset the patient-info side panel labels
        try:
            if hasattr(self, "pi_name_lbl"):
                self.pi_name_lbl.setText("—")
            if hasattr(self, "pi_visit_count_lbl"):
                self.pi_visit_count_lbl.setText("0")
            if hasattr(self, "pi_last_visit_lbl"):
                self.pi_last_visit_lbl.setText("—")
            if hasattr(self, "pi_phone_lbl"):
                self.pi_phone_lbl.setText("—")
            # v68: Also reset the new medical rows added in this version
            for attr in ("pi_age_lbl", "pi_blood_lbl", "pi_gpal_lbl",
                         "pi_chronic_lbl", "pi_meds_lbl",
                         "pi_allergies_lbl"):
                if hasattr(self, attr):
                    getattr(self, attr).setText("-")
                    getattr(self, attr).setToolTip("")
        except Exception as _ex:
            _log_warning("_clear_current_patient_view: side", exc=_ex)

        # 5) Hide the clinical banner — _update_clinical_banner already
        #    does this when current_patient is None, but we want a fresh
        #    one rendered with the new mode. The caller (_toggle_patient_mode)
        #    will call _update_clinical_banner right after; here we only
        #    re-show as the empty-mode placeholder.
        try:
            if hasattr(self, "clinical_banner"):
                # Show a friendly "pick a patient" message in the
                # current mode's colour, instead of just hiding.
                effective_mode = getattr(self, "_mode_override", None)
                if effective_mode == "gynecologic":
                    self.clinical_banner.setStyleSheet(
                        "QLabel#ClinicalBanner{"
                        "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                        "stop:0 #8B2A6D, stop:1 #B5368A);"
                        "color:#FFFFFF;border:none;border-radius:6px;"
                        "padding:14px 20px;font:600 14px 'Segoe UI';}")
                    self.clinical_banner.setText(
                        "<span style='font-size:15px;'>"
                        "🌸 <b>Jinekoloji Modu</b>"
                        "</span>"
                        "  <span style='opacity:0.7;'>•</span>  "
                        "<span style='font-size:12px;opacity:0.92;'>"
                        "Sol listeden bir jinekolojik hasta seçin "
                        "veya yeni hasta arayın</span>")
                else:
                    self.clinical_banner.setStyleSheet(
                        "QLabel#ClinicalBanner{"
                        "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                        "stop:0 #005A9E, stop:1 #0078D4);"
                        "color:#FFFFFF;border:none;border-radius:6px;"
                        "padding:14px 20px;font:600 14px 'Segoe UI';}")
                    self.clinical_banner.setText(
                        "<span style='font-size:15px;'>"
                        "🤰 <b>Obstetrik (Gebelik Takip) Modu</b>"
                        "</span>"
                        "  <span style='opacity:0.7;'>•</span>  "
                        "<span style='font-size:12px;opacity:0.92;'>"
                        "Sol listeden bir gebe hasta seçin "
                        "veya yeni hasta arayın</span>")
                self.clinical_banner.setToolTip(
                    "Hasta seçili değil — sol listeden bir hasta seçin.")
                self.clinical_banner.show()
        except Exception as _ex:
            _log_warning("_clear_current_patient_view: banner", exc=_ex)

        # 6) Hide the flag-warning ribbon if any
        try:
            if hasattr(self, "flag_warning_ribbon"):
                self.flag_warning_ribbon.hide()
        except Exception as _ex:
            _log_warning("_clear_current_patient_view: flag", exc=_ex)

        # 7) Clear PDF viewer + image gallery + DICOM grid + videos + notes
        try:
            if hasattr(self, "pdf_viewer") and \
               hasattr(self.pdf_viewer, "load_pdf"):
                # Existing PdfViewer accepts None to display an empty
                # placeholder — there's no separate clear_pdf method.
                self.pdf_viewer.load_pdf(None)
        except Exception as _ex:
            _log_warning("_clear_current_patient_view: pdf", exc=_ex)
        try:
            if hasattr(self, "gallery_host"):
                # Image gallery is a QWidget container with a layout —
                # remove every child widget to clear it.
                lay = self.gallery_host.layout()
                if lay is not None:
                    while lay.count() > 0:
                        it = lay.takeAt(0)
                        w = it.widget()
                        if w is not None:
                            w.deleteLater()
            if hasattr(self, "gallery_count_lbl"):
                self.gallery_count_lbl.setText("0 resim")
        except Exception as _ex:
            _log_warning("_clear_current_patient_view: gallery", exc=_ex)
        try:
            if hasattr(self, "_clear_dicom_grid"):
                self._clear_dicom_grid()
            if hasattr(self, "dicom_count_lbl"):
                self.dicom_count_lbl.setText("0 görüntü")
        except Exception as _ex:
            _log_warning("_clear_current_patient_view: dicom", exc=_ex)
        try:
            if hasattr(self, "note_edit"):
                self.note_edit.blockSignals(True)
                self.note_edit.clear()
                self.note_edit.blockSignals(False)
            if hasattr(self, "notes_summary_text"):
                self.notes_summary_text.clear()
            if hasattr(self, "notes_visits_list"):
                self.notes_visits_list.clear()
        except Exception as _ex:
            _log_warning("_clear_current_patient_view: notes", exc=_ex)

        # 8) Reset summary tab if it has a known root widget
        try:
            if hasattr(self, "summary_text"):
                self.summary_text.clear()
        except Exception as _ex:
            _log_warning("_clear_current_patient_view: summary", exc=_ex)

        # 9) Switch to the patient-summary tab so the doctor lands
        #    on the welcome banner instead of staying on, say, the
        #    DICOM tab from the previous patient.
        try:
            if hasattr(self, "tabs"):
                # v68: Obstetric mode → "📋 Gebelik Takibi" top tab.
                # Gyn mode → "🌸 Jinekolojik Takip" top tab.
                effective_mode = getattr(self, "_mode_override", None)
                is_gyn_mode = (effective_mode == "gynecologic")
                if hasattr(self, "_gynec_tab_index"):
                    self.tabs.setTabVisible(
                        self._gynec_tab_index, is_gyn_mode)
                if hasattr(self, "_obs_tab_index"):
                    self.tabs.setTabVisible(
                        self._obs_tab_index, not is_gyn_mode)
                self.tabs.setCurrentIndex(0)
        except Exception as _ex:
            _log_warning("_clear_current_patient_view: tabs", exc=_ex)

    def _refresh_mode_toggle_label(self):
        """Sync the toolbar toggle button's label with the current
        effective mode (obstetric vs gynecologic). Called whenever
        the mode changes or the patient changes."""
        if not hasattr(self, "a_mode_toggle"):
            return
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
            _log_warning("_refresh_mode_toggle_label", exc=_ex)
        # Button label shows the CURRENT mode — clicking the button
        # switches to the OTHER mode. (Reversed from the previous
        # "...e Geç" wording per doctor's preference: simpler, clearer
        # at a glance.)
        if is_gyn:
            self.a_mode_toggle.setText("🌸 Jinekolojik")
            self.a_mode_toggle.setToolTip(
                "Şu an: 🌸 Jinekoloji Modu.\n"
                "Tıkla → Obstetrik (gebe takibi) moduna geç.\n"
                "Hasta değiştiğinde otomatik algılamaya döner.")
        else:
            self.a_mode_toggle.setText("🤰 Obstetrik")
            self.a_mode_toggle.setToolTip(
                "Şu an: 🤰 Obstetrik (Gebelik) Modu.\n"
                "Tıkla → Jinekoloji (infertilite) moduna geç.\n"
                "Hasta değiştiğinde otomatik algılamaya döner.")

    def _reset_mode_override(self):
        """Clear any manual mode override. Call from the patient-change
        handler so each new patient starts in auto-detect mode."""
        self._mode_override = None
        self._refresh_mode_toggle_label()

    def _update_clinical_banner(self):
        """Update the big blue 'at-a-glance' banner with pregnancy status.

        Shows: GA (weeks+days), EDD (days remaining), last visit, blood
        type + Rh if recorded, GPAL. For C-section–flagged patients the
        banner adds the PLANNED DELIVERY DATE (EDD − 14 days) next to
        the obstetric EDD. When GA ≥ 36 weeks an orange/red warning
        strip appears at the right of the banner — this is the
        "36. haftaya yaklaştı" proactive warning.
        """
        if not hasattr(self, "clinical_banner"):
            return
        if not self.current_patient:
            self.clinical_banner.hide()
            # v68: Show welcome card when no patient selected
            if hasattr(self, "welcome_card"):
                # v68-AI: Personalize with recent activity hint
                try:
                    self._refresh_welcome_card_personalized()
                except Exception as _ex:
                    _log_warning(
                        f"_refresh_welcome_card_personalized: {_ex}")
                # v68-AI: Show entire welcome container (welcome card +
                # big New Patient button) when no patient is selected
                if hasattr(self, "welcome_container"):
                    self.welcome_container.show()
                else:
                    self.welcome_card.show()
            return
        # v68: Hide welcome card when a patient is selected
        if hasattr(self, "welcome_container"):
            self.welcome_container.hide()
        elif hasattr(self, "welcome_card"):
            self.welcome_card.hide()

        # v68: Support a manual mode override. If the doctor clicked
        # "Jinekolojiye Geç" / "Obstetriğe Geç" from the toolbar we
        # honour that choice instead of auto-detecting from the PDF.
        # The override is cleared whenever the selected patient changes.
        mode_override = getattr(self, "_mode_override", None)

        # v68: Gynecologic patients get a simplified pink banner with just
        # their name + age + "🌸 Jinekolojik Takip" chip — GA/EDD don't
        # apply. The doctor still sees the patient name prominently and
        # the visit date chip, but we don't pretend to show pregnancy data.
        try:
            if mode_override == "gynecologic":
                is_gyn = True
            elif mode_override == "obstetric":
                is_gyn = False
            else:
                is_gyn = is_gynecologic_patient(self.current_patient)
            if is_gyn:
                self._render_gynecologic_banner()
                return
        except Exception as _ex:
            _log_warning("clinical banner: gyn check", exc=_ex)

        # Back to obstetric — reset style so if we came from gyn the
        # blue gradient is properly restored.
        self._apply_obstetric_banner_style()

        # Collect what we can from the latest PDF. We try the currently-
        # selected visit's PDF first; if no visit is selected (or its PDF
        # can't be parsed) we fall back to the most recent PDF we can find
        # across all of the patient's visits. This makes the clinical banner
        # useful the moment a patient is selected, without requiring the
        # doctor to also click a specific visit first.
        ga_days = None          # "snapshot" GA — GA at the time of the scan
        edd_str = ""
        edd_dt = None
        is_twin = False
        try:
            if self.current_subfolder:
                pdf = get_latest_pdf_in_folder(self.current_subfolder)
                if pdf:
                    data = parse_pdf_summary_data(pdf)
                    ga_days = data.get("ga_days")
                    edd_str = data.get("edd") or ""
                    edd_dt = data.get("edd_dt")
                    is_twin = data.get("is_twin", False)
        except Exception as _ex:
            _log_warning("clinical banner: primary PDF parse failed",
                         exc=_ex)

        # Fallback: no visit selected (or current-visit PDF gave nothing
        # useful) — scan all visits for the newest PDF.
        if edd_dt is None and self.current_patient is not None:
            try:
                visits = get_subfolders(self.current_patient)  # newest first
                for v in visits:
                    p = get_latest_pdf_in_folder(v)
                    if not p:
                        continue
                    d = parse_pdf_summary_data(p)
                    if d.get("edd_dt") or d.get("ga_days"):
                        if ga_days is None:
                            ga_days = d.get("ga_days")
                        if not edd_str:
                            edd_str = d.get("edd") or ""
                        if edd_dt is None:
                            edd_dt = d.get("edd_dt")
                        if not is_twin:
                            is_twin = d.get("is_twin", False)
                        break
            except Exception as _ex:
                _log_warning("clinical banner: fallback visit scan failed",
                             exc=_ex)

        # GA as W+D — this is the SNAPSHOT GA from the PDF, kept for display
        # continuity. The 36-week WARNING below uses a different value
        # (today's GA), because the snapshot can be weeks old.
        ga_str = "—"
        if isinstance(ga_days, (int, float)) and ga_days > 0:
            w = int(ga_days) // 7
            d = int(ga_days) % 7
            ga_str = f"{w}<sup>+{d}</sup> hafta"

        # Today's GA (computed from EDD rather than snapshot). EDD = LMP +
        # 280 days is a constant, so today's GA = 280 − (edd − today).days.
        # This is what the 36-week strip check must use — otherwise a
        # patient whose last PDF was at 34w+0d three weeks ago would never
        # trigger the warning even though they're currently at 37 weeks.
        current_ga_weeks: Optional[int] = None
        if isinstance(edd_dt, datetime):
            days_to_edd = (edd_dt.date() - datetime.now().date()).days
            current_ga_days = 280 - days_to_edd
            if 0 < current_ga_days <= 300:   # sanity: 0-300 days
                current_ga_weeks = current_ga_days // 7

        # Is this a C-section–flagged patient?
        patient_key = self.active_patient_key() or ""
        is_cs = is_c_section_planned(patient_key)

        # Days to EDD / planned delivery. When C-section flag is set we
        # show BOTH: the scheduled date (EDD − 14) is the one the doctor
        # plans around, the raw EDD is shown for reference.
        edd_part = "—"
        if edd_str:
            edd_part = edd_str
            if isinstance(edd_dt, datetime):
                if is_cs:
                    pdd_dt = planned_delivery_date(patient_key, edd_dt)
                    if pdd_dt is not None:
                        delta_pdd = (pdd_dt.date() - datetime.now().date()).days
                        pdd_str = pdd_dt.strftime("%d.%m.%Y")
                        if delta_pdd > 0:
                            edd_part = (f"🩺 {pdd_str} ({delta_pdd} gün, C/S)"
                                        f" · 40-hf {edd_str}")
                        elif delta_pdd == 0:
                            edd_part = (f"🩺 {pdd_str} (BUGÜN, C/S!)"
                                        f" · 40-hf {edd_str}")
                        else:
                            edd_part = (f"🩺 {pdd_str} ({-delta_pdd} gün geçti,"
                                        f" C/S) · 40-hf {edd_str}")
                else:
                    delta = (edd_dt.date() - datetime.now().date()).days
                    if delta > 0:
                        edd_part = f"{edd_str} ({delta} gün)"
                    elif delta == 0:
                        edd_part = f"{edd_str} (BUGÜN!)"
                    else:
                        edd_part = f"{edd_str} ({-delta} gün geçti)"

        # Last visit — how many days ago
        last_visit_part = "—"
        try:
            last_d = get_patient_last_visit_date(self.current_patient)
            if last_d:
                days_ago = (datetime.now().date() - last_d.date()).days
                if days_ago == 0:
                    last_visit_part = "Bugün"
                elif days_ago == 1:
                    last_visit_part = "Dün"
                elif days_ago < 7:
                    last_visit_part = f"{days_ago} gün önce"
                elif days_ago < 30:
                    last_visit_part = f"{days_ago // 7} hafta önce"
                else:
                    last_visit_part = f"{days_ago} gün önce"
        except Exception as _ex:
            _log_warning("clinical banner: computing last-visit age failed",
                         exc=_ex)

        # Blood type / Rh from demographics
        demo = {}
        try:
            demo = load_patient_demographics(self.active_patient_key())
        except Exception as _ex:
            _log_warning("clinical banner: load_patient_demographics failed",
                         exc=_ex)
        blood_str = ""
        if demo.get("blood_type") or demo.get("rh_factor"):
            bt = demo.get("blood_type") or "?"
            rh = demo.get("rh_factor") or ""
            rh_sign = {"positive": "+", "negative": "-", "+": "+", "-": "-"}.get(rh, "")
            blood_str = f"{bt}{rh_sign}"

        # G/P/A/L
        gpal_str = ""
        g = demo.get("gravida"); p = demo.get("para")
        a = demo.get("abortus"); l = demo.get("living")
        if any(x is not None for x in (g, p, a, l)):
            gpal_str = (f"G{g if g is not None else '?'}"
                        f"P{p if p is not None else '?'}"
                        f"A{a if a is not None else '?'}"
                        f"L{l if l is not None else '?'}")

        # ── Birth-outcome check (highest priority strip) ─────────────────
        # If the doctor has marked dogum_normal or dogum_sezaryan on this
        # patient, the pregnancy is closed — show a GREEN strip with the
        # outcome instead of computing GA-based delivery warnings. This
        # prevents the banner from saying "DOĞUM ZAMANI" weeks/months
        # after the actual delivery.
        outcome_strip = ""
        outcome_notes = ""
        try:
            patient_flags = get_patient_flags(patient_key) if patient_key else {}
        except Exception as _ex:
            _log_warning("clinical banner: get_patient_flags failed", exc=_ex)
            patient_flags = {}

        for outcome_key in _BIRTH_OUTCOME_FLAG_KEYS:
            data = patient_flags.get(outcome_key)
            if data and data.get("value") == "1":
                if outcome_key == "dogum_sezaryan":
                    label = "SEZARYEN İLE DOĞUM YAPILDI"
                else:
                    label = "DOĞUM YAPILDI (normal vajinal)"
                detail = (data.get("notes") or "").strip()
                # Truncate detail for banner; full text in tooltip
                detail_inline = (f" — {detail[:60]}"
                                 + ("..." if len(detail) > 60 else "")
                                 if detail else "")
                fg, bg = "#0B5D0B", "#E5F1E5"
                outcome_strip = (
                    f"<span style='background-color:{bg};color:{fg};"
                    f"font-weight:800;font-size:15px;'>"
                    f"&nbsp; 🎉 {label}{detail_inline} &nbsp;"
                    f"</span>&nbsp;&nbsp;")
                outcome_notes = detail
                break

        # ── 42-week postterm auto-detect ─────────────────────────────────
        # If no outcome flag is set AND the computed GA is ≥ 42 weeks, the
        # patient is past term with no recorded delivery. Two interpretations:
        #   (a) doctor forgot to set dogum_* flag — most common case
        #   (b) lost to follow-up / delivered elsewhere
        # Either way the banner should NOT say "DOĞUM ZAMANI" anymore — it
        # should switch to a darker red "POSTTERM — gebelik bitti?" strip
        # that prompts the doctor to either record the outcome or set
        # `dogum_postterm` to acknowledge the unknown status.
        postterm_auto = (
            outcome_strip == "" and
            current_ga_weeks is not None and
            current_ga_weeks >= WEEK_POSTTERM
        )

        # ── 36+ week proactive warning ───────────────────────────────────
        # When GA ≥ 36 weeks, prepend an orange "doğuma hazırlık" strip.
        # Above 38 (for C-section) or 40 (for normal), it escalates to red.
        # Suppressed entirely if a birth outcome flag is set (closed pregnancy).
        #
        # Styling approach: we use BOTH a dark foreground colour AND a light
        # tinted background-color. QLabel RichText renders `color`, `font-*`,
        # and `background-color` on inline spans reliably, but `padding`,
        # `border-radius` and the shorthand `background:` / `font:` forms
        # are silently ignored. The fallback is a bold, uppercase, emoji-
        # led phrase in a saturated colour — readable even if every CSS
        # property above is dropped by the renderer.
        term_warning = ""
        if outcome_strip:
            # Pregnancy closed — no GA warning at all
            pass
        elif postterm_auto:
            # GA ≥ 42 weeks with no recorded delivery — strongest red alert
            fg, bg = "#8B0000", "#FFD0D0"
            term_warning = (
                f"<span style='background-color:{bg};color:{fg};"
                f"font-weight:800;font-size:15px;'>"
                f"&nbsp; ⛔ POSTTERM — {current_ga_weeks}+ HAFTA — "
                f"GEBELİK BİTTİ Mİ? &nbsp;"
                f"</span>&nbsp;&nbsp;")
        elif current_ga_weeks is not None and current_ga_weeks >= WEEK_EARLY_WARNING:
            # Decide severity. C-section patients are "overdue" at 38+,
            # normal at 40+; otherwise the strip is a milder "hazırlık" note.
            overdue_threshold = WEEK_CSECTION_TARGET if is_cs else WEEK_NORMAL_TARGET
            if current_ga_weeks >= overdue_threshold:
                # Past expected delivery point — dark red text on light red
                fg, bg = "#C42B1C", "#FFE5E5"
                icon = "⚠"
                tail = "SEZARYEN ZAMANI" if is_cs else "DOĞUM ZAMANI"
                term_warning = (
                    f"<span style='background-color:{bg};color:{fg};"
                    f"font-weight:800;font-size:15px;'>"
                    f"&nbsp; {icon} {current_ga_weeks}+ HAFTA — {tail} &nbsp;"
                    f"</span>&nbsp;&nbsp;")
            else:
                # 36-37 weeks (or 36-39 for C-section) — dark orange text on
                # light orange
                fg, bg = "#B45500", "#FFF0E0"
                icon = "📅"
                tail = "sezaryen planı hazırlığı" if is_cs else "doğum hazırlığı"
                term_warning = (
                    f"<span style='background-color:{bg};color:{fg};"
                    f"font-weight:700;font-size:14px;'>"
                    f"&nbsp; {icon} {current_ga_weeks}+ HAFTA — {tail} &nbsp;"
                    f"</span>&nbsp;&nbsp;")

        # Build HTML
        twin_icon = "👶👶 " if is_twin else ""
        # Outcome strip takes precedence — it's the first thing shown.
        parts = []

        # v68: Visit date/time chip — moved INTO the main banner so the
        # separate light-blue "Geliş:" strip could be removed, freeing
        # vertical space for the PDF pane. Small muted style so it
        # doesn't compete with the patient name.
        try:
            if getattr(self, "current_subfolder", None) is not None:
                _visit_name = format_visit_name(self.current_subfolder.name)
                if _visit_name:
                    parts.append(
                        f"<span style='font-size:11px;font-weight:500;"
                        f"opacity:0.82;'>📅 {_visit_name}</span>"
                        f"  <span style='opacity:0.45;'>•</span>  ")
        except Exception as _ex:
            _log_warning("clinical_banner: visit date chip", exc=_ex)

        # Patient name — first thing the doctor should see at a glance.
        # Bold, slightly smaller than GA but large enough to read across
        # the room. Uses format_patient_name for proper "Soyad, Ad" → "Ad Soyad".
        try:
            pname = format_patient_name(self.current_patient.name)
            if pname:
                parts.append(
                    f"<span style='font-size:18px;font-weight:700;'>"
                    f"{pname}</span>"
                    f"  <span style='opacity:0.6;'>|</span>  ")
        except Exception as _ex:
            _log_warning("clinical_banner: format_patient_name", exc=_ex)
        if outcome_strip:
            parts.append(outcome_strip)
        if term_warning:
            parts.append(term_warning)
        # When pregnancy is closed, GA loses its meaning (it's the GA at
        # delivery, in the past). Hide GA + EDD for cleaner display.
        if not outcome_strip:
            parts.append(
                f"<span style='font-size:22px;font-weight:800;'>"
                f"{twin_icon}{ga_str}</span>")
        sep = "  <span style='opacity:0.6;'>|</span>  "
        # EDD line is meaningless once delivered. For closed pregnancies
        # show "Doğum tarihi: ..." (parsed from outcome notes if present)
        # rather than the predicted EDD.
        if outcome_strip:
            # Try to extract a date from the outcome notes (DD.MM.YYYY)
            import re as _re
            date_match = _re.search(r'\b(\d{1,2}[./]\d{1,2}[./]\d{4})\b',
                                    outcome_notes)
            if date_match:
                parts.append(sep + f"<b>Doğum:</b> {date_match.group(1)}")
        else:
            parts.append(sep + f"<b>EDD:</b> {edd_part}")
        parts.append(sep + f"<b>Son geliş:</b> {last_visit_part}")
        if blood_str:
            parts.append(sep + f"<b>Kan:</b> {blood_str}")
        if gpal_str:
            parts.append(sep + f"<b>{gpal_str}</b>")

        self.clinical_banner.setText("".join(parts))
        # Diagnostic tooltip: lets the doctor hover the banner to see why
        # the "36+ hafta" strip does or doesn't render. Useful when the
        # strip is unexpectedly missing — the tooltip shows the raw values
        # that drove the decision.
        try:
            tooltip_lines = [
                "— Klinik banner tanılama —",
                f"snapshot GA (PDF'ten): {ga_days} gün" if ga_days is not None else "snapshot GA: yok (PDF'ten alınamadı)",
                f"bugünkü GA (EDD'den): {current_ga_weeks} hafta" if current_ga_weeks is not None else "bugünkü GA: yok (EDD yok)",
                f"EDD: {edd_str or '-'}",
                f"Sezaryen planı: {'evet' if is_cs else 'hayır'}",
                f"Doğum eşiği: {'38 hafta (C/S)' if is_cs else '40 hafta (normal)'}",
            ]
            if outcome_strip:
                tooltip_lines.append(
                    f"DURUM: gebelik sonuçlandı (outcome flag set)")
                if outcome_notes:
                    tooltip_lines.append(f"Doğum notu: {outcome_notes}")
            elif postterm_auto:
                tooltip_lines.append(
                    "DURUM: 42+ hf, doğum bayrağı yok — postterm uyarısı")
            tooltip_lines.append("Şerit: " + (
                    "doğum sonuçlandı şeridi"
                    if outcome_strip else
                    "postterm şeridi"
                    if postterm_auto else
                    "gösterilmiyor (bugünkü GA < 36)"
                    if not term_warning and current_ga_weeks is not None
                    else "gösterilmiyor (EDD/GA hesaplanamadı)"
                    if not term_warning
                    else "gösteriliyor"))
            self.clinical_banner.setToolTip("\n".join(tooltip_lines))
        except Exception as _ex:
            _log_warning("MainWindow._update_clinical_banner", exc=_ex)
        self.clinical_banner.show()
