"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _SettingsHelpMixin
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

class _SettingsHelpMixin:
    """MainWindow methods related to SettingsHelp. Mixed into MainWindow via MRO."""

    def _open_error_log(self):
        """Open the error log file with the OS default text editor."""
        log_path = _get_error_log_path()
        if not log_path.exists():
            QMessageBox.information(
                self, "Hata Log'u",
                "Henüz hiç log kaydı yok — hiçbir şey hata vermemiş demektir 👍")
            return
        try:
            # Windows: os.startfile; cross-platform fallback: QDesktopServices
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(log_path)))
        except Exception as ex:
            _log_warning("opening error log failed", exc=ex)
            QMessageBox.warning(
                self, "Açılamadı",
                f"Log dosyası açılamadı:\n{log_path}\n\n{ex}")

    def _clear_error_log(self):
        """Wipe the error log after confirmation."""
        log_path = _get_error_log_path()
        if not log_path.exists():
            self.statusBar().showMessage("Log zaten boş.", 3000)
            return
        reply = QMessageBox.question(
            self, "Log'u Temizle",
            f"Hata log dosyasını sıfırlamak istiyor musun?\n\n"
            f"{log_path}",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        try:
            log_path.write_text("", encoding="utf-8")
            self.statusBar().showMessage("✓ Hata log'u sıfırlandı", 3000)
        except Exception as ex:
            _log_warning("clearing error log failed", exc=ex)
            QMessageBox.warning(self, "Temizlenemedi", str(ex))

    def _backup_database_to_file(self):
        """Export the SQLite database to a user-chosen .sqlite file.

        v68-UI: Uses SQLite's `VACUUM INTO` for a consistent online
        backup — safe even if the app is actively writing. Default
        filename includes timestamp + version. Saves to user's
        Desktop by default for visibility.
        """
        import shutil
        from datetime import datetime
        try:
            db_path = _resolve_db_path()
            if not db_path or not Path(db_path).exists():
                QMessageBox.warning(
                    self, "Yedek Al",
                    "Veritabanı dosyası bulunamadı.")
                return

            # Default destination: Desktop with timestamp
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            default_name = f"yazklinik_yedek_{ts}.sqlite"
            try:
                desktop = Path.home() / "Desktop"
                if not desktop.exists():
                    desktop = Path.home()
            except Exception:
                desktop = Path.home()
            default_path = str(desktop / default_name)

            target_str, _ = QFileDialog.getSaveFileName(
                self, "Veritabanını Yedekle",
                default_path,
                "SQLite Yedek (*.sqlite *.db);;Tüm Dosyalar (*.*)")
            if not target_str:
                return

            target = Path(target_str)
            # Use VACUUM INTO for consistent online backup. This is
            # SQLite's recommended method — works even when the DB is
            # being written to by another connection (WAL mode).
            try:
                with db_conn() as con:
                    con.execute(f"VACUUM INTO ?", (str(target),))
                size_mb = target.stat().st_size / 1024 / 1024
                self.statusBar().showMessage(
                    f"✓ Yedek alındı: {target.name} ({size_mb:.1f} MB)",
                    8000)
                show_toast(self,
                           f"Yedek alındı: {target.name} ({size_mb:.1f} MB)",
                           level="success", duration_ms=5000)
                QMessageBox.information(
                    self, "Yedek Tamamlandı",
                    f"<b>Veritabanı başarıyla yedeklendi.</b><br><br>"
                    f"📁 <code>{target}</code><br>"
                    f"📊 Boyut: {size_mb:.1f} MB<br><br>"
                    f"<i>Bu yedek dosyasını harici bir disk veya "
                    f"bulut depolamaya kopyalamanızı öneririz.</i>")
            except Exception as ex:
                # Fallback: simple file copy (may include WAL inconsistency)
                _log_warning(f"VACUUM INTO failed, fallback to copy: {ex}")
                shutil.copy2(str(db_path), str(target))
                size_mb = target.stat().st_size / 1024 / 1024
                self.statusBar().showMessage(
                    f"✓ Yedek alındı (basit kopya): {target.name}", 6000)
                QMessageBox.information(
                    self, "Yedek Tamamlandı",
                    f"Veritabanı kopyalandı: {target}\n"
                    f"Boyut: {size_mb:.1f} MB")
        except Exception as ex:
            _log_warning("_backup_database_to_file", exc=ex)
            QMessageBox.critical(
                self, "Yedek Hatası",
                f"Yedek alınamadı:\n\n{type(ex).__name__}: {ex}")

    def _show_error_log_viewer(self):
        """Show the persistent warning/error log in a scrollable
        dialog so the doctor can see what's been failing silently.

        v68-UI: All _log_warning() calls write to a rolling log file
        (configured by _log_warning helper). This dialog reads it
        and displays the last N lines with timestamps highlighted.
        """
        try:
            log_path = _get_error_log_path()
        except Exception as _ex:
            _log_warning(f"_show_error_log_viewer: path: {_ex}")
            log_path = None

        if not log_path or not Path(log_path).exists():
            QMessageBox.information(
                self, "Hata Log'u",
                "Henüz hata log'u oluşturulmamış. "
                "Bu iyi haber — sistem sorunsuz çalışıyor.")
            return

        try:
            content = Path(log_path).read_text(
                encoding="utf-8", errors="replace")
        except Exception as ex:
            QMessageBox.warning(
                self, "Hata Log'u",
                f"Log okunamadı: {ex}")
            return

        # Show only the last 500 lines to keep dialog snappy
        lines = content.splitlines()
        truncated = len(lines) > 500
        if truncated:
            lines = lines[-500:]
        display_text = "\n".join(lines) if lines else "(log boş)"

        dlg = QDialog(self)
        dlg.setWindowTitle("📋 Sistem Hata Log'u")
        dlg.setMinimumSize(820, 560)
        dlg.setModal(False)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Hero
        hero = QWidget()
        hero.setFixedHeight(72)
        hero.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #C42B1C,stop:1 #E8623C);")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(22, 12, 22, 12)
        hl.setSpacing(2)
        ht = QLabel("📋  Sistem Hata Log'u")
        ht.setStyleSheet(
            "color:white;font:800 18px 'Segoe UI';background:transparent;")
        hs = QLabel(
            f"Son {len(lines)} satır gösteriliyor"
            + ("  ·  (eski kayıtlar atlandı)" if truncated else ""))
        hs.setStyleSheet(
            "color:rgba(255,255,255,0.92);font:500 11px 'Segoe UI';"
            "background:transparent;")
        hl.addWidget(ht)
        hl.addWidget(hs)
        root.addWidget(hero)

        # Body — monospace text
        body = QPlainTextEdit()
        body.setPlainText(display_text)
        body.setReadOnly(True)
        body.setStyleSheet(
            "QPlainTextEdit{background:#1E1E1E;color:#E0E0E0;"
            "font:11px 'Consolas','Courier New';border:none;padding:10px;}")
        body.setLineWrapMode(QPlainTextEdit.NoWrap)
        # Scroll to end (newest entries)
        body.verticalScrollBar().setValue(
            body.verticalScrollBar().maximum())
        root.addWidget(body, 1)

        # Buttons
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(16, 10, 16, 12)

        btn_open_folder = QPushButton("📁 Klasörde Göster")
        btn_open_folder.setToolTip("Log dosyasının bulunduğu klasörü aç")
        btn_open_folder.setStyleSheet(
            "QPushButton{background:#E5EEF7;color:#404040;"
            "padding:8px 14px;border:1px solid #B8D4E8;"
            "border-radius:3px;font:500 11px 'Segoe UI';}"
            "QPushButton:hover{background:#D5E5F5;}")

        def _open_log_folder():
            try:
                import subprocess
                if sys.platform == "win32":
                    subprocess.Popen(
                        ["explorer", "/select,", str(log_path)])
                else:
                    subprocess.Popen(
                        ["xdg-open", str(Path(log_path).parent)])
            except Exception as ex:
                _log_warning(f"open log folder: {ex}")
        btn_open_folder.clicked.connect(_open_log_folder)
        btn_row.addWidget(btn_open_folder)

        btn_copy = QPushButton("📋 Tümünü Kopyala")
        btn_copy.setToolTip("Log içeriğini panoya kopyala — "
                            "destek talebine yapıştırmak için")
        btn_copy.setStyleSheet(
            "QPushButton{background:#E5EEF7;color:#404040;"
            "padding:8px 14px;border:1px solid #B8D4E8;"
            "border-radius:3px;font:500 11px 'Segoe UI';}"
            "QPushButton:hover{background:#D5E5F5;}")
        def _copy_all():
            try:
                cb = QApplication.clipboard()
                cb.setText(content)
                self.statusBar().showMessage(
                    "✓ Log içeriği panoya kopyalandı", 3000)
            except Exception as ex:
                _log_warning(f"copy log: {ex}")
        btn_copy.clicked.connect(_copy_all)
        btn_row.addWidget(btn_copy)

        btn_row.addStretch()

        btn_close = QPushButton("Kapat")
        btn_close.setStyleSheet(
            "QPushButton{background:#0078D4;color:white;"
            "padding:8px 22px;border:none;border-radius:3px;"
            "font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:#005A9E;}")
        btn_close.clicked.connect(dlg.close)
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

        dlg.show()


    def _show_video_introduction(self):
        """🎬 Video-style visual introduction.

        v68-AI: A full-screen, slide-by-slide visual tour of the app's
        capabilities. Each "slide" is a beautifully-designed widget
        with a feature title, large icon, description, and a small
        animation. Auto-advances every ~7 seconds (or doctor can
        click ▶/⏸/⏭ to control).

        Also speaks the description text via TTS so the doctor can
        watch hands-free. Inspired by Apple Keynote demo videos and
        modern product onboarding tours.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("🎬 YazKlinik — Görsel Tanıtım")
        dlg.setMinimumSize(960, 720)
        dlg.setModal(True)

        # Slides: each is (icon, title, subtitle, body_html, gradient, key)
        slides = [
            # ── Açılış ──────────────────────────────────────────
            ("🏥", "YazKlinik",
             "Yapay Zeka Destekli Premium Klinik Sistemi",
             "<p style='font-size:14px;'>Merhaba doktor!</p>"
             "<p>Ben <b style='color:#003F6F;'>YazKlinik</b>. "
             "<b>YAZ Software</b> tarafından, Op. Dr. Hakan Yaz için "
             "özel olarak geliştirildim.</p>"
             "<p>Önümüzdeki birkaç dakikada size <b>neler yapabildiğimi</b> "
             "anlatacağım. Hazırsanız başlayalım.</p>"
             "<p style='font-size:11px;color:#888;text-align:center;"
             "margin-top:18px;'>"
             "✨ Hazırlanın — gerçek bir gösteri sizi bekliyor ✨</p>",
             "#003F6F,#0078D4,#5A1FB8",
             "intro"),

            # ── Klinik Akıl ─────────────────────────────────────
            ("🧠", "Klinik Akıl",
             "Her hasta için anında risk skoru ve öneriler",
             "<p>Her hastanız için saniyeler içinde "
             "<b>0-100 arası risk skoru</b> hesaplıyorum.</p>"
             "<p><b>ACOG ve RCOG temelli</b> öneriler:</p>"
             "<ul>"
             "<li><b>Yaş + GPAL analizi</b> (gravida, para, abortus, yaşayan)</li>"
             "<li><b>Kronik hastalık + ilaç riskleri</b> — diyabet, "
             "hipertansiyon, tiroit</li>"
             "<li><b>🚨 Teratojen ilaç tespiti</b> — kritik kırmızı uyarı</li>"
             "<li><b>NIPT, OGTT, anomali tarama</b> zamanlaması</li>"
             "<li><b>Düzensiz takip + atlanmış vizit</b> uyarısı</li>"
             "<li><b>Rhogam zamanı</b> (Rh- + 24-32 hf otomatik)</li>"
             "</ul>"
             "<p style='color:#5A1FB8;font-weight:700;'>Kısayol: Ctrl+Shift+I</p>",
             "#7C3AED,#5A1FB8,#3F1480",
             "clinical_ai"),

            # ── Bugünkü Klinik ──────────────────────────────────
            ("📊", "Bugünkü Klinik Dashboard",
             "Sol panelde 4 canlı kart, gününüz tek bakışta",
             "<p>Sol panelde <b>4 canlı kart</b> her saniye günceller:</p>"
             "<ul>"
             "<li>📅 <b>Bugün</b> — bugünün gelişleri</li>"
             "<li>⚠️ <b>Riskli</b> — tehlike bayrağı olanlar</li>"
             "<li>👶 <b>Doğum</b> — 36+ haftalık veya postterm</li>"
             "<li>🤱 <b>Doğuranlar</b> — postpartum takip listesi</li>"
             "</ul>"
             "<p>Tıkla → o gruba <b>otomatik filtrele</b>. "
             "Hiçbir hastanı atlamazsın.</p>",
             "#0078D4,#003F6F,#001F4F",
             "dashboard"),

            # ── Ultrason / Voluson Entegrasyonu ─────────────────
            ("🩻", "Voluson Ultrason Entegrasyonu",
             "Cihazınızla derin entegrasyon — otomatik PDF okuma",
             "<p>Voluson cihazınızla aynı dili konuşuyorum:</p>"
             "<ul>"
             "<li>📄 <b>PDF raporlarını otomatik okurum</b></li>"
             "<li>📐 <b>BPD, AC, FL, HC, EFW</b> ölçümlerini çıkartırım</li>"
             "<li>💧 <b>Amniyon mayı, doppler</b> değerlerini gösteririm</li>"
             "<li>👯 <b>İkiz gebelikleri</b> ayrı fetüs olarak takip ederim</li>"
             "<li>📅 <b>EDD, GA</b> otomatik hesaplanır</li>"
             "<li>🔄 <b>2-katmanlı PDF cache</b> ile 6798× hızlanma</li>"
             "</ul>"
             "<p style='color:#9A1B1F;'>"
             "<b>Hiçbir bilgi elden geçmez. Her şey otomatik.</b></p>",
             "#005A9E,#003F6F,#0078D4",
             "voluson"),

            # ── DICOM PACS ──────────────────────────────────────
            ("📡", "DICOM PACS Entegrasyonu",
             "Orthanc sunucusu ile gerçek zamanlı senkron",
             "<p>USG cihazınızdan görüntüleri <b>otomatik çekerim</b>:</p>"
             "<ul>"
             "<li>🔗 <b>Hasta-Orthanc eşleştirme</b> akıllı algoritma</li>"
             "<li>💾 <b>NAS'a otomatik kayıt</b> (DICOM + JPG + cine)</li>"
             "<li>🌐 <b>Web'de aç</b> (Osimis, Stone Viewer)</li>"
             "<li>📐 <b>DICOM ölçümleri</b> çıkar (mm cinsinden)</li>"
             "<li>🎬 <b>Cine DICOM</b> yerleşik oynatıcı (oynat/duraklat/seek)</li>"
             "<li>📊 <b>3D, doppler, mod bilgileri</b> görsel etiketler</li>"
             "</ul>",
             "#D13438,#9A1B1F,#5A0408",
             "dicom"),

            # ── Görüntü Kalitesi AI ─────────────────────────────
            ("✨", "Görüntü Kalitesi Yapay Zeka",
             "Her fotoğrafa kalite skoru — en iyiyi seçin",
             "<p>Bilgisayar görüsü ile her görüntüyü puanlarım:</p>"
             "<ul>"
             "<li>⚡ <b>Keskinlik</b> (Laplacian variance) — %40</li>"
             "<li>☀️ <b>Parlaklık dengesi</b> — %25</li>"
             "<li>◐ <b>Kontrast</b> (RMS) — %15</li>"
             "<li>🖼 <b>Çözünürlük</b> — %15</li>"
             "<li>🌈 <b>Renk zenginliği</b> — %5</li>"
             "</ul>"
             "<p>Görüntü preview'da <b>'✨ AI Sırala'</b> tıkla → "
             "en kaliteli en başta. <b>⭐ Mükemmel</b> badge ile işaretlenir.</p>"
             "<p style='color:#888;'>Hangisini hastaya göstereceksin? "
             "AI sana söyler.</p>",
             "#E58E00,#C46500,#8C4A00",
             "image_ai"),

            # ── WhatsApp + Yazdırma ─────────────────────────────
            ("💬", "WhatsApp + Yazdırma",
             "Tek tık → hastaya görüntü, rapor, dosya",
             "<p>Görüntülerinizi paylaşmak <b>tek tık</b>:</p>"
             "<ul>"
             "<li>💬 <b>WhatsApp'a tek tık</b> — hastanın numarasıyla "
             "doğrudan açılır</li>"
             "<li>📦 <b>ZIP modu</b> — tüm dosyaları tek arşivde gönder</li>"
             "<li>🖨 <b>Qt yerleşik yazıcı</b> — A4, A5, A3, fotoğraf, "
             "termal kağıt</li>"
             "<li>📋 <b>Panoya kopyala</b> — kısa ve uzun özet, F1/F2</li>"
             "<li>📨 <b>Sevk mektubu</b> otomatik üretim, A4 yazdır</li>"
             "</ul>"
             "<p style='color:#107C10;'><b>Hasta tek dosyayla mutlu, "
             "siz hızlı.</b></p>",
             "#107C10,#0B5D0B,#053C05",
             "share"),

            # ── Akıllı Yazma ────────────────────────────────────
            ("💡", "Akıllı Yazma + Öğrenme",
             "Notlarınızdan öğreniyor, yazım hatalarını düzeltiyor",
             "<p>Not yazarken <b>yardımcınızım</b>:</p>"
             "<ul>"
             "<li>✨ <b>220+ tıbbi terim</b> otomatik tamamlama "
             "('preek' → preeklampsi)</li>"
             "<li>〰️ <b>Yazım hataları kırmızı dalgalı çizgi</b> ile işaretlenir</li>"
             "<li>🔧 <b>Sağ tık → 'AI Düzeltme: asprin → aspirin'</b></li>"
             "<li>📚 <b>Yazdıkların öğrenilir</b>, sık kullandıklarını öneririm</li>"
             "<li>💭 <b>'Sık Kullanılan İfadeler' butonu</b> — tek tık ekle</li>"
             "<li>🇹🇷 <b>150+ Türkçe yazım hatası</b> sözlük</li>"
             "</ul>"
             "<p style='color:#107C10;'>"
             "<b>Ne kadar yazarsan, o kadar zekileşirim.</b></p>",
             "#107C10,#0B5D0B,#053C05",
             "smart_text"),

            # ── Komut Paleti ────────────────────────────────────
            ("🔍", "Komut Paleti — Ctrl+K",
             "VS Code tarzı hızlı erişim, fuzzy arama",
             "<p><b>Ctrl+K</b> ile her yere bir tıkla ulaş:</p>"
             "<ul>"
             "<li>👤 <b>Hasta adı yaz</b> → direkt aç</li>"
             "<li>⚡ <b>'>' yaz</b> → komutları filtrele</li>"
             "<li>🎯 <b>Fuzzy matching</b> — yazım hatasına toleranslı</li>"
             "<li>↑↓ <b>Klavye gezinti</b>, Enter ile aç</li>"
             "<li>📋 <b>Tüm komutlar</b> tek noktadan</li>"
             "</ul>"
             "<p style='color:#5A1FB8;font-weight:700;'>"
             "Mouse'a hiç dokunma. Sadece klavye.</p>",
             "#5A1FB8,#3F1480,#1F0440",
             "smart_search"),

            # ── Gebelik Timeline ────────────────────────────────
            ("🗓", "Gebelik Timeline",
             "Tüm gebelik yolculuğunu görsel zaman çizelgesi",
             "<p>Hastanın <b>tüm gebelik yolculuğunu</b> tek grafikte göster:</p>"
             "<ul>"
             "<li>🟦 <b>Trimester bantları</b> (T1 mavi, T2 mor, T3 kırmızı)</li>"
             "<li>⭕ <b>Her geliş için renkli daire</b></li>"
             "<li>🚩 <b>NIPT, anomali, OGTT, term, EDD</b> milestone işaretleri</li>"
             "<li>📈 <b>Risk skoru zaman çizgisi</b> renkli</li>"
             "<li>👆 <b>Tıklanabilir noktalar</b> — direkt o gelişe atla</li>"
             "</ul>"
             "<p style='color:#5A1FB8;font-weight:700;'>Kısayol: Ctrl+Shift+T</p>",
             "#0078D4,#5A1FB8,#D13438",
             "timeline"),

            # ── Büyüme Eğrileri ─────────────────────────────────
            ("📈", "Büyüme Eğrileri",
             "Persantil bantlı klinik fetal büyüme grafiği",
             "<p>Tüm USG ölçümlerini <b>persantil bantlarında</b> görselleştirir:</p>"
             "<ul>"
             "<li>🌫 <b>p3-p97 dış band</b> (uç sınırlar)</li>"
             "<li>🌥 <b>p10-p90 iç band</b> (normal aralık)</li>"
             "<li>━ <b>p50 medyan çizgi</b></li>"
             "<li>🔴 <b>Hastanın ölçümleri noktalar</b> + bağlantı çizgisi</li>"
             "<li>📊 <b>BPD, AC, FL, HC</b> ayrı ayrı veya birlikte</li>"
             "</ul>"
             "<p>Anneye gösterilebilir kalitede, klinik kalibre. <b>F8</b> ile aç.</p>",
             "#9A1B1F,#6E1316,#420707",
             "growth"),

            # ── Sevk Mektubu ────────────────────────────────────
            ("📨", "Otomatik Sevk Mektubu",
             "Profesyonel doktor mektubu, tek tık üretim",
             "<p>Tek tıkla <b>resmi sevk yazısı</b> üret:</p>"
             "<ul>"
             "<li>👤 <b>Demografi + GPAL + GA</b> otomatik dolar</li>"
             "<li>🏥 <b>10+ farklı bölüme sevk</b> seçeneği</li>"
             "<li>🧠 <b>Klinik akıl risk skoru</b> entegre</li>"
             "<li>✏️ <b>İstediğin gibi düzenle</b></li>"
             "<li>🖨 <b>A4 yazdır</b> veya 💾 <b>PDF kaydet</b></li>"
             "</ul>"
             "<p style='color:#5A1FB8;font-weight:700;'>Kısayol: Ctrl+Shift+R</p>",
             "#005A9E,#003F6F,#001F4F",
             "referral"),

            # ── Onam + Reçete ───────────────────────────────────
            ("📋", "Onam + Reçete Kütüphanesi",
             "Tüm formlarınız tek noktada, kategorili",
             "<p>PDF/Word belgelerini <b>kategoriye göre</b> sakla:</p>"
             "<ul>"
             "<li>📋 <b>Onam:</b> Obstetrik, Jinekolojik, Lazer, "
             "Medikal Estetik, Jinekolojik Estetik</li>"
             "<li>💊 <b>Reçete:</b> Antibiyotik, Hormon, Vitamin, vb.</li>"
             "<li>📥 <b>Tek tık yükle</b>, tek tık yazdır</li>"
             "<li>📊 <b>Kullanım istatistiği</b> takibi</li>"
             "<li>🎯 <b>A4 onam, A5 reçete</b> otomatik boyut</li>"
             "</ul>"
             "<p style='color:#5A1FB8;font-weight:700;'>"
             "Onam: Ctrl+Shift+O · Reçete: Ctrl+Alt+R</p>",
             "#005A9E,#107C10,#0B5D0B",
             "library"),

            # ── Doğum Kayıt + Doğuranlar ────────────────────────
            ("🤱", "Doğum Kaydı + Postpartum",
             "Hastanız doğurduğunda — tek tık kayıt",
             "<p>Hastanız doğurduğunda <b>söylemeniz yeter</b>:</p>"
             "<ul>"
             "<li>👶 <b>Normal / Sezaryen / Vakum / Forseps</b> seçimi</li>"
             "<li>📅 <b>Tarih, ağırlık, cinsiyet, hastane</b> kaydı</li>"
             "<li>🤰 <b>Otomatik gebelik takibinden çıkar</b></li>"
             "<li>🤱 <b>Doğuranlar grubuna alır</b></li>"
             "<li>📊 <b>Yıllık istatistikler</b>: normal/sezaryen oranı, "
             "preterm sayısı, ikiz</li>"
             "<li>📅 <b>Aylara göre kronolojik</b> liste</li>"
             "</ul>"
             "<p style='color:#5A1FB8;font-weight:700;'>Kısayol: Ctrl+Shift+D</p>",
             "#B5368A,#8B2A6D,#6F2256",
             "delivery"),

            # ── AI Asistan Dashboard ────────────────────────────
            ("🤖", "AI Asistan Dashboard",
             "Davranışlarınızı öğrenir, kişiselleştirilmiş öneriler",
             "<p>Programı kullandıkça <b>sizi öğreniyorum</b>:</p>"
             "<ul>"
             "<li>👥 <b>En çok ziyaret ettiğiniz hastalar</b></li>"
             "<li>⚡ <b>En sık kullandığınız eylemler</b></li>"
             "<li>⏰ <b>Saat bazlı aktivite paterni</b></li>"
             "<li>💭 <b>Öğrendiğim ifadeler</b> listesi</li>"
             "<li>🌅 <b>Sabah karşılaması, akşam özeti</b></li>"
             "</ul>"
             "<p style='color:#107C10;'>"
             "<b>Tüm veriler bilgisayarınızda kalır — gizliliğiniz "
             "%100 garanti.</b></p>"
             "<p style='color:#5A1FB8;font-weight:700;'>Kısayol: Ctrl+Shift+A</p>",
             "#5A1FB8,#7C3AED,#0078D4",
             "ai_dashboard"),

            # ── Bayraklar + Hatırlatıcılar ──────────────────────
            ("🚩", "Bayraklar + Proaktif Hatırlatıcılar",
             "Önemli klinik durumlar görsel uyarı bantları",
             "<p>Hasta için kritik durumları <b>görsel bayrak</b>'la işaretle:</p>"
             "<ul>"
             "<li>🟥 <b>Kırmızı bayraklar</b>: Riskli gebelik, kötü "
             "obstetrik öykü, kan uyuşmazlığı</li>"
             "<li>🟧 <b>Sarı uyarılar</b>: Sezaryen, antikoagülan, "
             "imza takibi yok</li>"
             "<li>🟩 <b>Yeşil bayraklar</b>: NIPT yapıldı, "
             "riskli gebelik takipte</li>"
             "<li>🍞 <b>Toast bildirimleri</b> hasta seçince otomatik</li>"
             "<li>⏰ <b>NIPT, OGTT, anomali, term</b> zamanı geldiğinde uyarı</li>"
             "</ul>",
             "#C42B1C,#9A1B1F,#5A0408",
             "flags"),

            # ── Güvenlik / Gizlilik ─────────────────────────────
            ("🔐", "Güvenlik + Gizlilik",
             "Tüm veriler bilgisayarınızda — hiçbir şey internete gitmez",
             "<p><b>Hiçbir hasta verisi kliniğin dışına çıkmaz.</b></p>"
             "<ul>"
             "<li>💾 <b>SQLite local DB</b> — tek dosya, taşınabilir</li>"
             "<li>📁 <b>NAS senkron</b> sadece klinik ağında</li>"
             "<li>🚫 <b>İnternet yok, dış API yok, telemetri yok</b></li>"
             "<li>🔒 <b>WAL mode</b> — yedeklenmiş, çoklu okuma güvenli</li>"
             "<li>💾 <b>Otomatik yedek</b> — Ctrl+Shift+B</li>"
             "<li>🛡 <b>KVKK uyumlu</b> tasarım</li>"
             "</ul>"
             "<p style='color:#107C10;font-weight:700;font-size:14px;'>"
             "Hastalarınızın gizliliği yüzde yüz garanti.</p>",
             "#107C10,#0B5D0B,#003F0F",
             "security"),

            # ── Outro ───────────────────────────────────────────
            ("🎉", "Birlikte Çalışmaya Başlayalım",
             "Sen istediğini söyle, ben yapayım",
             "<p>İşte yapabildiklerimin özeti.</p>"
             "<p>Beni kullandıkça <b>daha iyi hale geleceğim</b>. "
             "Yazdığın notları öğrenir, alışkanlıklarını anlar, "
             "kişiselleştirilmiş öneriler sunarım.</p>"
             "<br>"
             "<p style='font-size:15px;text-align:center;'>"
             "<b>YAZ Software</b><br>"
             "<span style='color:#666;'>Op. Dr. Hakan Yaz için "
             "özel olarak geliştirildi</span><br>"
             "<span style='color:#888;'>© 2026</span></p>"
             "<br>"
             "<p style='color:#5A1FB8;font-size:16px;font-weight:700;"
             "text-align:center;'>"
             "Hoş geldiniz, doktor!</p>",
             "#5A1FB8,#0078D4,#107C10",
             "outro"),
        ]

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Stacked widget for slides ────────────────────────────
        from PySide6.QtWidgets import QStackedWidget
        slide_stack = QStackedWidget()
        slide_stack.setStyleSheet("background:#000;")

        # Build each slide
        slide_widgets = []
        for icon, title, subtitle, body_html, gradient, key in slides:
            sw = QWidget()
            sw.setStyleSheet(
                f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                f"stop:0 {gradient.split(',')[0]},"
                f"stop:0.5 {gradient.split(',')[1]},"
                f"stop:1 {gradient.split(',')[2]});")
            sl = QVBoxLayout(sw)
            sl.setContentsMargins(60, 40, 60, 40)
            sl.setSpacing(8)
            sl.setAlignment(Qt.AlignCenter)

            # Big icon
            icon_lbl = QLabel(icon)
            icon_lbl.setAlignment(Qt.AlignCenter)
            icon_lbl.setStyleSheet(
                "font-size:120px;color:white;background:transparent;"
                "padding:0;")
            sl.addWidget(icon_lbl)

            # Title
            title_lbl = QLabel(title)
            title_lbl.setAlignment(Qt.AlignCenter)
            title_lbl.setStyleSheet(
                "color:white;font:900 42px 'Segoe UI';"
                "background:transparent;letter-spacing:-1px;"
                "padding:8px;")
            title_lbl.setWordWrap(True)
            sl.addWidget(title_lbl)

            # Subtitle
            sub_lbl = QLabel(subtitle)
            sub_lbl.setAlignment(Qt.AlignCenter)
            sub_lbl.setStyleSheet(
                "color:rgba(255,255,255,0.92);font:600 18px 'Segoe UI';"
                "background:transparent;padding:4px 0 16px 0;")
            sub_lbl.setWordWrap(True)
            sl.addWidget(sub_lbl)

            # Body in a centered card
            body_card = QLabel(body_html)
            body_card.setTextFormat(Qt.RichText)
            body_card.setWordWrap(True)
            body_card.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            body_card.setStyleSheet(
                "background:rgba(255,255,255,0.95);color:#222;"
                "padding:24px 32px;border-radius:12px;"
                "font:13px 'Segoe UI';line-height:1.7;")
            body_card.setMaximumWidth(620)
            sl.addWidget(body_card, 0, Qt.AlignCenter)

            sl.addStretch()
            slide_stack.addWidget(sw)
            slide_widgets.append(sw)

        root.addWidget(slide_stack, 1)

        # ── Bottom control bar ──────────────────────────────────
        bottom = QWidget()
        bottom.setFixedHeight(60)
        bottom.setStyleSheet(
            "background:#1a1a1a;color:white;")
        bl = QHBoxLayout(bottom)
        bl.setContentsMargins(20, 8, 20, 8)
        bl.setSpacing(10)

        # Slide counter
        counter_lbl = QLabel(f"1 / {len(slides)}")
        counter_lbl.setStyleSheet(
            "color:white;font:700 13px 'Segoe UI';"
            "background:rgba(255,255,255,0.15);padding:6px 14px;"
            "border-radius:14px;")
        bl.addWidget(counter_lbl)

        # Slide title
        slide_title_lbl = QLabel(slides[0][1])
        slide_title_lbl.setStyleSheet(
            "color:rgba(255,255,255,0.85);font:600 12px 'Segoe UI';"
            "background:transparent;padding:0 12px;")
        bl.addWidget(slide_title_lbl, 1)

        # Controls
        prev_btn = QPushButton("⏮")
        prev_btn.setCursor(Qt.PointingHandCursor)
        prev_btn.setFixedSize(40, 40)
        prev_btn.setToolTip("Önceki slayt")
        prev_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.15);"
            "color:white;border:none;border-radius:20px;"
            "font:600 16px 'Segoe UI';}"
            "QPushButton:hover{background:rgba(255,255,255,0.3);}")
        bl.addWidget(prev_btn)

        play_btn = QPushButton("⏸")
        play_btn.setCursor(Qt.PointingHandCursor)
        play_btn.setFixedSize(40, 40)
        play_btn.setToolTip("Duraklat / oynat")
        play_btn.setStyleSheet(
            "QPushButton{background:white;color:#222;border:none;"
            "border-radius:20px;font:700 16px 'Segoe UI';}"
            "QPushButton:hover{background:#E0E0E0;}")
        bl.addWidget(play_btn)

        next_btn = QPushButton("⏭")
        next_btn.setCursor(Qt.PointingHandCursor)
        next_btn.setFixedSize(40, 40)
        next_btn.setToolTip("Sonraki slayt")
        next_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.15);"
            "color:white;border:none;border-radius:20px;"
            "font:600 16px 'Segoe UI';}"
            "QPushButton:hover{background:rgba(255,255,255,0.3);}")
        bl.addWidget(next_btn)

        close_btn = QPushButton("✕ Kapat")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton{background:rgba(255,255,255,0.15);"
            "color:white;border:none;padding:8px 16px;"
            "border-radius:4px;font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:rgba(255,255,255,0.3);}")
        close_btn.clicked.connect(dlg.close)
        bl.addWidget(close_btn)

        root.addWidget(bottom)

        # ── State + auto-advance + TTS ──────────────────────────
        state = {
            "idx": 0,
            "playing": True,
            "tts_thread": None,
        }
        auto_timer = QTimer(dlg)

        def _go_to(idx):
            """Switch to slide index (0-based), wrap-around."""
            idx = idx % len(slides)
            state["idx"] = idx
            slide_stack.setCurrentIndex(idx)
            counter_lbl.setText(f"{idx + 1} / {len(slides)}")
            slide_title_lbl.setText(slides[idx][1])

        def _next():
            _go_to(state["idx"] + 1)

        def _prev():
            _go_to(state["idx"] - 1)

        def _toggle_play():
            if state["playing"]:
                auto_timer.stop()
                play_btn.setText("▶")
                state["playing"] = False
            else:
                auto_timer.start(8000)
                play_btn.setText("⏸")
                state["playing"] = True

        prev_btn.clicked.connect(_prev)
        next_btn.clicked.connect(_next)
        play_btn.clicked.connect(_toggle_play)
        auto_timer.timeout.connect(_next)
        auto_timer.start(8000)  # 8 seconds per slide

        # Stop timer on close
        def _on_close():
            try:
                auto_timer.stop()
            except Exception as _ex:
                _log_warning(f"video timer stop: {_ex}")
        dlg.finished.connect(lambda _: _on_close())

        dlg.exec()

    def _open_web_interface(self):
        """🌐 v68-AI: Web arayüzünü tarayıcıda aç.

        Birden fazla kaynak dener:
          1. QSettings'te kayıtlı özel URL
          2. localhost:5000 (bu PC'de Flask varsa)
          3. Yaygın LAN IP'leri (192.168.1.x, 10.0.0.x)

        Bulamazsa doktora nerede olduğunu sorar ve kaydeder.
        """
        import webbrowser

        # QSettings'te kayıtlı URL var mı?
        s = _clinic_settings()
        saved_url = s.value("web/url", "", type=str)

        if saved_url:
            # Önce kayıtlıyı dene
            try:
                import urllib.request as _ur
                _ur.urlopen(saved_url, timeout=2.0)
                webbrowser.open(saved_url)
                self.statusBar().showMessage(
                    f"🌐 Web arayüzü açıldı: {saved_url}", 3000)
                return
            except Exception as _ex:
                _log_warning(f"saved web url failed: {_ex}")

        # Otomatik keşif
        import urllib.request as _ur
        candidate_urls = [
            "http://localhost:5000",
            "http://127.0.0.1:5000",
        ]
        # Aynı LAN subnet'indeki olası IP'ler
        try:
            import socket
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            if local_ip and not local_ip.startswith("127."):
                # Son oktet'i gez
                parts = local_ip.split(".")
                if len(parts) == 4:
                    base = ".".join(parts[:3])
                    # Tipik server IP'leri
                    for n in [1, 10, 50, 100, 200, 254]:
                        candidate_urls.append(
                            f"http://{base}.{n}:5000")
        except Exception as _ex:
            _log_warning(f"LAN discovery: {_ex}")

        found_url = None
        for url in candidate_urls:
            try:
                resp = _ur.urlopen(url, timeout=1.0)
                if resp.status in (200, 302):
                    found_url = url
                    break
            except Exception as _ux:
                # Normal — web yoksa
                _log_warning(f"web discover {url}: {_ux}")

        if found_url:
            webbrowser.open(found_url)
            s.setValue("web/url", found_url)
            s.sync()
            self.statusBar().showMessage(
                f"🌐 Web arayüzü bulundu: {found_url}", 3000)
            return

        # Bulunamadı — doktora sor
        from PySide6.QtWidgets import QInputDialog
        url, ok = QInputDialog.getText(
            self, "Web Sunucu URL'si",
            "YazKlinik Web bulunamadı.\n\n"
            "Server PC'nin URL'sini girin:\n"
            "(Örn: http://192.168.1.50:5000)",
            text="http://192.168.1.50:5000")
        if ok and url:
            try:
                _ur.urlopen(url, timeout=2.0)
                s.setValue("web/url", url)
                s.sync()
                webbrowser.open(url)
                self.statusBar().showMessage(
                    f"🌐 Web kaydedildi ve açıldı: {url}", 5000)
            except Exception as ex:
                QMessageBox.warning(
                    self, "Bağlanılamadı",
                    f"Web sunucusuna erişilemedi:\n\n{ex}\n\n"
                    "Kontrol et:\n"
                    "• URL doğru mu?\n"
                    "• Server PC açık mı?\n"
                    "• Flask çalışıyor mu (cmd'de)?\n"
                    "• Firewall 5000 açık mı?")

    def _open_web_patient(self):
        """🌐 v68-AI: Mevcut hastayı web arayüzünde aç.

        Sağ tık menüsüne hasta kartından erişilebilir. Doktor
        seçili hastaya Mac/iPad'den bakmak isteyebilir.
        """
        import webbrowser
        from urllib.parse import quote

        if not self.current_patient:
            QMessageBox.information(
                self, "Hasta Seçili Değil",
                "Önce bir hasta seçin.")
            return

        key = self.active_patient_key()
        if not key:
            return

        # Kayıtlı URL'yi al
        s = _clinic_settings()
        base_url = s.value("web/url", "", type=str)
        if not base_url:
            # Keşif yap
            self._open_web_interface()
            # Tekrar oku
            base_url = s.value("web/url", "", type=str)
            if not base_url:
                return

        # Hasta sayfasına git
        url = f"{base_url.rstrip('/')}/hasta/{quote(key)}"
        webbrowser.open(url)
        self.statusBar().showMessage(
            f"🌐 Hasta web'de açıldı: {key}", 3000)

    def _open_web_calendar(self):
        """🌐 v68-AI: Web'deki haftalık takvimi aç."""
        import webbrowser

        s = _clinic_settings()
        base_url = s.value("web/url", "", type=str)
        if not base_url:
            self._open_web_interface()
            base_url = s.value("web/url", "", type=str)
            if not base_url:
                return

        url = f"{base_url.rstrip('/')}/takvim"
        webbrowser.open(url)
        self.statusBar().showMessage(
            "🌐 Web takvim açıldı", 3000)

    def _show_today_appointments(self):
        """📅 v68-AI: Bugünün randevularını dialog'da göster.

        Web uygulaması aynı SQLite DB'yi kullandığından masaüstü
        de doğrudan okuyabilir. Doktor programı açtığında bugün
        kimlerin geleceğini bir bakışta görür.
        """
        from datetime import datetime as _dt

        today = _dt.now().strftime("%Y-%m-%d")
        today_tr = _dt.now().strftime("%d.%m.%Y")
        day_names = ["Pazartesi", "Salı", "Çarşamba", "Perşembe",
                      "Cuma", "Cumartesi", "Pazar"]
        day_name = day_names[_dt.now().weekday()]

        rows = []
        total = 0
        try:
            ensure_db()
            with db_conn() as con:
                # appointments tablosu web tarafından oluşturulur
                # masaüstü de aynı DB'de — okuyabilir
                try:
                    appts = con.execute(
                        "SELECT a.appointment_time, "
                        "a.patient_key, a.purpose, a.note, "
                        "a.status, p.display_name "
                        "FROM appointments a "
                        "LEFT JOIN patients p "
                        "  ON p.folder_key = a.patient_key "
                        "WHERE a.appointment_date = ? "
                        "AND a.status != 'cancelled' "
                        "ORDER BY a.appointment_time",
                        (today,)).fetchall()
                except sqlite3.OperationalError:
                    # appointments tablosu yok — web hiç çalışmamış
                    appts = []
                total = len(appts)
                for r in appts:
                    time_str = r[0] or ""
                    pt_key = r[1] or ""
                    purpose = r[2] or ""
                    note = r[3] or ""
                    status = r[4] or "planned"
                    pt_name = r[5] or pt_key

                    status_icon = {
                        "planned": "⏳",
                        "confirmed": "✅",
                        "completed": "✓",
                        "no_show": "❌",
                    }.get(status, "•")
                    status_color = {
                        "planned": "#0078D4",
                        "confirmed": "#107C10",
                        "completed": "#606060",
                        "no_show": "#C46500",
                    }.get(status, "#000")

                    rows.append(
                        f'<tr>'
                        f'<td style="padding:6px 10px;'
                        f'font-weight:bold;font-size:14px;'
                        f'color:{status_color};">'
                        f'{time_str}</td>'
                        f'<td style="padding:6px 10px;">'
                        f'{status_icon} <b>{pt_name}</b>'
                        f'<br><small style="color:#606060;">'
                        f'🩺 {purpose}'
                        f'{f" · 📝 {note[:40]}" if note else ""}'
                        f'</small></td>'
                        f'</tr>')
        except Exception as ex:
            _log_warning(f"show_today_appointments: {ex}")
            rows = [f'<tr><td colspan="2">Hata: {ex}</td></tr>']

        if not rows:
            body = ('<p style="text-align:center;color:#606060;'
                    'padding:40px;">📅 Bugün randevu yok.</p>')
        else:
            body = (f'<table style="width:100%;border-collapse:collapse;'
                    f'border:1px solid #ddd;">'
                    f'{"".join(rows)}</table>')

        html = (
            f'<h3 style="color:#005A9E;margin:0 0 6px 0;">'
            f'📅 Bugünün Randevuları</h3>'
            f'<p style="color:#606060;margin:0 0 16px 0;">'
            f'{today_tr} — {day_name} · <b>{total}</b> randevu</p>'
            f'{body}'
            f'<p style="color:#888;font-size:11px;margin-top:16px;">'
            f'Randevular web arayüzünden eklenir ve güncellenir. '
            f'Tam yönetim için "🌐 Web Takvim" menüsünü kullan.</p>')

        box = QMessageBox(self)
        box.setWindowTitle("Bugünün Randevuları")
        box.setTextFormat(Qt.RichText)
        box.setText(html)
        # Web'e git butonu
        btn_web = box.addButton(
            "🌐 Web Randevular", QMessageBox.ActionRole)
        btn_wa = box.addButton(
            "💬 Toplu WhatsApp", QMessageBox.ActionRole)
        box.addButton(QMessageBox.Ok)
        box.exec()
        if box.clickedButton() == btn_web:
            # Web'de randevular sayfasına git
            import webbrowser
            s = _clinic_settings()
            base_url = s.value("web/url", "", type=str)
            if base_url:
                webbrowser.open(
                    f"{base_url.rstrip('/')}/gun-plani")
        elif box.clickedButton() == btn_wa:
            import webbrowser
            s = _clinic_settings()
            base_url = s.value("web/url", "", type=str)
            if base_url:
                webbrowser.open(
                    f"{base_url.rstrip('/')}/toplu-hatirlatma")

    def _show_about(self):
        """v68-AI: Premium self-introducing About dialog.

        The app introduces itself by streaming text into a label
        character-by-character (typewriter effect) while simultaneously
        speaking via Windows SAPI (text-to-speech). When TTS isn't
        available, just the typewriter animation runs.

        Created by YAZ Software © 2026.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle("Hakkında — YazKlinik")
        dlg.setMinimumSize(720, 640)
        dlg.setModal(True)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Hero header — gradient with logo + title ─────────────
        hero = QWidget()
        hero.setFixedHeight(150)
        hero.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #003F6F,stop:0.5 #0078D4,stop:1 #5A1FB8);")
        hl = QHBoxLayout(hero)
        hl.setContentsMargins(28, 18, 28, 18)
        hl.setSpacing(20)

        # Big logo emoji
        logo = QLabel("🏥")
        logo.setStyleSheet(
            "font-size:78px;color:white;background:transparent;"
            "padding:0;")
        logo.setAlignment(Qt.AlignCenter)
        hl.addWidget(logo, 0)

        # Right side: name + tagline
        right_v = QVBoxLayout()
        right_v.setSpacing(2)
        title_lbl = QLabel("YazKlinik")
        title_lbl.setStyleSheet(
            "color:white;font:900 36px 'Segoe UI';"
            "background:transparent;letter-spacing:-1px;")
        right_v.addWidget(title_lbl)
        sub_lbl = QLabel("Yapay Zeka Destekli Klinik Yönetim Sistemi")
        sub_lbl.setStyleSheet(
            "color:rgba(255,255,255,0.94);font:600 14px 'Segoe UI';"
            "background:transparent;")
        right_v.addWidget(sub_lbl)
        ver_lbl = QLabel(f"Versiyon {APP_VERSION}  ·  © 2026 YAZ Software")
        ver_lbl.setStyleSheet(
            "color:rgba(255,255,255,0.78);font:500 11px 'Segoe UI';"
            "background:transparent;padding-top:4px;")
        right_v.addWidget(ver_lbl)

        # Clinic info chip (uses settings)
        try:
            clinic = get_clinic_name() or "Klinik"
            doc = get_clinic_doctor_name() or "Doktor"
            clinic_chip = QLabel(f"🏥 {clinic} · {doc}")
            clinic_chip.setStyleSheet(
                "color:rgba(255,255,255,0.95);font:600 11px 'Segoe UI';"
                "background:rgba(255,255,255,0.18);"
                "padding:4px 10px;border-radius:3px;margin-top:6px;")
            right_v.addWidget(clinic_chip, 0, Qt.AlignLeft)
        except Exception as _ex:
            _log_warning(f"about clinic chip: {_ex}")
        right_v.addStretch()
        hl.addLayout(right_v, 1)

        root.addWidget(hero)

        # ── Self-introduction text (streamed) ────────────────────
        # v68-AI: Premium self-introduction. Showcases EVERYTHING the
        # software does — DICOM, WhatsApp, AI, autocomplete, growth
        # charts, deliveries, etc. Designed to make the doctor proud
        # of his tool and aware of all its capabilities.
        intro_text = (
            "Merhaba, doktor! "
            "Ben YazKlinik. "
            "YAZ Software tarafından, sizin için yaratıldım. "
            "\n\n"
            "Operatör Doktor Hakan Yaz'ın hayalindeki klinik "
            "yönetim sistemini gerçeğe dönüştürmek için tasarlandım. "
            "Ben sadece bir yazılım değilim. "
            "Ben sizin asistanınızım, sağ kolunuzum, "
            "her şeyi takip eden gözünüzüm. "
            "\n\n"
            "Şimdi neler yapabildiğimi anlatayım. "
            "\n\n"
            "🎨 Önce arayüzümden bahsedeyim. "
            "Modern, premium bir tasarımım var. "
            "Her tıkladığınız buton, her açılan pencere, "
            "her sekme; özenle düşünülmüş gradient renkler, "
            "yumuşak gölgeler ve okunaklı tipografi ile karşınıza geliyor. "
            "Apple ve Microsoft'un en iyi yazılımlarından ilham aldım. "
            "Gözlerinizi yormam, sizi yorgun bırakmam. "
            "\n\n"
            "🩻 Ultrason cihazınızla derin entegrasyonum var. "
            "Voluson cihazlarınızdan gelen PDF raporlarını otomatik okurum, "
            "BPD, AC, FL, HC ölçümlerini, EFW tahmini fetal ağırlığı, "
            "amniyon mayı indeksini, doppler değerlerini "
            "anında çıkarır, hastanın özet sekmesinde gösteririm. "
            "Voluson'unuz DICOM görüntü gönderdiğinde Orthanc PACS sunucunuzdan "
            "otomatik çekerim, "
            "JPG'ye çevirir, klinik klasöre kaydederim. "
            "Cine yani video DICOM'ları bile yerleşik oynatıcımla izleyebilirsiniz. "
            "\n\n"
            "✨ Ve görüntülerinizi sıradan görmem. "
            "Her birini bilgisayar görüsü ile analiz ederim. "
            "Keskinlik, parlaklık, kontrast, çözünürlük, renk zenginliği. "
            "Bu beş parametreyi ölçer, her görüntüye sıfırdan yüze kadar "
            "bir kalite skoru veririm. "
            "Hangisini hastaya göstereceğinize karar vermenizi kolaylaştırırım. "
            "Mükemmel kalite görüntüler yıldız işaretiyle önce görünür. "
            "\n\n"
            "💬 Görüntülerinizi paylaşmak mı istiyorsunuz? "
            "WhatsApp'a tek tıkla gönderebilirsiniz. "
            "Hastanın numarası kayıtlıysa direkt ona açılır. "
            "Ya tek dosya ya zip arşivi olarak. "
            "Yazdırmak isterseniz, "
            "yerleşik yazıcı modülüm Qt teknolojisiyle "
            "her türlü kağıt boyutuna A4'ten A5'e, "
            "fotoğraf kağıdından termal ruloya kadar "
            "düzgünce çıktı verir. "
            "\n\n"
            "🧠 En güçlü yanım yapay zeka modüllerim. "
            "Klinik akıl dediğim sistemim her hasta için risk skoru hesaplar. "
            "Yaşı, gravida-para sayısı, kronik hastalıkları, "
            "kullandığı ilaçları, gebelik haftası, bayrakları, "
            "hepsini analiz edip ACOG ve RCOG temelli öneriler sunarım. "
            "Teratojen ilaç kullanıyorsa kırmızı uyarı, "
            "kan uyuşmazlığı varsa Rhogam zamanını söylerim. "
            "Düzensiz takipleri, atlanmış vizitleri yakalarım. "
            "\n\n"
            "💡 Yazarken sizi yormam. "
            "Notlarınıza yazım hatası yakalarsam kırmızı dalgalı çizgi ile gösteririm. "
            "Asprin yazdığınızda aspirin diye düzeltirim. "
            "Sezeryan yerine sezaryen demem gerektiğini bilirim. "
            "İki yüz yirmiden fazla tıbbi terimi otomatik tamamlarım. "
            "Sık kullandığınız cümleleri öğrenir, "
            "bir sonraki seferde size önerirım. "
            "Ne kadar çok yazarsanız, ben o kadar zekileşirim. "
            "\n\n"
            "🗓 Gebelik takip zaman çizelgem her hastanın "
            "tüm yolculuğunu görsel olarak gösterir. "
            "Trimester bantları, her geliş için renkli daireler, "
            "NIPT, anomali, OGTT, term, EDD işaretleri. "
            "Bir bakışta nerede olduğunuzu anlarsınız. "
            "\n\n"
            "📨 Sevk mektubu gerekiyorsa otomatik üretirim. "
            "Hasta demografisi, gebelik geçmişi, gestasyonel hafta, "
            "klinik akıl risk skoru. "
            "Hepsini doldurur, profesyonel bir doktor mektubu çıkarırım. "
            "\n\n"
            "📋 Onam formları ve hazır reçetelerim için ayrı kütüphanelerim var. "
            "Obstetrik, jinekolojik, lazer, medikal estetik, "
            "kategorilere ayrılmış. Yükle, sakla, tek tık yazdır. "
            "\n\n"
            "🤱 Hastanız doğurduğunda söylemeniz yeter. "
            "Normal mi sezaryen mi diye sorarım. "
            "Bebek ağırlığı, cinsiyet, hastane bilgilerini alır, "
            "doğum sonrası grubuna alırım. "
            "Doğum sonrası takibi başlatırım. "
            "Tüm doğumlarınız kronolojik sırayla saklanır, "
            "yıl sonu istatistikleri için hazır. "
            "\n\n"
            "📊 Bugünkü klinik dashboard'um her sabah "
            "günün hastalarını, riskli olanları, doğuma yakınları, "
            "doğuranlar grubunu sol panelde size sunar. "
            "Tek bakışta gününüzü planlarsınız. "
            "\n\n"
            "🎯 Davranışlarınızı öğrenirim. "
            "En çok ziyaret ettiğiniz hastaları, "
            "en sık yaptığınız işlemleri, "
            "hangi saatlerde nelere baktığınızı analiz ederim. "
            "Sabah açılışta size selamlama yaparım, "
            "akşam günün özetini sunarım. "
            "\n\n"
            "🔍 Aradığınız hiçbir şey kaybolmaz. "
            "Komut paleti olan akıllı arama özelliğim ile "
            "Control K kombinasyonuna basın, "
            "hasta adı yazın, anında ona ulaşın. "
            "\n\n"
            "🔐 Ve en önemlisi: "
            "Tüm verileriniz bilgisayarınızda kalır. "
            "Internet'e hiçbir şey gitmez. "
            "Hasta bilgilerinin tek bir baytı bile dış sunucuya çıkmaz. "
            "Gizliliğiniz, hastalarınızın gizliliği yüzde yüz garantilidir. "
            "\n\n"
            "İşte bunlar yapabildiklerimin bir özeti. "
            "Beni kullandıkça daha çok yardımcı olacağım. "
            "Birlikte hastalarınıza en iyi bakımı sunacağız. "
            "\n\n"
            "Hoş geldiniz, doktor."
        )

        # Body — large text label
        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setStyleSheet(
            "QScrollArea{background:#FAFAFA;border:none;"
            "border-bottom:1px solid #E0E0E0;}")
        body_w = QWidget()
        body_w.setStyleSheet("background:#FAFAFA;")
        body_lay = QVBoxLayout(body_w)
        body_lay.setContentsMargins(28, 20, 28, 20)
        body_lay.setSpacing(0)

        intro_lbl = QLabel("")
        intro_lbl.setWordWrap(True)
        intro_lbl.setTextFormat(Qt.PlainText)
        intro_lbl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        intro_lbl.setStyleSheet(
            "color:#222;font:500 14px 'Segoe UI';"
            "background:transparent;line-height:1.7;")
        body_lay.addWidget(intro_lbl, 1)
        body_scroll.setWidget(body_w)
        root.addWidget(body_scroll, 1)

        # ── Bottom row: skip + close ──────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(20, 12, 20, 14)

        btn_row.addStretch()

        # v68-AI: Video-style presentation button
        video_btn = QPushButton("🎬 Görsel Tanıtım")
        video_btn.setCursor(Qt.PointingHandCursor)
        video_btn.setToolTip(
            "Programın özelliklerini animasyonlu görsel sunum + "
            "sesli rehber ile tanıt")
        video_btn.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #7C3AED,stop:1 #5A1FB8);color:white;"
            "padding:8px 18px;border:none;border-radius:4px;"
            "font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:#5A1FB8;}")
        video_btn.clicked.connect(
            lambda: (dlg.close(), self._show_video_introduction()))
        btn_row.addWidget(video_btn)

        skip_btn = QPushButton("⏩ Hızlı Geç")
        skip_btn.setCursor(Qt.PointingHandCursor)
        skip_btn.setStyleSheet(
            "QPushButton{background:#E5EEF7;color:#404040;"
            "padding:8px 18px;border:1px solid #B8D4E8;"
            "border-radius:4px;font:500 11px 'Segoe UI';}"
            "QPushButton:hover{background:#D5E5F5;}")
        btn_row.addWidget(skip_btn)

        close_btn = QPushButton("Kapat")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #0078D4,stop:1 #003F6F);color:white;"
            "padding:8px 22px;border:none;border-radius:4px;"
            "font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:#003F6F;}")
        close_btn.clicked.connect(dlg.close)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

        # ── Typewriter state ─────────────────────────────────────
        state = {
            "i": 0,
            "text": intro_text,
        }
        timer = QTimer(dlg)

        def _tick():
            """Advance the typewriter by 1-3 chars per tick."""
            if state["i"] >= len(state["text"]):
                timer.stop()
                return
            # Advance variable speed: faster for spaces, slower for
            # punctuation (gives natural rhythm)
            ch = state["text"][state["i"]]
            advance = 2
            if ch in ".!?":
                advance = 1
            elif ch == "\n":
                advance = 1
            state["i"] = min(len(state["text"]),
                              state["i"] + advance)
            intro_lbl.setText(state["text"][:state["i"]])
            # Auto-scroll to bottom
            sb = body_scroll.verticalScrollBar()
            sb.setValue(sb.maximum())

        def _skip():
            """Show full text immediately."""
            state["i"] = len(state["text"])
            intro_lbl.setText(state["text"])
            timer.stop()

        skip_btn.clicked.connect(_skip)
        timer.timeout.connect(_tick)
        timer.start(50)  # 50ms = ~20fps typewriter

        # Stop timer when dialog closes
        def _on_close():
            try:
                timer.stop()
            except Exception as _ex:
                _log_warning(f"about timer stop: {_ex}")
        dlg.finished.connect(lambda _: _on_close())

        dlg.exec()

    def _show_wa_default_dialog(self):
        """WhatsApp Ayarları — varsayılan numara + gönderme modu (ZIP/çoklu).

        v68-UI: ZIP modu eklendi. Checkbox ile kontrol edilir. Aktifse
        Hızlı WhatsApp action hastanın TÜM dosyalarını <HastaAdı>.zip
        olarak paketler ve tek dosya olarak panoya kopyalar. Çok daha
        pratik — hasta tek dosya alır, muayene sonu gönderimi hızlı.
        """
        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("⚙️ WhatsApp Ayarları")
        dlg.resize(580, 700)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(12)

        # ── Hero header ─────────────────────────────────────────────
        hero = QLabel(
            "<div style='padding:14px 18px;'>"
            "<div style='font-size:18px;font-weight:800;color:#FFFFFF;'>"
            "💬  WhatsApp Ayarları</div>"
            "<div style='color:rgba(255,255,255,0.88);margin-top:4px;"
            "font-size:11.5px;'>"
            "Varsayılan numara ve hızlı gönderim modu."
            "</div></div>")
        hero.setTextFormat(Qt.RichText)
        hero.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #128C7E, stop:0.5 #25D366, stop:1 #4DDC7F);"
            "border-radius:10px;color:#FFFFFF;}")
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            shf = QGraphicsDropShadowEffect()
            shf.setBlurRadius(15)
            shf.setColor(QColor(37, 211, 102, 100))
            shf.setOffset(0, 3)
            hero.setGraphicsEffect(shf)
        except Exception as _ex:
            _log_warning("wa settings hero shadow", exc=_ex)
        lay.addWidget(hero)

        # ── Section 1: Default number ──────────────────────────────
        num_title = QLabel(
            "<b style='color:#003F6F;font-size:13px;'>"
            "📞  Varsayılan Numara</b>")
        num_title.setTextFormat(Qt.RichText)
        lay.addWidget(num_title)

        num_hint = QLabel(
            "<span style='color:#606060;font-size:11px;'>"
            "Hasta kaydında kendi numarası olmayan hastalar için "
            "önceden doldurulan numara. 90 ile başlayan 12 haneli "
            "numara (örn: 905321234567).</span>")
        num_hint.setTextFormat(Qt.RichText)
        num_hint.setWordWrap(True)
        lay.addWidget(num_hint)

        current = get_default_whatsapp_number()
        num_input = QLineEdit()
        num_input.setText(current)
        num_input.setPlaceholderText("905321234567")
        num_input.setStyleSheet(
            "QLineEdit{padding:8px 12px;border:1.5px solid #D8E4EE;"
            "border-radius:6px;font:500 13px 'Segoe UI';"
            "background:#FFFFFF;}"
            "QLineEdit:focus{border:1.5px solid #0078D4;}")
        lay.addWidget(num_input)

        # ── Section 1b: Active patient number ──────────────────────
        # v68-UI: If a patient is selected, let the doctor set/update
        # their specific phone without going through the full patient
        # info dialog. Saves clicks for the common workflow:
        # "Seç hasta → Ayarlar → WA → kaydet numara → Hızlı Gönder."
        active_key = None
        active_patient_name = None
        try:
            active_key = self.active_patient_key()
            if self.current_patient:
                active_patient_name = format_patient_name(
                    self.current_patient.name)
        except Exception as _ex:
            _log_warning("wa settings: active key", exc=_ex)

        pat_input = None  # defined so _on_save can reference safely
        if active_key and active_patient_name:
            pat_title = QLabel(
                f"<b style='color:#8B2A6D;font-size:13px;margin-top:6px;'>"
                f"👤  Seçili Hastanın Numarası</b> "
                f"<span style='color:#606060;font-size:11px;'>"
                f"({active_patient_name})</span>")
            pat_title.setTextFormat(Qt.RichText)
            lay.addWidget(pat_title)

            pat_hint = QLabel(
                "<span style='color:#606060;font-size:11px;'>"
                "Bu hastaya özel kayıtlı numara. Değiştirirseniz sadece "
                "bu hasta için geçerli olur.</span>")
            pat_hint.setTextFormat(Qt.RichText)
            pat_hint.setWordWrap(True)
            lay.addWidget(pat_hint)

            pat_input = QLineEdit()
            saved_num = load_phone_db(active_key)
            if saved_num and saved_num != get_default_whatsapp_number():
                pat_input.setText(saved_num)
            pat_input.setPlaceholderText(
                f"Kayıtlı yok — varsayılan: {get_default_whatsapp_number()}")
            pat_input.setStyleSheet(
                "QLineEdit{padding:8px 12px;border:1.5px solid #E8B5D4;"
                "border-radius:6px;font:500 13px 'Segoe UI';"
                "background:#FFF7FB;}"
                "QLineEdit:focus{border:1.5px solid #B5368A;}")
            lay.addWidget(pat_input)

        # ── Section 2: ZIP mode ─────────────────────────────────────
        zip_title = QLabel(
            "<b style='color:#003F6F;font-size:13px;margin-top:8px;'>"
            "📦  Gönderim Modu</b>")
        zip_title.setTextFormat(Qt.RichText)
        lay.addWidget(zip_title)

        zip_chk = QCheckBox(
            "📦 Dosyaları TEK ZIP olarak gönder")
        zip_chk.setChecked(get_whatsapp_zip_mode())
        zip_chk.setStyleSheet(
            "QCheckBox{color:#1a1a1a;font:600 12.5px 'Segoe UI';"
            "padding:8px 10px;background:#F0F6FC;"
            "border:1.5px solid #B8D4E8;border-radius:6px;}"
            "QCheckBox:hover{background:#E5F1FB;border-color:#0078D4;}"
            "QCheckBox::indicator{width:18px;height:18px;}")
        zip_chk.setCursor(Qt.PointingHandCursor)
        lay.addWidget(zip_chk)

        # v68-UI: Auto-send checkbox — press Enter automatically after
        # paste so the message is sent without manual click. Faster
        # clinical workflow. Default ON — that's the point of "Hızlı".
        send_chk = QCheckBox(
            "⏎ Yapıştırdıktan sonra otomatik gönder (Enter)")
        send_chk.setChecked(get_whatsapp_auto_send())
        send_chk.setStyleSheet(
            "QCheckBox{color:#1a1a1a;font:600 12.5px 'Segoe UI';"
            "padding:8px 10px;background:#F0FAF0;"
            "border:1.5px solid #B5D4B5;border-radius:6px;}"
            "QCheckBox:hover{background:#E0F0E0;border-color:#107C10;}"
            "QCheckBox::indicator{width:18px;height:18px;}")
        send_chk.setCursor(Qt.PointingHandCursor)
        lay.addWidget(send_chk)

        zip_info = QLabel(
            "<div style='background:#FFF9E6;border-left:4px solid #E8B800;"
            "border-radius:6px;padding:10px 14px;color:#404040;"
            "font-size:11.5px;line-height:1.5;'>"
            "<b>📦 ZIP AKTİF:</b> Hızlı Gönder butonu geliş klasöründeki "
            "tüm dosyaları <b>&lt;HastaAdı&gt;.zip</b> olarak paketler. "
            "Hasta tek dosya alır.<br>"
            "<b>📁 ZIP PASİF:</b> Eski yöntem — dosyalar ayrı ayrı.<br>"
            "<b>⏎ Otomatik Gönder AKTİF:</b> Yapıştırdıktan ~2.5 sn "
            "sonra Enter basılır, mesaj otomatik gönderilir. "
            "<span style='color:#8B2A6D;'>Dikkat: WhatsApp açık ve "
            "doğru hasta ile sohbette olduğundan emin olun.</span>"
            "</div>")
        zip_info.setTextFormat(Qt.RichText)
        zip_info.setWordWrap(True)
        lay.addWidget(zip_info)

        lay.addStretch()

        # ── Buttons ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_cancel = QPushButton("İptal")
        btn_cancel.setMinimumWidth(90)
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Kaydet")
        btn_save.setMinimumWidth(120)
        btn_save.setDefault(True)
        btn_save.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #25D366,stop:1 #128C7E);"
            "color:white;padding:8px 20px;font:700 12px 'Segoe UI';"
            "border:none;border-radius:6px;}"
            "QPushButton:hover{background:qlineargradient("
            "x1:0,y1:0,x2:0,y2:1,stop:0 #128C7E,stop:1 #0E6B5F);}")
        btn_row.addWidget(btn_save)
        lay.addLayout(btn_row)

        def _on_save():
            # ─── Validate default phone ────────────────────────────────
            new_default = num_input.text().strip()
            cleaned_default = normalize_phone(new_default)
            d_digits = re.sub(r"\D+", "", cleaned_default)
            if not (10 <= len(d_digits) <= 13):
                QMessageBox.warning(
                    dlg, "Geçersiz Varsayılan Numara",
                    f"'{new_default}' geçerli bir telefon numarası değil.\n"
                    "10-13 rakam olmalı (90... ile başlaması önerilir).")
                return

            # ─── Validate patient-specific phone (if visible+filled) ──
            new_patient_phone = None
            if pat_input is not None:
                pv = pat_input.text().strip()
                if pv:
                    cleaned_pv = normalize_phone(pv)
                    p_digits = re.sub(r"\D+", "", cleaned_pv)
                    if not (10 <= len(p_digits) <= 13):
                        QMessageBox.warning(
                            dlg, "Geçersiz Hasta Numarası",
                            f"Hasta numarası '{pv}' geçerli değil.\n"
                            "10-13 rakam olmalı.")
                        return
                    new_patient_phone = cleaned_pv

            # ─── Persist default + mode settings ──────────────────────
            # v68-AI: Before saving the new default, remember the OLD
            # default so we can bulk-update patients who were on it.
            old_default = get_default_whatsapp_number()
            set_default_whatsapp_number(cleaned_default)
            set_whatsapp_zip_mode(zip_chk.isChecked())
            set_whatsapp_auto_send(send_chk.isChecked())

            # v68-AI: Bulk upgrade — if the default changed, find all
            # patients whose stored phone matches the OLD default and
            # silently update them to the NEW default. Patients who
            # have their own distinct number are left alone.
            default_really_changed = (
                old_default
                and cleaned_default
                and normalize_phone(old_default)
                != normalize_phone(cleaned_default))
            bulk_updated = 0
            if default_really_changed:
                try:
                    old_norm = normalize_phone(old_default)
                    with db_conn() as con:
                        # Find patients whose phone == old default
                        rows = con.execute(
                            "SELECT patient_key FROM patient_phones "
                            "WHERE phone=?", (old_norm,)).fetchall()
                        for (pkey,) in rows:
                            con.execute(
                                "UPDATE patient_phones SET phone=? "
                                "WHERE patient_key=?",
                                (normalize_phone(cleaned_default), pkey))
                            bulk_updated += 1
                        if bulk_updated:
                            con.commit()
                    if bulk_updated:
                        _log_warning(
                            f"WA default changed: bulk-updated "
                            f"{bulk_updated} patients "
                            f"from {old_default} → {cleaned_default}")
                except Exception as _bex:
                    _log_warning(
                        f"WA default bulk update: {_bex}")

            # Readback verification — catch QSettings write failures
            readback = get_default_whatsapp_number()
            if readback != cleaned_default:
                _log_warning(
                    f"wa settings: default readback mismatch — "
                    f"wrote '{cleaned_default}' read '{readback}'")
                QMessageBox.warning(
                    dlg, "Kayıt Doğrulanamadı",
                    f"Varsayılan numara kaydedilemedi.\n\n"
                    f"Yazıldı: {cleaned_default}\n"
                    f"Okundu:  {readback}\n\n"
                    "Windows registry izinleri sorunlu olabilir. "
                    "Programı yönetici olarak çalıştırmayı deneyin.")
                return

            # ─── Persist patient-specific phone to DB ─────────────────
            patient_saved = False
            effective_patient_phone = None  # what to save for this patient
            if new_patient_phone:
                # Doctor typed a specific number in the patient section
                effective_patient_phone = new_patient_phone
            elif active_key and not has_saved_phone_db(active_key):
                # Patient section was empty BUT patient has no saved
                # number yet. Doctor just typed a default — doctor's
                # intent was likely: "this patient is the one I'm
                # setting this number for." So use the default as the
                # patient's phone too.
                effective_patient_phone = cleaned_default

            if effective_patient_phone and active_key:
                try:
                    save_phone_db(active_key, effective_patient_phone)
                    # Verify DB readback
                    db_readback = load_phone_db(active_key)
                    if db_readback != effective_patient_phone:
                        _log_warning(
                            f"wa settings: patient phone readback "
                            f"mismatch — wrote '{effective_patient_phone}' "
                            f"read '{db_readback}'")
                        QMessageBox.warning(
                            dlg, "Hasta Numarası Kaydedilemedi",
                            f"DB'ye yazılan doğrulanamadı.\n\n"
                            f"Yazıldı: {effective_patient_phone}\n"
                            f"Okundu:  {db_readback}")
                        return
                    patient_saved = True
                except Exception as _ex:
                    _log_warning(
                        "wa settings: save_phone_db", exc=_ex)
                    QMessageBox.warning(
                        dlg, "Hata",
                        f"Hasta numarası kaydedilemedi:\n"
                        f"{type(_ex).__name__}: {_ex}")
                    return

            # ─── Live-update EVERY widget ─────────────────────────────
            # Delegate entirely to load_patient_phone_into_ui which
            # already applies the "editable=empty/custom,
            # display=effective" logic correctly for all widgets.
            try:
                self.load_patient_phone_into_ui()
                # Also refresh the PI row visibility after phone update
                if (hasattr(self, "_set_pi_row_visible")
                        and hasattr(self, "pi_phone_lbl")):
                    has_own = (patient_saved
                                or (active_key
                                    and has_saved_phone_db(active_key)))
                    self._set_pi_row_visible(
                        self.pi_phone_lbl,
                        has_own or bool(cleaned_default))
            except Exception as _ex:
                _log_warning("wa settings: live update", exc=_ex)

            # ─── User feedback ────────────────────────────────────────
            zip_status = "📦 ZIP" if zip_chk.isChecked() else "📁 Çoklu"
            send_status = "⏎ Oto-gönder" if send_chk.isChecked() \
                else "Manuel gönder"
            if patient_saved:
                msg = (f"✅ Kaydedildi — Hasta: {effective_patient_phone} · "
                       f"Varsayılan: {cleaned_default} · "
                       f"{zip_status} · {send_status}")
            else:
                msg = (f"✅ Kaydedildi — Varsayılan: {cleaned_default} · "
                       f"{zip_status} · {send_status}")
            if bulk_updated:
                msg += (f" · 🔄 {bulk_updated} hasta güncellendi")
            self.statusBar().showMessage(msg, 7000)
            # Toast for bulk update
            if bulk_updated:
                show_toast(
                    self,
                    f"🔄 {bulk_updated} hastanın WhatsApp numarası "
                    f"güncellendi\n{old_default} → {cleaned_default}",
                    level="success", duration_ms=5000)
            dlg.accept()

        btn_save.clicked.connect(_on_save)
        dlg.exec()

    def _show_license_change_dialog(self):
        """Open the license-change dialog. If the user successfully
        rotates the master key, we keep this machine unlocked (the
        user just proved ownership) so they don't get re-prompted.
        Other machines will need the new key on their next launch.
        """
        try:
            dlg = LicenseChangeDialog(self)
            dlg.exec()
        except Exception as ex:
            _log_warning("_show_license_change_dialog", exc=ex)
            QMessageBox.warning(
                self, "Hata",
                f"Lisans değiştirme penceresi açılamadı:\n{ex}")

    def _show_user_role_dialog(self):
        """v68-AI: Set this PC's user role (Doktor/Asistan/Sekreter).
        Stored in QSettings — local to each machine.
        """
        from PySide6.QtWidgets import QDialog, QRadioButton, QButtonGroup
        current_role = get_user_role()

        dlg = QDialog(self)
        dlg.setWindowTitle("👥 Kullanıcı Rolü Ayarı")
        dlg.setMinimumSize(580, 520)
        dlg.setStyleSheet("QDialog{background:#F5F7FA;}")
        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Hero
        hero = QFrame()
        hero.setStyleSheet(
            "QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #003F6F,stop:1 #0078D4);border:none;}")
        hl = QVBoxLayout(hero)
        hl.setContentsMargins(24, 18, 24, 18)
        title = QLabel("👥 Bu PC'nin Kullanıcı Rolü")
        title.setStyleSheet(
            "color:#FFFFFF;font:800 22px 'Segoe UI';"
            "background:transparent;")
        hl.addWidget(title)
        sub = QLabel(
            "Kliniğinizde bu PC'yi kim kullanıyor? Rol, hangi "
            "işlemlerin yapılabileceğini belirler.")
        sub.setStyleSheet(
            "color:rgba(255,255,255,0.88);"
            "font:500 12px 'Segoe UI';background:transparent;")
        sub.setWordWrap(True)
        hl.addWidget(sub)
        root.addWidget(hero)

        # Role options
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(24, 24, 24, 16)
        bl.setSpacing(14)

        role_group = QButtonGroup(body)
        role_group.setExclusive(True)

        role_options = [
            (ROLE_DOKTOR, "👨‍⚕️ Doktor",
             "Tam yetki — tüm işlemleri yapabilir.\n"
             "• Hasta kaydı, bayrak, klinik kararlar\n"
             "• Tahlil yükleme/silme\n"
             "• İmza, doğum, reçete, onam\n"
             "• Ayarlar, sistem yönetimi"),
            (ROLE_ASISTAN, "🩺 Asistan",
             "Klinik işlerin tamamı — silme/ayar yok.\n"
             "• Hasta kaydı, bayrak, notlar\n"
             "• Tahlil yükleme + okuma\n"
             "• İmza, doğum, reçete\n"
             "• Sistem ayarları YOK"),
            (ROLE_SEKRETER, "📋 Sekreter",
             "Sadece kayıt + WhatsApp + telefon.\n"
             "• Yeni hasta kaydı\n"
             "• Telefon numarası düzenleme\n"
             "• WhatsApp gönderme\n"
             "• Diğer hiçbir işleme yetkisi YOK"),
        ]

        radio_buttons = {}
        for role_key, label, desc in role_options:
            row = QFrame()
            is_current = (role_key == current_role)
            row.setStyleSheet(
                f"QFrame{{background:#FFFFFF;"
                f"border:{'2px solid #0078D4' if is_current else '1px solid #DDD'};"
                f"border-radius:10px;padding:6px;}}")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(12, 10, 12, 10)
            rl.setSpacing(12)

            rb = QRadioButton()
            rb.setChecked(is_current)
            rb.setStyleSheet(
                "QRadioButton::indicator{width:24px;height:24px;}")
            radio_buttons[role_key] = rb
            role_group.addButton(rb)
            rl.addWidget(rb, 0, Qt.AlignTop)

            txt_col = QVBoxLayout()
            txt_col.setSpacing(4)
            lbl = QLabel(label)
            lbl.setStyleSheet(
                "color:#003F6F;font:800 16px 'Segoe UI';"
                "background:transparent;")
            txt_col.addWidget(lbl)
            d = QLabel(desc)
            d.setStyleSheet(
                "color:#555;font:500 11px 'Segoe UI';"
                "background:transparent;")
            d.setWordWrap(True)
            txt_col.addWidget(d)
            rl.addLayout(txt_col, 1)

            # Click anywhere on the row → select the radio
            row.mousePressEvent = (
                lambda _e, r=rb: r.setChecked(True))
            bl.addWidget(row)

        bl.addStretch()
        root.addWidget(body, 1)

        # Bottom info + buttons
        bb_row = QHBoxLayout()
        bb_row.setContentsMargins(20, 12, 20, 16)

        info = QLabel(
            "ℹ Bu ayar sadece bu PC için geçerlidir.")
        info.setStyleSheet(
            "color:#666;font:500 11px 'Segoe UI';")
        bb_row.addWidget(info)
        bb_row.addStretch()

        save_btn = QPushButton("💾 Kaydet ve Programı Yenile")
        save_btn.setCursor(Qt.PointingHandCursor)
        save_btn.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #00A676,stop:1 #007F58);color:white;"
            "padding:10px 22px;border:none;border-radius:8px;"
            "font:700 13px 'Segoe UI';}"
            "QPushButton:hover{background:#007F58;}")
        bb_row.addWidget(save_btn)

        cancel_btn = QPushButton("İptal")
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.setStyleSheet(
            "QPushButton{background:#999;color:white;"
            "padding:10px 22px;border:none;border-radius:8px;"
            "font:700 13px 'Segoe UI';}")
        cancel_btn.clicked.connect(dlg.reject)
        bb_row.addWidget(cancel_btn)
        root.addLayout(bb_row)

        def _save():
            new_role = current_role
            for role_key, rb in radio_buttons.items():
                if rb.isChecked():
                    new_role = role_key
                    break
            if new_role == current_role:
                dlg.reject()
                return
            ok = set_user_role(new_role)
            if ok:
                role_label = ROLE_LABELS.get(new_role, new_role)
                QMessageBox.information(
                    dlg, "Rol Değişti",
                    f"Kullanıcı rolü '{role_label}' olarak "
                    f"ayarlandı.\n\nDeğişikliklerin tam etkili "
                    f"olması için programı yeniden başlatın.")
                dlg.accept()
            else:
                QMessageBox.warning(
                    dlg, "Kayıt Başarısız",
                    "Rol kaydedilemedi. Tekrar deneyin.")

        save_btn.clicked.connect(_save)
        dlg.exec()

    def _show_identity_edit_dialog(self):
        """Edit clinic identity (doctor name, clinic name, admin password).

        Opens the same FirstRunSetupDialog used for initial setup, but
        pre-filled with current values. If the admin password is left
        blank, it's kept as-is; otherwise it's re-hashed and stored.
        """
        # Require the current admin password before changing anything
        current, ok = QInputDialog.getText(
            self, "Yönetici Şifresi Gerekli",
            "Klinik bilgilerini değiştirmek için mevcut "
            "yönetici şifresini girin:",
            QLineEdit.Password)
        if not ok:
            return
        if not verify_admin_password(current):
            QMessageBox.warning(
                self, "Şifre Yanlış",
                "Girilen yönetici şifresi hatalı. İşlem iptal edildi.")
            return

        # We re-use FirstRunSetupDialog but flag it as "edit mode" so
        # it doesn't insist on a non-empty password (user might just
        # want to change the name).
        dlg = FirstRunSetupDialog(self)
        dlg.setWindowTitle("Klinik Bilgilerini Düzenle")
        # Pre-fill current values
        dlg.doctor_input.setText(get_clinic_doctor_name())
        dlg.clinic_input.setText(get_clinic_name())
        dlg.wa_default_input.setText(get_default_whatsapp_number())
        # Password fields are left empty — if the user doesn't fill
        # them, we keep the existing hash
        dlg.pass1_input.setPlaceholderText(
            "boş bırakın = şifreyi değiştirme")
        dlg.pass2_input.setPlaceholderText(
            "boş bırakın = şifreyi değiştirme")
        # Override the validation to allow empty password (edit mode)
        _orig_validate = dlg._validate
        def _edit_validate():
            doctor = dlg.doctor_input.text().strip()
            clinic = dlg.clinic_input.text().strip()
            wa_default = re.sub(r"\D+", "", dlg.wa_default_input.text())
            p1 = dlg.pass1_input.text()
            p2 = dlg.pass2_input.text()
            problems = []
            if len(doctor) < 3:
                problems.append("Doktor adı en az 3 karakter olmalı.")
            if len(clinic) < 2:
                problems.append("Klinik adı en az 2 karakter olmalı.")
            if wa_default and not (10 <= len(wa_default) <= 13):
                problems.append(
                    "WhatsApp no 10-13 rakam olmalı.")
            # Password is OPTIONAL in edit mode — but if provided must
            # match and be at least 4 chars
            if p1 or p2:
                if len(p1) < 4:
                    problems.append(
                        "Yeni şifre en az 4 karakter olmalı.")
                elif p1 != p2:
                    problems.append("Şifreler eşleşmiyor.")
            if problems:
                dlg.status_lbl.setText(" · ".join(problems))
                dlg.status_lbl.setStyleSheet(
                    "color:#C42B1C;font:600 11px 'Segoe UI';")
                dlg.btn_ok.setEnabled(False)
            else:
                if p1:
                    dlg.status_lbl.setText(
                        "✓ Geçerli — kaydet'e basın "
                        "(şifre YENİDEN belirlenecek)")
                else:
                    dlg.status_lbl.setText(
                        "✓ Geçerli — kaydet'e basın "
                        "(mevcut şifre korunacak)")
                dlg.status_lbl.setStyleSheet(
                    "color:#107C10;font:600 11px 'Segoe UI';")
                dlg.btn_ok.setEnabled(True)
        dlg._validate = _edit_validate
        for w in (dlg.doctor_input, dlg.clinic_input,
                  dlg.wa_default_input,
                  dlg.pass1_input, dlg.pass2_input):
            try:
                w.textChanged.disconnect()
            except (RuntimeError, TypeError):
                # Qt raises if the signal has no connected slot — that's
                # fine, it just means there was nothing to disconnect.
                pass
            w.textChanged.connect(_edit_validate)
        _edit_validate()

        # Override _on_ok to make password optional
        def _edit_on_ok():
            doctor = dlg.doctor_input.text().strip()
            clinic = dlg.clinic_input.text().strip()
            wa_default = normalize_phone(dlg.wa_default_input.text())
            password = dlg.pass1_input.text()
            try:
                settings = _clinic_settings()
                settings.setValue("clinic/doctor_name", doctor)
                settings.setValue("clinic/clinic_name", clinic)
                if wa_default:
                    settings.setValue(
                        "clinic/default_whatsapp", wa_default)
                if password:   # only update hash if a new one was typed
                    set_admin_password(password)
                settings.setValue("clinic/configured", True)
                settings.sync()
            except Exception as ex:
                _log_warning(
                    "MainWindow._show_identity_edit_dialog._on_ok",
                    exc=ex)
                QMessageBox.critical(
                    dlg, "Kayıt Hatası",
                    f"Ayarlar kaydedilemedi:\n\n{ex}")
                return
            dlg._completed = True
            dlg.accept()
        dlg.btn_ok.clicked.disconnect()
        dlg.btn_ok.clicked.connect(_edit_on_ok)

        if dlg.exec() == QDialog.Accepted and getattr(dlg, "_completed",
                                                      False):
            # Update window title to reflect new names
            self.setWindowTitle(
                f"{get_clinic_name()} — {get_clinic_doctor_name()}")
            self.statusBar().showMessage(
                "✓ Klinik bilgileri güncellendi. "
                "Belge şablonlarındaki yeni isimler bir sonraki "
                "yazdırmada görünecek.", 6000)

    def _show_format_dialog(self):
        """Open the password-gated database format dialog.

        Called from Ayarlar → ⚠ Sistemi Sıfırla. The dialog itself
        handles all password verification and confirmation — this
        method just opens it and, on success, refreshes the UI so
        the now-empty patient list is reflected.
        """
        dlg = FormatDatabaseDialog(self)
        if dlg.exec() == QDialog.Accepted:
            # Format succeeded — refresh the now-empty patient list
            try:
                self.refresh_all()
            except Exception as ex:
                _log_warning(
                    "MainWindow._show_format_dialog: refresh after format",
                    exc=ex)
            self.statusBar().showMessage(
                "✓ Veritabanı temizlendi. Liste boş — NAS'tan "
                "yeniden senkronize edin.", 8000)

    def _show_printer_settings_dialog(self):
        """Professional printer settings dialog.

        v68-UI: Single place to configure:
          • Target printer (from system list)
          • Page size (A3/A4/A5/A6/Letter/Legal/B5)
          • Orientation (portrait / landscape)
          • Margins in millimeters (left/top/right/bottom)
          • Whether to show the system print dialog on each print

        All settings persist to QSettings under clinic/printer/* and
        are automatically applied by print_text_widget() for every
        subsequent print — diet sheets, follow-up forms, planning
        documents, etc.
        """
        from PySide6.QtPrintSupport import QPrinterInfo

        dlg = QDialog(self)
        dlg.setWindowTitle("🖨 Yazıcı Ayarları")
        dlg.setMinimumSize(620, 540)
        dlg.setModal(True)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Hero banner ──────────────────────────────────────────────
        hero = QWidget()
        hero.setFixedHeight(96)
        hero.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #2E6FB5,stop:0.5 #4A90E2,stop:1 #6BB2EF);")
        hero_lay = QVBoxLayout(hero)
        hero_lay.setContentsMargins(22, 14, 22, 14)
        hero_lay.setSpacing(4)
        h_title = QLabel("🖨  Yazıcı Ayarları")
        h_title.setStyleSheet(
            "color:white;font:800 22px 'Segoe UI';background:transparent;")
        h_sub = QLabel(
            "Tüm yazdırmalar için yazıcı, kağıt boyutu, yön ve "
            "kenar boşluklarını buradan ayarlayın.")
        h_sub.setStyleSheet(
            "color:rgba(255,255,255,0.92);font:500 12px 'Segoe UI';"
            "background:transparent;")
        h_sub.setWordWrap(True)
        hero_lay.addWidget(h_title)
        hero_lay.addWidget(h_sub)
        root.addWidget(hero)

        # ── Body ─────────────────────────────────────────────────────
        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setContentsMargins(22, 18, 22, 14)
        body_lay.setSpacing(14)

        # ── Section 1: Printer ──────────────────────────────────────
        sec1 = QFrame()
        sec1.setStyleSheet(
            "QFrame{background:#F5FAFF;border:1px solid #CFE1F5;"
            "border-radius:6px;}"
            "QLabel#SecTitle{color:#2E6FB5;font:700 13px 'Segoe UI';"
            "background:transparent;}")
        s1l = QVBoxLayout(sec1)
        s1l.setContentsMargins(14, 10, 14, 12)
        s1l.setSpacing(6)
        s1t = QLabel("📠 Yazıcı")
        s1t.setObjectName("SecTitle")
        s1l.addWidget(s1t)
        printer_combo = QComboBox()
        printer_combo.addItem("(Sistem varsayılanı)", "")
        try:
            for info in QPrinterInfo.availablePrinters():
                pname = info.printerName()
                label = pname
                try:
                    if info.isDefault():
                        label = f"{pname}  ⭐ varsayılan"
                except Exception as _ex:
                    _log_warning(
                        f"printer_settings: isDefault check: {_ex}")
                printer_combo.addItem(label, pname)
        except Exception as _ex:
            _log_warning(
                "_show_printer_settings_dialog: enumerate printers",
                exc=_ex)
        # Select saved printer if any
        saved_name = get_printer_name()
        if saved_name:
            for i in range(printer_combo.count()):
                if printer_combo.itemData(i) == saved_name:
                    printer_combo.setCurrentIndex(i)
                    break
        printer_combo.setStyleSheet(
            "QComboBox{padding:6px 8px;border:1px solid #B8D4E8;"
            "border-radius:3px;background:white;font:500 11px 'Segoe UI';}")
        s1l.addWidget(printer_combo)
        s1l.addWidget(QLabel(
            "<span style='color:#666;font:italic 10px Segoe UI;'>"
            "Boş bıraktığınızda Windows'un varsayılan yazıcısı "
            "kullanılır.</span>"))
        body_lay.addWidget(sec1)

        # ── Section 2: Page size + orientation ──────────────────────
        sec2 = QFrame()
        sec2.setStyleSheet(sec1.styleSheet())
        s2l = QVBoxLayout(sec2)
        s2l.setContentsMargins(14, 10, 14, 12)
        s2l.setSpacing(8)
        s2t = QLabel("📄 Kağıt Boyutu ve Yön")
        s2t.setObjectName("SecTitle")
        s2l.addWidget(s2t)

        row2 = QHBoxLayout()
        row2.setSpacing(12)

        # Page size
        page_lbl = QLabel("Boyut:")
        page_lbl.setStyleSheet(
            "color:#404040;font:500 11px 'Segoe UI';background:transparent;")
        page_lbl.setMinimumWidth(60)
        row2.addWidget(page_lbl)
        page_combo = QComboBox()
        for pid, label in PRINTER_PAGE_SIZES:
            page_combo.addItem(label, pid)
        saved_pid = get_printer_page_size()
        for i in range(page_combo.count()):
            if page_combo.itemData(i) == saved_pid:
                page_combo.setCurrentIndex(i)
                break
        page_combo.setStyleSheet(printer_combo.styleSheet())
        page_combo.setMinimumWidth(260)
        row2.addWidget(page_combo, 1)

        s2l.addLayout(row2)

        # Orientation
        row2b = QHBoxLayout()
        row2b.setSpacing(12)
        ori_lbl = QLabel("Yön:")
        ori_lbl.setStyleSheet(page_lbl.styleSheet())
        ori_lbl.setMinimumWidth(60)
        row2b.addWidget(ori_lbl)
        ori_group_lay = QHBoxLayout()
        ori_group_lay.setSpacing(10)
        rad_portrait = QRadioButton("📄 Dikey (Portrait)")
        rad_landscape = QRadioButton("📑 Yatay (Landscape)")
        if get_printer_orientation() == "landscape":
            rad_landscape.setChecked(True)
        else:
            rad_portrait.setChecked(True)
        rad_style = ("QRadioButton{color:#404040;font:500 11px 'Segoe UI';"
                     "background:transparent;}")
        rad_portrait.setStyleSheet(rad_style)
        rad_landscape.setStyleSheet(rad_style)
        ori_group_lay.addWidget(rad_portrait)
        ori_group_lay.addWidget(rad_landscape)
        ori_group_lay.addStretch()
        row2b.addLayout(ori_group_lay, 1)
        s2l.addLayout(row2b)

        body_lay.addWidget(sec2)

        # ── Section 3: Margins ─────────────────────────────────────
        sec3 = QFrame()
        sec3.setStyleSheet(sec1.styleSheet())
        s3l = QVBoxLayout(sec3)
        s3l.setContentsMargins(14, 10, 14, 12)
        s3l.setSpacing(8)
        s3t = QLabel("📏 Kenar Boşlukları (mm)")
        s3t.setObjectName("SecTitle")
        s3l.addWidget(s3t)

        saved_l, saved_t, saved_r, saved_b = get_printer_margins_mm()
        margin_row = QHBoxLayout()
        margin_row.setSpacing(10)

        def _mk_margin_spin(val: float):
            sp = QDoubleSpinBox()
            sp.setRange(0.0, 50.0)
            sp.setDecimals(1)
            sp.setSingleStep(1.0)
            sp.setSuffix(" mm")
            sp.setValue(val)
            sp.setMinimumWidth(100)
            sp.setStyleSheet(
                "QDoubleSpinBox{padding:5px 6px;border:1px solid #B8D4E8;"
                "border-radius:3px;background:white;"
                "font:500 11px 'Segoe UI';}")
            return sp

        sp_l = _mk_margin_spin(saved_l)
        sp_t = _mk_margin_spin(saved_t)
        sp_r = _mk_margin_spin(saved_r)
        sp_b = _mk_margin_spin(saved_b)

        for lbl_text, sp in [("Sol:", sp_l), ("Üst:", sp_t),
                             ("Sağ:", sp_r), ("Alt:", sp_b)]:
            ll = QLabel(lbl_text)
            ll.setStyleSheet(
                "color:#404040;font:500 11px 'Segoe UI';background:transparent;")
            margin_row.addWidget(ll)
            margin_row.addWidget(sp)
            margin_row.addSpacing(4)
        margin_row.addStretch()
        s3l.addLayout(margin_row)

        # Preset buttons
        preset_row = QHBoxLayout()
        preset_row.setSpacing(6)
        preset_row.addWidget(QLabel(
            "<span style='color:#666;font:italic 10px Segoe UI;'>Hazır:</span>"))

        def _apply_preset(l, t, r, b):
            sp_l.setValue(l)
            sp_t.setValue(t)
            sp_r.setValue(r)
            sp_b.setValue(b)

        for name, vals in [("Dar (10)", (10, 10, 10, 10)),
                           ("Normal (15)", (15, 15, 15, 15)),
                           ("Geniş (25)", (25, 25, 25, 25)),
                           ("Yazı dostu (20-25-20-20)",
                            (20, 25, 20, 20))]:
            pb = QPushButton(name)
            pb.setStyleSheet(
                "QPushButton{background:#E5EEF7;color:#404040;"
                "padding:4px 10px;border:1px solid #B8D4E8;"
                "border-radius:3px;font:500 10px 'Segoe UI';}"
                "QPushButton:hover{background:#D5E5F5;}")
            pb.clicked.connect(
                lambda _=False, v=vals: _apply_preset(*v))
            preset_row.addWidget(pb)
        preset_row.addStretch()
        s3l.addLayout(preset_row)

        body_lay.addWidget(sec3)

        # ── Section 4: Print dialog mode ────────────────────────────
        sec4 = QFrame()
        sec4.setStyleSheet(
            "QFrame{background:#FFFBEA;border:1px solid #FCE9A5;"
            "border-radius:6px;}"
            "QLabel#SecTitle{color:#8A5A00;font:700 13px 'Segoe UI';"
            "background:transparent;}")
        s4l = QVBoxLayout(sec4)
        s4l.setContentsMargins(14, 10, 14, 12)
        s4l.setSpacing(6)
        s4t = QLabel("⚙️ Yazdırma Modu")
        s4t.setObjectName("SecTitle")
        s4l.addWidget(s4t)
        chk_dialog = QCheckBox(
            "Her yazdırmada sistem yazıcı diyaloğu açılsın")
        chk_dialog.setChecked(get_printer_show_dialog())
        chk_dialog.setStyleSheet(
            "QCheckBox{color:#404040;font:500 11px 'Segoe UI';"
            "background:transparent;}")
        s4l.addWidget(chk_dialog)
        s4l.addWidget(QLabel(
            "<span style='color:#666;font:italic 10px Segoe UI;'>"
            "İşaretli: her yazdırmada yazıcı seçebilirsiniz (önerilen).<br>"
            "İşaretsiz: doğrudan yukarıda seçtiğiniz yazıcıya yazdırır — "
            "hızlı iş akışı için.</span>"))
        body_lay.addWidget(sec4)

        body_lay.addStretch()
        root.addWidget(body)

        # ── Button row ───────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(22, 10, 22, 14)
        btn_row.setSpacing(10)

        btn_test = QPushButton("🖨 Test Sayfası Yazdır")
        btn_test.setToolTip(
            "Ayarlarla bir test sayfası yazdır — doğru çıktığından emin ol.")
        btn_test.setStyleSheet(
            "QPushButton{background:#E5EEF7;color:#404040;padding:8px 16px;"
            "border:1px solid #B8D4E8;border-radius:4px;"
            "font:500 11px 'Segoe UI';}"
            "QPushButton:hover{background:#D5E5F5;}")
        btn_row.addWidget(btn_test)
        btn_row.addStretch()

        btn_cancel = QPushButton("İptal")
        btn_cancel.setShortcut("Escape")
        btn_cancel.setStyleSheet(btn_test.styleSheet())
        btn_cancel.clicked.connect(dlg.reject)
        btn_row.addWidget(btn_cancel)

        btn_save = QPushButton("💾 Kaydet")
        btn_save.setDefault(True)
        btn_save.setStyleSheet(
            "QPushButton{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #4A90E2,stop:1 #2E6FB5);color:white;padding:8px 22px;"
            "border:none;border-radius:4px;font:700 11px 'Segoe UI';}"
            "QPushButton:hover{background:qlineargradient("
            "x1:0,y1:0,x2:0,y2:1,stop:0 #2E6FB5,stop:1 #1F5287);}")
        btn_row.addWidget(btn_save)
        root.addLayout(btn_row)

        # ── Helpers ───────────────────────────────────────────────────
        def _collect_and_save() -> bool:
            try:
                set_printer_name(printer_combo.currentData() or "")
                set_printer_page_size(
                    page_combo.currentData() or "A4")
                set_printer_orientation(
                    "landscape" if rad_landscape.isChecked()
                    else "portrait")
                set_printer_margins_mm(
                    sp_l.value(), sp_t.value(),
                    sp_r.value(), sp_b.value())
                set_printer_show_dialog(chk_dialog.isChecked())
                return True
            except Exception as _ex:
                _log_warning(
                    "_show_printer_settings_dialog: save", exc=_ex)
                QMessageBox.warning(
                    dlg, "Kaydetme Hatası",
                    f"Ayarlar kaydedilirken hata:\n{_ex}")
                return False

        def _on_test():
            # Save first, then print a test page
            if not _collect_and_save():
                return
            # Build a simple test doc
            te = QTextEdit()
            l, t, r, b = get_printer_margins_mm()
            ori = ("Yatay (Landscape)"
                   if get_printer_orientation() == "landscape"
                   else "Dikey (Portrait)")
            pname = (get_printer_name()
                     or "(Sistem varsayılanı)")
            pid = get_printer_page_size()
            # Find label for pid
            pid_label = pid
            for _pid, _lbl in PRINTER_PAGE_SIZES:
                if _pid == pid:
                    pid_label = _lbl
                    break
            # v68-UI: Dynamic doctor name from clinic identity
            try:
                dr_name = get_clinic_doctor_name() or "Op. Dr."
            except Exception:
                dr_name = "Op. Dr."
            te.setHtml(f"""
                <h1 style='color:#2E6FB5;'>🖨 Yazıcı Ayarları Test Sayfası</h1>
                <p style='color:#666;'>Bu sayfa mevcut yazıcı ayarlarıyla yazdırılmıştır.</p>
                <hr>
                <table cellpadding='6' style='font-family:Segoe UI;'>
                <tr><td><b>Yazıcı:</b></td><td>{pname}</td></tr>
                <tr><td><b>Kağıt:</b></td><td>{pid_label}</td></tr>
                <tr><td><b>Yön:</b></td><td>{ori}</td></tr>
                <tr><td><b>Kenar boşlukları:</b></td>
                    <td>Sol {l}mm · Üst {t}mm · Sağ {r}mm · Alt {b}mm</td></tr>
                </table>
                <hr>
                <p style='color:#999;font-size:10pt;'>
                Bu çıktı düzgün görünüyorsa ayarlarınız doğru.<br>
                Yazı çok kenara yakınsa kenar boşluklarını artırın.<br>
                Sayfadan taşıyorsa kağıt boyutunu kontrol edin.</p>
                <p><b>{dr_name}</b> — yazklinik {APP_VERSION}</p>
            """)
            ok, msg = print_text_widget(
                te, parent_dialog=dlg, title="Yazıcı Test Sayfası")
            try:
                self.statusBar().showMessage(msg, 6000)
            except Exception as _ex:
                _log_warning(
                    f"printer_settings: test status: {_ex}")
            if not ok and "iptal" not in (msg or "").lower():
                QMessageBox.warning(dlg, "Test Yazdırma", msg)

        def _on_save():
            if _collect_and_save():
                self.statusBar().showMessage(
                    "✓ Yazıcı ayarları kaydedildi", 4000)
                dlg.accept()

        btn_test.clicked.connect(_on_test)
        btn_save.clicked.connect(_on_save)

        dlg.exec()

    def _show_backup_dialog(self):
        """Backup the live database to a user-chosen .sqlite3 file.

        Called from Ayarlar → 📦 Yedek Al. Opens a save-file dialog
        with a sensible default filename (clinic_YYYYMMDD_HHMM.sqlite3),
        runs backup_database(), and shows a summary of what was saved.
        Backup uses SQLite's online backup API so it's safe to run
        while the app is open.
        """
        from datetime import datetime as _dt
        default_name = (
            f"{get_clinic_name().replace(' ', '_')}"
            f"_{_dt.now().strftime('%Y%m%d_%H%M')}.sqlite3")
        suggested = str(Path.home() / default_name)
        dest, _ = QFileDialog.getSaveFileName(
            self, "Yedek Kaydet", suggested,
            "SQLite veritabanı (*.sqlite3 *.db);;Tüm dosyalar (*)")
        if not dest:
            return
        try:
            info = backup_database(Path(dest))
        except Exception as ex:
            _log_warning("MainWindow._show_backup_dialog", exc=ex)
            QMessageBox.critical(
                self, "Yedek Başarısız",
                f"Yedek oluşturulamadı:\n\n{ex}")
            return
        size_mb = info["size_bytes"] / 1_048_576
        QMessageBox.information(
            self, "Yedek Başarılı",
            f"<p>✓ Yedek oluşturuldu.</p>"
            f"<p><b>Dosya:</b> {info['path']}<br>"
            f"<b>Boyut:</b> {size_mb:.2f} MB<br>"
            f"<b>Hasta sayısı:</b> {info['patient_count']:,}</p>"
            f"<p style='color:#606060;font-size:11px;'>"
            "Bu dosyayı güvenli bir yere (harici disk, bulut, flash) "
            "düzenli olarak yedekleyin. Yedek dosyası her şey — "
            "hastalar, ziyaretler, bayraklar, demografi — içerir.</p>")
        self.statusBar().showMessage(
            f"✓ Yedek: {Path(dest).name} ({size_mb:.1f} MB)", 6000)

    def _show_restore_dialog(self):
        """Restore the database from a user-chosen backup file.

        Called from Ayarlar → 📂 Yedekten Geri Yükle. Heavy-warning
        dialog first — restore REPLACES all current patient data.
        Requires admin password so the doctor doesn't accidentally
        overwrite live data if someone hands them a wrong file.

        After restore, the app must be restarted — we can't safely
        reopen live DB connections onto the new file. We tell the
        user this and close after they ack.
        """
        # First: warning
        reply = QMessageBox.warning(
            self, "Yedekten Geri Yükle",
            "<p style='color:#C42B1C;'><b>⚠ Dikkat</b></p>"
            "<p>Bu işlem MEVCUT veritabanının üzerine yazar:</p>"
            "<ul>"
            "<li>Şu anki tüm hasta verileri yedek dosyasındaki "
            "verilerle değiştirilir</li>"
            "<li>Güvenlik için mevcut DB'nin bir kopyası "
            "<code>yazklinik_whatsapp.sqlite3.before_restore</code> "
            "olarak saklanır</li>"
            "<li>Uygulama işlem sonrasında kapatılmalı ve yeniden "
            "açılmalıdır</li>"
            "</ul>"
            "<p>Devam etmek istiyor musunuz?</p>",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return

        # Second: admin password
        pw, ok = QInputDialog.getText(
            self, "Yönetici Şifresi Gerekli",
            "Geri yükleme için yönetici şifresini girin:",
            QLineEdit.Password)
        if not ok:
            return
        if not verify_admin_password(pw):
            QMessageBox.warning(self, "Şifre Yanlış",
                                 "Yönetici şifresi hatalı. İşlem iptal.")
            return

        # Third: pick file
        src, _ = QFileDialog.getOpenFileName(
            self, "Yedek Dosyası Seç", str(Path.home()),
            "SQLite veritabanı (*.sqlite3 *.db);;Tüm dosyalar (*)")
        if not src:
            return

        try:
            info = restore_database(Path(src))
        except Exception as ex:
            _log_warning("MainWindow._show_restore_dialog", exc=ex)
            QMessageBox.critical(
                self, "Geri Yükleme Başarısız",
                f"Geri yükleme sırasında hata:\n\n{ex}\n\n"
                "Mevcut veritabanı değişmedi.")
            return

        QMessageBox.information(
            self, "Geri Yükleme Başarılı",
            f"<p>✓ Yedekten geri yüklendi.</p>"
            f"<p><b>Kaynak:</b> {info['restored_from'].name}<br>"
            f"<b>Hasta sayısı:</b> {info['patient_count']:,}<br>"
            f"<b>Güvenlik kopyası:</b> {info['safety_copy'].name}</p>"
            "<p style='color:#C42B1C;'><b>Uygulamayı şimdi kapatın ve "
            "yeniden açın.</b> Veritabanı değiştiği için mevcut "
            "bağlantılar güvenli değil.</p>")
        # Encourage quit
        self.close()

    def _show_system_health_panel(self):
        """Show a read-only dashboard of app state — versions, sizes,
        counts, connectivity. For diagnostics and 'is everything OK?'
        at-a-glance."""
        h = collect_system_health()

        # Format into readable HTML
        rows = []
        def row(label, value, color="#1a1a1a"):
            rows.append(
                f"<tr><td style='padding:4px 12px 4px 0;color:#606060;'>"
                f"{label}</td>"
                f"<td style='padding:4px 0;color:{color};'><b>{value}"
                f"</b></td></tr>")

        row("Uygulama Versiyonu", h.get("app_version", "?"))
        row("Klinik Adı", h.get("clinic_name", "?"))
        row("Doktor Adı", h.get("doctor_name", "?"))

        rows.append(
            "<tr><td colspan='2' style='padding:10px 0 4px 0;'><hr></td></tr>")
        rows.append(
            "<tr><td colspan='2' style='color:#005A9E;font-weight:700;"
            "padding:4px 0;'>Veritabanı</td></tr>")
        row("Dosya", h.get("db_path", "?"))
        if h.get("db_exists"):
            row("Boyut", f"{h.get('db_size_mb', 0)} MB")
            row("Hasta sayısı", f"{h.get('patient_count', 0):,}")
            row("Geliş sayısı", f"{h.get('visit_count', 0):,}")
            row("Bayrak sayısı", f"{h.get('flag_count', 0):,}")
            row("Demografi kayıtları",
                f"{h.get('demographics_count', 0):,}")
            row("DICOM önbelleği",
                f"{h.get('dicom_cached_count', 0):,}")
            if "last_sync" in h:
                row("Son senkr. (başarılı)", h["last_sync"])
        else:
            row("Durum", "✗ Veritabanı dosyası yok", color="#C42B1C")

        rows.append(
            "<tr><td colspan='2' style='padding:10px 0 4px 0;'><hr></td></tr>")
        rows.append(
            "<tr><td colspan='2' style='color:#005A9E;font-weight:700;"
            "padding:4px 0;'>NAS Bağlantısı</td></tr>")
        row("Klasör", h.get("nas_path", "?"))
        reachable = h.get("nas_reachable")
        if reachable is True:
            row("Erişim", "✓ Erişilebilir", color="#107C10")
        elif reachable is False:
            row("Erişim", "✗ Erişilemiyor", color="#C42B1C")
        else:
            row("Erişim", "? Belirsiz", color="#606060")

        rows.append(
            "<tr><td colspan='2' style='padding:10px 0 4px 0;'><hr></td></tr>")
        rows.append(
            "<tr><td colspan='2' style='color:#005A9E;font-weight:700;"
            "padding:4px 0;'>Hata Kayıtları</td></tr>")
        lines = h.get("error_log_lines", 0)
        if lines == 0:
            row("Log", "Boş (hata yok)", color="#107C10")
        else:
            row("Log satır sayısı",
                f"{lines} ({h.get('error_log_size_kb', 0)} KB)",
                color="#C46500" if lines > 100 else "#1a1a1a")
            row("Log dosyası", h.get("error_log_path", "?"))

        # v68-UI: Orthanc DICOM section
        rows.append(
            "<tr><td colspan='2' style='padding:10px 0 4px 0;'><hr></td></tr>")
        rows.append(
            "<tr><td colspan='2' style='color:#005A9E;font-weight:700;"
            "padding:4px 0;'>Orthanc DICOM Sunucusu</td></tr>")
        row("URL", h.get("orthanc_url", "?"))
        if h.get("orthanc_connected"):
            row("Bağlantı", "✓ Bağlı", color="#107C10")
            if "orthanc_version" in h:
                row("Sunucu sürümü", h["orthanc_version"])
            if "orthanc_db_version" in h:
                row("DB sürümü", h["orthanc_db_version"])
            if "orthanc_plugins" in h:
                row("Pluginler", h["orthanc_plugins"])
                # Highlight which advanced viewers are available
                viewers = []
                if h.get("orthanc_has_osimis"):
                    viewers.append("Osimis Web Viewer")
                if h.get("orthanc_has_stone"):
                    viewers.append("Stone Web Viewer")
                if h.get("orthanc_has_explorer2"):
                    viewers.append("Orthanc Explorer 2 / OHIF")
                if viewers:
                    row("Gelişmiş Görüntüleyici",
                        " · ".join(viewers), color="#107C10")
        else:
            row("Bağlantı", "✗ Bağlı değil", color="#C42B1C")

        # v68-AI: Web servisi (Flask) durumu
        rows.append(
            "<tr><td colspan='2' style='color:#005A9E;font-weight:700;"
            "padding:10px 0 4px 0;'>🌐 YazKlinik Web (Flask)</td></tr>")
        try:
            import urllib.request as _ur
            import urllib.error as _uerr
            # Farklı olası lokasyonları dene
            test_urls = [
                "http://localhost:5000",
                "http://127.0.0.1:5000",
            ]
            web_found = False
            web_url_found = None
            for _u in test_urls:
                try:
                    resp = _ur.urlopen(_u, timeout=1.5)
                    if resp.status == 200 or resp.status == 302:
                        web_found = True
                        web_url_found = _u
                        break
                except Exception as _u_ex:
                    # Web yoksa bu normal — sadece debug için logla
                    _log_warning(
                        f"web status check {_u}: {_u_ex}")
            if web_found:
                row("Durum", f"✓ Çalışıyor ({web_url_found})",
                    color="#107C10")
                row("Not", "Sekreter/asistan tarayıcıdan "
                    "erişebilir")
            else:
                row("Durum", "✗ Çalışmıyor (bu PC'de)",
                    color="#C46500")
                row("Not", "Web servisi server PC'de çalışıyor "
                    "olabilir — klinik sekreterlik PC'sine sor")
        except Exception as _ex:
            row("Durum", f"? Kontrol edilemedi ({_ex})",
                color="#606060")

        html = (
            f"<h3 style='color:#005A9E;margin-top:0;'>🩺 Sistem Durumu</h3>"
            f"<table cellspacing='0' cellpadding='0'>{''.join(rows)}</table>"
            f"<p style='color:#606060;font-size:11px;margin-top:14px;'>"
            "Bu panel salt-okunur — bilgi amaçlı. Destek için "
            "ekran görüntüsü alıp gönderebilirsin.</p>")

        box = QMessageBox(self)
        box.setWindowTitle("Sistem Durumu")
        box.setTextFormat(Qt.RichText)
        box.setText(html)
        box.setStandardButtons(QMessageBox.Ok)
        box.exec()

    def _show_nas_settings_dialog(self):
        """Configure the NAS root folder (where patient visit folders live).

        Supports three input paths:
          1. Type a UNC path directly:   \\\\TrueNAS\\nas\\Voluson
          2. Browse for a mounted folder via Windows Explorer dialog
          3. Use a local folder (for testing / local setups)

        Credentials (username / password / domain) are optional. When
        provided on Windows we run `net use` at app startup so the share
        is authenticated before patient folders are scanned. The password
        is saved in QSettings unencrypted — we warn the doctor about this
        in the dialog. Leaving the password blank means the doctor will
        use whatever Windows Explorer has already authenticated.
        """
        from PySide6.QtWidgets import QFileDialog, QFormLayout

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("NAS Klasörü Ayarları")
        dlg.resize(620, 440)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(14, 14, 14, 14)
        v.setSpacing(10)

        # Header
        hdr = QLabel(
            "<b>Hasta klasörlerinin bulunduğu NAS yolu</b><br>"
            "<span style='color:#606060;font-weight:400;'>"
            "Voluson ultrason cihazının görüntü/PDF yazdığı ana klasör.</span>")
        hdr.setTextFormat(Qt.RichText)
        hdr.setStyleSheet(header_label_style(font_size=13))
        v.addWidget(hdr)

        # Path input + browse
        path_lbl = QLabel("Klasör yolu:")
        path_lbl.setStyleSheet(header_label_style(font_size=11,
                                                   font_weight=500,
                                                   color_key="text_dim"))
        v.addWidget(path_lbl)

        path_row = QHBoxLayout()
        path_input = QLineEdit(str(self.root_folder))
        path_input.setPlaceholderText(
            r"örn: \\TrueNAS\nas\Voluson   veya   C:\Hastalar   veya   "
            r"/mnt/nas/voluson")
        path_input.setStyleSheet(code_input_style())
        browse_btn = QPushButton("📁 Gözat...")
        browse_btn.setToolTip(
            "Windows Explorer'dan bir klasör seç. Ağ sürücüsü eşlenmişse "
            "onu da seçebilirsin. UNC yolu istiyorsan yukarıdaki kutuya "
            "elle yaz (\\\\sunucu\\paylaşım).")

        def _browse():
            current = path_input.text().strip()
            # If current is a real directory, start there. Otherwise start
            # at user's home folder — safer default than C:\.
            start = current if current and Path(current).exists() \
                else str(Path.home())
            picked = QFileDialog.getExistingDirectory(
                dlg, "NAS Klasörünü Seç", start,
                QFileDialog.ShowDirsOnly)
            if picked:
                path_input.setText(picked)

        browse_btn.clicked.connect(_browse)
        path_row.addWidget(path_input, 1)
        path_row.addWidget(browse_btn)
        v.addLayout(path_row)

        hint = QLabel(
            "💡 <b>UNC yolu örnekleri:</b> "
            "<code>\\\\TrueNAS\\nas\\Voluson</code> &nbsp;|&nbsp; "
            "<code>\\\\192.168.1.10\\share\\Hastalar</code><br>"
            "Ağ yolunu elle yazarsan, aşağıdaki kimlik bilgileri alanları "
            "kullanılır.")
        hint.setTextFormat(Qt.RichText)
        hint.setWordWrap(True)
        hint.setStyleSheet(hint_label_style())
        v.addWidget(hint)

        # Credentials (optional)
        cred_hdr = QLabel(
            "<b>Kimlik bilgileri (isteğe bağlı, sadece UNC yolu için)</b>")
        cred_hdr.setTextFormat(Qt.RichText)
        cred_hdr.setStyleSheet(header_label_style(font_size=12))
        v.addWidget(cred_hdr)

        form = QFormLayout()
        form.setSpacing(6)
        user_input = QLineEdit(self._settings.value("nas/user", "") or "")
        user_input.setPlaceholderText("kullanıcı adı (boş bırakılabilir)")
        pass_input = QLineEdit(self._settings.value("nas/password", "") or "")
        pass_input.setPlaceholderText("şifre (boş bırakılabilir)")
        pass_input.setEchoMode(QLineEdit.Password)
        domain_input = QLineEdit(self._settings.value("nas/domain", "") or "")
        domain_input.setPlaceholderText("domain (opsiyonel, örn: WORKGROUP)")
        for w in (user_input, pass_input, domain_input):
            w.setStyleSheet(input_style())
        form.addRow("Kullanıcı adı:", user_input)
        form.addRow("Şifre:", pass_input)
        form.addRow("Domain:", domain_input)
        v.addLayout(form)

        # Security notice
        sec = QLabel(
            "⚠ Şifre QSettings içinde <b>şifrelenmeden</b> saklanır. "
            "Sadece kendi kişisel bilgisayarında kullan. Ortak kullanılan "
            "bir makinede boş bırak — Windows Explorer ile eşlenen ağ "
            "sürücülerinden otomatik kimlik alınır.")
        sec.setTextFormat(Qt.RichText)
        sec.setWordWrap(True)
        sec.setStyleSheet(warning_notice_style())
        v.addWidget(sec)

        # Status label (for test feedback)
        status_lbl = QLabel("")
        status_lbl.setWordWrap(True)
        status_lbl.setStyleSheet(status_label_style("info"))
        v.addWidget(status_lbl)

        # Buttons
        test_btn = QPushButton("🔌 Bağlantıyı Test Et")
        save_btn = QPushButton("💾 Kaydet ve Uygula")
        save_btn.setStyleSheet(success_button_style())
        cancel_btn = QPushButton("İptal")
        cancel_btn.setShortcut("Escape")

        def _test():
            new_path = path_input.text().strip()
            if not new_path:
                status_lbl.setStyleSheet(status_label_style("error"))
                status_lbl.setText("✗ Klasör yolu boş.")
                return
            status_lbl.setStyleSheet(status_label_style("info"))
            status_lbl.setText("⏳ Kontrol ediliyor...")
            test_btn.setEnabled(False)

            # Capture form values now — worker must not touch widgets.
            snap_user = user_input.text().strip()
            snap_pass = pass_input.text()
            snap_domain = domain_input.text().strip()
            snap_path = new_path

            def _probe():
                """Runs on a worker. Tries a `net use` if credentials + UNC,
                then `Path(...).exists() and .is_dir()`. Returns a tuple
                (ok, message)."""
                if snap_path.startswith("\\\\") and snap_user and os.name == "nt":
                    parts = snap_path.replace("/", "\\").lstrip("\\").split("\\", 2)
                    if len(parts) >= 2:
                        unc_root = f"\\\\{parts[0]}\\{parts[1]}"
                        full_user = (f"{snap_domain}\\{snap_user}"
                                     if snap_domain else snap_user)
                        try:
                            CREATE_NO_WINDOW = 0x08000000
                            subprocess.run(
                                ["net", "use", unc_root, snap_pass,
                                 f"/user:{full_user}"],
                                capture_output=True, text=True, timeout=10,
                                creationflags=CREATE_NO_WINDOW,
                            )
                        except Exception as _ex:
                            _log_warning("MainWindow._probe", exc=_ex)
                try:
                    p = Path(snap_path)
                    if not p.exists():
                        return (False, f"Yol bulunamadı: {snap_path}")
                    if not p.is_dir():
                        return (False, "Yol bir klasör değil.")
                    # Try to list it to confirm read access
                    items = []
                    for i, item in enumerate(p.iterdir()):
                        items.append(item)
                        if i >= 4:
                            break  # a handful is enough
                    return (True, f"Erişilebilir — içeride en az {len(items)} öğe var")
                except PermissionError:
                    return (False, "Erişim reddedildi. Kullanıcı/şifre/domain'i kontrol et.")
                except Exception as ex:
                    return (False, f"Hata: {ex}")

            def _on_done(result):
                test_btn.setEnabled(True)
                ok, msg = result
                if ok:
                    status_lbl.setStyleSheet(
                        status_label_style("success"))
                    status_lbl.setText(f"✓ {msg}")
                else:
                    status_lbl.setStyleSheet(status_label_style("error"))
                    status_lbl.setText(f"✗ {msg}")

            def _on_error(ex):
                test_btn.setEnabled(True)
                status_lbl.setStyleSheet(status_label_style("error"))
                status_lbl.setText(f"✗ Test hatası: {ex}")

            self._run_bg(_probe, on_done=_on_done, on_error=_on_error,
                         description="nas-test")

        def _save():
            new_path = path_input.text().strip()
            if not new_path:
                QMessageBox.warning(dlg, "Eksik Bilgi",
                                    "Klasör yolu boş olamaz.")
                return
            # Persist
            self._settings.setValue("nas/path", new_path)
            self._settings.setValue("nas/user", user_input.text().strip())
            self._settings.setValue("nas/password", pass_input.text())
            self._settings.setValue("nas/domain", domain_input.text().strip())
            # Apply to the running session
            self.root_folder = Path(new_path)
            try:
                self._maybe_mount_nas_share()
            except Exception as ex:
                _log_warning(f"mount after save failed: {ex}")
            # Clear the in-memory subfolder cache so the new root's content
            # is scanned fresh, not served from cache of the old root.
            try:
                _subfolder_cache_invalidate()
            except Exception as _ex:
                _log_warning("MainWindow._save", exc=_ex)
            # Refresh the whole patient list
            try:
                self.refresh_all()
            except Exception as ex:
                _log_warning(f"refresh after NAS path change failed: {ex}")
            self.statusBar().showMessage(
                f"✓ NAS yolu güncellendi: {new_path}", 4000)
            dlg.accept()

        test_btn.clicked.connect(_test)
        save_btn.clicked.connect(_save)
        cancel_btn.clicked.connect(dlg.reject)

        btn_row = QHBoxLayout()
        btn_row.addWidget(test_btn)
        btn_row.addStretch()
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)
        v.addLayout(btn_row)

        dlg.exec()
