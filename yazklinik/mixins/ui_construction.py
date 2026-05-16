"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _UiConstructionMixin
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

class _UiConstructionMixin:
    """MainWindow methods related to UiConstruction. Mixed into MainWindow via MRO."""

    def _build_menu_bar(self):
        """Menu bar organised into 7 logical groups — each menu is
        about ONE domain. Previous layout had 10 menus, some with only
        1-2 entries (Düzen, Görüntüleme, Görünüm), which fragments the
        doctor's mental model. Consolidated grouping:

          • Dosya       → app-level file ops (refresh, sync, folder, exit)
          • Hasta       → everything per-patient: copy/summary, info,
                          handouts (test/calendar/diet), WhatsApp
          • Belgeler    → PDF + signature + DICOM cache
          • Filtreler   → patient list filters + advanced search +
                          "focus list" jump
          • İstatistik  → clinic-wide stats
          • Ayarlar     → all config (NAS, Orthanc, theme, identity, format)
          • Yardım      → about, shortcuts, error log

        Each item shows its shortcut right-aligned by Qt automatically,
        so the user sees F-keys + Ctrl-combos inline.
        """
        mb = self.menuBar()

        # ═══════════════════════════════════════════════════════════════
        # 1. DOSYA — app-level file ops
        # ═══════════════════════════════════════════════════════════════
        m_file = mb.addMenu("&Dosya")

        a_refresh = QAction("🔁  &Yenile", self)
        a_refresh.setShortcut("F5")
        a_refresh.setToolTip(
            "Hasta listesini diskten yeniden yükle (F5)")
        a_refresh.triggered.connect(self.refresh_all)
        m_file.addAction(a_refresh)

        a_sync = QAction("🔄  NAS ile &Senkronize Et", self)
        a_sync.setToolTip(
            "NAS klasörünü tarar ve değişiklikleri veritabanına yazar")
        a_sync.triggered.connect(self._run_nas_sync)
        m_file.addAction(a_sync)

        a_sync_status = QAction("📊  Son Senkronizasyon Durumu...", self)
        a_sync_status.triggered.connect(self._show_sync_status)
        m_file.addAction(a_sync_status)

        m_file.addSeparator()
        a_open_folder = QAction("📂  Geliş &Klasörünü Aç", self)
        a_open_folder.setShortcut("Ctrl+O")
        a_open_folder.setToolTip(
            "Seçili gelişin klasörünü dosya gezgininde aç (Ctrl+O)")
        a_open_folder.triggered.connect(self.open_folder)
        m_file.addAction(a_open_folder)

        m_file.addSeparator()
        a_exit = QAction("🚪  &Çıkış", self)
        a_exit.setShortcut("Alt+F4")
        a_exit.triggered.connect(self.close)
        m_file.addAction(a_exit)

        # ═══════════════════════════════════════════════════════════════
        # 2. HASTA — everything about the CURRENT patient
        # Grouped into three sub-sections by separator:
        #   (a) Copy / summary
        #   (b) Info + growth curves
        #   (c) Printable handouts (test / calendar / diet)
        #   (d) WhatsApp
        # ═══════════════════════════════════════════════════════════════
        m_patient = mb.addMenu("&Hasta")

        # v68: Manual patient registration. Opens a dialog where the
        # doctor enters name + age + phone + obstetric/gynecologic
        # type, then creates the folder and switches the app into
        # the matching mode automatically.
        a_new = QAction("🆕  &Yeni Hasta Kaydı…", self)
        a_new.setShortcut("Ctrl+N")
        a_new.setToolTip(
            "Yeni hasta klasörü oluştur ve obstetrik/jinekolojik "
            "olarak işaretle. Program otomatik olarak ilgili moda "
            "geçer (Ctrl+N).")
        a_new.triggered.connect(self._open_new_patient_dialog)
        m_patient.addAction(a_new)

        # v68: Manual visit creation for the currently-selected patient.
        # Creates a YYYY-MM-DD_HHMM-formatted folder and saves the
        # geliş notunu visit_notes tablosuna.
        a_new_visit = QAction("➕  Yeni &Geliş Ekle…", self)
        a_new_visit.setShortcut("Ctrl+Shift+N")
        a_new_visit.setToolTip(
            "Mevcut hastaya yeni bir geliş kaydı ekle. Tarih + saat "
            "+ not gir; klasör otomatik oluşturulur ve seçilir "
            "(Ctrl+Shift+N).")
        a_new_visit.triggered.connect(self._open_new_visit_dialog)
        m_patient.addAction(a_new_visit)

        # v68: Delete patient — removes folder + all DB rows after a
        # double-confirmation dialog.
        a_delete = QAction("🗑  Hastayı &Sil…", self)
        a_delete.setShortcut("Ctrl+Shift+Delete")
        a_delete.setToolTip(
            "Seçili hastanın klasörü, görüntü/DICOM/notları, formları "
            "ve veritabanı kayıtlarını KALICI olarak siler "
            "(Ctrl+Shift+Delete). Bu işlem geri alınamaz.")
        a_delete.triggered.connect(self._delete_current_patient)
        m_patient.addAction(a_delete)

        m_patient.addSeparator()

        # (a) Copy / summary
        a_copy = QAction("📋  Özeti &Kopyala", self)
        a_copy.setShortcut("Ctrl+C")
        a_copy.setToolTip(
            "Görünen özeti panoya kopyala — not varsa onu da ekler (Ctrl+C)")
        a_copy.triggered.connect(self.copy_summary)
        m_patient.addAction(a_copy)

        a_long = QAction("📄  &Uzun Özet — konsültasyon için", self)
        a_long.setShortcut("Ctrl+Shift+C")
        a_long.setToolTip(
            "Demografi + bayraklar + son ziyaret → panoya — konsültasyon / "
            "devir teslim için (Ctrl+Shift+C veya F2)")
        a_long.triggered.connect(self.copy_long_summary)
        m_patient.addAction(a_long)

        m_patient.addSeparator()

        # (b) Info + growth curves
        a_demo = QAction("👤  Hasta &Bilgileri…", self)
        a_demo.setShortcut("F3")
        a_demo.setToolTip(
            "Kan grubu, Rh, obstetrik öykü, kronik hastalıklar, "
            "ilaçlar, alerjiler (F3)")
        a_demo.triggered.connect(self._show_demographics_dialog)
        m_patient.addAction(a_demo)

        a_growth = QAction("📈  Büyüme &Eğrileri…", self)
        a_growth.setShortcut("F8")
        a_growth.setToolTip(
            "Bebek ölçümlerinin haftalara göre değişim grafiği + "
            "Hadlock persentil bandları + EFW (F8)")
        a_growth.triggered.connect(self._show_growth_trend_dialog)
        m_patient.addAction(a_growth)

        m_patient.addSeparator()

        # (c) Printable A4 handouts
        a_tests_print = QAction("🧪  Test &Listesi — yazdır", self)
        a_tests_print.setShortcut("F4")
        a_tests_print.setToolTip(
            "Bugün ve bundan sonra yapılması gereken tetkiklerin "
            "hafta-tarih listesi — A4 yazdırılabilir (F4)")
        a_tests_print.triggered.connect(self._show_patient_test_sheet)
        m_patient.addAction(a_tests_print)

        a_calendar = QAction("📅  Gebelik &Takvimi — yazdır", self)
        a_calendar.setShortcut("F6")
        a_calendar.setToolTip(
            "LMP'den doğuma kadar tüm izlem planı — A4 çıktı (F6)")
        a_calendar.triggered.connect(self._show_pregnancy_calendar)
        m_patient.addAction(a_calendar)

        a_diet = QAction("🍎  &Diyet Listesi — yazdır", self)
        a_diet.setShortcut("F7")
        a_diet.setToolTip(
            "Gebelik / GDM / sınırda şeker için 3 hazır diyet — "
            "düzenlenebilir, A4 yazdırılabilir (F7)")
        a_diet.triggered.connect(self._show_diet_sheet_dialog)
        m_patient.addAction(a_diet)

        m_patient.addSeparator()

        # (d) WhatsApp
        a_whatsapp = QAction("💬  &WhatsApp — şablondan mesaj", self)
        a_whatsapp.setShortcut("Ctrl+W")
        a_whatsapp.setToolTip(
            "Şablondan mesaj seç: randevu / sonuç / test hatırlatma / "
            "doğum günü. Hasta numarasına WhatsApp açar (Ctrl+W)")
        a_whatsapp.triggered.connect(self.prepare_whatsapp)
        m_patient.addAction(a_whatsapp)

        a_wa_quick = QAction("⚡  Hı&zlı WhatsApp — dosya gönder", self)
        a_wa_quick.setShortcut("Ctrl+Shift+W")
        a_wa_quick.setToolTip(
            "Gelişin dosyalarını (resim+video+PDF) panoya kopyalar + "
            "WhatsApp açar → Ctrl+V ile yapıştır (Ctrl+Shift+W)")
        a_wa_quick.triggered.connect(self.prepare_whatsapp_quick)
        m_patient.addAction(a_wa_quick)

        # ═══════════════════════════════════════════════════════════════
        # 3. BELGELER — PDF + signature + DICOM cache
        # ═══════════════════════════════════════════════════════════════
        m_docs = mb.addMenu("&Belgeler")

        a_print = QAction("🖨️  PDF'i &Yazdır", self)
        a_print.setShortcut("Ctrl+P")
        a_print.setToolTip(
            "Mevcut PDF raporunu sistem yazıcısına gönder (Ctrl+P)")
        a_print.triggered.connect(self.print_current_pdf)
        m_docs.addAction(a_print)

        # v68: "PDF Oluştur" menu entry removed per doctor's request —
        # PDF generation now happens exclusively through the 📄 Rapor
        # tab's sub-tabs (Mevcut PDF + Yeni PDF), which is where the
        # doctor already goes to build reports. The Ctrl+Shift+P
        # shortcut is preserved as a hidden QShortcut below so existing
        # muscle memory still triggers build_pdf_from_selection.
        _build_pdf_sc = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        _build_pdf_sc.activated.connect(self.build_pdf_from_selection)

        a_tmpl = QAction("📝  Şablon &Düzenle / Ekle…", self)
        a_tmpl.setShortcut("Ctrl+T")
        a_tmpl.setToolTip(
            "PDF şablonlarını yönet — raporun son sayfasına "
            "eklenecek hazır metin blokları (Ctrl+T)")
        a_tmpl.triggered.connect(self._open_templates_dialog)
        m_docs.addAction(a_tmpl)

        m_docs.addSeparator()

        a_dicom_status = QAction("📊  DICOM &Önbellek Durumu…", self)
        a_dicom_status.setToolTip(
            "Kaç hastanın DICOM görüntüsü önbellekte var, son "
            "senkronizasyon ne zaman")
        a_dicom_status.triggered.connect(self._show_dicom_cache_status)
        m_docs.addAction(a_dicom_status)

        # ═══════════════════════════════════════════════════════════════
        # 3.5 ONAM & REÇETE — printable library (consents + prescriptions)
        # ═══════════════════════════════════════════════════════════════
        m_print = mb.addMenu("&Onam && Reçete")

        a_consent = QAction("📋  &Onam Formları...", self)
        a_consent.setShortcut(QKeySequence("Ctrl+Shift+O"))
        a_consent.setToolTip(
            "Onam formları kütüphanesi — Obstetrik / Jinekolojik / "
            "Lazer / Medikal Estetik / Jinekolojik Estetik. "
            "Tek tık → A4 yazdır.")
        a_consent.triggered.connect(self._show_consent_forms_dialog)
        m_print.addAction(a_consent)

        a_rx = QAction("💊  &Hazır Reçeteler...", self)
        a_rx.setShortcut(QKeySequence("Ctrl+Alt+R"))
        a_rx.setToolTip(
            "Hazır reçete şablonları — kategorize edilmiş, "
            "tek tık → A5 yazdır.")
        a_rx.triggered.connect(self._show_prescription_dialog)
        m_print.addAction(a_rx)

        # ═══════════════════════════════════════════════════════════════
        # 4. FİLTRELER — patient list filters + advanced search
        # ═══════════════════════════════════════════════════════════════
        m_filt = mb.addMenu("&Filtreler")

        a_focus_list = QAction("🔎  Hastada &Ara (liste filtresi)", self)
        # NOTE: Ctrl+F is owned by the toolbar's search_shortcut QAction
        # (see _build_tool_bar). Binding it here too would cause Qt's
        # 'Ambiguous shortcut overload' warning. The menu entry is
        # clickable from the menu; the shortcut works via the toolbar.
        a_focus_list.setToolTip(
            "İmleci sol üstteki hasta arama kutusuna koyar — "
            "yazmaya başla, hasta listesi anında filtrelenir (Ctrl+F)")
        a_focus_list.triggered.connect(
            lambda: self.search_input.setFocus()
            if hasattr(self, "search_input") else None)
        m_filt.addAction(a_focus_list)

        a_advanced = QAction("🔎  &Gelişmiş Arama...", self)
        a_advanced.setShortcut("Ctrl+Shift+F")
        a_advanced.setToolTip(
            "Çoklu kriter arama: ad + yaş + bayrak + tarih "
            "aralığı (Ctrl+Shift+F)")
        a_advanced.triggered.connect(self._show_advanced_search_dialog)
        m_filt.addAction(a_advanced)

        m_filt.addSeparator()

        # Time-based filters (active / lost / dropped)
        a_active = QAction(
            "💚  Son 2 Ay &Aktif Takibim (≤ 60 gün)", self)
        a_active.setToolTip(
            "Son 60 gün içinde gelmiş hastalar — şu anda kaç gebe "
            "takibimde olduğunu görmek için.")
        a_active.triggered.connect(
            lambda: self._show_filter_dialog("active_60"))
        m_filt.addAction(a_active)

        a_near = QAction("🤰  &Doğumu Yakın Olanlar (6 hafta)", self)
        a_near.setToolTip(
            "6 hafta içinde beklenen doğumlar — C/S planı varsa "
            "2 hafta erken listede görünür. Doğum yapmış hastalar "
            "otomatik dışlanır.")
        a_near.triggered.connect(
            lambda: self._show_filter_dialog("near_delivery"))
        m_filt.addAction(a_near)

        a_lost = QAction(
            "⏰  Takibi &Bırakanlar (45+ gün — erken uyarı)", self)
        a_lost.setToolTip(
            "Son ziyaretten 45+ gün geçmiş ama henüz 'takipten "
            "düşmüş' sayılmayan hastalar — takipten çıkmalarını "
            "önlemek için erken uyarı listesi.")
        a_lost.triggered.connect(
            lambda: self._show_filter_dialog("no_visit_45"))
        m_filt.addAction(a_lost)

        # v68: "Takipten Düşenler (2 ay+)" removed per doctor's request.
        # The earlier-warning "Takibi Bırakanlar (45+ gün)" covers the
        # same patients and already filters out delivered cases, so a
        # separate 60-day menu entry was redundant.

        # Jinekolojik hastalar — patients whose PDFs don't say
        # "Obstetrics Report". These are excluded from the pregnancy
        # follow-up filters/stats above so they don't get mixed in
        # with obstetric patients.
        a_gyn = QAction("♀️  &Jinekolojik Hastalar (gebe dışı)", self)
        a_gyn.setToolTip(
            "Voluson raporlarında 'Obstetrics Report' başlığı olmayan "
            "hastalar — jinekolojik muayene kayıtları. Gebe takibi "
            "filtrelerine dahil değildirler.")
        a_gyn.triggered.connect(
            lambda: self._show_filter_dialog("gynecologic"))
        m_filt.addAction(a_gyn)

        m_filt.addSeparator()

        # Flag-based filter submenu — one click per flag
        m_by_flag = m_filt.addMenu("🏷️  &Bayrağa Göre Filtrele")
        m_by_flag.setToolTip(
            "Belirli bir bayrağı işaretli olan tüm hastaları listele")

        a_flagged = QAction("🏷️  Tüm Bayraklı Hastalar", self)
        a_flagged.triggered.connect(
            lambda: self._show_filter_dialog("flagged"))
        m_by_flag.addAction(a_flagged)
        m_by_flag.addSeparator()

        for fkey, flabel, _level in PATIENT_FLAGS:
            a = QAction(flabel, self)
            a.triggered.connect(
                lambda _checked=False, k=fkey:
                self._show_filter_dialog("flag", k))
            m_by_flag.addAction(a)

        # ═══════════════════════════════════════════════════════════════
        # 5. İSTATİSTİK — clinic-wide stats
        # ═══════════════════════════════════════════════════════════════
        m_stats = mb.addMenu("&İstatistik")

        a_overview = QAction("📊  &Genel Bakış", self)
        a_overview.setToolTip(
            "Toplam hasta, aktif gebe, doğum yapmış, ortalama GA, "
            "bayrak dağılımı gibi genel rakamlar")
        a_overview.triggered.connect(self._show_stats_overview)
        m_stats.addAction(a_overview)

        a_monthly = QAction("📅  &Aylık Hasta Sayıları", self)
        a_monthly.setToolTip(
            "Her ay kaç yeni hasta geldi, kaç ziyaret yapıldı")
        a_monthly.triggered.connect(self._show_stats_monthly)
        m_stats.addAction(a_monthly)

        a_flags_dist = QAction("🏷️  &Bayrak Dağılımı", self)
        a_flags_dist.setToolTip(
            "Hangi bayrak kaç hastada işaretli — risk yoğunluğu "
            "için genel tablo")
        a_flags_dist.triggered.connect(self._show_stats_flags)
        m_stats.addAction(a_flags_dist)

        m_stats.addSeparator()

        # v68: Gynecologic / Infertility stats — separate from obstetric
        # numbers because pregnancy-specific metrics (GA, EDD, term-dönem)
        # don't apply to gyn patients.
        a_infertilite = QAction("🌸  &İnfertilite İstatistikleri", self)
        a_infertilite.setToolTip(
            "Jinekolojik hastalar (Obstetrics Report olmayan) için "
            "ayrı istatistik tablosu — toplam, son 30 gün, son 1 yıl")
        a_infertilite.triggered.connect(self._show_stats_infertility)
        m_stats.addAction(a_infertilite)

        # ═══════════════════════════════════════════════════════════════
        # 5b. KLİNİK — Web ile eşleme: Obstetrik / Jinekoloji / Riskli
        # ═══════════════════════════════════════════════════════════════
        m_clinic = mb.addMenu("&Klinik")

        a_obstetrik = QAction("🤰 &Obstetrik Hastalar", self)
        a_obstetrik.setToolTip("Sadece gebe takibi olan hastalar")
        a_obstetrik.triggered.connect(
            lambda: self._filter_by_type("obstetric"))
        m_clinic.addAction(a_obstetrik)

        a_jinekoloji = QAction("🌸 &Jinekoloji Hastalar", self)
        a_jinekoloji.setToolTip("Gebelik dışı kadın sağlığı")
        a_jinekoloji.triggered.connect(
            lambda: self._filter_by_type("gynecologic"))
        m_clinic.addAction(a_jinekoloji)

        a_riskli = QAction("⚠️ &Riskli Gebelik", self)
        a_riskli.setToolTip(
            "Yüksek riskli gebeler — preeklampsi, GDM, "
            "IUGR, anomali şüphesi")
        a_riskli.triggered.connect(self._show_riskli_gebelik)
        m_clinic.addAction(a_riskli)

        m_clinic.addSeparator()

        a_recent = QAction("⏱ &Son Gelen Hastalar", self)
        a_recent.setToolTip(
            "Son ziyaret tarihine göre sıralı liste")
        a_recent.triggered.connect(self._show_recent_patients)
        m_clinic.addAction(a_recent)

        # ═══════════════════════════════════════════════════════════════
        # 5c. YAPAY ZEKA — Web ile aynı 8 aksiyon
        # ═══════════════════════════════════════════════════════════════
        m_ai = mb.addMenu("&Yapay Zeka")

        a_ai_open = QAction("🤖 YZ &Asistan Aç (Ctrl+Y)", self)
        a_ai_open.setShortcut("Ctrl+Y")
        a_ai_open.setToolTip(
            "8 uzman aksiyonlu YZ paneli")
        a_ai_open.triggered.connect(self._open_ai_assistant)
        m_ai.addAction(a_ai_open)

        m_ai.addSeparator()

        # 8 quick AI action shortcuts
        ai_actions = [
            ("🩺 &Vaka Tartışması", "case_discuss",
             "Aktif hasta için klinik karar destek"),
            ("🔬 &Tahlil Yorumu", "lab_interpret",
             "Son tahlil yorumla"),
            ("💊 &Reçete Kontrolü", "rx_check",
             "Etkileşim + gebelik kategorisi"),
            ("🥗 &Diyet Planı", "diet_plan",
             "Kişiselleştirilmiş diyet"),
            ("🚨 &Anomali Tarama", "anomaly_screen",
             "USG bulgularını değerlendir"),
            ("📚 A&kademik Sorgu", "academic",
             "ACOG/RCOG kılavuzlu literatür"),
            ("📋 Muayene &Özeti", "visit_summary",
             "Notu yapılandırılmış formata"),
            ("💬 &Genel Sohbet", "general",
             "Sınırsız tıbbi soru-cevap"),
        ]
        for label, key, tip in ai_actions:
            a = QAction(label, self)
            a.setToolTip(tip)
            a.triggered.connect(
                lambda checked=False, k=key:
                self._open_ai_with_action(k))
            m_ai.addAction(a)

        m_ai.addSeparator()

        a_ai_setup = QAction("🚀 YZ &Kurulum Rehberi", self)
        a_ai_setup.setToolTip("Web'de YZ kurulum adımları")
        a_ai_setup.triggered.connect(
            lambda: self._open_url(
                "/yz-kurulum-rehberi"))
        m_ai.addAction(a_ai_setup)

        a_ai_wizard = QAction("🧠 YZ &Sihirbazı (Web)", self)
        a_ai_wizard.setToolTip("Web'de model seçim sihirbazı")
        a_ai_wizard.triggered.connect(
            lambda: self._open_url("/yz-sihirbazi"))
        m_ai.addAction(a_ai_wizard)

        a_bulutklinik = QAction(
            "📋 &Bulutklinik Aktarım (Web)", self)
        a_bulutklinik.setToolTip(
            "Web tarayıcıda Bulutklinik/e-Nabız aktarım")
        a_bulutklinik.triggered.connect(
            lambda: self._open_url("/bulutklinik-aktarim"))
        m_ai.addAction(a_bulutklinik)

        # ═══════════════════════════════════════════════════════════════
        # 6. AYARLAR — all app configuration in one place
        # Grouped:
        #   (a) Server/path configuration (NAS, Orthanc)
        #   (b) Appearance (dark theme)
        #   (c) Clinic identity + destructive (format) at bottom
        # ═══════════════════════════════════════════════════════════════
        m_settings = mb.addMenu("&Ayarlar")

        # ── Group 1: external services (NAS, DICOM, WhatsApp) ───────────
        a_nas = QAction("🗂️  &NAS Klasörü ve Kimlik…", self)
        a_nas.setToolTip(
            "Hasta klasörlerinin okunduğu NAS yolu, kullanıcı adı, "
            "şifre, domain")
        a_nas.triggered.connect(self._show_nas_settings_dialog)
        m_settings.addAction(a_nas)

        a_orthanc_cfg = QAction("🩻  &Orthanc DICOM Sunucusu…", self)
        a_orthanc_cfg.setToolTip(
            "Orthanc sunucu IP, port, kullanıcı adı ve şifre")
        a_orthanc_cfg.triggered.connect(self._show_orthanc_settings_dialog)
        m_settings.addAction(a_orthanc_cfg)

        a_wa_default = QAction("💬  &WhatsApp Ayarları…", self)
        a_wa_default.setToolTip(
            "WhatsApp gönderim ayarları:\n"
            "  • Varsayılan numara (kendi numarası olmayan hastalar için)\n"
            "  • Seçili hastanın özel numarası\n"
            "  • 📦 ZIP modu (tüm dosyaları tek arşivde gönder)\n"
            "  • ⏎ Otomatik gönder (Enter'a otomatik bas)")
        a_wa_default.triggered.connect(self._show_wa_default_dialog)
        m_settings.addAction(a_wa_default)

        a_printer_cfg = QAction("🖨  &Yazıcı Ayarları…", self)
        a_printer_cfg.setToolTip(
            "Profesyonel yazıcı ayarları:\n"
            "  • Hedef yazıcı\n"
            "  • Kağıt boyutu (A3/A4/A5/A6/Letter/Legal/B5)\n"
            "  • Yön (dikey/yatay)\n"
            "  • Kenar boşlukları (mm)\n"
            "  • Yazdırma diyaloğu modu (her defasında aç / doğrudan)\n"
            "Ayarlar tüm diyet listesi, takip formu, planlama vb. "
            "yazdırmalarına uygulanır.")
        a_printer_cfg.triggered.connect(self._show_printer_settings_dialog)
        m_settings.addAction(a_printer_cfg)

        m_settings.addSeparator()

        # v68-UI: Database backup — critical for data safety
        a_backup = QAction("💾  Veritabanını &Yedekle…", self)
        a_backup.setShortcut("Ctrl+Shift+B")
        a_backup.setToolTip(
            "SQLite veritabanını dosyaya yedekle (VACUUM INTO ile "
            "tutarlı online yedek). Default konum: Masaüstü/"
            "yazklinik_yedek_TARIH.sqlite. Düzenli olarak harici "
            "diske kopyalamanız önerilir.")
        a_backup.triggered.connect(self._backup_database_to_file)
        m_settings.addAction(a_backup)

        m_settings.addSeparator()

        # ── Group 2: appearance ────────────────────────────────────────
        a_dark = QAction("🌙  &Koyu Tema", self)
        a_dark.setCheckable(True)
        a_dark.setChecked(bool(self._settings.value("ui/dark_mode", False,
                                                     type=bool)))
        a_dark.setToolTip(
            "Arayüzü koyu renklere boyar. Yazılar, menüler, listeler "
            "ve kenar çubukları anında değişir. Özel renkli banner/"
            "uyarı çubukları (DİKKAT, RHOGAM vb.) görsel amaçla "
            "aynı kalır — bu bilinçli bir tercih.")

        def _toggle_dark(checked: bool):
            self._settings.setValue("ui/dark_mode", checked)
            _apply_app_palette(QApplication.instance())
            # Re-style inline-styled widgets so the theme actually sticks
            try:
                self._refresh_themed_widgets()
            except Exception as _ex:
                _log_warning("dark toggle: refresh widgets", exc=_ex)
            self.statusBar().showMessage(
                "✓ Koyu tema " + ("açık" if checked else "kapalı"),
                4000)

        a_dark.toggled.connect(_toggle_dark)
        m_settings.addAction(a_dark)

        m_settings.addSeparator()

        # ── Group 3: clinic identity ───────────────────────────────────
        a_identity = QAction("✏️  &Klinik Bilgilerini Düzenle…", self)
        a_identity.setToolTip(
            "Doktor adı, klinik adı ve yönetici şifresini değiştir "
            "— mevcut şifre gerekir")
        a_identity.triggered.connect(self._show_identity_edit_dialog)
        m_settings.addAction(a_identity)

        a_license = QAction("🔑  &Lisans Anahtarını Değiştir…", self)
        a_license.setToolTip(
            "Programı açmak için kullanılan ana lisans anahtarını "
            "değiştir. Acil anahtar (yazklinik796) değişmez — her "
            "zaman geçerli kalır.")
        a_license.triggered.connect(self._show_license_change_dialog)
        m_settings.addAction(a_license)

        m_settings.addSeparator()

        # ── Group 4: data safety (backup/restore) ───────────────────────
        a_backup = QAction("📦  &Yedek Al — DB'yi dışa aktar…", self)
        a_backup.setToolTip(
            "Mevcut veritabanının bir kopyasını seçtiğin klasöre "
            "kaydet. Harici disk/bulut için düzenli yedek alınması "
            "tavsiye edilir.")
        a_backup.triggered.connect(self._show_backup_dialog)
        m_settings.addAction(a_backup)

        a_restore = QAction(
            "📂  Yedek&ten Geri Yükle (uygulama kapanır)…", self)
        a_restore.setToolTip(
            "Önceden alınmış bir yedek dosyasından geri yükle. "
            "Yönetici şifresi gerekir. Mevcut DB'nin güvenlik kopyası "
            "ayrıca saklanır.")
        a_restore.triggered.connect(self._show_restore_dialog)
        m_settings.addAction(a_restore)

        m_settings.addSeparator()

        # v68-AI: Kullanıcı Rolü — multi-PC role selection
        a_role = QAction("👥  &Kullanıcı Rolü...", self)
        a_role.setToolTip(
            "Bu PC'nin rolünü ayarlayın (Doktor / Asistan / Sekreter). "
            "Rol, hangi işlemlerin yapılabileceğini belirler. "
            "Sekreter rolünde bayrak/silme/ayar gibi işlemler "
            "engellenir.")
        a_role.triggered.connect(self._show_user_role_dialog)
        m_settings.addAction(a_role)

        m_settings.addSeparator()

        # ── Group 5: destructive (visually separated at bottom) ─────────
        a_format = QAction(
            "⚠️  &Sistemi Sıfırla — tüm hasta verilerini sil…", self)
        a_format.setToolTip(
            "TÜM hasta verilerini DB'den siler — NAS klasörleri "
            "korunur. Yeni klinikte temiz başlangıç için. Yönetici "
            "şifresi gerekir.")
        a_format.triggered.connect(self._show_format_dialog)
        m_settings.addAction(a_format)

        # ═══════════════════════════════════════════════════════════════
        # 7. YARDIM — about + shortcuts + error log
        # ═══════════════════════════════════════════════════════════════
        m_help = mb.addMenu("&Yardım")

        a_shortcuts = QAction("⌨  &Klavye Kısayolları...", self)
        a_shortcuts.setShortcut("F1")
        a_shortcuts.setToolTip(
            "Tüm klavye kısayollarının referans listesi (F1)")
        a_shortcuts.triggered.connect(self._show_shortcuts_dialog)
        m_help.addAction(a_shortcuts)

        a_health = QAction("🩺  &Sistem Durumu…", self)
        a_health.setToolTip(
            "Uygulama versiyonu, DB boyutu, hasta sayısı, NAS "
            "erişimi, hata kayıt durumu — hepsi bir ekranda")
        a_health.triggered.connect(self._show_system_health_panel)
        m_help.addAction(a_health)

        a_about = QAction("ℹ️  &Hakkında", self)
        a_about.triggered.connect(self._show_about)
        m_help.addAction(a_about)

        m_help.addSeparator()

        # v68-AI: Web arayüzünü tarayıcıda aç
        a_open_web = QAction("🌐  Web &Arayüzünü Aç...", self)
        a_open_web.setToolTip(
            "YazKlinik Web'i tarayıcıda aç — sekreter/asistan "
            "için kullanılan, Mac/iPad uyumlu web sürümü")
        a_open_web.triggered.connect(self._open_web_interface)
        m_help.addAction(a_open_web)

        # v68-AI: Mevcut hastayı web'de aç
        a_open_web_pt = QAction(
            "🌐  Mevcut Hastayı Web'de Aç", self)
        a_open_web_pt.setToolTip(
            "Seçili hastayı tarayıcıda doğrudan aç — Mac/iPad'den "
            "detaya bakmak için")
        a_open_web_pt.triggered.connect(self._open_web_patient)
        m_help.addAction(a_open_web_pt)

        # v68-AI: Web takvim (randevu)
        a_open_web_cal = QAction(
            "📆  Web Takvim (Randevular)", self)
        a_open_web_cal.setToolTip(
            "Web arayüzündeki haftalık randevu takvimini aç")
        a_open_web_cal.triggered.connect(self._open_web_calendar)
        m_help.addAction(a_open_web_cal)

        # v68-AI: Bugünün randevuları (dialog)
        a_today_appts = QAction(
            "📅  Bugünün Randevuları...", self)
        a_today_appts.setShortcut("Ctrl+Alt+R")
        a_today_appts.setToolTip(
            "Bugün gelecek hastaları göster (web'deki randevulardan)")
        a_today_appts.triggered.connect(
            self._show_today_appointments)
        m_help.addAction(a_today_appts)

        m_help.addSeparator()

        a_show_log = QAction("🔍  Hata &Log'unu Aç…", self)
        a_show_log.setToolTip(
            "Arka planda tutulan hata kayıt dosyasını aç — bir şey "
            "çalışmıyorsa sebebi burada görünür")
        a_show_log.triggered.connect(self._open_error_log)
        m_help.addAction(a_show_log)

        # v68-UI: In-app log viewer with premium UI (no external editor needed)
        a_log_viewer = QAction("📋  Hata Log Görüntüleyici…", self)
        a_log_viewer.setToolTip(
            "Hata log'unu uygulama içinde göster — son 500 satır, "
            "kopyalama + klasörde göster butonları")
        a_log_viewer.triggered.connect(self._show_error_log_viewer)
        m_help.addAction(a_log_viewer)

        a_clear_log = QAction("🧹  Hata Log'unu &Temizle", self)
        a_clear_log.setToolTip(
            "Hata log dosyasını sıfırla — uzun zamandır birikmişse")
        a_clear_log.triggered.connect(self._clear_error_log)
        m_help.addAction(a_clear_log)

        m_help.addSeparator()

        # v68-AI: AI Assistant Dashboard
        a_ai_asst = QAction("🤖  &AI Asistan…", self)
        a_ai_asst.setShortcut(QKeySequence("Ctrl+Shift+A"))
        a_ai_asst.setToolTip(
            "AI Asistan paneli — kullanım analizin, en çok ziyaret "
            "ettiğin hastalar, sık kullandığın eylemler, saat bazlı "
            "aktivite (Ctrl+Shift+A)")
        a_ai_asst.triggered.connect(self._show_ai_assistant_dashboard)
        m_help.addAction(a_ai_asst)


    def _build_tool_bar(self):
        """Toolbar with frequently-used buttons. The keyboard shortcuts
        for these actions are owned by the MENU bar (see _build_menu_bar),
        not by the toolbar buttons themselves — binding the same shortcut
        to two QActions causes Qt's 'Ambiguous shortcut overload' warning
        and sometimes means neither trigger fires.

        Toolbar actions here are click-only; their tooltips still mention
        the shortcut so the user can discover it.
        """
        tb = QToolBar("Ana Araç Çubuğu")
        tb.setObjectName("MainToolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(Qt.TopToolBarArea, tb)

        style = self.style()

        # Group 1: Data refresh
        a_refresh = QAction(style.standardIcon(QStyle.SP_BrowserReload), "Yenile", self)
        a_refresh.setToolTip("Hasta listesini diskten yeniden yükle (F5)")
        a_refresh.triggered.connect(self.refresh_all)
        tb.addAction(a_refresh)

        tb.addSeparator()

        # Group 2: Communication — summary, WhatsApp, print
        a_copy = QAction(style.standardIcon(QStyle.SP_FileDialogDetailedView),
                         "Özeti Kopyala", self)
        a_copy.setToolTip("Hasta özetini panoya kopyala (Ctrl+C)")
        a_copy.triggered.connect(self.copy_summary)
        tb.addAction(a_copy)

        a_wa = QAction(style.standardIcon(QStyle.SP_DialogYesButton),
                       "WhatsApp", self)
        a_wa.setToolTip("WhatsApp şablon seçiciyi aç (özet / randevu / test "
                        "önerisi / doğum günü)")
        a_wa.triggered.connect(self.prepare_whatsapp)
        tb.addAction(a_wa)

        # Hızlı Gönder — tek tık, şablonsuz, direkt dosya transferi
        a_wa_quick = QAction("⚡ Hızlı Gönder", self)
        a_wa_quick.setToolTip(
            "Hızlı WhatsApp Gönderimi: tek tıkla geliş dosyalarını "
            "(resim+video+PDF) panoya kopyala ve hasta numarasında "
            "WhatsApp aç. Ctrl+V ile yapıştır.")
        a_wa_quick.triggered.connect(self.prepare_whatsapp_quick)
        tb.addAction(a_wa_quick)

        a_print = QAction(style.standardIcon(QStyle.SP_FileDialogContentsView),
                          "Yazdır", self)
        a_print.setToolTip("Mevcut PDF raporunu yazdır (Ctrl+P)")
        a_print.triggered.connect(self.print_current_pdf)
        tb.addAction(a_print)

        tb.addSeparator()

        # Group 3: Document operations
        # v68-UI: "PDF Oluştur" toolbar action removed per doctor's
        # request — the dedicated "✓ PDF Oluştur" action button inside
        # the "Yeni PDF" tab serves the same purpose. Keeping it on
        # the top toolbar created visual clutter and was a common
        # mis-click target.

        a_folder = QAction(style.standardIcon(QStyle.SP_DirOpenIcon),
                           "Klasörü Aç", self)
        a_folder.setToolTip("Seçili gelişin klasörünü dosya gezgininde aç")
        a_folder.triggered.connect(self.open_folder)
        tb.addAction(a_folder)

        tb.addSeparator()

        # Group 4: Workflow actions — templates, video
        # NOTE: İmza (signature) button was removed from toolbar AND menu
        # per doctor's request — it now lives only as a clickable button
        # in the Patient Info panel (visible at all times, one click away).
        # Ctrl+I keyboard shortcut still works.

        a_tmpl = QAction(style.standardIcon(QStyle.SP_FileDialogDetailedView),
                         "Şablon", self)
        a_tmpl.setToolTip("Şablon seç / oluştur / düzenle — PDF son sayfasına "
                          "ekle (Ctrl+T)")
        a_tmpl.triggered.connect(self._open_templates_dialog)
        tb.addAction(a_tmpl)

        a_video = QAction(style.standardIcon(QStyle.SP_MediaPlay),
                          "Video", self)
        a_video.setToolTip("Video sekmesine geç — bu gelişe ait videoları göster")
        a_video.triggered.connect(self._goto_videos_tab)
        tb.addAction(a_video)

        tb.addSeparator()

        # v68: Manual mode toggle — obstetric ↔ gynecologic. By default
        # we auto-detect from the PDF content, but the doctor may want
        # to force a view (eg. a gynecologic patient has just become
        # pregnant but the PDF hasn't been scanned yet, or a postpartum
        # patient wants gyn follow-up). The override is remembered for
        # the current patient only — selecting a different patient
        # resets to auto-detect.
        self.a_mode_toggle = QAction("🌸 Jinekoloji Modu", self)
        self.a_mode_toggle.setToolTip(
            "Obstetrik (gebe takibi) ile jinekoloji (infertilite) modu "
            "arasında geçiş yap. Hasta değiştirildiğinde otomatik "
            "algılamaya geri döner.")
        self.a_mode_toggle.triggered.connect(self._toggle_patient_mode)
        tb.addAction(self.a_mode_toggle)

        tb.addSeparator()

        # v68-UI-PREMIUM: AI/Smart features prominently in toolbar
        a_ai = QAction("🧠 Klinik Akıl", self)
        a_ai.setToolTip(
            "Risk skoru + akıllı klinik içgörüler (Ctrl+Shift+I)")
        a_ai.triggered.connect(self._show_clinical_intelligence_dialog)
        tb.addAction(a_ai)

        a_timeline = QAction("🗓 Timeline", self)
        a_timeline.setToolTip(
            "Görsel gebelik zaman çizelgesi (Ctrl+Shift+T)")
        a_timeline.triggered.connect(self._show_pregnancy_timeline_dialog)
        tb.addAction(a_timeline)

        a_search = QAction("🔍 Hızlı Ara", self)
        a_search.setToolTip(
            "Komut paleti — hasta veya komut ara (Ctrl+K)")
        a_search.triggered.connect(self._show_smart_search_dialog)
        tb.addAction(a_search)

        tb.addSeparator()

        # v68-UI-PREMIUM: Printable library — consents + Rx
        a_consent_tb = QAction("📋 Onam", self)
        a_consent_tb.setToolTip(
            "Onam Formları kütüphanesi — tek tıkla A4 yazdır (Ctrl+Shift+O)")
        a_consent_tb.triggered.connect(self._show_consent_forms_dialog)
        tb.addAction(a_consent_tb)

        a_rx_tb = QAction("💊 Reçete", self)
        a_rx_tb.setToolTip(
            "Hazır Reçete şablonları — tek tıkla A5 yazdır (Ctrl+Alt+R)")
        a_rx_tb.triggered.connect(self._show_prescription_dialog)
        tb.addAction(a_rx_tb)

        tb.addSeparator()

        # v68-AI: AI Asistan — kullanım analizi + öneriler
        a_ai_tb = QAction("🤖 AI", self)
        a_ai_tb.setToolTip(
            "AI Asistan — kullanım analizin, en çok ziyaret ettiğin "
            "hastalar, sık kullandığın eylemler (Ctrl+Shift+A)")
        a_ai_tb.triggered.connect(self._show_ai_assistant_dashboard)
        tb.addAction(a_ai_tb)

        tb.addSeparator()

        # Group 5: Help (small)
        a_help = QAction(style.standardIcon(QStyle.SP_MessageBoxQuestion),
                         "Kısayollar", self)
        a_help.setToolTip("Klavye kısayollarını göster (F1)")
        a_help.triggered.connect(self._show_shortcuts_dialog)
        tb.addAction(a_help)

        # Push the search box to the right of the toolbar
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        tb.addWidget(spacer)

        search_lbl = QLabel("  🔍  Hasta ara: ")
        search_lbl.setObjectName("ToolbarLabel")
        tb.addWidget(search_lbl)
        self.search_input = QLineEdit()
        self.search_input.setObjectName("SearchBox")
        self.search_input.setPlaceholderText("ad · soyad · telefon (örn: 0532)")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setFixedWidth(260)
        self.search_input.textChanged.connect(self.apply_patient_filter)
        # Ctrl+F → focus the search box. This is the ONLY binding for
        # Ctrl+F — the menu's "Hastada Ara" entry intentionally has no
        # shortcut to avoid ambiguous-shortcut conflicts with this one.
        search_shortcut = QAction(self)
        search_shortcut.setShortcut("Ctrl+F")
        search_shortcut.triggered.connect(lambda: (
            self.search_input.setFocus(),
            self.search_input.selectAll(),
        ))
        self.addAction(search_shortcut)
        tb.addWidget(self.search_input)
        tb.addSeparator()

        # v68: set initial mode toggle button label (no patient yet,
        # so this just shows "🌸 Jinekolojiye Geç" as the default)
        try:
            self._refresh_mode_toggle_label()
        except Exception as _ex:
            _log_warning("toolbar: initial mode label", exc=_ex)

    def _build_status_bar(self):
        sb = QStatusBar()
        sb.setObjectName("MainStatusBar")
        sb.setSizeGripEnabled(True)
        self.setStatusBar(sb)

        # Stat cards (text-based, classic)
        self.stat_patients  = StatCard("Hastalar", "0")
        self.stat_visits    = StatCard("Gelişler", "0")
        self.stat_files     = StatCard("Dosyalar", "0")
        self.stat_visit     = StatCard("Geliş", "--")
        self.stat_wa        = StatCard("WhatsApp", get_default_whatsapp_number())
        self.stat_signature = StatCard("İmza", "KONTROL")

        for w in [self.stat_patients, self.stat_visits, self.stat_files,
                  self.stat_visit, self.stat_wa, self.stat_signature]:
            sb.addPermanentWidget(self._sb_separator())
            sb.addPermanentWidget(w)

        # NAS connectivity badge — shows online/offline status.
        # Clicking it opens the sync dialog / shows NAS info.
        sb.addPermanentWidget(self._sb_separator())
        self.nas_status_badge = QLabel("⚪ NAS: kontrol ediliyor...")
        self.nas_status_badge.setStyleSheet(
            "color:#606060;font:600 10px 'Segoe UI';"
            "background:#F0F0F0;border:1px solid #C8C8C8;padding:2px 8px;")
        self.nas_status_badge.setToolTip(
            "NAS klasörü erişim durumu\nTıklayın: senkronizasyon başlat")
        self.nas_status_badge.setCursor(Qt.PointingHandCursor)
        # Qt QLabel doesn't have clicked signal — use mousePressEvent override
        def _on_nas_badge_click(event):
            try:
                self._run_nas_sync()
            except Exception as _ex:
                _log_warning("MainWindow._on_nas_badge_click", exc=_ex)
        self.nas_status_badge.mousePressEvent = _on_nas_badge_click
        sb.addPermanentWidget(self.nas_status_badge)

        sb.addPermanentWidget(self._sb_separator())
        self.clock_label = QLabel("--:--:--")
        self.clock_label.setObjectName("ClockValue")
        sb.addPermanentWidget(self.clock_label)

        # v68-AI: AI learning indicator — shows how much the AI has
        # learned from the doctor. Click to open AI Asistan dashboard.
        sb.addPermanentWidget(self._sb_separator())
        self.ai_status_badge = QLabel("🤖 AI: yükleniyor...")
        self.ai_status_badge.setStyleSheet(
            "color:white;font:700 10px 'Segoe UI';"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #7C3AED,stop:1 #5A1FB8);"
            "padding:3px 10px;border-radius:9px;border:none;margin:2px;")
        self.ai_status_badge.setCursor(Qt.PointingHandCursor)
        self.ai_status_badge.setToolTip(
            "🤖 AI Asistan — kullanım analizi + kişisel öneriler\n"
            "Tıkla: dashboard aç (Ctrl+Shift+A)")

        def _on_ai_badge_click(event):
            try:
                self._show_ai_assistant_dashboard()
            except Exception as _ex:
                _log_warning(f"ai_badge click: {_ex}")
        self.ai_status_badge.mousePressEvent = _on_ai_badge_click
        sb.addPermanentWidget(self.ai_status_badge)

        # Schedule first refresh
        QTimer.singleShot(2000, self._refresh_ai_status_badge)
        # Periodic refresh every 60s
        self._ai_badge_timer = QTimer(self)
        self._ai_badge_timer.setInterval(60000)
        self._ai_badge_timer.timeout.connect(
            self._refresh_ai_status_badge)
        self._ai_badge_timer.start()

        # v68: Version pill — permanent reminder of which build is running
        sb.addPermanentWidget(self._sb_separator())
        ver_badge = QLabel(f"✨ {APP_VERSION}")
        ver_badge.setStyleSheet(
            "color:#FFFFFF;font:700 10.5px 'Segoe UI';"
            "padding:3px 10px;border-radius:9px;border:none;"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #0078D4,stop:1 #005A9E);"
            "margin:2px;")
        ver_badge.setToolTip(
            f"YazKlinik {APP_VERSION}\n"
            f"Premium UI overhaul · gradient hero headers")
        sb.addPermanentWidget(ver_badge)

        # Initial ready message on the left
        sb.showMessage("Hazır — F1 ile klavye kısayollarına bakabilirsiniz")
        self.stat_signature.set_state("warning")

    def _build_ui(self):
        central = BackgroundWidget()
        central.setObjectName("BackgroundRoot")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # Three-column splitter (resizable like real ViewPoint)
        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("MainSplitter")
        splitter.setHandleWidth(5)
        splitter.setChildrenCollapsible(False)
        root.addWidget(splitter, 1)

        # ─── Left: Patient Info + Worklist tree ──────────────────────────────
        left = self._build_left_panel()
        splitter.addWidget(left)

        # ─── Center: Tabs ────────────────────────────────────────────────────
        center = self._build_center_panel()
        splitter.addWidget(center)

        # ─── Right panel HIDDEN (v46.x) ──────────────────────────────────────
        # The vertical thumbnail sidebar is hidden per user feedback, but
        # we still add it to the splitter so its widgets (thumb_counter,
        # thumb_scroll, thumb_layout) stay alive. hide() was dropped because
        # Qt garbage-collected the C++ widgets, causing RuntimeError:
        # "Internal C++ object already deleted" on populate_files().
        # Solution: add to splitter BUT force zero width via setMaximumWidth.
        # This keeps the C++ objects alive without any visible UI strip.
        right = self._build_right_panel()
        right.setMaximumWidth(0)  # bullet-proof: widget exists but 0px wide
        right.setMinimumWidth(0)
        splitter.addWidget(right)

        # Initial sizes — right panel gets 0 width (invisible)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        # Left panel: 340px gives the patient list room to show full
        # Turkish names without ellipsis. v68-UI: widened from 290 because
        # the doctor reported names being clipped ("ru Erdogan" instead
        # of "Ebru Erdoğan").
        splitter.setSizes([340, 1420, 0])
        splitter.setCollapsible(2, True)
        # Disable the handle between center and right so the user can't
        # even drag it open accidentally
        try:
            h = splitter.handle(2)
            if h:
                h.setDisabled(True)
                h.setMaximumWidth(0)
        except Exception as _ex:
            _log_warning("MainWindow._build_ui", exc=_ex)

    def _build_left_panel(self) -> QWidget:
        w = QFrame()
        w.setObjectName("LeftPanel")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Patient Info header (top box) ──
        # v68-UI: Fixed size policy so this panel never grabs extra
        # vertical space — the patient + visits lists below get the
        # leftover room. Without this, Qt gave the PI grid a huge
        # share of the panel and the list got cramped to 2-3 items.
        pi_box = QFrame()
        pi_box.setObjectName("InfoBox")
        pi_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        # v68-UI: Cap the PI box height so it never eats into the
        # patient list's space. ~340px is enough for the 10 data rows
        # + name + badge. Beyond this, the list needs the room more.
        pi_box.setMaximumHeight(340)
        pi_lay = QVBoxLayout(pi_box)
        pi_lay.setContentsMargins(8, 6, 8, 8)
        pi_lay.setSpacing(2)

        pi_title = QLabel("👤  Hasta Bilgisi")
        pi_title.setObjectName("BoxTitle")
        pi_lay.addWidget(pi_title)

        self.pi_name_lbl = QLabel("— Hasta seçilmedi —")
        self.pi_name_lbl.setObjectName("PIName")
        self.pi_name_lbl.setWordWrap(True)
        pi_lay.addWidget(self.pi_name_lbl)

        self.pi_grid = QGridLayout()
        self.pi_grid.setHorizontalSpacing(6)
        self.pi_grid.setVerticalSpacing(2)
        self.pi_grid.setContentsMargins(0, 4, 0, 0)
        pi_lay.addLayout(self.pi_grid)

        self.pi_visit_count_lbl = self._pi_make_row("Geliş sayısı:", "0", row=0)
        self.pi_phone_lbl       = self._pi_make_row("Telefon:", get_default_whatsapp_number(), row=1)
        self.pi_last_visit_lbl  = self._pi_make_row("Son geliş:", "-", row=2)
        # v68: Surface medical demographics directly in the side panel
        # so the doctor sees them at a glance (instead of having to
        # open the F3 dialog every time). Empty values show "-".
        self.pi_age_lbl         = self._pi_make_row("Yaş:", "-", row=3)
        self.pi_blood_lbl       = self._pi_make_row("Kan grubu:", "-", row=4)
        self.pi_gpal_lbl        = self._pi_make_row("G/P/A/Y:", "-", row=5)
        self.pi_chronic_lbl     = self._pi_make_row("Kronik:", "-", row=6)
        self.pi_meds_lbl        = self._pi_make_row("İlaç:", "-", row=7)
        self.pi_allergies_lbl   = self._pi_make_row("Alerji:", "-", row=8)
        self.pi_signature_lbl   = self._pi_make_row("İmza:", "-", row=9)

        # ── Clickable signature buttons ────────────────────────────────
        # Previously hidden behind Belgeler → İmzasını Kaydet (Ctrl+I)
        # and a separate "İmza Takip" top-level tab. Both consolidated
        # into two small buttons right under the Patient Info panel so
        # the most frequent actions are one click away.
        sig_btn_row = QHBoxLayout()
        sig_btn_row.setContentsMargins(0, 4, 0, 0)
        sig_btn_row.setSpacing(4)

        self.pi_signature_btn = QPushButton("✍️  İmza Alındı")
        self.pi_signature_btn.setObjectName("PISigButton")
        self.pi_signature_btn.setCursor(Qt.PointingHandCursor)
        self.pi_signature_btn.setToolTip(
            "Bu geliş için takip imzasının alındığını işaretle "
            "(Ctrl+I kısayolu da çalışır)")
        self.pi_signature_btn.setStyleSheet(
            "QPushButton#PISigButton{"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #F0FAF0,stop:1 #E0F0E0);"
            "color:#0E5F0E;"
            "border:1.5px solid #9CCF9C;border-radius:6px;"
            "padding:7px 10px;font:600 11.5px 'Segoe UI';}"
            "QPushButton#PISigButton:hover{"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #CFEACF,stop:1 #B5DDB5);"
            "border-color:#107C10;color:#0B5D0B;}"
            "QPushButton#PISigButton:pressed{background:#A0D0A0;}")
        self.pi_signature_btn.clicked.connect(self.mark_signature_received)
        sig_btn_row.addWidget(self.pi_signature_btn, 1)

        # İmza Takip — opens a dialog with status + full history
        self.pi_sig_history_btn = QPushButton("📋  Takip")
        self.pi_sig_history_btn.setObjectName("PISigHistBtn")
        self.pi_sig_history_btn.setCursor(Qt.PointingHandCursor)
        self.pi_sig_history_btn.setToolTip(
            "Bu hastanın imza durumu ve geçmiş imzaları (son 5)")
        self.pi_sig_history_btn.setStyleSheet(
            "QPushButton#PISigHistBtn{"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #F0F6FC,stop:1 #E0EDF8);"
            "color:#005A9E;"
            "border:1.5px solid #B8D4E8;border-radius:6px;"
            "padding:7px 10px;font:600 11.5px 'Segoe UI';}"
            "QPushButton#PISigHistBtn:hover{"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #CCE4F7,stop:1 #B8D4E8);"
            "border-color:#0078D4;color:#003F6F;}")
        self.pi_sig_history_btn.clicked.connect(
            self._show_signature_history_dialog)
        sig_btn_row.addWidget(self.pi_sig_history_btn, 0)

        # v68-UI: Sil — undo the most recent signature event for this
        # patient. Useful when the doctor accidentally pressed İmza
        # Alındı or needs to redo. Compact red button.
        self.pi_sig_delete_btn = QPushButton("✕")
        self.pi_sig_delete_btn.setObjectName("PISigDelBtn")
        self.pi_sig_delete_btn.setCursor(Qt.PointingHandCursor)
        self.pi_sig_delete_btn.setToolTip(
            "Bu hastanın son imza kaydını sil "
            "(yanlışlıkla işaretlemişseniz)")
        self.pi_sig_delete_btn.setFixedWidth(34)
        self.pi_sig_delete_btn.setStyleSheet(
            "QPushButton#PISigDelBtn{"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #FCF0F0,stop:1 #F8E0E0);"
            "color:#9A1B1F;"
            "border:1.5px solid #E8B5B5;border-radius:6px;"
            "padding:7px 4px;font:700 13px 'Segoe UI';}"
            "QPushButton#PISigDelBtn:hover{"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #F4D0D0,stop:1 #E8B5B5);"
            "border-color:#D13438;color:#6E1316;}")
        self.pi_sig_delete_btn.clicked.connect(self._delete_last_signature)
        sig_btn_row.addWidget(self.pi_sig_delete_btn, 0)

        pi_lay.addLayout(sig_btn_row)

        lay.addWidget(pi_box)

        # ── Worklist tree + quick-access panel in a vertical splitter ──
        body_split = QSplitter(Qt.Vertical)
        body_split.setObjectName("LeftBodySplitter")
        body_split.setChildrenCollapsible(False)
        body_split.setHandleWidth(4)

        # Top half: Worklist
        wl_box = QFrame()
        wl_box.setObjectName("InfoBox")
        wl_lay = QVBoxLayout(wl_box)
        wl_lay.setContentsMargins(8, 6, 8, 8)
        wl_lay.setSpacing(4)

        # v68: Header with title + count pill (modern)
        wl_header = QHBoxLayout()
        wl_header.setContentsMargins(0, 0, 0, 0)
        wl_title = QLabel("👥  Hastalar")
        wl_title.setObjectName("BoxTitle")
        wl_header.addWidget(wl_title)
        wl_header.addStretch()
        self.patients_count_lbl = QLabel("0")
        self.patients_count_lbl.setStyleSheet(
            "color:#FFFFFF;font:700 11px 'Segoe UI';"
            "padding:3px 10px;border-radius:10px;border:none;"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #0078D4,stop:1 #005A9E);"
            "min-width:24px;")
        self.patients_count_lbl.setAlignment(Qt.AlignCenter)
        wl_header.addWidget(self.patients_count_lbl)
        wl_lay.addLayout(wl_header)

        # v68-UI-PREMIUM: Mini Dashboard — at-a-glance stats above
        # the patient list. Shows three colour-coded "pulse cards":
        #   • Bugün: today's visits (planned + completed)
        #   • Riskli: high-risk patients needing attention
        #   • Doğum: patients near delivery (≥36 wk or postterm)
        # Click any card to filter the patient list to that group.
        self._build_clinic_dashboard_widget(wl_lay)

        # Flat patient list (no expansion tree any more)
        self.patient_list = QListWidget()
        self.patient_list.setObjectName("WorkList")
        self.patient_list.setAlternatingRowColors(True)
        self.patient_list.setUniformItemSizes(True)
        self.patient_list.currentItemChanged.connect(self._on_patient_list_changed)
        wl_lay.addWidget(self.patient_list, 1)

        body_split.addWidget(wl_box)

        # ── Middle section: Visits of the selected patient ────────────────
        visits_box = QFrame()
        visits_box.setObjectName("InfoBox")
        vl_lay = QVBoxLayout(visits_box)
        vl_lay.setContentsMargins(8, 6, 8, 8)
        vl_lay.setSpacing(4)

        visits_header = QHBoxLayout()
        visits_title = QLabel("📅  Gelişler")
        visits_title.setObjectName("BoxTitle")
        visits_header.addWidget(visits_title)
        visits_header.addStretch()
        self.visits_count_lbl = QLabel("0")
        self.visits_count_lbl.setStyleSheet(
            "color:#FFFFFF;font:700 11px 'Segoe UI';"
            "padding:3px 10px;border-radius:10px;border:none;"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #0078D4,stop:1 #005A9E);"
            "min-width:24px;")
        self.visits_count_lbl.setAlignment(Qt.AlignCenter)
        visits_header.addWidget(self.visits_count_lbl)
        vl_lay.addLayout(visits_header)

        self.visits_list = QListWidget()
        self.visits_list.setObjectName("WorkList")
        self.visits_list.setAlternatingRowColors(True)
        self.visits_list.setUniformItemSizes(True)
        self.visits_list.currentItemChanged.connect(self._on_visits_list_changed)
        vl_lay.addWidget(self.visits_list, 1)

        body_split.addWidget(visits_box)

        # Bottom half: Quick-access tabs (Bugün / İmza Bekleyen / İstatistik)
        quick_box = QFrame()
        quick_box.setObjectName("InfoBox")
        quick_lay = QVBoxLayout(quick_box)
        quick_lay.setContentsMargins(4, 4, 4, 4)
        quick_lay.setSpacing(2)

        self.quick_tabs = QTabWidget()
        self.quick_tabs.setObjectName("QuickTabs")
        self.quick_tabs.setDocumentMode(True)

        # Tab 1: Today's visits
        today_tab = QWidget()
        tl = QVBoxLayout(today_tab)
        tl.setContentsMargins(2, 2, 2, 2)
        tl.setSpacing(2)
        today_header = QHBoxLayout()
        today_header.setSpacing(4)
        self.today_count_lbl = QLabel("📍 Bugün: 0 hasta")
        self.today_count_lbl.setStyleSheet(
            "color:#003F6F;font:700 12px 'Segoe UI';padding:4px 6px;"
            "background:transparent;border:none;")
        today_refresh = QPushButton("↻")
        today_refresh.setObjectName("MiniBtn")
        today_refresh.setFixedSize(24, 24)
        today_refresh.setToolTip("Listeyi yenile")
        today_refresh.setStyleSheet(
            "QPushButton{background:#F0F6FC;color:#005A9E;"
            "border:1px solid #B8D4E8;border-radius:12px;"
            "font:700 13px 'Segoe UI';}"
            "QPushButton:hover{background:#0078D4;color:#FFFFFF;"
            "border-color:#005A9E;}")
        today_refresh.clicked.connect(self._refresh_quick_panels)
        today_header.addWidget(self.today_count_lbl)
        today_header.addStretch()
        today_header.addWidget(today_refresh)
        tl.addLayout(today_header)

        self.today_list = QListWidget()
        self.today_list.setObjectName("WorkList")
        self.today_list.itemDoubleClicked.connect(self._on_quick_item_activated)
        tl.addWidget(self.today_list, 1)
        self.quick_tabs.addTab(today_tab, "📍 Bugün")

        # Tab 2: Pending signatures
        sig_tab = QWidget()
        sl = QVBoxLayout(sig_tab)
        sl.setContentsMargins(2, 2, 2, 2)
        sl.setSpacing(2)
        self.pending_sig_count_lbl = QLabel("✍️ İmza bekleyen: 0")
        self.pending_sig_count_lbl.setStyleSheet(
            "color:#C46500;font:700 12px 'Segoe UI';padding:4px 6px;"
            "background:transparent;border:none;")
        sl.addWidget(self.pending_sig_count_lbl)

        self.pending_sig_list = QListWidget()
        self.pending_sig_list.setObjectName("WorkList")
        self.pending_sig_list.itemDoubleClicked.connect(self._on_quick_item_activated)
        sl.addWidget(self.pending_sig_list, 1)
        self.quick_tabs.addTab(sig_tab, "✍️ İmza")

        # Tab 3: Stats
        stats_tab = QWidget()
        st = QVBoxLayout(stats_tab)
        st.setContentsMargins(8, 8, 8, 8)
        st.setSpacing(4)
        # Subtle gradient header card on top of stats
        stats_hero = QLabel(
            "<div style='text-align:center;padding:8px 4px;'>"
            "<div style='font-size:18px;'>📈</div>"
            "<div style='font-size:11px;color:#003F6F;"
            "font-weight:700;margin-top:2px;'>KLİNİK ÖZETİ</div>"
            "</div>")
        stats_hero.setTextFormat(Qt.RichText)
        stats_hero.setStyleSheet(
            "QLabel{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #F0F6FC, stop:1 #E0EDF8);"
            "border:1px solid #B8D4E8;border-radius:6px;"
            "padding:6px;}")
        st.addWidget(stats_hero)
        self.stats_labels = {}
        for key, label, emoji in [
            ("today",    "Bugün",        "📍"),
            ("week",     "Bu hafta",     "📅"),
            ("month",    "Bu ay",        "🗓️"),
            ("patients", "Toplam hasta", "👥"),
            ("visits",   "Toplam geliş", "📋"),
        ]:
            row = QHBoxLayout()
            row.setSpacing(6)
            row.setContentsMargins(4, 3, 4, 3)
            lbl = QLabel(f"{emoji}  {label}")
            lbl.setStyleSheet(
                "color:#404040;font:500 11.5px 'Segoe UI';"
                "background:transparent;border:none;")
            val = QLabel("–")
            val.setStyleSheet(
                "color:#FFFFFF;font:700 11px 'Segoe UI';"
                "padding:2px 10px;border-radius:9px;border:none;"
                "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                "stop:0 #0078D4,stop:1 #005A9E);"
                "min-width:24px;")
            val.setAlignment(Qt.AlignCenter)
            row.addWidget(lbl)
            row.addStretch()
            row.addWidget(val)
            st.addLayout(row)
            self.stats_labels[key] = val
        st.addStretch(1)
        self.quick_tabs.addTab(stats_tab, "📊 İstatistik")

        quick_lay.addWidget(self.quick_tabs)

        body_split.addWidget(quick_box)
        body_split.setStretchFactor(0, 5)  # Hastalar — en çok
        body_split.setStretchFactor(1, 3)  # Gelişler — orta
        body_split.setStretchFactor(2, 1)  # Quick tabs — en az
        # v68-UI: 3-part vertical split. Patient list gets ~55%,
        # visits list ~30%, quick tabs ~15%. The patient+visits lists
        # are the primary workspace; quick tabs are secondary.
        body_split.setSizes([500, 280, 140])

        lay.addWidget(body_split, 1)
        return w

    def _build_center_panel(self) -> QWidget:
        w = QFrame()
        w.setObjectName("CenterPanel")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("MainTabs")
        self.tabs.setDocumentMode(False)
        self.tabs.setMovable(False)
        self.tabs.setTabPosition(QTabWidget.North)

        # ── v68: "Rapor" tab unifies "Ana PDF" (edit existing) + "Yeni PDF"
        # (build from scratch) under a single top-level tab so the doctor
        # doesn't have to hunt across two tabs. Internal sub-tabs let them
        # switch between the two modes without leaving "Rapor".
        # v68 note: "İmza Takip" tab was removed from the top bar per
        # doctor's request. Its content (status + last-5 history table)
        # now opens as a popup dialog via the "📋 İmza Takip" button in
        # the Patient Info panel. The underlying widgets (signature_btn,
        # signature_history_table, etc.) are still built — just hosted
        # in the dialog rather than a tab.
        self.tabs.addTab(self._build_tab_summary(),   "Hasta Özeti")
        self.tabs.addTab(self._build_tab_report(),    "📄 Rapor")
        self.tabs.addTab(self._build_tab_images(),    "Görüntüler")
        self.tabs.addTab(self._build_tab_dicom(),     "📡 DICOM")
        self.tabs.addTab(self._build_tab_videos(),    "Videolar")
        self.tabs.addTab(self._build_tab_notes(),     "Notlar")
        # v68: Jinekolojik Takip tab — hidden by default, shown when
        # the app is in gynecology mode (via manual toggle or auto-
        # detected from a gynecologic patient). Contains form fields
        # for endometrial thickness, AMH, AFC, follicle measurements,
        # prior treatments, etc.
        self._gynec_tab_widget = self._build_tab_gynec_followup()
        self._gynec_tab_index = self.tabs.addTab(
            self._gynec_tab_widget, "🌸 Jinekolojik Takip")
        # Hide by default — will be shown when mode is gynecologic
        self.tabs.setTabVisible(self._gynec_tab_index, False)

        # v68: "📋 Gebelik Takibi" tab — pregnancy follow-up form.
        # Default visible in obstetric mode. Hidden only when the app
        # flips into gynecology mode. The F6 quick-action button shows
        # the printable "Gebelik Takvimi" handout (milestone schedule)
        # — to access the FORM the doctor opens this tab directly.
        self._obs_tab_widget = self._build_tab_obstetric_followup()
        self._obs_tab_index = self.tabs.addTab(
            self._obs_tab_widget, "📋 Gebelik Takibi")
        # Visible by default — obstetric is the most common mode
        self.tabs.setTabVisible(self._obs_tab_index, True)

        # Build the (now-headless) signature widget and park it in a
        # hidden host so it stays alive — the "İmza Takip" dialog
        # grabs it and re-parents it on demand.
        self._signature_tab_widget = self._build_tab_signature()
        self._signature_tab_widget.setParent(self)
        self._signature_tab_widget.hide()
        # New tab order: 0=Özet, 1=Ana PDF, 2=Görüntüler, 3=DICOM,
        # 4=Videolar, 5=Yeni PDF, 6=Notlar, 7=İmza
        self._videos_tab_index = 4
        self._dicom_tab_index = 3
        # Lazy-load handler: the PDF editor is expensive; load only when the
        # user opens that tab and a reload is pending.
        self._pending_editor_reload: bool = False
        self.tabs.currentChanged.connect(self._on_main_tab_changed)

        lay.addWidget(self.tabs, 1)
        return w

    def _build_right_panel(self) -> QWidget:
        w = QFrame()
        w.setObjectName("RightPanel")
        lay = QVBoxLayout(w)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.setSpacing(4)

        # Title
        ttl = QLabel("Görüntüler")
        ttl.setObjectName("BoxTitle")
        lay.addWidget(ttl)

        # Scroll area for thumbnails
        self.thumb_scroll = QScrollArea()
        self.thumb_scroll.setObjectName("ThumbScroll")
        self.thumb_scroll.setWidgetResizable(True)
        self.thumb_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.thumb_scroll.setFrameShape(QFrame.StyledPanel)

        self.thumb_host = QWidget()
        self.thumb_host.setObjectName("ThumbHost")
        self.thumb_layout = QVBoxLayout(self.thumb_host)
        self.thumb_layout.setContentsMargins(2, 2, 2, 2)
        self.thumb_layout.setSpacing(4)
        self.thumb_layout.addStretch(1)
        self.thumb_scroll.setWidget(self.thumb_host)

        lay.addWidget(self.thumb_scroll, 1)

        # Counter at bottom
        self.thumb_counter = QLabel("0 / 0")
        self.thumb_counter.setObjectName("ThumbCounter")
        self.thumb_counter.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.thumb_counter)

        return w

    def _build_tab_summary(self) -> QWidget:
        page = QWidget()
        page.setObjectName("TabPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Header strip — visit info
        # v68: This light-blue strip ("Geliş: 20.04.2026 ...") is HIDDEN
        # per doctor's request. The visit date now lives inside the
        # main clinical banner, freeing vertical space so the PDF pane
        # below starts higher up.
        # visit_info_label is still built & updated — other code paths
        # (toolbar drift-banner, flag rows) reference it — but the
        # container strip isn't added to the layout.
        hdr = QFrame()
        hdr.setObjectName("InfoStrip")
        hl = QHBoxLayout(hdr)
        hl.setContentsMargins(8, 4, 8, 4)
        hl.setSpacing(12)
        self.visit_info_label = QLabel("Geliş seçilmedi")
        self.visit_info_label.setObjectName("VisitInfo")
        hl.addWidget(self.visit_info_label)
        hl.addStretch()
        self.twin_badge = QLabel("İKİZ GEBELİK")
        self.twin_badge.setObjectName("TwinBadge")
        self.twin_badge.hide()
        hl.addWidget(self.twin_badge)
        # Keep the strip alive (parent = page) but don't add it to the
        # layout — this prevents the label from being GC'd while freeing
        # ~28px of vertical space for the PDF pane.
        hdr.setParent(page)
        hdr.hide()

        # ── Klinik özet banner'ı (at-a-glance pregnancy info) ─────────────
        # Most important info the doctor needs when opening a patient: how
        # many weeks, when's EDD, when was last visit. Prominent "hero"
        # style so it's readable at a glance during a busy clinic.
        # v68 polish: drop shadow + larger radius + slightly deeper
        # gradient — looks like a premium medical app.
        self.clinical_banner = QLabel("")
        self.clinical_banner.setObjectName("ClinicalBanner")
        self.clinical_banner.setWordWrap(True)
        self.clinical_banner.setTextFormat(Qt.RichText)
        self.clinical_banner.setMinimumHeight(70)
        self.clinical_banner.setStyleSheet(
            "QLabel#ClinicalBanner{"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #003F6F, stop:0.5 #005A9E, stop:1 #0078D4);"
            "color:#FFFFFF;"
            "border:none;"
            "border-radius:10px;"
            "padding:18px 24px;"
            "font:600 14px 'Segoe UI';}"
            "QLabel#ClinicalBanner:hover{"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #002B4C, stop:0.5 #003F6F, stop:1 #005A9E);}")
        # Drop shadow for premium look
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            shadow = QGraphicsDropShadowEffect()
            shadow.setBlurRadius(18)
            shadow.setColor(QColor(0, 90, 158, 100))
            shadow.setOffset(0, 4)
            self.clinical_banner.setGraphicsEffect(shadow)
        except Exception as _ex:
            _log_warning("clinical banner: shadow", exc=_ex)
        self.clinical_banner.setCursor(Qt.PointingHandCursor)
        self.clinical_banner.setToolTip(
            "Tıkla → kan grubu, Rh, obstetrik öykü, ilaçlar düzenle")
        # Click handler
        def _banner_click(event):
            try:
                self._show_demographics_dialog()
            except Exception as _ex:
                _log_warning("MainWindow._banner_click", exc=_ex)
        self.clinical_banner.mousePressEvent = _banner_click
        self.clinical_banner.hide()
        lay.addWidget(self.clinical_banner)

        # ── v68: Welcome empty state (shown when no patient is selected)
        # When the doctor has just opened the app or de-selected a patient,
        # the summary tab is otherwise empty. Show a friendly welcome card
        # with quick onboarding hints — much warmer than a blank pane.
        clinic_doctor = get_clinic_doctor_name() if hasattr(
            sys.modules[__name__], "get_clinic_doctor_name") else "Doktorum"
        try:
            clinic_doctor = get_clinic_doctor_name() or "Doktorum"
        except Exception:
            clinic_doctor = "Doktorum"
        self.welcome_card = QLabel()
        self.welcome_card.setObjectName("WelcomeCard")
        self.welcome_card.setTextFormat(Qt.RichText)
        self.welcome_card.setWordWrap(True)
        self.welcome_card.setAlignment(Qt.AlignCenter)
        self.welcome_card.setText(
            f"""
            <div style='text-align:center;padding:36px 28px;'>
                <div style='font-size:64px;margin-bottom:6px;'>🏥</div>
                <div style='font-size:26px;font-weight:800;
                color:#003F6F;margin-bottom:4px;letter-spacing:-0.3px;'>
                    Hoş Geldiniz, {clinic_doctor}
                </div>
                <div style='font-size:13px;color:#0078D4;
                font-weight:600;margin-bottom:18px;'>
                    YazKlinik · Kadın Hastalıkları ve Doğum
                </div>
                <div style='font-size:13px;color:#606060;
                margin-bottom:28px;line-height:1.7;
                max-width:480px;margin-left:auto;margin-right:auto;'>
                    Sol panelden bir hasta seçin. Tüm USG raporları,
                    geliş geçmişi, takip planı ve klinik bayraklar
                    bir tıkla erişilebilir.
                </div>
                <table cellpadding='0' cellspacing='0' style='margin:0 auto;'>
                <tr>
                <td style='text-align:center;padding:0 6px;'>
                  <div style='background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                  stop:0 #FFFFFF, stop:1 #F0F6FC);
                  border:1px solid #B8D4E8;border-radius:10px;
                  padding:16px 20px;min-width:104px;'>
                    <div style='font-size:34px;'>🆕</div>
                    <div style='font-size:12px;color:#003F6F;
                    font-weight:700;margin-top:6px;'>Yeni Hasta</div>
                    <div style='font-size:10px;color:#0078D4;
                    font-weight:600;background:#E5F1FB;
                    padding:2px 6px;border-radius:8px;
                    display:inline-block;margin-top:4px;'>Ctrl+N</div>
                  </div>
                </td>
                <td style='text-align:center;padding:0 6px;'>
                  <div style='background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                  stop:0 #FFFFFF, stop:1 #F0F6FC);
                  border:1px solid #B8D4E8;border-radius:10px;
                  padding:16px 20px;min-width:104px;'>
                    <div style='font-size:34px;'>🔍</div>
                    <div style='font-size:12px;color:#003F6F;
                    font-weight:700;margin-top:6px;'>Hasta Ara</div>
                    <div style='font-size:10px;color:#0078D4;
                    font-weight:600;background:#E5F1FB;
                    padding:2px 6px;border-radius:8px;
                    display:inline-block;margin-top:4px;'>Ctrl+F</div>
                  </div>
                </td>
                <td style='text-align:center;padding:0 6px;'>
                  <div style='background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                  stop:0 #FFFFFF, stop:1 #F0F6FC);
                  border:1px solid #B8D4E8;border-radius:10px;
                  padding:16px 20px;min-width:104px;'>
                    <div style='font-size:34px;'>📊</div>
                    <div style='font-size:12px;color:#003F6F;
                    font-weight:700;margin-top:6px;'>İstatistik</div>
                    <div style='font-size:10px;color:#909090;
                    font-weight:600;background:#F0F0F0;
                    padding:2px 6px;border-radius:8px;
                    display:inline-block;margin-top:4px;'>İstatistik</div>
                  </div>
                </td>
                <td style='text-align:center;padding:0 6px;'>
                  <div style='background:qlineargradient(x1:0,y1:0,x2:0,y2:1,
                  stop:0 #FFFFFF, stop:1 #F0F6FC);
                  border:1px solid #B8D4E8;border-radius:10px;
                  padding:16px 20px;min-width:104px;'>
                    <div style='font-size:34px;'>⌨️</div>
                    <div style='font-size:12px;color:#003F6F;
                    font-weight:700;margin-top:6px;'>Kısayollar</div>
                    <div style='font-size:10px;color:#0078D4;
                    font-weight:600;background:#E5F1FB;
                    padding:2px 6px;border-radius:8px;
                    display:inline-block;margin-top:4px;'>F1</div>
                  </div>
                </td>
                </tr>
                </table>
                <div style='margin-top:32px;font-size:11px;color:#909090;
                font-style:italic;'>
                    💡 İpucu: Toolbar'daki <b style='color:#0078D4;'>🤰
                    Obstetrik / 🌸 Jinekolojik</b> butonu ile mod
                    değiştirebilirsiniz
                </div>
            </div>
            """)
        self.welcome_card.setStyleSheet(
            "QLabel#WelcomeCard{"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #FFFFFF,stop:1 #F4F8FC);"
            "border:1px solid #D8E4EE;"
            "border-radius:12px;"
            "padding:20px;"
            "}")
        # Subtle drop shadow
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            wsh = QGraphicsDropShadowEffect()
            wsh.setBlurRadius(20)
            wsh.setColor(QColor(0, 90, 158, 60))
            wsh.setOffset(0, 4)
            self.welcome_card.setGraphicsEffect(wsh)
        except Exception as _ex:
            _log_warning("welcome card shadow", exc=_ex)

        # v68-AI: Big "Yeni Hasta Kayıt" action button under the welcome
        # card. Same premium gradient style as the quick-action buttons
        # (Hasta Bilgileri, Bayraklar, etc) but full-width and larger.
        # Tıklanınca obstetrik / jinekolojik seçimi sunan dialog açar.
        # Mod değişimi sırasında bile her zaman erişilebilir olsun diye
        # welcome alanına yerleştirildi.
        self.welcome_container = QWidget()
        wc_lay = QVBoxLayout(self.welcome_container)
        wc_lay.setContentsMargins(0, 0, 0, 0)
        wc_lay.setSpacing(14)
        wc_lay.addWidget(self.welcome_card)

        self.new_patient_card_btn = QPushButton("  🆕   Yeni Hasta Kayıt")
        self.new_patient_card_btn.setCursor(Qt.PointingHandCursor)
        self.new_patient_card_btn.setMinimumHeight(46)
        self.new_patient_card_btn.setMaximumHeight(46)
        self.new_patient_card_btn.setToolTip(
            "Yeni hasta kayıt — Obstetrik (gebelik) veya "
            "Jinekolojik (kadın hastalıkları) seçimi yapın\n\n"
            "Kısayol: Ctrl+N")
        # v68-AI: Compact pill-style button (matches quick action style
        # but slim — doctor doesn't want a huge green slab on welcome)
        self.new_patient_card_btn.setStyleSheet(
            "QPushButton{"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #00A676,stop:1 #007F58);"
            "color:#FFFFFF;"
            "border:1.5px solid #005A3F;"
            "padding:6px 22px;"
            "font:700 13px 'Segoe UI';"
            "border-radius:10px;"
            "text-align:center;"
            "letter-spacing:-0.2px;"
            "}"
            "QPushButton:hover{"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #007F58,stop:1 #005A3F);"
            "border:2px solid #FFFFFF;"
            "}"
            "QPushButton:pressed{"
            "background:#005A3F;"
            "}")
        # Drop shadow for premium depth (matches quick-action buttons)
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            np_sh = QGraphicsDropShadowEffect()
            np_sh.setBlurRadius(14)
            np_sh.setColor(QColor(0, 90, 60, 80))
            np_sh.setOffset(0, 3)
            self.new_patient_card_btn.setGraphicsEffect(np_sh)
        except Exception as _ex:
            _log_warning("new patient card shadow", exc=_ex)
        self.new_patient_card_btn.clicked.connect(
            self._open_new_patient_dialog)
        # Center the button — don't let it span the whole width
        np_row = QHBoxLayout()
        np_row.addStretch()
        np_row.addWidget(self.new_patient_card_btn)
        np_row.addStretch()
        wc_lay.addLayout(np_row)

        lay.addWidget(self.welcome_container)

        # ── Patient flag ribbon (split: red danger + green good) ──────────
        # Two ribbons side-by-side. Left = danger/warning flags (red/orange
        # bar, "DİKKAT: ..."). Right = good/reassuring flags (green bar,
        # "✓ ..."). Each ribbon hides itself when its list is empty.
        self.flag_ribbon_container = QWidget()
        self.flag_ribbon_container.setObjectName("FlagRibbonContainer")
        frc_lay = QHBoxLayout(self.flag_ribbon_container)
        frc_lay.setContentsMargins(0, 0, 0, 0)
        frc_lay.setSpacing(8)

        self.flag_ribbon = QLabel("")  # danger/warning half (kept name for
                                       # backward compat with callers)
        self.flag_ribbon.setWordWrap(True)
        self.flag_ribbon.setObjectName("FlagRibbon")
        self.flag_ribbon.setStyleSheet(
            "QLabel#FlagRibbon{"
            "color:#FFFFFF;"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #8B1F14, stop:0.5 #C42B1C, stop:1 #E04A3C);"
            "border:none;"
            "border-radius:10px;"
            "font:700 13.5px 'Segoe UI';padding:12px 18px;}")
        # Drop shadow for danger
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            rsh = QGraphicsDropShadowEffect()
            rsh.setBlurRadius(14)
            rsh.setColor(QColor(196, 43, 28, 120))
            rsh.setOffset(0, 3)
            self.flag_ribbon.setGraphicsEffect(rsh)
        except Exception as _ex:
            _log_warning("flag ribbon shadow", exc=_ex)
        self.flag_ribbon.hide()
        frc_lay.addWidget(self.flag_ribbon, 1)

        self.flag_ribbon_good = QLabel("")  # green good-flags half
        self.flag_ribbon_good.setWordWrap(True)
        self.flag_ribbon_good.setObjectName("FlagRibbonGood")
        self.flag_ribbon_good.setStyleSheet(
            "QLabel#FlagRibbonGood{"
            "color:#FFFFFF;"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #0B5D0B, stop:0.5 #107C10, stop:1 #4DA84D);"
            "border:none;"
            "border-radius:10px;"
            "font:700 13.5px 'Segoe UI';padding:12px 18px;}")
        try:
            gsh2 = QGraphicsDropShadowEffect()
            gsh2.setBlurRadius(14)
            gsh2.setColor(QColor(16, 124, 16, 120))
            gsh2.setOffset(0, 3)
            self.flag_ribbon_good.setGraphicsEffect(gsh2)
        except Exception as _ex:
            _log_warning("flag ribbon good shadow", exc=_ex)
        self.flag_ribbon_good.hide()
        frc_lay.addWidget(self.flag_ribbon_good, 1)

        self.flag_ribbon_container.hide()
        lay.addWidget(self.flag_ribbon_container)

        # ── Quick Actions row ─────────────────────────────────────────────
        # The features added over v50→v65 live in deep menus (Hasta →
        # Diyet Listesi, Düzenle → Uzun Özet, etc.). Surfacing the six
        # most-used per-patient actions right here — at the top of the
        # patient summary tab, always visible when a patient is selected
        # — gives the doctor one-click access to every hand-out he
        # produces during a visit. Keyboard shortcuts are also attached
        # (F2-F8) so hands never have to leave the keyboard.
        self.quick_actions_box = QFrame()
        self.quick_actions_box.setObjectName("QuickActionsBox")
        self.quick_actions_box.setStyleSheet(
            "QFrame#QuickActionsBox{"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #FAFCFE,stop:1 #EBF3FB);"
            "border:1.5px solid #B8D4E8;"
            "border-radius:10px;"
            "}")
        qa_lay = QHBoxLayout(self.quick_actions_box)
        qa_lay.setContentsMargins(12, 10, 12, 10)
        qa_lay.setSpacing(8)

        qa_title = QLabel("⚡")
        qa_title.setToolTip("Hızlı Eylemler — F2-F8 kısayolları")
        qa_title.setStyleSheet(
            "color:#005A9E;font:700 16px 'Segoe UI';background:transparent;"
            "border:none;padding:0 4px;")
        qa_lay.addWidget(qa_title)

        # Each button: (label, emoji, tooltip, shortcut, slot_name, color_pair)
        # color_pair = (gradient_start, gradient_end, border_color, text_color)
        _quick_buttons = [
            ("Kısa Özet",  "📝",
             "Sadece seçili gelişin özeti (PDF'den) + doktor notu → "
             "panoya kopyala. Kısa, pratik özet — WhatsApp için ideal.",
             "Ctrl+Shift+X",  "copy_summary",
             ("#4A90E2", "#2E6FB5", "#1F5287", "#FFFFFF")),  # Açık mavi
            ("Uzun Özet",  "📋",
             "Demografik bilgiler + bayraklar + tüm notlar + son ziyaret "
             "→ panoya kopyala (hasta takip programına yüklemek, "
             "konsültasyon, devir teslim için)",
             "F2",  "copy_long_summary",
             ("#0078D4", "#005A9E", "#003F6F", "#FFFFFF")),  # Mavi — primary
            ("Hasta Bilgileri", "👤",
             "Demografik bilgiler, kronik hastalıklar, ilaçlar, "
             "alerjiler, G/P/A/L, doğum tercihi",
             "F3",  "_show_demographics_dialog",
             ("#00A676", "#007F58", "#005A3F", "#FFFFFF")),  # Yeşil turkuaz
            # v68: Bayraklar butonu — "🏷️ Bayrakları Düzenle" butonu
            # daha önce "Bu Hafta Yapılabilecekler" kutusunun içindeydi.
            # Kutu jinekoloji modunda gizlendiğinde buton da kayboldu.
            # Burada ayrı bir quick-action olarak ekliyoruz — her iki
            # modda da her zaman görünür. Mode-aware editor dialog açar.
            ("Bayraklar", "🏷️",
             "Hasta bayrakları — obstetrik modda gebelik bayrakları, "
             "jinekoloji modda infertilite / jinekoloji bayrakları",
             "Ctrl+B",  "_open_flag_editor_dialog",
             ("#E8A500", "#C46500", "#8C4A00", "#FFFFFF")),  # Turuncu
            ("Test Listesi", "🧪",
             "Hastaya bugün ve bundan sonra yapılacak tetkikleri "
             "A4 olarak yazdır",
             "F4",  "_show_patient_test_sheet",
             ("#B5368A", "#8B2A6D", "#6F2256", "#FFFFFF")),  # Pembe
            ("Planlama", "📋",
             "Planlama menüsü:\n"
             "  • Gebelik Takibi — LMP'den doğuma tüm milestone'lar "
             "(A4 yazdırılır)\n"
             "  • Tetkik Listesi — Bu gebelik haftasında yapılması "
             "gereken tetkikler (A5 yazdırılır)",
             "F6",  "_show_planlama_menu",
             ("#6C4EC4", "#513899", "#3A2770", "#FFFFFF")),  # Mor
            ("Diyet Listesi", "🍎",
             "Gebelik / GDM / sınırda şeker diyet planı — "
             "düzenlenebilir, A4 yazdırılabilir",
             "F7",  "_show_diet_sheet_dialog",
             ("#4DA84D", "#107C10", "#0B5D0B", "#FFFFFF")),  # Yeşil
            ("Büyüme Eğrileri", "📈",
             "Fetal büyüme ölçümlerinin zamansal grafiği "
             "(biparietal çap, karın çevresi, femur, ağırlık)",
             "F8",  "_show_growth_trend_dialog",
             ("#D13438", "#9A1B1F", "#6E1316", "#FFFFFF")),  # Kırmızı
            # v68-UI-PREMIUM: Klinik Akıl — automatic risk scoring + insights
            ("Klinik Akıl", "🧠",
             "Otomatik risk skorlaması + akıllı klinik içgörüler:\n"
             "  • Yaş, GPAL, kronik hastalık, ilaç ve bayraklara göre risk skoru\n"
             "  • ACOG/RCOG temelli önerilen tetkikler ve eylemler\n"
             "  • Eksik takip uyarıları (NIPT, OGTT, anomali, Tdap, vb.)\n"
             "  • Teratojen ilaç tespiti\n"
             "  • Düzensiz takip + uzun gap analizi\n"
             "Tüm hesaplamalar yardımcıdır — son kararı doktor verir.",
             "Ctrl+Shift+I",  "_show_clinical_intelligence_dialog",
             ("#7C3AED", "#5A1FB8", "#3F1480", "#FFFFFF")),  # Indigo / mor
            # v68-UI-PREMIUM: Onam Formları — printable consent library
            ("Onam Formları", "📋",
             "Onam formları kütüphanesi (Obstetrik / Jinekolojik / "
             "Lazer / Medikal Estetik / Jinekolojik Estetik). "
             "Tek tık → A4 yazdır.",
             "Ctrl+Shift+O",  "_show_consent_forms_dialog",
             ("#005A9E", "#003F6F", "#002A4F", "#FFFFFF")),  # Lacivert
            # v68-UI-PREMIUM: Hazır Reçeteler — printable Rx templates
            ("Hazır Reçete", "💊",
             "Hazır reçete şablonları kütüphanesi. "
             "Tek tık → A5 yazdır.",
             "Ctrl+Alt+R",  "_show_prescription_dialog",
             ("#0B5D0B", "#085008", "#053C05", "#FFFFFF")),  # Koyu yeşil
            # v68-AI: Doğum Kaydet — record patient delivery
            ("Doğum Kaydet", "🤱",
             "Hasta doğurdu — doğum tipi (normal/sezaryen/vakum/forseps) "
             "ve detayları kaydet. Hasta gebelik takibinden çıkar, "
             "Doğuranlar grubuna alınır. Postpartum takip başlar.",
             "Ctrl+Shift+D",  "_show_record_delivery_dialog",
             ("#B5368A", "#8B2A6D", "#6F2256", "#FFFFFF")),  # Pembe
            # v68-AI: Tahliller — ayrı buton (eski Test Listesi'nin yerinde)
            ("Tahliller", "📋",
             "PDF tahlil yükle (e-Nabız veya laboratuar). "
             "Değerler otomatik çıkarılır, tarihli arşiv oluşur. "
             "Tetkik istemi bu kayıtlara göre öneri üretir.",
             "Ctrl+Shift+L",  "_show_lab_tracker_dialog",
             ("#0078D4", "#005A9E", "#003F6F", "#FFFFFF")),  # Mavi
        ]

        # v68: Track quick-action buttons by semantic key so we can
        # change their label dynamically when the doctor flips between
        # obstetric and gynecologic mode (the F6 button changes
        # between "Obstetrik Takip" and "Jinekolojik Takip").
        self._qa_buttons: dict = {}

        for label, emoji, tip, shortcut, slot, colors in _quick_buttons:
            c_start, c_end, c_border, c_text = colors
            btn = QPushButton(f"{emoji}\n{label}")
            btn.setToolTip(f"{tip}\n\nKısayol: {shortcut}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(72)
            # v68-UI-PREMIUM: Colored gradient card buttons — each
            # button gets its own brand colour so the doctor can
            # quickly locate the action they need via colour memory.
            btn.setStyleSheet(
                f"QPushButton{{"
                f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                f"stop:0 {c_start},stop:1 {c_end});"
                f"color:{c_text};"
                f"border:1.5px solid {c_border};"
                f"padding:8px 6px;"
                f"font:700 11.5px 'Segoe UI';"
                f"border-radius:10px;"
                f"text-align:center;"
                f"}}"
                f"QPushButton:hover{{"
                f"background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
                f"stop:0 {c_end},stop:1 {c_border});"
                f"border:1.5px solid #FFFFFF;"
                f"}}"
                f"QPushButton:pressed{{"
                f"background:{c_border};"
                f"}}")
            # Drop shadow for premium depth
            try:
                from PySide6.QtWidgets import QGraphicsDropShadowEffect
                from PySide6.QtGui import QColor
                sh = QGraphicsDropShadowEffect()
                sh.setBlurRadius(12)
                sh.setColor(QColor(0, 0, 0, 70))
                sh.setOffset(0, 3)
                btn.setGraphicsEffect(sh)
            except Exception as _ex:
                _log_warning("qa btn shadow", exc=_ex)
            # Deferred slot lookup so the order of mixin definitions
            # doesn't matter at this point
            btn.clicked.connect(
                lambda _checked=False, s=slot: self._quick_action_dispatch(s))
            # Keyboard shortcut
            sc = QShortcut(QKeySequence(shortcut), self)
            sc.activated.connect(
                lambda s=slot: self._quick_action_dispatch(s))
            qa_lay.addWidget(btn, 1)   # stretch=1 → equal widths
            # Register buttons by semantic key so we can manipulate
            # them later (relabel, hide, etc) based on mode.
            if slot == "_open_followup_tab_for_mode":
                self._qa_buttons["followup"] = btn
            elif slot == "_show_growth_trend_dialog":
                # v68: The Büyüme Eğrileri (growth curves) button is
                # meaningful only in obstetric mode — gyn patients have
                # no fetus, so the graph is empty / irrelevant.
                # _refresh_quick_action_labels() hides this button
                # entirely when the mode flips to gynecologic.
                self._qa_buttons["growth"] = btn

        self.quick_actions_box.setToolTip(
            "Sık kullanılan hasta eylemleri — fareyle tıkla ya da "
            "F2-F8 kısayollarını kullan.")
        lay.addWidget(self.quick_actions_box)

        # ── Weekly clinical recommendations panel ─────────────────────────
        # Shows GA-specific perinatology recommendations (what tests/actions
        # are due at the current gestational week). Only visible when there
        # are active recommendations.
        #
        # v68 layout: the right side of this yellow box hosts the compact
        # "Bayrakları Düzenle" button + inline WhatsApp input, so we don't
        # need a separate row below. Saves ~40-50px of vertical space.
        self.ga_recommendations_box = QFrame()
        self.ga_recommendations_box.setObjectName("GARecBox")
        self.ga_recommendations_box.setStyleSheet(
            "QFrame#GARecBox{"
            "background:qlineargradient(x1:0,y1:0,x2:0,y2:1,"
            "stop:0 #FFF9E6,stop:1 #FFEFC0);"
            "border:1.5px solid #E8B800;"
            "border-left:5px solid #C46500;"
            "border-radius:8px;}")
        # Drop shadow for premium depth
        try:
            from PySide6.QtWidgets import QGraphicsDropShadowEffect
            from PySide6.QtGui import QColor
            gsh = QGraphicsDropShadowEffect()
            gsh.setBlurRadius(12)
            gsh.setColor(QColor(232, 184, 0, 80))
            gsh.setOffset(0, 3)
            self.ga_recommendations_box.setGraphicsEffect(gsh)
        except Exception as _ex:
            _log_warning("ga rec shadow", exc=_ex)
        rec_outer = QHBoxLayout(self.ga_recommendations_box)
        rec_outer.setContentsMargins(14, 10, 14, 10)
        rec_outer.setSpacing(12)

        # Left: recommendations text (title + content), takes all
        # remaining width
        rec_left = QVBoxLayout()
        rec_left.setContentsMargins(0, 0, 0, 0)
        rec_left.setSpacing(4)
        self.ga_recommendations_title = QLabel(
            "📋 <b>Bu Hafta Yapılabilecekler</b>")
        self.ga_recommendations_title.setStyleSheet(
            "color:#7A5A00;font:800 13px 'Segoe UI';"
            "background:transparent;border:none;")
        rec_left.addWidget(self.ga_recommendations_title)
        self.ga_recommendations_content = QLabel("")
        self.ga_recommendations_content.setWordWrap(True)
        self.ga_recommendations_content.setTextFormat(Qt.RichText)
        self.ga_recommendations_content.setStyleSheet(
            "color:#333333;font:500 11.5px 'Segoe UI';"
            "background:transparent;border:none;")
        rec_left.addWidget(self.ga_recommendations_content)
        rec_outer.addLayout(rec_left, 1)  # stretch = 1

        # Right: compact flag-edit button + WhatsApp input, stacked
        # vertically to take minimal horizontal width.
        rec_right = QVBoxLayout()
        rec_right.setContentsMargins(0, 0, 0, 0)
        rec_right.setSpacing(6)
        rec_right.setAlignment(Qt.AlignTop)

        flag_edit_btn = QPushButton("🏷️  Bayrakları Düzenle")
        flag_edit_btn.setStyleSheet(
            "QPushButton{background:#FFFFFF;color:#005A9E;"
            "border:1px solid #A8C8E8;border-radius:3px;"
            "padding:5px 12px;font:600 11px 'Segoe UI';}"
            "QPushButton:hover{background:#E5EEF7;border-color:#0078D4;}")
        flag_edit_btn.setToolTip(
            "Hasta bayraklarını düzenle — bu hastanın risk/durum "
            "etiketlerini işaretle veya kaldır. "
            "Aktif bayraklar üstteki kırmızı çubukta görünür.")
        flag_edit_btn.setCursor(Qt.PointingHandCursor)
        flag_edit_btn.clicked.connect(self._open_flag_editor_dialog)
        rec_right.addWidget(flag_edit_btn)

        # Inline WhatsApp editor — same input the compact bar had, moved here
        wa_row = QHBoxLayout()
        wa_row.setContentsMargins(0, 0, 0, 0)
        wa_row.setSpacing(4)
        phone_lbl = QLabel("📱")
        phone_lbl.setStyleSheet(
            "color:#606060;font:600 12px 'Segoe UI';background:transparent;"
            "border:none;")
        phone_lbl.setToolTip("Hasta WhatsApp numarası")
        wa_row.addWidget(phone_lbl)
        self.phone_input_compact = QLineEdit(get_default_whatsapp_number())
        self.phone_input_compact.setObjectName("PhoneBox")
        self.phone_input_compact.setPlaceholderText("905321234567")
        self.phone_input_compact.setClearButtonEnabled(True)
        self.phone_input_compact.setFixedWidth(160)
        self.phone_input_compact.setStyleSheet(
            "QLineEdit#PhoneBox{background:#FFFFFF;border:1px solid #C8C8C8;"
            "border-radius:3px;padding:3px 6px;font:500 11px 'Segoe UI';}")
        self.phone_input_compact.setToolTip(
            "Bu hastaya özel WhatsApp numarası — yazdıkça kaydedilir")
        self.phone_input_compact.editingFinished.connect(
            self._on_compact_phone_changed)
        wa_row.addWidget(self.phone_input_compact)
        rec_right.addLayout(wa_row)

        rec_outer.addLayout(rec_right, 0)  # stretch = 0 (fixed-ish width)

        self.ga_recommendations_box.hide()
        lay.addWidget(self.ga_recommendations_box)

        # ── Hidden flag checkbox host ─────────────────────────────────
        # The actual QCheckBox widgets for each flag live here,
        # permanently hidden. `_load_patient_flags_into_ui`, `_on_flag_toggled`
        # and the editor dialog reference them via `self._flag_checkboxes`.
        # Qt requires a parent to keep C++ objects alive, so we add this
        # to the main layout (but .hide() it so there's no visual impact).
        #
        # The user-visible "Bayrakları Düzenle" button now lives INSIDE
        # the yellow "Bu Hafta Yapılabilecekler" box (right side), saving
        # the entire height of this panel.
        self._flag_checkboxes: dict = {}
        # v68: Also store the gynecologic-set checkboxes separately so
        # we can swap in the right set when the mode toggles.
        self._gynec_flag_checkboxes: dict = {}
        self._flag_hidden_host = QFrame()
        self._flag_hidden_host.hide()
        _hidden_layout = QGridLayout(self._flag_hidden_host)
        severity_rank = {"danger": 0, "warning": 1, "good": 2, "info": 3}
        sorted_flags = sorted(
            enumerate(PATIENT_FLAGS),
            key=lambda x: (severity_rank.get(x[1][2], 99), x[0]))
        for idx, (_orig_idx, (key, label, level)) in enumerate(sorted_flags):
            cb = QCheckBox(label)
            cb.toggled.connect(
                lambda checked, k=key: self._on_flag_toggled(k, checked))
            self._flag_checkboxes[key] = cb
            _hidden_layout.addWidget(cb, idx // 3, idx % 3)
        # v68: Gynecologic flag checkboxes — separate set for jinekoloji
        # mode. Stored in a second hidden host; the flag editor dialog
        # selects the right host based on mode.
        self._gynec_flag_hidden_host = QFrame()
        self._gynec_flag_hidden_host.hide()
        _gynec_hidden_layout = QGridLayout(self._gynec_flag_hidden_host)
        sorted_gynec = sorted(
            enumerate(GYNEC_FLAGS),
            key=lambda x: (severity_rank.get(x[1][2], 99), x[0]))
        for idx, (_orig_idx, (key, label, level)) in enumerate(sorted_gynec):
            cb = QCheckBox(label)
            cb.toggled.connect(
                lambda checked, k=key: self._on_flag_toggled(k, checked))
            self._gynec_flag_checkboxes[key] = cb
            _gynec_hidden_layout.addWidget(cb, idx // 3, idx % 3)
        lay.addWidget(self._flag_hidden_host)
        lay.addWidget(self._gynec_flag_hidden_host)

        # ── Phone / WhatsApp row ────────────────────────────────────────────
        # NOTE (user feedback): This row was previously shown prominently
        # at the top of the summary tab. The doctor asked to remove it —
        # the WhatsApp number is already editable from the toolbar's
        # WhatsApp button / Ctrl+Shift+W. We still build the widgets
        # because other code references phone_input_summary, and we
        # still add the frame to the layout so Qt owns the widgets
        # (without that, Qt GC-deletes the C++ objects and any later
        # access raises "Internal C++ object already deleted").
        # The frame itself is hide()d so nothing shows.
        phone_box = QFrame()
        phone_box.setObjectName("InnerBox")
        pb = QHBoxLayout(phone_box)
        pb.setContentsMargins(10, 8, 10, 8)
        pb.setSpacing(8)

        ptt = QLabel("📱  Hasta WhatsApp No:")
        ptt.setStyleSheet(
            "color:#005A9E;font:700 13px 'Segoe UI';background:transparent;")
        pb.addWidget(ptt)

        self.phone_input_summary = QLineEdit(get_default_whatsapp_number())
        self.phone_input_summary.setObjectName("PhoneBox")
        self.phone_input_summary.setPlaceholderText("90 ile başlayan 12 haneli no")
        self.phone_input_summary.setClearButtonEnabled(True)
        self.phone_input_summary.setMinimumWidth(220)
        self.phone_input_summary.textChanged.connect(
            self._on_summary_phone_changed)
        self.phone_input_summary.editingFinished.connect(
            self.save_current_patient_phone)
        pb.addWidget(self.phone_input_summary)

        self.phone_mark_summary = QLabel("● ÖZEL")
        self.phone_mark_summary.setObjectName("PhoneMark")
        self.phone_mark_summary.setToolTip(
            "Bu hastaya özel numara (varsayılandan farklı). "
            "Veritabanında saklanıyor ve bir dahaki sefere otomatik gelir.")
        self.phone_mark_summary.hide()
        pb.addWidget(self.phone_mark_summary)

        self.phone_saved_summary = QLabel("✓ Kayıtlı")
        self.phone_saved_summary.setObjectName("SaveStatus")
        self.phone_saved_summary.hide()
        pb.addWidget(self.phone_saved_summary)

        pb.addStretch()

        # Save + WhatsApp buttons — kept alive in layout but hidden
        save_phone_btn = ActionButton("💾 Kaydet")
        save_phone_btn.setToolTip(
            "Bu telefon numarasını bu hasta için veritabanına kaydet")
        save_phone_btn.clicked.connect(self.save_current_patient_phone)
        pb.addWidget(save_phone_btn)

        wa_btn = ActionButton("📤 WhatsApp Gönder", primary=True)
        wa_btn.setToolTip("WhatsApp'ı aç + özet/klasörü panoya kopyala")
        wa_btn.clicked.connect(self.prepare_whatsapp)
        pb.addWidget(wa_btn)

        # Add to layout BUT hide — widgets need a parent to stay alive
        # (Qt C++ objects get garbage-collected if they're parentless).
        lay.addWidget(phone_box)
        phone_box.hide()

        # ── Top: summary HTML box — fixed-ish height ─────────────────────────
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setObjectName("SummaryText")
        self.summary_text.setMinimumHeight(180)
        self.summary_text.setMaximumHeight(280)
        self.summary_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        lay.addWidget(self.summary_text)

        # ── Bottom: embedded PDF viewer — takes the rest ────────────────────
        pdfhdr = QLabel("PDF (seçili gelişten)")
        pdfhdr.setObjectName("BoxTitle")
        lay.addWidget(pdfhdr)
        self.pdf_viewer = PdfViewer()
        self.pdf_viewer.setMinimumHeight(300)
        lay.addWidget(self.pdf_viewer, 1)

        # Bottom button bar
        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        self.copy_btn = ActionButton("Özeti Kopyala", primary=True)
        self.copy_btn.clicked.connect(self.copy_summary)
        self.open_folder_btn = ActionButton("Klasörü Aç")
        self.open_folder_btn.clicked.connect(self.open_folder)
        self.print_btn = ActionButton("PDF Yazdır")
        self.print_btn.clicked.connect(self.print_current_pdf)
        zoom_lbl = QLabel("PDF yakınlaştırma:")
        zoom_lbl.setStyleSheet("color:#606060;")
        self.summary_zoom_out_btn = QPushButton("−")
        self.summary_zoom_out_btn.setObjectName("MiniBtn")
        self.summary_zoom_out_btn.setFixedSize(28, 24)
        self.summary_zoom_out_btn.setToolTip("PDF'i uzaklaştır (Ctrl+-)")
        self.summary_zoom_out_btn.clicked.connect(
            lambda: self.pdf_viewer.set_zoom(self.pdf_viewer.zoom() - 0.15))
        self.summary_zoom_in_btn = QPushButton("+")
        self.summary_zoom_in_btn.setObjectName("MiniBtn")
        self.summary_zoom_in_btn.setFixedSize(28, 24)
        self.summary_zoom_in_btn.setToolTip("PDF'i yakınlaştır (Ctrl++)")
        self.summary_zoom_in_btn.clicked.connect(
            lambda: self.pdf_viewer.set_zoom(self.pdf_viewer.zoom() + 0.15))
        btn_row.addWidget(zoom_lbl)
        btn_row.addWidget(self.summary_zoom_out_btn)
        btn_row.addWidget(self.summary_zoom_in_btn)
        btn_row.addStretch()
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.open_folder_btn)
        btn_row.addWidget(self.print_btn)
        lay.addLayout(btn_row)

        return page

    def _build_tab_images(self) -> QWidget:
        """Images tab — single-purpose NAS folder gallery with large thumbnails.
        DICOM previews live in their own dedicated tab now (see _build_tab_dicom)."""
        page = QWidget()
        page.setObjectName("TabPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        hdr.setSpacing(6)
        title = QLabel("Görüntüler")
        title.setObjectName("BoxTitle")
        hdr.addWidget(title)
        hdr.addStretch()
        self.gallery_count_lbl = QLabel("0 resim")
        self.gallery_count_lbl.setStyleSheet(
            "color:#606060;font:600 12px 'Segoe UI';padding:2px 8px;"
            "background:#F0F0F0;border:1px solid #C8C8C8;")
        hdr.addWidget(self.gallery_count_lbl)
        lay.addLayout(hdr)

        # Hint
        hint = QLabel(
            "Bir resme tıkla → büyük önizleme açılır (◀ ▶ ile gez)."
            "   •   Tıklayıp sürükle → Ana PDF sayfasına bırak."
        )
        hint.setStyleSheet(subtle_text_style(font_size=11, padding="2px"))
        hint.setWordWrap(True)
        lay.addWidget(hint)

        # Big scrollable grid
        self.gallery_scroll = QScrollArea()
        self.gallery_scroll.setObjectName("ImageScroll")
        self.gallery_scroll.setWidgetResizable(True)
        self.gallery_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.gallery_host = QWidget()
        self.gallery_host.setObjectName("GalleryHost")
        self.gallery_host.setStyleSheet("background:#F5F5F5;")
        self.gallery_grid = QGridLayout(self.gallery_host)
        self.gallery_grid.setContentsMargins(12, 12, 12, 12)
        self.gallery_grid.setSpacing(12)
        self.gallery_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.gallery_scroll.setWidget(self.gallery_host)

        # Wrap the gallery scroll in a QStackedWidget so we can swap in
        # the inline preview (QFrame) without ever opening a new window.
        # Page 0 = thumbnails grid (default view)
        # Page 1 = preview panel (created on demand in _open_gallery_preview)
        self.gallery_stack = QStackedWidget()
        self.gallery_stack.addWidget(self.gallery_scroll)  # index 0
        lay.addWidget(self.gallery_stack, 1)

        self._gallery_paths: List[Path] = []
        return page

    def _build_tab_pdf(self) -> QWidget:
        """Yeni PDF — yeniden tasarım.

        Sol: Canlı PDF önizleme (sayfaları büyük göster, scroll edilebilir)
        Sağ üst: Eklenecek görüntüler galerisi (hastanın resimleri)
              → drag-and-drop'la sol PDF tuvaline atılır
        Sağ alt: Şablon + sayfa düzeni + hasta bilgisi başlığı + yazı ekleme
        Alt: PDF Oluştur · Son PDF Aç · Önceki PDF Aç (dropdown)
        """
        # Interactive page widgets for the Yeni PDF tab — each one is a
        # PdfPageEditWidget (same widget Ana PDF uses) so all of its
        # drag/drop/swap/resize/cross-page behaviour works identically.
        # Populated by _refresh_pdf_canvas; rebuilt on every change.
        self._new_pdf_pages: List["PdfPageEditWidget"] = []
        # Number of user-created pages (separate from USG cover which is
        # always a read-only preview)
        if not hasattr(self, "_new_pdf_page_count"):
            self._new_pdf_page_count = 1  # start with 1 empty page

        page = QWidget()
        page.setObjectName("TabPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # v68: The "📄 Yeni PDF" title label was removed from here
        # because the sub-tab label above already says it — the doctor
        # asked for the extra header to be dropped for a cleaner,
        # menu-continuity look matching Mevcut PDF.
        hdr_lay = QHBoxLayout()
        hdr_lay.addStretch()
        # Status indicator (right-aligned, no big title needed)
        self.pdf_status_label = QLabel("Hazır.")
        self.pdf_status_label.setStyleSheet(
            "color:#606060;font:600 11px 'Segoe UI';padding:2px 8px;"
            "background:#F0F0F0;border:1px solid #C8C8C8;")
        hdr_lay.addWidget(self.pdf_status_label)
        lay.addLayout(hdr_lay)

        # ── Top settings row ─────────────────────────────────────────────
        opt_box = QFrame()
        opt_box.setObjectName("InnerBox")
        opt_box.setStyleSheet(
            "QFrame#InnerBox{background:#F8F8F8;border:1px solid #C8C8C8;}")
        ob = QHBoxLayout(opt_box)
        ob.setContentsMargins(8, 6, 8, 6)
        ob.setSpacing(8)

        # Layout mode: 1/2/3 columns per row (legacy — kept for compat)
        ob.addWidget(QLabel("Düzen:"))
        self.pdf_layout_mode = QComboBox()
        self.pdf_layout_mode.addItems([
            "Otomatik (resim sayısına göre)",
            "1 sütun (ortalanmış)",
            "2 resim (yan yana)",
            "3 resim (2 üst + 1 alt)",
            "4 resim (2×2)",
            "6 resim (3×2)",
            "9 resim (3×3)",
        ])
        self.pdf_layout_mode.setCurrentIndex(0)
        # DO NOT auto-refresh on combo change — triggers legacy rebuild
        # which destroys interactive overlays. Doctor must hit Uygula.
        ob.addWidget(self.pdf_layout_mode)

        # Apply-layout button — mirrors Ana PDF's ↻ Uygula
        self.pdf_apply_layout_btn = QPushButton("↻ Uygula")
        self.pdf_apply_layout_btn.setObjectName("MiniBtn")
        self.pdf_apply_layout_btn.setCursor(Qt.PointingHandCursor)
        self.pdf_apply_layout_btn.setToolTip(
            "Seçili düzeni görünen Yeni PDF sayfasındaki resimlere uygula")
        self.pdf_apply_layout_btn.clicked.connect(
            self._new_pdf_apply_layout_to_visible)
        ob.addWidget(self.pdf_apply_layout_btn)

        # Patient header on first page?
        self.pdf_include_header = QCheckBox("Hasta bilgisi başlığı (1. sayfa)")
        self.pdf_include_header.setChecked(True)
        self.pdf_include_header.toggled.connect(self._refresh_pdf_canvas)
        ob.addWidget(self.pdf_include_header)

        # USG cover page — first page of the visit's USG report as cover.
        # This is the doctor's explicit request: PDF starts with the USG
        # report page, then the images follow on pages 2+.
        self.pdf_include_usg_cover = QCheckBox("📄 İlk sayfa: USG Raporu (kapak)")
        self.pdf_include_usg_cover.setChecked(True)
        self.pdf_include_usg_cover.setToolTip(
            "Oluşturulan PDF'in ilk sayfası olarak hastanın bu gelişteki "
            "USG raporunun 1. sayfasını otomatik koyar. Eklediğiniz "
            "resimler ve yazılar 2. sayfadan başlar.")
        self.pdf_include_usg_cover.toggled.connect(self._refresh_pdf_canvas)
        ob.addWidget(self.pdf_include_usg_cover)

        # Quick template — copies header text from front page of summary PDF
        ob.addWidget(QLabel("Şablon:"))
        self.pdf_template_combo = QComboBox()
        self.pdf_template_combo.addItems([
            "(şablon yok)",
            "Standart Ultrason Raporu",
            "Anomali Tarama Raporu",
            "Doppler İncelemesi",
        ])
        self.pdf_template_combo.currentIndexChanged.connect(self._refresh_pdf_canvas)
        ob.addWidget(self.pdf_template_combo)

        ob.addStretch()

        # Add free text annotation
        self.pdf_addtext_btn = QPushButton("✏️ Yazı Ekle")
        self.pdf_addtext_btn.setObjectName("MiniBtn")
        self.pdf_addtext_btn.setCursor(Qt.PointingHandCursor)
        self.pdf_addtext_btn.setToolTip(
            "PDF'e serbest metin ekle — başlık, not, açıklama. "
            "Sıraya alınır, görüntüler arasında veya sonunda yer alır.")
        self.pdf_addtext_btn.clicked.connect(self._pdf_add_text_annotation)
        ob.addWidget(self.pdf_addtext_btn)

        # Add saved template text (the doctor's reusable text blocks)
        self.pdf_addtmpl_btn = QPushButton("📝 Şablon Ekle")
        self.pdf_addtmpl_btn.setObjectName("MiniBtn")
        self.pdf_addtmpl_btn.setCursor(Qt.PointingHandCursor)
        self.pdf_addtmpl_btn.setToolTip(
            "Önceden kaydedilmiş şablon yazılarınızı PDF'e ekleyin "
            "(resimlerin altında veya ayrı sayfada belirir)")
        self.pdf_addtmpl_btn.clicked.connect(self._pdf_add_template_block)
        ob.addWidget(self.pdf_addtmpl_btn)

        # New: explicit "Yeni Sayfa" button — forces a page break so the
        # next item starts on a fresh page regardless of what fits
        self.pdf_newpage_btn = QPushButton("➕ Yeni Sayfa")
        self.pdf_newpage_btn.setObjectName("MiniBtn")
        self.pdf_newpage_btn.setCursor(Qt.PointingHandCursor)
        self.pdf_newpage_btn.setToolTip(
            "Sıradaki öğeyi yeni bir sayfada başlatır (sayfa arası boşluk)")
        self.pdf_newpage_btn.clicked.connect(self._new_pdf_add_page)
        ob.addWidget(self.pdf_newpage_btn)

        # Delete last page — inverse of Yeni Sayfa, with undo support
        self.pdf_delpage_btn = QPushButton("🗑 Sayfayı Sil")
        self.pdf_delpage_btn.setObjectName("MiniBtn")
        self.pdf_delpage_btn.setCursor(Qt.PointingHandCursor)
        self.pdf_delpage_btn.setToolTip(
            "Son sayfayı sil (üzerindeki resim/yazılarla birlikte). "
            "Ctrl+Z ile geri alınabilir.")
        self.pdf_delpage_btn.clicked.connect(self._new_pdf_delete_last_page)
        ob.addWidget(self.pdf_delpage_btn)

        # Clear all
        self.pdf_clear_btn = QPushButton("🗑 Temizle")
        self.pdf_clear_btn.setObjectName("MiniBtn")
        self.pdf_clear_btn.setCursor(Qt.PointingHandCursor)
        self.pdf_clear_btn.setToolTip(
            "PDF kanvasındaki tüm öğeleri sil — sıfırdan başla. "
            "Geri alınamaz, dikkat!")
        self.pdf_clear_btn.clicked.connect(self._new_pdf_clear_all)
        ob.addWidget(self.pdf_clear_btn)

        # v68: Layout-template buttons ("Düzeni Kaydet" + "Şablon Uygula")
        # were removed per doctor's request. "Şablon Ekle" (text-block
        # insertion) is the only template entry point now — simpler and
        # matches the Mevcut PDF flow. The underlying methods are still
        # callable from Belgeler menu (Ctrl+T) if needed.

        lay.addWidget(opt_box)

        # ── Main split: left = preview, right = source images + extras ──
        main_split = QSplitter(Qt.Horizontal)
        main_split.setHandleWidth(6)
        main_split.setChildrenCollapsible(False)

        # LEFT: PDF page preview (vertical scroll of A4 pages)
        left_box = QFrame()
        left_box.setObjectName("InnerBox")
        ll = QVBoxLayout(left_box)
        ll.setContentsMargins(6, 6, 6, 6)
        ll.setSpacing(4)
        ll_hdr = QHBoxLayout()
        ll_title = QLabel("📋 Sayfa Düzeni Önizleme")
        ll_title.setStyleSheet(accent_label_style(font_size=11))
        ll_hdr.addWidget(ll_title)
        ll_hdr.addStretch()
        self.pdf_page_count_lbl = QLabel("0 sayfa · 0 resim")
        self.pdf_page_count_lbl.setStyleSheet(
            "color:#606060;font:600 10px 'Segoe UI';background:transparent;")
        ll_hdr.addWidget(self.pdf_page_count_lbl)
        ll.addLayout(ll_hdr)

        self.pdf_canvas_scroll = QScrollArea()
        self.pdf_canvas_scroll.setWidgetResizable(True)
        self.pdf_canvas_scroll.setStyleSheet(
            "QScrollArea{background:#E0E0E0;border:1px solid #A8A8A8;}")
        self.pdf_canvas_host = QWidget()
        self.pdf_canvas_host.setStyleSheet("background:#E0E0E0;")
        self.pdf_canvas_layout = QVBoxLayout(self.pdf_canvas_host)
        self.pdf_canvas_layout.setContentsMargins(20, 20, 20, 20)
        self.pdf_canvas_layout.setSpacing(15)
        self.pdf_canvas_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.pdf_canvas_scroll.setWidget(self.pdf_canvas_host)
        ll.addWidget(self.pdf_canvas_scroll, 1)
        main_split.addWidget(left_box)

        # RIGHT: source images — same vertical strip as Ana PDF so the
        # doctor gets the exact same look & feel on both tabs.
        right_box = QFrame()
        right_box.setObjectName("InnerBox")
        rl = QVBoxLayout(right_box)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setSpacing(4)

        rl_hdr = QHBoxLayout()
        rl_title = QLabel("🖼️ Eklenebilir Resimler")
        rl_title.setStyleSheet(accent_label_style(font_size=11))
        rl_hdr.addWidget(rl_title)
        rl_hdr.addStretch()
        self.pdf_source_count_lbl = QLabel("0 resim")
        self.pdf_source_count_lbl.setStyleSheet(
            "color:#606060;font:600 10px 'Segoe UI';background:transparent;")
        rl_hdr.addWidget(self.pdf_source_count_lbl)
        rl.addLayout(rl_hdr)

        # Hint — exactly matching Ana PDF's wording for consistency
        rl_hint = QLabel(
            "<i style='color:#606060;font-size:10px;'>"
            "Sürükle → sol PDF sayfasına bırak<br>"
            "veya çift tıkla → son sayfaya ekle<br>"
            "Üzerine gel → büyük önizleme</i>")
        rl_hint.setTextFormat(Qt.RichText)
        rl_hint.setWordWrap(True)
        rl_hint.setStyleSheet(transparent_icon_button_style())
        rl.addWidget(rl_hint)

        # Scrollable vertical strip — same as Ana PDF.
        # Uses DraggableThumb (hover-zoomable) instead of ImageGalleryThumb
        # so the doctor gets the big-preview-on-hover behaviour they're
        # already used to.
        self.pdf_source_scroll = QScrollArea()
        self.pdf_source_scroll.setWidgetResizable(True)
        self.pdf_source_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pdf_source_scroll.setStyleSheet(
            "QScrollArea{background:#FFFFFF;border:1px solid #C8C8C8;}")
        self.pdf_source_host = QWidget()
        self.pdf_source_host.setStyleSheet("background:#FFFFFF;")
        # Single-column VERTICAL layout — matches Ana PDF exactly
        self.pdf_source_layout = QVBoxLayout(self.pdf_source_host)
        self.pdf_source_layout.setContentsMargins(4, 4, 4, 4)
        self.pdf_source_layout.setSpacing(4)
        self.pdf_source_layout.addStretch()
        self.pdf_source_scroll.setWidget(self.pdf_source_host)
        rl.addWidget(self.pdf_source_scroll, 1)

        # Legacy attribute kept for backward-compat (some older code may
        # still check hasattr). Points to the vertical layout now.
        self.pdf_source_grid = None

        main_split.addWidget(right_box)
        # 75/25 split — same ratio as Ana PDF, so the canvas stays big
        main_split.setSizes([1200, 280])
        main_split.setStretchFactor(0, 1)
        main_split.setStretchFactor(1, 0)
        lay.addWidget(main_split, 1)

        # ── Bottom action row ─────────────────────────────────────────────
        act = QHBoxLayout()
        act.setSpacing(6)

        self.pdf_open_last_btn = ActionButton("📂 Son PDF'i Aç")
        self.pdf_open_last_btn.clicked.connect(self._open_last_built_pdf)
        act.addWidget(self.pdf_open_last_btn)

        # Previous PDFs dropdown
        act.addWidget(QLabel("Önceki PDF:"))
        self.pdf_previous_combo = QComboBox()
        self.pdf_previous_combo.setMinimumWidth(220)
        self.pdf_previous_combo.setToolTip(
            "Bu hastanın daha önce oluşturulmuş PDF'leri")
        act.addWidget(self.pdf_previous_combo)
        self.pdf_open_prev_btn = ActionButton("Aç")
        self.pdf_open_prev_btn.clicked.connect(self._open_selected_previous_pdf)
        act.addWidget(self.pdf_open_prev_btn)

        act.addStretch()

        self.pdf_build_btn = ActionButton("✓ PDF Oluştur", primary=True)
        self.pdf_build_btn.setMinimumWidth(160)
        self.pdf_build_btn.clicked.connect(self.build_pdf_from_selection)
        act.addWidget(self.pdf_build_btn)
        lay.addLayout(act)

        # State for the new canvas-based builder
        # _pdf_canvas_items: list of dicts describing each item to render
        #   each dict: {"type": "image"|"text"|"header", ...kwargs}
        self._pdf_canvas_items: List[dict] = []
        # Old code paths still reference some of these names, so keep dummies:
        self.pdf_title_input = QLineEdit()
        self.pdf_include_note = QCheckBox()
        self.pdf_include_note.setChecked(False)
        self.pdf_include_summary = QCheckBox()
        self.pdf_include_summary.setChecked(False)
        # Compatibility: legacy build_pdf_from_selection iterates over
        # self.image_checks (set elsewhere) — keep honoured.

        return page

    def _build_tab_obstetric_followup(self) -> QWidget:
        """Build the "🤰 Obstetrik Takip" tab — patient-centric form
        for pregnancy follow-up. Mirrors the gynec form's structure
        but tailored for obstetric concerns: LMP/EDD/GA, vital signs,
        gebelik şikâyetleri, fetal hareket, USG bulguları, eski
        gebelikler, risk faktörleri, plan.

        Auto-saves to obstetric_form table keyed on patient_key.
        """
        page = QWidget()
        page.setObjectName("TabPage")
        outer_lay = QVBoxLayout(page)
        outer_lay.setContentsMargins(8, 8, 8, 8)
        outer_lay.setSpacing(6)

        # Header
        hdr = QHBoxLayout()
        title = QLabel("🤰 Obstetrik / Gebelik Takip")
        title.setObjectName("BoxTitle")
        title.setStyleSheet(
            "color:#003A66;font:700 15px 'Segoe UI';padding:4px 0;")
        hdr.addWidget(title)

        # v68-UI: Kısa İzlem checkbox — collapses non-essential
        # sections so routine visits aren't overwhelming. Default on.
        self.obs_short_chk = QCheckBox("📝 Kısa İzlem")
        self.obs_short_chk.setChecked(get_short_followup_mode())
        self.obs_short_chk.setToolTip(
            "Kısa İzlem AÇIK: sadece sık kullanılan alanlar görünür "
            "(Vital Signs, Şikayetler, Fetal İzlem, Plan).\n"
            "KAPALI: tüm bölümler (aile öyküsü, genetik, detaylı USG vs.) "
            "açılır — uzun ilk muayene için ideal.")
        self.obs_short_chk.setCursor(Qt.PointingHandCursor)
        self.obs_short_chk.setStyleSheet(
            "QCheckBox{color:#003A66;font:600 11px 'Segoe UI';"
            "padding:4px 10px;background:#E5F1FB;"
            "border:1px solid #B8D4E8;border-radius:4px;}"
            "QCheckBox:hover{background:#CCE4F7;}"
            "QCheckBox::indicator{width:16px;height:16px;}")
        self.obs_short_chk.toggled.connect(self._on_obs_short_toggled)
        hdr.addSpacing(12)
        hdr.addWidget(self.obs_short_chk)
        hdr.addStretch()
        self.obs_save_lbl = QLabel("✓ Kaydedildi")
        self.obs_save_lbl.setStyleSheet(
            "color:#107C10;font:600 10px 'Segoe UI';background:transparent;")
        self.obs_save_lbl.hide()
        hdr.addWidget(self.obs_save_lbl)
        outer_lay.addLayout(hdr)

        # Scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet(
            "QScrollArea{border:none;background:transparent;}")
        host = QWidget()
        host.setObjectName("ObsFormHost")
        host.setStyleSheet("background:#F0F7FC;")
        lay = QVBoxLayout(host)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(12)

        self._obs_form_widgets: dict = {}

        # v68-UI: For Kısa İzlem mode, we need to hide non-essential
        # sections. Each call to _section_header() creates a NEW QFrame
        # that subsequent _field_row() calls populate. The frame is
        # registered for visibility toggling.
        # CORE sections stay visible in compact mode.
        self._obs_section_frames: dict = {}  # key → QFrame
        self._obs_active_section_lay: list = [None]  # current section layout
        OBS_CORE_SECTIONS = {
            "vitals", "complaints", "fetal", "plan",
        }

        # Auto-numbered section keys when caller doesn't provide one.
        # We need a clean shim that works without modifying every old
        # _section_header / _field_row call site.
        _section_counter = [0]
        # Map auto-numbered keys to semantic labels for the CORE check
        # (we'll fill this manually right after the section is created
        # using _set_section_key()).
        self._obs_section_key_for_pos: dict = {}

        def _section_header(emoji_text: str) -> QFrame:
            """Create a section: a QFrame containing the header label
            and (later) all field rows for that section. Returns the
            FRAME — caller must add it to the parent layout via
            lay.addWidget(). Subsequent _field_row() calls go into
            this section's layout.
            """
            _section_counter[0] += 1
            section_key = f"sec_{_section_counter[0]}"
            frame = QFrame()
            frame.setObjectName(f"ObsSection_{section_key}")
            frame.setStyleSheet(
                "QFrame[objectName^='ObsSection']{"
                "background:transparent;border:none;}")
            section_lay = QVBoxLayout(frame)
            section_lay.setContentsMargins(0, 0, 0, 0)
            section_lay.setSpacing(6)
            hdr = QLabel(emoji_text)
            hdr.setStyleSheet(
                "color:#FFFFFF;background:qlineargradient("
                "x1:0,y1:0,x2:1,y2:0,stop:0 #003A66,stop:1 #0078D4);"
                "padding:6px 12px;border-radius:4px;"
                "font:700 12px 'Segoe UI';")
            section_lay.addWidget(hdr)
            self._obs_section_frames[section_key] = frame
            self._obs_active_section_lay[0] = section_lay
            # Hint: figure out the section's semantic key from the emoji
            # text so we can keep CORE sections visible in compact mode.
            etext = emoji_text.lower()
            if any(t in etext for t in ("vital", "muayene", "📊")):
                self._obs_section_key_for_pos[section_key] = "vitals"
            elif any(t in etext for t in ("şikay", "şikâ", "⚠")):
                self._obs_section_key_for_pos[section_key] = "complaints"
            elif any(t in etext for t in ("fetal", "👶", "izlem")):
                self._obs_section_key_for_pos[section_key] = "fetal"
            elif any(t in etext for t in ("plan", "📝", "not")):
                self._obs_section_key_for_pos[section_key] = "plan"
            else:
                self._obs_section_key_for_pos[section_key] = section_key
            return frame

        def _field_row(label_text: str, widget: QWidget,
                       tooltip: str = "") -> QHBoxLayout:
            row = QHBoxLayout()
            row.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setMinimumWidth(180)
            lbl.setStyleSheet(
                "color:#404040;font:500 11px 'Segoe UI';")
            row.addWidget(lbl)
            if tooltip:
                widget.setToolTip(tooltip)
            row.addWidget(widget, 1)
            # v68-UI: Attach this row to the current section's layout
            # so it gets hidden/shown together with the section frame.
            # The caller's `_field_row(...)` will then
            # try to add the row to `lay` — but since the row already
            # has a parent layout, Qt will reject the second addLayout
            # silently (which is what we want — the row stays in the
            # section frame, not in the outer lay).
            cur_lay = self._obs_active_section_lay[0]
            if cur_lay is not None:
                cur_lay.addLayout(row)
            return row

        def _line(key: str, placeholder: str = "",
                  width: int = 0) -> QLineEdit:
            le = QLineEdit()
            le.setPlaceholderText(placeholder)
            if width > 0:
                le.setMaximumWidth(width)
            le.setStyleSheet(
                "QLineEdit{padding:5px 8px;border:1px solid #B8D4E8;"
                "border-radius:3px;font:11px 'Segoe UI';background:white;}"
                "QLineEdit:focus{border-color:#0078D4;}")
            le.textChanged.connect(
                lambda: self._schedule_obs_autosave())
            # v68-AI: Attach autocomplete to text-heavy fields (those
            # likely to contain medical terms — vitamins, meds, tests, plans)
            if key in ("vitamins", "medications", "recommended_tests",
                        "delivery_plan", "next_visit", "allergies",
                        "chronic_conditions", "fetal_findings",
                        "fetal_problems", "complaints", "diagnosis",
                        "consultation"):
                try:
                    SmartAutocomplete.attach(le)
                except Exception as _ex:
                    _log_warning(f"obs _line autocomplete: {_ex}")
            self._obs_form_widgets[key] = le
            return le

        def _text(key: str, min_h: int = 70) -> QTextEdit:
            te = QTextEdit()
            te.setMinimumHeight(min_h)
            te.setStyleSheet(
                "QTextEdit{padding:5px 8px;border:1px solid #B8D4E8;"
                "border-radius:3px;font:11px 'Segoe UI';background:white;}"
                "QTextEdit:focus{border-color:#0078D4;}")
            te.textChanged.connect(
                lambda: self._schedule_obs_autosave())
            # v68-AI: Attach smart autocomplete (medical terms +
            # learned phrases) to every text area in the obstetric form
            try:
                SmartAutocomplete.attach(te)
            except Exception as _ex:
                _log_warning(f"obs form _text autocomplete: {_ex}")
            self._obs_form_widgets[key] = te
            return te

        # ── Section 1: Hasta Bilgisi ─────────────────────────────────────
        lay.addWidget(_section_header("👤 Hasta Bilgisi"))
        _field_row("Yaş:", _line("age", "Yaş", 100))
        _field_row(
            "Gebelik öncesi kilo (kg):",
            _line("pre_weight", "kg", 100))
        _field_row(
            "Şu anki kilo (kg):", _line("current_weight", "kg", 100))
        _field_row("Boy (cm):", _line("height", "cm", 100))
        _field_row("BMI (gebelik öncesi):",
                                 _line("bmi", "otomatik", 100))
        _field_row("Meslek:", _line("occupation", ""))
        _field_row(
            "Sigara/Alkol:",
            _line("smoke_alcohol",
                  "örn: gebelikte sigara bıraktı / hiç içmemiş"))

        # ── Section 2: Bu Gebelik ────────────────────────────────────────
        lay.addWidget(_section_header("🤰 Bu Gebelik"))
        _field_row(
            "LMP (Son Adet):", _line("lmp", "GG.AA.YYYY", 160))
        _field_row(
            "EDD (Tahmini Doğum):",
            _line("edd", "USG ve LMP'den", 160))
        _field_row(
            "Şu anki gebelik haftası:",
            _line("current_ga", "örn: 22+3 hafta", 160))
        _field_row(
            "Gebelik tipi:",
            _line("preg_type",
                  "örn: tekiz, ikiz monokoryonik, IVF gebeliği"))
        _field_row(
            "ART tedavisi:",
            _line("art_history",
                  "örn: yok / IVF (1. siklus) / IUI / OI"))
        _field_row(
            "Sezaryen planlandı:",
            _line("c_section_plan",
                  "örn: planlanmadı / 39. hafta primer / tekrar"))

        # ── Section 3: Obstetrik Öykü ────────────────────────────────────
        lay.addWidget(_section_header("📖 Obstetrik Öykü"))
        _field_row(
            "Gebelik (G):", _line("gravida", "", 100))
        _field_row(
            "Doğum (P):", _line("para", "", 100))
        _field_row(
            "Abortus (A):", _line("abortus", "", 100))
        _field_row(
            "Yaşayan (Y):", _line("living", "", 100))
        _field_row(
            "Önceki sezaryen sayısı:",
            _line("prev_csection", "", 100))
        _field_row(
            "Önceki preterm doğum:",
            _line("prev_preterm",
                  "örn: yok / 32. haftada vajinal"))
        _field_row(
            "Önceki preeklampsi:",
            _line("prev_preeclampsia",
                  "örn: yok / 36. haftada hafif"))
        _field_row(
            "Önceki GDM:",
            _line("prev_gdm", "örn: yok / Tip 2 GDM"))
        _field_row(
            "Önceki postpartum komplikasyon:",
            _line("prev_pp_complications",
                  "örn: yok / atoni, kanama"))

        # ── Section 4: Aile Öyküsü + Genetik ─────────────────────────────
        lay.addWidget(_section_header("👨‍👩‍👧 Aile Öyküsü"))
        _field_row(
            "Diyabet:", _line("family_dm",
                              "örn: anne Tip2, baba yok"))
        _field_row(
            "Hipertansiyon:", _line("family_ht",
                                    "örn: anne HT, baba yok"))
        _field_row(
            "Tromboz/PE öyküsü:", _line("family_thrombosis",
                                        "örn: yok / kız kardeş DVT"))
        _field_row(
            "Genetik hastalık:",
            _line("family_genetic",
                  "örn: yok / talasemi taşıyıcı / Down sendromlu kuzen"))
        _field_row(
            "Akraba evliliği:",
            _line("consanguinity",
                  "örn: yok / 2. derece kuzen evliliği"))

        # ── Section 5: Mevcut Gebelik Şikayetleri ────────────────────────
        lay.addWidget(_section_header("⚠️ Bu Gelişin Şikayetleri"))
        _field_row(
            "Bulantı/Kusma:",
            _line("nausea_vomit",
                  "örn: yok / hafif / şiddetli (hyperemezis)"))
        _field_row(
            "Baş ağrısı:",
            _line("headache",
                  "örn: yok / hafif / şiddetli + görme bulanıklığı"))
        _field_row(
            "Ödem:",
            _line("edema",
                  "örn: yok / ayakta hafif / yüz+el (preeklampsi şüphesi)"))
        _field_row(
            "Kanama / akıntı:",
            _line("bleeding",
                  "örn: yok / leke / aktif kanama"))
        _field_row(
            "Karın ağrısı / kasılma:",
            _line("abdominal_pain",
                  "örn: yok / Braxton-Hicks / düzenli"))
        _field_row(
            "Üriner şikayet:",
            _line("urinary_complaints",
                  "örn: yok / sık idrar / yanma (UTI?)"))
        _field_row(
            "Fetal hareket:",
            _line("fetal_movement",
                  "örn: aktif / azalmış / hissetmiyor"))

        # ── Section 6: Vital Signs / Muayene ─────────────────────────────
        lay.addWidget(_section_header("📊 Vital Signs ve Muayene"))
        _field_row(
            "Tansiyon (mmHg):",
            _line("bp", "örn: 120/80", 160))
        _field_row(
            "Nabız (/dk):", _line("pulse", "örn: 78", 100))
        _field_row(
            "Sıcaklık (°C):", _line("temp", "örn: 36.8", 100))
        _field_row(
            "Bu gelişteki kilo (kg):",
            _line("visit_weight", "kg", 100))
        _field_row(
            "Fundus yüksekliği (cm):",
            _line("fundal_height", "cm", 100))
        _field_row(
            "FH lokalizasyonu:",
            _line("fh_position",
                  "örn: göbek hizasında / 2 cm üzerinde"))
        _field_row(
            "Fetal kalp atımı (/dk):",
            _line("fhr", "örn: 145", 100))
        _field_row(
            "Prezantasyon:",
            _line("presentation",
                  "örn: baş, makat, transvers, henüz belirsiz"))

        # ── Section 7: Lab + USG ─────────────────────────────────────────
        lay.addWidget(_section_header("🔬 Lab ve USG Bulguları"))
        _field_row(
            "Hemoglobin (g/dL):",
            _line("hb", "anemi taraması", 100))
        _field_row(
            "Açlık kan şekeri:",
            _line("fbg", "mg/dL", 100))
        _field_row(
            "OGTT 75g (24-28. hf):",
            _line("ogtt",
                  "örn: 88/172/154 mg/dL — GDM yok"))
        _field_row(
            "Tam idrar:",
            _line("urinalysis",
                  "örn: protein +, lökosit yok"))
        _field_row(
            "USG bulguları:",
            _line("usg_findings",
                  "örn: tekiz canlı 22hf, plasenta posterior fundal"))
        _field_row(
            "Bebek ölçümleri:",
            _line("biometry",
                  "örn: BPD 50mm (22+1), AC 165mm, FL 35mm, EFW 480g"))
        _field_row(
            "Amniyon mayisi:",
            _line("amniotic_fluid",
                  "örn: AFI 14 cm, normal"))
        _field_row(
            "Plasenta:",
            _line("placenta",
                  "örn: posterior fundal, derece 1, normal"))
        _field_row(
            "Servikal uzunluk:",
            _line("cervical_length", "mm", 100))

        # ── Section 8: Risk Değerlendirmesi ──────────────────────────────
        lay.addWidget(_section_header("⚡ Risk Değerlendirmesi"))
        _field_row(
            "Yüksek risk gebelik:",
            _line("high_risk",
                  "örn: hayır / evet (ileri yaş + GDM)"))
        _field_row(
            "Risk faktörleri:",
            _line("risk_factors",
                  "örn: ileri yaş, BMI 32, kronik HT, IVF"))
        _field_row(
            "Preeklampsi profilaksi:",
            _line("preeclampsia_prophylaxis",
                  "örn: aspirin 100mg gece (12. hf'den)"))
        _field_row(
            "GDM riski:",
            _line("gdm_risk",
                  "örn: düşük / yüksek (BMI 32)"))

        # ── Section 9: Tedavi Planı ──────────────────────────────────────
        lay.addWidget(_section_header("💊 Tedavi ve Plan"))
        _field_row(
            "Vitamin / mineral:",
            _line("vitamins",
                  "örn: folik asit, demir, kalsiyum, D vitamini"))
        _field_row(
            "Kullandığı ilaçlar:",
            _line("medications",
                  "örn: aspirin 100mg, levotiroksin 50mcg"))
        _field_row(
            "Önerilen tetkikler:",
            _line("recommended_tests",
                  "örn: 11-14 hf NT, 16-20 hf 2nd trimester, OGTT"))
        _field_row(
            "Sonraki kontrol:",
            _line("next_visit",
                  "örn: 4 hafta sonra / 2 hafta sonra"))
        _field_row(
            "Doğum planı:",
            _line("delivery_plan",
                  "örn: vajinal doğum / sezaryen 39 hafta"))

        # ── Section 10: Notlar ───────────────────────────────────────────
        lay.addWidget(_section_header("📝 Ek Notlar"))
        lay.addWidget(_text("notes", 100))

        scroll.setWidget(host)
        outer_lay.addWidget(scroll, 1)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_save = QPushButton("💾 Hemen Kaydet")
        btn_save.setStyleSheet(
            "QPushButton{background:#003A66;color:white;padding:8px 22px;"
            "font:600 12px 'Segoe UI';border:none;border-radius:3px;}"
            "QPushButton:hover{background:#002B4C;}")
        btn_save.clicked.connect(self._save_obs_form_now)
        btn_row.addWidget(btn_save)

        btn_print = QPushButton("🖨 Yazdır")
        btn_print.setStyleSheet(
            "QPushButton{background:#0078D4;color:white;padding:8px 22px;"
            "font:600 12px 'Segoe UI';border:none;border-radius:3px;}"
            "QPushButton:hover{background:#005A9E;}")
        btn_print.clicked.connect(self._print_obs_form)
        btn_row.addWidget(btn_print)

        btn_clear = QPushButton("🗑 Formu Temizle")
        btn_clear.setStyleSheet(
            "QPushButton{background:#E5EEF7;color:#404040;padding:8px 18px;"
            "font:500 11px 'Segoe UI';border:1px solid #B8D4E8;"
            "border-radius:3px;}"
            "QPushButton:hover{background:#D5E5F5;}")
        btn_clear.clicked.connect(self._clear_obs_form)
        btn_row.addWidget(btn_clear)
        btn_row.addStretch()
        outer_lay.addLayout(btn_row)

        # Autosave timer
        self._obs_save_timer = QTimer(self)
        self._obs_save_timer.setSingleShot(True)
        self._obs_save_timer.timeout.connect(self._auto_save_obs_form)

        # v68-UI: Apply initial Kısa İzlem state (default ON)
        try:
            self._apply_obs_short_mode(self.obs_short_chk.isChecked())
        except Exception as _ex:
            _log_warning("obs build: apply short mode", exc=_ex)

        return page

    def _schedule_obs_autosave(self):
        """Schedule an obstetric form autosave (1.5sn debounce)."""
        if hasattr(self, "obs_save_lbl"):
            self.obs_save_lbl.hide()
        if hasattr(self, "_obs_save_timer"):
            self._obs_save_timer.start(1500)

    def _auto_save_obs_form(self):
        """Persist obstetric form values keyed by patient_key (or
        '__template__' when no patient is active)."""
        pkey = "__template__"
        if self.current_patient is not None:
            pkey = self.current_patient.name
        try:
            data = {}
            for key, widget in self._obs_form_widgets.items():
                if isinstance(widget, QTextEdit):
                    data[key] = widget.toPlainText()
                elif isinstance(widget, QLineEdit):
                    data[key] = widget.text()
            _save_obs_form_data(pkey, data)
            if hasattr(self, "obs_save_lbl"):
                self.obs_save_lbl.setText("✓ Kaydedildi")
                self.obs_save_lbl.show()
        except Exception as _ex:
            _log_warning("_auto_save_obs_form", exc=_ex)

    def _save_obs_form_now(self):
        """Manual save button — same as autosave + status bar message."""
        self._auto_save_obs_form()
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(
                "✓ Obstetrik takip formu kaydedildi", 3000)

    def _on_obs_short_toggled(self, checked: bool):
        """Handle the Obstetric form's '📝 Kısa İzlem' checkbox.
        Persists the preference and applies visibility to all sections.
        """
        try:
            set_short_followup_mode(bool(checked))
        except Exception as _ex:
            _log_warning("_on_obs_short_toggled: persist", exc=_ex)
        self._apply_obs_short_mode(bool(checked))
        # Also flip the gynec form checkbox to keep them in sync
        try:
            if hasattr(self, "gyn_short_chk") and \
                    self.gyn_short_chk.isChecked() != checked:
                self.gyn_short_chk.blockSignals(True)
                self.gyn_short_chk.setChecked(checked)
                self.gyn_short_chk.blockSignals(False)
                self._apply_gyn_short_mode(bool(checked))
        except Exception as _ex:
            _log_warning(
                "_on_obs_short_toggled: gyn sync", exc=_ex)

    def _apply_obs_short_mode(self, short_mode: bool):
        """Show/hide non-essential obstetric form sections.

        v68-UI: Sections classified as CORE (vitals, complaints, fetal,
        plan) stay visible at all times. Other sections (aile öyküsü,
        genetik, önceki gebelikler, etc.) are collapsed when
        short_mode=True.
        """
        if not hasattr(self, "_obs_section_frames"):
            return
        try:
            CORE = {"vitals", "complaints", "fetal", "plan"}
            for sec_key, frame in self._obs_section_frames.items():
                semantic = self._obs_section_key_for_pos.get(
                    sec_key, sec_key)
                # Show if not in short mode OR section is CORE
                visible = (not short_mode) or (semantic in CORE)
                frame.setVisible(visible)
        except Exception as _ex:
            _log_warning("_apply_obs_short_mode", exc=_ex)

    def _on_gyn_short_toggled(self, checked: bool):
        """Handle the Gynec form's '📝 Kısa İzlem' checkbox."""
        try:
            set_short_followup_mode(bool(checked))
        except Exception as _ex:
            _log_warning("_on_gyn_short_toggled: persist", exc=_ex)
        self._apply_gyn_short_mode(bool(checked))
        # Also flip the obs form checkbox to keep them in sync
        try:
            if hasattr(self, "obs_short_chk") and \
                    self.obs_short_chk.isChecked() != checked:
                self.obs_short_chk.blockSignals(True)
                self.obs_short_chk.setChecked(checked)
                self.obs_short_chk.blockSignals(False)
                self._apply_obs_short_mode(bool(checked))
        except Exception as _ex:
            _log_warning(
                "_on_gyn_short_toggled: obs sync", exc=_ex)

    def _apply_gyn_short_mode(self, short_mode: bool):
        """Show/hide non-essential gynecologic form sections."""
        if not hasattr(self, "_gyn_section_frames"):
            return
        try:
            CORE = {"complaints", "exam", "labs_brief", "plan"}
            for sec_key, frame in self._gyn_section_frames.items():
                semantic = self._gyn_section_key_for_pos.get(
                    sec_key, sec_key)
                visible = (not short_mode) or (semantic in CORE)
                frame.setVisible(visible)
        except Exception as _ex:
            _log_warning("_apply_gyn_short_mode", exc=_ex)

    def _load_obs_form(self):
        """Load saved obstetric form values for the current patient.

        v68: If the patient's form is empty (fresh / never filled in),
        we auto-populate fields from the latest Voluson PDF so the
        doctor sees a pre-filled form ready to review. PDF-derived
        values never overwrite existing user-entered data — we only
        fill EMPTY fields. This way the doctor's manual edits are
        preserved while convenience auto-fill still works.
        """
        pkey = "__template__"
        if self.current_patient is not None:
            pkey = self.current_patient.name
        try:
            data = _load_obs_form_data(pkey)
            # v68: Try to enrich with PDF-extracted values (only fills
            # empty fields — user data always wins). Only runs for
            # real patients with a latest PDF; no-op otherwise.
            try:
                pdf_data = self._extract_obs_pdf_fields_for_autofill()
                if pdf_data:
                    # Merge: saved data wins over PDF data
                    for key, val in pdf_data.items():
                        if val and not (data.get(key) or "").strip():
                            data[key] = val
            except Exception as _ex:
                _log_warning("_load_obs_form: pdf autofill", exc=_ex)

            for key, widget in self._obs_form_widgets.items():
                val = data.get(key, "")
                if isinstance(widget, QTextEdit):
                    widget.blockSignals(True)
                    widget.setPlainText(val)
                    widget.blockSignals(False)
                elif isinstance(widget, QLineEdit):
                    widget.blockSignals(True)
                    widget.setText(val)
                    widget.blockSignals(False)
        except Exception as _ex:
            _log_warning("_load_obs_form", exc=_ex)

    def _extract_obs_pdf_fields_for_autofill(self) -> dict:
        """Pull values from the latest PDF and map them to obstetric
        form field keys. Returns a dict of {form_key: value} where
        values are stringified for QLineEdit population.

        Also pulls saved demographic data (LMP, G/P/A/L, kronik,
        ilaç, alerji) from patient_demographics so the form shows
        those too.
        """
        out: dict = {}
        if self.current_patient is None:
            return out

        # ── Demographics (stored in DB) ───────────────────────────
        try:
            demo = load_patient_demographics(self.current_patient.name)
            if demo:
                # LMP
                lmp = demo.get("lmp_override") or ""
                if lmp:
                    out["lmp"] = lmp
                # Gravida / Para / Abortus / Living
                for src_key, dst_key in (
                        ("gravida", "gravida"),
                        ("para", "para"),
                        ("abortus", "abortus"),
                        ("living", "living")):
                    v = demo.get(src_key)
                    if v is not None:
                        out[dst_key] = str(v)
                # Medications / chronic / allergies → shown in
                # "Kullandığı ilaçlar" + notlar
                meds = demo.get("medications") or ""
                if meds:
                    out["medications"] = meds
                chronic = demo.get("chronic_conditions") or ""
                allergies = demo.get("allergies") or ""
                note_bits = []
                if chronic:
                    note_bits.append(f"Kronik hastalıklar: {chronic}")
                if allergies:
                    note_bits.append(f"Alerjiler: {allergies}")
                if note_bits:
                    out["notes"] = "\n".join(note_bits)
        except Exception as _ex:
            _log_warning("pdf autofill: demographics", exc=_ex)

        # ── Manual-registration meta (age, phone) ─────────────────
        try:
            manual = get_patient_manual_meta(self.current_patient.name)
            if manual.get("age"):
                out["age"] = str(manual["age"])
        except Exception as _ex:
            _log_warning("pdf autofill: manual meta", exc=_ex)

        # ── PDF data (latest visit) ───────────────────────────────
        try:
            subs = get_subfolders(self.current_patient)
            if subs:
                pdf = get_latest_pdf_in_folder(subs[0])
                if pdf:
                    pdf_data = parse_pdf_summary_data(pdf)
                    # Age — PDF if not already from manual meta
                    if not out.get("age"):
                        yas = pdf_data.get("Yaş")
                        if yas and yas != "-":
                            out["age"] = str(yas)
                    # Current GA
                    ga_aua = pdf_data.get("GA(AUA)") or ""
                    ga_lmp = pdf_data.get("GA(LMP)") or ""
                    if ga_aua and ga_aua != "-":
                        out["current_ga"] = ga_aua
                    elif ga_lmp and ga_lmp != "-":
                        out["current_ga"] = ga_lmp
                    # EDD
                    edd = pdf_data.get("edd") or ""
                    if edd:
                        out["edd"] = edd
                    # USG biometry — concat the measurements into
                    # a single readable line
                    bio_bits = []

                    def _meas(key, label):
                        v = pdf_data.get(key)
                        if (isinstance(v, (tuple, list))
                                and len(v) >= 1 and v[0]):
                            bio_bits.append(f"{label} {v[0]}")
                        elif isinstance(v, str) and v not in ("", "-"):
                            bio_bits.append(f"{label} {v}")
                    _meas("BPD", "BPD")
                    _meas("HC", "HC")
                    _meas("AC", "AC")
                    _meas("FL", "FL")
                    _meas("CRL", "CRL")
                    efw = pdf_data.get("EFW")
                    if efw and efw != "-":
                        bio_bits.append(f"EFW {efw}")
                    nt = pdf_data.get("NT")
                    if (isinstance(nt, (tuple, list))
                            and len(nt) >= 1 and nt[0]):
                        bio_bits.append(f"NT {nt[0]}")
                    if bio_bits:
                        out["biometry"] = ", ".join(bio_bits)
                    # Pregnancy type (twin detection)
                    if pdf_data.get("is_twin"):
                        out["preg_type"] = "İkiz gebelik"
                    else:
                        out["preg_type"] = "Tekiz"
                    # USG findings — short summary
                    usg_parts = []
                    if pdf_data.get("is_twin"):
                        usg_parts.append("İkiz canlı gebelik")
                    else:
                        usg_parts.append("Tekiz canlı gebelik")
                    if ga_aua and ga_aua != "-":
                        usg_parts.append(ga_aua)
                    if not out.get("usg_findings"):
                        out["usg_findings"] = ", ".join(usg_parts)
        except Exception as _ex:
            _log_warning("pdf autofill: pdf data", exc=_ex)

        return out

    def _clear_obs_form(self):
        """Empty all obstetric form fields after confirmation."""
        reply = QMessageBox.question(
            self, "Form Temizle",
            "Tüm obstetrik takip alanlarını temizlemek istediğinize "
            "emin misiniz?\n\nYazılı değerler silinecek.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        for widget in self._obs_form_widgets.values():
            if isinstance(widget, QTextEdit):
                widget.blockSignals(True)
                widget.clear()
                widget.blockSignals(False)
            elif isinstance(widget, QLineEdit):
                widget.blockSignals(True)
                widget.clear()
                widget.blockSignals(False)
        self._auto_save_obs_form()

    def _print_obs_form(self):
        """Render the obstetric form as a printable handout."""
        pname = "—"
        if self.current_patient is not None:
            pname = format_patient_name(self.current_patient.name)
        today = datetime.now().strftime("%d.%m.%Y")

        def _g(k):
            w = self._obs_form_widgets.get(k)
            if w is None:
                return "—"
            if isinstance(w, QTextEdit):
                t = w.toPlainText().strip()
            else:
                t = w.text().strip()
            return t if t else "—"

        rows = []

        def _grp(title, fields):
            rows.append(
                f'<tr><td colspan="2" style="background:#E5F1FB;'
                f'color:#003A66;padding:8px 10px;font-weight:700;'
                f'font-size:12px;">{title}</td></tr>')
            for label, key in fields:
                rows.append(
                    f'<tr>'
                    f'<td style="padding:6px 10px;background:#FAFAFA;'
                    f'border-bottom:1px solid #E8E8E8;width:40%;'
                    f'font-size:11px;color:#606060;">{label}</td>'
                    f'<td style="padding:6px 10px;border-bottom:1px '
                    f'solid #E8E8E8;font-size:12px;color:#202020;'
                    f'font-weight:500;">{_g(key)}</td>'
                    f'</tr>')

        _grp("👤 Hasta Bilgisi", [
            ("Yaş", "age"),
            ("Gebelik öncesi kilo", "pre_weight"),
            ("Şu anki kilo", "current_weight"),
            ("Boy", "height"), ("BMI", "bmi"),
            ("Meslek", "occupation"),
            ("Sigara/Alkol", "smoke_alcohol"),
        ])
        _grp("🤰 Bu Gebelik", [
            ("LMP", "lmp"), ("EDD", "edd"),
            ("Gebelik haftası", "current_ga"),
            ("Gebelik tipi", "preg_type"),
            ("ART tedavisi", "art_history"),
            ("Sezaryen planı", "c_section_plan"),
        ])
        _grp("📖 Obstetrik Öykü", [
            ("G", "gravida"), ("P", "para"),
            ("A", "abortus"), ("Y", "living"),
            ("Önceki sezaryen", "prev_csection"),
            ("Önceki preterm", "prev_preterm"),
            ("Önceki preeklampsi", "prev_preeclampsia"),
            ("Önceki GDM", "prev_gdm"),
            ("Önceki PP komplikasyon", "prev_pp_complications"),
        ])
        _grp("👨‍👩‍👧 Aile Öyküsü", [
            ("Diyabet", "family_dm"),
            ("Hipertansiyon", "family_ht"),
            ("Tromboz/PE", "family_thrombosis"),
            ("Genetik hastalık", "family_genetic"),
            ("Akraba evliliği", "consanguinity"),
        ])
        _grp("⚠️ Şikayetler", [
            ("Bulantı/Kusma", "nausea_vomit"),
            ("Baş ağrısı", "headache"),
            ("Ödem", "edema"),
            ("Kanama/akıntı", "bleeding"),
            ("Karın ağrısı/kasılma", "abdominal_pain"),
            ("Üriner şikayet", "urinary_complaints"),
            ("Fetal hareket", "fetal_movement"),
        ])
        _grp("📊 Vital Signs", [
            ("Tansiyon", "bp"), ("Nabız", "pulse"),
            ("Sıcaklık", "temp"),
            ("Bu gelişteki kilo", "visit_weight"),
            ("Fundus yüksekliği", "fundal_height"),
            ("FH lokalizasyonu", "fh_position"),
            ("Fetal kalp atımı", "fhr"),
            ("Prezantasyon", "presentation"),
        ])
        _grp("🔬 Lab ve USG", [
            ("Hemoglobin", "hb"),
            ("Açlık kan şekeri", "fbg"),
            ("OGTT 75g", "ogtt"),
            ("Tam idrar", "urinalysis"),
            ("USG bulguları", "usg_findings"),
            ("Bebek ölçümleri", "biometry"),
            ("Amniyon mayisi", "amniotic_fluid"),
            ("Plasenta", "placenta"),
            ("Servikal uzunluk", "cervical_length"),
        ])
        _grp("⚡ Risk", [
            ("Yüksek risk", "high_risk"),
            ("Risk faktörleri", "risk_factors"),
            ("Preeklampsi profilaksi", "preeclampsia_prophylaxis"),
            ("GDM riski", "gdm_risk"),
        ])
        _grp("💊 Tedavi", [
            ("Vitamin/mineral", "vitamins"),
            ("İlaçlar", "medications"),
            ("Önerilen tetkikler", "recommended_tests"),
            ("Sonraki kontrol", "next_visit"),
            ("Doğum planı", "delivery_plan"),
        ])
        notes_val = _g("notes")
        if notes_val != "—":
            rows.append(
                '<tr><td colspan="2" style="background:#E5F1FB;'
                'color:#003A66;padding:8px 10px;font-weight:700;'
                'font-size:12px;">📝 Notlar</td></tr>')
            rows.append(
                f'<tr><td colspan="2" style="padding:8px 12px;'
                f'white-space:pre-wrap;font-size:12px;">{notes_val}</td></tr>')

        html = f"""
<html><head><meta charset="utf-8"><style>
  body {{font-family:'Segoe UI',Arial,sans-serif;margin:20px 30px;color:#202020;}}
  .header {{border-bottom:3px solid #0078D4;padding-bottom:12px;margin-bottom:16px;}}
  .clinic {{font-size:11px;color:#606060;text-align:right;}}
  .doc-title {{font-size:20px;font-weight:800;color:#003A66;margin:12px 0 6px 0;}}
  .meta {{font-size:13px;color:#404040;}}
  table {{border-collapse:collapse;width:100%;margin-top:6px;}}
</style></head><body>
  <div class="header">
    <div class="clinic">
      <b>{get_clinic_doctor_name()}</b><br>
      Kadın Hastalıkları ve Doğum<br>
      Riskli Gebelik ve Gebelik Takibi
    </div>
    <div class="doc-title">🤰 Obstetrik / Gebelik Takip Formu</div>
    <div class="meta">Hasta: <b>{pname}</b> &nbsp;·&nbsp; Tarih: <b>{today}</b></div>
  </div>
  <table>{''.join(rows)}</table>
</body></html>"""

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("Obstetrik Takip Formu — Yazdır")
        dlg.resize(780, 760)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(12, 12, 12, 12)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setStyleSheet(
            "QTextEdit{background:#FFFFFF;color:#202020;"
            "border:1px solid #C8C8C8;}")
        txt.setHtml(html)
        v.addWidget(txt, 1)

        btn_row = QHBoxLayout()
        btn_p = QPushButton("🖨 Yazdır")
        btn_p.setStyleSheet(
            "QPushButton{background:#0078D4;color:white;padding:8px 22px;"
            "font:600 12px 'Segoe UI';border:none;border-radius:3px;}"
            "QPushButton:hover{background:#005A9E;}")

        def _do_print():
            # v68-UI: Use the central print_text_widget helper.
            # It handles QTextDocument print, dialog modality,
            # printer state checking, and gives a meaningful error
            # message if the print silently fails.
            ok, msg = print_text_widget(txt, parent_dialog=dlg,
                                        title="Yazdır")
            try:
                self.statusBar().showMessage(msg, 5000)
            except Exception as _ex:
                _log_warning("_do_print: status", exc=_ex)
            if not ok and "iptal" not in (msg or "").lower():
                QMessageBox.warning(dlg, "Yazdırma", msg)
        btn_p.clicked.connect(_do_print)
        btn_row.addWidget(btn_p)
        btn_row.addStretch()
        btn_c = QPushButton("Kapat")
        btn_c.setShortcut("Escape")
        btn_c.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_c)
        v.addLayout(btn_row)
        dlg.exec()

    def _build_tab_gynec_followup(self) -> QWidget:
        """Jinekolojik Takip — pink-themed form for gynecology patients.

        Lets the doctor record/inspect:
          • Endometrial thickness (mm)
          • Antral follicle count (AFC)
          • Largest follicle diameters (left + right ovary)
          • AMH value (with last-measured date)
          • Cycle day (siklus günü)
          • Prior treatments (IUI / IVF / clomifene / letrozole / gonadotropin)
          • Free-text gyn notes

        Form is per-patient (keyed on patient folder name). Auto-saves
        to a small SQLite table — see save_gynec_record / load_gynec_record.
        Includes a "Print" button for handing to the patient + "Reset
        Form" for cases where data should be cleared without saving.
        """
        page = QWidget()
        page.setObjectName("TabPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # ── Pink header strip ─────────────────────────────────────────────
        hdr = QFrame()
        hdr.setStyleSheet(
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #8B2A6D, stop:1 #B5368A);"
            "color:white;border-radius:6px;padding:10px 14px;")
        hdr_lay = QHBoxLayout(hdr)
        hdr_lay.setContentsMargins(8, 4, 8, 4)
        hdr_title = QLabel(
            "🌸  <b>Jinekolojik Takip</b>  •  "
            "Hasta-spesifik infertilite/jin değerlendirmesi")
        hdr_title.setStyleSheet("color:white;font:600 13px 'Segoe UI';")
        hdr_lay.addWidget(hdr_title)
        hdr_lay.addStretch()

        # v68-UI: Kısa İzlem checkbox (mirrors obs form)
        self.gyn_short_chk = QCheckBox("📝 Kısa İzlem")
        self.gyn_short_chk.setChecked(get_short_followup_mode())
        self.gyn_short_chk.setToolTip(
            "Kısa İzlem AÇIK: sadece sık kullanılan alanlar görünür.\n"
            "KAPALI: tüm bölümler açılır.")
        self.gyn_short_chk.setCursor(Qt.PointingHandCursor)
        self.gyn_short_chk.setStyleSheet(
            "QCheckBox{color:#FFFFFF;font:600 11px 'Segoe UI';"
            "padding:4px 10px;background:rgba(255,255,255,0.18);"
            "border:1px solid rgba(255,255,255,0.4);border-radius:4px;}"
            "QCheckBox:hover{background:rgba(255,255,255,0.28);}"
            "QCheckBox::indicator{width:16px;height:16px;}")
        self.gyn_short_chk.toggled.connect(self._on_gyn_short_toggled)
        hdr_lay.addWidget(self.gyn_short_chk)
        hdr_lay.addSpacing(10)

        self.gynec_save_status_lbl = QLabel("")
        self.gynec_save_status_lbl.setStyleSheet(
            "color:white;font:500 11px 'Segoe UI';opacity:0.92;")
        hdr_lay.addWidget(self.gynec_save_status_lbl)
        lay.addWidget(hdr)

        # ── Scroll area — main form ──────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        form_host = QWidget()
        form_host.setStyleSheet("background:#FAFAFA;")
        flay = QVBoxLayout(form_host)
        flay.setContentsMargins(14, 14, 14, 14)
        flay.setSpacing(14)

        # v68-UI: Track gynec sections for Kısa İzlem toggle, same
        # approach as obstetric form. CORE sections stay visible in
        # compact mode; others collapse for routine visits.
        self._gyn_section_frames: dict = {}
        self._gyn_section_key_for_pos: dict = {}
        _gyn_section_counter = [0]

        # Helper to build a section
        def _section(title: str, color: str = "#8B2A6D") -> QFrame:
            box = QFrame()
            box.setStyleSheet(
                f"QFrame{{background:white;border:1px solid #E0D0DA;"
                f"border-radius:5px;}}"
                f"QLabel#SectionTitle{{color:{color};font:700 13px 'Segoe UI';"
                f"padding:0;margin:0;}}")
            # v68-UI: Auto-register for visibility toggling
            _gyn_section_counter[0] += 1
            sec_key = f"gsec_{_gyn_section_counter[0]}"
            self._gyn_section_frames[sec_key] = box
            tl = title.lower()
            if any(t in tl for t in ("şikay", "yakın")):
                self._gyn_section_key_for_pos[sec_key] = "complaints"
            elif any(t in tl for t in ("muayene", "bazal", "yumurtalık")):
                self._gyn_section_key_for_pos[sec_key] = "exam"
            elif any(t in tl for t in ("plan", "öneri", "tedavi")):
                self._gyn_section_key_for_pos[sec_key] = "plan"
            else:
                self._gyn_section_key_for_pos[sec_key] = sec_key
            return box

        # Container references for the form fields, keyed by name —
        # makes save/load trivially declarative
        self._gynec_fields: dict = {}

        # ── 1) Bazal değerlendirme ────────────────────────────────────────
        sec1 = _section("Bazal Değerlendirme")
        s1l = QVBoxLayout(sec1)
        s1l.setContentsMargins(14, 12, 14, 12)
        s1l.setSpacing(8)
        t1 = QLabel("📋 Bazal Değerlendirme")
        t1.setObjectName("SectionTitle")
        s1l.addWidget(t1)

        from PySide6.QtWidgets import QFormLayout, QSpinBox, QDoubleSpinBox
        f1 = QFormLayout()
        f1.setHorizontalSpacing(12)
        f1.setVerticalSpacing(6)
        f1.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        cycle_day = QSpinBox()
        cycle_day.setRange(0, 99)
        cycle_day.setSuffix(" gün")
        cycle_day.setSpecialValueText("—")
        cycle_day.setMinimumWidth(120)
        f1.addRow("Siklus günü:", cycle_day)
        self._gynec_fields["cycle_day"] = cycle_day

        endometrium = QDoubleSpinBox()
        endometrium.setRange(0.0, 50.0)
        endometrium.setDecimals(1)
        endometrium.setSuffix(" mm")
        endometrium.setSpecialValueText("—")
        endometrium.setMinimumWidth(120)
        f1.addRow("Endometrial kalınlık:", endometrium)
        self._gynec_fields["endometrium"] = endometrium

        endo_pattern = QComboBox()
        endo_pattern.addItems(["—", "Trilaminer", "Homojen", "Düzensiz"])
        endo_pattern.setMinimumWidth(120)
        f1.addRow("Endometrial pattern:", endo_pattern)
        self._gynec_fields["endo_pattern"] = endo_pattern

        s1l.addLayout(f1)
        flay.addWidget(sec1)

        # ── 2) Yumurtalık değerlendirmesi ─────────────────────────────────
        sec2 = _section("Yumurtalık Değerlendirmesi")
        s2l = QVBoxLayout(sec2)
        s2l.setContentsMargins(14, 12, 14, 12)
        s2l.setSpacing(8)
        t2 = QLabel("🥚 Yumurtalık Değerlendirmesi")
        t2.setObjectName("SectionTitle")
        s2l.addWidget(t2)

        f2 = QFormLayout()
        f2.setHorizontalSpacing(12)
        f2.setVerticalSpacing(6)
        f2.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        afc_left = QSpinBox()
        afc_left.setRange(0, 60)
        afc_left.setSpecialValueText("—")
        afc_left.setMinimumWidth(120)
        f2.addRow("AFC (sol over):", afc_left)
        self._gynec_fields["afc_left"] = afc_left

        afc_right = QSpinBox()
        afc_right.setRange(0, 60)
        afc_right.setSpecialValueText("—")
        afc_right.setMinimumWidth(120)
        f2.addRow("AFC (sağ over):", afc_right)
        self._gynec_fields["afc_right"] = afc_right

        # Largest follicle diameters
        foll_left = QDoubleSpinBox()
        foll_left.setRange(0.0, 60.0)
        foll_left.setDecimals(1)
        foll_left.setSuffix(" mm")
        foll_left.setSpecialValueText("—")
        foll_left.setMinimumWidth(120)
        f2.addRow("En büyük folikül (sol):", foll_left)
        self._gynec_fields["foll_left"] = foll_left

        foll_right = QDoubleSpinBox()
        foll_right.setRange(0.0, 60.0)
        foll_right.setDecimals(1)
        foll_right.setSuffix(" mm")
        foll_right.setSpecialValueText("—")
        foll_right.setMinimumWidth(120)
        f2.addRow("En büyük folikül (sağ):", foll_right)
        self._gynec_fields["foll_right"] = foll_right

        s2l.addLayout(f2)
        flay.addWidget(sec2)

        # ── 3) Hormon değerleri ────────────────────────────────────────────
        sec3 = _section("Hormon Değerleri")
        s3l = QVBoxLayout(sec3)
        s3l.setContentsMargins(14, 12, 14, 12)
        s3l.setSpacing(8)
        t3 = QLabel("🩸 Hormon Değerleri (en son ölçülen)")
        t3.setObjectName("SectionTitle")
        s3l.addWidget(t3)

        f3 = QFormLayout()
        f3.setHorizontalSpacing(12)
        f3.setVerticalSpacing(6)
        f3.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        amh = QDoubleSpinBox()
        amh.setRange(0.0, 30.0)
        amh.setDecimals(2)
        amh.setSuffix(" ng/mL")
        amh.setSpecialValueText("—")
        amh.setMinimumWidth(120)
        f3.addRow("AMH:", amh)
        self._gynec_fields["amh"] = amh

        fsh = QDoubleSpinBox()
        fsh.setRange(0.0, 200.0)
        fsh.setDecimals(1)
        fsh.setSuffix(" mIU/mL")
        fsh.setSpecialValueText("—")
        fsh.setMinimumWidth(120)
        f3.addRow("FSH (3. gün):", fsh)
        self._gynec_fields["fsh"] = fsh

        lh = QDoubleSpinBox()
        lh.setRange(0.0, 200.0)
        lh.setDecimals(1)
        lh.setSuffix(" mIU/mL")
        lh.setSpecialValueText("—")
        lh.setMinimumWidth(120)
        f3.addRow("LH (3. gün):", lh)
        self._gynec_fields["lh"] = lh

        e2 = QDoubleSpinBox()
        e2.setRange(0.0, 5000.0)
        e2.setDecimals(1)
        e2.setSuffix(" pg/mL")
        e2.setSpecialValueText("—")
        e2.setMinimumWidth(120)
        f3.addRow("E2:", e2)
        self._gynec_fields["e2"] = e2

        prl = QDoubleSpinBox()
        prl.setRange(0.0, 500.0)
        prl.setDecimals(1)
        prl.setSuffix(" ng/mL")
        prl.setSpecialValueText("—")
        prl.setMinimumWidth(120)
        f3.addRow("Prolaktin:", prl)
        self._gynec_fields["prolactin"] = prl

        tsh = QDoubleSpinBox()
        tsh.setRange(0.0, 100.0)
        tsh.setDecimals(2)
        tsh.setSuffix(" µIU/mL")
        tsh.setSpecialValueText("—")
        tsh.setMinimumWidth(120)
        f3.addRow("TSH:", tsh)
        self._gynec_fields["tsh"] = tsh

        s3l.addLayout(f3)
        flay.addWidget(sec3)

        # ── 4) Önceki tedaviler ────────────────────────────────────────────
        sec4 = _section("Önceki Tedaviler")
        s4l = QVBoxLayout(sec4)
        s4l.setContentsMargins(14, 12, 14, 12)
        s4l.setSpacing(8)
        t4 = QLabel("💊 Önceki Tedaviler")
        t4.setObjectName("SectionTitle")
        s4l.addWidget(t4)

        f4 = QFormLayout()
        f4.setHorizontalSpacing(12)
        f4.setVerticalSpacing(6)
        f4.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)

        prior_iui = QSpinBox()
        prior_iui.setRange(0, 30)
        prior_iui.setSuffix(" siklus")
        prior_iui.setSpecialValueText("—")
        prior_iui.setMinimumWidth(120)
        f4.addRow("Önceki IUI:", prior_iui)
        self._gynec_fields["prior_iui"] = prior_iui

        prior_ivf = QSpinBox()
        prior_ivf.setRange(0, 30)
        prior_ivf.setSuffix(" siklus")
        prior_ivf.setSpecialValueText("—")
        prior_ivf.setMinimumWidth(120)
        f4.addRow("Önceki IVF/ICSI:", prior_ivf)
        self._gynec_fields["prior_ivf"] = prior_ivf

        treatment_used = QLineEdit()
        treatment_used.setPlaceholderText(
            "Klomifen / Letrozol / Gonadotropin / GnRH agonist...")
        f4.addRow("Kullanılan ilaç(lar):", treatment_used)
        self._gynec_fields["treatment_used"] = treatment_used

        s4l.addLayout(f4)
        flay.addWidget(sec4)

        # ── 5) Klinik notlar ───────────────────────────────────────────────
        sec5 = _section("Klinik Notlar")
        s5l = QVBoxLayout(sec5)
        s5l.setContentsMargins(14, 12, 14, 12)
        s5l.setSpacing(8)
        t5 = QLabel("📝 Klinik Notlar / Plan")
        t5.setObjectName("SectionTitle")
        s5l.addWidget(t5)

        notes = QTextEdit()
        notes.setMinimumHeight(120)
        notes.setMaximumHeight(180)
        notes.setPlaceholderText(
            "Tanı, tedavi planı, değerlendirme notları, izlem aralığı, "
            "eş için öneriler, sonraki randevu...")
        notes.setStyleSheet(
            "QTextEdit{background:#FFFFFF;color:#202020;"
            "border:1px solid #C8C8C8;font:11px 'Segoe UI';}")
        # v68-AI: Smart autocomplete for gynec notes
        try:
            SmartAutocomplete.attach(notes)
        except Exception as _ex:
            _log_warning(f"gynec notes autocomplete: {_ex}")
        s5l.addWidget(notes)
        self._gynec_fields["notes"] = notes
        flay.addWidget(sec5)

        flay.addStretch()
        scroll.setWidget(form_host)
        lay.addWidget(scroll, 1)

        # ── Action buttons ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        btn_save = QPushButton("💾 Kaydet")
        btn_save.setStyleSheet(
            "QPushButton{background:#107C10;color:white;padding:8px 22px;"
            "font:600 12px 'Segoe UI';border:none;border-radius:3px;}"
            "QPushButton:hover{background:#0B5C0B;}")
        btn_save.clicked.connect(self._save_gynec_followup)
        btn_row.addWidget(btn_save)

        btn_print = QPushButton("🖨 Yazdır")
        btn_print.setStyleSheet(
            "QPushButton{background:#B5368A;color:white;padding:8px 22px;"
            "font:600 12px 'Segoe UI';border:none;border-radius:3px;}"
            "QPushButton:hover{background:#8B2A6D;}")
        btn_print.clicked.connect(self._print_gynec_followup)
        btn_row.addWidget(btn_print)

        btn_clear = QPushButton("↺ Formu Temizle")
        btn_clear.setStyleSheet(
            "QPushButton{background:#F0F0F0;color:#404040;padding:8px 22px;"
            "font:500 12px 'Segoe UI';border:1px solid #C8C8C8;"
            "border-radius:3px;}"
            "QPushButton:hover{background:#E0E0E0;}")
        btn_clear.clicked.connect(self._clear_gynec_followup)
        btn_row.addWidget(btn_clear)

        btn_row.addStretch()

        lay.addLayout(btn_row)

        # v68-UI: Apply initial Kısa İzlem state
        try:
            self._apply_gyn_short_mode(self.gyn_short_chk.isChecked())
        except Exception as _ex:
            _log_warning("gyn build: apply short mode", exc=_ex)

        # Auto-load whenever a patient is selected (handler hooked
        # in _select_patient_by_path). For now, leave fields blank.
        return page

    def _gynec_db_init(self):
        """Lazily create the per-patient gyn-followup table in the
        same SQLite DB used for everything else."""
        try:
            with db_conn() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS gynec_followup ("
                    "patient_key TEXT PRIMARY KEY, data_json TEXT, "
                    "updated_at TEXT)")
                conn.commit()
        except Exception as ex:
            _log_warning("_gynec_db_init", exc=ex)

    def _save_gynec_followup(self):
        """Save the current form state for the active patient."""
        if not getattr(self, "_gynec_fields", None):
            return
        if self.current_patient is None:
            QMessageBox.information(
                self, "Hasta Yok",
                "Form kaydedilemedi — önce sol listeden bir hasta seçin. "
                "(Hasta seçilmeden form sadece şablon olarak gösteriliyor.)")
            return

        # Snapshot every field
        data = {}
        for key, w in self._gynec_fields.items():
            try:
                if isinstance(w, QSpinBox):
                    data[key] = w.value() if w.value() != w.minimum() else None
                elif isinstance(w, QDoubleSpinBox):
                    data[key] = w.value() if w.value() != w.minimum() else None
                elif isinstance(w, QComboBox):
                    txt = w.currentText()
                    data[key] = None if txt == "—" else txt
                elif isinstance(w, QLineEdit):
                    data[key] = w.text().strip() or None
                elif isinstance(w, QTextEdit):
                    data[key] = w.toPlainText().strip() or None
            except Exception as _ex:
                _log_warning(f"gynec save: {key}", exc=_ex)

        try:
            self._gynec_db_init()
            with db_conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO gynec_followup "
                    "(patient_key, data_json, updated_at) VALUES (?, ?, ?)",
                    (self.current_patient.name, json.dumps(data, ensure_ascii=False),
                     datetime.now().isoformat()))
                conn.commit()
            self.gynec_save_status_lbl.setText("✓ Kaydedildi")
            QTimer.singleShot(
                3000, lambda: self.gynec_save_status_lbl.setText(""))
            if hasattr(self, "statusBar"):
                self.statusBar().showMessage(
                    f"✓ Jinekolojik takip kaydedildi — "
                    f"{format_patient_name(self.current_patient.name)}", 4000)
        except Exception as ex:
            _log_warning("_save_gynec_followup", exc=ex)
            QMessageBox.critical(
                self, "Kaydetme Hatası",
                f"Form kaydedilemedi:\n\n{ex}")

    def _load_gynec_followup(self):
        """Load saved form state for the current patient (or clear)."""
        if not getattr(self, "_gynec_fields", None):
            return
        # Clear first
        self._clear_gynec_followup(silent=True)

        if self.current_patient is None:
            return
        try:
            self._gynec_db_init()
            with db_conn() as conn:
                cur = conn.execute(
                    "SELECT data_json FROM gynec_followup WHERE patient_key=?",
                    (self.current_patient.name,))
                row = cur.fetchone()
            if row is None:
                return
            data = json.loads(row[0])
        except Exception as ex:
            _log_warning("_load_gynec_followup", exc=ex)
            return

        for key, w in self._gynec_fields.items():
            val = data.get(key)
            if val is None:
                continue
            try:
                if isinstance(w, (QSpinBox, QDoubleSpinBox)):
                    w.setValue(val)
                elif isinstance(w, QComboBox):
                    idx = w.findText(val)
                    if idx >= 0:
                        w.setCurrentIndex(idx)
                elif isinstance(w, QLineEdit):
                    w.setText(val)
                elif isinstance(w, QTextEdit):
                    w.setPlainText(val)
            except Exception as _ex:
                _log_warning(f"gynec load: {key}", exc=_ex)

    def _clear_gynec_followup(self, silent: bool = False):
        """Reset all form fields to empty/default."""
        if not getattr(self, "_gynec_fields", None):
            return
        for key, w in self._gynec_fields.items():
            try:
                if isinstance(w, (QSpinBox, QDoubleSpinBox)):
                    w.setValue(w.minimum())
                elif isinstance(w, QComboBox):
                    w.setCurrentIndex(0)
                elif isinstance(w, QLineEdit):
                    w.clear()
                elif isinstance(w, QTextEdit):
                    w.clear()
            except Exception as _ex:
                _log_warning(f"gynec clear: {key}", exc=_ex)
        if not silent and hasattr(self, "gynec_save_status_lbl"):
            self.gynec_save_status_lbl.setText("Form temizlendi")
            QTimer.singleShot(
                2000, lambda: self.gynec_save_status_lbl.setText(""))

    def _print_gynec_followup(self):
        """Print the gyn followup form as a structured A4 document."""
        if not getattr(self, "_gynec_fields", None):
            return
        # Snapshot field values into a printable table
        rows = []
        labels = {
            "cycle_day": ("Siklus günü", " gün"),
            "endometrium": ("Endometrial kalınlık", " mm"),
            "endo_pattern": ("Endometrial pattern", ""),
            "afc_left": ("AFC — Sol over", ""),
            "afc_right": ("AFC — Sağ over", ""),
            "foll_left": ("En büyük folikül — Sol", " mm"),
            "foll_right": ("En büyük folikül — Sağ", " mm"),
            "amh": ("AMH", " ng/mL"),
            "fsh": ("FSH (3. gün)", " mIU/mL"),
            "lh": ("LH (3. gün)", " mIU/mL"),
            "e2": ("E2", " pg/mL"),
            "prolactin": ("Prolaktin", " ng/mL"),
            "tsh": ("TSH", " µIU/mL"),
            "prior_iui": ("Önceki IUI", " siklus"),
            "prior_ivf": ("Önceki IVF/ICSI", " siklus"),
            "treatment_used": ("Kullanılan ilaç(lar)", ""),
        }
        for key, (lbl, unit) in labels.items():
            w = self._gynec_fields.get(key)
            if w is None:
                continue
            val = "—"
            try:
                if isinstance(w, (QSpinBox, QDoubleSpinBox)):
                    if w.value() != w.minimum():
                        val = f"{w.value()}{unit}"
                elif isinstance(w, QComboBox):
                    val = w.currentText() if w.currentText() != "—" else "—"
                elif isinstance(w, QLineEdit):
                    val = w.text().strip() or "—"
            except Exception as _ex:
                _log_warning("gynec print: read field", exc=_ex)
            rows.append((lbl, val))

        notes_w = self._gynec_fields.get("notes")
        notes_text = notes_w.toPlainText().strip() if notes_w else ""

        pname = "—"
        if self.current_patient is not None:
            pname = format_patient_name(self.current_patient.name)
        today = datetime.now().strftime("%d.%m.%Y")

        rows_html = "".join(
            f"<tr><td style='padding:4px 10px;color:#404040;width:55%;'>"
            f"{lbl}</td>"
            f"<td style='padding:4px 10px;font-weight:600;color:#202020;'>"
            f"{val}</td></tr>"
            for lbl, val in rows)

        html = f"""
<html><head><meta charset="utf-8">
<style>
  body{{font-family:'Segoe UI',Arial,sans-serif;margin:20px 30px;color:#202020;}}
  .header{{border-bottom:3px solid #B5368A;padding-bottom:12px;margin-bottom:18px;}}
  .clinic{{font-size:11px;color:#606060;text-align:right;}}
  .doc-title{{font-size:20px;font-weight:800;color:#B5368A;margin:10px 0 6px 0;}}
  .meta{{font-size:13px;color:#404040;}}
  table{{width:100%;border-collapse:collapse;margin-top:8px;}}
  tr:nth-child(even){{background:#FCF5F9;}}
  .notes{{margin-top:18px;padding:12px 16px;background:#FCF5F9;
          border-left:4px solid #B5368A;border-radius:3px;}}
</style></head>
<body>
  <div class="header">
    <div class="clinic">
      <b>{get_clinic_doctor_name()}</b><br>
      Kadın Hastalıkları ve Doğum<br>
      İnfertilite ve Üreme Endokrinolojisi
    </div>
    <div class="doc-title">🌸 Jinekolojik Takip Formu</div>
    <div class="meta">Hasta: <b>{pname}</b> &nbsp;·&nbsp; Tarih: <b>{today}</b></div>
  </div>
  <table>{rows_html}</table>
  {f'<div class="notes"><b>📝 Klinik Notlar:</b><br>{notes_text.replace(chr(10), "<br>")}</div>' if notes_text else ""}
</body></html>"""

        # Show preview + print dialog
        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle(f"Jinekolojik Takip — Yazdır — {pname}")
        dlg.resize(780, 720)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(12, 12, 12, 12)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setStyleSheet(
            "QTextEdit{background:#FFFFFF;color:#202020;"
            "border:1px solid #C8C8C8;}")
        txt.setHtml(html)
        v.addWidget(txt, 1)

        btn_row = QHBoxLayout()
        btn_print = QPushButton("🖨 Yazdır")
        btn_print.setStyleSheet(
            "QPushButton{background:#B5368A;color:white;padding:8px 22px;"
            "font:600 12px 'Segoe UI';border:none;border-radius:3px;}"
            "QPushButton:hover{background:#8B2A6D;}")

        def _do_print():
            # v68-UI: Use the central print_text_widget helper
            # for reliable printing across Windows drivers.
            ok, msg = print_text_widget(txt, parent_dialog=dlg,
                                        title="Yazdır")
            try:
                self.statusBar().showMessage(msg, 5000)
            except Exception as _ex:
                _log_warning("_do_print: status", exc=_ex)
            if not ok and "iptal" not in (msg or "").lower():
                QMessageBox.warning(dlg, "Yazdırma", msg)
        btn_print.clicked.connect(_do_print)

        btn_close = QPushButton("Kapat")
        btn_close.setShortcut("Escape")
        btn_close.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_print)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        v.addLayout(btn_row)
        dlg.exec()

    def _refresh_gynec_tab_visibility(self):
        """Show or hide the Jinekolojik Takip / Gebelik Takibi tabs
        based on current mode. Called whenever mode changes (auto
        detect or manual toggle) and whenever the patient changes.

        v68: Visibility rules:
          • Obstetric mode: "📋 Gebelik Takibi" tab VISIBLE at top.
          • Gynecology mode: "🌸 Jinekolojik Takip" tab VISIBLE at top
            (next to Notlar), symmetric with the obstetric form tab.
          Each mode's form is accessed via its dedicated top tab —
          clean, discoverable, no hidden-tab weirdness.
        Also updates the "Bu Hafta Yapılabilecekler" box and the
        quick-action labels / button visibility.
        """
        if not hasattr(self, "tabs") or \
           not hasattr(self, "_gynec_tab_index"):
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
            _log_warning("_refresh_gynec_tab_visibility", exc=_ex)
        # Jinekolojik tab — visible only in gyn mode (top tab bar)
        try:
            self.tabs.setTabVisible(self._gynec_tab_index, is_gyn)
        except Exception as _ex:
            _log_warning("_refresh_gynec_tab: setTabVisible gyn", exc=_ex)
        # Gebelik Takibi tab — visible only in obstetric mode
        try:
            if hasattr(self, "_obs_tab_index"):
                self.tabs.setTabVisible(
                    self._obs_tab_index, not is_gyn)
        except Exception as _ex:
            _log_warning(
                "_refresh_gynec_tab: setTabVisible obs", exc=_ex)
        # "Bu Hafta Yapılabilecekler" mode-aware
        try:
            if hasattr(self, "_update_ga_recommendations"):
                self._update_ga_recommendations()
        except Exception as _ex:
            _log_warning(
                "_refresh_gynec_tab: ga rec box", exc=_ex)
        # Quick-action button labels + visibility
        try:
            if hasattr(self, "_refresh_quick_action_labels"):
                self._refresh_quick_action_labels()
        except Exception as _ex:
            _log_warning(
                "_refresh_gynec_tab: qa labels", exc=_ex)
        # Flags list — obstetric vs gynecologic set
        try:
            if hasattr(self, "_refresh_flags_for_mode"):
                self._refresh_flags_for_mode()
        except Exception as _ex:
            _log_warning(
                "_refresh_gynec_tab: flags", exc=_ex)

    def _build_tab_notes(self) -> QWidget:
        """Notes tab — historical view of all visits + per-visit PDF summary
        and editable doctor's note. Newest visit on top.

        Layout:
          [ visits list (left) ] | [ summary (top) + note (bottom) (right) ]
          [ phone row + WhatsApp/Copy buttons across the bottom ]
        """
        page = QWidget()
        page.setObjectName("TabPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(6)

        # Header
        notes_hdr = QHBoxLayout()
        nl = QLabel("📝  Hasta Geliş Notları")
        nl.setObjectName("BoxTitle")
        notes_hdr.addWidget(nl)
        notes_hdr.addStretch()
        self.note_save_lbl = QLabel("✓ Kaydedildi")
        self.note_save_lbl.setObjectName("SaveStatus")
        self.note_save_lbl.hide()
        notes_hdr.addWidget(self.note_save_lbl)
        lay.addLayout(notes_hdr)

        # ── Main horizontal split ────────────────────────────────────────
        main_split = QSplitter(Qt.Horizontal)
        main_split.setHandleWidth(6)
        main_split.setChildrenCollapsible(False)

        # LEFT: visits list (newest on top)
        left_box = QFrame()
        left_box.setObjectName("InnerBox")
        ll = QVBoxLayout(left_box)
        ll.setContentsMargins(6, 6, 6, 6)
        ll.setSpacing(4)
        ll_hdr = QLabel("Tüm Gelişler (en yeni üstte)")
        ll_hdr.setStyleSheet(accent_label_style(font_size=11))
        ll.addWidget(ll_hdr)

        self.notes_visits_list = QListWidget()
        self.notes_visits_list.setObjectName("WorkList")
        self.notes_visits_list.setAlternatingRowColors(True)
        self.notes_visits_list.setUniformItemSizes(False)
        self.notes_visits_list.currentItemChanged.connect(
            self._on_notes_visits_list_changed)
        ll.addWidget(self.notes_visits_list, 1)
        main_split.addWidget(left_box)

        # RIGHT: vertical split — top: summary  bottom: note editor
        right_split = QSplitter(Qt.Vertical)
        right_split.setHandleWidth(6)
        right_split.setChildrenCollapsible(False)

        # Summary (top half)
        sum_box = QFrame()
        sum_box.setObjectName("InnerBox")
        sl = QVBoxLayout(sum_box)
        sl.setContentsMargins(6, 6, 6, 6)
        sl.setSpacing(4)
        sl_hdr = QLabel("📋  Geliş PDF Özeti")
        sl_hdr.setStyleSheet(accent_label_style(font_size=11))
        sl.addWidget(sl_hdr)
        self.notes_summary_text = QTextEdit()
        self.notes_summary_text.setReadOnly(True)
        self.notes_summary_text.setStyleSheet(
            "background:#FAFAFA;border:1px solid #C8C8C8;font:11px 'Segoe UI';")
        sl.addWidget(self.notes_summary_text, 1)
        right_split.addWidget(sum_box)

        # Note editor (bottom half)
        note_box = QFrame()
        note_box.setObjectName("InnerBox")
        nl_l = QVBoxLayout(note_box)
        nl_l.setContentsMargins(6, 6, 6, 6)
        nl_l.setSpacing(4)
        nl_hdr = QHBoxLayout()
        note_lbl = QLabel("✏️  Bu Gelişe Ait Not")
        note_lbl.setStyleSheet(accent_label_style(font_size=11))
        nl_hdr.addWidget(note_lbl)
        nl_hdr.addStretch()
        self.notes_visit_save_lbl = QLabel("✓ Kaydedildi")
        self.notes_visit_save_lbl.setStyleSheet(
            "color:#107C10;font:600 10px 'Segoe UI';background:transparent;")
        self.notes_visit_save_lbl.hide()
        nl_hdr.addWidget(self.notes_visit_save_lbl)

        # v68-AI: "Sık Kullandığın İfadeler" quick-insert button
        self.phrases_btn = QPushButton("💡 Sık Kullanılan")
        self.phrases_btn.setCursor(Qt.PointingHandCursor)
        self.phrases_btn.setToolTip(
            "En çok kullandığın ifadeleri göster — tek tıkla not "
            "alanına ekle. AI, yazdıklarından öğrenir.")
        self.phrases_btn.setStyleSheet(
            "QPushButton{background:#F5F3FA;color:#5A1FB8;"
            "border:1px solid #C8B8E0;padding:4px 10px;"
            "font:600 10px 'Segoe UI';border-radius:3px;}"
            "QPushButton:hover{background:#E8DDFA;}")
        self.phrases_btn.clicked.connect(self._show_common_phrases_popup)
        nl_hdr.addWidget(self.phrases_btn)

        nl_l.addLayout(nl_hdr)

        self.note_edit = QTextEdit()
        self.note_edit.setObjectName("NoteEdit")
        self.note_edit.setPlaceholderText(
            "Bu geliş için not girin — yazdıkça otomatik kaydedilir.\n"
            "💡 Yazdıkça AI tıbbi terim ve sık kullandığın ifadeleri "
            "önerir (Ctrl+Boşluk veya tabloda gözüken seçeneği seç).\n"
            "Eski gelişlerin notları sol listedeki gelişe tıklayınca burada görünür.")
        self.note_edit.textChanged.connect(self._on_note_changed)
        # v68-AI: Attach smart autocomplete (medical terms + learned phrases)
        try:
            SmartAutocomplete.attach(self.note_edit)
        except Exception as _ex:
            _log_warning(f"note_edit autocomplete attach: {_ex}")
        # v68-AI: Attach spell-check (wavy red underline + right-click fix)
        try:
            attach_spell_check(self.note_edit)
        except Exception as _ex:
            _log_warning(f"note_edit spell-check attach: {_ex}")
        nl_l.addWidget(self.note_edit, 1)
        right_split.addWidget(note_box)

        right_split.setSizes([300, 250])
        main_split.addWidget(right_split)
        main_split.setSizes([300, 700])

        lay.addWidget(main_split, 1)

        # ── Phone + WhatsApp row (kept from old design) ──────────────────
        phone_box = QFrame()
        phone_box.setObjectName("InnerBox")
        pb = QHBoxLayout(phone_box)
        pb.setContentsMargins(8, 6, 8, 6)
        pb.setSpacing(6)

        phone_lbl = QLabel("WhatsApp No:")
        phone_lbl.setObjectName("PhoneLabel")
        pb.addWidget(phone_lbl)
        self.phone_input = QLineEdit(get_default_whatsapp_number())
        self.phone_input.setObjectName("PhoneBox")
        self.phone_input.textChanged.connect(self._on_phone_changed)
        self.phone_input.editingFinished.connect(self.save_current_patient_phone)
        pb.addWidget(self.phone_input, 1)
        self.phone_mark_label = QLabel("Özel")
        self.phone_mark_label.setObjectName("PhoneMark")
        self.phone_mark_label.hide()
        pb.addWidget(self.phone_mark_label)
        self.save_status_label = QLabel("Kayıtlı")
        self.save_status_label.setObjectName("SaveStatus")
        self.save_status_label.hide()
        pb.addWidget(self.save_status_label)
        lay.addWidget(phone_box)

        # Action buttons
        row1 = QHBoxLayout()
        row1.setSpacing(4)
        self.copy_btn_notes = ActionButton("Özet+Not Kopyala")
        self.copy_btn_notes.clicked.connect(self.copy_summary)
        self.whatsapp_btn = ActionButton("WhatsApp Hazırla")
        self.whatsapp_btn.clicked.connect(self.prepare_whatsapp)
        row1.addStretch()
        row1.addWidget(self.copy_btn_notes)
        row1.addWidget(self.whatsapp_btn)
        lay.addLayout(row1)

        # State for the notes tab
        self._notes_current_visit_path: Optional[Path] = None

        return page

    def _schedule_gynec_autosave(self):
        """Schedule an autosave after edits; debounce edits within
        1.5 seconds."""
        if hasattr(self, "gynec_save_lbl"):
            self.gynec_save_lbl.hide()
        if hasattr(self, "_gynec_save_timer"):
            self._gynec_save_timer.start(1500)

    def _auto_save_gynec_form(self):
        """Write the gynec form values to the SQLite patient_gynec
        table keyed on patient_key. If no patient is selected, silently
        buffer in memory under a special '__template__' key so the
        doctor can still fill in a template without losing work."""
        pkey = "__template__"
        if self.current_patient is not None:
            pkey = self.current_patient.name
        try:
            if not hasattr(self, "_gynec_form_widgets"):
                return
            data = {}
            for key, widget in self._gynec_form_widgets.items():
                if isinstance(widget, QTextEdit):
                    data[key] = widget.toPlainText()
                elif isinstance(widget, QLineEdit):
                    data[key] = widget.text()
            _save_gynec_form_data(pkey, data)
            if hasattr(self, "gynec_save_lbl"):
                self.gynec_save_lbl.setText("✓ Kaydedildi")
                self.gynec_save_lbl.show()
        except Exception as _ex:
            _log_warning("_auto_save_gynec_form", exc=_ex)

    def _save_gynec_form_now(self):
        """Explicit save button handler — same as autosave but triggers
        a visible status bar message for confirmation."""
        self._auto_save_gynec_form()
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(
                "✓ Jinekolojik takip formu kaydedildi", 3000)

    def _load_gynec_form(self):
        """Load the saved form values (if any) into the UI. Called when
        a new patient is selected or the tab is shown."""
        pkey = "__template__"
        if self.current_patient is not None:
            pkey = self.current_patient.name
        try:
            if not hasattr(self, "_gynec_form_widgets"):
                # Form widget'ı henüz oluşturulmamış (jinekoloji
                # tab'ı ilk kez açılırken çağrılmış) — sessizce çık.
                return
            data = _load_gynec_form_data(pkey)
            for key, widget in self._gynec_form_widgets.items():
                val = data.get(key, "")
                if isinstance(widget, QTextEdit):
                    widget.blockSignals(True)
                    widget.setPlainText(val)
                    widget.blockSignals(False)
                elif isinstance(widget, QLineEdit):
                    widget.blockSignals(True)
                    widget.setText(val)
                    widget.blockSignals(False)
        except Exception as _ex:
            _log_warning("_load_gynec_form", exc=_ex)

    def _clear_gynec_form(self):
        """Empty all form fields after confirmation."""
        reply = QMessageBox.question(
            self, "Form Temizle",
            "Tüm jinekolojik takip alanlarını temizlemek istediğinize "
            "emin misiniz?\n\nYazılı değerler silinecek.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        if not hasattr(self, "_gynec_form_widgets"):
            return
        for widget in self._gynec_form_widgets.values():
            if isinstance(widget, QTextEdit):
                widget.blockSignals(True)
                widget.clear()
                widget.blockSignals(False)
            elif isinstance(widget, QLineEdit):
                widget.blockSignals(True)
                widget.clear()
                widget.blockSignals(False)
        # Persist the cleared state
        self._auto_save_gynec_form()

    def _print_gynec_form(self):
        """Render the form as a printable handout (HTML → QPrinter)."""
        pname = "—"
        if self.current_patient is not None:
            pname = format_patient_name(self.current_patient.name)
        today = datetime.now().strftime("%d.%m.%Y")

        # Gather values
        def _g(k):
            if not hasattr(self, "_gynec_form_widgets"):
                return "—"
            w = self._gynec_form_widgets.get(k)
            if w is None:
                return "—"
            if isinstance(w, QTextEdit):
                t = w.toPlainText().strip()
            else:
                t = w.text().strip()
            return t if t else "—"

        rows = []
        def _grp(title, fields):
            rows.append(
                f'<tr><td colspan="2" style="background:#FCE5F2;'
                f'color:#8B2A6D;padding:8px 10px;font-weight:700;'
                f'font-size:12px;">{title}</td></tr>')
            for label, key in fields:
                rows.append(
                    f'<tr>'
                    f'<td style="padding:6px 10px;background:#FAFAFA;'
                    f'border-bottom:1px solid #E8E8E8;width:40%;'
                    f'font-size:11px;color:#606060;">{label}</td>'
                    f'<td style="padding:6px 10px;border-bottom:1px '
                    f'solid #E8E8E8;font-size:12px;color:#202020;'
                    f'font-weight:500;">{_g(key)}</td>'
                    f'</tr>')

        _grp("👤 Hasta Bilgisi", [
            ("Yaş", "age"), ("Kilo (kg)", "weight"),
            ("Boy (cm)", "height"), ("BMI", "bmi"),
            ("Meslek", "occupation"),
            ("Sigara/Alkol", "smoke_alcohol"),
        ])
        _grp("🩸 Adet Öyküsü", [
            ("Son adet tarihi", "lmp"),
            ("Menarş yaşı", "menarche_age"),
            ("Siklus düzeni", "cycle_regularity"),
            ("Akış/süre", "flow_duration"),
            ("Dismenore", "dysmenorrhea"),
        ])
        _grp("🤰 Obstetrik Öykü", [
            ("Gebelik (G)", "gravida"),
            ("Doğum (P)", "parity"),
            ("Abortus/küretaj", "abortion"),
            ("Dış gebelik/molar", "ectopic_molar"),
        ])
        _grp("💑 İnfertilite Öyküsü", [
            ("Süre", "infert_duration"),
            ("Birincil/İkincil", "infert_type"),
            ("Önceki gebelikler", "prev_pregnancies"),
        ])
        _grp("🧬 Hormon Profili", [
            ("AMH (ng/mL)", "amh"),
            ("FSH (mIU/mL)", "fsh"),
            ("LH (mIU/mL)", "lh"),
            ("E2 (pg/mL)", "e2"),
            ("TSH (mIU/L)", "tsh"),
            ("Prolaktin (ng/mL)", "prolactin"),
            ("DHEA-S", "dhea_s"),
            ("Testosteron", "testo"),
            ("17-OHP", "hdp17"),
            ("Progesteron (21.gün)", "progesterone"),
        ])
        _grp("🔬 Görüntüleme", [
            ("Endometrial kalınlık", "endometrium_mm"),
            ("AFC", "afc_total"),
            ("Sağ over", "right_ovary"),
            ("Sol over", "left_ovary"),
            ("Uterus", "uterus_size"),
            ("Patoloji", "pathology"),
            ("HSG", "hsg_result"),
        ])
        _grp("👨 Eş / Erkek Faktörü", [
            ("Eş yaşı", "partner_age"),
            ("Konsantrasyon", "sperm_conc"),
            ("Motilite", "sperm_motility"),
            ("Morfoloji", "sperm_morph"),
            ("Hacim", "sperm_volume"),
            ("DNA Fragmantasyon", "sperm_dfi"),
        ])
        _grp("💊 Önceki Tedaviler", [
            ("IUI siklus", "iui_cycles"),
            ("IVF siklus", "ivf_cycles"),
            ("Protokoller", "protocols"),
            ("Komplikasyonlar", "complications"),
        ])
        notes_val = _g("notes")
        if notes_val != "—":
            rows.append(
                '<tr><td colspan="2" style="background:#FCE5F2;'
                'color:#8B2A6D;padding:8px 10px;font-weight:700;'
                'font-size:12px;">📝 Notlar</td></tr>')
            rows.append(
                f'<tr><td colspan="2" style="padding:8px 12px;'
                f'white-space:pre-wrap;font-size:12px;">{notes_val}</td></tr>')

        html = f"""
<html><head><meta charset="utf-8"><style>
  body {{font-family:'Segoe UI',Arial,sans-serif;margin:20px 30px;color:#202020;}}
  .header {{border-bottom:3px solid #B5368A;padding-bottom:12px;margin-bottom:16px;}}
  .clinic {{font-size:11px;color:#606060;text-align:right;}}
  .doc-title {{font-size:20px;font-weight:800;color:#B5368A;margin:12px 0 6px 0;}}
  .meta {{font-size:13px;color:#404040;}}
  table {{border-collapse:collapse;width:100%;margin-top:6px;}}
</style></head><body>
  <div class="header">
    <div class="clinic">
      <b>{get_clinic_doctor_name()}</b><br>
      Kadın Hastalıkları ve Doğum<br>
      İnfertilite ve Üreme Endokrinolojisi
    </div>
    <div class="doc-title">🌸 Jinekolojik / İnfertilite Takip Formu</div>
    <div class="meta">Hasta: <b>{pname}</b> &nbsp;·&nbsp; Tarih: <b>{today}</b></div>
  </div>
  <table>{''.join(rows)}</table>
</body></html>"""

        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("Jinekolojik Takip Formu — Yazdır")
        dlg.resize(780, 760)
        v = QVBoxLayout(dlg)
        v.setContentsMargins(12, 12, 12, 12)
        txt = QTextEdit()
        txt.setReadOnly(True)
        txt.setStyleSheet(
            "QTextEdit{background:#FFFFFF;color:#202020;"
            "border:1px solid #C8C8C8;}")
        txt.setHtml(html)
        v.addWidget(txt, 1)

        btn_row = QHBoxLayout()
        btn_p = QPushButton("🖨 Yazdır")
        btn_p.setStyleSheet(
            "QPushButton{background:#B5368A;color:white;padding:8px 22px;"
            "font:600 12px 'Segoe UI';border:none;border-radius:3px;}"
            "QPushButton:hover{background:#8B2A6D;}")
        def _do_print():
            # v68-UI: Use the central print_text_widget helper
            # for reliable printing across Windows drivers.
            ok, msg = print_text_widget(txt, parent_dialog=dlg,
                                        title="Yazdır")
            try:
                self.statusBar().showMessage(msg, 5000)
            except Exception as _ex:
                _log_warning("_do_print: status", exc=_ex)
            if not ok and "iptal" not in (msg or "").lower():
                QMessageBox.warning(dlg, "Yazdırma", msg)
        btn_p.clicked.connect(_do_print)
        btn_row.addWidget(btn_p)
        btn_row.addStretch()
        btn_c = QPushButton("Kapat")
        btn_c.setShortcut("Escape")
        btn_c.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_c)
        v.addLayout(btn_row)
        dlg.exec()

    def _build_tab_signature(self) -> QWidget:
        page = QWidget()
        page.setObjectName("TabPage")
        lay = QVBoxLayout(page)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        ttl = QLabel("Takip İmzası Durumu")
        ttl.setObjectName("BoxTitle")
        lay.addWidget(ttl)

        sig_frame = QFrame()
        sig_frame.setObjectName("SigFrame")
        sig_v = QVBoxLayout(sig_frame)
        sig_v.setContentsMargins(10, 8, 10, 8)
        sig_v.setSpacing(6)

        sig_top = QHBoxLayout()
        sig_top.setSpacing(8)
        self.signature_alert = QLabel("İmza durumu bekleniyor...")
        self.signature_alert.setObjectName("SigAlert")
        self.signature_alert.setWordWrap(True)
        sig_top.addWidget(self.signature_alert, 1)
        self.signature_btn = ActionButton("İmzayı Kaydet", primary=True)
        self.signature_btn.clicked.connect(self.mark_signature_received)
        self.signature_btn.setMinimumWidth(180)
        self.signature_btn.setMinimumHeight(32)
        sig_top.addWidget(self.signature_btn)
        sig_v.addLayout(sig_top)

        self.signature_status_label = QLabel("")
        self.signature_status_label.setObjectName("SigStatus")
        self.signature_status_label.setWordWrap(True)
        sig_v.addWidget(self.signature_status_label)
        lay.addWidget(sig_frame)

        # History table
        hist_lbl = QLabel("İmza Geçmişi (son 5)")
        hist_lbl.setObjectName("BoxTitle")
        lay.addWidget(hist_lbl)

        self.signature_history_table = QTableWidget(0, 3)
        self.signature_history_table.setObjectName("DataTable")
        self.signature_history_table.setHorizontalHeaderLabels(["Tarih / Saat", "Hafta", "Geliş"])
        self.signature_history_table.verticalHeader().setVisible(False)
        self.signature_history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.signature_history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.signature_history_table.setAlternatingRowColors(True)
        h = self.signature_history_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        lay.addWidget(self.signature_history_table, 1)

        return page

    def _apply_style(self):
        # ─── GE ViewPoint 6 authentic theme ───────────────────────────────────
        # ViewPoint 6 uses a classic light Windows look with subtle blue accents.
        # Palette:
        #   chrome bg       #F0F0F0   (window, menubar, toolbars, status bar)
        #   panel bg        #F5F5F5   (side panels)
        #   work surface    #FFFFFF   (lists, tables, content)
        #   alt row         #F7F7F7
        #   divider         #C8C8C8
        #   thin border     #ABABAB
        #   text default    #202020
        #   text muted      #606060
        #   accent blue     #0078D4   (selection, focus, highlights)
        #   accent dark     #005A9E   (pressed, headers underline)
        #   header band     #E5EEF7   (light blue group headers)
        #   warn orange     #C46500
        #   ok green        #107C10
        self.setStyleSheet("""
            /* ── Base ─────────────────────────────────────────────────────── */
            QMainWindow, #BackgroundRoot {
                background: #F0F0F0;
            }
            QWidget { font-family: 'Segoe UI'; font-size: 12px; color: #202020; }

            /* ── Menu bar ──────────────────────────────────────────────────── */
            QMenuBar {
                background: #F0F0F0;
                border-bottom: 1px solid #C8C8C8;
                color: #202020;
                font: 400 12px 'Segoe UI';
                padding: 1px 0;
            }
            QMenuBar::item {
                background: transparent;
                color: #202020;
                padding: 4px 10px;
            }
            QMenuBar::item:selected { background: #CCE4F7; color: #202020; }
            QMenuBar::item:pressed  { background: #92C0E0; color: #202020; }
            QMenu {
                background: #FFFFFF;
                border: 1px solid #ABABAB;
                color: #202020;
                font: 400 12px 'Segoe UI';
                padding: 2px 0;
            }
            QMenu::item { padding: 5px 28px; color: #202020; }
            QMenu::item:selected { background: #CCE4F7; color: #202020; }
            QMenu::separator { height: 1px; background: #C8C8C8; margin: 3px 4px; }

            /* ── Toolbar (v68 modern flat design) ─────────────────────────── */
            QToolBar#MainToolbar {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #FFFFFF, stop:1 #F4F8FC);
                border: none;
                border-bottom: 1px solid #D8E4EE;
                spacing: 2px;
                padding: 4px 6px;
            }
            QToolBar#MainToolbar::separator {
                background: #D8E4EE;
                width: 1px;
                margin: 6px 6px;
            }
            QToolBar#MainToolbar QToolButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 6px 12px;
                font: 500 12px 'Segoe UI';
                color: #303030;
            }
            QToolBar#MainToolbar QToolButton:hover {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #F0F6FC, stop:1 #E0EDF8);
                border: 1px solid #B8D4E8;
                color: #003F6F;
            }
            QToolBar#MainToolbar QToolButton:pressed {
                background: #CCE4F7;
                border: 1px solid #0078D4;
                color: #003F6F;
            }
            #ToolbarLabel {
                color: #404040;
                font: 500 12px 'Segoe UI';
                background: transparent;
                padding: 0 4px;
            }

            /* ── Splitter (v68 modern) ────────────────────────────────────── */
            QSplitter#MainSplitter::handle {
                background: #E5EAEF;
                border: none;
            }
            QSplitter#MainSplitter::handle:hover { background: #0078D4; }

            /* ── Left panel ────────────────────────────────────────────────── */
            #LeftPanel {
                background: #F8FAFC;
                border-right: 1px solid #D8E4EE;
            }
            #BoxTitle {
                color: #003F6F;
                font: 700 13px 'Segoe UI';
                background: transparent;
                border: none;
                padding: 6px 4px;
                margin-bottom: 0;
            }
            #PIName {
                color: #003F6F;
                font: 800 15px 'Segoe UI';
                padding: 4px 0 8px 0;
                background: transparent;
                border-bottom: 2px solid #E5EAEF;
            }
            #PILabel {
                color: #707888;
                font: 500 11.5px 'Segoe UI';
            }
            #PIValue {
                color: #1a1a1a;
                font: 600 12px 'Segoe UI';
            }

            /* ── Tree (Worklist) ───────────────────────────────────────────── */
            #Tree {
                background: #FFFFFF;
                alternate-background-color: #F7F7F7;
                border: 1px solid #ABABAB;
                color: #202020;
                font: 400 12px 'Segoe UI';
                outline: 0;
            }
            #Tree::item {
                padding: 3px 3px;
                border: none;
            }
            #Tree::item:hover {
                background: #E5F1FB;
            }
            #Tree::item:selected {
                background: #CCE4F7;
                color: #202020;
            }
            #Tree::item:selected:!active {
                background: #E5EEF7;
                color: #202020;
            }
            #Tree::branch:has-siblings:!adjoins-item { border-image: none; }
            #Tree::branch:has-siblings:adjoins-item { border-image: none; }
            #Tree::branch:!has-children:!has-siblings:adjoins-item { border-image: none; }
            QHeaderView::section {
                background: #ECECEC;
                border: none;
                border-right: 1px solid #C8C8C8;
                border-bottom: 1px solid #ABABAB;
                padding: 4px 8px;
                color: #202020;
                font: 600 12px 'Segoe UI';
            }

            /* ── Center / tabs (v68 modern flat) ──────────────────────────── */
            #CenterPanel { background: #F8FAFC; }
            QTabWidget#MainTabs::pane {
                background: #F8FAFC;
                border: none;
                border-top: 1px solid #D8E4EE;
                top: -1px;
            }
            QTabWidget#MainTabs::tab-bar { left: 8px; }
            QTabBar::tab {
                background: transparent;
                color: #606060;
                border: none;
                border-bottom: 3px solid transparent;
                padding: 9px 20px 7px 20px;
                margin-right: 2px;
                font: 500 12px 'Segoe UI';
                min-width: 80px;
            }
            QTabBar::tab:hover {
                background: #F0F6FC;
                color: #003F6F;
                border-bottom: 3px solid #B8D4E8;
            }
            QTabBar::tab:selected {
                background: transparent;
                color: #003F6F;
                font: 700 12px 'Segoe UI';
                border-bottom: 3px solid #0078D4;
            }
            #TabPage { background: #F8FAFC; }

            /* ── Inner boxes ───────────────────────────────────────────────── */
            #InnerBox {
                background: #FFFFFF;
                border: 1px solid #ABABAB;
                border-radius: 0;
            }
            #InfoStrip {
                background: #E5EEF7;
                border: 1px solid #ABABAB;
                border-radius: 0;
            }
            #VisitInfo {
                color: #005A9E;
                font: 700 13px 'Segoe UI';
                background: transparent;
            }
            #TwinBadge {
                background: #FFF4E0;
                color: #C46500;
                font: 700 11px 'Segoe UI';
                border: 1px solid #C46500;
                border-radius: 0;
                padding: 2px 8px;
            }
            #InfoText {
                color: #202020;
                font: 400 12px 'Segoe UI';
                background: #FFF8E0;
                border: 1px solid #C46500;
                border-left: 3px solid #C46500;
                padding: 6px 10px;
            }

            /* ── Summary text ──────────────────────────────────────────────── */
            #SummaryText {
                background: #FFFFFF;
                border: 1px solid #ABABAB;
                border-radius: 0;
                color: #202020;
                padding: 8px;
                font: 400 12px 'Segoe UI';
                selection-background-color: #0078D4;
                selection-color: #FFFFFF;
            }

            /* ── Doctor note ───────────────────────────────────────────────── */
            #NoteEdit {
                background: #FFFEF5;
                border: 1.5px solid #E8DDB8;
                border-radius: 8px;
                color: #1a1a1a;
                padding: 10px 12px;
                font: 500 12px 'Segoe UI';
            }
            #NoteEdit:focus {
                border: 1.5px solid #C46500;
                background: #FFFFFF;
            }

            /* ── Phone ─────────────────────────────────────────────────────── */
            #PhoneLabel {
                color: #202020;
                font: 600 12px 'Segoe UI';
                background: transparent;
            }
            #PhoneBox, #SearchBox, #PlainInput {
                background: #FFFFFF;
                border: 1.5px solid #D8E4EE;
                border-radius: 6px;
                padding: 6px 10px;
                color: #1a1a1a;
                font: 500 12px 'Segoe UI';
            }
            #PhoneBox:focus, #SearchBox:focus, #PlainInput:focus {
                border: 1.5px solid #0078D4;
                background: #FFFFFF;
            }
            #SearchBox {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #FFFFFF, stop:1 #F8FAFC);
            }
            #SearchBox:focus {
                background: #FFFFFF;
            }
            #PhoneMark {
                color: #C46500;
                font: 700 11px 'Segoe UI';
                background: #FFF4E0;
                border: 1px solid #C46500;
                border-radius: 0;
                padding: 2px 6px;
            }
            #SaveStatus {
                color: #107C10;
                font: 700 11px 'Segoe UI';
                background: #E6F4E6;
                border: 1px solid #107C10;
                border-radius: 0;
                padding: 2px 6px;
            }

            /* ── Image picker ──────────────────────────────────────────────── */
            #ImageScroll, #ThumbScroll {
                background: #FFFFFF;
                border: 1px solid #E5EAEF;
                border-radius: 8px;
            }
            #ImageListHost, #ThumbHost { background: #FFFFFF; }
            #ImageCheck {
                color: #1a1a1a;
                font: 500 12px 'Segoe UI';
                padding: 4px 8px;
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
            }
            #ImageCheck:hover {
                background: #F0F6FC;
                color: #003F6F;
            }
            #ImageCheck::indicator {
                width: 14px; height: 14px;
            }
            #OptCheck {
                color: #202020;
                font: 400 12px 'Segoe UI';
            }
            #OptCheck::indicator { width: 14px; height: 14px; }

            #MiniBtn {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #FFFFFF, stop:1 #F4F8FC);
                border: 1.5px solid #C0D4E4;
                border-radius: 6px;
                color: #303030;
                font: 600 11.5px 'Segoe UI';
                padding: 6px 12px;
            }
            #MiniBtn:hover {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #E5F1FB, stop:1 #CCE4F7);
                border: 1.5px solid #0078D4;
                color: #003F6F;
            }
            #MiniBtn:pressed {
                background: #A8D4F0;
                border: 1.5px solid #005A9E;
                color: #003F6F;
            }

            /* ── Tables ────────────────────────────────────────────────────── */
            QTableWidget#DataTable {
                background: #FFFFFF;
                alternate-background-color: #F8FAFC;
                gridline-color: #E5EAEF;
                border: 1px solid #D8E4EE;
                border-radius: 8px;
                font: 500 12px 'Segoe UI';
                color: #1a1a1a;
                selection-background-color: #0078D4;
                selection-color: #FFFFFF;
            }
            QTableWidget#DataTable QHeaderView::section {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #F8FAFC, stop:1 #EBF3FB);
                border: none;
                border-right: 1px solid #E5EAEF;
                border-bottom: 2px solid #B8D4E8;
                padding: 8px 10px;
                color: #003F6F;
                font: 700 12px 'Segoe UI';
            }

            /* ── Preview ───────────────────────────────────────────────────── */
            #Preview {
                background: #1a1a1a;
                border: 1px solid #303030;
                border-radius: 8px;
                color: #B0B0B0;
                font: 500 12px 'Segoe UI';
            }
            #CounterLabel {
                color: #FFFFFF;
                font: 700 11px 'Segoe UI';
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #0078D4, stop:1 #005A9E);
                border: none;
                border-radius: 10px;
                padding: 3px 10px;
                min-width: 24px;
            }
            #FileName {
                color: #005A9E;
                font: 700 12px 'Segoe UI';
            }
            #MetaLabel {
                color: #606060;
                font: 400 11px 'Segoe UI';
            }
            #StatusText {
                color: #606060;
                font: 400 12px 'Segoe UI';
            }

            /* ── Right (thumbnail) panel ───────────────────────────────────── */
            #RightPanel {
                background: #F5F5F5;
                border-left: 1px solid #C8C8C8;
            }
            #ThumbButton {
                background: #FFFFFF;
                border: 1px solid #ABABAB;
                border-radius: 0;
                padding: 2px;
                margin: 0;
            }
            #ThumbButton:hover { border: 2px solid #0078D4; padding: 1px; }
            #ThumbButton:checked, #ThumbButton[active="true"] {
                border: 2px solid #C46500;
                background: #FFF8E0;
                padding: 1px;
            }
            #ThumbCounter {
                color: #404040;
                font: 400 11px 'Segoe UI';
                padding: 3px;
            }

            /* ── Signature frame ───────────────────────────────────────────── */
            #SigFrame {
                background: #FFF8E0;
                border: 1px solid #C46500;
                border-left: 3px solid #C46500;
                border-radius: 0;
            }
            #SigAlert {
                color: #202020;
                font: 700 13px 'Segoe UI';
                background: transparent;
                padding: 2px;
            }
            #SigStatus {
                color: #606060;
                font: 400 12px 'Segoe UI';
                background: transparent;
            }

            /* ── Status bar (v68 modern) ──────────────────────────────────── */
            QStatusBar#MainStatusBar {
                background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                    stop:0 #F8FAFC, stop:1 #EBF3FB);
                border-top: 1px solid #D8E4EE;
                color: #303030;
                font: 500 11.5px 'Segoe UI';
                padding: 2px 8px;
            }
            QStatusBar#MainStatusBar QLabel { color: #303030; }
            QStatusBar::item { border: none; }
            #SBSep {
                color: #D8E4EE;
                background: #D8E4EE;
                max-width: 1px;
                min-width: 1px;
                margin: 4px 0;
            }
            #ClockValue {
                color: #005A9E;
                font: 700 12px 'Segoe UI';
                padding: 0 10px;
            }

            /* ── Scrollbars (modern, thin, subtle) ─────────────────────────── */
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                border: none;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #C8D4DE;
                border: none;
                border-radius: 5px;
                min-height: 30px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover { background: #0078D4; }
            QScrollBar::handle:vertical:pressed { background: #005A9E; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                background: transparent; border: none; height: 0;
            }
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
                background: transparent;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 10px;
                border: none;
                margin: 0;
            }
            QScrollBar::handle:horizontal {
                background: #C8D4DE;
                border: none;
                border-radius: 5px;
                min-width: 30px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal:hover { background: #0078D4; }
            QScrollBar::handle:horizontal:pressed { background: #005A9E; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                background: transparent; border: none; width: 0;
            }
            QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {
                background: transparent;
            }

            /* ── v68 Modern Polish ─────────────────────────────────────────
               Premium card-style for the patient list, visits list, and
               other side-panel "InfoBox" containers. Goal: a clean,
               friendly look that feels modern (not retro Windows).
            */
            QFrame#InfoBox {
                background: #FFFFFF;
                border: 1px solid #D8E4EE;
                border-radius: 8px;
            }
            QLabel#BoxTitle {
                color: #003F6F;
                font: 700 13px 'Segoe UI';
                padding: 4px 4px 6px 4px;
                background: transparent;
                border: none;
            }
            QListWidget#WorkList {
                background: #FFFFFF;
                border: 1px solid #E5EAEF;
                border-radius: 6px;
                font: 400 12px 'Segoe UI';
                outline: 0;
                padding: 2px;
            }
            QListWidget#WorkList::item {
                padding: 5px 8px;
                color: #1a1a1a;
                border-radius: 4px;
                margin: 0;
            }
            QListWidget#WorkList::item:hover {
                background: #F0F6FC;
                color: #003F6F;
            }
            QListWidget#WorkList::item:selected {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #0078D4, stop:1 #005A9E);
                color: #FFFFFF;
                font-weight: 600;
            }
            QListWidget#WorkList::item:selected:hover {
                background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #005A9E, stop:1 #003F6F);
            }

            /* Quick tabs (right side bottom panel) */
            QTabWidget#QuickTabs::pane {
                background: #FFFFFF;
                border: none;
                border-top: 1px solid #E5EAEF;
            }
            QTabWidget#QuickTabs::tab-bar { left: 4px; }
            QTabWidget#QuickTabs QTabBar::tab {
                background: transparent;
                color: #707888;
                border: none;
                border-bottom: 2px solid transparent;
                padding: 6px 12px 4px 12px;
                margin-right: 2px;
                font: 600 11px 'Segoe UI';
                min-width: 60px;
            }
            QTabWidget#QuickTabs QTabBar::tab:hover {
                color: #003F6F;
                border-bottom: 2px solid #B8D4E8;
            }
            QTabWidget#QuickTabs QTabBar::tab:selected {
                color: #003F6F;
                font: 700 11px 'Segoe UI';
                border-bottom: 2px solid #0078D4;
            }
        """)

    def _build_pdf_header_html(self) -> str:
        """Build the header HTML used on the cover page (patient info).
        Pulls name, age, EDD, GA from the latest summary PDF if available."""
        if not self.current_patient:
            return "<b>Hasta seçilmedi</b>"
        name = format_patient_name(self.current_patient.name)
        # Try to extract more info from latest PDF
        ga_text = ""
        edd_text = ""
        try:
            if self.current_subfolder:
                pdf = get_latest_pdf_in_folder(self.current_subfolder)
                if pdf:
                    data = parse_pdf_summary_data(pdf)
                    ga_text = best_ga_text_from_data(data) or ""
                    edd = data.get("edd") or ""
                    if isinstance(edd, str):
                        edd_text = edd
        except Exception as _ex:
            _log_warning("MainWindow._build_pdf_header_html", exc=_ex)
        date_str = datetime.now().strftime("%d.%m.%Y")
        parts = [f"<b>HASTA:</b> {name}"]
        if ga_text:
            parts.append(f"<b>GA:</b> {ga_text}")
        if edd_text:
            parts.append(f"<b>EDD:</b> {edd_text}")
        parts.append(f"<b>Tarih:</b> {date_str}")
        return "  ·  ".join(parts) + f"<br><b>{get_clinic_doctor_name()}</b>"
