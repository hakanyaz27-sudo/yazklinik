"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _PreviewThumbMixin
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

class _PreviewThumbMixin:
    """MainWindow methods related to PreviewThumb. Mixed into MainWindow via MRO."""

    def _run_preview(self):
        if not self.pending_preview:
            return
        f = self.pending_preview
        if hasattr(self, "file_name_label"):
            self.file_name_label.setText(f.name)
        try:
            sz = f.stat().st_size / (1024 * 1024)
            meta = f"Boyut: {sz:.2f} MB    |    Tür: {f.suffix.lower()}"
        except Exception:
            meta = f"Tür: {f.suffix.lower()}"
        if hasattr(self, "file_meta_label"):
            self.file_meta_label.setText(meta)
        self.show_preview(f)

    def _show_thumbnail_context_menu(self, img_path: Path,
                                     thumb_widget, pos):
        """Context menu on a gallery thumbnail — lets the doctor send the
        image to a PDF, print it, or open externally, all without first
        opening the large preview panel."""
        from PySide6.QtWidgets import QMenu
        menu = QMenu(thumb_widget)
        menu.setStyleSheet(
            "QMenu{background:#FFFFFF;border:1px solid #808080;padding:4px;}"
            "QMenu::item{padding:6px 20px;font:500 12px 'Segoe UI';}"
            "QMenu::item:selected{background:#0078D4;color:white;}"
            "QMenu::separator{height:1px;background:#C8C8C8;margin:4px 0;}")

        act_new_pdf = menu.addAction("📄  Yeni PDF'e ekle")
        act_main_pdf = menu.addAction("📑  Ana PDF'e ekle")
        menu.addSeparator()
        act_print = menu.addAction("🖨  Yazdır")
        menu.addSeparator()
        act_external = menu.addAction("🗔  Windows'ta Aç (harici)")

        try:
            act_print.setText("Yazdir")
        except Exception:
            pass
        chosen = menu.exec(thumb_widget.mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == act_new_pdf:
            try:
                self._preview_add_to_new_pdf(img_path)
            except Exception as ex:
                _log_warning(f"thumb→new PDF failed: {ex}")
        elif chosen == act_main_pdf:
            try:
                self._preview_add_to_pdf(img_path)
            except Exception as ex:
                _log_warning(f"thumb→main PDF failed: {ex}")
        elif chosen == act_print:
            try:
                self._preview_print_image(img_path)
            except Exception as ex:
                _log_warning(f"thumb print failed: {ex}")
        elif chosen == act_external:
            try:
                self._preview_open_externally(img_path)
            except Exception as ex:
                _log_warning(f"thumb external open failed: {ex}")

    def _preview_add_to_new_pdf(self, img_path: Path):
        """Callback: add this image to Yeni PDF as an interactive overlay
        on the last non-full page. The doctor can then drag/resize/right-click.
        If no page yet, creates one."""
        if not hasattr(self, "_new_pdf_pages") or not self._new_pdf_pages:
            # Canvas not built yet — fall back to queue + refresh
            if not hasattr(self, "_pdf_canvas_items"):
                self._pdf_canvas_items = []
            self._pdf_canvas_items.append(
                {"type": "image", "path": str(img_path)})
            try:
                self._refresh_pdf_canvas()
            except Exception as _ex:
                _log_warning("MainWindow._preview_add_to_new_pdf", exc=_ex)
        else:
            # Find the last page with space; spill to a new page if all full
            target = None
            for pw in reversed(self._new_pdf_pages):
                if len(pw.overlays) < pw.MAX_IMAGES_PER_PAGE:
                    target = pw
                    break
            if target is None:
                self._new_pdf_page_count += 1
                self._refresh_pdf_canvas()
                # After refresh, last page is the new empty one
                target = self._new_pdf_pages[-1] if self._new_pdf_pages else None
            if target is not None:
                center = QPoint(target.width() // 2, target.height() // 2)
                target.add_overlay(img_path, center, notify_full=True)
        # Rebuild the side strip so the added image disappears from the
        # thumbnail list (doctor doesn't want duplicates)
        try:
            self._populate_pdf_source_grid()
        except Exception as _ex:
            _log_warning("MainWindow._preview_add_to_new_pdf", exc=_ex)
        self.statusBar().showMessage(
            f"✓ {img_path.name} → Yeni PDF'e eklendi · "
            f"sayfada sağ tıklayarak boyut/konum ayarlayabilirsiniz",
            5000)

    def _preview_add_to_pdf(self, img_path: Path):
        """Callback from LargePreviewDialog: drop this image into the
        Ana PDF editor on the last non-full page. Uses the doctor's
        last-used size preset (remembered across images & patients)
        instead of asking every time — the doctor explicitly said the
        repeating popup was breaking their flow."""
        if not hasattr(self, "pdf_editor") or not self.pdf_editor.current_pdf():
            self.statusBar().showMessage(
                "Ana PDF sekmesinde bir PDF yüklü değil", 3000)
            return

        # Doctor's last chosen size — defaults to medium, updated every
        # time they right-click an overlay and pick a preset.
        size_preset = getattr(self, "_preferred_size_preset", "medium")

        # Drop onto the last non-full page (drop_point=None signals that
        # behaviour to drop_image_auto — "pile up at the end, make a new
        # page if we run out").
        actual = self.pdf_editor.drop_image_auto(0, img_path, drop_point=None)
        if actual >= 0:
            # Reconnect drop handlers in case of page re-render
            for page_w in self.pdf_editor.pages():
                try:
                    page_w.imageDropped.disconnect()
                except Exception as _ex:
                    _log_warning("MainWindow._preview_add_to_pdf", exc=_ex)
                page_w.imageDropped.connect(self._on_editor_image_dropped)

            # Apply the remembered size preset to the newest overlay
            try:
                target_page = self.pdf_editor.pages()[actual]
                if target_page.overlays:
                    newest = target_page.overlays[-1]
                    newest._resize_to_preset(size_preset)
            except Exception as _ex:
                _log_warning("MainWindow._preview_add_to_pdf", exc=_ex)

            self._push_undo({"kind": "overlay", "page": actual,
                             "path": img_path})
            # Rebuild the editor thumb strip so the added image disappears
            try:
                self._rebuild_editor_thumbnails()
            except Exception as _ex:
                _log_warning("MainWindow._preview_add_to_pdf", exc=_ex)
            size_label = {"small": "Küçük",
                          "medium": "Orta"}.get(size_preset, "Orta")
            self.statusBar().showMessage(
                f"✓ Resim Ana PDF sayfa {actual + 1}'e {size_label} boyutta "
                f"eklendi — sağ tık ile boyutu değiştirebilirsin",
                5000,
            )

    def _refresh_pdf_preview(self):
        """Backwards-compat shim — old code paths called this to refresh the
        legacy file table. The new tab uses a canvas-based preview which is
        refreshed via _refresh_pdf_canvas() instead. We just forward to it
        and to the new source-image grid populator so legacy callers still
        get a sensible refresh."""
        try:
            self._populate_pdf_source_grid()
        except Exception as _ex:
            _log_warning("MainWindow._refresh_pdf_preview", exc=_ex)
        try:
            self._refresh_pdf_canvas()
        except Exception as _ex:
            _log_warning("MainWindow._refresh_pdf_preview", exc=_ex)
        try:
            self._populate_previous_pdfs_combo()
        except Exception as _ex:
            _log_warning("MainWindow._refresh_pdf_preview", exc=_ex)

    def _clear_thumbnails(self):
        while self.thumb_layout.count() > 1:
            item = self.thumb_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._thumb_buttons = []

    def _rebuild_thumbnails(self):
        self._clear_thumbnails()
        if not self.current_files:
            return
        # Görüntüler sekmesi SADECE resim göstersin — MP4 ve diğer video
        # dosyaları "Videolar" sekmesinde görünür, bu yüzden burada skip
        # edilir. PDF de thumbnail'a gelmez — ayrı viewer'ı var.
        for f in self.current_files:
            ext = f.suffix.lower()
            if ext not in IMAGE_EXTS:
                continue  # skip videos & PDFs
            pix = self._make_thumbnail(f)
            # Images: draggable + hover-zoomable thumbnails so the user can
            # drop them onto the PDF editor's pages.
            btn = DraggableThumb(f, pix)
            btn.setFixedSize(260, 180)
            btn.setIconSize(QSize(248, 168))
            btn.clicked.connect(
                lambda _checked=False, path=f: self._select_file(path))

            self.thumb_layout.insertWidget(self.thumb_layout.count() - 1, btn)
            self._thumb_buttons.append((f, btn))

        self._highlight_active_thumbnail()

    def _make_thumbnail(self, f: Path) -> Optional[QPixmap]:
        """Create a thumbnail pixmap. Cached per path for the bottom strip."""
        if f in self._thumb_pixmap_cache:
            return self._thumb_pixmap_cache[f]
        ext = f.suffix.lower()
        try:
            if ext in IMAGE_EXTS and PIL_AVAILABLE:
                with Image.open(str(f)) as img:
                    img.thumbnail((520, 360))
                    if img.mode != "RGBA":
                        img = img.convert("RGBA")
                    qimg = QImage(img.tobytes("raw", "RGBA"), img.width, img.height,
                                  QImage.Format_RGBA8888).copy()
                    pm = QPixmap.fromImage(qimg)
                    self._thumb_pixmap_cache[f] = pm
                    return pm
            elif ext == ".pdf":
                doc = fitz.open(str(f))
                try:
                    page = doc[0]
                    pix = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), alpha=False)
                    qimg = QImage(pix.samples, pix.width, pix.height, pix.stride,
                                  QImage.Format_RGB888).copy()
                    pm = QPixmap.fromImage(qimg).scaled(
                        300, 240, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self._thumb_pixmap_cache[f] = pm
                    return pm
                finally:
                    doc.close()
            elif ext in VIDEO_EXTS and CV2_AVAILABLE:
                cap = cv2.VideoCapture(str(f))
                try:
                    if cap and cap.isOpened():
                        ok, frame = cap.read()
                        if ok:
                            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                            h, w, ch = frame.shape
                            qimg = QImage(frame.data, w, h, ch * w,
                                          QImage.Format_RGB888).copy()
                            pm = QPixmap.fromImage(qimg).scaled(
                                150, 110, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                            self._thumb_pixmap_cache[f] = pm
                            return pm
                finally:
                    try: cap.release()
                    except Exception: pass
        except Exception as _ex:
            _log_warning("MainWindow._make_thumbnail", exc=_ex)
        return None

    def _highlight_active_thumbnail(self):
        if not hasattr(self, "_thumb_buttons"):
            return
        active = (self.current_files[self.current_file_index]
                  if 0 <= self.current_file_index < len(self.current_files) else None)
        for f, btn in self._thumb_buttons:
            is_active = (f == active)
            btn.setProperty("active", "true" if is_active else "false")
            # Force restyle
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            if is_active:
                # Scroll to make sure it's visible
                self.thumb_scroll.ensureWidgetVisible(btn, 0, 20)
