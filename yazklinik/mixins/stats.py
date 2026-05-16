"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _StatsMixin
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

class _StatsMixin:
    """MainWindow methods related to Stats. Mixed into MainWindow via MRO."""

    def _open_file(self, path: str):
        """Open a file with the system default app (PDF viewer, etc.)."""
        if not path:
            return
        try:
            if not os.path.exists(path):
                QMessageBox.warning(
                    self, "Dosya Yok",
                    f"Dosya bulunamadı:\n{path}\n\n"
                    "Yeniden yüklemek gerekebilir.")
                return
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except Exception as ex:
            _log_warning(f"_open_file: {ex}")
            QMessageBox.warning(
                self, "Hata",
                f"Dosya açılamadı:\n{ex}")

    def _show_lab_tracker_dialog(self):
        """📋 Tahliller — PDF yükleme + tüm tahlil geçmişi görüntüleme.

        v68-AI: Doctor uploads PDF lab reports (e-Nabız or laboratory
        fax). The parser extracts common Turkish lab values and
        stores them with a test_date. Previous uploads are listed
        chronologically with their extracted values.
        """
        if self.current_patient is None:
            QMessageBox.warning(self, "Hasta Yok",
                                  "Önce bir hasta seçin.")
            return
        key = self.active_patient_key()
        if not key:
            return

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle(
            f"📋 Tahliller — {self.current_patient}")
        dlg.setMinimumSize(980, 720)
        dlg.setModal(False)
        dlg.setStyleSheet("QDialog{background:#F5F7FA;}")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Hero ────────────────────────────────────────────────────
        hero = QFrame()
        hero.setStyleSheet(
            "QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #0078D4,stop:1 #003F6F);"
            "border:none;}")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(24, 18, 24, 18)
        title = QLabel(f"📋 Tahlil Arşivi — {self.current_patient}")
        title.setStyleSheet(
            "color:#FFFFFF;font:800 22px 'Segoe UI';"
            "background:transparent;letter-spacing:-0.3px;")
        hl.addWidget(title)
        sub = QLabel(
            "PDF tetkik raporlarını yükleyin. Sistem "
            "otomatik okur, tarihli arşivler.")
        sub.setStyleSheet(
            "color:rgba(255,255,255,0.88);font:500 12px 'Segoe UI';"
            "background:transparent;")
        hl.addWidget(sub)
        root.addWidget(hero)

        # ── Upload bar ──────────────────────────────────────────────
        upload_bar = QFrame()
        upload_bar.setStyleSheet(
            "QFrame{background:#FFFFFF;"
            "border-bottom:1px solid #E0E0E0;}")
        ul = QHBoxLayout(upload_bar)
        ul.setContentsMargins(20, 12, 20, 12)
        ul.setSpacing(10)

        upload_btn = QPushButton("📤 PDF Tahlil Yükle")
        upload_btn.setCursor(Qt.PointingHandCursor)
        upload_btn.setToolTip(
            "e-Nabız'dan veya laboratuar raporundan PDF yükle.\n"
            "Otomatik olarak değerler çıkarılır.")
        upload_btn.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #00A676,stop:1 #007F58);color:white;"
            "padding:10px 22px;border:none;border-radius:8px;"
            "font:700 13px 'Segoe UI';}"
            "QPushButton:hover{background:#007F58;}")
        ul.addWidget(upload_btn)

        ul.addStretch()

        count_lbl = QLabel("")
        count_lbl.setStyleSheet(
            "color:#555;font:600 12px 'Segoe UI';")
        ul.addWidget(count_lbl)

        root.addWidget(upload_bar)

        # ── Lab results scroll area ────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea{background:#F5F7FA;border:none;}")
        list_w = QWidget()
        list_lay = QVBoxLayout(list_w)
        list_lay.setContentsMargins(20, 16, 20, 20)
        list_lay.setSpacing(12)
        scroll.setWidget(list_w)
        root.addWidget(scroll, 1)

        def _refresh():
            # Clear
            while list_lay.count():
                item = list_lay.takeAt(0)
                w = item.widget()
                if w:
                    w.deleteLater()
            results = list_lab_results(key)
            count_lbl.setText(f"{len(results)} kayıt")
            if not results:
                empty = QLabel(
                    "📋 Henüz tahlil yüklenmemiş.\n\n"
                    "Yukarıdan 📤 PDF Tahlil Yükle butonuyla "
                    "e-Nabız veya laboratuar PDF'lerini ekleyin.\n"
                    "Değerler otomatik çıkarılıp arşivlenecek.")
                empty.setAlignment(Qt.AlignCenter)
                empty.setStyleSheet(
                    "color:#888;font:500 14px 'Segoe UI';"
                    "padding:60px 20px;background:#FFFFFF;"
                    "border:2px dashed #D0D0D0;border-radius:10px;")
                empty.setWordWrap(True)
                list_lay.addWidget(empty)
                list_lay.addStretch()
                return

            for r in results:
                list_lay.addWidget(_build_lab_card(r))
            list_lay.addStretch()

        def _build_lab_card(r):
            card = QFrame()
            card.setStyleSheet(
                "QFrame{background:#FFFFFF;border:1px solid #E0E0E0;"
                "border-radius:10px;}")
            try:
                sh = QGraphicsDropShadowEffect()
                sh.setBlurRadius(10)
                sh.setColor(QColor(0, 0, 0, 25))
                sh.setOffset(0, 2)
                card.setGraphicsEffect(sh)
            except Exception as _ex:
                _log_warning(f"lab card shadow: {_ex}")
            cl = QVBoxLayout(card)
            cl.setContentsMargins(16, 12, 16, 14)
            cl.setSpacing(8)

            # Header row: date + source + delete
            hrow = QHBoxLayout()
            try:
                tdate = datetime.strptime(
                    r["test_date"][:10], "%Y-%m-%d")
                date_str = tdate.strftime("%d.%m.%Y")
            except Exception:
                date_str = r["test_date"] or r["uploaded_at"][:10]
            head_lbl = QLabel(f"📅 <b>{date_str}</b>")
            head_lbl.setStyleSheet(
                "color:#003F6F;font:700 14px 'Segoe UI';"
                "background:transparent;")
            hrow.addWidget(head_lbl)

            src_chip = QLabel(r["source"].upper())
            src_chip.setStyleSheet(
                "color:#0078D4;background:#E3F2FD;"
                "padding:3px 10px;border-radius:10px;"
                "font:700 10px 'Segoe UI';")
            hrow.addWidget(src_chip)

            test_count = len(r["values"])
            cnt_chip = QLabel(f"{test_count} tetkik")
            cnt_chip.setStyleSheet(
                "color:#107C10;background:#EFF9EF;"
                "padding:3px 10px;border-radius:10px;"
                "font:700 10px 'Segoe UI';")
            hrow.addWidget(cnt_chip)

            hrow.addStretch()

            if r.get("pdf_path"):
                open_btn = QPushButton("📄 PDF Aç")
                open_btn.setCursor(Qt.PointingHandCursor)
                open_btn.setStyleSheet(
                    "QPushButton{background:transparent;color:#0078D4;"
                    "border:1px solid #0078D4;padding:4px 10px;"
                    "border-radius:6px;font:600 10px 'Segoe UI';}"
                    "QPushButton:hover{background:#E3F2FD;}")
                open_btn.clicked.connect(
                    lambda _=None, p=r["pdf_path"]: self._open_file(p))
                hrow.addWidget(open_btn)

            del_btn = QPushButton("🗑")
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setToolTip("Bu tahlil kaydını sil")
            del_btn.setStyleSheet(
                "QPushButton{background:transparent;color:#C42B1C;"
                "border:1px solid #C42B1C;padding:4px 10px;"
                "border-radius:6px;font:700 12px 'Segoe UI';}"
                "QPushButton:hover{background:#FDE7E5;}")

            def _del(_=None, lid=r["id"]):
                ok = QMessageBox.question(
                    dlg, "Sil?",
                    f"Bu tahlil kaydını silmek istiyor musunuz?\n"
                    f"Tarih: {date_str}",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No)
                if ok == QMessageBox.Yes:
                    if delete_lab_result(lid):
                        _refresh()
                        self.statusBar().showMessage(
                            "✓ Tahlil silindi", 2000)
            del_btn.clicked.connect(_del)
            hrow.addWidget(del_btn)
            cl.addLayout(hrow)

            # Values table
            if r["values"]:
                from PySide6.QtWidgets import QTableWidget, \
                    QTableWidgetItem, QHeaderView
                tbl = QTableWidget()
                tbl.setColumnCount(4)
                tbl.setHorizontalHeaderLabels(
                    ["Tetkik", "Değer", "Birim", "Referans"])
                tbl.setRowCount(len(r["values"]))
                tbl.setStyleSheet(
                    "QTableWidget{background:#FAFAFA;border:none;"
                    "gridline-color:#EEE;font:500 12px 'Segoe UI';}"
                    "QHeaderView::section{background:#E3F2FD;"
                    "color:#003F6F;padding:6px;border:none;"
                    "font:700 11px 'Segoe UI';}")
                tbl.verticalHeader().setVisible(False)
                tbl.setEditTriggers(QTableWidget.NoEditTriggers)
                tbl.setSelectionBehavior(QTableWidget.SelectRows)
                tbl.setMaximumHeight(
                    min(400, 36 + len(r["values"]) * 26))

                for i, (t, v) in enumerate(sorted(r["values"].items())):
                    tbl.setItem(i, 0, QTableWidgetItem(t))
                    tbl.setItem(i, 1, QTableWidgetItem(
                        str(v.get("value", ""))))
                    tbl.setItem(i, 2, QTableWidgetItem(
                        str(v.get("unit", ""))))
                    tbl.setItem(i, 3, QTableWidgetItem(
                        str(v.get("ref", ""))))
                tbl.resizeColumnsToContents()
                tbl.horizontalHeader().setSectionResizeMode(
                    0, QHeaderView.Stretch)
                cl.addWidget(tbl)
            else:
                no_val = QLabel(
                    "⚠ Otomatik çıkarma başarısız. PDF'i "
                    "elle incelemek için 'PDF Aç' butonuna basın.")
                no_val.setStyleSheet(
                    "color:#C46500;font:600 11px 'Segoe UI';"
                    "background:#FFF4E5;padding:8px 12px;"
                    "border-radius:6px;")
                cl.addWidget(no_val)

            if r.get("notes"):
                nl = QLabel(f"📝 {r['notes']}")
                nl.setStyleSheet(
                    "color:#555;font:500 11px 'Segoe UI';"
                    "padding:4px 0 0 0;background:transparent;")
                nl.setWordWrap(True)
                cl.addWidget(nl)

            return card

        def _upload():
            """Pick PDF(s), parse, save to DB."""
            paths, _ = QFileDialog.getOpenFileNames(
                dlg, "Tahlil PDF'i Seç", "",
                "PDF Dosyaları (*.pdf)")
            if not paths:
                return
            added = 0
            for p in paths:
                try:
                    parsed = parse_lab_pdf(p)
                    save_lab_result(key, p, parsed,
                                     source="upload")
                    added += 1
                except Exception as ex:
                    _log_warning(f"lab upload: {ex}")
                    QMessageBox.warning(
                        dlg, "Yükleme Hatası",
                        f"'{os.path.basename(p)}' yüklenemedi:\n{ex}")
            if added:
                _refresh()
                self.statusBar().showMessage(
                    f"✓ {added} tahlil yüklendi", 3000)
                show_toast(
                    self, f"📋 {added} tahlil yüklendi · "
                           "değerler otomatik çıkarıldı",
                    level="success", duration_ms=3500)

        upload_btn.clicked.connect(_upload)

        _refresh()
        dlg.exec()

    def _show_test_order_dialog(self):
        """🧾 Tetkik Listesi — yapılmış tahlillere ve GA'ya göre
        akıllı öneri listesi + A5 yazdırma.
        """
        if not require_permission(
                "view_test_order", self, "Tetkik listesi"):
            return
        if self.current_patient is None:
            QMessageBox.warning(self, "Hasta Yok",
                                  "Önce bir hasta seçin.")
            return
        key = self.active_patient_key()
        if not key:
            return

        # GA from latest PDF
        ga_days = None
        try:
            if self.current_subfolder:
                pdf = get_latest_pdf_in_folder(self.current_subfolder)
                if pdf:
                    data = parse_pdf_summary_data(pdf)
                    gd = data.get("ga_days")
                    if isinstance(gd, (int, float)):
                        ga_days = int(gd)
        except Exception as _ex:
            _log_warning(f"test order GA: {_ex}")

        flags = get_patient_flags(key)
        recommendations = recommend_lab_tests(key, ga_days, flags)

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle(
            f"🧾 Tetkik Listesi — {self.current_patient}")
        dlg.setMinimumSize(820, 680)
        dlg.setModal(True)
        dlg.setStyleSheet("QDialog{background:#F5F7FA;}")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Hero
        hero = QFrame()
        hero.setStyleSheet(
            "QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #7C3AED,stop:1 #3F1480);border:none;}")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(24, 18, 24, 18)
        title = QLabel(
            f"🧾 Tetkik Listesi — {self.current_patient}")
        title.setStyleSheet(
            "color:#FFF;font:800 22px 'Segoe UI';"
            "background:transparent;")
        hl.addWidget(title)
        if ga_days is not None:
            ga_w = ga_days // 7
            ga_d = ga_days % 7
            sub_txt = (f"Gebelik: {ga_w} hafta {ga_d} gün · "
                        f"{len(recommendations)} öneri")
        else:
            sub_txt = f"Gebelik dışı · {len(recommendations)} öneri"
        sub = QLabel(sub_txt)
        sub.setStyleSheet(
            "color:rgba(255,255,255,0.88);"
            "font:500 12px 'Segoe UI';background:transparent;")
        hl.addWidget(sub)
        root.addWidget(hero)

        if not recommendations:
            empty = QLabel(
                "✅ Tüm rutin tetkikler güncel — ek öneri yok.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(
                "color:#107C10;background:#EFF9EF;"
                "font:700 14px 'Segoe UI';padding:30px;")
            root.addWidget(empty, 1)
            close_btn = QPushButton("Kapat")
            close_btn.setCursor(Qt.PointingHandCursor)
            close_btn.clicked.connect(dlg.accept)
            close_btn.setStyleSheet(
                "QPushButton{background:#666;color:white;"
                "padding:10px 22px;border:none;border-radius:8px;"
                "font:700 13px 'Segoe UI';}")
            bl = QHBoxLayout()
            bl.addStretch()
            bl.addWidget(close_btn)
            bl.addStretch()
            bl.setContentsMargins(20, 12, 20, 16)
            root.addLayout(bl)
            dlg.exec()
            return

        # Scroll area with checkboxes
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            "QScrollArea{background:#F5F7FA;border:none;}")
        cw = QWidget()
        cw.setStyleSheet("background:#F5F7FA;")
        clay = QVBoxLayout(cw)
        clay.setContentsMargins(20, 16, 20, 16)
        clay.setSpacing(8)

        check_map = {}
        prio_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(
            key=lambda r: prio_order.get(r.get("priority", "low"), 3))

        for rec in recommendations:
            row = QFrame()
            prio = rec["priority"]
            if prio == "high":
                border_col = "#C42B1C"
                badge_col = "#C42B1C"
                badge_bg = "#FDE7E5"
                badge_txt = "YÜKSEK"
            elif prio == "medium":
                border_col = "#C46500"
                badge_col = "#C46500"
                badge_bg = "#FFF4E5"
                badge_txt = "ORTA"
            else:
                border_col = "#0078D4"
                badge_col = "#0078D4"
                badge_bg = "#E3F2FD"
                badge_txt = "DÜŞÜK"
            row.setStyleSheet(
                f"QFrame{{background:#FFFFFF;"
                f"border-left:4px solid {border_col};"
                f"border-top:1px solid #E0E0E0;"
                f"border-right:1px solid #E0E0E0;"
                f"border-bottom:1px solid #E0E0E0;"
                f"border-radius:6px;}}")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 10, 12, 10)
            rl.setSpacing(10)

            cb = QCheckBox()
            cb.setChecked(True)
            cb.setStyleSheet(
                "QCheckBox::indicator{width:20px;height:20px;}")
            check_map[rec["test"]] = cb
            rl.addWidget(cb)

            info_col = QVBoxLayout()
            info_col.setSpacing(2)
            name_lbl = QLabel(f"<b>{rec['test']}</b>")
            name_lbl.setStyleSheet(
                "color:#003F6F;font:700 14px 'Segoe UI';"
                "background:transparent;")
            info_col.addWidget(name_lbl)

            reason_txt = rec["reason"]
            if rec.get("last_date"):
                reason_txt += (f" · Son: {rec['last_date']}")
                if rec.get("last_value"):
                    reason_txt += f" ({rec['last_value']})"
            elif rec.get("stale"):
                reason_txt += " · Henüz yapılmamış"
            reason_lbl = QLabel(reason_txt)
            reason_lbl.setStyleSheet(
                "color:#666;font:500 11px 'Segoe UI';"
                "background:transparent;")
            reason_lbl.setWordWrap(True)
            info_col.addWidget(reason_lbl)
            rl.addLayout(info_col, 1)

            badge = QLabel(badge_txt)
            badge.setStyleSheet(
                f"color:{badge_col};background:{badge_bg};"
                f"padding:4px 10px;border-radius:10px;"
                f"font:800 10px 'Segoe UI';")
            rl.addWidget(badge)

            clay.addWidget(row)

        clay.addStretch()
        scroll.setWidget(cw)
        root.addWidget(scroll, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 12, 20, 16)

        sel_all_btn = QPushButton("✓ Hepsini Seç")
        sel_all_btn.setCursor(Qt.PointingHandCursor)
        sel_all_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#0078D4;"
            "border:1px solid #0078D4;padding:8px 14px;"
            "border-radius:6px;font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:#E3F2FD;}")
        sel_all_btn.clicked.connect(
            lambda: [cb.setChecked(True)
                      for cb in check_map.values()])
        btn_row.addWidget(sel_all_btn)

        none_btn = QPushButton("☐ Hiçbirini")
        none_btn.setCursor(Qt.PointingHandCursor)
        none_btn.setStyleSheet(sel_all_btn.styleSheet())
        none_btn.clicked.connect(
            lambda: [cb.setChecked(False)
                      for cb in check_map.values()])
        btn_row.addWidget(none_btn)

        btn_row.addStretch()

        print_btn = QPushButton("🖨 A5 Yazdır")
        print_btn.setCursor(Qt.PointingHandCursor)
        print_btn.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #7C3AED,stop:1 #5A1FB8);color:white;"
            "padding:10px 22px;border:none;border-radius:8px;"
            "font:700 13px 'Segoe UI';}"
            "QPushButton:hover{background:#5A1FB8;}")
        btn_row.addWidget(print_btn)

        close_btn = QPushButton("Kapat")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton{background:#999;color:white;"
            "padding:10px 22px;border:none;border-radius:8px;"
            "font:700 13px 'Segoe UI';}"
            "QPushButton:hover{background:#777;}")
        close_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

        def _print_a5():
            selected = [t for t, cb in check_map.items()
                         if cb.isChecked()]
            if not selected:
                QMessageBox.warning(
                    dlg, "Seçim Yok",
                    "En az bir tetkik seçmelisiniz.")
                return
            self._print_test_order_a5(
                self.current_patient, ga_days, selected)

        print_btn.clicked.connect(_print_a5)
        dlg.exec()

    def _print_test_order_a5(self, patient_name: str,
                              ga_days: Optional[int],
                              selected_tests: list):
        """Print the selected tests as an A5 tetkik istemi."""
        from PySide6.QtPrintSupport import (
            QPrinter, QPrintPreviewDialog)
        from PySide6.QtGui import (QTextDocument, QPageLayout,
                                     QPageSize)
        from PySide6.QtCore import QMarginsF

        doctor = get_clinic_doctor_name()
        today = datetime.now().strftime("%d.%m.%Y")
        ga_txt = ""
        if isinstance(ga_days, (int, float)):
            w = int(ga_days) // 7
            d = int(ga_days) % 7
            ga_txt = f"Gebelik: {w} hafta {d} gün"

        rows_html = ""
        for i, t in enumerate(selected_tests, 1):
            rows_html += (
                f"<tr>"
                f"<td style='padding:4px 6px;border:1px solid #999;"
                f"width:30px;text-align:center;'>{i}</td>"
                f"<td style='padding:4px 6px;border:1px solid #999;'>"
                f"{t}</td>"
                f"<td style='padding:4px 6px;border:1px solid #999;"
                f"width:30px;text-align:center;'>□</td>"
                f"</tr>")

        ga_row_html = ""
        if ga_txt:
            ga_row_html = (
                f"<tr><td style='padding:3px;border:1px solid #999;"
                f"background:#F0F0F0;font-weight:700;'>Durum</td>"
                f"<td style='padding:3px;border:1px solid #999;'>"
                f"{ga_txt}</td></tr>")

        html = f"""
        <html><body style='font-family:Arial,sans-serif;font-size:10pt;
                            margin:0;padding:0;'>
          <div style='text-align:center;margin-bottom:10px;'>
            <div style='font-size:14pt;font-weight:700;color:#003F6F;'>
              TETKİK İSTEMİ
            </div>
            <div style='font-size:9pt;color:#555;'>{doctor}</div>
          </div>
          <table style='width:100%;border-collapse:collapse;
                         font-size:9pt;margin-bottom:10px;'>
            <tr>
              <td style='padding:3px;border:1px solid #999;width:30%;
                         background:#F0F0F0;font-weight:700;'>Hasta</td>
              <td style='padding:3px;border:1px solid #999;'>
                {patient_name}</td>
            </tr>
            <tr>
              <td style='padding:3px;border:1px solid #999;
                         background:#F0F0F0;font-weight:700;'>Tarih</td>
              <td style='padding:3px;border:1px solid #999;'>{today}</td>
            </tr>
            {ga_row_html}
          </table>
          <table style='width:100%;border-collapse:collapse;
                         font-size:9pt;'>
            <thead>
              <tr style='background:#003F6F;color:#FFF;'>
                <th style='padding:5px;border:1px solid #003F6F;
                            width:30px;'>#</th>
                <th style='padding:5px;border:1px solid #003F6F;'>
                  Tetkik</th>
                <th style='padding:5px;border:1px solid #003F6F;
                            width:30px;'>✓</th>
              </tr>
            </thead>
            <tbody>{rows_html}</tbody>
          </table>
          <div style='margin-top:20px;font-size:8pt;color:#777;
                       border-top:1px solid #CCC;padding-top:6px;'>
            Toplam {len(selected_tests)} tetkik · Yazdırıldı: {today}
          </div>
          <div style='margin-top:30px;font-size:9pt;text-align:right;'>
            İmza: _________________<br>
            <span style='color:#555;'>{doctor}</span>
          </div>
        </body></html>
        """

        doc = QTextDocument()
        doc.setHtml(html)

        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.A5))
        printer.setPageOrientation(QPageLayout.Portrait)
        page_layout = printer.pageLayout()
        page_layout.setUnits(QPageLayout.Millimeter)
        page_layout.setMargins(QMarginsF(10, 10, 10, 10))
        printer.setPageLayout(page_layout)

        try:
            preview = QPrintPreviewDialog(printer, self)
            preview.setWindowTitle("🖨 Tetkik İstemi — A5 Önizleme")
            preview.resize(800, 1000)
            preview.paintRequested.connect(doc.print_)
            preview.exec()
        except Exception as ex:
            _log_warning(f"print test order: {ex}")
            QMessageBox.warning(
                self, "Yazdırma Hatası",
                f"Yazdırma diyaloğu açılamadı:\n{ex}")

    def _show_infertility_plan_dialog(self):
        """🌸 İnfertilite / Tedavi Planlaması — yazılabilir tedavi
        planı notu (jinekoloji modunda Planlama'ya basınca açılır).

        Hastanın IUI / IVF / ovulasyon indüksiyonu / cerrahi planı,
        ilaç protokolü, takip planı, vb. serbest metin olarak yazılır.
        Otomatik kaydedilir, A4 yazdırılabilir.
        """
        if self.current_patient is None:
            QMessageBox.warning(self, "Hasta Yok",
                                  "Önce bir hasta seçin.")
            return
        key = self.active_patient_key()
        if not key:
            return

        existing = get_infertility_plan(key)

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle(
            f"🌸 Tedavi Planlaması — {self.current_patient}")
        dlg.setMinimumSize(820, 700)
        dlg.setModal(True)
        dlg.setStyleSheet("QDialog{background:#F5F7FA;}")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Hero
        hero = QFrame()
        hero.setStyleSheet(
            "QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #B5368A,stop:1 #6F2256);border:none;}")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(24, 18, 24, 18)
        title = QLabel(
            f"🌸 Tedavi Planlaması — {self.current_patient}")
        title.setStyleSheet(
            "color:#FFF;font:800 22px 'Segoe UI';"
            "background:transparent;letter-spacing:-0.3px;")
        hl.addWidget(title)
        sub = QLabel(
            "İnfertilite / jinekoloji tedavi protokolü, ilaç planı, "
            "takip programı — otomatik kaydedilir.")
        sub.setStyleSheet(
            "color:rgba(255,255,255,0.88);"
            "font:500 12px 'Segoe UI';background:transparent;")
        hl.addWidget(sub)
        root.addWidget(hero)

        # Template chip bar — quick insert templates
        chip_bar = QFrame()
        chip_bar.setStyleSheet(
            "QFrame{background:#FFFFFF;"
            "border-bottom:1px solid #E0E0E0;}")
        cl = QHBoxLayout(chip_bar)
        cl.setContentsMargins(20, 8, 20, 8)
        cl.setSpacing(6)
        cl.addWidget(QLabel("📌 Şablon ekle:"))

        # Plan text editor
        editor = QTextEdit()
        editor.setStyleSheet(
            "QTextEdit{background:#FFFFFF;border:none;"
            "padding:18px 22px;font:500 13.5px 'Segoe UI';"
            "color:#222;line-height:1.5;}")
        editor.setPlainText(existing)
        editor.setPlaceholderText(
            "Bu hastanın tedavi planını yazın...\n\n"
            "Örnek başlıklar:\n"
            "• Tanı / Endikasyon\n"
            "• Önceki tedaviler\n"
            "• Bu siklusun planı (protokol, ilaç dozları, takip)\n"
            "• Beklenen takvim (USG, hCG, transfer tarihi)\n"
            "• Hasta ile konuşulanlar")

        templates = [
            ("Ovulasyon İndüksiyonu",
             "🌱 OVULASYON İNDÜKSİYONU PROTOKOLÜ\n"
             "─────────────────────────────────\n"
             "Tanı: \n"
             "Önceki sikluslar: \n"
             "\n"
             "Bu siklus:\n"
             "  • İlaç: Letrozole 5 mg, siklus 3-7. günler\n"
             "  • USG takip: 10. gün (folikül boyutu, "
             "endometrium kalınlığı)\n"
             "  • Trigger: Ovitrelle 250 mcg "
             "(folikül ≥18 mm olduğunda)\n"
             "  • İlişki/IUI: trigger sonrası 36 saat\n"
             "  • β-hCG: trigger sonrası 14 gün\n"
             "\n"
             "Notlar:\n"),
            ("IUI Planı",
             "💉 İNTRAUTERİN İNSEMİNASYON (IUI) PLANI\n"
             "─────────────────────────────────────\n"
             "Tanı: \n"
             "Eş analizi (tarih + sonuç): \n"
             "Tubal patens (HSG): \n"
             "\n"
             "Stimülasyon: \n"
             "  • İlaç: \n"
             "  • USG takvimi: \n"
             "\n"
             "IUI günü:\n"
             "  • Trigger: \n"
             "  • IUI zamanı: \n"
             "  • Hazırlanmış sperm parametreleri: \n"
             "\n"
             "Luteal destek: \n"
             "β-hCG: \n"
             "\n"
             "Notlar:\n"),
            ("IVF/ICSI Protokolü",
             "🧬 IVF / ICSI PROTOKOLÜ\n"
             "─────────────────────\n"
             "Tanı: \n"
             "AMH: \n"
             "AFC: \n"
             "Önceki sikluslar: \n"
             "\n"
             "Protokol seçimi: (uzun agonist / antagonist / mini-IVF)\n"
             "İlaç dozları:\n"
             "  • FSH: \n"
             "  • Antagonist (GnRH-ant) başlangıç: \n"
             "  • Trigger: \n"
             "\n"
             "USG takvimi: \n"
             "OPU planlanan tarih: \n"
             "ET planlanan tarih: \n"
             "Embriyo transferi: (taze / dondurulmuş, "
             "blastokist sayısı)\n"
             "\n"
             "Luteal destek: \n"
             "β-hCG: \n"
             "\n"
             "Notlar:\n"),
            ("Cerrahi Plan",
             "🔪 CERRAHİ PLANLAMA\n"
             "──────────────────\n"
             "Endikasyon: \n"
             "Planlanan operasyon: \n"
             "Cerrahi yaklaşım: (laparoskopi / laparotomi / "
             "histeroskopi)\n"
             "Ameliyat tarihi: \n"
             "Hastane: \n"
             "Anestezi: \n"
             "\n"
             "Pre-op tetkikler:\n"
             "  • Hemogram, biyokimya, koagülasyon\n"
             "  • EKG, akciğer grafisi\n"
             "  • Anestezi konsültasyonu\n"
             "\n"
             "Risk konuşulan hasta: ☐\n"
             "Onam alındı: ☐\n"
             "\n"
             "Post-op plan: \n"
             "Notlar:\n"),
            ("Endometriozis Yönetimi",
             "🌸 ENDOMETRİOZİS YÖNETİMİ\n"
             "────────────────────────\n"
             "Endometriozis evresi (rASRM): \n"
             "Ana semptom: (dismenore / dispareuni / kronik "
             "pelvik ağrı / infertilite)\n"
             "\n"
             "Mevcut tedavi: \n"
             "  • Hormonal: (KOK / progestin / GnRH analoğu / "
             "Dienogest)\n"
             "  • Analjezik: \n"
             "\n"
             "Cerrahi indikasyon: \n"
             "Fertilite planı: \n"
             "\n"
             "Takip:\n"
             "  • Yan etki kontrolü: \n"
             "  • USG: \n"
             "  • CA-125: \n"
             "\n"
             "Notlar:\n"),
            ("PGT Planlaması",
             "🧪 PRE-İMPLANTASYON GENETİK TEST (PGT) PLANI\n"
             "──────────────────────────────────────────\n"
             "Endikasyon: "
             "(PGT-A / PGT-M / PGT-SR)\n"
             "  • İleri anne yaşı (≥38)\n"
             "  • Tekrarlayan düşük (≥2)\n"
             "  • Monogenik hastalık (gen: ...)\n"
             "  • Translokasyon taşıyıcılığı\n"
             "\n"
             "Genetik danışmanlık (tarih/doktor): \n"
             "Karyotip sonuçları (eş): \n"
             "\n"
             "IVF protokolü: \n"
             "Biyopsi planı: (gün 3 blastomere / gün 5-6 "
             "blastokist trofektoderm)\n"
             "Embriyo dondurma: vitrifikasyon\n"
             "FET planı: (doğal siklus / HRT)\n"
             "\n"
             "Notlar:\n"),
            ("OHSS Riski + Yönetim",
             "⚠ OHSS RİSKİ VE YÖNETİMİ\n"
             "────────────────────────\n"
             "Risk faktörleri:\n"
             "  ☐ PCOS\n"
             "  ☐ AMH >3.4 ng/mL\n"
             "  ☐ AFC >24\n"
             "  ☐ Genç hasta (<35)\n"
             "  ☐ Önceki OHSS öyküsü\n"
             "  ☐ Folikül sayısı >20\n"
             "  ☐ E2 >3500 pg/mL\n"
             "\n"
             "Önleyici strateji:\n"
             "  • GnRH antagonist protokolü\n"
             "  • GnRH agonist trigger (hCG yerine)\n"
             "  • Freeze-all stratejisi\n"
             "  • Cabergoline 0.5 mg/gün × 8 gün\n"
             "\n"
             "Takip:\n"
             "  • Günlük: kilo, bel çevresi, idrar çıkışı\n"
             "  • Hct, Na, K, Cr, albümin\n"
             "  • USG: asit/plevral efüzyon\n"
             "\n"
             "Hospitalizasyon kriterleri:\n"
             "  • Hct >45%\n"
             "  • Ciddi asit/dispne\n"
             "  • Oligüri\n"
             "  • Tromboemboli riski\n"
             "\n"
             "Notlar:\n"),
            ("Mikro-TESE",
             "🔬 MİKRO-TESE (Azospermi Yönetimi)\n"
             "─────────────────────────────────\n"
             "Azospermi tipi: (obstrüktif / non-obstrüktif)\n"
             "FSH: \n"
             "LH: \n"
             "Testosteron: \n"
             "AMH (inhibin-B alternatifi): \n"
             "Karyotip: \n"
             "Y-mikrodelesyon: \n"
             "Testis hacmi (USG): \n"
             "\n"
             "Ameliyat tarihi: \n"
             "Ameliyat öncesi ICSI takvimi:\n"
             "  • Kadın stimülasyonu başlangıç: \n"
             "  • OPU tahmini tarih: \n"
             "  • Mikro-TESE aynı gün ICSI için senkronize\n"
             "\n"
             "Sonuç (sperm bulundu mu): \n"
             "Kriyoprezervasyon: \n"
             "\n"
             "Notlar:\n"),
            ("Lüteal Faz Defekti",
             "🩸 LÜTEAL FAZ DEFEKTİ\n"
             "──────────────────────\n"
             "Tanı: (LH-day 7 progesteron <10 ng/mL veya "
             "endometrial out-of-phase)\n"
             "Etiyoloji:\n"
             "  ☐ Hipotiroidizm\n"
             "  ☐ Hiperprolaktinemi\n"
             "  ☐ Kötü folikülogenez\n"
             "  ☐ Tekrarlayan düşük\n"
             "\n"
             "Luteal destek:\n"
             "  • Vajinal progesteron 200 mg × 3/gün\n"
             "  • VEYA IM progesteron 50 mg/gün\n"
             "  • Başlama: ovulasyondan 2 gün sonra\n"
             "  • Süre: hCG + ise 10-12 hf'ya kadar\n"
             "\n"
             "Takip:\n"
             "  • Siklus ortası: folikül USG\n"
             "  • Luteal: progesteron değeri\n"
             "\n"
             "Notlar:\n"),
            ("PCOS Tedavi Planı",
             "🌸 POLİKİSTİK OVER SENDROMU (PCOS)\n"
             "───────────────────────────────────\n"
             "Rotterdam kriterleri:\n"
             "  ☐ Oligo/anovulasyon\n"
             "  ☐ Klinik/biyokimyasal hiperandrojenemi\n"
             "  ☐ USG'de polikistik over morfolojisi\n"
             "\n"
             "Metabolik durum:\n"
             "  • BMI: \n"
             "  • Açlık insülin / HOMA-IR: \n"
             "  • OGTT 2h: \n"
             "  • Lipid profili: \n"
             "\n"
             "Öncelikli şikayet: "
             "(düzensiz regl / hirsutizm / infertilite / "
             "metabolik)\n"
             "\n"
             "Tedavi:\n"
             "  • Yaşam tarzı: %5-10 kilo kaybı hedef\n"
             "  • Metformin 500 mg × 2-3/gün (insülin direnci)\n"
             "  • KOK (gebelik istemiyor + hirsutizm)\n"
             "  • Letrozole/Klomifen (gebelik istiyor)\n"
             "  • Spironolakton 50-100 mg (hirsutizm)\n"
             "  • Kozmetik (lazer/elektroliz)\n"
             "\n"
             "Takip: 3-6 ayda bir AKŞ, HbA1c, lipid\n"
             "\n"
             "Notlar:\n"),
            ("Myom Takibi / Tedavi",
             "🫧 MYOM TAKİBİ / TEDAVİSİ\n"
             "────────────────────────\n"
             "Myom sayısı ve lokalizasyon: \n"
             "En büyük myom çapı: \n"
             "FIGO tipi (0-8): \n"
             "\n"
             "Semptomlar:\n"
             "  ☐ Menoraji\n"
             "  ☐ Ağrı (dismenore/baskı)\n"
             "  ☐ İnfertilite\n"
             "  ☐ Asemptomatik\n"
             "\n"
             "Laboratuvar: Hgb \n"
             "Fertilite isteği: \n"
             "\n"
             "Tedavi seçenekleri:\n"
             "  • Takip (asemptomatik, <5 cm)\n"
             "  • Medikal: traneksamik asit, KOK, LNG-IUD, "
             "GnRH analoğu\n"
             "  • Cerrahi: myomektomi (LAP/HSK/laparotomi), "
             "histerektomi\n"
             "  • UAE (uterin arter embolizasyonu)\n"
             "  • HIFU\n"
             "\n"
             "Planlanan yaklaşım: \n"
             "Takip: 6 aylık USG\n"
             "\n"
             "Notlar:\n"),
            ("Anormal Uterin Kanama",
             "🩸 ANORMAL UTERİN KANAMA (PALM-COEIN)\n"
             "─────────────────────────────────────\n"
             "PALM (yapısal):\n"
             "  ☐ Polip      ☐ Adenomyozis\n"
             "  ☐ Leiomyom   ☐ Malignite/hiperplazi\n"
             "\n"
             "COEIN (non-yapısal):\n"
             "  ☐ Koagülopati\n"
             "  ☐ Ovulatuar disfonksiyon\n"
             "  ☐ Endometrial\n"
             "  ☐ İyatrojenik\n"
             "  ☐ Sınıflandırılamayan\n"
             "\n"
             "Tetkikler:\n"
             "  • TSH, prolaktin, androjen profili\n"
             "  • vWF, PT/aPTT (koagülopati)\n"
             "  • USG (TV), SIS/HSG\n"
             "  • Endometrial biyopsi (≥45 yaş veya "
             "risk faktörü)\n"
             "\n"
             "Tedavi:\n"
             "  • Akut: traneksamik asit, KOK\n"
             "  • Uzun dönem: LNG-IUD, siklik progestin, "
             "KOK\n"
             "  • Cerrahi: polip/myom eksizyonu, "
             "endometrial ablasyon, histerektomi\n"
             "\n"
             "Notlar:\n"),
            ("Menopoz / HRT",
             "🌺 MENOPOZ / HORMON REPLASMAN TEDAVİSİ\n"
             "──────────────────────────────────────\n"
             "Son adet tarihi: \n"
             "Menopoz semptomları:\n"
             "  ☐ Vazomotor (sıcak basma/gece terlemeleri)\n"
             "  ☐ Genitoüriner (GSM: vajinal kuruluk, "
             "dispareuni)\n"
             "  ☐ Ruh hali / uyku\n"
             "  ☐ Osteoporoz riski\n"
             "\n"
             "Baseline:\n"
             "  • Mammografi: \n"
             "  • TSH, lipid, glukoz\n"
             "  • DXA (kemik dansitometrisi)\n"
             "  • Jinekolojik muayene + smear\n"
             "\n"
             "HRT endikasyonu/kontrendikasyonu:\n"
             "  • Yaş <60, menopoz <10 yıl (window of opp.)\n"
             "  • Kontrendikasyon: aktif meme ca, VTE öykü, "
             "kontrol edilmeyen HT\n"
             "\n"
             "Seçim:\n"
             "  • Uterus var → kombine (estrojen + "
             "progestin)\n"
             "  • Uterus yok (histerektomi) → sadece "
             "estrojen\n"
             "  • Sadece GSM → lokal vajinal estrojen\n"
             "\n"
             "Takip: 3 ay sonra, sonra yıllık\n"
             "\n"
             "Notlar:\n"),
            ("Tekrarlayan Gebelik Kaybı",
             "💔 TEKRARLAYAN GEBELİK KAYBI\n"
             "──────────────────────────────\n"
             "Tanım: ≥2 ardışık klinik gebelik kaybı\n"
             "Gebelik sayısı: \n"
             "Kayıp haftaları: \n"
             "\n"
             "Değerlendirme:\n"
             "  • Anatomik: USG + SIS/HSG + histeroskopi\n"
             "  • Genetik: çift karyotip, abort materyali\n"
             "  • Endokrin: TSH, prolaktin, HbA1c, AMH\n"
             "  • İmmünolojik: APA (aCL, anti-β2GP1, LA)\n"
             "  • Trombofilik: FV Leiden, protrombin, MTHFR, "
             "protein C/S, antitrombin\n"
             "  • Spermiogram + DNA fragmantasyonu\n"
             "\n"
             "Tedavi (tanıya göre):\n"
             "  • APS → düşük doz aspirin + LMWH\n"
             "  • Lüteal faz defekti → progesteron desteği\n"
             "  • Uterin anomali → cerrahi düzeltme\n"
             "  • Genetik → PGT-SR\n"
             "  • İdiyopatik → destekleyici, levotiroksin (subklinik "
             "hipotiroidi)\n"
             "\n"
             "Notlar:\n"),
        ]

        def _make_chip(label, txt):
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton{background:#FFE5F1;color:#6F2256;"
                "border:1px solid #B5368A;padding:5px 12px;"
                "border-radius:12px;font:600 10px 'Segoe UI';}"
                "QPushButton:hover{background:#FFCCDD;}")
            btn.clicked.connect(
                lambda: editor.insertPlainText(
                    ("\n\n" if editor.toPlainText().strip()
                      else "") + txt))
            return btn

        for lbl, txt in templates:
            cl.addWidget(_make_chip(lbl, txt))
        cl.addStretch()
        root.addWidget(chip_bar)

        root.addWidget(editor, 1)

        # Bottom bar
        bb = QHBoxLayout()
        bb.setContentsMargins(20, 12, 20, 14)
        save_lbl = QLabel("")
        save_lbl.setStyleSheet(
            "color:#107C10;font:600 11px 'Segoe UI';")
        bb.addWidget(save_lbl)
        bb.addStretch()

        print_btn = QPushButton("🖨 A4 Yazdır")
        print_btn.setCursor(Qt.PointingHandCursor)
        print_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#003F6F;"
            "border:1px solid #003F6F;padding:8px 14px;"
            "border-radius:6px;font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:#E3F2FD;}")
        bb.addWidget(print_btn)

        save_btn = QPushButton("💾 Kaydet")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #B5368A,stop:1 #6F2256);color:white;"
            "padding:10px 22px;border:none;border-radius:8px;"
            "font:700 13px 'Segoe UI';}"
            "QPushButton:hover{background:#6F2256;}")
        bb.addWidget(save_btn)

        close_btn = QPushButton("Kapat")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton{background:#999;color:white;"
            "padding:10px 22px;border:none;border-radius:8px;"
            "font:700 13px 'Segoe UI';}"
            "QPushButton:hover{background:#777;}")
        close_btn.clicked.connect(dlg.reject)
        bb.addWidget(close_btn)
        root.addLayout(bb)

        # Save handler
        def _save():
            txt = editor.toPlainText()
            save_infertility_plan(key, txt)
            save_lbl.setText("✓ Kaydedildi")
            self.statusBar().showMessage(
                "✓ Tedavi planı kaydedildi", 3000)
            QTimer.singleShot(
                3000, lambda: save_lbl.setText(""))

        save_btn.clicked.connect(_save)

        # Auto-save on close
        def _auto_save_on_close():
            try:
                txt = editor.toPlainText()
                if txt.strip() != existing.strip():
                    save_infertility_plan(key, txt)
            except Exception as _ex:
                _log_warning(f"plan auto save: {_ex}")
        dlg.finished.connect(lambda _: _auto_save_on_close())

        # Print A4
        def _print():
            self._print_infertility_plan_a4(
                self.current_patient, editor.toPlainText())
        print_btn.clicked.connect(_print)

        dlg.exec()

    def _print_infertility_plan_a4(self, patient_name: str,
                                     plan_text: str):
        """A4 olarak tedavi planını yazdır."""
        from PySide6.QtPrintSupport import (
            QPrinter, QPrintPreviewDialog)
        from PySide6.QtGui import (QTextDocument, QPageLayout,
                                     QPageSize)
        from PySide6.QtCore import QMarginsF

        if not (plan_text or "").strip():
            QMessageBox.information(
                self, "Boş Plan",
                "Yazdırılacak içerik yok. Önce planı yazın.")
            return

        doctor = get_clinic_doctor_name()
        today = datetime.now().strftime("%d.%m.%Y")
        # Convert plain text to HTML preserving line breaks
        body_html = (
            html.escape(plan_text)
            .replace("\n", "<br>"))

        report_html = f"""
        <html><body style='font-family:Arial,sans-serif;font-size:11pt;
                            margin:0;padding:0;color:#222;'>
          <div style='text-align:center;margin-bottom:14px;'>
            <div style='font-size:18pt;font-weight:700;color:#6F2256;'>
              TEDAVİ PLANLAMASI
            </div>
            <div style='font-size:10pt;color:#555;'>{doctor}</div>
          </div>
          <table style='width:100%;border-collapse:collapse;
                         font-size:10pt;margin-bottom:14px;'>
            <tr>
              <td style='padding:5px 8px;border:1px solid #999;width:25%;
                         background:#FFE5F1;font-weight:700;'>Hasta</td>
              <td style='padding:5px 8px;border:1px solid #999;'>
                {patient_name}</td>
            </tr>
            <tr>
              <td style='padding:5px 8px;border:1px solid #999;
                         background:#FFE5F1;font-weight:700;'>Tarih</td>
              <td style='padding:5px 8px;border:1px solid #999;'>
                {today}</td>
            </tr>
          </table>
          <div style='font-size:11pt;line-height:1.6;
                       padding:10px 0;'>
            {body_html}
          </div>
          <div style='margin-top:30px;font-size:10pt;text-align:right;'>
            İmza: _________________<br>
            <span style='color:#555;'>{doctor}</span>
          </div>
        </body></html>
        """

        doc = QTextDocument()
        doc.setHtml(report_html)
        printer = QPrinter(QPrinter.HighResolution)
        printer.setPageSize(QPageSize(QPageSize.A4))
        printer.setPageOrientation(QPageLayout.Portrait)
        page_layout = printer.pageLayout()
        page_layout.setUnits(QPageLayout.Millimeter)
        page_layout.setMargins(QMarginsF(15, 15, 15, 15))
        printer.setPageLayout(page_layout)

        try:
            preview = QPrintPreviewDialog(printer, self)
            preview.setWindowTitle(
                "🖨 Tedavi Planı — A4 Önizleme")
            preview.resize(900, 1100)
            preview.paintRequested.connect(doc.print_)
            preview.exec()
        except Exception as ex:
            _log_warning(f"print plan: {ex}")
            QMessageBox.warning(
                self, "Yazdırma Hatası",
                f"Yazdırma diyaloğu açılamadı:\n{ex}")

    def _show_record_delivery_dialog(self):
        """🤱 Record a delivery for the current patient.

        v68-AI: Asks the doctor:
          • Delivery date (default: today)
          • Delivery type (Normal / Sezaryen / Vakum / Forseps) — required
          • Baby weight (optional)
          • Baby sex (Erkek / Kız / İkiz / İkiz farklı cins)
          • Brief notes

        On save: stores the delivery, the patient is moved out of
        active prenatal follow-up and into the "🤱 Doğuranlar" group.
        Postpartum nudges (lactation, contraception, mood, 6-week
        visit) start firing.
        """
        if not require_permission(
                "record_delivery", self, "Doğum kaydı"):
            return
        if self.current_patient is None:
            QMessageBox.warning(self, "Hasta Yok",
                                  "Önce bir hasta seçin.")
            return

        patient_key = self.current_patient.name
        try:
            display_name = format_patient_name(patient_key)
        except Exception:
            display_name = patient_key

        # If already recorded, ask if doctor wants to edit/delete
        existing = get_delivery(patient_key)
        if existing:
            choice = QMessageBox.question(
                self, "Doğum Kaydı Zaten Var",
                f"<b>{display_name}</b> hastası için zaten bir doğum "
                f"kaydı var:<br><br>"
                f"📅 <b>Tarih:</b> {existing['delivery_date']}<br>"
                f"🩺 <b>Tip:</b> "
                f"{existing['delivery_type'].title()}<br>"
                f"👶 <b>Bebek:</b> {existing['baby_count']} "
                f"({existing.get('baby_weight_g', '?')} g, "
                f"{existing.get('baby_sex', '?')})"
                f"<br><br>Düzenlemek ister misiniz?",
                QMessageBox.Yes | QMessageBox.No)
            if choice != QMessageBox.Yes:
                return

        # Build dialog
        dlg = QDialog(self)
        dlg.setWindowTitle(f"🤱 Doğum Kaydet — {display_name}")
        dlg.setMinimumSize(560, 600)
        dlg.setModal(True)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Hero
        hero = QWidget()
        hero.setFixedHeight(96)
        hero.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #B5368A,stop:1 #6F2256);")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(24, 12, 24, 12)
        hl.setSpacing(2)
        ht = QLabel("🤱  Doğum Kaydet")
        ht.setStyleSheet(
            "color:white;font:800 22px 'Segoe UI';background:transparent;")
        hl.addWidget(ht)
        hsub = QLabel(display_name)
        hsub.setStyleSheet(
            "color:rgba(255,255,255,0.92);font:600 13px 'Segoe UI';"
            "background:transparent;")
        hl.addWidget(hsub)
        root.addWidget(hero)

        # Body — form
        body = QWidget()
        body.setStyleSheet("background:white;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 18, 24, 12)
        bl.setSpacing(12)

        # Delivery type — biggest decision, big buttons
        type_lbl = QLabel("Doğum şekli:")
        type_lbl.setStyleSheet(
            "color:#6F2256;font:700 13px 'Segoe UI';")
        bl.addWidget(type_lbl)

        type_btn_row = QHBoxLayout()
        type_btn_row.setSpacing(8)
        delivery_type = {"value": ""}
        type_buttons = {}

        def _make_type_btn(value: str, emoji: str, label: str,
                            color: str):
            b = QPushButton(f"{emoji}\n{label}")
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(72)
            b.setCheckable(True)
            b.setStyleSheet(
                f"QPushButton{{background:#FFFFFF;color:{color};"
                f"border:2px solid #E0D0DA;padding:8px;"
                f"font:700 13px 'Segoe UI';border-radius:8px;}}"
                f"QPushButton:hover{{background:#FAF5F8;"
                f"border-color:{color};}}"
                f"QPushButton:checked{{background:{color};"
                f"color:white;border-color:{color};}}")

            def _select(_checked=False, val=value):
                delivery_type["value"] = val
                for bn in type_buttons.values():
                    bn.setChecked(False)
                type_buttons[val].setChecked(True)
            b.clicked.connect(_select)
            type_buttons[value] = b
            return b

        type_btn_row.addWidget(_make_type_btn(
            "normal", "👶", "Normal\nDoğum", "#107C10"))
        type_btn_row.addWidget(_make_type_btn(
            "sezaryen", "🩺", "Sezaryen", "#0078D4"))
        type_btn_row.addWidget(_make_type_btn(
            "vakum", "🔧", "Vakum", "#E58E00"))
        type_btn_row.addWidget(_make_type_btn(
            "forseps", "🔧", "Forseps", "#9A1B1F"))
        bl.addLayout(type_btn_row)

        # Date
        date_lbl = QLabel("Doğum tarihi:")
        date_lbl.setStyleSheet(
            "color:#6F2256;font:700 13px 'Segoe UI';margin-top:6px;")
        bl.addWidget(date_lbl)
        from PySide6.QtWidgets import QDateEdit
        from PySide6.QtCore import QDate
        date_edit = QDateEdit()
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("dd.MM.yyyy")
        date_edit.setDate(QDate.currentDate())
        date_edit.setStyleSheet(
            "QDateEdit{background:white;color:#222;"
            "padding:8px 10px;border:1px solid #C8C8C8;"
            "font:13px 'Segoe UI';border-radius:4px;}")
        bl.addWidget(date_edit)

        # Baby info row
        baby_row = QHBoxLayout()
        baby_row.setSpacing(10)

        # Baby weight
        bw_col = QVBoxLayout()
        bw_lbl = QLabel("Bebek ağırlığı (g):")
        bw_lbl.setStyleSheet(
            "color:#6F2256;font:700 12px 'Segoe UI';")
        bw_col.addWidget(bw_lbl)
        weight_edit = QLineEdit()
        weight_edit.setPlaceholderText("ör: 3450")
        weight_edit.setStyleSheet(
            "QLineEdit{background:white;color:#222;"
            "padding:6px 10px;border:1px solid #C8C8C8;"
            "font:13px 'Segoe UI';border-radius:4px;}")
        bw_col.addWidget(weight_edit)
        baby_row.addLayout(bw_col, 1)

        # Baby count
        bc_col = QVBoxLayout()
        bc_lbl = QLabel("Bebek sayısı:")
        bc_lbl.setStyleSheet(
            "color:#6F2256;font:700 12px 'Segoe UI';")
        bc_col.addWidget(bc_lbl)
        count_combo = QComboBox()
        count_combo.addItems(["1", "2 (ikiz)", "3 (üçüz)"])
        count_combo.setStyleSheet(
            "QComboBox{background:white;color:#222;"
            "padding:6px 10px;border:1px solid #C8C8C8;"
            "font:13px 'Segoe UI';border-radius:4px;}")
        bc_col.addWidget(count_combo)
        baby_row.addLayout(bc_col, 1)

        # Baby sex
        bs_col = QVBoxLayout()
        bs_lbl = QLabel("Cinsiyet:")
        bs_lbl.setStyleSheet(
            "color:#6F2256;font:700 12px 'Segoe UI';")
        bs_col.addWidget(bs_lbl)
        sex_combo = QComboBox()
        sex_combo.addItems(["", "Kız", "Erkek",
                              "İkiz (Kız-Kız)", "İkiz (Erkek-Erkek)",
                              "İkiz (Kız-Erkek)"])
        sex_combo.setStyleSheet(
            "QComboBox{background:white;color:#222;"
            "padding:6px 10px;border:1px solid #C8C8C8;"
            "font:13px 'Segoe UI';border-radius:4px;}")
        bs_col.addWidget(sex_combo)
        baby_row.addLayout(bs_col, 1)
        bl.addLayout(baby_row)

        # Hospital
        hosp_lbl = QLabel("Hastane (opsiyonel):")
        hosp_lbl.setStyleSheet(
            "color:#6F2256;font:700 12px 'Segoe UI';margin-top:6px;")
        bl.addWidget(hosp_lbl)
        hospital_edit = QLineEdit()
        hospital_edit.setPlaceholderText("Doğumun yapıldığı hastane")
        hospital_edit.setStyleSheet(
            "QLineEdit{background:white;color:#222;"
            "padding:6px 10px;border:1px solid #C8C8C8;"
            "font:13px 'Segoe UI';border-radius:4px;}")
        bl.addWidget(hospital_edit)

        # Notes
        notes_lbl = QLabel("Notlar (opsiyonel):")
        notes_lbl.setStyleSheet(
            "color:#6F2256;font:700 12px 'Segoe UI';margin-top:6px;")
        bl.addWidget(notes_lbl)
        notes_edit = QTextEdit()
        notes_edit.setMaximumHeight(80)
        notes_edit.setPlaceholderText(
            "Doğum süresi, komplikasyonlar, anestezi tipi, vb.")
        notes_edit.setStyleSheet(
            "QTextEdit{background:white;color:#222;"
            "padding:6px 10px;border:1px solid #C8C8C8;"
            "font:12px 'Segoe UI';}")
        bl.addWidget(notes_edit)

        # If existing, prefill
        if existing:
            for v in ("normal", "sezaryen", "vakum", "forseps"):
                if existing.get("delivery_type") == v:
                    delivery_type["value"] = v
                    type_buttons[v].setChecked(True)
            try:
                from datetime import date as _date
                d = existing.get("delivery_date", "")[:10]
                y, m, dd = d.split("-")
                date_edit.setDate(QDate(int(y), int(m), int(dd)))
            except Exception as _ex:
                _log_warning(f"prefill date: {_ex}")
            if existing.get("baby_weight_g"):
                weight_edit.setText(str(existing["baby_weight_g"]))
            if existing.get("baby_count"):
                idx = max(0, min(2, int(existing["baby_count"]) - 1))
                count_combo.setCurrentIndex(idx)
            if existing.get("baby_sex"):
                idx = sex_combo.findText(existing["baby_sex"])
                if idx >= 0:
                    sex_combo.setCurrentIndex(idx)
            if existing.get("hospital"):
                hospital_edit.setText(existing["hospital"])
            if existing.get("notes"):
                notes_edit.setPlainText(existing["notes"])

        root.addWidget(body, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 10, 20, 14)

        if existing:
            del_btn = QPushButton("🗑 Kaydı Sil")
            del_btn.setCursor(Qt.PointingHandCursor)
            del_btn.setStyleSheet(
                "QPushButton{background:#FFEBEB;color:#9A1B1F;"
                "padding:8px 18px;border:1px solid #C42B1C;"
                "border-radius:4px;font:600 11px 'Segoe UI';}"
                "QPushButton:hover{background:#FFD8D8;}")
            def _del():
                confirm = QMessageBox.question(
                    self, "Kaydı Sil",
                    f"<b>{display_name}</b> hastasının doğum kaydını "
                    f"silmek istediğinize emin misiniz?<br><br>"
                    f"Hasta tekrar aktif gebelik takibine alınacak.",
                    QMessageBox.Yes | QMessageBox.No)
                if confirm == QMessageBox.Yes:
                    try:
                        delete_delivery(patient_key)
                        show_toast(self,
                                    f"✓ {display_name} kaydı silindi",
                                    level="info")
                        # Refresh patient list / sidebar
                        try:
                            self._refresh_patient_filter_view()
                        except Exception as _ex:
                            _log_warning(f"refresh after del: {_ex}")
                        try:
                            self._refresh_today_dashboard()
                        except Exception as _ex:
                            _log_warning(f"dash after del: {_ex}")
                        dlg.accept()
                    except Exception as ex:
                        QMessageBox.warning(self, "Hata",
                                              f"Silinemedi: {ex}")
            del_btn.clicked.connect(_del)
            btn_row.addWidget(del_btn)

        btn_row.addStretch()

        cancel_btn = QPushButton("İptal")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(
            "QPushButton{background:#E5EEF7;color:#404040;"
            "padding:8px 18px;border:1px solid #B8D4E8;"
            "border-radius:4px;font:500 11px 'Segoe UI';}"
            "QPushButton:hover{background:#D5E5F5;}")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("💾 Kaydet")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #B5368A,stop:1 #6F2256);color:white;"
            "padding:9px 22px;border:none;border-radius:4px;"
            "font:700 12px 'Segoe UI';}"
            "QPushButton:hover{background:#6F2256;}")

        def _save():
            if not delivery_type["value"]:
                QMessageBox.warning(
                    self, "Eksik Bilgi",
                    "Doğum şeklini seçin (Normal / Sezaryen / Vakum "
                    "/ Forseps).")
                return
            try:
                date_str = date_edit.date().toString("yyyy-MM-dd")
                bw = None
                wt = weight_edit.text().strip()
                if wt:
                    try:
                        bw = int(re.sub(r"[^\d]", "", wt))
                    except Exception:
                        bw = None
                bc = count_combo.currentIndex() + 1
                bs = sex_combo.currentText() or None
                hosp = hospital_edit.text().strip() or None
                notes_v = notes_edit.toPlainText().strip() or None

                # Compute GA at delivery if we have LMP
                ga_days = None
                try:
                    visits = self.subfolder_paths or []
                    if visits:
                        pdf = get_latest_pdf_in_folder(visits[0])
                        if pdf:
                            pdata = parse_pdf_summary_data(pdf)
                            ref_ga = pdata.get("ga_days")
                            edd_dt = pdata.get("edd_dt")
                            if edd_dt:
                                from datetime import datetime as _dt
                                d_dt = _dt.strptime(date_str, "%Y-%m-%d")
                                # 280 days from LMP, EDD = LMP + 280
                                # GA at delivery = 280 - days_to_edd
                                days_to_edd = (edd_dt - d_dt).days
                                ga_days = 280 - days_to_edd
                except Exception as _ex:
                    _log_warning(f"GA at delivery: {_ex}")

                record_delivery(
                    patient_key=patient_key,
                    delivery_date=date_str,
                    delivery_type=delivery_type["value"],
                    ga_at_delivery_days=ga_days,
                    baby_count=bc,
                    baby_weight_g=bw,
                    baby_sex=bs,
                    hospital=hosp,
                    notes=notes_v)

                # v68-AI: Behavior log + toast
                try:
                    BehaviorLearner.log_action(
                        "record_delivery",
                        delivery_type["value"],
                        patient_key=patient_key)
                except Exception as _bex:
                    _log_warning(f"behavior log delivery: {_bex}")

                msg_emoji = ("👶" if delivery_type["value"] == "normal"
                              else "🩺")
                msg_label = {
                    "normal": "Normal doğum",
                    "sezaryen": "Sezaryen",
                    "vakum": "Vakum doğum",
                    "forseps": "Forseps doğum",
                }[delivery_type["value"]]
                show_toast(
                    self,
                    f"{msg_emoji} {display_name} → {msg_label} "
                    f"kaydedildi · Doğuranlar grubuna alındı",
                    level="success", duration_ms=5000)

                # Refresh sidebar / dashboard
                try:
                    self._refresh_patient_filter_view()
                except Exception as _ex:
                    _log_warning(f"refresh after delivery: {_ex}")
                try:
                    self._refresh_today_dashboard()
                except Exception as _ex:
                    _log_warning(f"dash after delivery: {_ex}")

                dlg.accept()
            except Exception as ex:
                _log_warning("record_delivery save", exc=ex)
                QMessageBox.warning(self, "Hata",
                                      f"Kaydedilemedi: {ex}")

        save_btn.clicked.connect(_save)
        btn_row.addWidget(save_btn)
        root.addLayout(btn_row)

        dlg.exec()

    def _show_growth_trend_dialog(self):
        """Show a chart of fetal biometry measurements (BPD, AC, FL, HC)
        plotted against gestational age across all visits of the current
        patient. Helps spot growth restriction / macrosomia trends."""
        if not self.current_patient:
            QMessageBox.warning(self, "Hasta Yok",
                                "Önce bir hasta seçin.")
            return

        visits = self.subfolder_paths or []
        if not visits:
            QMessageBox.information(self, "Geliş Yok",
                                    "Bu hastanın hiç gelişi yok.")
            return

        # Collect measurements from each visit's PDF
        # Each row: (ga_days, ga_label, bpd_mm, ac_mm, fl_mm, hc_mm, visit_date)
        rows = []
        skipped_reasons = []  # collect debug info per skipped visit
        for v in visits:
            try:
                pdf = get_latest_pdf_in_folder(v)
                if not pdf:
                    skipped_reasons.append(f"{v.name}: PDF yok")
                    continue
                data = parse_pdf_summary_data(pdf)
                ga_days = data.get("ga_days")

                # Extract measurement value + per-measurement GA label.
                # Voluson stores each biometry as ("45.2mm", "19w3d") so we
                # keep both so the table can show "45.2 (19w3d)".
                def _mm(k):
                    t = data.get(k, ("", ""))
                    if isinstance(t, (tuple, list)) and len(t) >= 1 and t[0]:
                        try:
                            m = re.search(r"(\d+(?:\.\d+)?)", str(t[0]))
                            if m:
                                ga_str = (str(t[1])
                                          if len(t) > 1 and t[1] else "")
                                return (float(m.group(1)), ga_str)
                        except Exception as _ex:
                            _log_warning("MainWindow._mm", exc=_ex)
                    return (None, "")

                # Twin: use fetus 1 only for the chart
                if data.get("is_twin"):
                    f1 = data.get("fetüs_1", {})
                    def _mm_twin(k):
                        t = f1.get(k, ("", ""))
                        if isinstance(t, (tuple, list)) and len(t) >= 1 and t[0]:
                            m = re.search(r"(\d+(?:\.\d+)?)",
                                           str(t[0]))
                            if m:
                                ga_str = (str(t[1])
                                          if len(t) > 1 and t[1] else "")
                                return (float(m.group(1)), ga_str)
                        return (None, "")
                    bpd = _mm_twin("BPD"); ac = _mm_twin("AC")
                    fl = _mm_twin("FL"); hc = _mm_twin("HC")
                else:
                    bpd = _mm("BPD"); ac = _mm("AC")
                    fl = _mm("FL"); hc = _mm("HC")

                # v68-AI: If GA is missing, try to recover it from any
                # of the per-measurement GA strings ("19w3d" beside BPD)
                # — Voluson sometimes shows per-measurement GA but no
                # global AUA/LMP GA. Take the median to avoid outliers.
                if not isinstance(ga_days, (int, float)) or ga_days <= 0:
                    candidates = []
                    for measurement in (bpd, ac, fl, hc):
                        if (isinstance(measurement, (tuple, list))
                                and len(measurement) >= 2):
                            ga_alt = _ga_string_to_days(measurement[1])
                            if ga_alt and ga_alt > 0:
                                candidates.append(ga_alt)
                    if candidates:
                        candidates.sort()
                        ga_days = candidates[len(candidates) // 2]
                        # Log this fallback for transparency
                        _log_warning(
                            f"_show_growth_trend: GA recovered from "
                            f"biometry tags for {v.name}: {ga_days}d")

                # If we STILL don't have GA but have at least one
                # measurement, plot anyway using the visit date as
                # x-axis label (no GA-percentile band but at least
                # the trend is visible).
                if not isinstance(ga_days, (int, float)) or ga_days <= 0:
                    # Last resort: any measurement at all?
                    has_any = any(
                        m[0] is not None
                        for m in (bpd, ac, fl, hc))
                    if not has_any:
                        skipped_reasons.append(
                            f"{v.name}: ne GA ne ölçüm var")
                        continue
                    # Use a placeholder GA so we don't crash;
                    # this row will show in the table but be excluded
                    # from the percentile chart by ga_days==-1 marker.
                    ga_days = -1

                # Visit date
                vdate = _parse_visit_folder_date(v.name)
                date_str = (vdate.strftime("%d.%m.%Y")
                            if vdate else v.name)

                if ga_days >= 0:
                    w = int(ga_days) // 7
                    d = int(ga_days) % 7
                    ga_lbl = f"{w}⁺{d} hf"
                else:
                    ga_lbl = "GA?"
                # Also keep the datetime for inter-visit gap calculations
                rows.append((int(ga_days), ga_lbl, bpd, ac, fl, hc,
                             date_str, vdate))
            except Exception as _ex:
                _log_warning(f"_show_growth_trend_dialog: visit "
                              f"{getattr(v, 'name', '?')}: {_ex}")
                skipped_reasons.append(
                    f"{getattr(v, 'name', '?')}: {_ex}")
                continue

        if not rows:
            # v68-AI: Better error message — explain WHY no data
            # so the doctor knows what to do next instead of just
            # "Veri yok". Count visits + PDFs to give context.
            n_visits = len(visits)
            pdf_count = sum(1 for v in visits
                             if get_latest_pdf_in_folder(v) is not None)
            msg = (
                f"<b>📈 Büyüme Eğrisi Çizilemiyor</b><br><br>"
                f"Bu hastanın <b>{n_visits} gelişi</b> var, bunlardan "
                f"<b>{pdf_count} tanesinde PDF</b> mevcut.<br><br>")
            if pdf_count == 0:
                msg += (
                    "❌ <b>Hiç PDF yok.</b> Büyüme eğrisi için "
                    "gelişlerde Voluson USG raporu (PDF) bulunmalı.<br><br>"
                    "💡 PDF'i NAS klasörüne ekleyin, sonra F5 ile yenileyin.")
            else:
                msg += (
                    "❌ <b>PDF'lerden ölçüm okunamadı.</b> Olası nedenler:<br>"
                    "&nbsp;&nbsp;• PDF'lerde GA (gestasyonel hafta) bilgisi yok<br>"
                    "&nbsp;&nbsp;• Voluson formatı tanınmıyor (eski sürüm?)<br>"
                    "&nbsp;&nbsp;• PDF tarama (resim) — metin değil<br>"
                    "&nbsp;&nbsp;• BPD/AC/FL ölçümleri PDF'de yok<br><br>"
                    "💡 Hastanın PDF özet sekmesine bakıp ölçümlerin "
                    "'BPD', 'AC', 'FL' olarak görüntülenip görüntülenmediğini "
                    "kontrol edin.")
                # Show debug detail per visit (helps doctor understand)
                if skipped_reasons:
                    msg += "<br><br><b>🔍 Detay:</b><br>"
                    for reason in skipped_reasons[:8]:
                        msg += f"&nbsp;&nbsp;• <code>{reason}</code><br>"
                    if len(skipped_reasons) > 8:
                        msg += (f"&nbsp;&nbsp;... ve "
                                f"{len(skipped_reasons) - 8} tane daha")
            QMessageBox.information(self, "Büyüme Eğrisi", msg)
            return

        # v68-AI: Separate rows with valid GA from those without —
        # only valid-GA rows go on the percentile chart, but all rows
        # show in the table below.
        all_rows = list(rows)  # keep all for table
        rows = [r for r in rows if r[0] >= 0]  # chart-eligible only

        if not rows:
            # Have some PDFs but none have GA — show table-only view
            # via fallback message
            QMessageBox.information(
                self, "Büyüme Eğrisi",
                f"<b>📊 Tablo Modu</b><br><br>"
                f"<b>{len(all_rows)} ölçüm</b> bulundu ama hiçbirinde "
                f"GA (gestasyonel hafta) bilgisi yok.<br><br>"
                f"Voluson PDF'lerinde her biyometrinin yanında "
                f"'19w3d' gibi bir etiket olmalı. Bu olmadan "
                f"persantil eğrisi çizilemez.<br><br>"
                f"💡 Hastanın LMP / EDD bilgilerini kontrol edin.")
            return

        # Sort by GA
        rows.sort(key=lambda r: r[0])

        # ── Build a richer, clinical-grade SVG chart ───────────────────────
        # v68: Moved from a basic line-chart to a shaded-percentile
        # layout the doctor can show to patients. Each biometry gets:
        #   • p3-p97 outer band (very light tint)
        #   • p10-p90 inner band (light tint)
        #   • p50 median line (solid)
        #   • Patient's actual measurements as prominent dots + line
        # Larger overall canvas, modern serif-free typography, and
        # clearer axis labels + legend.
        W, H = 880, 520
        ML, MR, MT, MB = 70, 32, 48, 60
        chart_w = W - ML - MR
        chart_h = H - MT - MB

        # Axes ranges — clamp to sensible obstetric window
        min_ga = max(0, min(r[0] for r in rows) - 7)
        max_ga = max(294, max(r[0] for r in rows) + 7)  # 42w ceiling
        # Each measurement is now (value, ga_str) tuple — unwrap the value
        all_vals = [t[0] for r in rows for t in (r[2], r[3], r[4], r[5])
                    if t is not None and t[0] is not None]
        if not all_vals:
            # v68-AI: 1st trimester patients (≤14 wk) typically only
            # have CRL, not BPD/AC/FL/HC. Show a smarter explanation.
            ga_weeks_list = sorted(set(int(r[0]) // 7 for r in rows))
            min_w = ga_weeks_list[0] if ga_weeks_list else 0
            max_w = ga_weeks_list[-1] if ga_weeks_list else 0
            n_visits = len(rows)
            visit_summary = ", ".join(f"{int(r[0])//7}+{int(r[0])%7}"
                                       for r in rows[:5])
            if max_w < 14:
                msg = (
                    f"<b>📈 Bu Hasta Henüz 1. Trimesterde</b><br><br>"
                    f"Hasta <b>{min_w}-{max_w} haftalar</b> arasında "
                    f"({n_visits} geliş: {visit_summary}).<br><br>"
                    f"Bu dönemde Voluson PDF'lerinde sadece "
                    f"<b>CRL</b> ölçümü olur — büyüme eğrisi için "
                    f"gerekli olan <b>BPD/AC/FL/HC</b> ölçümleri "
                    f"<b>20. haftadan sonra</b> başlar.<br><br>"
                    f"💡 Anomali taraması (18-22 hf) ve sonrasındaki "
                    f"USG'lerde grafik otomatik dolacak.")
            else:
                msg = (
                    f"<b>📈 Ölçüm Bulunamadı</b><br><br>"
                    f"Hasta <b>{min_w}-{max_w} haftalar</b> arasında "
                    f"<b>{n_visits} geliş</b> yapmış ({visit_summary}) "
                    f"ama PDF'lerden BPD/AC/FL/HC ölçümleri "
                    f"okunamadı.<br><br>"
                    f"💡 PDF özet sekmesine bakıp ölçümlerin "
                    f"görünüp görünmediğini kontrol edin.")
            QMessageBox.information(self, "Büyüme Eğrisi", msg)
            return
        min_v = 0
        max_v = max(all_vals) * 1.18

        def x_for(ga):
            return ML + (ga - min_ga) / (max_ga - min_ga) * chart_w

        def y_for(v):
            return MT + chart_h - (v - min_v) / (max_v - min_v) * chart_h

        svg_parts = [
            f'<svg width="{W}" height="{H}" xmlns="http://www.w3.org/2000/svg" '
            'style="background:#FFFFFF;border:1px solid #B8B8B8;'
            'border-radius:6px;box-shadow:0 2px 6px rgba(0,0,0,0.05);">'
        ]

        # ── Title + sub-header (rendered inside SVG) ───────────────────────
        svg_parts.append(
            f'<text x="{W/2}" y="24" text-anchor="middle" '
            f'font-family="Segoe UI" font-size="14" font-weight="700" '
            f'fill="#003A66">Fetal Büyüme Takibi — Hadlock Persentilleri</text>')
        svg_parts.append(
            f'<text x="{W/2}" y="40" text-anchor="middle" '
            f'font-family="Segoe UI" font-size="10" font-style="italic" '
            f'fill="#808080">Gölgeli bantlar: p3–p97 (açık) ve p10–p90 (koyu) '
            f'normal popülasyon aralığı</text>')

        # ── Plot chart background grid ─────────────────────────────────────
        # Horizontal grid (mm)
        for i in range(6):
            y = MT + i * chart_h / 5
            val = max_v - i * max_v / 5
            svg_parts.append(
                f'<line x1="{ML}" y1="{y}" x2="{ML + chart_w}" y2="{y}" '
                f'stroke="#F0F0F0" stroke-width="1"/>')
            svg_parts.append(
                f'<text x="{ML - 8}" y="{y + 4}" text-anchor="end" '
                f'font-family="Segoe UI" font-size="10" fill="#606060">'
                f'{int(val)}</text>')

        # Vertical grid — every 2 weeks (finer) but only label every 4
        for w in range(int(min_ga // 7 // 2 * 2), int(max_ga // 7) + 1, 2):
            ga_d = w * 7
            if ga_d < min_ga or ga_d > max_ga:
                continue
            x = x_for(ga_d)
            is_major = (w % 4 == 0)
            line_color = "#E8E8E8" if is_major else "#F5F5F5"
            svg_parts.append(
                f'<line x1="{x}" y1="{MT}" x2="{x}" y2="{MT + chart_h}" '
                f'stroke="{line_color}" stroke-width="1"/>')
            if is_major:
                svg_parts.append(
                    f'<text x="{x}" y="{MT + chart_h + 18}" text-anchor="middle" '
                    f'font-family="Segoe UI" font-size="10" font-weight="600" '
                    f'fill="#606060">{w}w</text>')

        # Axis labels
        svg_parts.append(
            f'<text x="{ML - 54}" y="{MT + chart_h / 2}" '
            f'transform="rotate(-90, {ML - 54}, {MT + chart_h / 2})" '
            f'text-anchor="middle" font-family="Segoe UI" font-size="12" '
            f'font-weight="700" fill="#303030">Ölçüm (mm)</text>')
        svg_parts.append(
            f'<text x="{ML + chart_w / 2}" y="{H - 18}" text-anchor="middle" '
            f'font-family="Segoe UI" font-size="12" font-weight="700" '
            f'fill="#303030">Gebelik Haftası</text>')

        # Plot definitions
        measures = [
            ("BPD", 2, "#C42B1C"),  # red
            ("HC", 5, "#7A4DC5"),   # purple
            ("AC", 3, "#005A9E"),   # blue
            ("FL", 4, "#107C10"),   # green
        ]

        # ── Shaded Hadlock percentile bands ───────────────────────────────
        # For each measurement: render p3-p97 as very light tint, p10-p90
        # as darker tint, then p50 as solid line. Overlaps gracefully
        # because we use very low opacity.
        for name, _, color in measures:
            table = HADLOCK_TABLES.get(name)
            if table is None:
                continue
            min_week = max(min(table.keys()), int(min_ga // 7))
            max_week = min(max(table.keys()), int(max_ga // 7) + 1)
            if min_week >= max_week:
                continue
            # Collect p10 and p90 for inner band, p50 for median line
            p10_pts, p50_pts, p90_pts = [], [], []
            for wk in range(min_week, max_week + 1):
                row = table.get(wk)
                if row is None:
                    continue
                p10_pts.append((wk * 7, row[0]))
                p50_pts.append((wk * 7, row[1]))
                p90_pts.append((wk * 7, row[2]))
            # Build a closed polygon for the p10-p90 band
            if len(p10_pts) >= 2 and len(p90_pts) >= 2:
                up = [f"{x_for(ga)},{y_for(v)}" for ga, v in p90_pts]
                down = [f"{x_for(ga)},{y_for(v)}"
                        for ga, v in reversed(p10_pts)]
                band = " ".join(up + down)
                svg_parts.append(
                    f'<polygon points="{band}" fill="{color}" '
                    f'fill-opacity="0.07" stroke="none"/>')
            # p50 median line (dashed, thin)
            if len(p50_pts) >= 2:
                path_d = f"M {x_for(p50_pts[0][0])} {y_for(p50_pts[0][1])}"
                for ga, v in p50_pts[1:]:
                    path_d += f" L {x_for(ga)} {y_for(v)}"
                svg_parts.append(
                    f'<path d="{path_d}" fill="none" stroke="{color}" '
                    f'stroke-width="1.2" stroke-dasharray="3,4" '
                    f'opacity="0.55"/>')

        # ── Patient's lines + dots (drawn LAST so they're on top) ─────────
        for name, col_idx, color in measures:
            points = [(r[0], r[col_idx][0]) for r in rows
                      if r[col_idx] is not None and r[col_idx][0] is not None]
            if len(points) < 1:
                continue
            # Connect with a bold line
            if len(points) > 1:
                path_d = f"M {x_for(points[0][0])} {y_for(points[0][1])}"
                for ga, v in points[1:]:
                    path_d += f" L {x_for(ga)} {y_for(v)}"
                svg_parts.append(
                    f'<path d="{path_d}" fill="none" stroke="{color}" '
                    f'stroke-width="2.5" stroke-linecap="round" '
                    f'stroke-linejoin="round"/>')
            # Dots with white halo
            for ga, v in points:
                svg_parts.append(
                    f'<circle cx="{x_for(ga)}" cy="{y_for(v)}" r="6" '
                    f'fill="white" stroke="{color}" stroke-width="2.2"/>')
                svg_parts.append(
                    f'<circle cx="{x_for(ga)}" cy="{y_for(v)}" r="3" '
                    f'fill="{color}"/>')

        # ── Legend bar (bottom-right, clean) ───────────────────────────────
        lg_box_x = W - MR - 170
        lg_box_y = MT + 8
        svg_parts.append(
            f'<rect x="{lg_box_x}" y="{lg_box_y}" width="165" height="92" '
            f'fill="white" stroke="#D8D8D8" stroke-width="1" rx="4"/>')
        svg_parts.append(
            f'<text x="{lg_box_x + 8}" y="{lg_box_y + 18}" '
            f'font-family="Segoe UI" font-size="11" font-weight="700" '
            f'fill="#303030">Ölçümler</text>')
        for i, (name, _, color) in enumerate(measures):
            row_y = lg_box_y + 34 + i * 14
            svg_parts.append(
                f'<line x1="{lg_box_x + 10}" y1="{row_y}" '
                f'x2="{lg_box_x + 28}" y2="{row_y}" '
                f'stroke="{color}" stroke-width="2.5"/>')
            svg_parts.append(
                f'<circle cx="{lg_box_x + 19}" cy="{row_y}" r="3" '
                f'fill="{color}"/>')
            svg_parts.append(
                f'<text x="{lg_box_x + 36}" y="{row_y + 4}" '
                f'font-family="Segoe UI" font-size="11" fill="#303030">'
                f'{name}</text>')

        svg_parts.append('</svg>')
        svg_raw = "".join(svg_parts)

        # Qt's QTextDocument HTML renderer doesn't parse inline SVG as real
        # vector — it prints the characters out. Workaround: encode the SVG
        # as a data: URL and embed via <img>. Qt handles SVG images natively
        # provided the 'svg' image plugin is available (it is, with PySide6).
        import base64 as _b64
        svg_b64 = _b64.b64encode(svg_raw.encode("utf-8")).decode("ascii")
        svg = (f'<img src="data:image/svg+xml;base64,{svg_b64}" '
               f'width="{W}" height="{H}" '
               f'style="display:block;margin:6px auto;"/>')

        # Build the table of raw data with inter-visit analytics.
        # For each visit (after the first) we compute:
        # - Δ Takvim (calendar days elapsed since previous visit)
        # - Δ GA    (gestational-age days added since previous visit)
        # - Uyum    (concordance: calendar Δ vs GA Δ)
        tbl = ['<table cellpadding="4" cellspacing="0" '
               'style="border-collapse:collapse;font-family:Segoe UI;font-size:11px;margin-top:10px;">']
        tbl.append(
            '<tr style="background:#E5EEF7;">'
            '<th align="left" style="padding:6px;">Tarih</th>'
            '<th>Gebelik Haftası</th>'
            '<th>Δ Takvim</th>'
            '<th>Δ GA</th>'
            '<th>Uyum</th>'
            '<th>BPD (mm)</th><th>HC (mm)</th>'
            '<th>AC (mm)</th><th>FL (mm)</th>'
            '<th>EFW (g)</th><th>EFW Persentil</th></tr>')

        def _f(v):
            return f"{v:.1f}" if v is not None else "—"

        def _pct_html(lbl: str) -> str:
            """Colour-code percentile label — red for extremes, green
            for normal range."""
            if not lbl:
                return "—"
            if "<p10" in lbl or ">p90" in lbl:
                return f'<span style="color:#C42B1C;font-weight:700;">{lbl}</span>'
            # Get numeric percentile, flag moderate deviation
            m = re.search(r"p(\d+)", lbl)
            if m:
                p = int(m.group(1))
                if 25 <= p <= 75:
                    return f'<span style="color:#107C10;">{lbl}</span>'
                if 10 <= p <= 90:
                    return f'<span style="color:#C46500;">{lbl}</span>'
            return lbl

        prev = None  # (ga_days, vdate)
        for r in rows:
            ga_days_cur = r[0]
            ga_lbl = r[1]
            bpd_t, ac_t, fl_t, hc_t = r[2], r[3], r[4], r[5]
            # Each is (value_mm, ga_str) — unwrap for calculations
            bpd = bpd_t[0] if bpd_t else None
            ac = ac_t[0] if ac_t else None
            fl = fl_t[0] if fl_t else None
            hc = hc_t[0] if hc_t else None
            # GA labels per-measurement (e.g. "19w3d") so doctor sees what
            # gestational age each biometry implies
            bpd_ga = bpd_t[1] if bpd_t and bpd_t[1] else ""
            ac_ga = ac_t[1] if ac_t and ac_t[1] else ""
            fl_ga = fl_t[1] if fl_t and fl_t[1] else ""
            hc_ga = hc_t[1] if hc_t and hc_t[1] else ""
            date_str = r[6]
            vdate = r[7]

            # Calculated EFW + percentile (Hadlock-4 formula)
            efw = hadlock_efw(bpd, hc, ac, fl)
            efw_str = f"{int(round(efw))}" if efw else "—"
            ga_wk = ga_days_cur // 7
            efw_pct = _pct_html(percentile_label(efw, ga_wk, "EFW")) if efw else "—"

            # Per-measurement percentile labels + formatted cell ("45.0 mm (p50) · 19w3d")
            def _cell(val, ga_str, meas_key):
                if val is None:
                    return "—"
                pct = _pct_html(percentile_label(val, ga_wk, meas_key))
                base = f"<b>{val:.1f}</b>"
                parts = [base]
                if pct and pct != "—":
                    parts.append(f"<br><span style='font-size:10px;'>{pct}</span>")
                if ga_str:
                    parts.append(
                        f"<br><span style='color:#606060;font-size:10px;'>"
                        f"({ga_str})</span>")
                return "".join(parts)

            # Compute deltas vs previous visit
            delta_cal_str = "—"
            delta_ga_str = "—"
            uyum_html = "—"
            if prev is not None and vdate is not None and prev[1] is not None:
                cal_days = (vdate - prev[1]).days
                ga_days_delta = ga_days_cur - prev[0]
                if cal_days > 0:
                    delta_cal_str = f"{cal_days // 7}⁺{cal_days % 7} hf"
                    delta_ga_str = f"{ga_days_delta // 7}⁺{ga_days_delta % 7} hf"
                    diff_days = ga_days_delta - cal_days
                    if abs(diff_days) <= 3:
                        uyum_html = ('<span style="color:#107C10;font-weight:700;">'
                                     '✓ Uyumlu</span>')
                    elif diff_days > 3:
                        uyum_html = (f'<span style="color:#0078D4;font-weight:700;">'
                                     f'↑ {diff_days // 7}⁺{diff_days % 7} hf ileri</span>')
                    else:
                        lag = -diff_days
                        uyum_html = (f'<span style="color:#C42B1C;font-weight:700;">'
                                     f'↓ {lag // 7}⁺{lag % 7} hf geri</span>')

            tbl.append(
                f'<tr>'
                f'<td>{date_str}</td>'
                f'<td align="center"><b>{ga_lbl}</b></td>'
                f'<td align="center">{delta_cal_str}</td>'
                f'<td align="center">{delta_ga_str}</td>'
                f'<td align="center">{uyum_html}</td>'
                f'<td align="center">{_cell(bpd, bpd_ga, "BPD")}</td>'
                f'<td align="center">{_cell(hc, hc_ga, "HC")}</td>'
                f'<td align="center">{_cell(ac, ac_ga, "AC")}</td>'
                f'<td align="center">{_cell(fl, fl_ga, "FL")}</td>'
                f'<td align="center"><b>{efw_str}</b></td>'
                f'<td align="center">{efw_pct}</td>'
                f'</tr>')
            prev = (ga_days_cur, vdate)
        tbl.append('</table>')

        pname = format_patient_name(self.current_patient.name)

        # ── Growth Summary Panel ──────────────────────────────────────────
        # A clinical one-glance view: latest EFW percentile + trend vs the
        # previous measurement + color-coded status banner. Designed so
        # the doctor can assess growth status in under 2 seconds.
        last_row = rows[-1] if rows else None
        summary_html = ""
        if last_row:
            ga_days_last = last_row[0]
            # Find latest EFW from the table we built
            last_efw_txt = "—"
            last_efw_pct = "—"
            last_status_color = "#606060"
            last_status_bg = "#F0F0F0"
            last_status_label = "Veri yok"
            # Recompute summary metrics for the last visit
            try:
                pdf_last = get_latest_pdf_in_folder(visits[0])
                if pdf_last:
                    data_last = parse_pdf_summary_data(pdf_last)
                    efw_raw = data_last.get("EFW") if not data_last.get("is_twin") \
                        else data_last.get("fetüs_1", {}).get("EFW", "")
                    if isinstance(efw_raw, str):
                        m = re.search(r"(\d+)\s*g\s*±\s*(\d+)", efw_raw)
                        if m:
                            last_efw_txt = f"{int(m.group(1)):,} g (±{m.group(2)})"
                            efw_val = int(m.group(1))
                            # EFW percentile estimation via Hadlock-like lookup
                            pct_result = self._estimate_efw_percentile(
                                efw_val, ga_days_last // 7)
                            if pct_result:
                                last_efw_pct, pct_num = pct_result
                                if pct_num < 10:
                                    last_status_color = "#FFFFFF"
                                    last_status_bg = "#C42B1C"
                                    last_status_label = "⚠️ SGA (küçük)"
                                elif pct_num > 90:
                                    last_status_color = "#FFFFFF"
                                    last_status_bg = "#C46500"
                                    last_status_label = "⚠️ LGA (büyük)"
                                else:
                                    last_status_color = "#FFFFFF"
                                    last_status_bg = "#107C10"
                                    last_status_label = "✓ Normal (AGA)"
            except Exception as _ex:
                _log_warning("growth summary: efw percentile", exc=_ex)

            # Trend arrow vs previous visit
            trend_html = "—"
            if len(rows) >= 2:
                try:
                    prev_efw_txt = "—"
                    pdf_prev = get_latest_pdf_in_folder(visits[1])
                    if pdf_prev:
                        data_prev = parse_pdf_summary_data(pdf_prev)
                        efw_raw_p = data_prev.get("EFW") \
                            if not data_prev.get("is_twin") \
                            else data_prev.get("fetüs_1", {}).get("EFW", "")
                        if isinstance(efw_raw_p, str):
                            mp = re.search(r"(\d+)\s*g", efw_raw_p)
                            if mp and m:
                                delta = int(m.group(1)) - int(mp.group(1))
                                arrow = "↑" if delta > 0 else ("↓" if delta < 0 else "→")
                                color = "#107C10" if delta > 0 else \
                                    ("#C42B1C" if delta < 0 else "#606060")
                                trend_html = (
                                    f'<span style="color:{color};font-weight:700;'
                                    f'font-size:16px;">{arrow}</span> '
                                    f'<b>{delta:+,} g</b> '
                                    f'<span style="color:#808080;font-size:11px;">'
                                    f'(bir önceki gelişe göre)</span>')
                except Exception as _ex:
                    _log_warning("growth summary: trend", exc=_ex)

            ga_w = ga_days_last // 7
            ga_d = ga_days_last % 7
            summary_html = (
                f'<div style="display:block;background:#F8F8F8;'
                f'border:1px solid #D0D0D0;border-radius:6px;'
                f'padding:14px 18px;margin:10px 0;">'
                f'<table cellpadding="6" cellspacing="0" '
                f'style="border-collapse:collapse;width:100%;">'
                f'<tr>'
                f'<td style="vertical-align:top;">'
                f'<div style="font-size:10px;color:#808080;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:0.5px;">'
                f'Son Geliş</div>'
                f'<div style="font-size:18px;font-weight:800;color:#003A66;'
                f'margin-top:2px;">{ga_w}⁺{ga_d} hafta</div>'
                f'</td>'
                f'<td style="vertical-align:top;">'
                f'<div style="font-size:10px;color:#808080;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:0.5px;">'
                f'Tahmini Ağırlık</div>'
                f'<div style="font-size:18px;font-weight:800;color:#003A66;'
                f'margin-top:2px;">{last_efw_txt}</div>'
                f'<div style="font-size:11px;color:#606060;margin-top:2px;">'
                f'Persentil: <b>{last_efw_pct}</b></div>'
                f'</td>'
                f'<td style="vertical-align:top;">'
                f'<div style="font-size:10px;color:#808080;font-weight:600;'
                f'text-transform:uppercase;letter-spacing:0.5px;">'
                f'Büyüme Trendi</div>'
                f'<div style="font-size:13px;margin-top:6px;">{trend_html}</div>'
                f'</td>'
                f'<td style="vertical-align:middle;text-align:right;">'
                f'<div style="display:inline-block;background:{last_status_bg};'
                f'color:{last_status_color};padding:10px 18px;'
                f'border-radius:22px;font-weight:700;font-size:13px;">'
                f'{last_status_label}</div>'
                f'</td>'
                f'</tr></table>'
                f'</div>')

        full_html = (
            f'<h3 style="margin:0;color:#005A9E;font-size:18px;">'
            f'📈 Büyüme Eğrileri — {pname}</h3>'
            f'<p style="color:#606060;margin:4px 0 10px 0;font-size:11px;">'
            f'Toplam {len(rows)} geliş, {len(rows)} ölçüm seti</p>'
            f'{summary_html}'
            f'{svg}'
            f'{"".join(tbl)}'
            f'<p style="color:#606060;font-size:10px;margin-top:10px;'
            f'font-style:italic;">'
            f'İkiz gebelikte sadece Fetus A gösterilir. '
            f'<br><b>Uyum</b> kolonu: gelişler arası takvim günleri ile gebelik '
            f'haftası artışını karşılaştırır. "✓ Uyumlu" ±3 gün içinde; '
            f'"↑ X hf ileri" GA olması gerektiğinden fazla ilerlemiş; '
            f'"↓ X hf geri" GA arkasında kalmış (IUGR riski).</p>'
        )

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle(f"Büyüme Eğrileri — {pname}")
        dlg.resize(1040, 760)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(12, 12, 12, 12)
        txt = QTextEdit()
        txt.setReadOnly(True)
        # Force white background so dark theme doesn't corrupt the chart
        txt.setStyleSheet(
            "QTextEdit{background:#FFFFFF;color:#202020;"
            "border:1px solid #C8C8C8;}")
        txt.setHtml(full_html)
        v.addWidget(txt, 1)
        btn = QPushButton("Kapat")
        btn.setShortcut("Escape")
        btn.clicked.connect(dlg.accept)
        v.addWidget(btn)
        dlg.exec()

    def _estimate_efw_percentile(
            self, efw_g: int, ga_week: int) -> Optional[Tuple[str, int]]:
        """Rough percentile estimation for Estimated Fetal Weight.

        Uses a simplified Hadlock-based table (p10/p50/p90 for each week
        28-40). Returns (label like 'p35', numeric p) or None if out of
        range. Used by the growth dashboard summary panel — not for
        clinical decision-making (Voluson's own percentile is canonical).
        """
        # Hadlock 1991 EFW percentiles (rough, interpolated)
        EFW_PCT = {
            20: (320, 350, 390),
            22: (440, 500, 570),
            24: (590, 670, 770),
            26: (770, 900, 1040),
            28: (980, 1150, 1350),
            30: (1230, 1460, 1720),
            32: (1530, 1840, 2180),
            34: (1880, 2260, 2690),
            36: (2250, 2710, 3250),
            38: (2620, 3160, 3790),
            40: (2900, 3480, 4160),
        }
        if ga_week not in EFW_PCT:
            # Find closest week with data
            keys = sorted(EFW_PCT.keys())
            if ga_week < keys[0]:
                ga_week = keys[0]
            elif ga_week > keys[-1]:
                ga_week = keys[-1]
            else:
                # Snap to nearest
                ga_week = min(keys, key=lambda k: abs(k - ga_week))
        p10, p50, p90 = EFW_PCT[ga_week]
        # Linear interpolation between anchors
        if efw_g <= p10:
            if efw_g <= p10 * 0.85:
                return ("<p3", 2)
            pct = int(10 * efw_g / p10)
            return (f"p{max(1, pct)}", max(1, pct))
        if efw_g <= p50:
            pct = 10 + int(40 * (efw_g - p10) / (p50 - p10))
            return (f"p{pct}", pct)
        if efw_g <= p90:
            pct = 50 + int(40 * (efw_g - p50) / (p90 - p50))
            return (f"p{pct}", pct)
        if efw_g <= p90 * 1.15:
            pct = 90 + int(7 * (efw_g - p90) / (p90 * 0.15))
            return (f"p{min(97, pct)}", min(97, pct))
        return (">p97", 98)

    # ═══════════════════════════════════════════════════════════════
    # YENİ MENÜ AKSİYONLARI — Web ile eşleme
    # ═══════════════════════════════════════════════════════════════

    def _filter_by_type(self, ptype: str):
        """Hasta tipine göre filtrele."""
        try:
            self._current_type_filter = ptype
            if hasattr(self, "_refresh_patient_list"):
                self._refresh_patient_list()
            elif hasattr(self, "load_patients"):
                self.load_patients()
            else:
                # Fallback: bilgi mesajı
                QMessageBox.information(
                    self, "Filtre",
                    f"Tip filtresi: {ptype}\n"
                    "(Hasta listesi manuel yenilensin)")
        except Exception as ex:
            QMessageBox.warning(
                self, "Filtre", str(ex))

    def _show_riskli_gebelik(self):
        """Riskli Gebelik paneli — preeklampsi, GDM, IUGR, vs."""
        from PySide6.QtWidgets import (
            QDialog, QVBoxLayout, QListWidget,
            QListWidgetItem, QPushButton, QHBoxLayout)
        try:
            dlg = QDialog(self)
            dlg.setWindowTitle("⚠️ Riskli Gebelik Paneli")
            dlg.resize(700, 500)
            v = QVBoxLayout(dlg)

            header = QLabel(
                "<h3 style='color:#A03A2A;'>⚠️ Riskli Gebeler</h3>"
                "<p>Preeklampsi · GDM · IUGR · Anomali · "
                "Çoğul · İleri yaş · KOAH · Hipertansiyon</p>")
            header.setTextFormat(Qt.RichText)
            v.addWidget(header)

            lst = QListWidget()
            lst.setStyleSheet(
                "QListWidget::item { padding: 8px; }")

            # Tüm hastalardan riskli olanları topla
            riskli_count = 0
            try:
                if hasattr(self, "patients") and self.patients:
                    for p in self.patients:
                        flags = getattr(p, "flags", {}) or {}
                        risk_flags = []
                        for fname in ["preeklampsi", "gdm",
                                       "iugr", "anomali",
                                       "cogul", "ileri_yas",
                                       "hipertansiyon",
                                       "diyabet", "tiroid"]:
                            if flags.get(fname, {}).get(
                                    "value") == "1":
                                risk_flags.append(fname)
                        if risk_flags:
                            riskli_count += 1
                            display = getattr(
                                p, "display_name",
                                getattr(p, "name", "?"))
                            item = QListWidgetItem(
                                f"⚠ {display}\n   "
                                f"Riskler: {', '.join(risk_flags)}")
                            item.setData(
                                Qt.UserRole,
                                getattr(p, "name", ""))
                            lst.addItem(item)
            except Exception as ex:
                lst.addItem(f"Hata: {ex}")

            if riskli_count == 0:
                lst.addItem("(riskli gebe yok)")

            def open_selected():
                cur = lst.currentItem()
                if cur:
                    pkey = cur.data(Qt.UserRole)
                    if pkey and hasattr(self,
                                          "_open_patient_by_name"):
                        self._open_patient_by_name(pkey)
                        dlg.accept()

            lst.itemDoubleClicked.connect(
                lambda i: open_selected())
            v.addWidget(lst, 1)

            footer = QLabel(
                f"<small>Toplam: {riskli_count} riskli gebe — "
                f"hastayı çift tıklayarak açın</small>")
            footer.setTextFormat(Qt.RichText)
            v.addWidget(footer)

            btn_row = QHBoxLayout()
            close_btn = QPushButton("Kapat")
            close_btn.clicked.connect(dlg.accept)
            btn_row.addStretch()
            btn_row.addWidget(close_btn)
            v.addLayout(btn_row)

            dlg.exec()
        except Exception as ex:
            QMessageBox.warning(
                self, "Riskli Gebelik", str(ex))

    def _show_recent_patients(self):
        """Son gelen hastaları göster."""
        try:
            from PySide6.QtWidgets import (
                QDialog, QVBoxLayout, QListWidget,
                QListWidgetItem)
            dlg = QDialog(self)
            dlg.setWindowTitle("⏱ Son Gelen Hastalar")
            dlg.resize(600, 500)
            v = QVBoxLayout(dlg)

            v.addWidget(QLabel(
                "<h3>⏱ Son Gelen Hastalar</h3>"))

            lst = QListWidget()
            try:
                if hasattr(self, "patients") and self.patients:
                    sorted_pts = sorted(
                        self.patients,
                        key=lambda p: getattr(
                            p, "last_visit", "0000"),
                        reverse=True)[:50]
                    for p in sorted_pts:
                        display = getattr(
                            p, "display_name",
                            getattr(p, "name", "?"))
                        last = getattr(p, "last_visit",
                                        "(ziyaret yok)")
                        item = QListWidgetItem(
                            f"{display}\n   Son: {last}")
                        item.setData(
                            Qt.UserRole,
                            getattr(p, "name", ""))
                        lst.addItem(item)
            except Exception as ex:
                lst.addItem(f"Hata: {ex}")

            def open_selected():
                cur = lst.currentItem()
                if cur:
                    pkey = cur.data(Qt.UserRole)
                    if pkey and hasattr(
                            self, "_open_patient_by_name"):
                        self._open_patient_by_name(pkey)
                        dlg.accept()

            lst.itemDoubleClicked.connect(
                lambda i: open_selected())
            v.addWidget(lst, 1)
            dlg.exec()
        except Exception as ex:
            QMessageBox.warning(
                self, "Son Hastalar", str(ex))

    def _open_ai_assistant(self):
        """YZ asistanını aç — YENİ: standalone dialog (web'siz)."""
        # Önce yeni dialog'u dene (Ollama direkt)
        try:
            import yazklinik_v68_dialogs
            patient = getattr(
                self, "current_patient", None)
            patient_ctx = None
            if patient:
                patient_ctx = {
                    "name": str(getattr(
                        patient, "name", patient)),
                    "path": str(patient),
                }
            yazklinik_v68_dialogs.show_ai_assistant(
                self, patient_ctx)
            return
        except ImportError:
            pass
        except Exception as ex:
            QMessageBox.warning(
                self, "YZ Asistan",
                f"Standalone dialog hatası: {ex}\n"
                f"Eski moda geçiliyor...")

        # Fallback: eski yazklinik_v68_ai modülü
        try:
            import yazklinik_v68_ai
            patient = getattr(self, "current_patient", None)
            yazklinik_v68_ai.open_ai_assistant(self, patient)
        except Exception as ex:
            QMessageBox.warning(
                self, "YZ Asistan",
                f"YZ asistan açılamadı: {ex}\n\n"
                "yazklinik_v68_dialogs.py veya "
                "yazklinik_v68_ai.py dosyasının aynı "
                "klasörde olduğundan emin olun.")

    def _open_ai_with_action(self, action_key: str):
        """YZ asistanını belirli bir aksiyon seçili açar."""
        try:
            import yazklinik_v68_ai
            patient = getattr(self, "current_patient", None)
            win = yazklinik_v68_ai.open_ai_assistant(
                self, patient)
            # Aksiyonu seç
            if win and hasattr(win, "action_list"):
                for i, action in enumerate(
                        yazklinik_v68_ai.AI_ACTIONS):
                    if action["key"] == action_key:
                        win.action_list.setCurrentRow(i)
                        break
        except Exception as ex:
            QMessageBox.warning(
                self, "YZ Aksiyon", str(ex))

    def _open_url(self, path: str):
        """Web tarayıcıda URL aç."""
        try:
            import webbrowser
            try:
                from PySide6.QtCore import QSettings
                qs = QSettings("YazKlinik", "YazKlinikV68")
                base = qs.value(
                    "ai_server_url",
                    "http://localhost:5000",
                    type=str) or "http://localhost:5000"
            except Exception:
                base = "http://localhost:5000"
            url = f"{base.rstrip('/')}{path}"
            webbrowser.open(url)
        except Exception as ex:
            QMessageBox.warning(
                self, "URL", f"Açılamadı: {ex}")

    def _show_stats_infertility(self):
        """Infertility / gynecologic stats panel.

        Counts only patients classified as gynecologic (no Obstetrics
        Report in their PDFs). Same format as the main overview but
        with pink theme + clickable drill-down to the patient list.
        """
        if not db_has_any_patients():
            reply = QMessageBox.question(
                self, "İnfertilite İstatistikleri",
                "<h3 style='color:#C46500'>📊 İstatistikler henüz hazır değil</h3>"
                "<p>İnfertilite hastalarını görebilmek için önce NAS "
                "klasörü senkronize edilmelidir.</p>"
                "<p>Şimdi senkronize edilsin mi?</p>",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self._run_nas_sync()
            return

        # Walk all patients, filter gyn
        all_patients = list(getattr(self, "patient_paths", []) or [])

        gyn_patients = []
        for p in all_patients:
            try:
                if is_gynecologic_patient(p):
                    gyn_patients.append(p)
            except Exception:
                continue

        total_gyn = len(gyn_patients)

        # Dates
        from datetime import date as _date
        today = _date.today()
        thirty_ago = today - timedelta(days=30)
        year_ago = today - timedelta(days=365)

        gyn_30 = 0
        gyn_365 = 0
        for p in gyn_patients:
            last_d = get_patient_last_visit_date(p)
            if last_d is None:
                continue
            if last_d.date() >= thirty_ago:
                gyn_30 += 1
            if last_d.date() >= year_ago:
                gyn_365 += 1

        # Build dialog
        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("🌸 İnfertilite / Jinekolojik İstatistikler")
        dlg.resize(560, 520)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)

        # v68: Hero header — pink 3-stop gradient
        title = QLabel(
            "<div style='padding:14px 18px;'>"
            "<div style='font-size:18px;font-weight:800;color:#FFFFFF;'>"
            "🌸  İnfertilite / Jinekolojik</div>"
            "<div style='color:rgba(255,255,255,0.85);margin-top:4px;"
            "font-size:11.5px;'>"
            "PDF'lerinde 'Obstetrics Report' bulunmayan hastalar"
            "</div></div>")
        title.setTextFormat(Qt.RichText)
        title.setStyleSheet(
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
            title.setGraphicsEffect(shf)
        except Exception as _ex:
            _log_warning("gyn stats hero shadow", exc=_ex)
        v.addWidget(title)

        def _section_header(text):
            h = QLabel(f"<b>{text}</b>")
            h.setStyleSheet(
                "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                "stop:0 #FCF0F8, stop:1 #F8E5F2);"
                "color:#6F2256;padding:8px 12px;"
                "border-left:4px solid #B5368A;"
                "border-radius:6px;font:700 12.5px 'Segoe UI';"
                "margin-top:6px;")
            return h

        def _row(icon_text, value):
            l = QLabel(
                f"<span style='color:#404040;'>{icon_text}</span> "
                f"&nbsp; <b style='color:#1a1a1a;font-size:13px;'>{value}</b>")
            l.setStyleSheet("padding:6px 10px;background:transparent;")
            return l

        def _clickable(icon_text, value, callback):
            btn = QPushButton(f"   {icon_text}   →   {value}   ")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton{text-align:left;padding:6px 10px;"
                "background:#FCF5F9;border:1px solid #E8B8D0;"
                "border-radius:3px;color:#6F2256;"
                "font:500 12px 'Segoe UI';}"
                "QPushButton:hover{background:#FFE5F2;"
                "border-color:#B5368A;}")
            btn.clicked.connect(callback)
            return btn

        v.addWidget(_section_header("📊 Toplam"))
        v.addWidget(_clickable(
            "♀️ Tüm Jinekolojik Hastalar",
            f"{total_gyn:,} hasta",
            lambda: (dlg.accept(),
                     self._show_filter_dialog("gynecologic"))))

        v.addWidget(_section_header("📅 Son 30 Gün"))
        v.addWidget(_row("♀️ Gelen jinekolojik hasta",
                         f"{gyn_30:,} hasta"))

        v.addWidget(_section_header("📆 Son 1 Yıl"))
        v.addWidget(_row("♀️ Gelen jinekolojik hasta",
                         f"{gyn_365:,} hasta"))

        v.addWidget(_section_header("🧪 Tedavi Notları"))
        hint = QLabel(
            "İnfertilite tedavi takibi ayrı bir modülde geliştirilecek. "
            "Şu an için hastaların test listeleri <b>🧪 Test Listesi</b> "
            "butonundan açılıyor (hasta seçiliyken)."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet(
            "color:#606060;font:400 11px 'Segoe UI';"
            "padding:8px 10px;background:#F8F8F8;"
            "border:1px solid #E0E0E0;border-radius:3px;")
        v.addWidget(hint)

        v.addStretch()
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn = QPushButton("Kapat")
        btn.setMinimumWidth(90)
        btn.clicked.connect(dlg.accept)
        btn_row.addWidget(btn)
        v.addLayout(btn_row)
        dlg.exec()

    def _show_stats_overview(self):
        """Show a high-level dashboard of key clinic numbers, with
        clickable sections that pop up the matching patient list.

        v68: Sections "Son 30 Gün", "Son 1 Yıl", "Klinik Durum" are
        now clickable buttons — tapping them shows the actual patients
        behind the number (names + last visit date), not just totals.
        The doctor asked for this so the stats panel becomes an
        entry point into the patient list, not a dead-end text summary.
        """
        if not db_has_any_patients():
            reply = QMessageBox.question(
                self, "İstatistik",
                "<h3 style='color:#C46500'>📊 İstatistikler henüz hazır değil</h3>"
                "<p>İstatistik ve grafiklerin çalışabilmesi için önce "
                "NAS klasörü senkronize edilmelidir.</p>"
                "<p><b>Şimdi senkronize edilsin mi?</b><br>"
                "<i>(5000+ hasta için birkaç dakika sürebilir)</i></p>",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self._run_nas_sync()
            return

        with db_conn() as con:
            total_patients = con.execute(
                "SELECT COUNT(*) FROM patients").fetchone()[0]
            total_visits = con.execute(
                "SELECT COUNT(*) FROM visits").fetchone()[0]
            total_files = con.execute(
                "SELECT COUNT(*) FROM files").fetchone()[0]
            total_images = con.execute(
                "SELECT COUNT(*) FROM files WHERE file_kind='image'").fetchone()[0]
            total_videos = con.execute(
                "SELECT COUNT(*) FROM files WHERE file_kind='video'").fetchone()[0]
            total_pdfs = con.execute(
                "SELECT COUNT(*) FROM files WHERE file_kind='pdf'").fetchone()[0]
            twin_pregnancies = con.execute(
                "SELECT COUNT(*) FROM parsed_summaries WHERE is_twin=1").fetchone()[0]
            active_flags = con.execute(
                "SELECT COUNT(DISTINCT patient_key) FROM patient_flags "
                "WHERE value='1'").fetchone()[0]
            # v68: Manual / gynecologic patient counts (new in v68 —
            # tracked via patient_type table which is_manual=1 means
            # the patient was registered through the New Patient dialog,
            # not from a NAS PDF scan).
            try:
                manual_patients = con.execute(
                    "SELECT COUNT(*) FROM patient_type "
                    "WHERE is_manual=1").fetchone()[0]
            except Exception:
                manual_patients = 0
            try:
                gynec_patients = con.execute(
                    "SELECT COUNT(*) FROM patient_type "
                    "WHERE ptype='gynecologic'").fetchone()[0]
            except Exception:
                gynec_patients = 0
            try:
                obs_patients_manual = con.execute(
                    "SELECT COUNT(*) FROM patient_type "
                    "WHERE ptype='obstetric' AND is_manual=1").fetchone()[0]
            except Exception:
                obs_patients_manual = 0
            # Visits in last 30 / 365 days
            from datetime import date as _date
            today = _date.today().isoformat()
            thirty_ago = (_date.today() - timedelta(days=30)).isoformat()
            year_ago = (_date.today() - timedelta(days=365)).isoformat()
            recent_visits = con.execute(
                "SELECT COUNT(*) FROM visits WHERE visit_date>=? AND visit_date<=?",
                (thirty_ago, today)).fetchone()[0]
            recent_patients = con.execute(
                "SELECT COUNT(DISTINCT patient_folder_key) FROM visits "
                "WHERE visit_date>=? AND visit_date<=?",
                (thirty_ago, today)).fetchone()[0]
            year_patients = con.execute(
                "SELECT COUNT(DISTINCT patient_folder_key) FROM visits "
                "WHERE visit_date>=? AND visit_date<=?",
                (year_ago, today)).fetchone()[0]

        avg_visits = (total_visits / total_patients) if total_patients else 0

        # Build dialog with a mix of text rows and clickable buttons
        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("İstatistikler — Genel Bakış")
        dlg.resize(560, 680)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(8)

        # v68: Hero header with gradient
        hero = QLabel(
            f"<div style='padding:14px 18px;'>"
            f"<div style='font-size:18px;font-weight:800;color:#FFFFFF;'>"
            f"📊  Klinik İstatistikleri</div>"
            f"<div style='color:rgba(255,255,255,0.85);margin-top:4px;"
            f"font-size:11.5px;'>"
            f"Tüm hastalar, gelişler, dosyalar ve klinik bayraklar"
            f"</div></div>")
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
            _log_warning("stats hero shadow", exc=_ex)
        v.addWidget(hero)

        def _section_header(text: str) -> QLabel:
            h = QLabel(f"<b>{text}</b>")
            h.setStyleSheet(
                "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                "stop:0 #E5F1FB, stop:1 #CCE4F7);"
                "color:#003A66;"
                "padding:8px 12px;border-radius:6px;"
                "border-left:4px solid #0078D4;"
                "font:700 12.5px 'Segoe UI';"
                "margin-top:6px;")
            return h

        def _row(icon_text: str, value: str) -> QLabel:
            l = QLabel(
                f"<span style='color:#404040;'>{icon_text}</span> "
                f"&nbsp; <b style='color:#1a1a1a;font-size:13px;'>{value}</b>")
            l.setStyleSheet("padding:6px 10px;background:transparent;")
            return l

        def _clickable_row(icon_text: str, value: str,
                           callback) -> QPushButton:
            btn = QPushButton()
            btn.setText(
                f"   {icon_text}   →   {value}   (tıklayın, liste açılır)   ")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setStyleSheet(
                "QPushButton{text-align:left;padding:8px 12px;"
                "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                "stop:0 #FFFFFF,stop:1 #F0F6FC);"
                "border:1.5px solid #B8D4E8;"
                "border-radius:6px;color:#003A66;"
                "font:600 12px 'Segoe UI';}"
                "QPushButton:hover{"
                "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                "stop:0 #E5F1FB,stop:1 #CCE4F7);"
                "border-color:#0078D4;color:#003F6F;}")
            btn.clicked.connect(callback)
            return btn

        # Toplam
        v.addWidget(_section_header("📊 Toplam"))
        v.addWidget(_row("👤 Hasta sayısı:", f"{total_patients:,}"))
        v.addWidget(_row("🏥 Toplam geliş:", f"{total_visits:,}"))
        v.addWidget(_row("📁 Toplam dosya:", f"{total_files:,}"))
        v.addWidget(_row("📈 Ortalama geliş / hasta:",
                         f"{avg_visits:.1f}"))

        # Dosya
        v.addWidget(_section_header("📁 Dosya Türleri"))
        v.addWidget(_row("🖼️ Resim:", f"{total_images:,}"))
        v.addWidget(_row("🎥 Video:", f"{total_videos:,}"))
        v.addWidget(_row("📄 PDF:", f"{total_pdfs:,}"))

        # Son 30 Gün + Son 1 Yıl — clickable
        v.addWidget(_section_header("📅 Son 30 Gün"))
        v.addWidget(_row("🏥 Geliş sayısı:", f"{recent_visits:,}"))
        v.addWidget(_clickable_row(
            f"👤 Son 30 günde gelen farklı hasta",
            f"{recent_patients:,} hasta",
            lambda: (dlg.accept(),
                     self._show_filter_dialog("active_60"))))

        v.addWidget(_section_header("📆 Son 1 Yıl"))
        v.addWidget(_clickable_row(
            f"👤 Son 365 günde gelen farklı hasta",
            f"{year_patients:,} hasta",
            lambda: (dlg.accept(),
                     self._show_stats_year_patients())))

        # Klinik Durum — clickable
        v.addWidget(_section_header("🏥 Klinik Durum"))
        v.addWidget(_clickable_row(
            f"💚 Aktif takipteki hastalar (≤60 gün)",
            "Tüm liste",
            lambda: (dlg.accept(),
                     self._show_filter_dialog("active_60"))))
        v.addWidget(_clickable_row(
            f"🏷️ Bayraklı hastalar",
            f"{active_flags:,} hasta",
            lambda: (dlg.accept(),
                     self._show_filter_dialog("flagged"))))
        v.addWidget(_row("👶 İkiz gebelik sayısı:",
                         f"{twin_pregnancies}"))

        # v68: Manual / gynecologic registry stats
        v.addWidget(_row("🆕 Manuel kayıtlı hastalar:",
                         f"{manual_patients:,} hasta"))
        v.addWidget(_row("🌸 Jinekolojik / İnfertilite hastalar:",
                         f"{gynec_patients:,} hasta"))
        if obs_patients_manual:
            v.addWidget(_row("🤰 Manuel obstetrik kayıt:",
                             f"{obs_patients_manual:,} hasta"))

        v.addStretch()
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn = QPushButton("Kapat")
        btn.setMinimumWidth(90)
        btn.clicked.connect(dlg.accept)
        btn_row.addWidget(btn)
        v.addLayout(btn_row)
        dlg.exec()

    def _show_stats_year_patients(self):
        """Pop up the list of patients seen in the last 365 days.
        Uses the same dialog the other filter views use for consistency
        — click a name to jump to that patient in the main list.
        """
        # Reuse the filter dialog machinery but with a 365-day window.
        # We temporarily swap the threshold by calling with a special kind.
        self._show_filter_dialog("active_365")

    def _show_stats_monthly(self):
        """Monthly breakdown of visit counts as a text table."""
        if not db_has_any_patients():
            reply = QMessageBox.question(
                self, "Aylık İstatistik",
                "<b>Aylık hasta sayıları için önce NAS senkronize edilmeli.</b>"
                "<p>Şimdi başlatılsın mı?</p>",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self._run_nas_sync()
            return
        with db_conn() as con:
            # Group visits by year-month
            rows = con.execute(
                "SELECT substr(visit_date, 1, 7) AS ym, COUNT(*) AS cnt, "
                "COUNT(DISTINCT patient_folder_key) AS patients "
                "FROM visits WHERE visit_date IS NOT NULL AND visit_date!='' "
                "GROUP BY ym ORDER BY ym DESC LIMIT 36"
            ).fetchall()

        if not rows:
            QMessageBox.information(
                self, "Aylık İstatistik",
                "Hiç geliş tarihi bulunamadı. Geliş klasörlerinizin "
                "YYYY-MM-DD formatında olduğundan emin olun.")
            return

        # Find max for bar scaling
        max_cnt = max(r[1] for r in rows)

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("Aylık Hasta Gelişleri")
        dlg.resize(640, 600)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(12, 12, 12, 12)
        hdr = QLabel(f"<h3>📅 Son {len(rows)} ay</h3>")
        v.addWidget(hdr)

        # Build a simple HTML "bar chart" using nbsp-filled spans
        parts = ["<table cellpadding='4' cellspacing='0' style='border-collapse:collapse;font:12px Segoe UI;'>"]
        parts.append(
            "<tr style='background:#E5EEF7;'>"
            "<th align='left'>Ay</th><th align='left'>Geliş</th>"
            "<th align='left'>Hasta</th><th align='left'>Grafik</th></tr>")
        for ym, cnt, patients in rows:
            width_pct = int(cnt / max_cnt * 100) if max_cnt else 0
            bar = (f"<div style='background:#0078D4;height:14px;"
                   f"width:{max(width_pct, 1)}%;'></div>")
            parts.append(
                f"<tr><td><b>{ym}</b></td><td>{cnt}</td><td>{patients}</td>"
                f"<td style='min-width:250px;'>{bar}</td></tr>")
        parts.append("</table>")
        html = "".join(parts)

        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setHtml(html)
        v.addWidget(txt, 1)

        btn = QPushButton("Kapat")
        btn.clicked.connect(dlg.accept)
        v.addWidget(btn)
        dlg.exec()

    def _refresh_stats(self):
        """Kept for backward-compat. Delegates to _refresh_quick_panels."""
        self._refresh_quick_panels()
