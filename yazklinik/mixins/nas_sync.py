"""
╔══════════════════════════════════════════════════════════════╗
║  YazKlinik v68 — _NasSyncMixin
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

class _NasSyncMixin:
    """MainWindow methods related to NasSync. Mixed into MainWindow via MRO."""

    def _run_nas_sync(self):
        """Run a full sync from NAS into the DB with a progress dialog.

        First sync on a fresh clinic may take a few minutes (it parses every
        PDF once). Subsequent syncs skip unchanged folders via mtime check
        and typically finish in seconds.

        Threading model: the heavy work (SyncService.sync_all) runs on a
        QThreadPool worker via _run_bg. Progress updates cross thread
        boundaries via Qt signals (BackgroundTask.progress), so the GUI
        thread is never blocked — the progress dialog stays responsive and
        the user can cancel mid-sync.
        """
        from PySide6.QtWidgets import QProgressDialog
        if not self.root_folder or not self.root_folder.exists():
            QMessageBox.warning(
                self, "NAS Erişimi",
                "NAS klasörüne erişilemiyor:\n\n"
                f"{self.root_folder}\n\n"
                "Ağ bağlantınızı veya sürücü eşlemesini kontrol edin.")
            return

        # Rough upper bound on progress (first-run pessimistic)
        try:
            n_patients = sum(1 for _ in self.root_folder.iterdir()
                             if _.is_dir())
        except Exception:
            n_patients = 100

        pd = QProgressDialog(
            "NAS klasörü taranıyor...", "İptal",
            0, max(n_patients, 1), self)
        pd.setWindowTitle("NAS Senkronizasyonu")
        pd.setMinimumDuration(200)
        pd.setWindowModality(Qt.WindowModal)

        svc = SyncService(self.root_folder)

        # Cancel wiring: the progress dialog's cancel button flips a flag
        # on SyncService, which polls it inside its main loop.
        pd.canceled.connect(svc.cancel)

        t0 = _time.time()

        # ── Worker function (runs on background thread) ─────────────────
        # IMPORTANT: this function must not touch any widget directly. It
        # reports progress via `task.emit_progress` (cross-thread signal)
        # and returns the result dict on completion; the GUI-thread slot
        # (`_on_sync_done`) handles UI updates.
        #
        # We capture the BackgroundTask object via `task_holder` so the
        # worker's progress callback can reach back into it. This is a
        # workaround for the chicken-and-egg of `_run_bg` needing `fn`
        # before it creates the task.
        task_holder: dict = {"task": None}

        def _worker():
            svc_progress_adapter = lambda cur, total, msg: (
                task_holder["task"].emit_progress(cur, total, msg)
                if task_holder["task"] is not None else None
            )
            svc.progress_cb = svc_progress_adapter
            return svc.sync_all()

        # ── Main-thread slots ───────────────────────────────────────────
        def _on_progress(cur: int, total: int, msg: str):
            # Queued-delivered from worker thread → safe to touch widgets.
            if pd.wasCanceled():
                return
            pd.setMaximum(max(total, 1))
            pd.setValue(cur)
            pd.setLabelText(f"{msg}\n\nİlerleme: {cur} / {total}")

        def _on_sync_done(counters):
            pd.setValue(pd.maximum())
            pd.close()
            dt = _time.time() - t0

            # Detect "nothing changed" case for a clearer message
            total_changes = (counters['patients_added'] + counters['patients_updated']
                             + counters['visits_added'] + counters['visits_updated']
                             + counters['files_added'] + counters['files_removed'])

            if total_changes == 0 and counters.get('errors', 0) == 0:
                summary = (
                    f"<h3 style='color:#107C10;'>✓ Her şey güncel ({dt:.1f}s)</h3>"
                    "<p>NAS klasöründe yeni değişiklik yok. "
                    "Database veriniz günceldir.</p>"
                )
            else:
                summary = (
                    f"<h3 style='color:#005A9E;'>✓ Senkronizasyon tamamlandı ({dt:.1f}s)</h3>"
                    "<table cellpadding='4' cellspacing='0'>"
                    f"<tr><td>Yeni hasta:</td><td><b style='color:#107C10'>{counters['patients_added']}</b></td></tr>"
                    f"<tr><td>Güncellenen hasta:</td><td><b>{counters['patients_updated']}</b></td></tr>"
                    f"<tr><td>Yeni geliş:</td><td><b style='color:#107C10'>{counters['visits_added']}</b></td></tr>"
                    f"<tr><td>Güncellenen geliş:</td><td><b>{counters['visits_updated']}</b></td></tr>"
                    f"<tr><td>Yeni dosya:</td><td><b style='color:#107C10'>{counters['files_added']}</b></td></tr>"
                    f"<tr><td>Silinen dosya:</td><td><b>{counters['files_removed']}</b></td></tr>"
                    f"<tr><td>PDF işlendi:</td><td><b>{counters['pdfs_parsed']}</b></td></tr>"
                    "</table>"
                )
            if counters.get("errors", 0) > 0:
                summary += (f"<p style='color:#C42B1C;'>"
                            f"⚠ {counters['errors']} hata oluştu. "
                            f"Logs için: yazklinik_error_log.txt</p>")
            QMessageBox.information(self, "Senkronizasyon Sonucu", summary)

            # After sync, refresh the main patient list so new patients appear
            self.refresh_all()

        def _on_sync_error(ex):
            pd.close()
            _log_warning("SyncService.sync_all failed", exc=ex)
            QMessageBox.critical(self, "Senkronizasyon Hatası",
                                 f"Beklenmeyen hata:\n{ex}")

        # Submit
        task_holder["task"] = self._run_bg(
            _worker,
            on_done=_on_sync_done,
            on_error=_on_sync_error,
            on_progress=_on_progress,
            description="nas-sync")

    def _show_sync_status(self):
        """Show the last sync result in a read-only dialog."""
        info = db_latest_sync_info()
        if not info:
            QMessageBox.information(
                self, "Senkronizasyon Durumu",
                "Henüz bir senkronizasyon yapılmamış.\n\n"
                "Dosya → 🔄 NAS ile Senkronize Et menüsünü kullanın.")
            return
        html = (
            "<h3>Son Senkronizasyon</h3>"
            f"<p>Başlangıç: <b>{info['started_at']}</b><br>"
            f"Bitiş: <b>{info['finished_at'] or '(devam ediyor?)'}</b><br>"
            f"Tip: <b>{info['sync_type']}</b><br>"
            f"Süre: <b>{info['duration_sec']}s</b></p>"
            "<table cellpadding='4' cellspacing='0'>"
            f"<tr><td>Yeni hasta:</td><td><b>{info['patients_added']}</b></td></tr>"
            f"<tr><td>Güncellenen hasta:</td><td><b>{info['patients_updated']}</b></td></tr>"
            f"<tr><td>Yeni geliş:</td><td><b>{info['visits_added']}</b></td></tr>"
            f"<tr><td>Güncellenen geliş:</td><td><b>{info['visits_updated']}</b></td></tr>"
            f"<tr><td>Yeni dosya:</td><td><b>{info['files_added']}</b></td></tr>"
            f"<tr><td>Silinen dosya:</td><td><b>{info['files_removed']}</b></td></tr>"
            f"<tr><td>PDF işlendi:</td><td><b>{info['pdfs_parsed']}</b></td></tr>"
            "</table>"
        )
        QMessageBox.information(self, "Senkronizasyon Durumu", html)

    def _auto_sync_check(self):
        """Periodic lightweight check: has the NAS root mtime changed?
        If yes, run an incremental sync in the background. No UI dialog —
        status goes to the status bar only.

        The check itself is a single stat() call on the root folder plus a
        fast metadata-only pass through all known patients. On a 5000-patient
        clinic with no changes, this finishes in ~200ms.
        """
        if self._auto_sync_in_progress:
            return

        # ── Update NAS connectivity badge ─────────────────────────────
        # (This runs whether or not we have DB data, so offline use shows
        # the correct state even on a fresh install.)
        nas_online = False
        try:
            if self.root_folder and self.root_folder.exists():
                # is_dir is a cheap syscall — don't list, just probe
                nas_online = self.root_folder.is_dir()
        except Exception:
            nas_online = False
        if hasattr(self, "nas_status_badge"):
            # v68-UI: Compute DB location label for tooltip
            try:
                db_on_nas = DB_PATH.is_relative_to(self.root_folder) \
                    if hasattr(DB_PATH, "is_relative_to") \
                    else str(DB_PATH).startswith(str(self.root_folder))
            except Exception:
                db_on_nas = False
            db_loc = ("📡 Paylaşımlı (NAS)" if db_on_nas
                      else "💾 Yerel (bu bilgisayar)")
            if nas_online:
                self.nas_status_badge.setText("🟢 NAS: Çevrimiçi")
                self.nas_status_badge.setStyleSheet(
                    "color:#107C10;font:600 10px 'Segoe UI';"
                    "background:#E6F4E6;border:1px solid #107C10;padding:2px 8px;")
                self.nas_status_badge.setToolTip(
                    f"NAS erişilebilir: {self.root_folder}\n"
                    f"Veritabanı: {db_loc}\n"
                    f"    {DB_PATH}")
            else:
                self.nas_status_badge.setText("🔴 NAS: Çevrimdışı")
                self.nas_status_badge.setStyleSheet(
                    "color:#C42B1C;font:600 10px 'Segoe UI';"
                    "background:#FFF0F0;border:1px solid #C42B1C;padding:2px 8px;")
                self.nas_status_badge.setToolTip(
                    f"NAS erişilemiyor: {self.root_folder}\n"
                    f"Veritabanı: {db_loc}\n"
                    f"    {DB_PATH}\n"
                    "DB'deki veriler kullanılabilir — dosya açma "
                    "işlemleri NAS gerektiriyor.")

        if not db_has_any_patients():
            return  # Nothing to sync against yet — user should do first sync
        if not nas_online:
            return  # NAS is offline — silently skip

        # Pre-check work (cheap): decide whether a sync is needed. Flag is
        # NOT set here — we only flip it to True when we actually submit a
        # worker, so that if the pre-check returns early, a later poll
        # can run again without being blocked.
        try:
            # Cheap top-level check: did the root folder's mtime change?
            try:
                root_mtime = self.root_folder.stat().st_mtime
            except Exception:
                return
            root_changed = (self._last_root_mtime is None or
                            abs((self._last_root_mtime or 0) - root_mtime) > 0.1)
            self._last_root_mtime = root_mtime

            # Even if root looks unchanged, check a sample of recently-visited
            # patient folders to catch cases where a visit was added inside
            # an existing patient folder (which may or may not bump the root
            # mtime depending on the OS / share).
            needs_sync = root_changed

            if not needs_sync:
                # Quickly check the 20 most recently synced patients
                try:
                    with db_conn() as con:
                        rows = con.execute(
                            "SELECT folder_key, full_path, folder_mtime FROM patients "
                            "ORDER BY last_synced_at DESC LIMIT 20"
                        ).fetchall()
                    for _, fp, db_mtime in rows:
                        try:
                            live_mtime = Path(fp).stat().st_mtime
                            if abs((db_mtime or 0) - live_mtime) > 0.1:
                                needs_sync = True
                                break
                        except Exception:
                            continue
                except Exception as _ex:
                    _log_warning("MainWindow._auto_sync_check", exc=_ex)

            if not needs_sync:
                return  # All quiet on the NAS front

            # Kick off an incremental sync — same SyncService, just no modal.
            # Now runs on a background thread via _run_bg so the GUI doesn't
            # block if a silent sync picks up a lot of work. Flag is set
            # here (just before submitting) and cleared in the worker's
            # done/error callback — this keeps the poll timer from firing
            # parallel syncs while one is in flight.
            self._auto_sync_in_progress = True
            self.statusBar().showMessage(
                "📡 NAS değişikliği tespit edildi — arka planda senkronize ediliyor...",
                0)

            svc = SyncService(self.root_folder)

            def _auto_worker():
                # No progress reporting for the silent/background sync.
                return svc.sync_all()

            def _on_auto_done(counters):
                try:
                    changed = (counters.get("patients_added", 0) +
                               counters.get("visits_added", 0) +
                               counters.get("files_added", 0))
                    if changed > 0:
                        self.statusBar().showMessage(
                            f"✓ Sync: {counters.get('patients_added', 0)} yeni hasta, "
                            f"{counters.get('visits_added', 0)} yeni geliş, "
                            f"{counters.get('files_added', 0)} yeni dosya", 5000)
                        try:
                            self.refresh_all()
                        except Exception as _ex:
                            _log_warning("MainWindow._auto_sync_check", exc=_ex)
                    else:
                        self.statusBar().clearMessage()
                finally:
                    self._auto_sync_in_progress = False

            def _on_auto_error(ex):
                try:
                    _log_warning(f"auto-sync failed: {ex}")
                    self.statusBar().showMessage(
                        f"⚠ Otomatik sync hatası (log'a bak): {ex}", 4000)
                finally:
                    self._auto_sync_in_progress = False

            self._run_bg(_auto_worker,
                         on_done=_on_auto_done,
                         on_error=_on_auto_error,
                         description="auto-sync")
        except Exception as _ex:
            # Any unexpected failure during the pre-check — just log and
            # let the next poll try again. Don't leak the flag.
            _log_warning("MainWindow._auto_sync_check", exc=_ex)
            self._auto_sync_in_progress = False

    def refresh_all(self):
        """Reload patient list.

        Strategy: if the DB has patients (sync has run at least once), read
        from DB — much faster for 5000+ patients. If DB is empty, fall back
        to the old NAS scan and prompt the user to run a sync.
        """
        _subfolder_cache_invalidate()
        _latest_pdf_cache_invalidate()
        t0 = _time.time()

        used_db = False
        if db_has_any_patients():
            # DB-backed load — fast (~10-50ms even for 5000 patients)
            try:
                rows = db_list_patients()
                self.patient_paths = [Path(fp) for _, _, fp in rows]
                used_db = True
            except Exception as ex:
                _log_warning(f"db_list_patients failed, falling back to NAS: {ex}")

        if not used_db:
            # NAS fallback (original behaviour)
            self.patient_paths = get_patient_folders(self.root_folder)

        self.stat_patients.set_value(str(len(self.patient_paths)))
        self.apply_patient_filter()
        self._refresh_quick_panels()
        dt = _time.time() - t0
        source = "DB" if used_db else "NAS"
        self.statusBar().showMessage(
            f"Toplam {len(self.patient_paths)} hasta yüklendi "
            f"({dt:.2f}s, {source})", 3000)

        # On a fresh install, prompt the user to sync so they get the fast
        # DB-backed experience going forward.
        if not used_db and not getattr(self, "_sync_prompt_shown", False):
            self._sync_prompt_shown = True
            QTimer.singleShot(800, self._prompt_first_sync)

    def _prompt_first_sync(self):
        """Show a welcome / first-run prompt to run the initial sync."""
        try:
            if db_has_any_patients():
                return  # already synced at least once
        except Exception:
            return

        # Count patients on NAS so the user sees how long it'll take
        patient_count = 0
        try:
            if self.root_folder and self.root_folder.exists():
                patient_count = sum(1 for p in self.root_folder.iterdir()
                                    if p.is_dir())
        except Exception as _ex:
            _log_warning("MainWindow._prompt_first_sync", exc=_ex)

        # Rough time estimate: ~0.2s per patient for metadata + ~0.5s per PDF
        est_min = max(1, (patient_count // 200) if patient_count else 5)
        est_max = max(3, (patient_count // 50) if patient_count else 15)

        reply = QMessageBox.question(
            self, f"{get_clinic_name()} — İlk Kurulum",
            "<h3 style='color:#005A9E;margin-top:0'>"
            "Hoş geldiniz 👋</h3>"
            "<p>Uygulamanız ilk kez açılıyor. Daha hızlı çalışması için "
            "NAS klasörünüzün bir veritabanı kopyasını oluşturmak gerekiyor.</p>"
            f"<p><b>Taranacak hasta sayısı:</b> <b>{patient_count:,}</b><br>"
            f"<b>Tahmini süre:</b> ~{est_min}-{est_max} dakika</p>"
            "<p><b>Bu işlem sadece bir kez yapılır.</b> Sonrasında:</p>"
            "<ul>"
            "<li>⚡ Hasta listesi <b>anında</b> açılır (NAS yerine DB'den)</li>"
            "<li>📡 NAS'a yeni bir hasta eklenince <b>otomatik</b> yakalanır</li>"
            "<li>📴 NAS bağlantısı gittiğinde de <b>çalışmaya devam</b> eder</li>"
            "<li>📊 İstatistik ve filtre özellikleri aktif olur</li>"
            "</ul>"
            "<p>Şimdi başlatmak ister misiniz?<br>"
            "<i>(Daha sonra Dosya menüsünden de başlatabilirsiniz)</i></p>",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes)
        if reply == QMessageBox.Yes:
            self._run_nas_sync()
        else:
            self.statusBar().showMessage(
                "ℹ Senkronizasyon yapılmadı — Dosya menüsünden başlatabilirsiniz",
                6000)
