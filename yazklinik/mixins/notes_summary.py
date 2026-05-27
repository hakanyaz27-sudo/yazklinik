"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _NotesSummaryMixin
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

class _NotesSummaryMixin:
    """MainWindow methods related to NotesSummary. Mixed into MainWindow via MRO."""

    def _on_summary_phone_changed(self, _: str):
        """Summary-tab phone changed → sync to notes-tab input + badges.
        Auto-save happens on editingFinished (focus leaves) — see connection."""
        if hasattr(self, "phone_input"):
            if self.phone_input.text() != self.phone_input_summary.text():
                self.phone_input.blockSignals(True)
                self.phone_input.setText(self.phone_input_summary.text())
                self.phone_input.blockSignals(False)
        self.update_phone_badges()

    def _on_note_changed(self):
        if hasattr(self, "note_save_lbl"):
            self.note_save_lbl.hide()
        if hasattr(self, "notes_visit_save_lbl"):
            self.notes_visit_save_lbl.hide()
        self._note_save_timer.start(1500)

    def _auto_save_note(self):
        """Auto-save the note to the visit currently shown in the Notes tab.
        Falls back to the main current visit if no specific notes-tab visit
        is selected (e.g. on app startup)."""
        pkey = self.active_patient_key()
        if not pkey:
            return
        # Prefer the visit selected in the Notes-tab list; fall back otherwise
        vkey = None
        notes_path = getattr(self, "_notes_current_visit_path", None)
        if notes_path is not None:
            vkey = notes_path.name
        if not vkey:
            vkey = self.active_visit_key()
        if not vkey:
            return
        note = self.note_edit.toPlainText()
        save_visit_note(pkey, vkey, note)
        # v68-AI: Feed saved note to SmartTextEngine for phrase learning
        # so frequently-used sentences get auto-suggested next time
        try:
            if note and len(note.strip()) >= 8:
                SmartTextEngine.learn_text(note)
        except Exception as _ex:
            _log_warning(f"learn_text from note: {_ex}")
        if hasattr(self, "note_save_lbl"):
            self.note_save_lbl.setText("✓ Kaydedildi")
            self.note_save_lbl.show()
        if hasattr(self, "notes_visit_save_lbl"):
            self.notes_visit_save_lbl.show()

    def _load_note(self):
        pkey = self.active_patient_key()
        vkey = self.active_visit_key()
        note = load_visit_note(pkey, vkey) if pkey and vkey else ""
        self.note_edit.blockSignals(True)
        self.note_edit.setPlainText(note)
        self.note_edit.blockSignals(False)
        if hasattr(self, "note_save_lbl"):
            self.note_save_lbl.hide()
        # Also refresh the historical visits list in the Notes tab
        self._populate_notes_visits_list()

    def _on_notes_visits_list_changed(self, current, _previous):
        """A visit was selected in the Notes-tab list — load its summary
        + note into the right pane."""
        if current is None:
            return
        data = current.data(Qt.UserRole)
        if not data or data[0] != "visit":
            return
        vpath = Path(data[1])
        self._notes_current_visit_path = vpath
        self._load_notes_summary_for_visit(vpath)
        self._load_notes_note_for_visit(vpath)

    def _load_notes_summary_for_visit(self, vpath: Path):
        """Render the PDF summary for a specific visit into the notes summary box."""
        if not hasattr(self, "notes_summary_text"):
            return
        try:
            pdf = get_latest_pdf_in_folder(vpath)
        except Exception:
            pdf = None
        if not pdf:
            self.notes_summary_text.setHtml(
                f"<i style='color:#909090;'>Bu gelişte PDF bulunamadı: {vpath.name}</i>")
            return
        try:
            html = build_pdf_summary(pdf)
            visit_label = format_visit_name(vpath.name)
            header_html = (
                f"<div style='background:#F0F4FA;border:1px solid #6A8CB5;"
                f"padding:5px 10px;color:#003366;margin-bottom:6px;'>"
                f"<b>Geliş:</b> {visit_label}</div>"
            )
            self.notes_summary_text.setHtml(header_html + html)
        except Exception as e:
            self.notes_summary_text.setPlainText(
                f"PDF özeti alınamadı:\n{e}")

    def _load_notes_note_for_visit(self, vpath: Path):
        """Load the doctor's note for this visit into the editor."""
        if not hasattr(self, "note_edit"):
            return
        pkey = self.active_patient_key()
        vkey = vpath.name
        note = load_visit_note(pkey, vkey) if pkey else ""
        self.note_edit.blockSignals(True)
        self.note_edit.setPlainText(note or "")
        self.note_edit.blockSignals(False)
        if hasattr(self, "notes_visit_save_lbl"):
            self.notes_visit_save_lbl.hide()

    def _clear_note_ui(self):
        self.note_edit.blockSignals(True)
        self.note_edit.clear()
        self.note_edit.blockSignals(False)
        self.note_save_lbl.hide()

    def load_summary(self):
        if not self.current_subfolder:
            return
        visit_label = format_visit_name(self.current_subfolder.name)
        pdf = get_latest_pdf_in_folder(self.current_subfolder)
        if not pdf:
            self.last_summary_plain = f"GELİŞ: {visit_label}\n\nBu gelişte PDF bulunamadı."
            self.summary_text.setPlainText(self.last_summary_plain)
            self.twin_badge.hide(); return

        # Show a quick "loading" message so the user sees feedback immediately
        # rather than staring at the previous patient's data. The parse below
        # is fast due to the cache, but the very first visit of a PDF still
        # takes ~100-300ms.
        self.summary_text.setPlainText(f"GELİŞ: {visit_label}\n\nYükleniyor...")
        QApplication.processEvents()

        try:
            data = parse_pdf_summary_data(pdf)
            is_twin = data.get("is_twin", False)
            self.twin_badge.setVisible(is_twin)
            self.last_summary_plain = f"GELİŞ: {visit_label}\n\n" + build_pdf_summary_plain(pdf)
            # Use the original HTML summary builder, but wrap with a light header for classic look
            visit_html = (
                f'<div style="font-family:Segoe UI;margin-bottom:6px;">'
                f'<div style="background:#F0F4FA;border:1px solid #6A8CB5;'
                f'padding:5px 10px;display:inline-block;color:#003366;">'
                f'<b>Geliş Tarih / Saat:</b> {visit_label}'
                f'{" &nbsp; <span style=color:#C97700;font-weight:700>(İKİZ GEBELİK)</span>" if is_twin else ""}'
                f'</div></div>'
            )
            self.summary_text.setHtml(visit_html + build_pdf_summary(pdf))

            save_visit_summary(
                self.active_patient_key(),
                self.current_subfolder.name,
                visit_label,
                self.last_summary_plain,
                is_twin,
                str(pdf),
            )
        except Exception as e:
            self.last_summary_plain = f"GELİŞ: {visit_label}\n\nPDF özeti alınamadı.\n{e}"
            self.summary_text.setPlainText(self.last_summary_plain)
            self.twin_badge.hide()

    def copy_summary(self):
        txt = self._build_copy_text()
        if not txt:
            QMessageBox.warning(self, "Uyarı", "Kopyalanacak özet yok."); return
        copied, err = safe_copy_to_clipboard(txt)
        if copied:
            self.statusBar().showMessage(
                "✓ Özet (ve hekim notu varsa) panoya kopyalandı", 4000)
        else:
            QMessageBox.warning(self, "Bilgi", f"Kopyalanamadı.\n{err}")

    def build_patient_long_summary(self) -> str:
        """Build a comprehensive plaintext summary of the active patient.

        Includes everything we know that the doctor would want when handing
        the case off / referring / dictating to a notebook:
          • Header with name + key obstetric dates (LMP, EDD, PDD, current GA)
          • Demographics (blood/Rh, GPAL, allergies, chronic conditions,
            ongoing medications)
          • Active risk flags grouped by severity, with the doctor's notes
            attached to each flag
          • Latest visit's PDF summary + the doctor's note for that visit

        Returns a multi-line string ready to drop into clipboard / WhatsApp /
        consult letter. Returns "" if no patient is active.
        """
        if not self.current_patient:
            return ""

        patient_key = self.active_patient_key() or ""
        lines: List[str] = []

        # ── Header ──────────────────────────────────────────────────────
        name = format_patient_name(patient_key) if patient_key \
            else self.current_patient.name
        lines.append("═" * 60)
        lines.append(f"HASTA ÖZETİ — {name}")
        lines.append("═" * 60)

        # ── Check birth outcome first — if pregnancy is closed, we
        # show the outcome prominently instead of GA/EDD/planned C/S.
        # Matches the banner's behaviour so the summary is consistent
        # with what the doctor sees on screen.
        patient_flags_raw = {}
        try:
            patient_flags_raw = get_patient_flags(patient_key)
        except Exception as _ex:
            _log_warning("MainWindow.build_patient_long_summary", exc=_ex)

        birth_outcome_key: Optional[str] = None
        birth_outcome_notes: str = ""
        for _bo_key in _BIRTH_OUTCOME_FLAG_KEYS:
            _d = patient_flags_raw.get(_bo_key) if patient_flags_raw else None
            if _d and (_d.get("value") or "") == "1":
                birth_outcome_key = _bo_key
                birth_outcome_notes = (_d.get("notes") or "").strip()
                break

        if birth_outcome_key:
            # Pregnancy has been closed out. Show the outcome.
            if birth_outcome_key == "dogum_sezaryan":
                lines.append("  🎉 SEZARYEN İLE DOĞUM YAPILDI")
            else:
                lines.append("  🎉 DOĞUM YAPILDI (normal vajinal)")
            if birth_outcome_notes:
                for ln in birth_outcome_notes.splitlines():
                    lines.append(f"     {ln}")

        # LMP / EDD / PDD / current GA — only meaningful while pregnancy
        # is ongoing. If the patient has delivered, skip this whole block.
        if not birth_outcome_key:
            try:
                lmp = get_best_lmp_for_patient(self.current_patient)
            except Exception:
                lmp = None
            edd_str = ""
            edd_dt = None
            try:
                target = self.current_subfolder
                if target:
                    p = get_latest_pdf_in_folder(target)
                    if p:
                        d = parse_pdf_summary_data(p)
                        edd_str = d.get("edd") or ""
                        edd_dt = d.get("edd_dt")
                # Fallback: scan all visits
                if edd_dt is None:
                    for v in get_subfolders(self.current_patient):
                        p = get_latest_pdf_in_folder(v)
                        if not p:
                            continue
                        d = parse_pdf_summary_data(p)
                        if d.get("edd_dt"):
                            edd_str = d.get("edd") or ""
                            edd_dt = d.get("edd_dt")
                            break
            except Exception as _ex:
                _log_warning("MainWindow.build_patient_long_summary", exc=_ex)

            if lmp:
                lines.append(f"  Son adet (LMP): {lmp}")
            if edd_str:
                line = f"  Tahmini doğum (EDD): {edd_str}"
                if isinstance(edd_dt, datetime):
                    today = datetime.now().date()
                    # Current GA from EDD
                    cur_ga_days = 280 - (edd_dt.date() - today).days
                    if 0 < cur_ga_days <= 300:
                        w, dd = divmod(cur_ga_days, 7)
                        line += f"   ·   Bugünkü GA: {w}+{dd} hafta"
                lines.append(line)

            # Planned delivery date if C-section flagged
            is_cs = is_c_section_planned(patient_key)
            if is_cs and isinstance(edd_dt, datetime):
                pdd = planned_delivery_date(patient_key, edd_dt)
                if pdd is not None:
                    pdd_str = pdd.strftime("%d.%m.%Y")
                    days_to_pdd = (pdd.date() - datetime.now().date()).days
                    tail = f"({days_to_pdd} gün kaldı)" if days_to_pdd > 0 \
                        else ("(BUGÜN)" if days_to_pdd == 0
                              else f"({-days_to_pdd} gün geçti)")
                    lines.append(
                        f"  🩺 Planlı sezaryen tarihi: {pdd_str}  {tail}")

        # Last visit date
        try:
            last_d = get_patient_last_visit_date(self.current_patient)
            if last_d:
                days_ago = (datetime.now().date() - last_d.date()).days
                if days_ago == 0:
                    ago = "bugün"
                elif days_ago == 1:
                    ago = "dün"
                else:
                    ago = f"{days_ago} gün önce"
                lines.append(
                    f"  Son geliş: {last_d.strftime('%d.%m.%Y')}  ({ago})")
        except Exception as _ex:
            _log_warning("MainWindow.build_patient_long_summary", exc=_ex)

        # ── Demographics ────────────────────────────────────────────────
        demo = {}
        try:
            demo = load_patient_demographics(patient_key)
        except Exception as _ex:
            _log_warning("MainWindow.build_patient_long_summary", exc=_ex)

        if demo:
            demo_lines: List[str] = []
            # Blood + Rh
            bt = demo.get("blood_type") or ""
            rh = demo.get("rh_factor") or ""
            partner_rh = demo.get("partner_rh") or ""
            if bt or rh:
                rh_sign = {"positive": "+", "negative": "-",
                           "+": "+", "-": "-"}.get(rh, "")
                blood = f"{bt}{rh_sign}".strip() or "?"
                line = f"  Kan grubu: {blood}"
                if partner_rh:
                    p_sign = {"positive": "+", "negative": "-",
                              "+": "+", "-": "-"}.get(partner_rh, partner_rh)
                    line += f"   ·   Eş Rh: {p_sign}"
                    # Rh incompatibility flag
                    if rh == "negative" and partner_rh == "positive":
                        line += "   ⚠ Rh uyuşmazlığı"
                demo_lines.append(line)

            # G/P/A/L
            g = demo.get("gravida"); pa = demo.get("para")
            ab = demo.get("abortus"); lv = demo.get("living")
            if any(x is not None for x in (g, pa, ab, lv)):
                demo_lines.append(
                    f"  Obstetrik öykü: G{g if g is not None else '?'}"
                    f"P{pa if pa is not None else '?'}"
                    f"A{ab if ab is not None else '?'}"
                    f"L{lv if lv is not None else '?'}")

            # Chronic conditions
            chronic = (demo.get("chronic_conditions") or "").strip()
            if chronic:
                demo_lines.append(f"  Kronik hastalıklar: {chronic}")

            # Medications (regular ongoing meds, not pregnancy-specific)
            meds = (demo.get("medications") or "").strip()
            if meds:
                demo_lines.append(f"  Düzenli kullandığı ilaçlar: {meds}")

            # Allergies
            allergies = (demo.get("allergies") or "").strip()
            if allergies:
                demo_lines.append(f"  Alerjiler: {allergies}")

            if demo_lines:
                lines.append("")
                lines.append("─── Demografi ───")
                lines.extend(demo_lines)

        # ── Risk flags grouped by severity ──────────────────────────────
        # Re-use the raw flags we already loaded at the top of this method.
        # Filter to ACTIVE flags (value '1'), excluding birth-outcome flags
        # which are already shown in the header.
        flags = patient_flags_raw
        active_flags = {k: v for k, v in flags.items()
                        if (v.get("value") or "").strip() == "1"
                        and k not in _BIRTH_OUTCOME_FLAG_KEYS}

        if active_flags:
            # Group by severity
            by_level: dict = {"danger": [], "warning": [], "info": [], "good": []}
            for fkey, fdata in active_flags.items():
                level = PATIENT_FLAG_LEVELS.get(fkey, "info")
                label = PATIENT_FLAG_LABELS.get(fkey, fkey)
                note = (fdata.get("notes") or "").strip()
                by_level.setdefault(level, []).append((label, note))

            lines.append("")
            lines.append("─── Aktif Bayraklar ───")
            for level, header in [("danger",  "🔴 TEHLİKE"),
                                  ("warning", "🟠 UYARI"),
                                  ("info",    "🔵 BİLGİ"),
                                  ("good",    "🟢 OLUMLU")]:
                items = by_level.get(level, [])
                if not items:
                    continue
                lines.append(f"  {header}:")
                for label, note in items:
                    if note:
                        lines.append(f"    • {label} — {note}")
                    else:
                        lines.append(f"    • {label}")

        # ── Latest visit summary + doctor note ──────────────────────────
        # Use the same source the short copy uses, but call it out clearly.
        latest_summary = (self.last_summary_plain or "").strip()
        doctor_note = ""
        try:
            doctor_note = self.note_edit.toPlainText().strip()
        except Exception as _ex:
            _log_warning("MainWindow.build_patient_long_summary", exc=_ex)

        if latest_summary:
            lines.append("")
            lines.append("─── Son Ziyaret Özeti ───")
            lines.append(latest_summary)

        if doctor_note:
            lines.append("")
            lines.append("─── Hekim Notu (Seçili Geliş) ───")
            lines.append(doctor_note)

        # ── All visit notes — v68-UI: doctor wants the FULL history
        # for uploading into external tracking software. Skip the
        # current visit's note (already shown above to avoid dupe).
        try:
            all_notes = load_all_visit_notes_for_patient(patient_key)
            # Filter non-empty notes, skip current visit's
            current_visit_key = ""
            try:
                if getattr(self, "current_subfolder", None) is not None:
                    current_visit_key = self.current_subfolder.name
            except Exception as _ex:
                _log_warning(
                    "build_patient_long_summary: current visit", exc=_ex)
            other_notes = [
                (vk, n.strip()) for vk, n in all_notes.items()
                if n and n.strip() and vk != current_visit_key
            ]
            if other_notes:
                # Sort so most recent appears first
                other_notes.sort(key=lambda x: x[0], reverse=True)
                lines.append("")
                lines.append("─── Tüm Geliş Notları (Geçmiş) ───")
                for vk, note in other_notes:
                    vlabel = format_visit_name(vk) or vk
                    lines.append(f"")
                    lines.append(f"  📅 {vlabel}:")
                    for ln in note.splitlines():
                        lines.append(f"    {ln}")
        except Exception as _ex:
            _log_warning(
                "build_patient_long_summary: all notes", exc=_ex)

        # ── Obstetric follow-up form ─────────────────────────────────
        # v68-UI: Include every non-empty field the doctor filled out
        # in the Obstetrik Takip tab. These are the vital-signs, USG
        # findings, and plan text that don't show up in the PDF summary.
        try:
            obs_data = _load_obs_form_data(patient_key) or {}
            obs_filled = [
                (k, v) for k, v in obs_data.items()
                if v and str(v).strip() and str(v).strip() != "-"
            ]
            if obs_filled:
                lines.append("")
                lines.append("─── Obstetrik Takip Formu ───")
                for k, v in sorted(obs_filled):
                    # Make field names more readable
                    label = str(k).replace("_", " ").title()
                    val_str = str(v).strip()
                    if "\n" in val_str:
                        lines.append(f"  {label}:")
                        for ln in val_str.splitlines():
                            lines.append(f"    {ln}")
                    else:
                        lines.append(f"  {label}: {val_str}")
        except Exception as _ex:
            _log_warning(
                "build_patient_long_summary: obs form", exc=_ex)

        # ── Gynecologic follow-up form ───────────────────────────────
        try:
            gyn_data = _load_gynec_form_data(patient_key) or {}
            gyn_filled = [
                (k, v) for k, v in gyn_data.items()
                if v and str(v).strip() and str(v).strip() != "-"
            ]
            if gyn_filled:
                lines.append("")
                lines.append("─── Jinekolojik Takip Formu ───")
                for k, v in sorted(gyn_filled):
                    label = str(k).replace("_", " ").title()
                    val_str = str(v).strip()
                    if "\n" in val_str:
                        lines.append(f"  {label}:")
                        for ln in val_str.splitlines():
                            lines.append(f"    {ln}")
                    else:
                        lines.append(f"  {label}: {val_str}")
        except Exception as _ex:
            _log_warning(
                "build_patient_long_summary: gyn form", exc=_ex)

        # ── Footer with timestamp ───────────────────────────────────────
        lines.append("")
        lines.append("─" * 60)
        lines.append(
            f"Üretildi: {datetime.now().strftime('%d.%m.%Y %H:%M')}")

        return "\n".join(lines)

    def copy_long_summary(self):
        """Copy the comprehensive patient summary to the clipboard.

        This is the long form — demographics + flags + meds + risks + visit
        summary + doctor note — versus the short `copy_summary` which is
        just the visit summary + note. Bound to Ctrl+Shift+C.
        """
        if not self.current_patient:
            QMessageBox.warning(self, "Uyarı", "Önce bir hasta seçin.")
            return
        txt = self.build_patient_long_summary()
        if not txt:
            QMessageBox.warning(self, "Uyarı", "Kopyalanacak veri yok.")
            return
        copied, err = safe_copy_to_clipboard(txt)
        if copied:
            line_count = len(txt.splitlines())
            self.statusBar().showMessage(
                f"✓ Uzun hasta özeti panoya kopyalandı ({line_count} satır)",
                5000)
        else:
            QMessageBox.warning(self, "Bilgi", f"Kopyalanamadı.\n{err}")
