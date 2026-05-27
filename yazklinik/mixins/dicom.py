"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _DicomMixin
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

class _DicomMixin:
    """MainWindow methods related to Dicom. Mixed into MainWindow via MRO."""

    def _show_orthanc_settings_dialog(self):
        """Dialog for entering Orthanc DICOM server connection details.
        Settings are persisted in QSettings so the doctor only needs to
        enter them once. Reconnects the client immediately on save."""
        s = self._settings
        cur_url = s.value("orthanc/url", ORTHANC_URL) or ORTHANC_URL
        cur_user = s.value("orthanc/user", ORTHANC_USER) or ORTHANC_USER
        cur_pass = s.value("orthanc/pass", ORTHANC_PASS) or ORTHANC_PASS

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("Orthanc DICOM Sunucu Ayarları")
        dlg.resize(520, 340)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(8)

        title = QLabel(
            "<h3 style='margin:0;color:#005A9E'>🩻 Orthanc DICOM Sunucusu</h3>"
            "<p style='color:#606060;margin:4px 0 0 0;font-size:11px;'>"
            "Sunucu bilgilerini girin — bir kez kaydedilir, tekrar sorulmaz.</p>")
        title.setTextFormat(Qt.RichText)
        v.addWidget(title)

        # URL parse into IP + port for easier editing
        import re as _re
        ip_default = "192.168.1.100"
        port_default = "8042"
        try:
            m = _re.match(r"https?://([^:/]+)(?::(\d+))?", cur_url)
            if m:
                ip_default = m.group(1)
                port_default = m.group(2) or "8042"
        except Exception as _ex:
            _log_warning("MainWindow._show_orthanc_settings_dialog", exc=_ex)

        grid = QGridLayout()
        grid.setContentsMargins(8, 8, 8, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)

        grid.addWidget(QLabel("<b>IP adresi / Host:</b>"), 0, 0)
        ip_in = QLineEdit(ip_default)
        ip_in.setPlaceholderText("Örn: 192.168.1.100")
        grid.addWidget(ip_in, 0, 1)

        grid.addWidget(QLabel("<b>Port:</b>"), 1, 0)
        port_in = QLineEdit(port_default)
        port_in.setPlaceholderText("8042")
        port_in.setMaximumWidth(100)
        grid.addWidget(port_in, 1, 1, alignment=Qt.AlignLeft)

        grid.addWidget(QLabel("<b>Kullanıcı adı:</b>"), 2, 0)
        user_in = QLineEdit(cur_user)
        user_in.setPlaceholderText("admin")
        grid.addWidget(user_in, 2, 1)

        grid.addWidget(QLabel("<b>Şifre:</b>"), 3, 0)
        pass_in = QLineEdit(cur_pass)
        pass_in.setEchoMode(QLineEdit.Password)
        pass_in.setPlaceholderText("••••••••")
        grid.addWidget(pass_in, 3, 1)

        v.addLayout(grid)

        status_lbl = QLabel("")
        status_lbl.setWordWrap(True)
        status_lbl.setStyleSheet("color:#606060;font:500 11px 'Segoe UI';padding:4px;")
        v.addWidget(status_lbl)

        # Test button — runs `is_available()` on a worker so the dialog
        # stays responsive (a bad host would otherwise freeze for the full
        # 5s timeout).
        def _test():
            url = f"http://{ip_in.text().strip()}:{port_in.text().strip()}"
            status_lbl.setStyleSheet("color:#606060;font:500 11px;padding:4px;")
            status_lbl.setText("⏳ Bağlanılıyor...")
            test_btn.setEnabled(False)

            # Capture current form values up-front. The callable runs on a
            # worker thread and must NOT touch QLineEdit widgets.
            test_client = OrthancClient(
                base_url=url,
                username=user_in.text().strip(),
                password=pass_in.text(),
                timeout=5.0)

            def _on_done(ok):
                test_btn.setEnabled(True)
                if ok:
                    status_lbl.setStyleSheet(
                        "color:#107C10;font:600 11px;padding:4px;")
                    status_lbl.setText(
                        "✓ Bağlantı başarılı! Kaydet'e tıklayarak ayarları kaydedin.")
                else:
                    status_lbl.setStyleSheet(
                        "color:#C42B1C;font:600 11px;padding:4px;")
                    status_lbl.setText(
                        "✗ Sunucuya ulaşılamadı. IP/port/kimlik bilgilerini kontrol edin.")

            def _on_error(ex):
                test_btn.setEnabled(True)
                status_lbl.setStyleSheet(
                    "color:#C42B1C;font:600 11px;padding:4px;")
                status_lbl.setText(f"✗ Hata: {ex}")

            task = BackgroundTask(test_client.is_available,
                                  description="orthanc-test")
            task.finished.connect(_on_done)
            task.error.connect(_on_error)
            task.start()

        btn_row = QHBoxLayout()
        test_btn = QPushButton("🔌 Bağlantıyı Test Et")
        test_btn.clicked.connect(_test)
        save_btn = QPushButton("💾 Kaydet")
        save_btn.setStyleSheet(
            "QPushButton{background:#107C10;color:white;padding:8px 20px;"
            "font:600 12px;border:none;border-radius:3px;}"
            "QPushButton:hover{background:#0B5D0B;}")
        cancel_btn = QPushButton("İptal")
        cancel_btn.setShortcut("Escape")

        def _save():
            ip = ip_in.text().strip()
            port = port_in.text().strip() or "8042"
            if not ip:
                QMessageBox.warning(dlg, "Eksik Bilgi", "IP adresi gerekli.")
                return
            url = f"http://{ip}:{port}"
            s.setValue("orthanc/url", url)
            s.setValue("orthanc/user", user_in.text().strip())
            s.setValue("orthanc/pass", pass_in.text())
            # Reconnect client with new settings
            try:
                self.orthanc = OrthancClient(
                    base_url=url,
                    username=user_in.text().strip(),
                    password=pass_in.text(),
                    timeout=ORTHANC_TIMEOUT_SEC)
                self._orthanc_connected = None  # re-probe
                self._check_orthanc_connection()
            except Exception as ex:
                _log_warning(f"Orthanc reconnect failed: {ex}")
            self.statusBar().showMessage(
                "✓ Orthanc ayarları kaydedildi", 4000)
            dlg.accept()

        save_btn.clicked.connect(_save)
        cancel_btn.clicked.connect(dlg.reject)

        btn_row.addWidget(test_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        v.addLayout(btn_row)

        dlg.exec()

    def _build_tab_dicom(self) -> QWidget:
        """Dedicated DICOM (Orthanc PACS) browser tab.

        Shows the connection status, refresh control, and a thumbnail grid of
        the currently selected patient's DICOM previews. Click any thumbnail
        to open the same large-preview dialog as the regular Images tab —
        from there the doctor can add to PDF or print.
        """
        page = QWidget()
        page.setObjectName("TabPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Header row: title + status badge + refresh + count
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        dtitle = QLabel("📡  DICOM Görüntüleri")
        dtitle.setObjectName("BoxTitle")
        hdr.addWidget(dtitle)

        self.orthanc_status_lbl = QLabel("⚪ Bağlanıyor...")
        self.orthanc_status_lbl.setStyleSheet(
            "color:#606060;font:600 11px 'Segoe UI';"
            "background:#F0F0F0;border:1px solid #C8C8C8;padding:3px 10px;")
        self.orthanc_status_lbl.setToolTip("Orthanc DICOM sunucusu bağlantı durumu")
        hdr.addWidget(self.orthanc_status_lbl)

        hdr.addStretch()

        self.orthanc_refresh_btn = QPushButton("↻ Yenile")
        self.orthanc_refresh_btn.setObjectName("MiniBtn")
        self.orthanc_refresh_btn.setCursor(Qt.PointingHandCursor)
        self.orthanc_refresh_btn.setToolTip(
            "Önbellekle hızlı yükle + Orthanc'tan değişiklik kontrol et")
        self.orthanc_refresh_btn.clicked.connect(self._refresh_dicom_for_patient)
        hdr.addWidget(self.orthanc_refresh_btn)

        # Force refresh — bypasses cache entirely, useful if cache is stale
        self.orthanc_force_btn = QPushButton("⟳ Yeniden İndir")
        self.orthanc_force_btn.setObjectName("MiniBtn")
        self.orthanc_force_btn.setCursor(Qt.PointingHandCursor)
        self.orthanc_force_btn.setToolTip(
            "Önbelleği atla, DICOM'ları Orthanc'tan baştan indir")
        self.orthanc_force_btn.clicked.connect(self._force_refresh_dicom)
        hdr.addWidget(self.orthanc_force_btn)

        # v68-UI: Save DICOM + JPG images to the patient's visit folder
        # on NAS. Useful for offline access / documentation / sharing
        # via WhatsApp.
        self.orthanc_save_btn = QPushButton("💾 Hastaya Kaydet")
        self.orthanc_save_btn.setObjectName("MiniBtn")
        self.orthanc_save_btn.setCursor(Qt.PointingHandCursor)
        self.orthanc_save_btn.setToolTip(
            "Bu hastanın Orthanc'taki DICOM görüntülerini + JPG "
            "önizlemelerini seçili gelişin klasörüne kopyala. "
            "Multi-frame loop'lar da kare kare JPG olarak çıkarılır.")
        self.orthanc_save_btn.clicked.connect(
            self._save_dicom_to_patient_folder)
        hdr.addWidget(self.orthanc_save_btn)

        # v68-UI: Manual Orthanc match — useful when the NAS folder
        # name doesn't match the DICOM patient name (typos, different
        # spellings, TC vs. full name, etc.)
        self.orthanc_match_btn = QPushButton("🔗 Eşleştir")
        self.orthanc_match_btn.setObjectName("MiniBtn")
        self.orthanc_match_btn.setCursor(Qt.PointingHandCursor)
        self.orthanc_match_btn.setToolTip(
            "NAS klasör adıyla Orthanc hastası otomatik eşleşmiyorsa, "
            "bu butonla manuel bağlantı kur: Orthanc'taki tüm "
            "hastalarda ara, doğru olanı seç. Bir kez eşleşince "
            "program hatırlar, bir daha arama yapmaz.")
        self.orthanc_match_btn.clicked.connect(
            self._show_orthanc_match_dialog)
        hdr.addWidget(self.orthanc_match_btn)

        # v68-UI: Open the patient's page in Orthanc's web UI
        # (Osimis Viewer, Stone Viewer, or plain Explorer — whichever
        # plugin is configured on the server). Useful for advanced
        # DICOM tools the native app doesn't expose.
        self.orthanc_web_btn = QPushButton("🌐 Web'de Aç")
        self.orthanc_web_btn.setObjectName("MiniBtn")
        self.orthanc_web_btn.setCursor(Qt.PointingHandCursor)
        self.orthanc_web_btn.setToolTip(
            "Bu hastanın Orthanc sayfasını tarayıcıda aç.\n"
            "Plugin'ler (Osimis, Stone Web Viewer, Explorer 2) "
            "üzerinden gelişmiş DICOM görüntüleme / ölçüm / "
            "multi-planar reformat vb. işlemler yapılabilir.")
        self.orthanc_web_btn.clicked.connect(
            self._open_patient_in_orthanc_web)
        hdr.addWidget(self.orthanc_web_btn)

        # v68: Cine player — opens a DICOM file in the built-in multiframe
        # viewer. Useful for ultrasound cine loops (multiframe DICOM)
        # that can't be viewed as still images.
        self.dicom_cine_btn = QPushButton("🎬 Cine Oynat")
        self.dicom_cine_btn.setObjectName("MiniBtn")
        self.dicom_cine_btn.setCursor(Qt.PointingHandCursor)
        self.dicom_cine_btn.setToolTip(
            "Bir DICOM dosyası seçip cine (video) oynatıcıda aç. "
            "Multiframe loop'ları tam hızında oynatır; tek frame "
            "dosyalar still image olarak görünür.")
        self.dicom_cine_btn.clicked.connect(self._open_dicom_cine_dialog)
        hdr.addWidget(self.dicom_cine_btn)

        # v68: Weasis external viewer — for advanced DICOM features that
        # our built-in cine player can't do (3D volumetric rendering,
        # doppler colour flow, MPR, advanced measurements). Requires
        # Weasis to be installed (https://weasis.org — free, open-source,
        # cross-platform). If not installed, the button shows the
        # install instructions instead of launching.
        self.dicom_weasis_btn = QPushButton("🩻 Weasis'te Aç")
        self.dicom_weasis_btn.setObjectName("MiniBtn")
        self.dicom_weasis_btn.setCursor(Qt.PointingHandCursor)
        self.dicom_weasis_btn.setToolTip(
            "Seçili DICOM'u Weasis (profesyonel DICOM viewer) ile aç. "
            "Weasis kurulu değilse kurulum adresini gösterir. "
            "Orthanc web viewer alternatif olarak tarayıcıda da açılabilir.")
        self.dicom_weasis_btn.clicked.connect(self._open_in_weasis)
        hdr.addWidget(self.dicom_weasis_btn)

        # v68: Measurement extractor — parses DICOM SR + private tags
        # and shows numeric measurements (BPD, HC, AC, FL, EFW, follicle
        # diameter, endometrial thickness, etc) in a copyable table.
        self.dicom_measure_btn = QPushButton("📐 Ölçümleri Çıkar")
        self.dicom_measure_btn.setObjectName("MiniBtn")
        self.dicom_measure_btn.setCursor(Qt.PointingHandCursor)
        self.dicom_measure_btn.setToolTip(
            "Seçili DICOM'daki ölçümleri (BPD, HC, AC, FL, EFW, folikül, "
            "endometrium) otomatik çıkarır — SR + Voluson private tag'leri "
            "parse eder, panoya kopyalayabilirsiniz.")
        self.dicom_measure_btn.clicked.connect(self._open_dicom_measurements)
        hdr.addWidget(self.dicom_measure_btn)

        self.dicom_count_lbl = QLabel("0 görüntü")
        self.dicom_count_lbl.setStyleSheet(
            "color:#606060;font:600 12px 'Segoe UI';padding:2px 8px;"
            "background:#F0F0F0;border:1px solid #C8C8C8;")
        hdr.addWidget(self.dicom_count_lbl)
        lay.addLayout(hdr)

        # Hint
        dhint = QLabel(
            "Hasta seçince Orthanc'tan DICOM görüntüleri otomatik listelenir."
            "   •   Bir görüntüye tıkla → büyük önizleme + PDF'e ekle / yazdır."
        )
        dhint.setStyleSheet(subtle_text_style(font_size=11, padding="2px"))
        dhint.setWordWrap(True)
        lay.addWidget(dhint)

        # Big scrollable grid
        self.dicom_scroll = QScrollArea()
        self.dicom_scroll.setObjectName("ImageScroll")
        self.dicom_scroll.setWidgetResizable(True)
        self.dicom_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.dicom_host = QWidget()
        self.dicom_host.setObjectName("GalleryHost")
        self.dicom_host.setStyleSheet("background:#EEF2F7;")
        self.dicom_grid = QGridLayout(self.dicom_host)
        self.dicom_grid.setContentsMargins(12, 12, 12, 12)
        self.dicom_grid.setSpacing(12)
        self.dicom_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.dicom_scroll.setWidget(self.dicom_host)

        # QStackedWidget: page 0 = thumbnails, page 1 = inline preview
        self.dicom_stack = QStackedWidget()
        self.dicom_stack.addWidget(self.dicom_scroll)
        lay.addWidget(self.dicom_stack, 1)

        self._dicom_preview_cache: dict = {}
        self._dicom_instance_ids: List[str] = []
        self._dicom_preview_paths: List[Path] = []
        return page

    def _check_orthanc_connection(self):
        """One-shot connectivity check at startup. Updates the status badge
        on the Images tab. Silently fails if requests library isn't present."""
        if self.orthanc is None or not REQUESTS_AVAILABLE:
            self._orthanc_connected = False
            self._update_orthanc_status(False, "Modül yok")
            return
        try:
            ok = self.orthanc.is_available()
        except Exception:
            ok = False
        self._orthanc_connected = ok
        self._update_orthanc_status(ok)
        if ok and self.current_patient is not None:
            # Patient already loaded at startup — fetch DICOM for them
            self._refresh_dicom_for_patient()

    def _update_orthanc_status(self, connected: bool, custom_text: str = ""):
        """Update the small badge on the Images tab."""
        if not hasattr(self, "orthanc_status_lbl"):
            return
        if connected:
            self.orthanc_status_lbl.setText("🟢 Bağlı")
            self.orthanc_status_lbl.setStyleSheet(
                "color:#107C10;font:600 10px 'Segoe UI';"
                "background:#E6F4E6;border:1px solid #107C10;padding:2px 8px;")
            self.orthanc_status_lbl.setToolTip(
                f"Orthanc sunucusuna bağlanıldı: {ORTHANC_URL}")
        else:
            label = "🔴 " + (custom_text or "Bağlantı yok")
            self.orthanc_status_lbl.setText(label)
            self.orthanc_status_lbl.setStyleSheet(
                "color:#C42B1C;font:600 10px 'Segoe UI';"
                "background:#FFF0F0;border:1px solid #C42B1C;padding:2px 8px;")
            self.orthanc_status_lbl.setToolTip(
                f"Orthanc'a bağlanılamadı: {ORTHANC_URL}\n"
                f"IP/port/kullanıcı/şifre bilgilerini yazklinik_v46.py "
                f"içinden kontrol edin.")

    def _clear_dicom_grid(self):
        """Remove any previous DICOM thumbnail buttons from the grid."""
        if not hasattr(self, "dicom_grid"):
            return
        while self.dicom_grid.count() > 0:
            it = self.dicom_grid.takeAt(0)
            w = it.widget() if it else None
            if w is not None:
                w.deleteLater()
        self._dicom_instance_ids = []
        self._dicom_preview_paths = []
        if hasattr(self, "dicom_count_lbl"):
            self.dicom_count_lbl.setText("0 görüntü")

    def _refresh_dicom_for_patient(self):
        """Called when a patient is selected (or Refresh button clicked).
        Uses a cache-first strategy:
        1. Load instances from DB cache immediately (instant display)
        2. Query Orthanc IN THE BACKGROUND to check for new data
        3. If anything changed, refresh the grid (on the main thread)

        This avoids the 5-10 second delay every time the doctor switches
        patient — the doctor sees DICOM images instantly from cache while
        the Orthanc check proceeds off the GUI thread."""
        self._clear_dicom_grid()

        if self.current_patient is None:
            self._show_dicom_message(
                "🔍 Bir hasta seçildiğinde DICOM görüntüleri burada listelenecek.")
            return

        patient_key = self.current_patient.name
        search_name = format_patient_name(patient_key)

        # ── STEP 1: Show cached data instantly (main thread, fast) ────────
        cached = db_get_cached_dicom(patient_key)
        if cached:
            last_sync = db_get_dicom_last_sync(patient_key)
            sync_age_str = ""
            if last_sync:
                delta = datetime.now() - last_sync
                if delta.total_seconds() < 60:
                    sync_age_str = "(az önce)"
                elif delta.total_seconds() < 3600:
                    sync_age_str = f"({int(delta.total_seconds() // 60)} dk önce)"
                elif delta.days < 1:
                    sync_age_str = f"({int(delta.total_seconds() // 3600)} saat önce)"
                else:
                    sync_age_str = f"({delta.days} gün önce)"

            self.statusBar().showMessage(
                f"📦 DICOM önbellekten yükleniyor {sync_age_str}...", 2000)
            # Convert cached rows into the format our grid population expects
            cached_instances = [(iid, study_date, jpeg_path)
                                for iid, study_date, jpeg_path in cached]
            self._populate_dicom_from_cache(cached_instances)

        # Check Orthanc connection for freshness check
        if not self._orthanc_connected:
            if not cached:
                cur_url = self._settings.value("orthanc/url", ORTHANC_URL) or ORTHANC_URL
                self._show_dicom_message(
                    f"⚠ Orthanc sunucusuna bağlanılamadı.\n\n"
                    f"Yapılandırılmış adres: {cur_url}\n\n"
                    f"Ayarları güncellemek için:\n"
                    f"Araçlar → 🩻 Orthanc DICOM Sunucu Ayarları")
            else:
                self.statusBar().showMessage(
                    "📦 Önbellekten gösteriliyor (Orthanc offline)", 3000)
            return

        # ── STEP 2: Query Orthanc in background ───────────────────────────
        if not cached:
            self.statusBar().showMessage(
                f"Orthanc'ta '{search_name}' aranıyor...", 2000)

        # Snapshot the orthanc client and the patient key so the worker
        # doesn't reach back into self. Capturing `self.orthanc` is safe
        # because OrthancClient is stateless per-call (each HTTP call is
        # self-contained).
        orthanc = self.orthanc

        def _worker():
            # Runs on a pool thread — MUST NOT touch Qt widgets. Returns a
            # plain dict with everything the main-thread slot needs. If an
            # HTTP error occurs the task's error signal fires; if no match
            # is found we return a dict with matches=[] and let the slot
            # render the "not found" message.
            matches = orthanc.find_patient_by_name(search_name)
            if not matches:
                parts = search_name.split()
                if len(parts) >= 2:
                    matches = orthanc.find_patient_by_name(
                        " ".join(reversed(parts)))
            if not matches:
                parts = search_name.split()
                if parts:
                    matches = orthanc.find_patient_by_name(parts[-1])

            if not matches:
                return {"matches": [], "studies": [], "all_instances": [],
                        "cache_rows": [], "orthanc_id": "",
                        "display_name": ""}

            patient = matches[0]
            orthanc_id = patient.get("ID", "")
            tags = patient.get("MainDicomTags", {})
            dicom_name = tags.get("PatientName", "?")
            display_name = OrthancClient.dicom_name_to_display(dicom_name)

            studies = orthanc.get_patient_studies(orthanc_id)

            all_instances: List[Tuple[str, str]] = []
            cache_rows: List[Tuple[str, str, str, str]] = []
            for s in studies:
                study_id = s.get("ID", "")
                study_date = s.get("MainDicomTags", {}).get("StudyDate", "")
                try:
                    inst_ids = orthanc.get_study_instances(study_id)
                    for iid in inst_ids:
                        all_instances.append((iid, study_date))
                        cache_rows.append((iid, study_id, study_date, ""))
                except Exception:
                    # Per-study failures are non-fatal — skip and continue
                    continue

            return {
                "matches": matches,
                "studies": studies,
                "all_instances": all_instances,
                "cache_rows": cache_rows,
                "orthanc_id": orthanc_id,
                "display_name": display_name,
            }

        def _on_done(result):
            # Stale-result guard: user may have switched patient while the
            # worker was still running. Compare against the captured key.
            if (self.current_patient is None
                    or self.current_patient.name != patient_key):
                return  # discard — result is for a patient that's no longer selected
            self._on_dicom_orthanc_success(
                patient_key=patient_key,
                search_name=search_name,
                cached=cached,
                result=result)

        def _on_error(ex):
            if (self.current_patient is None
                    or self.current_patient.name != patient_key):
                return
            _log_warning(f"Orthanc search failed for '{search_name}': {ex}")
            if not cached:
                self._show_dicom_message(f"❌ Arama hatası:\n{ex}")
            else:
                self.statusBar().showMessage(
                    f"⚠ Orthanc erişim hatası, önbellek gösteriliyor", 3000)

        self._run_bg(_worker, on_done=_on_done, on_error=_on_error,
                     description=f"orthanc-refresh:{patient_key}")

    def _on_dicom_orthanc_success(self, *, patient_key: str, search_name: str,
                                  cached: list, result: dict) -> None:
        """Main-thread continuation of _refresh_dicom_for_patient. Called
        after the background Orthanc query returns. Handles no-match case,
        writes new instances to the DB cache, and re-renders the grid if
        Orthanc returned a different set than what we already showed."""
        matches = result.get("matches") or []
        if not matches:
            if not cached:
                self._show_dicom_message(
                    f"🔍 Orthanc'ta '{search_name}' için eşleşme bulunamadı.\n\n"
                    f"Voluson'da hasta adı farklı yazılmış olabilir.\n"
                    f"↻ Yenile butonuyla tekrar deneyebilirsin.")
            return

        orthanc_id = result["orthanc_id"]
        display_name = result["display_name"]
        studies = result["studies"]
        all_instances = result["all_instances"]
        cache_rows = result["cache_rows"]

        self.statusBar().showMessage(
            f"Orthanc eşleşme: {display_name} — çalışmalar yükleniyor...", 2000)

        if not studies:
            self._show_dicom_message(
                f"Orthanc'ta hasta bulundu ({display_name}) ama çalışma yok.")
            return

        if not all_instances:
            if not cached:
                self._show_dicom_message(
                    f"Orthanc'ta çalışmalar bulundu ama görüntü yok.")
            return

        # Persist to DB cache so next time we load instantly
        try:
            db_upsert_dicom_instances(patient_key, orthanc_id, cache_rows)
        except Exception as ex:
            _log_warning(f"DICOM cache upsert failed: {ex}")

        # If the Orthanc results match what we already showed from cache,
        # skip the re-render to avoid UI flicker.
        new_ids = {iid for iid, _ in all_instances}
        cached_ids = {iid for iid, _, _ in cached}
        if cached and new_ids == cached_ids:
            self.statusBar().showMessage(
                f"✓ Orthanc senkron — {len(new_ids)} görüntü (değişiklik yok)",
                3000)
            return

        # Orthanc has different data → clear and re-render
        if cached:
            self._clear_dicom_grid()

        # Populate the grid with thumbnails — limit to first 50 to avoid lag
        LIMIT = 50
        shown = all_instances[:LIMIT]
        total = len(all_instances)
        self.dicom_count_lbl.setText(
            f"{total} görüntü" + (f" (ilk {LIMIT})" if total > LIMIT else ""))

        # ── Group by study date (geliş tarihi) ─────────────────────────────
        # Orthanc returns StudyDate as "YYYYMMDD". We group instances by date
        # so the grid shows a date header above each group's thumbnails.
        from collections import OrderedDict
        date_groups: "OrderedDict[str, List[str]]" = OrderedDict()
        for inst_id, study_date in shown:
            # Sort key: dates sort lexicographically when in YYYYMMDD format,
            # newest first means reverse sort. Use "" for unknown dates at end.
            key = study_date if study_date else "00000000"
            if key not in date_groups:
                date_groups[key] = []
            date_groups[key].append(inst_id)

        # Sort by date descending (newest first)
        sorted_keys = sorted(date_groups.keys(), reverse=True)

        def _fmt_date(yyyymmdd: str) -> str:
            """YYYYMMDD → GG.MM.YYYY; empty/invalid → 'Tarih bilinmiyor'."""
            if not yyyymmdd or yyyymmdd == "00000000" or len(yyyymmdd) != 8:
                return "📅 Tarih bilinmiyor"
            try:
                return (f"📅 {yyyymmdd[6:8]}.{yyyymmdd[4:6]}.{yyyymmdd[0:4]}")
            except Exception:
                return "📅 Tarih bilinmiyor"

        # Build the grid: date header row (span all cols) + image rows below
        cols = 5
        grid_row = 0
        instance_display_idx = 0  # tracks the _dicom_preview_paths index

        for date_key in sorted_keys:
            inst_ids = date_groups[date_key]
            if not inst_ids:
                continue

            # Date header — spans all columns
            header = QLabel(
                f"{_fmt_date(date_key)}  "
                f"<span style='color:#606060;font-weight:normal;'>"
                f"({len(inst_ids)} görüntü)</span>")
            header.setTextFormat(Qt.RichText)
            header.setStyleSheet(
                "background:#E5F1FB;color:#003A66;"
                "font:700 13px 'Segoe UI';padding:8px 12px;"
                "border:1px solid #A0C8E8;border-radius:3px;margin-top:4px;")
            self.dicom_grid.addWidget(header, grid_row, 0, 1, cols)
            grid_row += 1

            # Image thumbnails for this date
            col_in_row = 0
            # patient_key needed below for DB cache writes
            pkey_for_cache = self.current_patient.name if self.current_patient else ""
            for inst_id in inst_ids:
                try:
                    jpeg_path = self._dicom_tmp_dir / f"{inst_id}.jpg"
                    if not jpeg_path.exists():
                        jpeg_bytes = self.orthanc.get_instance_preview_bytes(inst_id)
                        if not jpeg_bytes:
                            continue
                        with open(jpeg_path, "wb") as f:
                            f.write(jpeg_bytes)

                    # Remember the JPEG path in DB cache so next time we
                    # skip the re-download and load directly from disk.
                    try:
                        db_set_dicom_jpeg_path(pkey_for_cache, inst_id,
                                               str(jpeg_path))
                    except Exception as _ex:
                        _log_warning("MainWindow._on_dicom_orthanc_success", exc=_ex)

                    self._dicom_instance_ids.append(inst_id)
                    self._dicom_preview_paths.append(jpeg_path)

                    pix = self._make_thumbnail(jpeg_path)
                    tile = ImageGalleryThumb(jpeg_path, pix)
                    current_idx = len(self._dicom_preview_paths) - 1
                    tile.clicked.connect(
                        lambda _c=False, i=current_idx: self._open_dicom_preview(i))

                    self.dicom_grid.addWidget(tile, grid_row, col_in_row)
                    col_in_row += 1
                    if col_in_row >= cols:
                        col_in_row = 0
                        grid_row += 1
                    instance_display_idx += 1
                except Exception as e:
                    _log_warning(f"DICOM thumb {inst_id} failed: {e}")
                    continue

                # Yield to UI every 10 thumbnails
                if instance_display_idx % 10 == 9:
                    QApplication.processEvents()

            # Move to next row after each date group (leave empty row as spacing)
            if col_in_row > 0:
                grid_row += 1
            grid_row += 1

        self.statusBar().showMessage(
            f"✓ Orthanc: {len(self._dicom_instance_ids)} DICOM görüntüsü, "
            f"{len(sorted_keys)} geliş tarihine göre sınıflandı", 4000)

    def _show_dicom_cache_status(self):
        """Dialog: show which patients have cached DICOM data + last sync.
        Lets the user see cache size and selectively invalidate it."""
        try:
            ensure_db()
        except Exception as ex:
            QMessageBox.critical(self, "DB Hatası",
                                 f"Veritabanına erişilemedi:\n{ex}")
            return

        try:
            with db_conn() as con:
                rows = con.execute(
                    "SELECT s.patient_key, s.last_synced_at, s.instance_count, "
                    "s.last_study_date "
                    "FROM dicom_sync_state s "
                    "ORDER BY s.last_synced_at DESC"
                ).fetchall()
        except Exception as ex:
            rows = []
            _log_warning(f"dicom cache status query failed: {ex}")

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("DICOM Önbellek Durumu")
        dlg.resize(640, 520)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)

        if not rows:
            info = QLabel(
                "<h3 style='color:#0078D4;margin-top:0;'>📊 DICOM Önbellek Boş</h3>"
                "<p style='color:#606060;'>Henüz hiç hastanın DICOM görüntüsü "
                "önbelleğe alınmadı.</p>"
                "<p>Bir hasta seçip DICOM sekmesine gittiğinizde "
                "görüntüler otomatik önbelleğe alınır ve sonraki açılışlarda "
                "anında yüklenir.</p>")
            info.setTextFormat(Qt.RichText)
            info.setWordWrap(True)
            v.addWidget(info)
        else:
            total_instances = sum(r[2] or 0 for r in rows)
            hdr = QLabel(
                f"<h3 style='color:#0078D4;margin-top:0;'>"
                f"📊 {len(rows)} hasta · {total_instances} görüntü önbelleğe alındı</h3>"
                f"<p style='color:#606060;font-size:11px;'>"
                f"Hasta seçildiğinde DICOM görüntüleri önbellekten anında yüklenir, "
                f"sonra Orthanc ile senkronize edilir.</p>")
            hdr.setTextFormat(Qt.RichText)
            hdr.setWordWrap(True)
            v.addWidget(hdr)

            # Table
            from PySide6.QtWidgets import QTableWidget, QTableWidgetItem
            tbl = QTableWidget()
            tbl.setColumnCount(4)
            tbl.setHorizontalHeaderLabels(
                ["Hasta", "Görüntü Sayısı", "Son Geliş", "Senkronize"])
            tbl.setRowCount(len(rows))
            tbl.setAlternatingRowColors(True)
            tbl.setEditTriggers(QTableWidget.NoEditTriggers)
            tbl.setSelectionBehavior(QTableWidget.SelectRows)
            tbl.setStyleSheet(
                "QTableWidget{background:#FFFFFF;border:1px solid #C8C8C8;}"
                "QHeaderView::section{background:#E5EEF7;font-weight:700;"
                "padding:6px;border:none;border-right:1px solid #C8C8C8;}")

            for i, (pkey, synced, count, study_date) in enumerate(rows):
                pname = format_patient_name(pkey)
                tbl.setItem(i, 0, QTableWidgetItem(pname))
                tbl.setItem(i, 1, QTableWidgetItem(str(count or 0)))
                # Format study date
                sd_str = "—"
                if study_date and len(study_date) == 8:
                    try:
                        sd_str = f"{study_date[6:8]}.{study_date[4:6]}.{study_date[0:4]}"
                    except Exception as _ex:
                        _log_warning("MainWindow._show_dicom_cache_status", exc=_ex)
                tbl.setItem(i, 2, QTableWidgetItem(sd_str))
                # Format sync time
                sync_str = "—"
                if synced:
                    try:
                        dt = datetime.fromisoformat(synced)
                        delta = datetime.now() - dt
                        if delta.total_seconds() < 60:
                            sync_str = "Az önce"
                        elif delta.total_seconds() < 3600:
                            sync_str = f"{int(delta.total_seconds() // 60)} dk önce"
                        elif delta.days < 1:
                            sync_str = f"{int(delta.total_seconds() // 3600)} saat önce"
                        else:
                            sync_str = f"{delta.days} gün önce"
                    except Exception:
                        sync_str = synced
                tbl.setItem(i, 3, QTableWidgetItem(sync_str))

            tbl.resizeColumnsToContents()
            tbl.horizontalHeader().setStretchLastSection(True)
            v.addWidget(tbl, 1)

        btn_row = QHBoxLayout()

        clear_btn = QPushButton("🗑 Tüm Önbelleği Sil")
        clear_btn.setStyleSheet(
            "QPushButton{background:#C42B1C;color:white;padding:8px 18px;"
            "border:none;border-radius:3px;font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:#8B1F14;}")
        clear_btn.setToolTip(
            "Tüm DICOM önbelleğini sil. Bir dahaki seferinde tekrar "
            "Orthanc'tan indirilecek.")

        def _clear_all():
            resp = QMessageBox.question(
                dlg, "Önbelleği Sil",
                f"{len(rows)} hastanın DICOM önbelleği silinecek.\n\n"
                f"(Orthanc sunucusundaki veriler SİLİNMEZ — sadece "
                f"yerel önbellek temizlenir.)\n\nDevam edilsin mi?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if resp != QMessageBox.Yes:
                return
            try:
                with db_conn() as con2:
                    con2.execute("DELETE FROM dicom_cache")
                    con2.execute("DELETE FROM dicom_sync_state")
                    con2.commit()
                self.statusBar().showMessage(
                    "✓ DICOM önbelleği temizlendi", 3000)
                dlg.accept()
            except Exception as ex:
                QMessageBox.critical(dlg, "Hata",
                                     f"Önbellek silinemedi:\n{ex}")

        clear_btn.clicked.connect(_clear_all)
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()

        close_btn = QPushButton("Kapat")
        close_btn.setShortcut("Escape")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        v.addLayout(btn_row)

        dlg.exec()

    def _open_dicom_measurements(self):
        """Let the doctor pick a DICOM file and pop up the extracted
        measurements in a table (BPD / HC / AC / FL / EFW / follicle /
        endometrial thickness, etc). Uses extract_dicom_measurements —
        SR first, then Voluson private tags, then ImageComments text.

        v68-UI: If no DICOM exists in the patient's visit folder yet,
        offers to fetch the most recent DICOM directly from Orthanc
        into a temp file and open that. This makes measurements
        accessible WITHOUT requiring the doctor to first "💾 Hastaya
        Kaydet" the DICOMs.
        """
        start_dir = ""
        try:
            if self.current_subfolder is not None:
                dcm_sub = self.current_subfolder / "DICOM"
                if dcm_sub.exists():
                    start_dir = str(dcm_sub)
                else:
                    start_dir = str(self.current_subfolder)
            elif self.current_patient is not None:
                start_dir = str(self.current_patient)
        except Exception as _ex:
            _log_warning("_open_dicom_measurements: start_dir", exc=_ex)

        # v68-UI: If the DICOM subfolder has no .dcm files but we have
        # an Orthanc connection, offer to fetch the latest scan from
        # Orthanc directly.
        has_local_dcm = False
        try:
            if self.current_subfolder is not None:
                dcm_sub = self.current_subfolder / "DICOM"
                if dcm_sub.exists():
                    for f in dcm_sub.iterdir():
                        if f.suffix.lower() in (".dcm", ".dicom"):
                            has_local_dcm = True
                            break
        except Exception as _ex:
            _log_warning(
                f"_open_dicom_measurements: local scan: {_ex}")

        if (not has_local_dcm
                and self.current_patient is not None
                and getattr(self, "_orthanc_connected", False)):
            # Offer to fetch from Orthanc
            ans = QMessageBox.question(
                self, "Ölçüm Çıkar",
                "Bu gelişin DICOM klasörü boş.\n\n"
                "Orthanc'tan en yeni görüntüyü indirip ölçüm "
                "çıkarmak ister misiniz?\n\n"
                "(Tam yerel kopya için önce '💾 Hastaya Kaydet' "
                "kullanabilirsiniz.)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes)
            if ans == QMessageBox.Yes:
                self._measure_latest_orthanc_dicom()
                return

        path_str, _ = QFileDialog.getOpenFileName(
            self, "Ölçüm çıkarılacak DICOM dosyası",
            start_dir,
            "DICOM Dosyaları (*.dcm *.dicom *.ima *.img);;Tüm Dosyalar (*.*)")
        if not path_str:
            return

        try:
            dlg = DicomMeasurementsDialog(Path(path_str), self)
            dlg.exec()
        except Exception as ex:
            _log_warning("_open_dicom_measurements: dialog", exc=ex)
            QMessageBox.critical(
                self, "Ölçüm Hatası",
                f"DICOM ölçümleri çıkarılamadı:\n\n{ex}")

    def _measure_latest_orthanc_dicom(self):
        """Download the most recent DICOM instance for the current
        patient from Orthanc into a temp file, then open the
        measurements dialog on it.

        v68-UI: Walks backwards from newest instance and tries each
        until we find one with extractable measurements. Uses the
        saved Orthanc ID when possible to skip the name search.
        """
        if self.current_patient is None:
            return
        patient_key = self.current_patient.name
        display_name = format_patient_name(patient_key)

        # Resolve Orthanc ID
        orthanc_id = db_get_orthanc_patient_id(patient_key)
        if not orthanc_id:
            try:
                matches = self.orthanc.find_patient_by_name(display_name)
                if not matches:
                    parts = display_name.split()
                    if len(parts) >= 2:
                        matches = self.orthanc.find_patient_by_name(
                            " ".join(reversed(parts)))
                if matches:
                    orthanc_id = matches[0].get("ID", "")
                    if orthanc_id:
                        db_set_orthanc_patient_id(
                            patient_key, orthanc_id)
            except Exception as _ex:
                _log_warning(
                    f"_measure_latest_orthanc_dicom: lookup: {_ex}")

        if not orthanc_id:
            QMessageBox.warning(
                self, "Ölçüm Çıkar",
                f"Orthanc'ta '{display_name}' bulunamadı.\n\n"
                f"'🔗 Eşleştir' ile manuel eşleme yapabilirsiniz.")
            return

        # Get newest study
        studies = self.orthanc.get_patient_studies(orthanc_id)
        if not studies:
            QMessageBox.information(
                self, "Ölçüm Çıkar",
                f"Bu hastanın Orthanc'ta hiç çalışması yok.")
            return

        newest_study = studies[0]  # already sorted newest first
        study_id = newest_study.get("ID", "")

        # Get all instances of the newest study
        inst_ids = self.orthanc.get_study_instances(study_id)
        if not inst_ids:
            QMessageBox.information(
                self, "Ölçüm Çıkar",
                "Görüntü bulunamadı.")
            return

        # Download the first instance (usually contains SR measurements
        # or Voluson private tags) — we could download all but for
        # measurements one representative file is usually enough.
        import tempfile
        self.statusBar().showMessage(
            "📥 Orthanc'tan DICOM indiriliyor...", 5000)
        QApplication.processEvents()

        # Try several instances in case the first has no measurements
        tmp_path = None
        for iid in inst_ids[:5]:  # try up to 5 instances
            try:
                dcm_bytes = self.orthanc.get_instance_dicom_bytes(iid)
                if not dcm_bytes:
                    continue
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".dcm", delete=False)
                tmp.write(dcm_bytes)
                tmp.close()
                tmp_path = Path(tmp.name)

                # Quick-check: does this instance have measurements?
                try:
                    result = extract_dicom_measurements(tmp_path)
                    if result.get("measurements"):
                        break  # Found a usable instance
                except Exception as _ex:
                    _log_warning(
                        f"_measure_latest_orthanc_dicom: check {iid}: {_ex}")
                # No measurements in this one — keep tmp for final fallback
            except Exception as _ex:
                _log_warning(
                    f"_measure_latest_orthanc_dicom: download {iid}: {_ex}")

        if not tmp_path or not tmp_path.exists():
            QMessageBox.warning(
                self, "Ölçüm Çıkar",
                "DICOM indirilemedi.")
            return

        # Open the measurements dialog — it will re-extract, which
        # may or may not find measurements depending on the file
        try:
            dlg = DicomMeasurementsDialog(tmp_path, self)
            dlg.exec()
        except Exception as ex:
            _log_warning(
                "_measure_latest_orthanc_dicom: dialog", exc=ex)
            QMessageBox.critical(
                self, "Ölçüm Hatası",
                f"DICOM ölçümleri çıkarılamadı:\n\n{ex}")
        finally:
            # Clean up temp file after dialog closes
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception as _ex:
                _log_warning(
                    f"_measure_latest_orthanc_dicom: tmp cleanup: {_ex}")

    def _open_in_weasis(self):
        """Launch Weasis (external DICOM viewer) with the selected file.

        Weasis is a free, open-source, cross-platform DICOM viewer that
        supports 3D MPR, doppler colour flow, advanced measurements,
        and Voluson proprietary tags out of the box. We don't bundle
        it — the doctor installs it once from https://weasis.org.

        Search path (Windows):
          1. Program Files / Program Files (x86) / Weasis
          2. LOCALAPPDATA / Weasis
          3. Available on PATH
        Falls back to showing install instructions if not found.
        """
        # Locate weasis executable
        weasis_exe = self._find_weasis()
        if weasis_exe is None:
            # Graceful guidance dialog — don't just error out
            dlg_msg = (
                "<h3 style='color:#005A9E'>🩻 Weasis Kurulu Değil</h3>"
                "<p><b>Weasis</b> profesyonel, açık kaynaklı DICOM viewer'dır. "
                "3D MPR, doppler, ileri ölçümler ve Voluson uyumluluğu sunar.</p>"
                "<p><b>Kurulum:</b><br>"
                "1. Tarayıcıda <a href='https://weasis.org/en/'>weasis.org</a> "
                "adresini aç<br>"
                "2. <b>Windows Installer</b>'ı indir ve kur<br>"
                "3. Kurulduktan sonra bu butonu tekrar deneyin</p>"
                "<p><b>Alternatif:</b> Orthanc sunucunuzun tarayıcı "
                "viewer'ını kullanabilirsiniz:<br>"
                "<code>http://&lt;orthanc-ip&gt;:8042/stone-webviewer/"
                "</code></p>")
            QMessageBox.information(
                self, "Weasis Bulunamadı", dlg_msg)
            return

        # Pick a DICOM file
        start_dir = ""
        try:
            if self.current_subfolder is not None:
                dcm_sub = self.current_subfolder / "DICOM"
                if dcm_sub.exists():
                    start_dir = str(dcm_sub)
                else:
                    start_dir = str(self.current_subfolder)
            elif self.current_patient is not None:
                start_dir = str(self.current_patient)
        except Exception as _ex:
            _log_warning("_open_in_weasis: start_dir", exc=_ex)

        path_str, _ = QFileDialog.getOpenFileName(
            self, "Weasis'te açılacak DICOM dosyası",
            start_dir,
            "DICOM Dosyaları (*.dcm *.dicom *.ima *.img);;Tüm Dosyalar (*.*)")
        if not path_str:
            return

        try:
            flags = 0x08000000 if os.name == "nt" else 0
            # Weasis CLI syntax: weasis -i <file>  OR  weasis <file>
            subprocess.Popen(
                [str(weasis_exe), "-i", path_str],
                creationflags=flags)
            self.statusBar().showMessage(
                f"✓ Weasis açılıyor — {Path(path_str).name}", 5000)
        except Exception as ex:
            _log_warning("_open_in_weasis: launch", exc=ex)
            QMessageBox.critical(
                self, "Weasis Hatası",
                f"Weasis başlatılamadı:\n\n{ex}")

    def _find_weasis(self) -> Optional[Path]:
        """Locate the Weasis executable on the current system. Returns
        the Path to the executable or None if not found."""
        candidates = []
        if os.name == "nt":
            # Common Windows install locations
            for env_var in ("ProgramFiles", "ProgramFiles(x86)",
                            "LOCALAPPDATA"):
                base = os.environ.get(env_var)
                if not base:
                    continue
                for subdir in ("Weasis", "weasis"):
                    for exe in ("Weasis.exe", "weasis.exe"):
                        p = Path(base) / subdir / exe
                        if p.exists():
                            candidates.append(p)
            # Check PATH too
            try:
                import shutil
                on_path = shutil.which("weasis") or shutil.which("Weasis")
                if on_path:
                    candidates.append(Path(on_path))
            except Exception as _ex:
                _log_warning("dicom_measurements", exc=_ex)
        else:
            # Linux/Mac
            for p in ("/usr/bin/weasis", "/usr/local/bin/weasis",
                      "/Applications/Weasis.app/Contents/MacOS/Weasis"):
                pp = Path(p)
                if pp.exists():
                    candidates.append(pp)
            try:
                import shutil
                on_path = shutil.which("weasis")
                if on_path:
                    candidates.append(Path(on_path))
            except Exception as _ex:
                _log_warning("dicom_measurements", exc=_ex)
        return candidates[0] if candidates else None

    def _open_dicom_cine_dialog(self):
        """Let the doctor pick a DICOM file and open it in the built-in
        cine player. Usual search locations tried in order:
          1. Currently-selected visit's DICOM sub-folder (if any)
          2. The patient's "DICOM" sub-folder
          3. Fallback: free QFileDialog

        v68-UI: If no local DICOM is available and Orthanc is
        connected, offers to fetch multi-frame cine loops directly
        from Orthanc for playback.
        """
        # Build a reasonable default directory for the file dialog
        start_dir = ""
        try:
            if self.current_subfolder is not None:
                dcm_sub = self.current_subfolder / "DICOM"
                if dcm_sub.exists():
                    start_dir = str(dcm_sub)
                else:
                    start_dir = str(self.current_subfolder)
            elif self.current_patient is not None:
                start_dir = str(self.current_patient)
        except Exception as _ex:
            _log_warning("_open_dicom_cine_dialog: start_dir", exc=_ex)

        # Check if the local DICOM subfolder has any multi-frame DICOMs.
        # If not, offer the Orthanc fetch fallback.
        has_local_dcm = False
        try:
            if self.current_subfolder is not None:
                dcm_sub = self.current_subfolder / "DICOM"
                if dcm_sub.exists():
                    for f in dcm_sub.iterdir():
                        if f.suffix.lower() in (".dcm", ".dicom"):
                            has_local_dcm = True
                            break
        except Exception as _ex:
            _log_warning(
                f"_open_dicom_cine_dialog: local scan: {_ex}")

        if (not has_local_dcm
                and self.current_patient is not None
                and getattr(self, "_orthanc_connected", False)):
            ans = QMessageBox.question(
                self, "Cine Oynat",
                "Bu gelişin DICOM klasörü boş.\n\n"
                "Orthanc'tan bir video/cine loop indirip oynatmak "
                "ister misiniz?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes)
            if ans == QMessageBox.Yes:
                self._play_orthanc_cine_dicom()
                return

        path_str, _ = QFileDialog.getOpenFileName(
            self, "DICOM dosyası seç",
            start_dir,
            "DICOM Dosyaları (*.dcm *.dicom *.ima *.img);;Tüm Dosyalar (*.*)")
        if not path_str:
            return

        path = Path(path_str)
        if not path.exists():
            QMessageBox.warning(
                self, "Dosya Yok",
                f"Seçili dosya bulunamadı:\n{path}")
            return

        try:
            dlg = DicomCinePlayer(path, self)
            # Non-modal so the doctor can scroll through multiple DICOMs
            # if they want — open() instead of exec() lets other windows
            # stay interactive. But we keep a reference so Qt doesn't GC it.
            if not hasattr(self, "_open_cine_players"):
                self._open_cine_players = []
            self._open_cine_players.append(dlg)
            # Clean the list when the player closes
            dlg.finished.connect(
                lambda _result, d=dlg: self._open_cine_players.remove(d)
                if d in self._open_cine_players else None)
            dlg.show()
        except Exception as ex:
            _log_warning("_open_dicom_cine_dialog: open player", exc=ex)
            QMessageBox.critical(
                self, "Cine Oynatıcı Hatası",
                f"DICOM dosyası açılamadı:\n\n{ex}")

    def _play_orthanc_cine_dicom(self):
        """Download a multi-frame DICOM from Orthanc to a temp file
        and open it in the cine player.

        v68-UI: Walks the newest study, finds instances with >1 frame
        (likely cine loops), lets the doctor pick one, downloads it,
        plays it. Temp file is cleaned up when the dialog closes.
        """
        if self.current_patient is None:
            return
        patient_key = self.current_patient.name
        display_name = format_patient_name(patient_key)

        # Resolve Orthanc ID
        orthanc_id = db_get_orthanc_patient_id(patient_key)
        if not orthanc_id:
            try:
                matches = self.orthanc.find_patient_by_name(display_name)
                if not matches:
                    parts = display_name.split()
                    if len(parts) >= 2:
                        matches = self.orthanc.find_patient_by_name(
                            " ".join(reversed(parts)))
                if matches:
                    orthanc_id = matches[0].get("ID", "")
                    if orthanc_id:
                        db_set_orthanc_patient_id(
                            patient_key, orthanc_id)
            except Exception as _ex:
                _log_warning(
                    f"_play_orthanc_cine_dicom: lookup: {_ex}")

        if not orthanc_id:
            QMessageBox.warning(
                self, "Cine Oynat",
                f"Orthanc'ta '{display_name}' bulunamadı.\n\n"
                f"'🔗 Eşleştir' ile manuel eşleme yapabilirsiniz.")
            return

        # Pick newest study
        studies = self.orthanc.get_patient_studies(orthanc_id)
        if not studies:
            QMessageBox.information(
                self, "Cine Oynat",
                "Bu hastanın Orthanc'ta hiç çalışması yok.")
            return

        self.statusBar().showMessage(
            "🔍 Video/cine loop aranıyor...", 4000)
        QApplication.processEvents()

        # Find multi-frame instances in the newest study
        newest_study = studies[0]
        study_id = newest_study.get("ID", "")
        inst_ids = self.orthanc.get_study_instances(study_id)

        cine_instances = []  # [(iid, frame_count), ...]
        for iid in inst_ids:
            try:
                nframes = self.orthanc.get_instance_frame_count(iid)
                if nframes > 1:
                    cine_instances.append((iid, nframes))
            except Exception as _ex:
                _log_warning(
                    f"_play_orthanc_cine_dicom: frame count: {_ex}")

        if not cine_instances:
            QMessageBox.information(
                self, "Cine Oynat",
                "Bu çalışmada oynatılacak cine/video loop "
                "bulunamadı.\n\n"
                "(Sadece tek kareli görüntüler var.)")
            return

        # If multiple, pick the first one with the most frames
        # (usually the most clinically interesting cine loop)
        cine_instances.sort(key=lambda x: -x[1])
        chosen_iid, nframes = cine_instances[0]

        self.statusBar().showMessage(
            f"📥 Video indiriliyor ({nframes} kare)...", 8000)
        QApplication.processEvents()

        # Download the full DICOM to temp
        import tempfile
        try:
            dcm_bytes = self.orthanc.get_instance_dicom_bytes(chosen_iid)
            if not dcm_bytes:
                QMessageBox.warning(
                    self, "Cine Oynat",
                    "DICOM dosyası Orthanc'tan indirilemedi.")
                return
            tmp = tempfile.NamedTemporaryFile(
                suffix=".dcm", delete=False)
            tmp.write(dcm_bytes)
            tmp.close()
            tmp_path = Path(tmp.name)
        except Exception as ex:
            _log_warning(
                "_play_orthanc_cine_dicom: download", exc=ex)
            QMessageBox.critical(
                self, "Cine Oynat",
                f"DICOM indirilemedi:\n\n{ex}")
            return

        # Open cine player on the temp file
        try:
            dlg = DicomCinePlayer(tmp_path, self)
            if not hasattr(self, "_open_cine_players"):
                self._open_cine_players = []
            self._open_cine_players.append(dlg)

            # Clean up temp when dialog closes
            def _cleanup(_result, d=dlg, p=tmp_path):
                try:
                    if d in self._open_cine_players:
                        self._open_cine_players.remove(d)
                    p.unlink(missing_ok=True)
                except Exception as _ex:
                    _log_warning(
                        f"_play_orthanc_cine_dicom: cleanup: {_ex}")
            dlg.finished.connect(_cleanup)
            dlg.show()
            self.statusBar().showMessage(
                f"🎬 {display_name} — {nframes} kare cine oynatılıyor",
                5000)
        except Exception as ex:
            _log_warning(
                "_play_orthanc_cine_dicom: player", exc=ex)
            QMessageBox.critical(
                self, "Cine Oynatıcı Hatası",
                f"DICOM dosyası açılamadı:\n\n{ex}")
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception as _ex:
                _log_warning(
                    f"_play_orthanc_cine_dicom: tmp cleanup: {_ex}")

    def _open_patient_in_orthanc_web(self):
        """Open the current patient's Orthanc page in the default
        browser, using the best available plugin URL format.

        v68-UI: Opens Osimis Web Viewer / Stone Viewer / Explorer 2
        depending on which is installed on the server. Falls back to
        the default Orthanc Explorer if no plugin is detected.
        """
        if self.current_patient is None:
            QMessageBox.information(
                self, "Web'de Aç",
                "Önce bir hasta seçin.")
            return
        if not self._orthanc_connected:
            QMessageBox.warning(
                self, "Web'de Aç",
                "Orthanc sunucusuna bağlanılamıyor.")
            return

        patient_key = self.current_patient.name
        display_name = format_patient_name(patient_key)

        # Resolve Orthanc ID — use cache if available
        orthanc_id = db_get_orthanc_patient_id(patient_key)
        if not orthanc_id:
            # Try name search as fallback
            try:
                matches = self.orthanc.find_patient_by_name(display_name)
                if not matches:
                    parts = display_name.split()
                    if len(parts) >= 2:
                        matches = self.orthanc.find_patient_by_name(
                            " ".join(reversed(parts)))
                if not matches and parts:
                    matches = self.orthanc.find_patient_by_name(parts[-1])
                if matches:
                    orthanc_id = matches[0].get("ID", "")
                    if orthanc_id:
                        db_set_orthanc_patient_id(
                            patient_key, orthanc_id)
            except Exception as _ex:
                _log_warning(
                    f"open_orthanc_web: lookup: {_ex}")

        if not orthanc_id:
            QMessageBox.warning(
                self, "Web'de Aç",
                f"'{display_name}' için Orthanc'ta hasta bulunamadı.\n\n"
                f"'🔗 Eşleştir' butonuyla manuel eşleme yapabilirsiniz.")
            return

        url = self.orthanc.patient_web_url(orthanc_id)

        import webbrowser
        try:
            webbrowser.open(url)
            self.statusBar().showMessage(
                f"🌐 {display_name} Orthanc web sayfası açıldı",
                5000)
        except Exception as ex:
            _log_warning(f"open_orthanc_web: webbrowser: {ex}")
            QMessageBox.warning(
                self, "Web'de Aç",
                f"Tarayıcı açılamadı:\n{ex}\n\n"
                f"URL manuel kopyalayabilirsiniz:\n{url}")

    def _show_orthanc_match_dialog(self):
        """Manual Orthanc patient-match dialog.

        v68-UI: When a NAS folder name doesn't match the DICOM
        PatientName (typos, different spelling, TC vs name), the
        doctor needs to pick the right Orthanc patient by hand.
        This dialog lists ALL Orthanc patients + a live search box,
        and stores the chosen ID in `dicom_sync_state` so subsequent
        refreshes skip the name-based lookup.
        """
        if self.current_patient is None:
            QMessageBox.information(
                self, "Orthanc Eşleştir",
                "Önce bir hasta seçin.")
            return
        if not self._orthanc_connected:
            QMessageBox.warning(
                self, "Orthanc Eşleştir",
                "Orthanc sunucusuna bağlanılamıyor. "
                "Bağlantıyı kontrol edin.")
            return

        patient_key = self.current_patient.name
        display_name = format_patient_name(patient_key)
        current_orthanc_id = db_get_orthanc_patient_id(patient_key)

        dlg = QDialog(self)
        dlg.setWindowTitle("🔗 Orthanc Hasta Eşleştir")
        dlg.setMinimumSize(640, 540)
        dlg.setModal(True)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Hero banner
        hero = QWidget()
        hero.setFixedHeight(82)
        hero.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #6C4EC4,stop:1 #9A7ADF);")
        hero_lay = QVBoxLayout(hero)
        hero_lay.setContentsMargins(22, 12, 22, 12)
        hero_lay.setSpacing(3)
        h_t = QLabel("🔗  Orthanc Hasta Eşleştir")
        h_t.setStyleSheet(
            "color:white;font:800 20px 'Segoe UI';background:transparent;")
        h_s = QLabel(
            f"<b>{display_name}</b> için Orthanc'ta doğru "
            f"hastayı seç.")
        h_s.setStyleSheet(
            "color:rgba(255,255,255,0.92);font:500 12px 'Segoe UI';"
            "background:transparent;")
        hero_lay.addWidget(h_t)
        hero_lay.addWidget(h_s)
        root.addWidget(hero)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(22, 16, 22, 14)
        body_lay.setSpacing(10)

        # Current link info
        if current_orthanc_id:
            cur_lbl = QLabel(
                f"<span style='color:#107C10;'>✓ Zaten bağlı:</span> "
                f"<code>{current_orthanc_id[:16]}...</code>  "
                f"<span style='color:#999;'>(değiştirmek için aşağıdan yeni bir hasta seç)</span>")
            cur_lbl.setStyleSheet(
                "background:#EFF9EF;border:1px solid #A0DBA0;"
                "padding:8px 12px;border-radius:4px;"
                "font:12px 'Segoe UI';")
            body_lay.addWidget(cur_lbl)

        # Search box
        search_row = QHBoxLayout()
        search_lbl = QLabel("Ara:")
        search_lbl.setStyleSheet("font:500 12px 'Segoe UI';")
        search_row.addWidget(search_lbl)
        search_input = QLineEdit()
        search_input.setPlaceholderText(
            f"Hasta adı veya TC... (varsayılan: {display_name})")
        search_input.setText(display_name)
        search_input.setStyleSheet(
            "padding:6px 10px;border:1px solid #B8B0D4;"
            "border-radius:3px;font:500 12px 'Segoe UI';")
        search_row.addWidget(search_input, 1)
        body_lay.addLayout(search_row)

        # Results table
        tbl = QTableWidget()
        tbl.setColumnCount(4)
        tbl.setHorizontalHeaderLabels([
            "DICOM Adı", "TC / ID", "Çalışma", "Son Tarih"])
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.setColumnWidth(0, 230)
        tbl.setColumnWidth(1, 140)
        tbl.setColumnWidth(2, 90)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.setAlternatingRowColors(True)
        tbl.setStyleSheet(
            "QTableWidget{border:1px solid #B8B0D4;border-radius:3px;}"
            "QHeaderView::section{background:#F0ECFA;padding:6px;"
            "font:600 11px 'Segoe UI';border:none;"
            "border-bottom:1px solid #B8B0D4;}"
            "QTableWidget::item{padding:6px;}"
            "QTableWidget::item:selected{background:#D6CAF5;color:#1F0F60;}")
        body_lay.addWidget(tbl, 1)

        status_lbl = QLabel("")
        status_lbl.setStyleSheet(
            "color:#666;font:italic 11px 'Segoe UI';")
        body_lay.addWidget(status_lbl)

        root.addWidget(body, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(22, 10, 22, 14)
        btn_row.addStretch()
        btn_cancel = QPushButton("İptal")
        btn_cancel.setShortcut("Escape")
        btn_cancel.setStyleSheet(
            "QPushButton{background:#E5EEF7;color:#404040;"
            "padding:8px 18px;border:1px solid #B8D4E8;"
            "border-radius:3px;font:500 11px 'Segoe UI';}"
            "QPushButton:hover{background:#D5E5F5;}")
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_cancel)

        btn_unlink = QPushButton("🔓 Bağlantıyı Kaldır")
        btn_unlink.setToolTip(
            "Bu hastanın Orthanc bağlantısını sıfırla — "
            "bir dahaki DICOM yenilemesinde tekrar isim arar.")
        btn_unlink.setStyleSheet(
            "QPushButton{background:#FFF0F0;color:#C42B1C;"
            "padding:8px 18px;border:1px solid #E0A0A0;"
            "border-radius:3px;font:500 11px 'Segoe UI';}"
            "QPushButton:hover{background:#FFE0E0;}")
        if not current_orthanc_id:
            btn_unlink.setEnabled(False)
        btn_row.addWidget(btn_unlink)

        btn_link = QPushButton("🔗 Bu Hastayı Bağla")
        btn_link.setDefault(True)
        btn_link.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #6C4EC4,stop:1 #513899);color:white;"
            "padding:8px 22px;border:none;border-radius:3px;"
            "font:700 11px 'Segoe UI';}"
            "QPushButton:hover{background:qlineargradient("
            "x1:0,y1:0,x2:0,y2:1,stop:0 #513899,stop:1 #3D2B73);}"
            "QPushButton:disabled{background:#BBB;}")
        btn_link.setEnabled(False)
        btn_row.addWidget(btn_link)
        root.addLayout(btn_row)

        # Search logic
        orthanc = self.orthanc
        current_results = []  # [(orthanc_id, name, tc, study_count, last_date)]

        def _do_search():
            q = search_input.text().strip()
            if not q:
                return
            status_lbl.setText("🔍 Aranıyor...")
            QApplication.processEvents()
            tbl.setRowCount(0)
            current_results.clear()
            try:
                matches = orthanc.find_patient_by_name(q)
                # Also try reversed if single name
                parts = q.split()
                if not matches and len(parts) >= 2:
                    matches = orthanc.find_patient_by_name(
                        " ".join(reversed(parts)))
                # Also try PatientID search
                if not matches:
                    matches = orthanc.find_patient_by_id(q)
                if not matches:
                    status_lbl.setText(
                        f"⚠ '{q}' için eşleşme yok.")
                    btn_link.setEnabled(False)
                    return

                tbl.setRowCount(len(matches))
                for r, m in enumerate(matches):
                    oid = m.get("ID", "")
                    tags = m.get("MainDicomTags", {})
                    dname = tags.get("PatientName", "?")
                    tc = tags.get("PatientID", "")
                    studies = m.get("Studies", [])
                    nstudies = len(studies) if isinstance(studies, list) else 0

                    # Get last study date — need an extra lookup
                    last_date = ""
                    try:
                        if studies and isinstance(studies, list):
                            # Pick the most recent
                            stdies_full = orthanc.get_patient_studies(oid)
                            if stdies_full:
                                last_date = stdies_full[0].get(
                                    "MainDicomTags", {}).get("StudyDate", "")
                                if len(last_date) == 8:
                                    last_date = (f"{last_date[:4]}-"
                                                 f"{last_date[4:6]}-"
                                                 f"{last_date[6:]}")
                    except Exception as _ex:
                        _log_warning(
                            f"orthanc_match: last date lookup: {_ex}")

                    display = OrthancClient.dicom_name_to_display(dname)
                    tbl.setItem(
                        r, 0, QTableWidgetItem(display or dname))
                    tbl.setItem(r, 1, QTableWidgetItem(tc))
                    tbl.setItem(r, 2, QTableWidgetItem(str(nstudies)))
                    tbl.setItem(r, 3, QTableWidgetItem(last_date))
                    current_results.append(
                        (oid, display, tc, nstudies, last_date))
                status_lbl.setText(f"✓ {len(matches)} eşleşme bulundu.")
                # Auto-select first if only one match
                if len(matches) == 1:
                    tbl.selectRow(0)
                    btn_link.setEnabled(True)
            except Exception as ex:
                status_lbl.setText(
                    f"❌ Arama hatası: {type(ex).__name__}: {ex}")
                _log_warning("orthanc_match: search", exc=ex)

        def _on_selection_changed():
            btn_link.setEnabled(len(tbl.selectedItems()) > 0)

        def _on_link():
            sel = tbl.currentRow()
            if sel < 0 or sel >= len(current_results):
                return
            oid, name, tc, nstudies, last_date = current_results[sel]
            db_set_orthanc_patient_id(patient_key, oid)
            self.statusBar().showMessage(
                f"✓ {display_name} → {name} (Orthanc) bağlandı. "
                f"{nstudies} çalışma.", 6000)
            dlg.accept()
            # Trigger DICOM refresh so the doctor sees the new data
            try:
                self._refresh_dicom_for_patient()
            except Exception as _ex:
                _log_warning(
                    f"orthanc_match: refresh after link: {_ex}")

        def _on_unlink():
            try:
                with db_conn() as con:
                    con.execute(
                        "DELETE FROM dicom_sync_state WHERE patient_key=?",
                        (patient_key,))
                    con.execute(
                        "DELETE FROM dicom_cache WHERE patient_key=?",
                        (patient_key,))
                    con.commit()
                self.statusBar().showMessage(
                    f"✓ {display_name} Orthanc bağlantısı kaldırıldı.", 4000)
                dlg.accept()
            except Exception as ex:
                _log_warning("orthanc_match: unlink", exc=ex)

        # Wire up signals
        search_input.returnPressed.connect(_do_search)
        search_input.textChanged.connect(
            lambda _: search_input.setToolTip("Enter'a bas veya bekle…"))
        tbl.itemSelectionChanged.connect(_on_selection_changed)
        tbl.itemDoubleClicked.connect(lambda _: _on_link())
        btn_link.clicked.connect(_on_link)
        btn_unlink.clicked.connect(_on_unlink)

        # Auto-search on open with the patient's current name
        QTimer.singleShot(100, _do_search)

        dlg.exec()

    def _save_dicom_to_patient_folder(self):
        """Download all DICOM instances for the current patient from
        Orthanc and save them into the patient's currently-selected
        visit folder on NAS.

        v68-UI: Creates a `DICOM/` subfolder inside the visit folder.
        For each instance:
          • Writes the raw .dcm file (archival, full quality)
          • Writes a rendered .jpg (for quick preview / WhatsApp)
          • For multi-frame cine loops: extracts every frame as
            <name>_frame001.jpg, <name>_frame002.jpg, ...

        Runs in a background worker thread to avoid freezing the UI.
        Shows a progress dialog with cancel.
        """
        if self.current_patient is None:
            QMessageBox.information(
                self, "DICOM Kaydet",
                "Önce bir hasta seçin.")
            return
        if self.current_subfolder is None:
            # Pick most recent visit folder
            if self.subfolder_paths:
                target_visit = self.subfolder_paths[0]
            else:
                QMessageBox.warning(
                    self, "DICOM Kaydet",
                    "Bu hastanın henüz bir geliş klasörü yok. "
                    "Önce bir geliş oluşturun.")
                return
        else:
            target_visit = self.current_subfolder

        if not self._orthanc_connected:
            QMessageBox.warning(
                self, "DICOM Kaydet",
                "Orthanc sunucusuna bağlanılamıyor. "
                "Bağlantıyı kontrol edin (Ayarlar → Orthanc "
                "DICOM Sunucu Ayarları).")
            return

        patient_key = self.current_patient.name
        search_name = format_patient_name(patient_key)
        visit_label = format_visit_name(target_visit.name)

        # Confirmation dialog — explain what's about to happen
        confirm = QMessageBox.question(
            self, "DICOM Görüntülerini Kaydet",
            f"<b>{search_name}</b> hastasının Orthanc'taki tüm DICOM "
            f"görüntüleri <b>{visit_label}</b> gelişinin klasörüne "
            f"indirilecek.\n\n"
            f"Hedef: <code>{target_visit}\\DICOM\\</code>\n\n"
            f"Her görüntü için:\n"
            f"  • Orijinal .dcm dosyası (arşiv)\n"
            f"  • Yüksek kaliteli .jpg (hızlı önizleme)\n"
            f"  • Video/cine loop'lar için kare kare JPG\n\n"
            f"İşlem birkaç dakika sürebilir. Devam edilsin mi?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes)
        if confirm != QMessageBox.Yes:
            return

        dicom_dir = target_visit / "DICOM"
        try:
            dicom_dir.mkdir(parents=True, exist_ok=True)
        except Exception as ex:
            QMessageBox.critical(
                self, "DICOM Kaydet",
                f"DICOM klasörü oluşturulamadı:\n{ex}")
            return

        # Find the patient on Orthanc first (needed to enumerate studies)
        orthanc = self.orthanc

        # Progress dialog
        from PySide6.QtWidgets import QProgressDialog
        progress = QProgressDialog(
            "Orthanc'ta hasta aranıyor...",
            "İptal", 0, 100, self)
        progress.setWindowTitle("DICOM Kaydet")
        progress.setWindowModality(Qt.ApplicationModal)
        progress.setMinimumWidth(500)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()
        QApplication.processEvents()

        cancelled = {"flag": False}
        def _cancel():
            cancelled["flag"] = True
        progress.canceled.connect(_cancel)

        saved_dcm = 0
        saved_jpg = 0
        skipped = 0
        errors = 0

        try:
            # Step 1: Find patient on Orthanc — prefer saved ID, else search
            saved_oid = db_get_orthanc_patient_id(patient_key)
            orthanc_id = ""
            if saved_oid:
                # Verify the saved ID still exists
                try:
                    p = orthanc.get_patient(saved_oid)
                    if p:
                        orthanc_id = saved_oid
                        progress.setLabelText(
                            "Kayıtlı Orthanc eşleşmesi kullanılıyor...")
                        QApplication.processEvents()
                except Exception as _ex:
                    _log_warning(
                        f"save_dicom: verify saved oid: {_ex}")

            if not orthanc_id:
                progress.setLabelText(
                    f"Orthanc'ta '{search_name}' aranıyor...")
                QApplication.processEvents()
                matches = orthanc.find_patient_by_name(search_name)
                if not matches:
                    parts = search_name.split()
                    if len(parts) >= 2:
                        matches = orthanc.find_patient_by_name(
                            " ".join(reversed(parts)))
                if not matches:
                    parts = search_name.split()
                    if parts:
                        matches = orthanc.find_patient_by_name(parts[-1])

                if not matches:
                    progress.close()
                    QMessageBox.warning(
                        self, "DICOM Kaydet",
                        f"Orthanc'ta '{search_name}' adıyla "
                        f"eşleşen hasta bulunamadı.\n\n"
                        f"'🔗 Eşleştir' butonunu kullanarak manuel "
                        f"bağlantı kurabilirsiniz.")
                    return

                patient = matches[0]
                orthanc_id = patient.get("ID", "")
                # Save the mapping so next time we skip the search
                if orthanc_id:
                    db_set_orthanc_patient_id(patient_key, orthanc_id)

            # Step 2: Get all studies, then all instances
            progress.setLabelText("Çalışma listesi alınıyor...")
            QApplication.processEvents()
            studies = orthanc.get_patient_studies(orthanc_id)
            if not studies:
                progress.close()
                QMessageBox.information(
                    self, "DICOM Kaydet",
                    "Bu hasta için Orthanc'ta hiç çalışma yok.")
                return

            # Collect all instances with study context
            all_instances = []  # [(instance_id, study_date), ...]
            for s in studies:
                study_id = s.get("ID", "")
                study_date = s.get("MainDicomTags", {}).get(
                    "StudyDate", "")
                try:
                    inst_ids = orthanc.get_study_instances(study_id)
                    for iid in inst_ids:
                        all_instances.append((iid, study_date))
                except Exception:
                    continue

            total = len(all_instances)
            if total == 0:
                progress.close()
                QMessageBox.information(
                    self, "DICOM Kaydet",
                    "Hiç DICOM görüntü bulunamadı.")
                return

            progress.setMaximum(total)
            progress.setValue(0)

            # Step 3: For each instance, download .dcm + .jpg
            for idx, (iid, study_date) in enumerate(all_instances):
                if cancelled["flag"]:
                    break
                # Update progress
                progress.setLabelText(
                    f"İndiriliyor {idx + 1} / {total}\n"
                    f"{study_date or '(tarih yok)'}")
                progress.setValue(idx)
                QApplication.processEvents()

                # File prefix — sortable by study date
                prefix = f"{study_date or 'no_date'}_{iid[:8]}"

                # Check if already exists — skip if so
                dcm_path = dicom_dir / f"{prefix}.dcm"
                jpg_path = dicom_dir / f"{prefix}.jpg"
                if dcm_path.exists() and jpg_path.exists():
                    skipped += 1
                    continue

                # Download raw DICOM bytes
                if not dcm_path.exists():
                    try:
                        dcm_bytes = orthanc.get_instance_dicom_bytes(iid)
                        if dcm_bytes:
                            dcm_path.write_bytes(dcm_bytes)
                            saved_dcm += 1
                    except Exception as _ex:
                        _log_warning(
                            f"save_dicom: dcm download {iid}: {_ex}")
                        errors += 1

                # Download rendered JPG (full quality)
                if not jpg_path.exists():
                    try:
                        jpg_bytes = orthanc.get_instance_rendered_bytes(
                            iid, quality=95)
                        if not jpg_bytes:
                            # Fallback to low-res preview
                            jpg_bytes = orthanc.get_instance_preview_bytes(iid)
                        if jpg_bytes:
                            jpg_path.write_bytes(jpg_bytes)
                            saved_jpg += 1
                    except Exception as _ex:
                        _log_warning(
                            f"save_dicom: jpg render {iid}: {_ex}")

                # Multi-frame? Extract each frame as separate JPG
                try:
                    nframes = orthanc.get_instance_frame_count(iid)
                    if nframes > 1:
                        # This is a cine loop — extract every frame
                        progress.setLabelText(
                            f"İndiriliyor {idx + 1} / {total}\n"
                            f"Video {nframes} kare çıkarılıyor...")
                        QApplication.processEvents()
                        for f_idx in range(nframes):
                            if cancelled["flag"]:
                                break
                            frame_path = dicom_dir / (
                                f"{prefix}_frame{f_idx:03d}.jpg")
                            if frame_path.exists():
                                continue
                            try:
                                fbytes = orthanc.get_instance_frame_bytes(
                                    iid, f_idx, quality=85)
                                if fbytes:
                                    frame_path.write_bytes(fbytes)
                                    saved_jpg += 1
                            except Exception as _ex:
                                _log_warning(
                                    f"save_dicom: frame {iid}/{f_idx}: {_ex}")
                except Exception as _ex:
                    _log_warning(
                        f"save_dicom: frame count {iid}: {_ex}")

            progress.setValue(total)
        except Exception as ex:
            _log_warning("save_dicom_to_patient_folder", exc=ex)
            progress.close()
            QMessageBox.critical(
                self, "DICOM Kaydet",
                f"İşlem sırasında hata oluştu:\n\n"
                f"{type(ex).__name__}: {ex}\n\n"
                f"Kısmi kayıt olabilir. DICOM klasörünü kontrol edin:\n"
                f"{dicom_dir}")
            return

        progress.close()

        # Summary
        if cancelled["flag"]:
            msg = (f"❌ İşlem iptal edildi.\n\n"
                   f"Şu ana kadar kaydedilen:\n"
                   f"  • {saved_dcm} DICOM dosyası\n"
                   f"  • {saved_jpg} JPG görüntü\n"
                   f"  • {skipped} zaten vardı\n")
        else:
            msg = (f"✓ Tamamlandı.\n\n"
                   f"Kaydedilen:\n"
                   f"  • {saved_dcm} DICOM (.dcm) dosyası\n"
                   f"  • {saved_jpg} JPG görüntü/kare\n"
                   f"  • {skipped} zaten vardı, atlandı\n")
            if errors:
                msg += f"  • {errors} dosya indirilemedi\n"
            msg += f"\nKonum:\n{dicom_dir}"

        self.statusBar().showMessage(
            f"✓ DICOM kaydedildi: {saved_dcm} .dcm + "
            f"{saved_jpg} .jpg ({visit_label})", 8000)
        QMessageBox.information(
            self, "DICOM Kaydet — Tamamlandı", msg)

        # Trigger file list refresh so the new DICOM folder shows up
        try:
            if hasattr(self, "_refresh_file_list_for_current_visit"):
                self._refresh_file_list_for_current_visit()
        except Exception as _ex:
            _log_warning(
                f"save_dicom: file list refresh: {_ex}")

    def _force_refresh_dicom(self):
        """Bypass the cache and re-query Orthanc from scratch.
        Useful when the cache is stale or the doctor added new DICOMs
        outside the app."""
        if self.current_patient is None:
            return
        patient_key = self.current_patient.name
        # Delete cached rows for this patient so the cache-first path
        # treats this as a fresh query
        try:
            with db_conn() as con:
                con.execute(
                    "DELETE FROM dicom_cache WHERE patient_key=?",
                    (patient_key,))
                con.execute(
                    "DELETE FROM dicom_sync_state WHERE patient_key=?",
                    (patient_key,))
                con.commit()
        except Exception as ex:
            _log_warning(f"force refresh cache clear failed: {ex}")
        self.statusBar().showMessage("Önbellek temizlendi, Orthanc sorgulanıyor...",
                                      2000)
        self._refresh_dicom_for_patient()

    def _populate_dicom_from_cache(self,
                                    cached_instances: List[Tuple[str, str, str]]):
        """Render the DICOM grid from cached instance data, with JPEGs
        loaded from disk where available. Falls back to Orthanc fetch
        per-instance only if the JPEG isn't cached on disk yet.

        cached_instances: list of (instance_id, study_date, jpeg_path)
        """
        if not cached_instances:
            return

        LIMIT = 50
        shown = cached_instances[:LIMIT]
        total = len(cached_instances)
        self.dicom_count_lbl.setText(
            f"{total} görüntü (önbellekten)"
            + (f" · ilk {LIMIT}" if total > LIMIT else ""))

        # Group by study date — same grouping logic as Orthanc-driven render
        from collections import OrderedDict
        date_groups: "OrderedDict[str, List[Tuple[str, str]]]" = OrderedDict()
        for iid, study_date, jpeg_path in shown:
            key = study_date if study_date else "00000000"
            if key not in date_groups:
                date_groups[key] = []
            date_groups[key].append((iid, jpeg_path))

        sorted_keys = sorted(date_groups.keys(), reverse=True)

        def _fmt_date(yyyymmdd: str) -> str:
            if not yyyymmdd or yyyymmdd == "00000000" or len(yyyymmdd) != 8:
                return "📅 Tarih bilinmiyor"
            try:
                return f"📅 {yyyymmdd[6:8]}.{yyyymmdd[4:6]}.{yyyymmdd[0:4]}"
            except Exception:
                return "📅 Tarih bilinmiyor"

        cols = 5
        grid_row = 0
        display_idx = 0

        for date_key in sorted_keys:
            inst_list = date_groups[date_key]
            if not inst_list:
                continue

            header = QLabel(
                f"{_fmt_date(date_key)}  "
                f"<span style='color:#606060;font-weight:normal;'>"
                f"({len(inst_list)} görüntü)</span>")
            header.setTextFormat(Qt.RichText)
            header.setStyleSheet(
                "background:#E5F1FB;color:#003A66;"
                "font:700 13px 'Segoe UI';padding:8px 12px;"
                "border:1px solid #A0C8E8;border-radius:3px;margin-top:4px;")
            self.dicom_grid.addWidget(header, grid_row, 0, 1, cols)
            grid_row += 1

            col_in_row = 0
            for inst_id, jpeg_path_str in inst_list:
                try:
                    # Prefer the cached JPEG path from DB; fall back to tmp dir
                    jpeg_path = Path(jpeg_path_str) if jpeg_path_str else \
                                self._dicom_tmp_dir / f"{inst_id}.jpg"
                    # If the file doesn't exist, skip it (will be fetched
                    # on next Orthanc query)
                    if not jpeg_path.exists():
                        continue

                    self._dicom_instance_ids.append(inst_id)
                    self._dicom_preview_paths.append(jpeg_path)

                    pix = self._make_thumbnail(jpeg_path)
                    tile = ImageGalleryThumb(jpeg_path, pix)
                    current_idx = len(self._dicom_preview_paths) - 1
                    tile.clicked.connect(
                        lambda _c=False, i=current_idx: self._open_dicom_preview(i))

                    self.dicom_grid.addWidget(tile, grid_row, col_in_row)
                    col_in_row += 1
                    if col_in_row >= cols:
                        col_in_row = 0
                        grid_row += 1
                    display_idx += 1
                except Exception as ex:
                    _log_warning(f"cache thumb {inst_id} failed: {ex}")
                    continue

            if col_in_row > 0:
                grid_row += 1
            grid_row += 1

    def _show_dicom_message(self, text: str):
        """Show a centered message in the DICOM grid (empty state / error).

        v68-UI-PREMIUM: Uses EmptyStateWidget for a polished look.
        Auto-detects if the text is an error (starts with ❌/⚠) and
        picks an appropriate icon + tone.
        """
        if not hasattr(self, "dicom_grid"):
            return
        # Detect message type from emoji
        is_error = any(text.lstrip().startswith(e) for e in ("❌", "⚠"))
        is_loading = text.lstrip().startswith("⏳")
        if is_error:
            icon = "🩻"
            title = "DICOM Görüntüleri Yüklenemedi"
        elif is_loading:
            icon = "⏳"
            title = "Yükleniyor..."
        else:
            icon = "🩻"
            title = "DICOM Görüntü Yok"

        # Use EmptyStateWidget for premium look
        try:
            empty = EmptyStateWidget(
                icon=icon,
                title=title,
                subtitle=text,
                parent=None)
            self.dicom_grid.addWidget(empty, 0, 0, 1, 5)
        except Exception as _ex:
            _log_warning(f"_show_dicom_message: empty state: {_ex}")
            # Fallback: plain label
            lbl = QLabel(text)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setWordWrap(True)
            lbl.setStyleSheet(
                "color:#505050;font:400 12px 'Segoe UI';padding:30px 20px;"
                "background:transparent;line-height:1.6;")
            self.dicom_grid.addWidget(lbl, 0, 0, 1, 5)

    def _open_dicom_preview(self, start_index: int):
        """Open preview inline in the DICOM tab's stacked widget.
        Page 0 = thumbnails, page 1 = preview. No new window opens."""
        if not self._dicom_preview_paths:
            return
        if not hasattr(self, "dicom_stack"):
            return
        start_index = max(0, min(start_index, len(self._dicom_preview_paths) - 1))
        if not hasattr(self, "_favourite_dicom"):
            self._favourite_dicom = {}
        key = str(self.current_patient) if self.current_patient else "_"
        favs = self._favourite_dicom.get(key, set())

        # Remove any previous preview page
        while self.dicom_stack.count() > 1:
            old = self.dicom_stack.widget(1)
            self.dicom_stack.removeWidget(old)
            old.deleteLater()

        preview = LargePreviewDialog(
            self._dicom_preview_paths, start_index, self.dicom_stack,
            on_add_to_pdf=self._preview_add_to_new_pdf,
            on_add_to_pdf_editor=self._preview_add_to_pdf,
            on_print_image=self._preview_print_image,
            favourites=favs,
            embed_in=self.dicom_stack,
        )

        def _on_done(_r=0, p=preview, k=key):
            try:
                self._favourite_dicom[k] = p.favourites()
            except Exception as _ex:
                _log_warning("MainWindow._on_done", exc=_ex)
            try:
                self.dicom_stack.setCurrentIndex(0)
                idx = self.dicom_stack.indexOf(p)
                if idx > 0:
                    self.dicom_stack.removeWidget(p)
                    p.deleteLater()
            except Exception as _ex:
                _log_warning("MainWindow._on_done", exc=_ex)
        preview.finished.connect(_on_done)

        self.dicom_stack.addWidget(preview)
        self.dicom_stack.setCurrentWidget(preview)
        preview.setFocus()
