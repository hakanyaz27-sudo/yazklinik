"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _WhatsAppMixin
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

class _WhatsAppMixin:
    """MainWindow methods related to WhatsApp. Mixed into MainWindow via MRO."""

    def _build_copy_text(self) -> str:
        base = (self.last_summary_plain or self.summary_text.toPlainText()).strip()
        note = self.note_edit.toPlainText().strip()
        if note:
            return base + "\n\n--- Hekim Notu ---\n" + note
        return base

    def _schedule_whatsapp_auto_paste(self, app_label: str,
                                      file_count: int,
                                      is_zip: bool = False) -> None:
        """Schedule auto-paste on the MAIN Qt thread (not a worker).

        Why main-thread: Windows' EnumWindows API only works from a
        thread that has a GUI message queue. Our _run_bg workers don't
        have one, so EnumWindows silently returns nothing — which is
        exactly what we saw in the error log ("Visible windows: []").

        Solution: use QTimer.singleShot to chain polls on the GUI
        thread. Each poll runs a short _find_whatsapp_window() call
        and, if not found, schedules another poll 500ms later. Once
        found, focuses and sends Ctrl+V. The UI doesn't freeze because
        each step is very short and returns control to the event loop
        between polls.

        v68-UI: `is_zip` controls the post-paste Enter delay. A single
        ZIP is ready almost instantly (~600ms), while multi-file paste
        (20 images + videos) needs ~2.5s for WhatsApp to build preview
        thumbnails.
        """
        # Initial status
        self.statusBar().showMessage(
            f"⚡ {app_label} açılıyor, {file_count} dosya panoda. "
            "Otomatik yapıştırılacak...", 4000)

        INITIAL_DELAY_MS = 1800   # wait for WA to open the chat
        POLL_INTERVAL_MS = 500
        MAX_POLLS = 20            # 20 × 500ms = 10s total budget
        state = {"polls": 0}

        def _attempt_paste():
            state["polls"] += 1
            # Search for the WhatsApp window — now running on MAIN Qt
            # thread where EnumWindows actually works.
            hwnd = _find_whatsapp_window()
            if not hwnd:
                if state["polls"] < MAX_POLLS:
                    # Try again later
                    QTimer.singleShot(POLL_INTERVAL_MS, _attempt_paste)
                else:
                    # Gave up — ask user to paste manually
                    _log_warning(
                        f"_schedule_whatsapp_auto_paste: no window "
                        f"after {state['polls']} polls, user must "
                        f"paste manually")
                    self.statusBar().showMessage(
                        f"⚡ {app_label} — {file_count} dosya panoda "
                        "(pencere bulunamadı). Ctrl+V ile yapıştırın.",
                        8000)
                return

            # Found it — focus and paste
            _log_warning(
                f"_schedule_whatsapp_auto_paste: found hwnd={hwnd} "
                f"after {state['polls']} poll(s)")
            focus_ok = _focus_hwnd(hwnd)
            _log_warning(
                f"_schedule_whatsapp_auto_paste: focus result={focus_ok}")

            # Give the message input a beat to receive focus
            def _do_paste():
                VK_CONTROL = 0x11
                VK_V = 0x56
                keys = [
                    (VK_CONTROL, True),
                    (VK_V, True),
                    (VK_V, False),
                    (VK_CONTROL, False),
                ]
                sent = False
                # Try SendInput (VK) first
                try:
                    sent = _send_keys_sendinput(keys)
                    _log_warning(
                        f"_schedule_whatsapp_auto_paste: "
                        f"SendInput(VK)={sent}")
                except Exception as _ex:
                    _log_warning(
                        "_schedule_whatsapp_auto_paste SendInput(VK)",
                        exc=_ex)
                # Fallback: scancode
                if not sent:
                    try:
                        sent = _send_keys_scancode(keys)
                        _log_warning(
                            f"_schedule_whatsapp_auto_paste: "
                            f"SendInput(scan)={sent}")
                    except Exception as _ex:
                        _log_warning(
                            "_schedule_whatsapp_auto_paste scancode",
                            exc=_ex)
                # Final fallback: legacy keybd_event
                if not sent:
                    try:
                        _press_vk(VK_CONTROL, True)
                        time.sleep(0.03)
                        _press_vk(VK_V, True)
                        time.sleep(0.03)
                        _press_vk(VK_V, False)
                        _press_vk(VK_CONTROL, False)
                        sent = True
                        _log_warning(
                            "_schedule_whatsapp_auto_paste: "
                            "keybd_event completed")
                    except Exception as _ex:
                        _log_warning(
                            "_schedule_whatsapp_auto_paste keybd_event",
                            exc=_ex)

                if sent:
                    # v68-UI: Auto-send Enter after paste. Delay depends
                    # on clipboard content:
                    #   - ZIP (1 file): ~600ms — WhatsApp picks it up
                    #     instantly as a document attachment
                    #   - Multi-file: 2500ms — needs time to build
                    #     preview thumbnails for each image/video
                    if get_whatsapp_auto_send():
                        enter_delay_ms = 600 if is_zip else 2500
                        self.statusBar().showMessage(
                            f"✓ {app_label} — {file_count} dosya "
                            "yapıştırıldı. Gönderiliyor...",
                            4000)
                        show_toast(self,
                                   f"{app_label}: {file_count} dosya gönderiliyor...",
                                   level="success", duration_ms=3000)
                        QTimer.singleShot(enter_delay_ms, _do_press_enter)
                    else:
                        self.statusBar().showMessage(
                            f"✓ {app_label} — {file_count} dosya otomatik "
                            "yapıştırıldı. Göndermek için Enter'a basın.",
                            8000)
                        show_toast(self,
                                   f"{app_label}: {file_count} dosya yapıştırıldı — Enter'a basın",
                                   level="info", duration_ms=5000)
                else:
                    self.statusBar().showMessage(
                        f"⚡ {app_label} — {file_count} dosya panoda "
                        "(tuş gönderimi başarısız). "
                        "Ctrl+V ile yapıştırın.", 8000)

            def _do_press_enter():
                """Send Enter key to the WhatsApp window to fire the
                queued message. Re-focuses the window first in case
                the user clicked elsewhere during the upload wait."""
                # Re-find + re-focus — the user may have alt-tabbed
                hwnd2 = _find_whatsapp_window()
                if hwnd2:
                    try:
                        _focus_hwnd(hwnd2)
                    except Exception as _ex:
                        _log_warning("_do_press_enter: focus", exc=_ex)
                    # Brief pause so focus lands before we key
                    time.sleep(0.15)
                VK_RETURN = 0x0D
                enter_keys = [(VK_RETURN, True), (VK_RETURN, False)]
                sent_enter = False
                try:
                    sent_enter = _send_keys_sendinput(enter_keys)
                    _log_warning(
                        f"_do_press_enter: SendInput(VK)={sent_enter}")
                except Exception as _ex:
                    _log_warning(
                        "_do_press_enter SendInput(VK)", exc=_ex)
                if not sent_enter:
                    try:
                        sent_enter = _send_keys_scancode(enter_keys)
                        _log_warning(
                            f"_do_press_enter: SendInput(scan)="
                            f"{sent_enter}")
                    except Exception as _ex:
                        _log_warning(
                            "_do_press_enter scancode", exc=_ex)
                if not sent_enter:
                    try:
                        _press_vk(VK_RETURN, True)
                        time.sleep(0.03)
                        _press_vk(VK_RETURN, False)
                        sent_enter = True
                    except Exception as _ex:
                        _log_warning(
                            "_do_press_enter keybd_event", exc=_ex)

                if sent_enter:
                    self.statusBar().showMessage(
                        f"✅ {app_label} — {file_count} dosya "
                        "gönderildi (otomatik).", 6000)
                else:
                    self.statusBar().showMessage(
                        f"⚠ {app_label} — dosyalar yapıştırıldı ama "
                        "Enter gönderilemedi. Manuel tıklayın.",
                        8000)

            # 500ms after focus — let WhatsApp's message input grab
            # focus inside the window
            QTimer.singleShot(500, _do_paste)

        # Start the polling chain after initial delay
        QTimer.singleShot(INITIAL_DELAY_MS, _attempt_paste)

    def prepare_whatsapp(self):
        """Şablonla WhatsApp mesajı hazırla.

        Template seçer, hastanın WhatsApp numarasını bulur, ilgili
        mesajı panoya kopyalar (text olarak), WhatsApp Web'i açar.

        'summary' şablonu SEÇİLİRSE: özet mesajı VE dosyalar ikisini de
        ister. Clipboard tek tip içerik alabilir, yani öncelik dosyalarda
        (WhatsApp'ta dosya göndermek asıl amaç); özet mesajı kullanıcıya
        ayrıca gösterilir (InputDialog) ki manuel kopyalayabilsin.

        v68 YENİ: Explorer penceresi AÇILMAZ — dosyalar doğrudan
        Qt clipboard API ile kopyalanır.
        """
        if not self.current_subfolder:
            QMessageBox.warning(self, "Uyarı", "Geliş seçilmedi."); return
        # Ask which template the user wants to use
        template_choice = self._choose_whatsapp_template()
        if template_choice is None:
            return  # User cancelled
        number = normalize_phone(self.phone_input.text())
        self.phone_input.setText(number); self.stat_wa.set_value(number)
        key = self.active_patient_key()
        if key:
            save_phone_db(key, number); self.update_phone_badges(is_saved=True)

        # Build the message based on the chosen template
        if template_choice == "summary":
            message = self._build_copy_text()
        else:
            message = self._build_whatsapp_template_message(template_choice)

        _url, method = open_whatsapp(number, prefer_desktop=True)
        # Friendly label for the status bar based on what opened
        app_label = "WhatsApp Desktop" if method.startswith("desktop") \
                    else "WhatsApp Web"

        if template_choice == "summary":
            # Summary mode wants BOTH the message and the files. Since
            # clipboard holds only one type at a time, prioritize files
            # (the main WhatsApp-send intent). Auto-paste the files if
            # Desktop is in use (Web can't receive SendInput reliably).
            copied, file_count = copy_folder_files_to_clipboard(
                self.current_subfolder)
            if copied and method.startswith("desktop"):
                # Schedule auto-paste on the MAIN Qt thread — EnumWindows
                # only works from a thread with a GUI message queue.
                self._schedule_whatsapp_auto_paste(app_label, file_count)
            elif copied:
                self.statusBar().showMessage(
                    f"✓ {app_label} açıldı, {file_count} dosya panoda. "
                    "Ctrl+V ile yapıştırın.", 8000)
            else:
                # No files — fall back to message-only
                if message:
                    safe_copy_to_clipboard(message)
                self.statusBar().showMessage(
                    f"✓ {app_label} açıldı, özet metni panoda. "
                    "Ctrl+V ile yapıştırın.", 6000)
        else:
            # Message-only templates (appointment/results/birthday/etc)
            if message:
                safe_copy_to_clipboard(message)
            self.statusBar().showMessage(
                f"✓ {app_label} açıldı, mesaj panoya kopyalandı — "
                "Ctrl+V ile yapıştırın", 6000)

    def prepare_whatsapp_quick(self):
        """Hızlı WhatsApp — tek tıkla: geliş klasöründeki TÜM dosyaları
        (resim + video + PDF) panoya kopyala, hastanın WhatsApp numarasına
        WhatsApp Desktop app'ini (varsa) ya da Web'ini aç.

        v68 YENİ:
          - Explorer penceresi AÇILMAZ — dosyalar doğrudan Qt clipboard
            API ile kopyalanır. Daha hızlı, daha az göze batan, pencere
            odak kaybı yok.
          - WhatsApp Desktop kuruluysa whatsapp:// protocol'u ile
            direkt açılır. Kurulu değilse tarayıcıda WhatsApp Web açılır.
          - Desktop açılınca dosyalar OTOMATİK yapıştırılır (Ctrl+V
            arka planda gönderilir, ~2 saniye sonra). Web modunda
            manuel Ctrl+V gerekir (tarayıcı odağı güvenilir değil).

        Şablon seçici / mesaj oluşturma ATLANIR — sadece dosya transferi.
        İdeal senaryo: muayeneden çıkan hastaya USG görüntü+video+raporunu
        WhatsApp'tan gönderirken.
        """
        if not self.current_subfolder:
            QMessageBox.warning(self, "Uyarı", "Geliş seçilmedi."); return
        number = normalize_phone(self.phone_input.text())
        self.phone_input.setText(number)
        self.stat_wa.set_value(number)
        key = self.active_patient_key()
        if key:
            save_phone_db(key, number)
            self.update_phone_badges(is_saved=True)

        # Silent clipboard copy — no Explorer window, no keyboard tricks
        # v68-UI: Respect the WhatsApp ZIP mode setting. When enabled,
        # build a single <HastaAdı>.zip of the visit folder and copy
        # ONLY that zip to clipboard. Patient gets one download, not 20.
        zip_mode = get_whatsapp_zip_mode()
        zip_used = False
        zip_path_ref: Optional[Path] = None
        if zip_mode and self.current_patient:
            pname = format_patient_name(self.current_patient.name)
            vname = self.current_subfolder.name \
                if self.current_subfolder else None
            copied, inner_cnt, zip_path_ref = copy_zip_to_clipboard(
                self.current_subfolder, pname, vname)
            if copied:
                zip_used = True
                file_count = 1  # one zip file in clipboard
                inner_file_count = inner_cnt
            else:
                # ZIP creation failed — silently fall back to old path
                _log_warning(
                    "prepare_whatsapp_quick: zip failed, using legacy copy")
                copied, file_count = copy_folder_files_to_clipboard(
                    self.current_subfolder)
                inner_file_count = file_count
        else:
            copied, file_count = copy_folder_files_to_clipboard(
                self.current_subfolder)
            inner_file_count = file_count

        # Open WhatsApp — Desktop app if installed, Web otherwise
        _url, method = open_whatsapp(number, prefer_desktop=True)
        app_label = "WhatsApp Desktop" if method.startswith("desktop") \
                    else "WhatsApp Web"

        # Auto-paste: only for Desktop (browser focus is unreliable via
        # SendInput). Must run on the Qt MAIN THREAD — Windows' EnumWindows
        # API returns nothing when called from a worker thread without a
        # GUI message queue. We use QTimer.singleShot to schedule polls
        # and the final paste, all on the main thread.
        auto_paste = (copied and method.startswith("desktop"))
        if auto_paste:
            self._schedule_whatsapp_auto_paste(
                app_label, file_count, is_zip=zip_used)
            if zip_used and zip_path_ref:
                self.statusBar().showMessage(
                    f"📦 {app_label} — {zip_path_ref.name} "
                    f"({inner_file_count} dosya) panoda, yapıştırılıyor...",
                    6000)
        elif copied:
            # Web mode OR desktop with no files — user pastes manually
            if zip_used and zip_path_ref:
                self.statusBar().showMessage(
                    f"📦 {app_label} — {zip_path_ref.name} "
                    f"({inner_file_count} dosya tek ZIP'te) panoda. "
                    "Ctrl+V ile yapıştırın.",
                    8000)
            else:
                self.statusBar().showMessage(
                    f"⚡ {app_label} — {file_count} dosya panoda. "
                    "Ctrl+V ile yapıştırın.",
                    8000)
        else:
            self.statusBar().showMessage(
                "⚠ WhatsApp açıldı ama dosyalar kopyalanamadı "
                "(klasör boş veya erişilemiyor). "
                "Geliş klasörünü manuel açın.", 6000)

    def _choose_whatsapp_template(self) -> Optional[str]:
        """Show a compact template picker dialog.
        Returns one of: 'summary', 'appointment', 'results', 'test_reminder',
        'birthday', 'custom', or None if cancelled."""
        dlg = ClickOutsideDialog(self)
        dlg.setWindowTitle("WhatsApp Mesajı Türü")
        dlg.resize(420, 380)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(6)

        lbl = QLabel("<h3 style='margin:0;color:#005A9E'>Hangi mesaj türü?</h3>")
        lbl.setTextFormat(Qt.RichText)
        lay.addWidget(lbl)

        choice = {"value": None}

        def _make_btn(text: str, desc: str, value: str):
            b = QPushButton()
            b.setText(f"<h4 style='margin:0;text-align:left'>{text}</h4>"
                      f"<span style='color:#606060;font-size:10px;'>{desc}</span>")
            # QPushButton doesn't render HTML natively for the text(), so use
            # a plain format instead
            b.setText(f"{text}\n   {desc}")
            b.setStyleSheet(
                "QPushButton{text-align:left;padding:10px 14px;"
                "background:#F8F8F8;border:1px solid #C8C8C8;"
                "font:500 12px 'Segoe UI';border-radius:4px;}"
                "QPushButton:hover{background:#E5EEF7;border-color:#0078D4;}")
            b.setMinimumHeight(50)
            def _pick():
                choice["value"] = value
                dlg.accept()
            b.clicked.connect(_pick)
            lay.addWidget(b)

        _make_btn("📊 USG Rapor Özeti",
                  "Bu gelişin özeti + dosyalar (standart)", "summary")
        _make_btn("📅 Randevu Hatırlatma",
                  "Bir sonraki kontrol için hatırlatma", "appointment")
        _make_btn("✉️ Sonuç / Test Bilgilendirme",
                  "Tahlil / test sonuçları için", "results")
        _make_btn("🔬 Önerilen Test Bilgilendirme",
                  "GA'ya göre önerilen testler (NT, OGTT, vb.)", "test_reminder")
        _make_btn("🎉 Doğum Günü",
                  "Hastaya doğum günü mesajı", "birthday")

        cancel = QPushButton("İptal")
        cancel.setShortcut("Escape")
        cancel.clicked.connect(dlg.reject)
        lay.addWidget(cancel)

        dlg.exec()
        return choice["value"]

    def _build_whatsapp_template_message(self, template: str) -> str:
        """Generate a pre-filled message for the given template key.
        Uses patient name and, where applicable, GA/EDD information.

        If the patient has a birth outcome flag set, we know the pregnancy
        is closed — in that case the GA-specific `test_reminder` template
        would produce misleading output (e.g. suggesting GBS culture for a
        patient who delivered weeks ago), so we swap in a postpartum
        alternative. Other templates (appointment / results / birthday)
        remain valid for delivered patients.
        """
        pname = format_patient_name(self.current_patient.name) \
            if self.current_patient else "Sayın hastamız"
        first_name = pname.split()[0].title() if pname else "Sayın hastamız"

        # Detect closed pregnancy up front — we'll use this to decide which
        # template variant to emit.
        is_delivered = False
        if self.current_patient:
            try:
                is_delivered = is_pregnancy_closed(self.current_patient.name)
            except Exception as _ex:
                _log_warning(
                    "MainWindow._build_whatsapp_template_message:"
                    " flag check failed", exc=_ex)

        # Get GA for context-aware templates
        ga_weeks = None
        if self.current_subfolder:
            try:
                pdf = get_latest_pdf_in_folder(self.current_subfolder)
                if pdf:
                    data = parse_pdf_summary_data(pdf)
                    ga_days = data.get("ga_days")
                    if isinstance(ga_days, (int, float)) and ga_days > 0:
                        ga_weeks = int(ga_days) // 7
            except Exception as _ex:
                _log_warning("MainWindow._build_whatsapp_template_message", exc=_ex)

        if template == "appointment":
            return (
                f"Merhaba {first_name} Hanım,\n\n"
                f"Kontrol randevunuz için bilgilendirme:\n"
                f"📅 Tarih: [tarih giriniz]\n"
                f"🕐 Saat: [saat giriniz]\n\n"
                f"Randevuya gelirken lütfen önceki muayene sonuçlarınızı "
                f"yanınızda getiriniz.\n\n"
                f"Sağlıklı günler dilerim.\n"
                f"{get_clinic_doctor_name()}")

        elif template == "results":
            return (
                f"Merhaba {first_name} Hanım,\n\n"
                f"Tahlil/test sonuçlarınız hakkında bilgilendirme:\n\n"
                f"[sonuç detayları buraya]\n\n"
                f"Herhangi bir sorunuz olursa beni arayabilirsiniz.\n\n"
                f"Sağlıklı günler,\n"
                f"{get_clinic_doctor_name()}")

        elif template == "test_reminder":
            # For delivered patients this template doesn't apply — they
            # don't need NT / OGTT / GBS etc. Emit a postpartum follow-up
            # reminder so the doctor doesn't accidentally send a GBS-
            # culture reminder to someone who delivered a month ago.
            if is_delivered:
                return (
                    f"Merhaba {first_name} Hanım,\n\n"
                    f"Doğum sonrası kontrolünüz için hatırlatma:\n\n"
                    f"📅 Tarih: [tarih giriniz]\n"
                    f"🕐 Saat: [saat giriniz]\n\n"
                    f"Kontrol sırasında bakılacaklar:\n"
                    f"• Genel muayene ve iyileşme kontrolü\n"
                    f"• Tansiyon takibi\n"
                    f"• Sütyeme ve beslenme danışmanlığı\n"
                    f"• Aile planlaması / doğum kontrol yöntemleri\n\n"
                    f"Herhangi bir sorununuz olursa beni arayabilirsiniz.\n\n"
                    f"Sağlıklı günler,\n"
                    f"{get_clinic_doctor_name()}")
            # GA-specific test recommendations
            tests = ""
            if ga_weeks is None:
                tests = "[yapılacak test: NT/OGTT/detaylı USG vb.]"
            elif 11 <= ga_weeks <= 14:
                tests = "• 1. trimester taraması (NT + PAPP-A + fβhCG)"
            elif 15 <= ga_weeks <= 20:
                tests = "• İkili/üçlü test VEYA NIPT"
            elif 18 <= ga_weeks <= 23:
                tests = "• Detaylı anomali taraması (20. hafta USG)"
            elif 24 <= ga_weeks <= 28:
                tests = "• OGTT (Gestasyonel diyabet taraması - 75g şeker yükleme)"
            elif 28 <= ga_weeks <= 32:
                tests = "• Tam kan kontrolü + idrar tahlili"
            elif 35 <= ga_weeks <= 37:
                tests = "• Term öncesi rutin kontrol (muayene + USG)"
            else:
                tests = "[yapılacak test]"
            ga_str = f" ({ga_weeks}. haftada bulunuyorsunuz)" if ga_weeks else ""
            return (
                f"Merhaba {first_name} Hanım,\n\n"
                f"Gebelik takibinizle ilgili hatırlatma{ga_str}:\n\n"
                f"Önerilen test(ler):\n{tests}\n\n"
                f"Test için uygun olduğunuzda randevu almak üzere beni "
                f"arayabilirsiniz.\n\n"
                f"Sağlıklı günler,\n"
                f"{get_clinic_doctor_name()}")

        elif template == "birthday":
            return (
                f"Sevgili {first_name} Hanım,\n\n"
                f"Doğum gününüz kutlu olsun! 🎉🎂\n\n"
                f"Yeni yaşınızın sağlık, mutluluk ve güzelliklerle "
                f"dolu olmasını dilerim.\n\n"
                f"Saygılarımla,\n"
                f"{get_clinic_doctor_name()}")

        return ""
