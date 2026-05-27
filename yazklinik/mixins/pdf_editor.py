"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _PdfEditorMixin
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

class _PdfEditorMixin:
    """MainWindow methods related to PdfEditor. Mixed into MainWindow via MRO."""

    def _build_tab_report(self) -> QWidget:
        """Unified "Rapor" tab — hosts both PDF editing modes under one
        top-level tab, with two internal sub-tabs to switch between them:

          • Mevcut PDF  — edit/view the existing Voluson PDF report
          • Yeni PDF    — build a new PDF from scratch using selected
                           images, templates, and notes

        Before v68 these lived as two separate top-level tabs ("Ana PDF"
        and "Yeni PDF"). Merging them here reduces top-tab clutter and
        keeps all report-related work in one place, matching the doctor's
        mental model ("I want to work on the report").
        """
        page = QWidget()
        page.setObjectName("TabPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.report_subtabs = QTabWidget()
        self.report_subtabs.setObjectName("ReportSubTabs")
        # Make the sub-tabs look less prominent than the main tabs —
        # they're secondary navigation, not primary sections.
        self.report_subtabs.setStyleSheet(
            "QTabWidget#ReportSubTabs::pane{border-top:1px solid #C8C8C8;}"
            "QTabWidget#ReportSubTabs QTabBar::tab{"
            "padding:5px 16px;font:500 11px 'Segoe UI';}")

        # Sub-tab 1: existing PDF editor (was "Ana PDF")
        self.report_subtabs.addTab(
            self._build_tab_pdf_editor(), "📝  Mevcut PDF")
        # Sub-tab 2: new-from-scratch PDF builder (was "Yeni PDF")
        self.report_subtabs.addTab(
            self._build_tab_pdf(), "✨  Yeni PDF")

        # When the doctor switches to Yeni PDF, refresh its thumbnails
        # and preview. Sub-tabs hide their content widgets, and in some
        # Qt versions hidden widgets skip expensive updates — so without
        # this, the Yeni PDF tab can appear empty on first open.
        def _on_report_subtab_changed(idx):
            if idx == 1:  # Yeni PDF
                try:
                    if hasattr(self, "_populate_pdf_source_grid"):
                        self._populate_pdf_source_grid()
                    if hasattr(self, "_refresh_pdf_canvas"):
                        self._refresh_pdf_canvas()
                except Exception as _ex:
                    _log_warning("_on_report_subtab_changed", exc=_ex)
        self.report_subtabs.currentChanged.connect(_on_report_subtab_changed)

        lay.addWidget(self.report_subtabs)
        return page

    def _build_tab_pdf_editor(self) -> QWidget:
        """PDF sayfalarını düzenle — tüm ekranı kaplayan PDF alanı.

        Resimleri sağdaki thumbnail şeridinden (Görüntüler paneli) veya
        Görüntüler sekmesinden sağ tık ile sürükleyip buradaki PDF sayfalarına
        bırakabilirsiniz. Şablonlar toolbar'daki "Şablon" butonu ile eklenir.
        """
        page = QWidget()
        page.setObjectName("TabPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        # Top strip — title + tools + template queue indicator
        hdr = QHBoxLayout()
        hdr.setSpacing(8)
        rtt = QLabel("Ana PDF — orijinal PDF'in üzerine yazılır")
        rtt.setObjectName("BoxTitle")
        hdr.addWidget(rtt)

        # "+ Yeni Sayfa" button — appends a blank A4 page to the editor.
        # Useful when doctor needs extra space for more images or text.
        self.editor_newpage_btn = QPushButton("➕ Yeni Sayfa")
        self.editor_newpage_btn.setObjectName("MiniBtn")
        self.editor_newpage_btn.setCursor(Qt.PointingHandCursor)
        self.editor_newpage_btn.setToolTip(
            "PDF'in sonuna boş bir sayfa ekle — ekstra resim/yazı için")
        self.editor_newpage_btn.clicked.connect(self._editor_add_blank_page)
        hdr.addWidget(self.editor_newpage_btn)

        # "🗑 Sayfayı Sil" button — deletes the currently visible page.
        # Undo-capable: Ctrl+Z restores.
        self.editor_delpage_btn = QPushButton("🗑 Sayfayı Sil")
        self.editor_delpage_btn.setObjectName("MiniBtn")
        self.editor_delpage_btn.setCursor(Qt.PointingHandCursor)
        self.editor_delpage_btn.setToolTip(
            "Görüntülenen sayfayı sil (Ctrl+Z ile geri alınabilir)")
        self.editor_delpage_btn.clicked.connect(self._editor_delete_current_page)
        hdr.addWidget(self.editor_delpage_btn)

        # "📑 Sayfaları Seç" button — opens a checklist dialog where the
        # doctor can toggle which pages get saved. Cover is always kept.
        self.editor_selectpages_btn = QPushButton("📑 Sayfaları Seç")
        self.editor_selectpages_btn.setObjectName("MiniBtn")
        self.editor_selectpages_btn.setCursor(Qt.PointingHandCursor)
        self.editor_selectpages_btn.setToolTip(
            "PDF'in hangi sayfaları kaydedileceğini seç — "
            "kapak sayfası her zaman korunur")
        self.editor_selectpages_btn.clicked.connect(
            self._editor_select_pages_dialog)
        hdr.addWidget(self.editor_selectpages_btn)

        # ── Layout (2/3 columns) combo for the visible page ──────────────
        # The doctor wanted a way to quickly re-arrange images on the
        # currently visible page into a clean 2-column or 3-column grid.
        # Auto-layout already runs when images drop, but sometimes the
        # doctor adds images one at a time or moves them around and wants
        # to snap them back to a grid.
        hdr.addWidget(QLabel("│"))
        layout_lbl = QLabel("Düzen:")
        layout_lbl.setStyleSheet(
            "color:#606060;font:500 11px 'Segoe UI';padding:2px 4px;")
        hdr.addWidget(layout_lbl)

        self.editor_layout_combo = QComboBox()
        self.editor_layout_combo.setObjectName("EditorLayoutCombo")
        self.editor_layout_combo.addItem("Otomatik", "auto")
        self.editor_layout_combo.addItem("2 resim (yan yana)", "two")
        self.editor_layout_combo.addItem("3 resim (2 üst + 1 alt)", "three")
        self.editor_layout_combo.addItem("4 resim (2×2)", "four")
        self.editor_layout_combo.addItem("6 resim (3×2)", "six")
        self.editor_layout_combo.addItem("9 resim (3×3)", "nine")
        self.editor_layout_combo.setCurrentIndex(0)
        self.editor_layout_combo.setToolTip(
            "Görünen sayfadaki resimleri seçilen düzene göre yerleştir")
        self.editor_layout_combo.setStyleSheet(
            "QComboBox{font:500 11px 'Segoe UI';padding:3px 8px;"
            "border:1px solid #C8C8C8;background:#FFFFFF;min-width:150px;}")
        hdr.addWidget(self.editor_layout_combo)

        self.editor_apply_layout_btn = QPushButton("↻ Uygula")
        self.editor_apply_layout_btn.setObjectName("MiniBtn")
        self.editor_apply_layout_btn.setCursor(Qt.PointingHandCursor)
        self.editor_apply_layout_btn.setToolTip(
            "Seçili düzeni görünen sayfadaki resimlere uygula")
        self.editor_apply_layout_btn.clicked.connect(
            self._editor_apply_layout_to_visible)
        hdr.addWidget(self.editor_apply_layout_btn)

        hdr.addStretch()
        self.tmpl_queue_lbl = QLabel("Bekleyen şablon: 0")
        self.tmpl_queue_lbl.setStyleSheet(
            "color:#606060;font:400 11px 'Segoe UI';padding:2px 4px;")
        hdr.addWidget(self.tmpl_queue_lbl)
        lay.addLayout(hdr)

        # Main PDF editor area — PDF on left, draggable image strip on right.
        # The strip lets the doctor drag images from the current visit and
        # drop them directly on a PDF page (drop handlers are on PdfPageEditWidget).
        pdf_main_split = QSplitter(Qt.Horizontal)
        pdf_main_split.setHandleWidth(6)
        pdf_main_split.setChildrenCollapsible(False)

        self.pdf_editor = PdfEditor()
        pdf_main_split.addWidget(self.pdf_editor)

        # ── Right-side image picker panel ────────────────────────────────
        editor_right = QFrame()
        editor_right.setObjectName("InnerBox")
        editor_right.setStyleSheet(
            "QFrame#InnerBox{background:#F8F8F8;"
            "border-left:1px solid #C8C8C8;}")
        er_lay = QVBoxLayout(editor_right)
        er_lay.setContentsMargins(6, 6, 6, 6)
        er_lay.setSpacing(4)

        er_title = QLabel("<b>🖼️ Eklenebilir Resimler</b>")
        er_title.setTextFormat(Qt.RichText)
        er_title.setStyleSheet(
            "color:#005A9E;font:700 12px 'Segoe UI';padding:4px;"
            "background:transparent;border:none;")
        er_lay.addWidget(er_title)

        er_hint = QLabel(
            "<i style='color:#606060;font-size:10px;'>"
            "Sürükle → sol PDF sayfasına bırak<br>"
            "veya çift tıkla → son sayfaya ekle</i>")
        er_hint.setTextFormat(Qt.RichText)
        er_hint.setWordWrap(True)
        er_hint.setStyleSheet(transparent_icon_button_style())
        er_lay.addWidget(er_hint)

        # Scrollable area for thumbnails
        er_scroll = QScrollArea()
        er_scroll.setWidgetResizable(True)
        er_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        er_scroll.setStyleSheet(
            "QScrollArea{background:#FFFFFF;border:1px solid #C8C8C8;}")
        er_host = QWidget()
        self.editor_thumb_layout = QVBoxLayout(er_host)
        self.editor_thumb_layout.setContentsMargins(4, 4, 4, 4)
        self.editor_thumb_layout.setSpacing(4)
        self.editor_thumb_layout.addStretch()
        er_scroll.setWidget(er_host)
        er_lay.addWidget(er_scroll, 1)

        pdf_main_split.addWidget(editor_right)
        # Left 75%, right 25% - doctor sees PDF big, images scrollable
        pdf_main_split.setSizes([1200, 280])
        pdf_main_split.setStretchFactor(0, 1)
        pdf_main_split.setStretchFactor(1, 0)

        lay.addWidget(pdf_main_split, 1)

        # Action bar
        act = QHBoxLayout()
        act.setSpacing(4)
        self.editor_zoom_out_btn = QPushButton("−")
        self.editor_zoom_out_btn.setObjectName("MiniBtn")
        self.editor_zoom_out_btn.setFixedSize(28, 24)
        self.editor_zoom_out_btn.clicked.connect(
            lambda: self.pdf_editor.set_zoom(self.pdf_editor.zoom() - 0.15))
        self.editor_zoom_in_btn = QPushButton("+")
        self.editor_zoom_in_btn.setObjectName("MiniBtn")
        self.editor_zoom_in_btn.setFixedSize(28, 24)
        self.editor_zoom_in_btn.clicked.connect(
            lambda: self.pdf_editor.set_zoom(self.pdf_editor.zoom() + 0.15))
        self.editor_undo_btn = ActionButton("↶ Geri Al")
        self.editor_undo_btn.setToolTip("Son yapılan işlemi geri al (Ctrl+Z)")
        self.editor_undo_btn.clicked.connect(self._editor_undo)
        self.editor_undo_btn.setEnabled(False)
        self.editor_clear_btn = ActionButton("Tümünü Temizle")
        self.editor_clear_btn.clicked.connect(self._editor_clear_all)
        self.editor_save_btn = ActionButton("Kaydet (Orijinale Yaz)", primary=True)
        self.editor_save_btn.clicked.connect(self._editor_save)
        self.editor_save_as_btn = ActionButton("Farklı Kaydet...")
        self.editor_save_as_btn.clicked.connect(self._editor_save_as)

        act.addWidget(QLabel("Zoom:"))
        act.addWidget(self.editor_zoom_out_btn)
        act.addWidget(self.editor_zoom_in_btn)
        act.addSpacing(10)
        act.addWidget(self.editor_undo_btn)
        act.addWidget(self.editor_clear_btn)
        act.addSpacing(10)
        # New annotation tools
        self.editor_text_btn = ActionButton("✎ Yazı")
        self.editor_text_btn.setToolTip(
            "Boş alana serbest yazı kutusu ekle. Çift tıkla → metni düzenle")
        self.editor_text_btn.clicked.connect(self._editor_add_text)
        act.addWidget(self.editor_text_btn)

        self.editor_redact_btn = ActionButton("▭ Beyaz Örtü")
        self.editor_redact_btn.setToolTip(
            "Mevcut yazıyı beyaz dikdörtgenle ört ve üstüne yeni yazı ekle")
        self.editor_redact_btn.clicked.connect(self._editor_add_redact)
        act.addWidget(self.editor_redact_btn)

        self.editor_stamp_btn = ActionButton("⚑ Damga")
        self.editor_stamp_btn.setToolTip(
            "Hazır damgalar: KOPYA, KONTROL, GÖZDEN GEÇİRİLDİ, İMZALANDI...")
        self.editor_stamp_btn.clicked.connect(self._editor_add_stamp)
        act.addWidget(self.editor_stamp_btn)

        act.addSpacing(10)
        # Template button — also accessible from the main toolbar, but handy here
        self.editor_tmpl_btn = ActionButton("📝 Şablon Ekle...")
        self.editor_tmpl_btn.setToolTip("PDF'in son sayfasına şablon metni ekle")
        self.editor_tmpl_btn.clicked.connect(self._open_templates_dialog)
        act.addWidget(self.editor_tmpl_btn)
        act.addStretch()
        act.addWidget(self.editor_save_as_btn)
        act.addWidget(self.editor_save_btn)
        lay.addLayout(act)

        # Undo history
        self._editor_undo_stack: list = []
        undo_action = QAction(self)
        undo_action.setShortcut("Ctrl+Z")
        undo_action.triggered.connect(self._editor_undo)
        self.addAction(undo_action)

        # Ctrl+S → Save
        save_action = QAction(self)
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._editor_save)
        self.addAction(save_action)

        # Ctrl+T is already bound on the main toolbar (globally active), no
        # need to duplicate it here — Qt would warn about the collision.

        # Ctrl++ / Ctrl+- → Zoom
        zi_action = QAction(self)
        zi_action.setShortcut("Ctrl++")
        zi_action.triggered.connect(
            lambda: self.pdf_editor.set_zoom(self.pdf_editor.zoom() + 0.15))
        self.addAction(zi_action)
        zo_action = QAction(self)
        zo_action.setShortcut("Ctrl+-")
        zo_action.triggered.connect(
            lambda: self.pdf_editor.set_zoom(self.pdf_editor.zoom() - 0.15))
        self.addAction(zo_action)

        self.editor_status_label = QLabel("Hazır.")
        self.editor_status_label.setObjectName("StatusText")
        lay.addWidget(self.editor_status_label)

        return page

    def _refresh_pdf_canvas(self):
        """Repaint the interactive Yeni PDF preview.

        Each page is now a real PdfPageEditWidget (same widget Ana PDF uses)
        — so the doctor gets drag-drop, right-click size menu (small/medium/
        large), swap-by-drag, aspect-ratio-preserving fit, cross-page move,
        and the auto-side-by-side layout when there are 2 images per page.

        Data model: self._new_pdf_pages holds one PdfPageEditWidget per
        page. The USG cover (if enabled) is shown as a read-only preview
        above the editable pages. User edits go directly onto the widgets.
        """
        if not hasattr(self, "pdf_canvas_layout"):
            return

        # ── Preserve existing overlay state ───────────────────────────────
        # Every refresh tears down the page widgets (e.g. when a checkbox
        # is toggled, which rebuilds the header pixmap). Capture the
        # doctor's manual placements so we can restore them.
        preserved_images: List[Tuple[int, Path, QRect]] = []
        preserved_texts: List[Tuple[int, QRect, str]] = []
        if hasattr(self, "_new_pdf_pages"):
            for pi, pw in enumerate(self._new_pdf_pages):
                try:
                    for ov in pw.overlays:
                        preserved_images.append(
                            (pi, ov.image_path, QRect(ov.geometry())))
                    for tov in pw.text_overlays:
                        preserved_texts.append(
                            (pi, QRect(tov.geometry()),
                             getattr(tov, "text", "") or ""))
                except Exception:
                    continue

        # Clear current preview
        while self.pdf_canvas_layout.count() > 0:
            it = self.pdf_canvas_layout.takeAt(0)
            w = it.widget() if it else None
            if w is not None:
                w.deleteLater()
        self._new_pdf_pages = []  # reset list; pages are recreated below

        # Page geometry: A4 = 595×842 pt → preview 95%: ~565×800
        # Bigger preview per doctor's request — easier to work with.
        page_w, page_h = 565, 800
        pdf_w_pts, pdf_h_pts = 595.0, 842.0

        # ── USG COVER PAGE (read-only preview) ──────────────────────────────
        cover_pixmap: Optional[QPixmap] = None
        cover_enabled = (self.pdf_include_usg_cover.isChecked()
                         if hasattr(self, "pdf_include_usg_cover") else True)
        if cover_enabled:
            try:
                if self.current_subfolder:
                    src_pdf = get_latest_pdf_in_folder(self.current_subfolder)
                    if src_pdf and src_pdf.exists():
                        import fitz as _fitz
                        _doc = _fitz.open(str(src_pdf))
                        try:
                            if len(_doc) > 0:
                                _p = _doc[0]
                                zoom = min(page_w / _p.rect.width,
                                           page_h / _p.rect.height)
                                _m = _fitz.Matrix(zoom, zoom)
                                _pix = _p.get_pixmap(matrix=_m, alpha=False)
                                _qi = QImage(_pix.samples, _pix.width, _pix.height,
                                             _pix.stride, QImage.Format_RGB888).copy()
                                cover_pixmap = QPixmap.fromImage(_qi)
                        finally:
                            _doc.close()
            except Exception as ex:
                _log_warning(f"Cover page preview failed: {ex}")

        # Ensure we have at least one editable page
        if self._new_pdf_page_count < 1:
            self._new_pdf_page_count = 1

        # ── Render USG cover (read-only) ──────────────────────────────────
        from PySide6.QtWidgets import QFrame as _QF
        if cover_pixmap is not None and not cover_pixmap.isNull():
            cover_box = _QF()
            cover_box.setFixedSize(page_w, page_h + 22)
            cover_box.setStyleSheet(
                "background:#FFFFFF;border:2px solid #0078D4;")
            cl = QVBoxLayout(cover_box)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(0)
            cover_lbl = QLabel()
            cover_lbl.setPixmap(cover_pixmap)
            cover_lbl.setAlignment(Qt.AlignCenter)
            cl.addWidget(cover_lbl, 1)
            cf = QLabel("📄 Sayfa 1: USG Raporu (otomatik kapak)")
            cf.setAlignment(Qt.AlignCenter)
            cf.setStyleSheet(
                "color:white;background:#0078D4;"
                "font:600 10px 'Segoe UI';padding:3px;")
            cf.setMaximumHeight(22)
            cl.addWidget(cf)
            self.pdf_canvas_layout.addWidget(cover_box,
                                              alignment=Qt.AlignHCenter)

        page_offset = 1 if cover_pixmap else 0

        # ── Build interactive page widgets ────────────────────────────────
        # Render a blank white "page" pixmap (optionally with patient header)
        def _build_blank_pixmap(with_header: bool) -> QPixmap:
            pm = QPixmap(page_w, page_h)
            pm.fill(Qt.white)
            if with_header:
                try:
                    painter = QPainter(pm)
                    painter.setRenderHint(QPainter.Antialiasing)
                    # Patient header bar at top
                    hdr_rect = QRect(16, 16, page_w - 32, 60)
                    painter.fillRect(hdr_rect, QColor("#F0F4FA"))
                    painter.setPen(QColor("#6A8CB5"))
                    painter.drawRect(hdr_rect)
                    # Text
                    title_font = QFont("Segoe UI", 11, QFont.Bold)
                    painter.setFont(title_font)
                    painter.setPen(QColor("#003366"))
                    pname = (format_patient_name(self.current_patient.name)
                             if self.current_patient else "")
                    painter.drawText(
                        QRect(hdr_rect.x() + 10, hdr_rect.y() + 4,
                              hdr_rect.width() - 20, 20),
                        Qt.AlignLeft | Qt.AlignVCenter, f"HASTA: {pname}")
                    meta_font = QFont("Segoe UI", 8)
                    painter.setFont(meta_font)
                    painter.setPen(QColor("#405A7A"))
                    date_str = datetime.now().strftime("%d.%m.%Y")
                    meta_text = f"Tarih: {date_str}  ·  {get_clinic_doctor_name()}"
                    painter.drawText(
                        QRect(hdr_rect.x() + 10, hdr_rect.y() + 26,
                              hdr_rect.width() - 20, 30),
                        Qt.AlignLeft | Qt.AlignTop, meta_text)
                    painter.end()
                except Exception as _ex:
                    _log_warning("MainWindow._build_blank_pixmap", exc=_ex)
            return pm

        include_header = (self.pdf_include_header.isChecked()
                          if hasattr(self, "pdf_include_header") else False)

        for i in range(self._new_pdf_page_count):
            page_widget = PdfPageEditWidget(i, pdf_w_pts, pdf_h_pts)
            pm = _build_blank_pixmap(with_header=(i == 0 and include_header))
            page_widget.set_render(pm)
            page_widget.imageDropped.connect(self._on_new_pdf_image_dropped)
            self._new_pdf_pages.append(page_widget)

            # Wrap in a container showing page number footer
            container = _QF()
            cl = QVBoxLayout(container)
            cl.setContentsMargins(0, 0, 0, 6)
            cl.setSpacing(2)
            cl.addWidget(page_widget, alignment=Qt.AlignHCenter)
            foot = QLabel(f"— Sayfa {i + 1 + page_offset} —")
            foot.setStyleSheet(
                "color:#808080;font:400 9px 'Segoe UI';background:transparent;")
            foot.setAlignment(Qt.AlignCenter)
            cl.addWidget(foot)
            self.pdf_canvas_layout.addWidget(container,
                                              alignment=Qt.AlignHCenter)

        # ── Restore preserved overlays (pre-existing doctor placements) ──
        # Expand page count if the preserved state needs more pages
        max_preserved_page = 0
        if preserved_images:
            max_preserved_page = max(p[0] for p in preserved_images)
        if preserved_texts:
            max_preserved_page = max(max_preserved_page,
                                     max(p[0] for p in preserved_texts))
        if max_preserved_page >= len(self._new_pdf_pages):
            # Need more pages
            needed = max_preserved_page + 1 - len(self._new_pdf_pages)
            for _ in range(needed):
                i = len(self._new_pdf_pages)
                page_widget = PdfPageEditWidget(i, pdf_w_pts, pdf_h_pts)
                page_widget.set_render(_build_blank_pixmap(with_header=False))
                page_widget.imageDropped.connect(self._on_new_pdf_image_dropped)
                self._new_pdf_pages.append(page_widget)
                container = _QF()
                cl = QVBoxLayout(container)
                cl.setContentsMargins(0, 0, 0, 6)
                cl.setSpacing(2)
                cl.addWidget(page_widget, alignment=Qt.AlignHCenter)
                foot = QLabel(f"— Sayfa {i + 1 + page_offset} —")
                foot.setStyleSheet(
                    "color:#808080;font:400 9px 'Segoe UI';"
                    "background:transparent;")
                foot.setAlignment(Qt.AlignCenter)
                cl.addWidget(foot)
                self.pdf_canvas_layout.addWidget(
                    container, alignment=Qt.AlignHCenter)
            self._new_pdf_page_count = len(self._new_pdf_pages)

        # Now restore each overlay to its original geometry
        for pi, path, geom in preserved_images:
            if 0 <= pi < len(self._new_pdf_pages):
                try:
                    ov = OverlayImage(path, self._new_pdf_pages[pi])
                    ov.show()
                    ov.deleted.connect(
                        self._new_pdf_pages[pi]._on_overlay_deleted)
                    self._new_pdf_pages[pi].overlays.append(ov)
                    ov.setGeometry(geom)
                except Exception as ex:
                    _log_warning(f"overlay restore failed: {ex}")
        for pi, geom, text in preserved_texts:
            if 0 <= pi < len(self._new_pdf_pages):
                try:
                    self._new_pdf_pages[pi].add_text_overlay(
                        geom, text=text, mode="plain")
                except Exception as ex:
                    _log_warning(f"text overlay restore failed: {ex}")

        # Re-hydrate canvas_items onto pages as overlays (used when items
        # were added via 'double-click from gallery' or old code paths).
        pending_items = list(getattr(self, "_pdf_canvas_items", []) or [])
        if pending_items:
            # Drain them onto the pages using the same auto-layout
            target_page_idx = 0
            for item in pending_items:
                if item["type"] != "image":
                    continue
                path = Path(item["path"])
                if not path.exists():
                    continue
                # Find a page with space
                while target_page_idx < len(self._new_pdf_pages):
                    tgt = self._new_pdf_pages[target_page_idx]
                    if len(tgt.overlays) < tgt.MAX_IMAGES_PER_PAGE:
                        break
                    target_page_idx += 1
                if target_page_idx >= len(self._new_pdf_pages):
                    # Need a new page
                    self._new_pdf_page_count += 1
                    self._refresh_pdf_canvas()
                    return
                tgt = self._new_pdf_pages[target_page_idx]
                # Add centered — auto-layout kicks in for 1/2/3/4 images
                center = QPoint(tgt.width() // 2, tgt.height() // 2)
                tgt.add_overlay(path, center, notify_full=False)
            # Items have now been migrated to page widgets; clear the list
            self._pdf_canvas_items = []

        # Status
        total_pages = len(self._new_pdf_pages) + page_offset
        total_images = sum(len(p.overlays) for p in self._new_pdf_pages)
        self.pdf_page_count_lbl.setText(
            f"{total_pages} sayfa · {total_images} resim"
            + (" (1 USG kapak + düzenlenebilir sayfalar)" if cover_pixmap else ""))

    def _legacy_refresh_pdf_canvas(self):
        """Legacy preview-only canvas rebuild — kept for backward compat
        only, not used by the main flow anymore."""
        if not hasattr(self, "pdf_canvas_layout"):
            return
        # Clear current preview
        while self.pdf_canvas_layout.count() > 0:
            it = self.pdf_canvas_layout.takeAt(0)
            w = it.widget() if it else None
            if w is not None:
                w.deleteLater()

        items = list(self._pdf_canvas_items)

        # If empty, show a hint
        if not items and not self.pdf_include_header.isChecked():
            empty = QLabel(
                "Sağdaki resimleri çift tıklayarak veya sürükleyerek\n"
                "buraya ekleyin. Yazı eklemek için yukarıdaki '✏️ Yazı Ekle'.")
            empty.setStyleSheet(
                "color:#606060;font:400 12px 'Segoe UI';padding:60px 20px;"
                "background:#FFFFFF;border:1px dashed #A8A8A8;")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignCenter)
            empty.setFixedSize(460, 200)
            self.pdf_canvas_layout.addWidget(empty)
            self.pdf_page_count_lbl.setText("0 sayfa · 0 resim")
            return

        # Decide column mode
        mode = self.pdf_layout_mode.currentIndex()
        # 0=auto, 1=1-col, 2=2-col
        n_images = sum(1 for x in items if x["type"] == "image")
        if mode == 0:
            cols_per_page = 2 if n_images >= 4 else 1
        elif mode == 1:
            cols_per_page = 1
        else:
            cols_per_page = 2

        # Page geometry: A4 = 595x842 pt → preview 85%: ~506x715 (was 70%)
        # Much bigger preview per doctor's request — easier to evaluate layout.
        page_w, page_h = 506, 715
        margin = 32
        # Header (if any) takes ~80px on first page
        header_h = 80 if self.pdf_include_header.isChecked() else 0

        # ── USG COVER PAGE (auto-rendered on page 0) ──────────────────────
        # The first page of the generated PDF is always the visit's USG
        # report page 1 (unless the user disabled it in the options).
        # We render a preview thumbnail of it here so the doctor sees what
        # page 1 will look like.
        cover_pixmap: Optional[QPixmap] = None
        cover_enabled = (self.pdf_include_usg_cover.isChecked()
                         if hasattr(self, "pdf_include_usg_cover") else True)
        if cover_enabled:
            try:
                if self.current_subfolder:
                    src_pdf = get_latest_pdf_in_folder(self.current_subfolder)
                    if src_pdf and src_pdf.exists():
                        import fitz as _fitz
                        _doc = _fitz.open(str(src_pdf))
                        try:
                            if len(_doc) > 0:
                                _p = _doc[0]
                                # Scale PDF page to our preview size
                                zoom = min(page_w / _p.rect.width,
                                           page_h / _p.rect.height)
                                _m = _fitz.Matrix(zoom, zoom)
                                _pix = _p.get_pixmap(matrix=_m, alpha=False)
                                _qi = QImage(_pix.samples, _pix.width, _pix.height,
                                             _pix.stride, QImage.Format_RGB888).copy()
                                cover_pixmap = QPixmap.fromImage(_qi)
                        finally:
                            _doc.close()
            except Exception as ex:
                _log_warning(f"Cover page preview failed: {ex}")

        # Build pages: list of lists of items, each list is one page
        pages: List[List[dict]] = [[]]
        used_h = header_h
        # Each row is `cols_per_page` images side-by-side OR one text block
        row_buffer: List[dict] = []
        max_h = page_h - 2 * margin

        def flush_row():
            nonlocal used_h, row_buffer
            if not row_buffer:
                return
            # Row height: scale image to fit width slot
            slot_w = (page_w - 2 * margin - (cols_per_page - 1) * 8) // cols_per_page
            row_h = int(slot_w * 0.75) + 6  # heuristic 4:3 ratio
            if used_h + row_h > max_h:
                # New page
                pages.append([])
                used_h = 0
            for it in row_buffer:
                pages[-1].append({**it, "_w": slot_w, "_h": row_h - 6,
                                  "_cols": cols_per_page})
            used_h += row_h
            row_buffer = []

        for it in items:
            if it["type"] == "image":
                row_buffer.append(it)
                if len(row_buffer) >= cols_per_page:
                    flush_row()
            elif it["type"] == "text":
                # Flush any pending images first
                flush_row()
                # Estimate text block height
                txt_h = 20 + 14 * (len(it["content"]) // 50 + 1)
                if used_h + txt_h > max_h:
                    pages.append([])
                    used_h = 0
                pages[-1].append({**it, "_h": txt_h})
                used_h += txt_h + 8
            elif it["type"] == "page_break":
                # Force new page
                flush_row()
                pages.append([])
                used_h = 0
        flush_row()

        # Render each page as a white box with mini thumbnails
        from PySide6.QtWidgets import QFrame as _QF

        # ── Cover page (USG report page 1) ─────────────────────────────
        if cover_pixmap is not None and not cover_pixmap.isNull():
            cover_box = _QF()
            cover_box.setFixedSize(page_w, page_h)
            cover_box.setStyleSheet(
                "background:#FFFFFF;border:2px solid #0078D4;")
            cl = QVBoxLayout(cover_box)
            cl.setContentsMargins(0, 0, 0, 0)
            cl.setSpacing(0)
            cover_lbl = QLabel()
            cover_lbl.setPixmap(cover_pixmap)
            cover_lbl.setAlignment(Qt.AlignCenter)
            cl.addWidget(cover_lbl, 1)
            # Footer banner
            cf = QLabel("📄 Sayfa 1: USG Raporu (otomatik)")
            cf.setAlignment(Qt.AlignCenter)
            cf.setStyleSheet(
                "color:white;background:#0078D4;"
                "font:600 10px 'Segoe UI';padding:3px;")
            cf.setMaximumHeight(22)
            cl.addWidget(cf)
            self.pdf_canvas_layout.addWidget(cover_box,
                                              alignment=Qt.AlignHCenter)

        for page_idx, page_items in enumerate(pages):
            page_box = _QF()
            page_box.setFixedSize(page_w, page_h)
            page_box.setStyleSheet(
                "background:#FFFFFF;border:1px solid #808080;")
            pl = QVBoxLayout(page_box)
            pl.setContentsMargins(margin, margin, margin, margin)
            pl.setSpacing(6)
            # Header on page 1
            if page_idx == 0 and self.pdf_include_header.isChecked():
                hdr_lbl = QLabel(self._build_pdf_header_html())
                hdr_lbl.setStyleSheet(
                    "color:#003366;font:600 9px 'Segoe UI';"
                    "background:#F0F4FA;border:1px solid #6A8CB5;padding:4px;")
                hdr_lbl.setWordWrap(True)
                hdr_lbl.setMaximumHeight(70)
                pl.addWidget(hdr_lbl)
            # Items
            i = 0
            while i < len(page_items):
                it = page_items[i]
                if it["type"] == "image":
                    # Group consecutive images of same row
                    row_items = [it]
                    j = i + 1
                    while j < len(page_items) and page_items[j]["type"] == "image" \
                            and page_items[j].get("_cols") == it.get("_cols"):
                        row_items.append(page_items[j])
                        j += 1
                        if len(row_items) >= it.get("_cols", 1):
                            break
                    row_box = _QF()
                    rl = QHBoxLayout(row_box)
                    rl.setContentsMargins(0, 0, 0, 0)
                    rl.setSpacing(4)
                    for rit in row_items:
                        try:
                            pix = QPixmap(rit["path"])
                            if pix.isNull():
                                continue
                            scaled = pix.scaled(
                                rit["_w"], rit["_h"], Qt.KeepAspectRatio,
                                Qt.SmoothTransformation)
                            il = QLabel()
                            il.setPixmap(scaled)
                            il.setAlignment(Qt.AlignCenter)
                            il.setStyleSheet(
                                "background:#F8F8F8;border:1px solid #C0C0C0;")
                            il.setFixedSize(rit["_w"], rit["_h"])
                            rl.addWidget(il)
                        except Exception as _ex:
                            _log_warning("MainWindow._legacy_refresh_pdf_canvas", exc=_ex)
                    if it.get("_cols", 1) == 1:
                        rl.setAlignment(Qt.AlignCenter)
                    pl.addWidget(row_box)
                    i = j
                elif it["type"] == "text":
                    txt_lbl = QLabel(it["content"])
                    txt_lbl.setStyleSheet(
                        "color:#202020;font:400 9px 'Segoe UI';"
                        "background:#FFFFEC;border:1px solid #D4C580;padding:4px;")
                    txt_lbl.setWordWrap(True)
                    pl.addWidget(txt_lbl)
                    i += 1
                else:
                    i += 1
            pl.addStretch()
            # Page number footer
            pn_lbl = QLabel(f"— {page_idx + 1} / {len(pages)} —")
            pn_lbl.setStyleSheet(
                "color:#909090;font:400 8px 'Segoe UI';background:transparent;")
            pn_lbl.setAlignment(Qt.AlignCenter)
            pl.addWidget(pn_lbl)
            self.pdf_canvas_layout.addWidget(page_box, alignment=Qt.AlignHCenter)

        # Sayfa sayısı — cover page (USG) varsa +1
        has_cover = cover_pixmap is not None and not cover_pixmap.isNull()
        total_pages = len(pages) + (1 if has_cover else 0)
        page_offset = 1 if has_cover else 0
        self.pdf_page_count_lbl.setText(
            f"{total_pages} sayfa · {n_images} resim"
            + (" (1 USG kapak + resim sayfaları)" if has_cover else ""))

    def _rebuild_editor_thumbnails(self):
        """Refresh the draggable thumbnail palette in the PDF editor tab.
        Thumbnails can be drag-dropped onto any PDF page (handled by
        PdfPageEditWidget.dropEvent) or double-clicked to add on the
        last page via auto-layout.

        Images that have already been added to the PDF are hidden from
        the palette — the doctor asked that the same image not be shown
        twice on the side once it's been placed on a page.
        """
        if not hasattr(self, "editor_thumb_layout"):
            return
        # Clear existing
        while self.editor_thumb_layout.count() > 1:
            item = self.editor_thumb_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        if not self.current_subfolder:
            return

        # Build the set of images already placed on ANY PDF page
        used_paths = set()
        if hasattr(self, "pdf_editor"):
            try:
                for pw in self.pdf_editor.pages():
                    for ov in pw.overlays:
                        try:
                            used_paths.add(str(Path(ov.image_path).resolve()))
                        except Exception:
                            used_paths.add(str(ov.image_path))
            except Exception as _ex:
                _log_warning("MainWindow._rebuild_editor_thumbnails", exc=_ex)

        image_files = [f for f in (self.current_files or [])
                       if f.suffix.lower() in IMAGE_EXTS]
        for f in image_files:
            try:
                fp_key = str(f.resolve())
            except Exception:
                fp_key = str(f)
            if fp_key in used_paths:
                continue  # already placed — don't show duplicate
            pix = self._make_thumbnail(f)
            thumb = DraggableThumb(f, pix)
            thumb.setFixedSize(250, 180)
            thumb.setIconSize(QSize(240, 160))
            thumb.setToolTip(
                f"{f.name}\n\nSürükle → PDF sayfasına bırak\n"
                f"veya çift tık → son sayfaya ekle")
            def _make_double_handler(path):
                def _h(event):
                    self._editor_add_image_to_last_page(path)
                return _h
            thumb.mouseDoubleClickEvent = _make_double_handler(f)
            self.editor_thumb_layout.insertWidget(
                self.editor_thumb_layout.count() - 1, thumb)

    def _editor_select_pages_dialog(self):
        """Show a checklist of PDF pages. Unchecked pages will be SKIPPED
        when the user saves the PDF. The cover page (page 1) is ALWAYS
        kept — its checkbox is disabled so it can't be unchecked.

        This lets the doctor quickly decide which of the Voluson PDF's
        pages end up in the final document — very useful when the original
        has a bunch of boilerplate pages the patient doesn't need."""
        if not hasattr(self, "pdf_editor") or not self.pdf_editor.current_pdf():
            QMessageBox.information(
                self, "PDF Yok",
                "Önce bir hastanın PDF'ini yükleyin (geliş seçin).")
            return
        pages = self.pdf_editor.pages()
        if not pages:
            return

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("PDF Sayfalarını Seç")
        dlg.resize(440, 540)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)

        hdr = QLabel(
            "<b>Kaydedilecek sayfaları seçin:</b><br>"
            "<span style='color:#606060;font-size:11px;'>"
            "İşaretlenmeyen sayfalar son PDF'e dahil edilmez. "
            "Kapak sayfası (Sayfa 1) her zaman korunur.</span>")
        hdr.setTextFormat(Qt.RichText)
        hdr.setWordWrap(True)
        v.addWidget(hdr)

        # Scrollable checkbox list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea{border:1px solid #C8C8C8;background:#FAFAFA;}")
        inner = QWidget()
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(8, 8, 8, 8)
        inner_lay.setSpacing(2)

        disabled_now = set(self.pdf_editor._disabled_pages)
        checkboxes = []
        for i, pw in enumerate(pages):
            is_cover = (i == 0)
            n_img = len(pw.overlays)
            n_txt = len(pw.text_overlays)
            badges = []
            if n_img:
                badges.append(f"🖼 {n_img}")
            if n_txt:
                badges.append(f"✏ {n_txt}")
            badge_str = "   " + " · ".join(badges) if badges else ""
            label = f"Sayfa {i + 1}{' (Kapak)' if is_cover else ''}{badge_str}"
            cb = QCheckBox(label)
            # Default: all enabled except ones the doctor already disabled
            cb.setChecked(is_cover or i not in disabled_now)
            if is_cover:
                cb.setEnabled(False)  # can't uncheck cover
                cb.setStyleSheet("color:#606060;font-style:italic;")
            else:
                cb.setStyleSheet(
                    "QCheckBox{padding:4px;font:500 12px 'Segoe UI';}"
                    "QCheckBox:hover{background:#E5EEF7;}")
            inner_lay.addWidget(cb)
            checkboxes.append((i, cb))
        inner_lay.addStretch(1)
        scroll.setWidget(inner)
        v.addWidget(scroll, 1)

        # Quick-select buttons
        quick_row = QHBoxLayout()
        btn_all = QPushButton("Tümünü Seç")
        btn_none = QPushButton("Sadece Kapak")
        def _all():
            for _, cb in checkboxes:
                if cb.isEnabled():
                    cb.setChecked(True)
        def _only_cover():
            for idx, cb in checkboxes:
                if cb.isEnabled():
                    cb.setChecked(False)
        btn_all.clicked.connect(_all)
        btn_none.clicked.connect(_only_cover)
        quick_row.addWidget(btn_all)
        quick_row.addWidget(btn_none)
        quick_row.addStretch()
        v.addLayout(quick_row)

        # Cancel / OK
        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("İptal")
        ok_btn = QPushButton("✓ Uygula")
        ok_btn.setDefault(True)
        ok_btn.setStyleSheet(
            "QPushButton{background:#0078D4;color:white;font:600 12px 'Segoe UI';"
            "padding:6px 16px;border:none;border-radius:3px;}"
            "QPushButton:hover{background:#005A9E;}")
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        v.addLayout(btn_row)

        cancel_btn.clicked.connect(dlg.reject)
        ok_btn.clicked.connect(dlg.accept)

        if dlg.exec() != QDialog.Accepted:
            return

        # Update _disabled_pages based on checkboxes
        new_disabled = set()
        for idx, cb in checkboxes:
            if not cb.isChecked() and idx > 0:  # cover never disabled
                new_disabled.add(idx)
        self.pdf_editor._disabled_pages = new_disabled

        # Visual feedback: add a grey overlay on disabled pages so the
        # doctor sees which ones won't be saved
        for i, pw in enumerate(pages):
            try:
                if i in new_disabled:
                    pw.setStyleSheet(
                        "background:#FFFFFF;border:2px dashed #C42B1C;"
                        "opacity:0.5;")
                else:
                    pw.setStyleSheet(
                        "background:#FFFFFF;border:1px solid #ABABAB;")
            except Exception as _ex:
                _log_warning("MainWindow._editor_select_pages_dialog", exc=_ex)

        kept = len(pages) - len(new_disabled)
        if new_disabled:
            self.editor_status_label.setText(
                f"✓ {kept} sayfa seçili · {len(new_disabled)} sayfa "
                f"kaydedildiğinde atlanacak")
        else:
            self.editor_status_label.setText(
                f"✓ Tüm sayfalar ({kept}) kaydedilecek")

    def _editor_delete_current_page(self):
        """Delete the currently-visible PDF page in Ana PDF.
        Records an undo entry so the doctor can restore it."""
        if not hasattr(self, "pdf_editor") or not self.pdf_editor.current_pdf():
            self.statusBar().showMessage(
                "PDF yüklü değil — silinecek sayfa yok", 3000)
            return
        pages = self.pdf_editor.pages()
        if len(pages) <= 1:
            QMessageBox.information(
                self, "Son Sayfa",
                "Bu PDF'in sadece bir sayfası var — silinemez.\n\n"
                "Sayfayı temizlemek için resimleri tek tek silebilirsiniz.")
            return
        idx = self.pdf_editor.current_visible_page_index()
        if idx < 0:
            idx = 0
        # Confirm
        resp = QMessageBox.question(
            self, "Sayfayı Sil",
            f"Sayfa {idx + 1} silinsin mi?\n\n"
            f"(Sayfa üzerindeki tüm resimler ve yazılar da silinir. "
            f"Geri almak için Ctrl+Z kullanın.)",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if resp != QMessageBox.Yes:
            return

        # Collect content for undo (path + geometry of every overlay)
        target_page = pages[idx]
        undo_data = {
            "kind": "delete_page",
            "page_idx": idx,
            "overlays": [(ov.image_path, QRect(ov.geometry()))
                         for ov in target_page.overlays],
            "texts": [(QRect(tov.geometry()),
                       getattr(tov, "text", "") or "")
                      for tov in target_page.text_overlays],
        }

        try:
            self.pdf_editor.delete_page(idx)
        except Exception as ex:
            QMessageBox.critical(
                self, "Silme Hatası",
                f"Sayfa silinemedi:\n{ex}")
            return

        self._push_undo(undo_data)
        # Reconnect drop handlers
        for page_w in self.pdf_editor.pages():
            try:
                page_w.imageDropped.disconnect()
            except Exception as _ex:
                _log_warning("MainWindow._editor_delete_current_page", exc=_ex)
            page_w.imageDropped.connect(self._on_editor_image_dropped)
        self.statusBar().showMessage(
            f"✓ Sayfa {idx + 1} silindi · Ctrl+Z ile geri alabilirsiniz",
            5000)

    def _editor_apply_layout_to_visible(self):
        """Arrange the images on the currently visible Ana PDF page into
        a 2/3/4-column grid (or let auto-layout choose by count). The
        doctor triggers this via the 'Düzen → Uygula' toolbar combo."""
        if not hasattr(self, "pdf_editor") or not self.pdf_editor.current_pdf():
            self.statusBar().showMessage(
                "PDF yüklü değil — önce bir hastanın gelişini seçin", 3000)
            return
        pages = self.pdf_editor.pages()
        if not pages:
            return
        idx = self.pdf_editor.current_visible_page_index()
        if not (0 <= idx < len(pages)):
            return
        pw = pages[idx]
        if len(pw.overlays) == 0:
            self.statusBar().showMessage(
                "Görünen sayfada düzene sokulacak resim yok", 3000)
            return
        # If text overlays are present, warn — auto-layout may overlap them
        if pw.text_overlays:
            resp = QMessageBox.question(
                self, "Düzen Uygula",
                "Bu sayfada yazı bulunuyor — otomatik düzen yazıların "
                "üzerine gelebilir.\n\nYine de devam edilsin mi?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if resp != QMessageBox.Yes:
                return

        mode = self.editor_layout_combo.currentData()
        n = len(pw.overlays)
        try:
            # Existing auto-layout helpers require overlays.len >= N to run.
            # For a manual "apply" action we don't want that gate — the
            # doctor explicitly chose a layout. We temporarily pad the
            # overlays list is not safe; the cleanest path is to call the
            # existing helpers and rely on len(self.overlays) matching.
            # If mode asks for more slots than we have images, we fall back
            # to auto (by count).
            if mode == "two" and n >= 2:
                pw._auto_layout_two_images()
            elif mode == "three" and n >= 3:
                pw._auto_layout_three_images()
            elif mode == "four" and n >= 4:
                pw._auto_layout_four_images()
            elif mode == "six" and n >= 5:
                pw._auto_layout_six_images()
            elif mode == "nine" and n >= 7:
                pw._auto_layout_nine_images()
            else:
                # auto or mode chose too many slots — use by-count
                if n == 2:
                    pw._auto_layout_two_images()
                elif n == 3:
                    pw._auto_layout_three_images()
                elif n == 4:
                    pw._auto_layout_four_images()
                elif n in (5, 6):
                    pw._auto_layout_six_images()
                elif n >= 7:
                    pw._auto_layout_nine_images()
        except Exception as ex:
            _log_warning(f"apply layout failed: {ex}")
            return
        self.statusBar().showMessage(
            f"✓ Sayfa {idx + 1}: {n} resim '{self.editor_layout_combo.currentText()}' "
            f"düzenine yerleştirildi", 3000)

    def _editor_add_blank_page(self):
        """Toolbar "+ Yeni Sayfa" handler: append a blank A4 page to
        the Ana PDF editor. Reconnect drop handlers so the new page
        accepts image drops too."""
        if not hasattr(self, "pdf_editor") or not self.pdf_editor.current_pdf():
            QMessageBox.information(
                self, "PDF Yok",
                "Önce bir hastanın PDF'ini yükleyin (hasta seçin).\n\n"
                "Ana PDF mevcut bir USG raporunun üzerine çalışır.")
            return
        new_idx = self.pdf_editor.add_blank_page()
        if new_idx < 0:
            return
        # Reconnect drop handlers for every page (including the new one)
        for page_w in self.pdf_editor.pages():
            try:
                page_w.imageDropped.disconnect()
            except Exception as _ex:
                _log_warning("MainWindow._editor_add_blank_page", exc=_ex)
            page_w.imageDropped.connect(self._on_editor_image_dropped)
        self.statusBar().showMessage(
            f"✓ Ana PDF'e yeni sayfa eklendi (toplam {len(self.pdf_editor.pages())} sayfa)",
            3000)

    def _editor_add_image_to_last_page(self, path: Path):
        """Add an image to the last PDF page. Called from double-click on
        a thumbnail in the editor's right-side panel."""
        if not hasattr(self, "pdf_editor") or not self.pdf_editor._pages:
            self.statusBar().showMessage(
                "PDF yüklü değil — önce bir geliş seçin", 3000)
            return
        last_page = self.pdf_editor._pages[-1]
        # Drop at center of the page (auto-layout will re-arrange)
        center = QPoint(last_page.width() // 2, last_page.height() // 2)
        # Trigger the same pipeline as a drag-drop would
        try:
            last_page.imageDropped.emit(last_page.page_index, path, center)
            self.statusBar().showMessage(
                f"✓ {path.name} PDF'in son sayfasına eklendi", 3000)
        except Exception as ex:
            _log_warning(f"double-click add image failed: {ex}")

    def _reload_editor_pdf(self):
        """Load the current visit's PDF into the editor."""
        if not hasattr(self, "pdf_editor"):
            return
        pdf = (get_latest_pdf_in_folder(self.current_subfolder)
               if self.current_subfolder else None)
        # Clear any pending modifications from the previous visit/PDF
        self.pdf_editor.clear_pending_templates()
        self._update_template_queue_label()
        self._clear_undo()

        self.pdf_editor.load_pdf(pdf)
        # Wire up drop signal for each page
        for page_w in self.pdf_editor.pages():
            try:
                page_w.imageDropped.disconnect()
            except Exception as _ex:
                _log_warning("MainWindow._reload_editor_pdf", exc=_ex)
            page_w.imageDropped.connect(self._on_editor_image_dropped)
        if pdf:
            self.editor_status_label.setText(f"Yüklendi: {pdf.name}")
        else:
            self.editor_status_label.setText("Bu gelişte PDF yok.")

    def _on_editor_image_dropped(self, page_index: int, path: Path, drop_pt: QPoint):
        if not hasattr(self, "pdf_editor"):
            return
        actual = self.pdf_editor.drop_image_auto(page_index, path, drop_pt)
        if actual < 0:
            self.editor_status_label.setText("Resim eklenemedi.")
            return
        # After drop_image_auto may have re-rendered, re-connect drop handlers
        for page_w in self.pdf_editor.pages():
            try:
                page_w.imageDropped.disconnect()
            except Exception as _ex:
                _log_warning("MainWindow._on_editor_image_dropped", exc=_ex)
            page_w.imageDropped.connect(self._on_editor_image_dropped)
        self._push_undo({"kind": "overlay", "page": actual, "path": path})
        # Rebuild the side panel so the added image doesn't appear twice
        try:
            self._rebuild_editor_thumbnails()
        except Exception as _ex:
            _log_warning("MainWindow._on_editor_image_dropped", exc=_ex)
        if actual != page_index:
            self.editor_status_label.setText(
                f"Sayfa {page_index + 1} doluydu — sayfa {actual + 1}'e eklendi"
            )
        else:
            self.editor_status_label.setText(
                f"Sayfa {actual + 1}: {path.name} eklendi"
            )

    def _editor_add_text(self):
        """Add a free-text overlay on the currently visible page."""
        if not hasattr(self, "pdf_editor") or not self.pdf_editor.current_pdf():
            self.statusBar().showMessage(
                "Önce bir PDF yüklemek için bir geliş seçin", 3000)
            return
        tov = self.pdf_editor.add_text_to_visible_page(
            text="Yazı... (çift tıklayıp düzenleyin)",
            mode="plain", font_size_pt=11, color="#202020",
            approx_w=260, approx_h=60,
        )
        if tov is not None:
            self._push_undo({"kind": "text_overlay", "overlay": tov,
                             "page": self.pdf_editor.current_visible_page_index()})
            self.editor_status_label.setText(
                "Yazı kutusu eklendi — çift tıklayıp metni değiştirebilirsin")

    def _editor_add_redact(self):
        """Add a white 'redaction' rectangle with editable text."""
        if not hasattr(self, "pdf_editor") or not self.pdf_editor.current_pdf():
            self.statusBar().showMessage(
                "Önce bir PDF yüklemek için bir geliş seçin", 3000)
            return
        tov = self.pdf_editor.add_text_to_visible_page(
            text="...", mode="redact",
            font_size_pt=11, color="#202020",
            approx_w=220, approx_h=36,
        )
        if tov is not None:
            self._push_undo({"kind": "text_overlay", "overlay": tov,
                             "page": self.pdf_editor.current_visible_page_index()})
            self.editor_status_label.setText(
                "Beyaz örtü eklendi — altındaki yazıyı örtmek için boyutlandırın")

    def _editor_add_stamp(self):
        """Show preset-stamp picker and place the selected stamp."""
        if not hasattr(self, "pdf_editor") or not self.pdf_editor.current_pdf():
            self.statusBar().showMessage(
                "Önce bir PDF yüklemek için bir geliş seçin", 3000)
            return
        presets = [
            ("KOPYA",            "#C46500"),
            ("KONTROL",          "#0078D4"),
            ("GÖZDEN GEÇİRİLDİ", "#107C10"),
            ("İMZALANDI",        "#107C10"),
            ("ACİL",             "#C42B1C"),
            ("TAKİP",            "#8764B8"),
            ("ÖRNEKTİR",         "#606060"),
        ]
        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("Damga seç")
        dlg.resize(340, 360)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)
        title = QLabel("Hangi damgayı eklemek istersiniz?")
        title.setStyleSheet("font:600 12px 'Segoe UI';color:#202020;")
        lay.addWidget(title)
        for label, color in presets:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(34)
            btn.setStyleSheet(
                f"QPushButton{{border:2px solid {color};color:{color};"
                f"background:#FFF8E0;font:700 13px 'Segoe UI';padding:4px 12px;}}"
                f"QPushButton:hover{{background:#FFEFC8;}}"
            )
            btn.clicked.connect(lambda _c=False, lbl=label, col=color:
                                (self._place_stamp(lbl, col), dlg.accept()))
            lay.addWidget(btn)

        # Custom stamp at the bottom
        custom_row = QHBoxLayout()
        custom_input = QLineEdit()
        custom_input.setPlaceholderText("Özel damga metni...")
        custom_input.setStyleSheet("padding:6px;font:400 12px 'Segoe UI';")
        add_btn = QPushButton("Ekle")
        add_btn.clicked.connect(lambda: (
            self._place_stamp(
                custom_input.text().strip().upper() or "DAMGA",
                "#0078D4") if custom_input.text().strip() else None,
            dlg.accept() if custom_input.text().strip() else None,
        ))
        custom_row.addWidget(custom_input, 1)
        custom_row.addWidget(add_btn)
        lay.addLayout(custom_row)

        lay.addStretch()
        cancel = QPushButton("İptal"); cancel.clicked.connect(dlg.reject)
        lay.addWidget(cancel)
        dlg.exec()

    def _editor_clear_all(self):
        if not hasattr(self, "pdf_editor"):
            return
        if not self.pdf_editor.has_changes():
            return
        resp = QMessageBox.question(
            self, "Temizle",
            "Eklenen resimler ve bekleyen şablon metinleri\n"
            "temizlenecek. Emin misiniz?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if resp == QMessageBox.Yes:
            self.pdf_editor.clear_all_overlays()
            self.pdf_editor.clear_pending_templates()
            self._update_template_queue_label()
            self._clear_undo()
            self.editor_status_label.setText("Tüm düzenlemeler temizlendi.")

    def _editor_save(self):
        if not hasattr(self, "pdf_editor") or not self.pdf_editor.current_pdf():
            QMessageBox.warning(self, "Uyarı", "Kaydedilecek PDF yok.")
            return
        if not self.pdf_editor.has_changes():
            self.statusBar().showMessage(
                "Hiç değişiklik yok — kaydedilecek bir şey yok", 3000)
            return
        resp = QMessageBox.question(
            self, "Orijinali değiştir",
            "Orijinal PDF'in üzerine yazılacak. Devam?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if resp != QMessageBox.Yes:
            return
        try:
            self.editor_status_label.setText("Kaydediliyor...")
            QApplication.processEvents()
            target = self.pdf_editor.save_pdf()
            self.editor_status_label.setText(f"✓ Kaydedildi: {target.name}")
            self.statusBar().showMessage(
                f"✓ PDF güncellendi: {target.name}", 5000)
            # Refresh the summary-tab viewer so the change is visible immediately
            try:
                self.pdf_viewer.load_pdf(target)
            except Exception as _ex:
                _log_warning("MainWindow._editor_save", exc=_ex)
            # All pending modifications are now baked in — reset the UI
            self.pdf_editor.clear_pending_templates()
            self._update_template_queue_label()
            self._clear_undo()
            # Reload editor from disk so overlays are baked and it's clean
            self._reload_editor_pdf()
        except Exception as e:
            self.editor_status_label.setText(f"Hata: {e}")
            QMessageBox.critical(self, "Kaydetme Hatası", f"Dosya kaydedilirken hata oluştu:\n\n{e}")

    def _editor_save_as(self):
        if not hasattr(self, "pdf_editor") or not self.pdf_editor.current_pdf():
            QMessageBox.warning(self, "Uyarı", "Kaydedilecek PDF yok.")
            return
        if not self.pdf_editor.has_changes():
            self.statusBar().showMessage(
                "Hiç değişiklik yok — kaydedilecek bir şey yok", 3000)
            return
        src = self.pdf_editor.current_pdf()
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"{src.stem}_duzenli_{ts}.pdf"
        default_path = (self.current_subfolder or src.parent) / default_name
        out_str, _ = QFileDialog.getSaveFileName(
            self, "PDF'i farklı kaydet", str(default_path),
            "PDF Dosyası (*.pdf)")
        if not out_str:
            return
        out_path = Path(out_str)
        if out_path.suffix.lower() != ".pdf":
            out_path = out_path.with_suffix(".pdf")
        try:
            self.editor_status_label.setText("Kaydediliyor...")
            QApplication.processEvents()
            target = self.pdf_editor.save_pdf(out_path)
            self.editor_status_label.setText(f"✓ Kaydedildi: {target.name}")
            # Pending templates are one-shot — clear them even on Save As
            self.pdf_editor.clear_pending_templates()
            self._update_template_queue_label()
            self.statusBar().showMessage(
                f"✓ PDF kaydedildi: {target.name}", 5000)
        except Exception as e:
            self.editor_status_label.setText(f"Hata: {e}")
            QMessageBox.critical(self, "Kaydetme Hatası", f"Dosya kaydedilirken hata oluştu:\n\n{e}")

    def _editor_undo(self):
        """Undo the most recent editor action."""
        if not hasattr(self, "_editor_undo_stack") or not self._editor_undo_stack:
            return
        entry = self._editor_undo_stack.pop()
        kind = entry.get("kind")

        if kind == "overlay":
            # Remove the most recently added overlay on that page
            pages = self.pdf_editor.pages()
            pi = entry["page"]
            if 0 <= pi < len(pages):
                pw = pages[pi]
                # Pop by path match from the end (most recent wins)
                target_path = entry["path"]
                for ov in reversed(pw.overlays):
                    if ov.image_path == target_path:
                        pw._on_overlay_deleted(ov)  # also re-lays-out remaining
                        break
            msg = "Son resim kaldırıldı"

        elif kind == "template":
            popped = self.pdf_editor.pop_pending_template()
            self._update_template_queue_label()
            msg = "Son şablon metni geri alındı" if popped else "Geri alınacak şablon yok"

        elif kind == "text_overlay":
            ov = entry.get("overlay")
            if ov is not None:
                # The overlay may already be deleted by the user — guard it
                try:
                    parent = ov.parent()
                    if parent is not None and ov in getattr(parent, "text_overlays", []):
                        parent._on_text_overlay_deleted(ov)
                except Exception as _ex:
                    _log_warning("MainWindow._editor_undo", exc=_ex)
            msg = "Son yazı/damga kaldırıldı"

        elif kind == "delete_page":
            # Undo Ana PDF page deletion — reinsert a blank page at the
            # deleted index and repopulate its overlays/texts
            page_idx = entry.get("page_idx", 0)
            overlays = entry.get("overlays", [])
            texts = entry.get("texts", [])
            try:
                # Bump blank-page count (rebuild will show one more page)
                self.pdf_editor._extra_blank_pages += 1
                # Prepare restore plan — images & texts go onto the new page
                self.pdf_editor._pending_restore_images = []
                self.pdf_editor._pending_restore_texts = []
                # First, collect current contents of all surviving pages
                # mapped to their ORIGINAL indices (pre-deletion)
                for pi, pw in enumerate(self.pdf_editor.pages()):
                    # If pi < page_idx: keep same index
                    # If pi >= page_idx: shift up by one
                    orig_idx = pi if pi < page_idx else pi + 1
                    for ov in pw.overlays:
                        self.pdf_editor._pending_restore_images.append(
                            (orig_idx, ov.image_path, QRect(ov.geometry())))
                    for tov in pw.text_overlays:
                        self.pdf_editor._pending_restore_texts.append(
                            (orig_idx, QRect(tov.geometry()),
                             getattr(tov, "text", "") or "",
                             getattr(tov, "mode", "plain"),
                             getattr(tov, "font_size_pt", 11),
                             getattr(tov, "color", "#202020")))
                # Now add the deleted page's contents targeting page_idx
                for img_path, rect in overlays:
                    self.pdf_editor._pending_restore_images.append(
                        (page_idx, img_path, rect))
                for rect, text in texts:
                    self.pdf_editor._pending_restore_texts.append(
                        (page_idx, rect, text, "plain", 11, "#202020"))
                self.pdf_editor._refresh_view_preserving_overlays()
                # Reconnect drop handlers
                for page_w in self.pdf_editor.pages():
                    try:
                        page_w.imageDropped.disconnect()
                    except Exception as _ex:
                        _log_warning("MainWindow._editor_undo", exc=_ex)
                    page_w.imageDropped.connect(self._on_editor_image_dropped)
                msg = f"Sayfa {page_idx + 1} geri yüklendi"
            except Exception as ex:
                _log_warning(f"delete_page undo failed: {ex}")
                msg = "Sayfa geri yüklenemedi"

        elif kind == "delete_newpdf_page":
            # Undo Yeni PDF page deletion — increase the page count and
            # restore the overlays/texts onto the new last page
            try:
                self._new_pdf_page_count = getattr(
                    self, "_new_pdf_page_count", 1) + 1
                self._refresh_pdf_canvas()
                # Re-add overlays/texts to the (now last) page
                if self._new_pdf_pages:
                    page_idx = entry.get("page_idx", len(self._new_pdf_pages) - 1)
                    if page_idx >= len(self._new_pdf_pages):
                        page_idx = len(self._new_pdf_pages) - 1
                    target = self._new_pdf_pages[page_idx]
                    for img_path, rect in entry.get("overlays", []):
                        try:
                            ov = OverlayImage(img_path, target)
                            ov.show()
                            ov.deleted.connect(target._on_overlay_deleted)
                            target.overlays.append(ov)
                            ov.setGeometry(rect)
                        except Exception as _ex:
                            _log_warning("MainWindow._editor_undo", exc=_ex)
                    for rect, text in entry.get("texts", []):
                        try:
                            target.add_text_overlay(
                                rect, text=text, mode="plain")
                        except Exception as _ex:
                            _log_warning("MainWindow._editor_undo", exc=_ex)
                msg = "Yeni PDF sayfası geri yüklendi"
            except Exception as ex:
                _log_warning(f"newpdf delete undo failed: {ex}")
                msg = "Sayfa geri yüklenemedi"

        else:
            msg = "Bilinmeyen işlem"

        # Update button state
        if not self._editor_undo_stack:
            self.editor_undo_btn.setEnabled(False)
        self.editor_status_label.setText(msg)
