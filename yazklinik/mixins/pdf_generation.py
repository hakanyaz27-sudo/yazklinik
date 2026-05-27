"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _PdfGenerationMixin
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

class _PdfGenerationMixin:
    """MainWindow methods related to PdfGeneration. Mixed into MainWindow via MRO."""

    def _pdf_add_template_block(self):
        """Dialog: pick a saved template and add it as a text block to the
        Yeni PDF canvas. Templates live in the pdf_templates DB table
        and are shared across all PDF-generation flows.
        """
        try:
            tmpls = list_templates()
        except Exception as ex:
            QMessageBox.critical(
                self, "Şablon Hatası",
                f"Şablonlar yüklenemedi:\n\n{ex}")
            return
        if not tmpls:
            resp = QMessageBox.question(
                self, "Şablon Yok",
                "Henüz kayıtlı şablon yok.\n\n"
                "Şablon oluşturmak ister misiniz? "
                "(Ana PDF → 📝 Şablon Ekle → Yeni)",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if resp == QMessageBox.Yes:
                try:
                    self._open_templates_dialog()
                except Exception as _ex:
                    _log_warning("MainWindow._pdf_add_template_block", exc=_ex)
            return

        # Build a picker dialog with a list of titles
        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("Şablon Seç")
        dlg.resize(620, 500)
        v = QVBoxLayout(dlg)

        v.addWidget(QLabel(
            "<b>PDF'e eklenecek şablonu seçin:</b><br>"
            "<span style='color:#606060;font-size:10px;'>"
            "Seçtiğiniz şablon resimlerin arasına veya sonuna yazı bloğu "
            "olarak yerleştirilir.</span>"))

        lst = QListWidget()
        lst.setStyleSheet(
            "QListWidget{background:white;border:1px solid #C8C8C8;}"
            "QListWidget::item{padding:6px 8px;border-bottom:1px solid #F0F0F0;}"
            "QListWidget::item:selected{background:#E5EEF7;color:#003366;}")
        for tid, title, body in tmpls:
            item = QListWidgetItem(title)
            # Store body as user data so we can grab it on selection
            item.setData(Qt.UserRole, body)
            item.setToolTip(body[:400] + ("..." if len(body) > 400 else ""))
            lst.addItem(item)
        v.addWidget(lst, 1)

        # Preview area
        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setMaximumHeight(140)
        preview.setPlaceholderText("Şablon önizlemesi burada görünecek...")
        preview.setStyleSheet(
            "QTextEdit{background:#FFFFF4;border:1px solid #D4C56A;"
            "font:500 11px 'Segoe UI';padding:6px;}")
        v.addWidget(preview)

        def _on_select():
            it = lst.currentItem()
            if it is not None:
                body = it.data(Qt.UserRole) or ""
                preview.setPlainText(body)
        lst.currentItemChanged.connect(lambda _c, _p: _on_select())
        # Auto-select first
        if lst.count() > 0:
            lst.setCurrentRow(0)

        # Buttons
        btn_row = QHBoxLayout()
        add_btn = QPushButton("✓ Seçileni Ekle")
        add_btn.setStyleSheet(
            "QPushButton{background:#0078D4;color:white;padding:8px 22px;"
            "font:600 12px;border:none;border-radius:3px;}"
            "QPushButton:hover{background:#106EBE;}")
        cancel_btn = QPushButton("İptal")
        cancel_btn.setShortcut("Escape")
        add_btn.clicked.connect(dlg.accept)
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addStretch()
        btn_row.addWidget(add_btn)
        btn_row.addWidget(cancel_btn)
        v.addLayout(btn_row)

        if dlg.exec() == QDialog.Accepted:
            it = lst.currentItem()
            if it is not None:
                body = it.data(Qt.UserRole) or ""
                if body.strip():
                    # Add as an interactive text overlay on the last page.
                    # Doctor can drag/resize it like an image — much more
                    # flexible than the old 'append to canvas items' flow.
                    if (hasattr(self, "_new_pdf_pages")
                            and self._new_pdf_pages):
                        target = self._new_pdf_pages[-1]
                        # Default position: lower half of page, full-width strip
                        W, H = target.width(), target.height()
                        if W <= 0 or H <= 0:
                            # Widget not yet sized — fall back to queue
                            self._pdf_canvas_items.append(
                                {"type": "text",
                                 "content": body.strip()})
                            self._refresh_pdf_canvas()
                        else:
                            margin = max(20, int(min(W, H) * 0.04))
                            # Estimate height from body length
                            lines = max(3, body.count("\n") + 1
                                        + len(body) // 80)
                            est_h = min(H - 2 * margin,
                                        max(80, lines * 14 + 20))
                            rect = QRect(
                                margin, H - margin - est_h,
                                W - 2 * margin, est_h)
                            target.add_text_overlay(
                                rect, text=body.strip(),
                                mode="plain", font_size_pt=10,
                                color="#202020")
                        self.pdf_status_label.setText(
                            f"+ Şablon eklendi: {it.text()} · "
                            f"sürükleyerek taşıyabilirsiniz")
                    else:
                        # No page widgets yet — fall back to legacy queue
                        if not hasattr(self, "_pdf_canvas_items"):
                            self._pdf_canvas_items = []
                        self._pdf_canvas_items.append(
                            {"type": "text", "content": body.strip()})
                        self._refresh_pdf_canvas()
                        self.pdf_status_label.setText(
                            f"+ Şablon eklendi: {it.text()}")

    def _save_current_layout_as_template(self):
        """Serialise the current Yeni PDF arrangement to the DB as a
        reusable template. Captures per-page: image SLOTS (positions +
        sizes as fractions 0-1 of page dimensions) and text overlays
        (text content + position + style). Images themselves aren't
        saved — the doctor will drop new images into the saved slots."""
        if not hasattr(self, "_new_pdf_pages") or not self._new_pdf_pages:
            QMessageBox.information(
                self, "Boş Düzen",
                "Şablon olarak kaydedilecek bir düzen yok.\n\n"
                "Önce Yeni PDF sekmesinde birkaç resim/yazı yerleştirin.")
            return

        # Ask for a title
        title, ok = QInputDialog.getText(
            self, "Şablonu Kaydet",
            "Şablon adı:\n(örn. '2x2 grid + alt yazı', 'Nipt sonuç', "
            "'USG 4'lü')", text="Yeni Şablon")
        if not ok or not title.strip():
            return
        title = title.strip()

        # Build the layout JSON
        import json as _json
        layout = {"pages": []}
        for pw in self._new_pdf_pages:
            W = pw.width() or 1
            H = pw.height() or 1
            page_data = {"slots": [], "texts": []}
            for ov in pw.overlays:
                g = ov.geometry()
                page_data["slots"].append({
                    "x": round(g.x() / W, 4),
                    "y": round(g.y() / H, 4),
                    "w": round(g.width() / W, 4),
                    "h": round(g.height() / H, 4),
                })
            for tov in pw.text_overlays:
                g = tov.geometry()
                page_data["texts"].append({
                    "x": round(g.x() / W, 4),
                    "y": round(g.y() / H, 4),
                    "w": round(g.width() / W, 4),
                    "h": round(g.height() / H, 4),
                    "text": getattr(tov, "text", "") or "",
                    "mode": getattr(tov, "mode", "plain"),
                    "font_size": getattr(tov, "font_size_pt", 11),
                    "color": (tov.color.name()
                              if hasattr(tov, "color") else "#202020"),
                })
            layout["pages"].append(page_data)

        try:
            tid = db_save_layout_template(title, _json.dumps(layout))
        except Exception as ex:
            QMessageBox.critical(
                self, "Hata",
                f"Şablon kaydedilemedi:\n{ex}")
            return
        if tid is None:
            QMessageBox.warning(self, "Hata",
                                "Şablon veritabanına yazılamadı.")
            return
        total_slots = sum(len(p["slots"]) for p in layout["pages"])
        total_texts = sum(len(p["texts"]) for p in layout["pages"])
        self.statusBar().showMessage(
            f"✓ '{title}' şablonu kaydedildi "
            f"({len(layout['pages'])} sayfa · {total_slots} resim · "
            f"{total_texts} yazı)", 5000)

    def _apply_layout_template(self):
        """Show a picker of saved layout templates. When the doctor
        selects one, replace the current Yeni PDF structure with the
        template's pages + empty image slots + text overlays. Images
        from the current state are lost (confirmation asked first).
        Slots are empty frames that the doctor fills by dragging images."""
        templates = db_list_layout_templates()
        if not templates:
            QMessageBox.information(
                self, "Şablon Yok",
                "Henüz kayıtlı bir düzen şablonu yok.\n\n"
                "Önce bir düzen oluşturup '💾 Düzeni Kaydet' "
                "düğmesiyle şablon olarak saklayabilirsiniz.")
            return

        # Picker dialog
        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("Şablon Seç")
        dlg.resize(480, 420)
        v = QVBoxLayout(dlg)
        lbl = QLabel("Uygulanacak şablonu seçin:")
        lbl.setStyleSheet("font:600 12px 'Segoe UI';")
        v.addWidget(lbl)
        lst = QListWidget()
        for tid, title, upd in templates:
            item = QListWidgetItem(f"{title}\n   {upd}")
            item.setData(Qt.UserRole, tid)
            lst.addItem(item)
        lst.setStyleSheet("QListWidget::item{padding:6px;}")
        v.addWidget(lst, 1)

        btn_row = QHBoxLayout()
        del_btn = QPushButton("🗑 Sil")
        apply_btn = QPushButton("✓ Uygula")
        apply_btn.setDefault(True)
        cancel_btn = QPushButton("İptal")
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(apply_btn)
        v.addLayout(btn_row)

        def _on_delete():
            it = lst.currentItem()
            if it is None:
                return
            tid = it.data(Qt.UserRole)
            resp = QMessageBox.question(
                dlg, "Şablonu Sil",
                f"'{it.text().splitlines()[0]}' silinsin mi?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if resp == QMessageBox.Yes:
                db_delete_layout_template(tid)
                lst.takeItem(lst.row(it))

        del_btn.clicked.connect(_on_delete)
        cancel_btn.clicked.connect(dlg.reject)
        apply_btn.clicked.connect(dlg.accept)
        lst.itemDoubleClicked.connect(lambda _i: dlg.accept())

        if dlg.exec() != QDialog.Accepted:
            return
        current = lst.currentItem()
        if current is None:
            return
        template_id = current.data(Qt.UserRole)

        # Confirm if the current Yeni PDF has content
        if self._new_pdf_pages and any(
                pw.overlays or pw.text_overlays
                for pw in self._new_pdf_pages):
            resp = QMessageBox.question(
                self, "Mevcut Düzeni Değiştir",
                "Mevcut Yeni PDF düzeninde resimler/yazılar var — "
                "şablon uygulanırsa bunlar silinecek.\n\n"
                "Devam edilsin mi?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if resp != QMessageBox.Yes:
                return

        self._do_apply_layout_template(template_id)

    def _do_apply_layout_template(self, template_id: int):
        """Load a saved layout template from DB and apply it to Yeni PDF.
        Creates the right number of pages, then paints slot-frames and
        text overlays at the saved (fractional) coordinates."""
        row = db_load_layout_template(template_id)
        if row is None:
            QMessageBox.warning(self, "Hata", "Şablon yüklenemedi.")
            return
        title, layout_json = row
        import json as _json
        try:
            layout = _json.loads(layout_json)
        except Exception as ex:
            QMessageBox.critical(self, "Hata",
                                 f"Şablon bozuk:\n{ex}")
            return

        pages_data = layout.get("pages", [])
        if not pages_data:
            QMessageBox.information(
                self, "Boş Şablon",
                "Bu şablonda hiç sayfa yok.")
            return

        # Rebuild Yeni PDF with the right number of pages, empty
        self._pdf_canvas_items = []
        self._new_pdf_page_count = len(pages_data)
        self._refresh_pdf_canvas()
        QApplication.processEvents()

        if not self._new_pdf_pages or len(self._new_pdf_pages) != len(pages_data):
            QMessageBox.warning(
                self, "Hata",
                "Sayfalar oluşturulamadı.")
            return

        # Populate each page: empty image placeholders + text overlays
        total_slots = 0
        total_texts = 0
        for pi, page_data in enumerate(pages_data):
            if pi >= len(self._new_pdf_pages):
                break
            pw = self._new_pdf_pages[pi]
            W = pw.width()
            H = pw.height()
            # Text overlays — full fidelity restoration
            for t in page_data.get("texts", []):
                try:
                    rect = QRect(
                        int(t["x"] * W), int(t["y"] * H),
                        int(t["w"] * W), int(t["h"] * H))
                    pw.add_text_overlay(
                        rect,
                        text=t.get("text", ""),
                        mode=t.get("mode", "plain"),
                        font_size_pt=t.get("font_size", 11),
                        color=t.get("color", "#202020"))
                    total_texts += 1
                except Exception as ex:
                    _log_warning(f"template text restore failed: {ex}")
            # Image slot placeholders — painted rectangles that show
            # the doctor where to drop images. We don't create overlays
            # here since there's no image path; instead we set the
            # page's "slot hints" which are drawn as dashed rectangles.
            slot_hints = []
            for s in page_data.get("slots", []):
                rect = QRect(
                    int(s["x"] * W), int(s["y"] * H),
                    int(s["w"] * W), int(s["h"] * H))
                slot_hints.append(rect)
                total_slots += 1
            # Attach hints to the page for visual feedback
            try:
                pw.set_slot_hints(slot_hints)
            except Exception as _ex:
                # If the method isn't implemented, fall back silently;
                # the hints aren't critical — they're just visual guides.
                _log_warning("MainWindow._do_apply_layout_template", exc=_ex)

        self.pdf_status_label.setText(
            f"✓ '{title}' şablonu uygulandı · "
            f"{len(pages_data)} sayfa · {total_slots} resim yuvası · "
            f"{total_texts} yazı")
        self.statusBar().showMessage(
            f"Şablon uygulandı — resim yuvalarına kesikli çerçeveler "
            f"halinde sağdan resim sürükleyebilirsiniz", 8000)

    def build_pdf_from_selection(self):
        """Build a PDF from the interactive page widgets (new design).

        Each PdfPageEditWidget in self._new_pdf_pages becomes one PDF page.
        The position/size of each OverlayImage on the widget is converted
        from preview pixels back into PDF points (1:1 preserved), so the
        output mirrors exactly what the doctor sees in the preview.

        Falls back to the legacy image_checks selection if the user didn't
        use the interactive canvas.
        """
        if not self.current_subfolder:
            QMessageBox.warning(self, "Uyarı", "Önce bir geliş seçin.")
            return

        # Gather page widgets (authoritative source of truth now)
        page_widgets = list(getattr(self, "_new_pdf_pages", []) or [])

        # Check: any actual content on any page?
        has_content = any(
            (len(pw.overlays) > 0 or len(pw.text_overlays) > 0)
            for pw in page_widgets
        )

        # Fallback 1: legacy canvas items (double-click added)
        items_fallback = list(getattr(self, "_pdf_canvas_items", []) or [])

        # Fallback 2: legacy image_checks selection
        if not has_content and not items_fallback:
            try:
                paths = self._selected_image_paths()
            except Exception:
                paths = []
            if not paths:
                QMessageBox.warning(self, "Uyarı",
                    "PDF'e eklenecek içerik yok.\n\n"
                    "Sağdaki görüntülerden çift tıklayarak veya sürükleyerek "
                    "ekleyin. Sayfalar üzerinde resimleri sağ tıklayarak "
                    "boyutlandırabilir, sürükleyerek taşıyabilirsiniz.")
                return
            items_fallback = [{"type": "image", "path": str(p)} for p in paths]

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"rapor_{ts}.pdf"
        default_path = self.current_subfolder / default_name

        out_path_str, _ = QFileDialog.getSaveFileName(
            self, "PDF'i kaydet", str(default_path), "PDF Dosyası (*.pdf)"
        )
        if not out_path_str:
            self.pdf_status_label.setText("İptal edildi.")
            return
        out_path = Path(out_path_str)
        if out_path.suffix.lower() != ".pdf":
            out_path = out_path.with_suffix(".pdf")

        self.pdf_status_label.setText("PDF oluşturuluyor...")
        QApplication.processEvents()

        # Build the simple items list (used for the legacy flow path)
        items = items_fallback if not has_content else []

        try:
            doc = fitz.open()
            # A4 page in pt: 595 × 842
            PAGE_W, PAGE_H = 595, 842
            MARGIN = 40

            # ── FIRST PAGE: auto-include the visit's USG report first page ──
            include_usg_first = (self.pdf_include_usg_cover.isChecked()
                                 if hasattr(self, "pdf_include_usg_cover") else True)
            if include_usg_first:
                try:
                    src_pdf = get_latest_pdf_in_folder(self.current_subfolder)
                    if src_pdf and src_pdf.exists():
                        src_doc = fitz.open(str(src_pdf))
                        try:
                            # Copy only the first page of the USG report
                            if len(src_doc) > 0:
                                doc.insert_pdf(src_doc, from_page=0, to_page=0)
                        finally:
                            src_doc.close()
                except Exception as ex:
                    _log_warning(
                        f"Could not include USG first page: {ex}")
                    # Non-fatal — continue with image pages

            include_header = (self.pdf_include_header.isChecked()
                              if hasattr(self, "pdf_include_header") else False)

            mode = (self.pdf_layout_mode.currentIndex()
                    if hasattr(self, "pdf_layout_mode") else 0)
            n_images = sum(1 for it in items if it["type"] == "image")
            if mode == 0:
                cols = 2 if n_images >= 4 else 1
            elif mode == 1:
                cols = 1
            else:
                cols = 2

            # Helpers --------------------------------------------------
            def new_page():
                p = doc.new_page(width=PAGE_W, height=PAGE_H)
                return p

            def insert_header(page, y_top: float) -> float:
                """Insert a patient-info header bar near the top of the page.
                Returns the Y position where content should start."""
                title = format_patient_name(self.current_patient.name) \
                    if self.current_patient else ""
                ga_text = ""
                edd_text = ""
                try:
                    if self.current_subfolder:
                        spdf = get_latest_pdf_in_folder(self.current_subfolder)
                        if spdf:
                            data = parse_pdf_summary_data(spdf)
                            ga_text = best_ga_text_from_data(data) or ""
                            edd_v = data.get("edd") or ""
                            if isinstance(edd_v, str):
                                edd_text = edd_v
                except Exception as _ex:
                    _log_warning("MainWindow.insert_header", exc=_ex)
                date_str = datetime.now().strftime("%d.%m.%Y")
                # Background bar
                rect = fitz.Rect(MARGIN, y_top, PAGE_W - MARGIN, y_top + 60)
                page.draw_rect(rect, color=(0.4, 0.55, 0.7),
                               fill=(0.94, 0.96, 0.99), width=0.5)
                page.insert_text(
                    (MARGIN + 10, y_top + 20),
                    f"HASTA: {title}",
                    fontsize=12, fontname="helv", color=(0.0, 0.2, 0.4))
                meta_parts = []
                if ga_text:
                    meta_parts.append(f"GA: {ga_text}")
                if edd_text:
                    meta_parts.append(f"EDD: {edd_text}")
                meta_parts.append(f"Tarih: {date_str}")
                page.insert_text(
                    (MARGIN + 10, y_top + 38),
                    "  ·  ".join(meta_parts),
                    fontsize=9, fontname="helv", color=(0.2, 0.3, 0.5))
                page.insert_text(
                    (MARGIN + 10, y_top + 53),
                    get_clinic_doctor_name(),
                    fontsize=9, fontname="helv", color=(0.0, 0.2, 0.4))
                return y_top + 70

            # Build pages ----------------------------------------------
            current_page = new_page()
            cursor_y = MARGIN
            if include_header:
                cursor_y = insert_header(current_page, cursor_y)

            slot_w = (PAGE_W - 2 * MARGIN - (cols - 1) * 10) / cols
            row_buffer: List[dict] = []

            def flush_image_row():
                """Place buffered images on the current page side-by-side."""
                nonlocal cursor_y, current_page, row_buffer
                if not row_buffer:
                    return
                # Determine row height by aspect-fit each image into slot_w
                heights = []
                for r in row_buffer:
                    try:
                        with Image.open(r["path"]) as img:
                            iw, ih = img.size
                        h_at_slot = slot_w * ih / iw if iw > 0 else slot_w
                        # Cap to reasonable max
                        h_at_slot = min(h_at_slot, 300)
                        heights.append(h_at_slot)
                    except Exception:
                        heights.append(180)
                row_h = max(heights) + 6
                # Need a new page?
                if cursor_y + row_h > PAGE_H - MARGIN - 25:  # leave room for footer
                    current_page = new_page()
                    cursor_y = MARGIN
                # Centre row horizontally if cols=1
                total_w = len(row_buffer) * slot_w + (len(row_buffer) - 1) * 10
                start_x = (PAGE_W - total_w) / 2
                for i, r in enumerate(row_buffer):
                    x0 = start_x + i * (slot_w + 10)
                    h = heights[i]
                    rect = fitz.Rect(x0, cursor_y, x0 + slot_w, cursor_y + h)
                    try:
                        current_page.insert_image(rect, filename=r["path"],
                                                  keep_proportion=True)
                    except Exception as ex:
                        _log_warning(f"insert_image failed for {r['path']}: {ex}")
                cursor_y += row_h
                row_buffer = []

            def insert_text_block(content: str):
                nonlocal cursor_y, current_page
                # Estimate text block height
                line_h = 13
                lines = content.split("\n")
                wrapped_lines = 0
                CHARS_PER_LINE = 90
                for ln in lines:
                    wrapped_lines += max(1, (len(ln) // CHARS_PER_LINE) + 1)
                txt_h = wrapped_lines * line_h + 16
                if cursor_y + txt_h > PAGE_H - MARGIN - 25:
                    current_page = new_page()
                    cursor_y = MARGIN
                # Background box
                rect = fitz.Rect(MARGIN, cursor_y,
                                 PAGE_W - MARGIN, cursor_y + txt_h)
                current_page.draw_rect(rect, color=(0.7, 0.65, 0.4),
                                       fill=(1.0, 1.0, 0.92), width=0.5)
                # Insert text using HTML wrap if available
                try:
                    text_rect = fitz.Rect(MARGIN + 8, cursor_y + 4,
                                          PAGE_W - MARGIN - 8, cursor_y + txt_h - 4)
                    current_page.insert_textbox(
                        text_rect, content, fontsize=10,
                        fontname="helv", color=(0.1, 0.1, 0.1))
                except Exception as ex:
                    _log_warning(f"text block insert failed: {ex}")
                cursor_y += txt_h + 6

            # ── INTERACTIVE PATH: build from PdfPageEditWidget positions ──
            # When the doctor has arranged images on pages in the Yeni PDF
            # preview, honour those exact positions. Each preview pixel maps
            # to an A4 PDF point via the scale factors below.
            if has_content:
                for pw_idx, page_widget in enumerate(page_widgets):
                    # Empty pages are still emitted if the user explicitly
                    # added them via "Yeni Sayfa" button
                    pdf_page = current_page if pw_idx == 0 else new_page()
                    if pw_idx > 0:
                        cursor_y = MARGIN  # reset, new page
                    else:
                        current_page = pdf_page
                    if pw_idx == 0 and include_header:
                        # header already emitted above
                        pass

                    # Scale factors: preview pixel → PDF point
                    prev_w = max(1, page_widget.width())
                    prev_h = max(1, page_widget.height())
                    sx = PAGE_W / prev_w
                    sy = PAGE_H / prev_h

                    # Draw each image overlay
                    for ov in page_widget.overlays:
                        try:
                            g = ov.geometry()
                            pdf_rect = fitz.Rect(
                                g.x() * sx,
                                g.y() * sy,
                                (g.x() + g.width()) * sx,
                                (g.y() + g.height()) * sy,
                            )
                            pdf_page.insert_image(
                                pdf_rect, filename=str(ov.image_path),
                                keep_proportion=True)
                        except Exception as ex:
                            _log_warning(f"overlay insert failed: {ex}")

                    # Draw each text overlay
                    for tov in page_widget.text_overlays:
                        try:
                            g = tov.geometry()
                            pdf_rect = fitz.Rect(
                                g.x() * sx,
                                g.y() * sy,
                                (g.x() + g.width()) * sx,
                                (g.y() + g.height()) * sy,
                            )
                            # Background box
                            pdf_page.draw_rect(
                                pdf_rect, color=(0.7, 0.65, 0.4),
                                fill=(1.0, 1.0, 0.92), width=0.5)
                            pdf_page.insert_textbox(
                                pdf_rect,
                                getattr(tov, "text", "") or "",
                                fontsize=10, fontname="helv",
                                color=(0.1, 0.1, 0.1))
                        except Exception as ex:
                            _log_warning(f"text overlay insert failed: {ex}")
                # Skip the legacy flow
                items = []

            for it in items:
                if it["type"] == "image":
                    row_buffer.append(it)
                    if len(row_buffer) >= cols:
                        flush_image_row()
                elif it["type"] == "text":
                    flush_image_row()
                    insert_text_block(it["content"])
                elif it["type"] == "page_break":
                    # Force a new page — flush pending images, then open new
                    flush_image_row()
                    current_page = new_page()
                    cursor_y = MARGIN
            flush_image_row()  # leftover

            if doc.page_count == 0:
                doc.close()
                self.pdf_status_label.setText("Hata: hiçbir sayfa eklenemedi.")
                QMessageBox.warning(self, "Hata",
                                    "PDF'e eklenebilecek geçerli içerik bulunamadı.")
                return

            # Footer on every page
            try:
                date_str = datetime.now().strftime("%d.%m.%Y")
                footer_text = f"© {get_clinic_doctor_name()}  —  {date_str}"
                for page_idx in range(doc.page_count):
                    page = doc[page_idx]
                    pw = page.rect.width; ph = page.rect.height
                    approx_w = 8 * 0.5 * len(footer_text)
                    x = max(10, (pw - approx_w) / 2)
                    y = ph - 18
                    page.insert_text((x, y), footer_text, fontsize=8,
                                     fontname="helv", color=(0.55, 0.55, 0.55))
            except Exception as ex:
                _log_warning(f"footer failed on built PDF: {ex}")

            out_path.parent.mkdir(parents=True, exist_ok=True)
            doc.save(str(out_path), garbage=3, deflate=True)
            doc.close()

            self._last_built_pdf = out_path
            self.pdf_status_label.setText(
                f"✓ Oluşturuldu: {out_path.name} "
                f"({n_images} resim, {out_path.stat().st_size / 1024:.0f} KB)")
            self.statusBar().showMessage(
                f"✓ PDF oluşturuldu: {out_path.name}", 5000)
            # Refresh the previous-PDFs combo so the new file appears
            try:
                self._populate_previous_pdfs_combo()
            except Exception as _ex:
                _log_warning("MainWindow.build_pdf_from_selection", exc=_ex)
        except Exception as e:
            self.pdf_status_label.setText(f"Hata: {e}")
            QMessageBox.critical(self, "PDF Oluşturma Hatası", f"PDF dosyası oluşturulurken hata oluştu:\n\n{e}")

    def _open_templates_dialog(self):
        """Open the template picker. Selected template is queued into the PDF
        editor immediately (live preview shows it on the last page)."""
        if not hasattr(self, "pdf_editor") or not self.pdf_editor.current_pdf():
            QMessageBox.warning(self, "Uyarı",
                                "Önce PDF'li bir geliş seçin.")
            return
        dlg = TemplatePickerDialog(self)
        if dlg.exec() == QDialog.Accepted:
            body = dlg.selected_body()
            if body:
                self.pdf_editor.add_template_text(body)
                self._push_undo({"kind": "template"})
                self._update_template_queue_label()
                self.editor_status_label.setText(
                    "Şablon eklendi — son sayfada görünüyor")

    def _update_template_queue_label(self):
        """Refresh the small status label under the thumbnail list."""
        if not hasattr(self, "tmpl_queue_lbl"):
            return
        if hasattr(self, "pdf_editor"):
            n = len(self.pdf_editor.pending_templates())
            self.tmpl_queue_lbl.setText(f"Bekleyen şablon: {n}")
        else:
            self.tmpl_queue_lbl.setText("Bekleyen şablon: 0")
