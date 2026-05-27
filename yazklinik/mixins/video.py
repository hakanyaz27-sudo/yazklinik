"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _VideoMixin
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

class _VideoMixin:
    """MainWindow methods related to Video. Mixed into MainWindow via MRO."""

    def _build_tab_videos(self) -> QWidget:
        """Video sekmesi — yeniden tasarım.

        Sol: Geliş'in tüm videoları (compact list)
        Sağ (büyük): Seçili videonun büyük önizleme oynatıcısı
                  + Oynat / Duraklat / Tekrar başlat / Aç düğmeleri
        """
        page = QWidget()
        page.setObjectName("TabPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("🎥  Videolar")
        title.setObjectName("BoxTitle")
        hdr.addWidget(title)
        hdr.addStretch()
        self.videos_count_label = QLabel("0 video")
        self.videos_count_label.setStyleSheet(
            "color:#606060;font:600 11px 'Segoe UI';padding:2px 8px;"
            "background:#F0F0F0;border:1px solid #C8C8C8;")
        hdr.addWidget(self.videos_count_label)
        lay.addLayout(hdr)

        # Main split
        split = QSplitter(Qt.Horizontal)
        split.setHandleWidth(6)
        split.setChildrenCollapsible(False)

        # LEFT: video list
        left_box = QFrame()
        left_box.setObjectName("InnerBox")
        ll = QVBoxLayout(left_box)
        ll.setContentsMargins(6, 6, 6, 6)
        ll.setSpacing(4)
        ll_hdr = QLabel("Geliş Videoları")
        ll_hdr.setStyleSheet(accent_label_style(font_size=11))
        ll.addWidget(ll_hdr)

        self.video_list_widget = QListWidget()
        self.video_list_widget.setStyleSheet(
            "QListWidget{background:#FFFFFF;border:1px solid #C8C8C8;}"
            "QListWidget::item{padding:6px 8px;border-bottom:1px solid #F0F0F0;}"
            "QListWidget::item:selected{background:#E5EEF7;color:#003366;}")
        self.video_list_widget.currentItemChanged.connect(
            self._on_video_list_selected)
        ll.addWidget(self.video_list_widget, 1)
        split.addWidget(left_box)

        # RIGHT: big preview + controls
        right_box = QFrame()
        right_box.setObjectName("InnerBox")
        right_box.setStyleSheet(
            "QFrame#InnerBox{background:#1A1A1A;border:1px solid #404040;}")
        rl = QVBoxLayout(right_box)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setSpacing(4)

        # Big preview label (the cv2 frame is drawn here)
        self.video_big_preview = QLabel("Bir video seç →")
        self.video_big_preview.setStyleSheet(
            "background:#000000;color:#808080;font:400 14px 'Segoe UI';"
            "border:1px solid #303030;")
        self.video_big_preview.setAlignment(Qt.AlignCenter)
        self.video_big_preview.setMinimumSize(640, 480)

        # Wheel scroll + arrow keys navigate between videos in the visit.
        # This replaces the now-hidden left-side list widget: the doctor can
        # cycle through videos by scrolling the mouse wheel over the preview
        # or pressing ← / → keys.
        def _video_wheel(event):
            delta = event.angleDelta().y()
            if delta > 0:
                self._video_prev()
            elif delta < 0:
                self._video_next()
            event.accept()
        self.video_big_preview.wheelEvent = _video_wheel
        # Enable keyboard focus so arrows work
        self.video_big_preview.setFocusPolicy(Qt.StrongFocus)

        rl.addWidget(self.video_big_preview, 1)

        # Filename label
        self.video_now_playing_lbl = QLabel("")
        self.video_now_playing_lbl.setStyleSheet(
            "color:#FFFFFF;font:600 12px 'Segoe UI';background:#1A1A1A;padding:4px;")
        self.video_now_playing_lbl.setAlignment(Qt.AlignCenter)
        rl.addWidget(self.video_now_playing_lbl)

        # Controls
        ctrl = QHBoxLayout()
        ctrl.setSpacing(4)
        ctrl.addStretch()
        self.video_play_btn = QPushButton("▶ Oynat")
        self.video_play_btn.setStyleSheet(
            "background:#107C10;color:white;padding:6px 16px;font:600 11px 'Segoe UI';"
            "border:none;border-radius:3px;")
        self.video_play_btn.setCursor(Qt.PointingHandCursor)
        self.video_play_btn.setToolTip("Videoyu oynat (Space)")
        self.video_play_btn.clicked.connect(self._video_play_pause)
        ctrl.addWidget(self.video_play_btn)

        self.video_pause_btn = QPushButton("⏸ Duraklat")
        self.video_pause_btn.setStyleSheet(
            "background:#444444;color:white;padding:6px 16px;font:600 11px 'Segoe UI';"
            "border:none;border-radius:3px;")
        self.video_pause_btn.setCursor(Qt.PointingHandCursor)
        self.video_pause_btn.setToolTip("Videoyu duraklat")
        self.video_pause_btn.clicked.connect(self._video_pause)
        ctrl.addWidget(self.video_pause_btn)

        self.video_restart_btn = QPushButton("↺ Başa Sar")
        self.video_restart_btn.setStyleSheet(
            "background:#444444;color:white;padding:6px 16px;font:600 11px 'Segoe UI';"
            "border:none;border-radius:3px;")
        self.video_restart_btn.setCursor(Qt.PointingHandCursor)
        self.video_restart_btn.setToolTip("Videoyu en başa sar")
        self.video_restart_btn.clicked.connect(self._video_restart)
        ctrl.addWidget(self.video_restart_btn)

        self.video_open_external_btn = QPushButton("🖥 Sistem Oynatıcı")
        self.video_open_external_btn.setStyleSheet(
            "background:#0078D4;color:white;padding:6px 16px;font:600 11px 'Segoe UI';"
            "border:none;border-radius:3px;")
        self.video_open_external_btn.setCursor(Qt.PointingHandCursor)
        self.video_open_external_btn.setToolTip(
            "Videoyu Windows'un varsayılan oynatıcısında aç "
            "(daha büyük ekran, daha iyi kontroller)")
        self.video_open_external_btn.clicked.connect(self._video_open_external)
        ctrl.addWidget(self.video_open_external_btn)
        ctrl.addStretch()
        rl.addLayout(ctrl)

        # ── Alt thumbnail şeridi ──────────────────────────────────────────
        # Scroll edilebilir küçük video önizlemeleri (kaçıncı videoda
        # olduğumuz bakışta anlaşılsın). Tıklama → o videoya geç.
        self.video_thumb_scroll = QScrollArea()
        self.video_thumb_scroll.setFixedHeight(100)
        self.video_thumb_scroll.setWidgetResizable(True)
        self.video_thumb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self.video_thumb_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.video_thumb_scroll.horizontalScrollBar().setSingleStep(20)
        self.video_thumb_scroll.setStyleSheet(
            "QScrollArea{background:#1A1A1A;border:1px solid #303030;}"
            "QScrollBar:horizontal{background:#2A2A2A;height:12px;border:none;}"
            "QScrollBar::handle:horizontal{background:#606060;border-radius:5px;"
            "min-width:30px;margin:2px;}"
            "QScrollBar::handle:horizontal:hover{background:#808080;}"
            "QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{"
            "border:none;background:none;width:0;}")
        self._video_thumb_host = QWidget()
        self._video_thumb_host.setStyleSheet("background:#1A1A1A;")
        self._video_thumb_lay = QHBoxLayout(self._video_thumb_host)
        self._video_thumb_lay.setContentsMargins(6, 6, 6, 6)
        self._video_thumb_lay.setSpacing(4)
        self._video_thumb_lay.addStretch()
        self.video_thumb_scroll.setWidget(self._video_thumb_host)
        rl.addWidget(self.video_thumb_scroll)

        # Cache of thumbnail buttons for the current visit's videos
        self._video_thumb_buttons: List[Tuple[Path, QPushButton]] = []

        split.addWidget(right_box)
        # Hide the left list per user feedback — videos are navigated via
        # arrow keys / scroll on the big preview pane directly. The list
        # widget remains alive (not destroyed) so _populate_video_list_widget
        # and _on_video_list_selected don't crash.
        left_box.setMaximumWidth(0)
        left_box.setMinimumWidth(0)
        split.setSizes([0, 1500])
        split.setCollapsible(0, True)
        try:
            h = split.handle(1)
            if h:
                h.setDisabled(True)
                h.setMaximumWidth(0)
        except Exception as _ex:
            _log_warning("MainWindow._build_tab_videos", exc=_ex)
        lay.addWidget(split, 1)

        # State for the new video player
        self._video_current_path: Optional[Path] = None
        self._video_loop = True

        # Backwards compat (some old code uses these)
        self.videos_list_layout = QVBoxLayout()  # dummy to avoid AttributeError
        self.video_rows: List[Tuple[Path, "VideoChoiceRow"]] = []

        return page

    def _stop_video(self):
        try: self.video_timer.stop()
        except Exception: pass
        try:
            if self.video_capture is not None:
                self.video_capture.release()
        except Exception as _ex:
            _log_warning("MainWindow._stop_video", exc=_ex)
        self.video_capture = None

    def _next_video_frame(self):
        if self.video_capture is None:
            return
        ok, frame = self.video_capture.read()
        if not ok:
            try:
                self.video_capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = self.video_capture.read()
            except Exception:
                ok = False
            if not ok:
                self._stop_video(); return
        try:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            qimg = QImage(frame.data, w, h, ch * w, QImage.Format_RGB888).copy()
            self.current_pixmap = QPixmap.fromImage(qimg)
            self._fit_pixmap()
        except Exception:
            self._stop_video()

    def _video_prev(self):
        """Navigate to the previous video in the visit (called from wheel
        scroll on the big preview)."""
        if not hasattr(self, "video_list_widget"):
            return
        n = self.video_list_widget.count()
        if n <= 0:
            return
        cur = self.video_list_widget.currentRow()
        new_row = (cur - 1) % n if cur >= 0 else n - 1
        self.video_list_widget.setCurrentRow(new_row)

    def _video_next(self):
        """Navigate to the next video in the visit (called from wheel
        scroll on the big preview)."""
        if not hasattr(self, "video_list_widget"):
            return
        n = self.video_list_widget.count()
        if n <= 0:
            return
        cur = self.video_list_widget.currentRow()
        new_row = (cur + 1) % n if cur >= 0 else 0
        self.video_list_widget.setCurrentRow(new_row)

    def _populate_video_list_widget(self):
        """Fill the Videos tab's side list with the visit's video files.
        Also builds the bottom thumbnail strip so the user can see at a
        glance which video they're on."""
        if not hasattr(self, "video_list_widget"):
            return
        self.video_list_widget.blockSignals(True)
        try:
            self.video_list_widget.clear()
            if not self.current_subfolder:
                if hasattr(self, "videos_count_label"):
                    self.videos_count_label.setText("0 video")
                if hasattr(self, "video_big_preview"):
                    self.video_big_preview.setText("Önce bir geliş seç →")
                    self.video_big_preview.setPixmap(QPixmap())
                self._rebuild_video_thumb_strip([])
                return
            files = []
            try:
                files = sorted(
                    [f for f in self.current_subfolder.iterdir()
                     if f.is_file() and f.suffix.lower() in VIDEO_EXTS],
                    key=lambda f: f.name.lower())
            except Exception as _ex:
                _log_warning("MainWindow._populate_video_list_widget", exc=_ex)
            for f in files:
                try:
                    sz_mb = f.stat().st_size / (1024 * 1024)
                    sz_str = f"{sz_mb:.1f} MB"
                except Exception:
                    sz_str = "-"
                item = QListWidgetItem(f"🎥  {f.name}\n      {sz_str}")
                item.setData(Qt.UserRole, str(f))
                item.setToolTip(str(f))
                self.video_list_widget.addItem(item)
            if hasattr(self, "videos_count_label"):
                self.videos_count_label.setText(f"{len(files)} video")
            # Build the bottom thumbnail strip
            self._rebuild_video_thumb_strip(files)
            # Auto-select the first if available
            if files:
                self.video_list_widget.setCurrentRow(0)
        finally:
            self.video_list_widget.blockSignals(False)
        # Fire selection change manually so the first video loads
        cur = self.video_list_widget.currentItem()
        if cur is not None:
            self._on_video_list_selected(cur, None)

    def _rebuild_video_thumb_strip(self, files: List[Path]):
        """Build / refresh the bottom video thumbnail strip.
        Each thumbnail is clickable → navigates to that video."""
        if not hasattr(self, "_video_thumb_lay"):
            return
        # Clear existing thumbs (keep the final stretch)
        while self._video_thumb_lay.count() > 1:
            it = self._video_thumb_lay.takeAt(0)
            w = it.widget() if it else None
            if w is not None:
                w.deleteLater()
        self._video_thumb_buttons = []
        if not files:
            return
        for idx, f in enumerate(files):
            btn = QPushButton()
            btn.setFixedSize(120, 80)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setIconSize(QSize(114, 64))
            btn.setToolTip(f"{idx + 1}/{len(files)}  ·  {f.name}")
            # Video thumbnail: first frame via cv2 if available, else icon
            pix = None
            try:
                if CV2_AVAILABLE:
                    cap = cv2.VideoCapture(str(f))
                    ok, frame = cap.read()
                    cap.release()
                    if ok and frame is not None:
                        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                        h, w, ch = frame.shape
                        qimg = QImage(frame.data, w, h, ch * w,
                                      QImage.Format_RGB888).copy()
                        pix = QPixmap.fromImage(qimg).scaled(
                            114, 64, Qt.KeepAspectRatio,
                            Qt.SmoothTransformation)
            except Exception as _ex:
                _log_warning("MainWindow._rebuild_video_thumb_strip", exc=_ex)
            if pix is not None and not pix.isNull():
                btn.setIcon(QIcon(pix))
            else:
                btn.setText(f"🎥\n{idx + 1}")
            # Baseline style (overridden when selected)
            btn.setStyleSheet(
                "QPushButton{background:#333333;border:2px solid #606060;"
                "color:#C0C0C0;font:600 10px 'Segoe UI';padding:0;}"
                "QPushButton:hover{border:2px solid #0078D4;}")
            # Clicking the thumbnail navigates to that video
            btn.clicked.connect(
                lambda _checked=False, i=idx: self._video_thumb_clicked(i))
            self._video_thumb_lay.insertWidget(
                self._video_thumb_lay.count() - 1, btn)
            self._video_thumb_buttons.append((f, btn))

    def _video_thumb_clicked(self, idx: int):
        """User clicked a thumbnail in the bottom video strip."""
        if not hasattr(self, "video_list_widget"):
            return
        if 0 <= idx < self.video_list_widget.count():
            self.video_list_widget.setCurrentRow(idx)

    def _highlight_active_video_thumb(self):
        """Visually mark the currently playing video's thumbnail in the
        bottom strip."""
        if not hasattr(self, "_video_thumb_buttons"):
            return
        cur_idx = -1
        if hasattr(self, "video_list_widget"):
            cur_idx = self.video_list_widget.currentRow()
        for i, (path, btn) in enumerate(self._video_thumb_buttons):
            if i == cur_idx:
                btn.setStyleSheet(
                    "QPushButton{background:#0078D4;border:3px solid #40A0FF;"
                    "color:#FFFFFF;font:700 10px 'Segoe UI';padding:0;}"
                    "QPushButton:hover{border:3px solid #60B0FF;}")
            else:
                btn.setStyleSheet(
                    "QPushButton{background:#333333;border:2px solid #606060;"
                    "color:#C0C0C0;font:600 10px 'Segoe UI';padding:0;}"
                    "QPushButton:hover{border:2px solid #0078D4;}")
        # Auto-scroll to active thumb if not visible
        try:
            if 0 <= cur_idx < len(self._video_thumb_buttons):
                _, btn = self._video_thumb_buttons[cur_idx]
                self.video_thumb_scroll.ensureWidgetVisible(btn, 20, 0)
        except Exception as _ex:
            _log_warning("MainWindow._highlight_active_video_thumb", exc=_ex)

    def _on_video_list_selected(self, current, _previous):
        """A video was selected → load it into the big preview (paused).
        Also updates the bottom thumbnail strip's highlight."""
        if current is None:
            return
        # Highlight the active thumbnail in the bottom strip
        try:
            self._highlight_active_video_thumb()
        except Exception as _ex:
            _log_warning("MainWindow._on_video_list_selected", exc=_ex)
        data = current.data(Qt.UserRole)
        if not data:
            return
        path = Path(data)
        self._video_current_path = path
        if hasattr(self, "video_now_playing_lbl"):
            self.video_now_playing_lbl.setText(path.name)
        # Stop any ongoing capture and open the new file
        self._stop_video_preview()
        if not CV2_AVAILABLE:
            if hasattr(self, "video_big_preview"):
                self.video_big_preview.setText(
                    "🎥  Video önizleme devre dışı\n\n"
                    "OpenCV kütüphanesi kurulu değil.\n\n"
                    "Kurulum: Komut satırında (yönetici olarak)\n"
                    "    pip install opencv-python\n\n"
                    "Şimdilik 'Sistem Oynatıcıda Aç' butonunu kullanın.")
                self.video_big_preview.setStyleSheet(
                    "background:#FFF8EC;color:#8C4A00;"
                    "border:1px solid #C46500;padding:20px;"
                    "font:500 12px 'Segoe UI';")
            return
        try:
            self._video_tab_capture = cv2.VideoCapture(str(path))
            if not self._video_tab_capture.isOpened():
                self.video_big_preview.setText(
                    "Video açılamadı:\n" + path.name)
                self._video_tab_capture = None
                return
            # Show the first frame as a paused preview
            ok, frame = self._video_tab_capture.read()
            if ok:
                self._render_video_tab_frame(frame)
            # Auto-start playback
            self._video_tab_playing = True
            if not hasattr(self, "_video_tab_timer"):
                self._video_tab_timer = QTimer(self)
                self._video_tab_timer.timeout.connect(self._video_tab_next_frame)
            self._video_tab_timer.start(40)  # ~25fps
        except Exception as ex:
            _log_warning(f"video load failed: {ex}")
            if hasattr(self, "video_big_preview"):
                self.video_big_preview.setText(f"Hata: {ex}")

    def _render_video_tab_frame(self, frame):
        """Scale a BGR cv2 frame to fit the big preview label and display."""
        try:
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            h, w, ch = frame.shape
            qimg = QImage(frame.data, w, h, ch * w, QImage.Format_RGB888).copy()
            pm = QPixmap.fromImage(qimg)
            if hasattr(self, "video_big_preview"):
                label = self.video_big_preview
                tw = max(400, label.width() - 10)
                th = max(300, label.height() - 10)
                scaled = pm.scaled(QSize(tw, th), Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
                label.setPixmap(scaled)
                label.setText("")
        except Exception as ex:
            _log_warning(f"render video frame failed: {ex}")

    def _video_tab_next_frame(self):
        cap = getattr(self, "_video_tab_capture", None)
        if cap is None or not getattr(self, "_video_tab_playing", False):
            return
        ok, frame = cap.read()
        if not ok:
            # Loop back to start
            try:
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ok, frame = cap.read()
            except Exception:
                ok = False
            if not ok:
                self._stop_video_preview()
                return
        self._render_video_tab_frame(frame)

    def _stop_video_preview(self):
        try:
            if hasattr(self, "_video_tab_timer"):
                self._video_tab_timer.stop()
        except Exception as _ex:
            _log_warning("MainWindow._stop_video_preview", exc=_ex)
        try:
            if getattr(self, "_video_tab_capture", None) is not None:
                self._video_tab_capture.release()
        except Exception as _ex:
            _log_warning("MainWindow._stop_video_preview", exc=_ex)
        self._video_tab_capture = None
        self._video_tab_playing = False

    def _video_play_pause(self):
        """Toggle playback."""
        if getattr(self, "_video_tab_capture", None) is None:
            # No video loaded yet — try to load current selection
            if hasattr(self, "video_list_widget") and self.video_list_widget.currentItem():
                self._on_video_list_selected(
                    self.video_list_widget.currentItem(), None)
            return
        self._video_tab_playing = not getattr(self, "_video_tab_playing", False)
        if self._video_tab_playing:
            self._video_tab_timer.start(40)
            if hasattr(self, "video_play_btn"):
                self.video_play_btn.setText("⏸ Duraklat")
        else:
            self._video_tab_timer.stop()
            if hasattr(self, "video_play_btn"):
                self.video_play_btn.setText("▶ Oynat")

    def _video_pause(self):
        if hasattr(self, "_video_tab_timer"):
            try: self._video_tab_timer.stop()
            except Exception: pass
        self._video_tab_playing = False
        if hasattr(self, "video_play_btn"):
            self.video_play_btn.setText("▶ Oynat")

    def _video_restart(self):
        cap = getattr(self, "_video_tab_capture", None)
        if cap is None:
            return
        try:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = cap.read()
            if ok:
                self._render_video_tab_frame(frame)
        except Exception as _ex:
            _log_warning("MainWindow._video_restart", exc=_ex)

    def _video_open_external(self):
        """Open the currently selected video in the OS default player."""
        p = getattr(self, "_video_current_path", None)
        if p is None or not p.exists():
            self.statusBar().showMessage("Video seçilmedi", 2500)
            return
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(p))
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as ex:
            QMessageBox.critical(self, "Hata",
                                 f"Video açılamadı:\n{ex}")

    def _rebuild_videos_list(self):
        """Repopulate the dedicated Video tab from self.current_files."""
        if not hasattr(self, "videos_list_layout"):
            return
        # Clear previous rows (keep the trailing stretch)
        while self.videos_list_layout.count() > 1:
            it = self.videos_list_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        self.video_rows = []
        n = 0
        for f in self.current_files or []:
            if f.suffix.lower() not in VIDEO_EXTS:
                continue
            vrow = VideoChoiceRow(f)
            # Hide the checkbox — selection is meaningless here
            vrow.check.setVisible(False)
            # Double-click opens externally (wrap in try so missing files /
            # permission errors / non-Windows systems don't crash the UI)
            def _open_video(event, path=f):
                try:
                    if hasattr(os, "startfile"):
                        os.startfile(str(path))
                    else:
                        subprocess.Popen(["xdg-open", str(path)])
                except Exception as exc:
                    _log_warning(f"Video açılamadı {path}: {exc}")
            vrow.mouseDoubleClickEvent = _open_video
            self.videos_list_layout.insertWidget(
                self.videos_list_layout.count() - 1, vrow)
            self.video_rows.append((f, vrow))
            n += 1

        # Empty state
        if n == 0:
            empty = QLabel(
                "🎬\n\n"
                "Bu gelişte video bulunamadı.\n"
                "Bir geliş seçtiyseniz Voluson cihazı o geliş için\n"
                "video kaydı üretmemiş olabilir."
            )
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                "color:#909090;font:400 13px 'Segoe UI';padding:60px 40px;"
                "background:transparent;line-height:1.6;"
            )
            self.videos_list_layout.insertWidget(
                self.videos_list_layout.count() - 1, empty)

        if hasattr(self, "videos_count_label"):
            self.videos_count_label.setText(f"{n} video")

    def _goto_videos_tab(self):
        """Switch the main tab widget to the Videos tab."""
        idx = getattr(self, "_videos_tab_index", -1)
        if idx >= 0 and hasattr(self, "tabs"):
            self.tabs.setCurrentIndex(idx)
