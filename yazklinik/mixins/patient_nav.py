"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _PatientNavMixin
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

class _PatientNavMixin:
    """MainWindow methods related to PatientNav. Mixed into MainWindow via MRO."""

    def _populate_notes_visits_list(self):
        """Fill the visits list on the Notes tab with all the patient's
        visits, newest first. Each row shows: date · GA(if known) ·
        '✏' marker if a note exists."""
        if not hasattr(self, "notes_visits_list"):
            return
        self.notes_visits_list.blockSignals(True)
        try:
            self.notes_visits_list.clear()
            if not self.current_patient:
                self._notes_current_visit_path = None
                if hasattr(self, "notes_summary_text"):
                    self.notes_summary_text.setPlainText(
                        "Hasta seçilmedi.")
                return

            visits = self.subfolder_paths or []
            pkey = self.active_patient_key()
            # OPTIMIZATION: fetch ALL notes for this patient in one query
            # instead of one-query-per-visit (N queries → 1 query).
            try:
                all_notes = load_all_visit_notes_for_patient(pkey) if pkey else {}
            except Exception:
                all_notes = {}
            for v in visits:
                vkey = v.name
                visit_label = format_visit_name(vkey)
                note_text = all_notes.get(vkey, "")
                marker = " ✏" if note_text and note_text.strip() else ""
                # Try to get GA from cached summary parse (very fast if cached)
                ga_text = ""
                try:
                    pdf = get_latest_pdf_in_folder(v)
                    if pdf:
                        data = parse_pdf_summary_data(pdf)
                        ga_text = best_ga_text_from_data(data) or ""
                except Exception as _ex:
                    _log_warning("MainWindow._populate_notes_visits_list", exc=_ex)
                ga_part = f"  ·  GA: {ga_text}" if ga_text else ""
                item_text = f"{visit_label}{ga_part}{marker}"
                item = QListWidgetItem(item_text)
                item.setData(Qt.UserRole, ("visit", str(v)))
                item.setToolTip(vkey)
                if note_text and note_text.strip():
                    item.setForeground(QColor("#005A9E"))
                    f = item.font(); f.setBold(True); item.setFont(f)
                self.notes_visits_list.addItem(item)

            # Auto-select the newest (first) visit
            if self.notes_visits_list.count() > 0:
                first = self.notes_visits_list.item(0)
                self.notes_visits_list.setCurrentItem(first)
        finally:
            self.notes_visits_list.blockSignals(False)
        # Trigger explicit selection load (signal was suppressed)
        cur = self.notes_visits_list.currentItem()
        if cur is not None:
            self._on_notes_visits_list_changed(cur, None)

    def _nav_patient(self, direction: int):
        """Move selection up (-1) or down (+1) in the patient list.
        Called from Alt+↑ / Alt+↓ shortcuts."""
        if not hasattr(self, "patient_list"):
            return
        cur_row = self.patient_list.currentRow()
        new_row = cur_row + direction
        if 0 <= new_row < self.patient_list.count():
            self.patient_list.setCurrentRow(new_row)
            it = self.patient_list.currentItem()
            if it:
                self.patient_list.scrollToItem(it)

    def _nav_visit(self, direction: int):
        """Move selection to previous (-1) or next (+1) visit of current patient.
        Called from Alt+← / Alt+→ shortcuts."""
        if not self.current_patient or not self.subfolder_paths:
            return
        try:
            cur_idx = self.subfolder_paths.index(self.current_subfolder)
        except (ValueError, AttributeError):
            return
        new_idx = cur_idx + direction
        if 0 <= new_idx < len(self.subfolder_paths):
            new_visit = self.subfolder_paths[new_idx]
            try:
                self._select_visit_by_path(new_visit)
                # Also update the Notes-tab visits list highlight if present
                if hasattr(self, "notes_visits_list"):
                    for i in range(self.notes_visits_list.count()):
                        it = self.notes_visits_list.item(i)
                        d = it.data(Qt.UserRole)
                        if d and isinstance(d, tuple) and d[0] == "visit" \
                                and Path(d[1]) == new_visit:
                            self.notes_visits_list.setCurrentItem(it)
                            break
                self.statusBar().showMessage(
                    f"Geliş {new_idx + 1}/{len(self.subfolder_paths)}: "
                    f"{format_visit_name(new_visit.name)}", 2500)
            except Exception as ex:
                _log_warning(f"nav_visit failed: {ex}")

    def _populate_visits_list(self, patient_path: Optional[Path]):
        """Fill the visits list for the given patient. None → clear."""
        self._suppress_tree_signals = True
        try:
            self.visits_list.clear()
            if patient_path is None:
                self.visits_count_lbl.setText("0")
                return
            visits = get_subfolders(patient_path)
            self.visits_count_lbl.setText(str(len(visits)))
            for v in visits:
                item = QListWidgetItem(format_visit_name(v.name))
                item.setData(Qt.UserRole, ("visit", str(v)))
                item.setToolTip(v.name)
                self.visits_list.addItem(item)
            if not visits:
                placeholder = QListWidgetItem("— Geliş yok —")
                placeholder.setFlags(Qt.NoItemFlags)
                placeholder.setForeground(QColor("#909090"))
                self.visits_list.addItem(placeholder)
        finally:
            self._suppress_tree_signals = False

    def _on_patient_list_changed(self, current: Optional[QListWidgetItem],
                                 _previous: Optional[QListWidgetItem]):
        if self._suppress_tree_signals or current is None:
            return
        data = current.data(Qt.UserRole)
        if not data or data[0] != "patient":
            return
        patient_path = Path(data[1])
        # v68-AI: Log this patient selection so BehaviorLearner can
        # surface "most-viewed patients" and learn cadence patterns
        try:
            BehaviorLearner.log_action(
                "select_patient", patient_path.name,
                patient_key=patient_path.name)
        except Exception as _ex:
            _log_warning(f"behavior log: select_patient: {_ex}")
        self._select_patient_by_path(patient_path, reselect_visit=False)
        # Populate the visits list and auto-select the first (most recent) visit
        self._populate_visits_list(patient_path)
        if self.visits_list.count() > 0:
            first = self.visits_list.item(0)
            if first is not None and (first.flags() & Qt.ItemIsEnabled):
                self.visits_list.setCurrentItem(first)
        # v68: when the patient changes, always jump back to "Hasta Özeti"
        # — the doctor asked for this so a new patient always starts with
        # the summary view, regardless of which tab was open for the
        # previous patient. Visit changes DON'T trigger this (see
        # _select_visit_by_path) — those keep the current tab.
        try:
            if hasattr(self, "tabs"):
                self.tabs.setCurrentIndex(0)
        except Exception as _ex:
            _log_warning(
                "_on_patient_list_changed: jump to summary tab", exc=_ex)

    def _select_visit_by_path(self, visit_path: Path, reselect_file: bool = True):
        if self.current_subfolder == visit_path:
            return
        self.current_subfolder = visit_path
        vlabel = format_visit_name(visit_path.name)
        self.stat_visit.set_value(vlabel)
        self.visit_info_label.setText(f"Geliş:  {vlabel}")
        self.populate_files()
        self.load_summary()
        self._load_note()
        self.refresh_signature_ui()
        self._rebuild_image_checks()
        self._rebuild_thumbnails()

        # ── Lazy loads ──────────────────────────────────────────────
        # Heavy per-visit populators are deferred until the user actually
        # opens that tab. They set a pending flag here; _on_main_tab_changed
        # picks it up on first visit. If the tab is already open, we load
        # immediately so the user sees fresh content right away.
        self._pending_pdf_builder_reload = True
        self._pending_videos_reload = True
        self._pending_notes_reload = True

        current_tab = self.tabs.currentIndex() if hasattr(self, "tabs") else -1
        # Refresh PDF canvas (also populates the source grid + prev combo)
        if current_tab == 5:  # Yeni PDF
            self._refresh_pdf_preview()
            self._pending_pdf_builder_reload = False
        # Videos tab
        if current_tab == getattr(self, "_videos_tab_index", 4):
            try:
                self._populate_video_list_widget()
            except Exception as _ex:
                _log_warning("MainWindow._select_visit_by_path", exc=_ex)
            self._pending_videos_reload = False
        # Notes tab
        if current_tab == 6:  # Notlar
            try:
                self._populate_notes_visits_list()
            except Exception as _ex:
                _log_warning("MainWindow._select_visit_by_path", exc=_ex)
            self._pending_notes_reload = False

        # Flag ribbon: GA-dependent alerts (e.g. RhoGam) change per visit
        try:
            self._update_flag_ribbon()
        except Exception as _ex:
            _log_warning("MainWindow._select_visit_by_path", exc=_ex)
        # Clinical banner + GA-specific recommendations (new in v46.x)
        try:
            self._update_clinical_banner()
        except Exception as _ex:
            _log_warning("MainWindow._select_visit_by_path", exc=_ex)
        try:
            self._update_ga_recommendations()
        except Exception as _ex:
            _log_warning("MainWindow._select_visit_by_path", exc=_ex)
        # Embedded PDF viewer (Summary tab) — user sees this first, load now.
        self._load_embedded_pdf_viewer()
        # PDF editor is heavier (per-page fitz render). Defer it until the
        # user actually visits that tab. _pending_editor_reload is picked up
        # by the tabs.currentChanged handler.
        self._pending_editor_reload = True
        current_tab = self.tabs.currentIndex() if hasattr(self, "tabs") else -1
        if current_tab == 1:  # already on Ana PDF tab — load immediately
            self._reload_editor_pdf()
            try:
                self._rebuild_editor_thumbnails()
            except Exception as _ex:
                _log_warning("MainWindow._select_visit_by_path", exc=_ex)
            self._pending_editor_reload = False
        if reselect_file and self.current_files:
            self._select_file(self.current_files[0])

    def _populate_pdf_source_grid(self):
        """Fill the right-side vertical strip with DraggableThumb tiles —
        same widget Ana PDF uses. The doctor gets:
        - Drag onto any page → interactive overlay with right-click sizing
        - Hover zoom → big preview in a floating window
        - Double-click → add to last non-full page automatically
        """
        if not hasattr(self, "pdf_source_layout"):
            return
        # Clear existing thumbnails (preserve the trailing stretch)
        while self.pdf_source_layout.count() > 1:
            it = self.pdf_source_layout.takeAt(0)
            w = it.widget() if it else None
            if w is not None:
                w.deleteLater()

        if not self.current_subfolder:
            empty = QLabel("Hasta gelişi seçilmedi.")
            empty.setStyleSheet(
                "color:#909090;font:400 11px 'Segoe UI';padding:20px;"
                "background:transparent;")
            empty.setAlignment(Qt.AlignCenter)
            self.pdf_source_layout.insertWidget(0, empty)
            self.pdf_source_count_lbl.setText("0 resim")
            return

        # Collect image files (sorted by name for stable order)
        try:
            files = sorted(
                [f for f in self.current_subfolder.iterdir()
                 if f.is_file() and f.suffix.lower() in IMAGE_EXTS],
                key=lambda f: f.name.lower())
        except Exception:
            files = []
        if not files:
            empty = QLabel("Bu gelişte resim bulunamadı.")
            empty.setStyleSheet(
                "color:#909090;font:400 11px 'Segoe UI';padding:20px;"
                "background:transparent;")
            empty.setAlignment(Qt.AlignCenter)
            self.pdf_source_layout.insertWidget(0, empty)
            self.pdf_source_count_lbl.setText("0 resim")
            return

        # Build the set of images already placed on Yeni PDF pages —
        # skip them to avoid the same image appearing twice in the side
        # strip once it's been added.
        used_paths = set()
        if hasattr(self, "_new_pdf_pages"):
            try:
                for pw in self._new_pdf_pages or []:
                    for ov in pw.overlays:
                        try:
                            used_paths.add(str(Path(ov.image_path).resolve()))
                        except Exception:
                            used_paths.add(str(ov.image_path))
            except Exception as _ex:
                _log_warning("MainWindow._populate_pdf_source_grid", exc=_ex)

        # Build vertical strip of DraggableThumb — identical to Ana PDF
        n_shown = 0
        for path in files:
            try:
                key = str(path.resolve())
            except Exception:
                key = str(path)
            if key in used_paths:
                continue
            pix = self._make_thumbnail(path)
            thumb = DraggableThumb(path, pix)
            thumb.setFixedSize(250, 180)
            thumb.setIconSize(QSize(240, 160))
            thumb.setToolTip(
                f"{path.name}\n\nSürükle → PDF sayfasına bırak\n"
                f"veya çift tık → son sayfaya ekle")
            def _make_double_handler(p):
                def _h(event):
                    self._pdf_add_image_to_canvas(p)
                return _h
            thumb.mouseDoubleClickEvent = _make_double_handler(path)
            self.pdf_source_layout.insertWidget(
                self.pdf_source_layout.count() - 1, thumb)
            n_shown += 1

        self.pdf_source_count_lbl.setText(
            f"{n_shown} resim"
            + (f" ({len(files) - n_shown} tane eklendi)"
               if n_shown < len(files) else ""))

    def _populate_previous_pdfs_combo(self):
        """Populate the 'previous PDFs' dropdown with this patient's existing
        PDF files, sorted by modified date (newest first)."""
        if not hasattr(self, "pdf_previous_combo"):
            return
        self.pdf_previous_combo.clear()
        if not self.current_patient:
            self.pdf_previous_combo.addItem("(hasta seçilmedi)")
            return
        # Walk all visit subfolders, collect all .pdf files
        pdfs = []
        try:
            for sub in get_subfolders(self.current_patient):
                for f in sub.iterdir():
                    if f.is_file() and f.suffix.lower() == ".pdf":
                        try:
                            mt = f.stat().st_mtime
                        except Exception:
                            mt = 0
                        pdfs.append((mt, f))
        except Exception as _ex:
            _log_warning("MainWindow._populate_previous_pdfs_combo", exc=_ex)
        pdfs.sort(key=lambda x: x[0], reverse=True)
        if not pdfs:
            self.pdf_previous_combo.addItem("(önceki PDF yok)")
            return
        for _mt, p in pdfs[:50]:  # cap to 50 most recent
            label = f"{p.parent.name} / {p.name}"
            self.pdf_previous_combo.addItem(label, str(p))
