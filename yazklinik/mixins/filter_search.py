"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _FilterSearchMixin
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

class _FilterSearchMixin:
    """MainWindow methods related to FilterSearch. Mixed into MainWindow via MRO."""

    def _show_advanced_search_dialog(self):
        """Multi-criteria patient search: name + flags + date range + EDD."""
        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("🔎 Gelişmiş Arama")
        dlg.resize(760, 680)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(8)

        # v68: Hero header
        hero = QLabel(
            "<div style='padding:14px 18px;'>"
            "<div style='font-size:18px;font-weight:800;color:#FFFFFF;'>"
            "🔎  Gelişmiş Arama</div>"
            "<div style='color:rgba(255,255,255,0.85);margin-top:4px;"
            "font-size:11.5px;'>"
            "İsim, yaş, bayrak ve tarih aralığı ile çoklu kriter arama. "
            "Sonuçlara tıklayarak hastaya gidin."
            "</div></div>")
        hero.setTextFormat(Qt.RichText)
        hero.setStyleSheet(
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
            hero.setGraphicsEffect(shf)
        except Exception as _ex:
            _log_warning("adv search hero shadow", exc=_ex)
        lay.addWidget(hero)

        # Criteria box
        form_box = QFrame()
        form_box.setObjectName("InnerBox")
        fl = QGridLayout(form_box)
        fl.setHorizontalSpacing(10)
        fl.setVerticalSpacing(6)

        # Name contains
        fl.addWidget(QLabel("İsim içerir:"), 0, 0)
        name_in = QLineEdit()
        name_in.setPlaceholderText("örn: AYSE")
        fl.addWidget(name_in, 0, 1, 1, 3)

        # Last visit date range
        fl.addWidget(QLabel("Son geliş tarihi:"), 1, 0)
        from PySide6.QtWidgets import QDateEdit
        from PySide6.QtCore import QDate
        last_from = QDateEdit()
        last_from.setCalendarPopup(True)
        last_from.setDisplayFormat("dd.MM.yyyy")
        last_from.setDate(QDate.currentDate().addYears(-2))
        last_to = QDateEdit()
        last_to.setCalendarPopup(True)
        last_to.setDisplayFormat("dd.MM.yyyy")
        last_to.setDate(QDate.currentDate())
        fl.addWidget(last_from, 1, 1)
        fl.addWidget(QLabel("→"), 1, 2)
        fl.addWidget(last_to, 1, 3)
        last_use = QCheckBox("Filtrele")
        last_use.setChecked(False)
        fl.addWidget(last_use, 1, 4)

        # EDD range
        fl.addWidget(QLabel("EDD (tahmini doğum) aralığı:"), 2, 0)
        edd_from = QDateEdit()
        edd_from.setCalendarPopup(True)
        edd_from.setDisplayFormat("dd.MM.yyyy")
        edd_from.setDate(QDate.currentDate())
        edd_to = QDateEdit()
        edd_to.setCalendarPopup(True)
        edd_to.setDisplayFormat("dd.MM.yyyy")
        edd_to.setDate(QDate.currentDate().addMonths(3))
        fl.addWidget(edd_from, 2, 1)
        fl.addWidget(QLabel("→"), 2, 2)
        fl.addWidget(edd_to, 2, 3)
        edd_use = QCheckBox("Filtrele")
        fl.addWidget(edd_use, 2, 4)

        # Visit count range
        fl.addWidget(QLabel("Geliş sayısı:"), 3, 0)
        from PySide6.QtWidgets import QSpinBox
        visit_min = QSpinBox(); visit_min.setRange(0, 999); visit_min.setValue(1)
        visit_max = QSpinBox(); visit_max.setRange(0, 999); visit_max.setValue(99)
        fl.addWidget(visit_min, 3, 1)
        fl.addWidget(QLabel("→"), 3, 2)
        fl.addWidget(visit_max, 3, 3)
        visit_use = QCheckBox("Filtrele")
        fl.addWidget(visit_use, 3, 4)

        # Flag combinations
        fl.addWidget(QLabel("Bayraklar (hepsi olmalı):"), 4, 0)
        flag_box = QFrame()
        flag_lay = QGridLayout(flag_box)
        flag_lay.setContentsMargins(0, 0, 0, 0)
        flag_lay.setSpacing(4)
        flag_checks = {}
        for i, (fkey, flabel, level) in enumerate(PATIENT_FLAGS):
            cb = QCheckBox(flabel)
            colour = {"danger": "#C42B1C", "warning": "#C46500",
                      "info": "#005A9E", "good": "#107C10"
                      }.get(level, "#202020")
            cb.setStyleSheet(f"color:{colour};font:600 11px 'Segoe UI';")
            flag_checks[fkey] = cb
            flag_lay.addWidget(cb, i // 3, i % 3)
        fl.addWidget(flag_box, 4, 1, 1, 4)

        lay.addWidget(form_box)

        # Results
        res_hdr = QLabel("<b>Sonuçlar</b>")
        res_hdr.setStyleSheet(accent_label_style(font_size=12, padding="4px"))
        lay.addWidget(res_hdr)

        res_list = QListWidget()
        res_list.setStyleSheet(
            "QListWidget{background:#FFFFFF;border:1px solid #C8C8C8;}"
            "QListWidget::item{padding:6px 8px;border-bottom:1px solid #F0F0F0;}"
            "QListWidget::item:selected{background:#E5EEF7;}")
        lay.addWidget(res_list, 1)

        status_lbl = QLabel("Kriter seçin ve Ara'ya tıklayın")
        status_lbl.setStyleSheet(subtle_text_style(font_size=11))
        lay.addWidget(status_lbl)

        # Buttons
        btn_row = QHBoxLayout()
        search_btn = QPushButton("🔍 Ara")
        search_btn.setStyleSheet(
            "background:#0078D4;color:white;padding:8px 20px;font:600 12px;"
            "border:none;border-radius:3px;")
        close_btn = QPushButton("Kapat")
        btn_row.addStretch()
        btn_row.addWidget(search_btn)
        btn_row.addWidget(close_btn)
        lay.addLayout(btn_row)

        def _run_search():
            status_lbl.setText("⌛ Aranıyor...")
            QApplication.processEvents()
            res_list.clear()

            # Build the filter criteria
            name_q = name_in.text().strip().lower()
            wanted_flags = [k for k, cb in flag_checks.items() if cb.isChecked()]
            use_last_date = last_use.isChecked()
            use_edd_date = edd_use.isChecked()
            use_visit_count = visit_use.isChecked()

            # Query DB for candidate patients
            with db_conn() as con:
                rows = con.execute(
                    "SELECT folder_key, display_name, full_path FROM patients"
                ).fetchall()

            matches = []
            for folder_key, display_name, full_path in rows:
                # Name filter
                if name_q and name_q not in display_name.lower():
                    continue
                # Flag filter
                if wanted_flags:
                    pflags = get_patient_flags(folder_key)
                    active = {f for f, d in pflags.items() if d.get("value") == "1"}
                    if not all(f in active for f in wanted_flags):
                        continue
                # Visit count filter
                if use_visit_count:
                    vc = sum(1 for _ in db_list_visits(folder_key))
                    if vc < visit_min.value() or vc > visit_max.value():
                        continue
                # Last visit date filter
                if use_last_date:
                    last_d = get_patient_last_visit_date(Path(full_path))
                    if last_d is None:
                        continue
                    # Convert QDate → Python date via ISO string (compatible
                    # with all PySide6 versions, unlike toPython() which
                    # requires 6.0+)
                    try:
                        lf = datetime.strptime(
                            last_from.date().toString("yyyy-MM-dd"),
                            "%Y-%m-%d").date()
                        lt = datetime.strptime(
                            last_to.date().toString("yyyy-MM-dd"),
                            "%Y-%m-%d").date()
                    except Exception:
                        continue
                    if not (lf <= last_d.date() <= lt):
                        continue
                # EDD filter
                if use_edd_date:
                    edd = _get_edd_from_latest_pdf(Path(full_path))
                    if edd is None:
                        continue
                    try:
                        ef = datetime.strptime(
                            edd_from.date().toString("yyyy-MM-dd"),
                            "%Y-%m-%d").date()
                        et = datetime.strptime(
                            edd_to.date().toString("yyyy-MM-dd"),
                            "%Y-%m-%d").date()
                    except Exception:
                        continue
                    if not (ef <= edd.date() <= et):
                        continue
                matches.append((display_name, full_path))

            # Render
            for name, fp in matches:
                item = QListWidgetItem(name)
                item.setData(Qt.UserRole, fp)
                res_list.addItem(item)
            status_lbl.setText(f"✓ {len(matches)} sonuç bulundu")

        def _on_double(it):
            fp = it.data(Qt.UserRole)
            if fp:
                try:
                    self._select_patient_by_path(Path(fp))
                    self._highlight_patient_in_list(Path(fp))
                except Exception as _ex:
                    _log_warning("MainWindow._on_double", exc=_ex)
                dlg.accept()

        search_btn.clicked.connect(_run_search)
        close_btn.clicked.connect(dlg.reject)
        # Ensure Escape closes the dialog (QDialog default, but explicit)
        close_btn.setShortcut("Escape")
        res_list.itemDoubleClicked.connect(_on_double)
        dlg.exec()

    def _show_filter_dialog(self, kind: str, flag_key: str = ""):
        """Open a popup dialog listing patients matching a filter.
        Click a patient → main window jumps to them and dialog closes."""
        all_patients = list(getattr(self, "patient_paths", []) or [])
        if not all_patients:
            QMessageBox.information(
                self, "Hasta listesi boş",
                "Hasta listesi henüz yüklenmedi. Önce 'Yenile' deneyin.")
            return
        # Resolve patient_key → Path mapping (key is the folder name)
        key_to_path = {p.name: p for p in all_patients}

        title = ""
        rows: List[Tuple[str, str, Path]] = []  # (display_text, sub_text, path)

        if kind == "flagged":
            title = "🏷️ Bayraklı Hastalar"
            flagged = list_all_flagged_patients()
            for pkey, fnames in flagged.items():
                p = key_to_path.get(pkey)
                if not p:
                    continue
                labels = [PATIENT_FLAG_LABELS.get(f, f) for f in fnames]
                rows.append((format_patient_name(p.name),
                             "  •  ".join(labels), p))
            rows.sort(key=lambda r: r[0])

        elif kind == "flag":
            title = f"Bayrak: {PATIENT_FLAG_LABELS.get(flag_key, flag_key)}"
            keys = list_patients_with_flag(flag_key)
            for pkey in keys:
                p = key_to_path.get(pkey)
                if not p:
                    continue
                last = get_patient_last_visit_date(p)
                last_s = last.strftime("%d.%m.%Y") if last else "-"
                rows.append((format_patient_name(p.name),
                             f"Son geliş: {last_s}", p))
            rows.sort(key=lambda r: r[0])

        elif kind == "near_delivery":
            title = "🤰 Doğumu Yakın Olanlar"
            # Show a cancellable progress dialog while scanning — each patient
            # needs a PDF parse to determine EDD. With parsed-PDF cache this
            # is fast on 2nd run.
            # Note: uses planned_delivery_date() so C-section patients appear
            # ~2 weeks earlier on the list (target 38w rather than 40w).
            from PySide6.QtWidgets import QProgressDialog
            pd = QProgressDialog(
                "Hastaların doğum tarihleri hesaplanıyor...", "İptal",
                0, len(all_patients), self)
            pd.setWindowTitle("Tarama")
            pd.setMinimumDuration(400)  # only show if > 400ms
            pd.setWindowModality(Qt.WindowModal)
            # results: [(path, edd, pdd, is_cs)]
            results: List[Tuple[Path, datetime, datetime, bool]] = []
            today = datetime.now()
            horizon_end = today + timedelta(weeks=6)
            horizon_start = today - timedelta(weeks=2)
            for i, p in enumerate(all_patients):
                if pd.wasCanceled():
                    break
                pd.setValue(i)
                if i % 10 == 0:
                    QApplication.processEvents()
                try:
                    # Skip patients whose pregnancy has already concluded —
                    # if a birth outcome flag is set, this pregnancy isn't
                    # "yaklaşan doğum" any more.
                    _already_delivered = is_pregnancy_closed(p.name)
                    if _already_delivered:
                        continue
                    edd = _get_edd_from_latest_pdf(p)
                    if not edd:
                        continue
                    is_cs = is_c_section_planned(p.name)
                    pdd = planned_delivery_date(p.name, edd)
                    if pdd is None:
                        continue
                    # Filter by PDD (C-section-adjusted) so elective C/S
                    # patients appear on the list 2 weeks earlier.
                    if horizon_start <= pdd <= horizon_end:
                        results.append((p, edd, pdd, is_cs))
                except Exception:
                    continue
            pd.setValue(len(all_patients))
            # Sort by planned (effective) date — C-section patients that are
            # closer to 38w surface above normal-delivery patients at 40w.
            results.sort(key=lambda x: x[2])
            for p, edd, pdd, is_cs in results:
                days_to_pdd = (pdd - today).days
                if is_cs:
                    tag = "🩺 Sezaryen planı"
                    date_label = "Planlı tarih"
                else:
                    tag = "👶 Normal doğum"
                    date_label = "EDD"
                if days_to_pdd >= 0:
                    sub = (f"{tag}  ·  {date_label}: "
                           f"{pdd.strftime('%d.%m.%Y')}  ·  "
                           f"{days_to_pdd} gün kaldı")
                else:
                    sub = (f"{tag}  ·  {date_label}: "
                           f"{pdd.strftime('%d.%m.%Y')}  ·  "
                           f"{-days_to_pdd} gün geçti")
                # For C-section cases also show the raw EDD so the doctor
                # can cross-check — "planlı 25.03, 40-hafta 08.04"
                if is_cs and edd != pdd:
                    sub += f"  ·  40-hafta EDD: {edd.strftime('%d.%m.%Y')}"
                last = get_patient_last_visit_date(p)
                last_s = last.strftime("%d.%m.%Y") if last else "-"
                sub += f"  ·  Son geliş: {last_s}"
                rows.append((format_patient_name(p.name), sub, p))

        elif kind == "no_visit_45":
            title = "⏰ Takibi Bırakanlar — erken uyarı (45+ gün)"
            # No PDF parsing needed for this — only folder-name date parsing
            # which is very fast (no disk IO beyond the cached subfolder list).
            # v68: exclude patients whose pregnancy has closed (delivered
            # normal or cesarean) AND gynecologic-only patients (no
            # obstetric PDFs) — the doctor asked for these NOT to
            # appear in the dropout list anymore, since they're not
            # "dropped" — they just don't need prenatal follow-up.
            results = find_patients_no_visit_since(all_patients, days_threshold=45)
            for p, last_d, days in results:
                if is_pregnancy_closed(p.name):
                    continue
                if is_gynecologic_patient(p):
                    continue
                rows.append((format_patient_name(p.name),
                             f"Son geliş: {last_d.strftime('%d.%m.%Y')}  ·  "
                             f"{days} gün geçti", p))

        elif kind == "no_visit_60":
            title = "🚪 Takipten Düşenler (2 ay / 60+ gün)"
            # Same underlying scan as no_visit_45, stricter threshold. These
            # patients effectively stopped follow-up — list them so the
            # doctor can decide who to call / who's delivered elsewhere.
            results = find_patients_no_visit_since(all_patients, days_threshold=DAYS_ACTIVE_CUTOFF)
            for p, last_d, days in results:
                # Render "2 ay 5 gün" instead of "65 gün" for readability
                months = days // 30
                rem_days = days % 30
                if months >= 1:
                    human = f"{months} ay"
                    if rem_days > 0:
                        human += f" {rem_days} gün"
                else:
                    human = f"{days} gün"
                rows.append((format_patient_name(p.name),
                             f"Son geliş: {last_d.strftime('%d.%m.%Y')}  ·  "
                             f"{human} geçti", p))

        elif kind == "active_60":
            title = "💚 Son 2 Ay Aktif Takibim (≤ 60 gün)"
            results = find_patients_active_within(all_patients, days_threshold=DAYS_ACTIVE_CUTOFF)
            for p, last_d, days in results:
                if days == 0:
                    human = "bugün"
                elif days == 1:
                    human = "dün"
                elif days < 7:
                    human = f"{days} gün önce"
                elif days < 30:
                    human = f"{days // 7} hafta önce"
                else:
                    human = f"{days} gün önce"
                rows.append((format_patient_name(p.name),
                             f"Son geliş: {last_d.strftime('%d.%m.%Y')}  ·  "
                             f"{human}", p))

        elif kind == "active_365":
            title = "📆 Son 1 Yıl İçinde Gelen Hastalar (≤ 365 gün)"
            # v68: full-year view — the doctor asked to see every
            # patient seen in the last 12 months, sorted newest first.
            results = find_patients_active_within(all_patients, days_threshold=365)
            for p, last_d, days in results:
                if days == 0:
                    human = "bugün"
                elif days == 1:
                    human = "dün"
                elif days < 7:
                    human = f"{days} gün önce"
                elif days < 30:
                    human = f"{days // 7} hafta önce"
                elif days < 180:
                    human = f"{days // 30} ay önce"
                else:
                    # 6+ months: show month name, year for clarity
                    human = last_d.strftime("%B %Y").lower()
                rows.append((format_patient_name(p.name),
                             f"Son geliş: {last_d.strftime('%d.%m.%Y')}  ·  "
                             f"{human}", p))

        elif kind == "gynecologic":
            title = "♀️ Jinekolojik Hastalar (Obstetrics Report yok)"
            # v68: patients whose PDFs don't carry the "Obstetrics Report"
            # title — these are pelvic/follicular/non-pregnancy scans.
            # Kept separate from pregnancy follow-up stats per doctor's
            # request. A gyn-specific template is on the roadmap.
            for p in all_patients:
                if not is_gynecologic_patient(p):
                    continue
                last_d = get_patient_last_visit_date(p)
                last_s = last_d.strftime('%d.%m.%Y') if last_d else "—"
                rows.append((format_patient_name(p.name),
                             f"Jinekolojik takip  ·  Son geliş: {last_s}", p))

        # Build the popup dialog
        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(720, 540)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)

        # v68 polish — premium hero header with count pill
        hdr = QLabel(
            f"<div style='padding:14px 18px;'>"
            f"<div style='font-size:16px;font-weight:800;color:#FFFFFF;'>"
            f"{title}</div>"
            f"<div style='color:rgba(255,255,255,0.85);margin-top:4px;"
            f"font-size:11.5px;'>"
            f"<b>{len(rows)}</b> hasta · Listeden tıklayarak hastaya gidin"
            f"</div></div>")
        hdr.setTextFormat(Qt.RichText)
        hdr.setStyleSheet(
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
            hdr.setGraphicsEffect(shf)
        except Exception as _ex:
            _log_warning("filter dialog hero shadow", exc=_ex)
        v.addWidget(hdr)

        if not rows:
            empty = QLabel(
                "Bu kritere uyan hasta bulunmadı.\n\n"
                "Bu boş listeyi gördüğünüz için sorun yoktur — eğer beklediğiniz "
                "hasta burada değilse: hasta klasör adının tarih içerdiğinden "
                "(örn. 2024-08-15) ve PDF özeti içinde EDD yazıldığından emin olun.")
            empty.setStyleSheet(
                "color:#606060;font:400 12px 'Segoe UI';padding:30px 20px;")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignCenter)
            v.addWidget(empty, 1)
        else:
            lst = QListWidget()
            lst.setStyleSheet(
                "QListWidget{background:#FFFFFF;border:1px solid #C8C8C8;}"
                "QListWidget::item{padding:6px 8px;border-bottom:1px solid #F0F0F0;}"
                "QListWidget::item:selected{background:#E5EEF7;color:#003366;}")
            for display, sub, p in rows:
                txt = f"{display}\n   {sub}" if sub else display
                item = QListWidgetItem(txt)
                item.setData(Qt.UserRole, str(p))
                lst.addItem(item)

            def _on_double(it):
                pstr = it.data(Qt.UserRole)
                if pstr:
                    try:
                        self._select_patient_by_path(Path(pstr))
                        # Make sure the side list scrolls to it too
                        self._highlight_patient_in_list(Path(pstr))
                    except Exception as ex:
                        _log_warning(f"select from filter failed: {ex}")
                    dlg.accept()

            lst.itemDoubleClicked.connect(_on_double)
            v.addWidget(lst, 1)

            hint = QLabel("Hasta üzerine çift tıklayın → ana ekranda açılır.")
            hint.setStyleSheet(subtle_text_style(font_size=11))
            v.addWidget(hint)

        # Close button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(dlg.accept)
        btn_row.addWidget(close_btn)
        v.addLayout(btn_row)

        dlg.exec()
