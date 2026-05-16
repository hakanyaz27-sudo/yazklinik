from __future__ import annotations

import os
import py_compile
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def ok(label: str) -> None:
    print(f"PASS: {label}")


def fail(label: str, detail: str = "") -> None:
    msg = f"FAIL: {label}"
    if detail:
        msg += f" - {detail}"
    print(msg)
    raise SystemExit(1)


def must_exist(rel: str) -> None:
    path = ROOT / rel
    if not path.exists():
        fail("missing file", rel)
    ok(f"exists {rel}")


def must_contain(rel: str, needle: str) -> None:
    text = read(rel)
    if needle not in text:
        fail(f"{rel} contains", needle)
    ok(f"{rel} contains {needle}")


def must_not_contain(rel: str, needle: str) -> None:
    text = read(rel)
    if needle in text:
        fail(f"{rel} must not contain", needle)
    ok(f"{rel} does not contain {needle}")


def compile_file(rel: str) -> None:
    pycache = Path(tempfile.gettempdir()) / "yazklinik_d104_pycache"
    pycache.mkdir(parents=True, exist_ok=True)
    old = os.environ.get("PYTHONPYCACHEPREFIX")
    old_prefix = getattr(sys, "pycache_prefix", None)
    os.environ["PYTHONPYCACHEPREFIX"] = str(pycache)
    sys.pycache_prefix = str(pycache)
    try:
        py_compile.compile(str(ROOT / rel), doraise=True)
    finally:
        sys.pycache_prefix = old_prefix
        if old is None:
            os.environ.pop("PYTHONPYCACHEPREFIX", None)
        else:
            os.environ["PYTHONPYCACHEPREFIX"] = old
    ok(f"compile {rel}")


def main() -> int:
    for rel in [
        "yazklinik_web.py",
        "WebShell/main.py",
        "WebShell/api_client.py",
        "WebShell/shell_window.py",
        "yazklinik_pdf_patient_extract.py",
    ]:
        compile_file(rel)

    for rel in [
        "YazKlinik_Windows_Terminal_D104.bat",
        "YazKlinik_macOS_Terminal_D104.command",
        "YazKlinik_macOS_Tam_Sistem_D104.command",
        "YAZKLINIK_D104_FULL_SYSTEM_AUDIT.py",
        "Build_D104_MacOS_Codex_Handoff.ps1",
        "Build_D104_Android_Package.ps1",
        "CODEX_MACOS_DEVAM_D104.md",
        "CODEX_MACOS_PROMPT_D104.txt",
        "TESLIM_OKU_D104.md",
        "mobile_shell/README_MOBILE_D104.txt",
        "mobile_shell/android/gradlew.bat",
        "mobile_shell/android/gradlew",
        "mobile_shell/android/tools/gradle-bootstrap.ps1",
        "mobile_shell/android/SETUP_ANDROID_WINDOWS.ps1",
        "mobile_shell/android/SETUP_ANDROID_WINDOWS.bat",
        "mobile_shell/android/BUILD_ANDROID_APK_MANUAL_WINDOWS.ps1",
        "mobile_shell/android/BUILD_ANDROID_APK_MANUAL_WINDOWS.bat",
        "mobile_shell/android/BUILD_ANDROID_APK_WINDOWS.ps1",
        "mobile_shell/android/INSTALL_ANDROID_APK_WINDOWS.ps1",
        "mobile_shell/android/ANDROID_KURULUM_REHBERI_D104.md",
        "mobile_shell/android/app/src/main/java/com/yazklinik/terminal/MainActivity.java",
        "mobile_shell/ios/YazKlinikMobile/ContentView.swift",
        "mobile_shell/pwa/index.html",
    ]:
        must_exist(rel)

    must_contain("WebShell/api_client.py", "http://192.168.1.40:5052")
    must_contain("WebShell/main.py", "http://192.168.1.40:5052")
    must_contain("WebShell/main.py", "def _prefer_loopback_for_local_webshell")
    must_contain("WebShell/main.py", "YAZKLINIK_WEBSHELL_RUNTIME_LOCAL_URL")
    must_contain("WebShell/main.py", "def _configure_windows_terminal_accelerator")
    must_contain("WebShell/main.py", "YAZKLINIK_WEBSHELL_WINDOWS_ACCELERATOR")
    must_contain("WebShell/main.py", "CanvasOopRasterization")
    must_contain("WebShell/shell_window.py", "def _record_local_audio_wav_payload")
    must_contain("WebShell/shell_window.py", "window.ykNativeRecordWav")
    must_contain("WebShell/shell_window.py", "MENU_MODE_TOOLTIPS")
    must_contain("WebShell/shell_window.py", "def _mode_button_style")
    must_contain("WebShell/shell_window.py", "button.setStyleSheet(_mode_button_style(active, key))")
    must_contain("WebShell/shell_window.py", "class TerminalPcBuffer")
    must_contain("WebShell/shell_window.py", "_WEBSHELL_WINDOWS_ACCELERATOR_JS")
    must_contain("WebShell/shell_window.py", "Windows Buffer AKTIF")
    must_contain("WebShell/theme.py", 'QLabel[role="accelerator"]')
    must_contain("YazKlinik_Windows_Terminal_D104.bat", "http://192.168.1.40:5052")
    must_contain("YazKlinik_Windows_Terminal_D104.bat", 'if /I not "%%~I"=="http://127.0.0.1:5052"')
    must_contain("YazKlinik_Windows_Terminal_D104.bat", "YAZKLINIK_WEBSHELL_WINDOWS_ACCELERATOR=0")
    must_contain("YazKlinik_Windows_Terminal_D104.bat", "YAZKLINIK_WEBSHELL_SAFE_MODE=1")
    must_contain("YazKlinik_WebShell_Windows.bat", "YAZKLINIK_WEBSHELL_WINDOWS_ACCELERATOR=0")
    must_contain("YazKlinik_WebShell_Windows.bat", "YAZKLINIK_WEBSHELL_SAFE_MODE=1")
    must_contain("YazKlinik_macOS_Terminal_D104.command", "http://192.168.1.40:5052")
    must_contain("YazKlinik_macOS_Terminal_D104.command", "is_saved_local_server()")
    must_contain(
        "mobile_shell/android/app/src/main/java/com/yazklinik/terminal/MainActivity.java",
        "http://192.168.1.40:5052",
    )
    must_contain("mobile_shell/android/app/src/main/java/com/yazklinik/terminal/MainActivity.java", "TAILSCALE_SERVER")
    must_contain("mobile_shell/android/app/src/main/java/com/yazklinik/terminal/MainActivity.java", "onReceivedSslError")
    must_contain("mobile_shell/android/app/src/main/java/com/yazklinik/terminal/MainActivity.java", "POST_NOTIFICATIONS")
    must_contain("mobile_shell/android/app/src/main/java/com/yazklinik/terminal/MainActivity.java", "YazKlinikAndroid/D104")
    must_contain("mobile_shell/android/app/src/main/AndroidManifest.xml", "POST_NOTIFICATIONS")
    must_contain("mobile_shell/android/app/src/main/AndroidManifest.xml", "resizeableActivity")
    must_contain("mobile_shell/android/app/src/main/AndroidManifest.xml", 'package="com.yazklinik.terminal"')
    must_contain("mobile_shell/android/app/src/main/res/xml/network_security_config.xml", "100.71.108.26")
    must_contain("mobile_shell/android/SETUP_ANDROID_WINDOWS.ps1", "commandlinetools-win-11076708_latest.zip")
    must_contain("mobile_shell/android/SETUP_ANDROID_WINDOWS.ps1", "api.adoptium.net")
    must_contain("mobile_shell/android/SETUP_ANDROID_WINDOWS.ps1", "--no_https")
    must_contain("mobile_shell/android/BUILD_ANDROID_APK_MANUAL_WINDOWS.ps1", "aapt2")
    must_contain("mobile_shell/android/BUILD_ANDROID_APK_MANUAL_WINDOWS.ps1", "apksigner")
    must_contain("mobile_shell/android/BUILD_ANDROID_APK_WINDOWS.ps1", ".android-local\\android-sdk")
    must_contain("mobile_shell/android/BUILD_ANDROID_APK_WINDOWS.ps1", "BUILD_ANDROID_APK_MANUAL_WINDOWS.ps1")
    must_contain("mobile_shell/README_MOBILE_D104.txt", "BUILD_ANDROID_APK_WINDOWS.bat")
    must_contain("mobile_shell/README_MOBILE_D104.txt", "BUILD_ANDROID_APK_MANUAL_WINDOWS.bat")
    must_contain("mobile_shell/README_MOBILE_D104.txt", "SETUP_ANDROID_WINDOWS.bat")
    must_contain("mobile_shell/ios/YazKlinikMobile/ContentView.swift", "http://192.168.1.40:5052")
    must_contain("mobile_shell/pwa/index.html", "http://192.168.1.40:5052")

    must_not_contain("yazklinik_web.py", "fetch(mediaUrl")
    must_not_contain("yazklinik_web.py", "data-yk-patient-media-collapse")
    must_contain("yazklinik_web.py", "scheme === 'yazklinik-print-photo'")
    must_contain("yazklinik_web.py", "if (!ykCanUseNativePhotoHelper()) return ykServerJpegPrint();")
    must_contain("yazklinik_web.py", "function ykFxCanUseNativePhotoHelperWithoutBrowserPrompt()")
    must_contain("yazklinik_web.py", "function mediaTryNativePhotoPrint(payload)")
    must_contain("yazklinik_web.py", "async function ykFxTryNativePhotoPrint(payload)")
    must_contain("yazklinik_web.py", "if(await ykFxTryNativePhotoPrint(payload)) return;")
    must_contain("yazklinik_web.py", 'Cift tik, "Foto da Ac" butonuyla ayni yolu izlesin.')
    must_contain("yazklinik_web.py", 'Cift tik, "Foto da Ac" ile ayni Windows Foto yolunu izler.')
    must_contain("yazklinik_web.py", "openCurrentMediaInWindowsPhoto();")
    must_contain("yazklinik_web.py", "openMediaPreviewPage(p.src, p.title);")
    must_contain("yazklinik_web.py", "if(ykFxCanUseNativePhotoHelperWithoutBrowserPrompt()){")
    must_contain("yazklinik_web.py", "openMediaPrintPage(p.src, p.title);")
    must_contain("yazklinik_web.py", "printCurrentMedia();")
    must_contain("yazklinik_web.py", "yk-hd-hero")
    must_contain("yazklinik_web.py", "Resim ve Video G&ouml;r&uuml;nt&uuml;")
    must_contain("yazklinik_web.py", "function _isWebShell()")
    must_contain("yazklinik_web.py", "function _recordWebShellNativeOnce(autoRestart")
    must_contain("yazklinik_web.py", "VOICE_AGENT_RECORD_SECONDS = 4")
    must_contain("yazklinik_web.py", "ALEX_COMMAND_RECORD_SECONDS = 6")
    must_contain("yazklinik_web.py", "function markAlexHeard")
    must_contain("yazklinik_web.py", "Alex duydu:")
    must_contain("yazklinik_web.py", "recordAlexChunk(seconds)")
    must_contain("yazklinik_web.py", "window.ykNativeRecordWav(VOICE_AGENT_RECORD_SECONDS)")
    must_contain("yazklinik_web.py", "VOICE_AGENT_DIALOG_TIMEOUT_MS = 18000")
    must_contain("yazklinik_web.py", '"source": "fast_action"')
    must_contain("yazklinik_web.py", "def _smart_dialog_live_companion_reply")
    must_contain("yazklinik_web.py", '"source": "live_companion"')
    must_contain("yazklinik_web.py", "alex_mode: !!alexLoop")
    must_contain("yazklinik_web.py", "Adin Alex")
    must_contain("yazklinik_web.py", 'id="ykVoiceAlex"')
    must_contain("yazklinik_web.py", "function recordAlexChunk")
    must_contain("yazklinik_web.py", "function _recordBrowserAlexChunk")
    must_contain("yazklinik_web.py", "Web Alex icin HTTPS veya localhost gerekir")
    must_contain("yazklinik_web.py", "function startAlexAlwaysOn")
    must_contain("yazklinik_web.py", "function alexHasOpen")
    must_contain("yazklinik_web.py", "function alexIsAddressed")
    must_contain("yazklinik_web.py", "function alexIsOnlyAddress")
    must_contain("yazklinik_web.py", "Buradayim doktorum, seni dinliyorum.")
    must_contain("yazklinik_web.py", "Pasifim. Alex dersen yine cevap veririm.")
    must_contain("yazklinik_web.py", '@app.route("/api/web-mic/context")')
    must_contain("yazklinik_web.py", "server_native_safe")
    must_contain("yazklinik_web.py", "ykWebMicHelp")
    must_contain("yazklinik_web.py", "window.ykMicNativeSafe")
    must_contain("yazklinik_web.py", "Ses odak")
    must_contain("yazklinik_web.py", "function _voiceFocusAudioConstraints")
    must_contain("yazklinik_web.py", "function _isLikelyBackgroundSpeech")
    must_contain("yazklinik_web.py", "function _focusGetUserMediaConstraints")
    must_contain("yazklinik_web.py", "def _voice_focus_clean_transcript")
    must_contain("yazklinik_web.py", "def _ai_phone_focus_native_samples")
    must_contain("yazklinik_web.py", "voice_focus_meta")
    must_contain("WebShell/shell_window.py", "def _focus_local_voice_samples")
    must_contain("WebShell/shell_window.py", "voice_focus_meta")
    must_contain("yazklinik_web.py", "filename = data.get(\"filename\") or filename")
    must_contain("yazklinik_web.py", "def _rx_daily_review_payload")
    must_contain("yazklinik_web.py", "def _diet_display_text_v1000")
    must_contain("yazklinik_web.py", "def _diet_display_block_text_v1000")
    must_contain("yazklinik_web.py", "def _diet_sanitize_saved_html_v1000")
    must_contain("yazklinik_web.py", "def _diet_day_title_v1000")
    must_contain("yazklinik_web.py", "yk-diet-readability-d104")
    must_contain("yazklinik_web.py", "def _diet_is_transposed_week_table_v1000")
    must_contain("yazklinik_web.py", "def _diet_render_transposed_week_table_v1000")
    must_contain("yazklinik_web.py", 'grid-template-columns:repeat(auto-fit,minmax(240px,1fr))')
    must_contain("yazklinik_web.py", '.yk-ai-section[data-section-key*="makro"]')
    must_contain("yazklinik_web.py", '@app.route("/api/recete/gunluk-kontrol")')
    must_contain("yazklinik_web.py", '@app.route("/recete-gunluk-kontrol")')
    must_contain("yazklinik_web.py", "yk-rx-review-btn")
    must_contain("yazklinik_web.py", "RX_PRINT_PATIENT_FIELDS")
    must_contain("yazklinik_web.py", "RX_PRINT_DRUG_FIELDS")
    must_contain("yazklinik_web.py", "ykRxApplyFieldVisibility")
    must_contain("yazklinik_web.py", 'name="ykRxDrugField"')
    must_contain("yazklinik_web.py", "ykRxPrintDiagnosis")
    must_contain("yazklinik_web.py", "ykRxPrintDrugResults")
    must_contain("yazklinik_web.py", "function ykRxAddPrintDrugFromList")
    must_contain("yazklinik_web.py", "rxDrugsHost")
    must_contain("yazklinik_web.py", "def _voice_rx_apply_from_command")
    must_contain("yazklinik_web.py", "def _voice_rx_match_diagnoses")
    must_contain("yazklinik_web.py", "def _voice_rx_match_medication_name")
    must_contain("yazklinik_web.py", "voice_rx_created")
    must_contain("yazklinik_web.py", "Kutu: {box_count}")
    must_contain("yazklinik_web.py", '"daily_frequency": str(freq or "")')
    must_contain("yazklinik_web.py", "D105: Koyu aktif hasta bandinda")
    must_contain("yazklinik_web.py", ".active-patient-banner .apb-action")
    must_contain("yazklinik_web.py", "/yk-core.css?v=D108")
    must_contain("yazklinik_web.py", "def _upcoming_delivery_items(")
    must_contain("yazklinik_web.py", "force_full_scan")
    must_contain("yazklinik_web.py", "upcoming_delivery_items_v6")
    must_contain("yazklinik_web.py", "/yaklasan-dogumlar?refresh=1")
    must_contain("yazklinik_web.py", "def _dicom_command_panel_state")
    must_contain("yazklinik_web.py", "id=\"ykDicomCommandResult\"")
    must_contain("yazklinik_web.py", "id=\"ykDicomQuickSyncBtn\"")
    must_contain("yazklinik_web.py", "id=\"ykDicomSendWorklistBtn\"")
    must_contain("yazklinik_web.py", "runCommand(this, 'Hizli Orthanc senkronu', '/api/orthanc/sync'")
    must_contain("yazklinik_web.py", "runCommand(this, 'Bugunku Worklist gonderimi', '/api/dicom/worklist/bugunu-gonder'")
    must_contain("yazklinik_web.py", '@app.route("/onam/ac/<int:form_id>")')
    must_contain("yazklinik_web.py", "def open_consent(form_id):")
    must_contain("yazklinik_web.py", "def _send_db_printable_blob(")
    must_contain("yazklinik_web.py", 'href="/onam/ac/{form_id}"')
    must_contain("yazklinik_web.py", 'href="/onam/indir/{form_id}"')
    must_contain("yazklinik_web.py", 'def _pdf_atelier_extract_layout')
    must_contain("yazklinik_web.py", '@app.route("/hasta/<patient_key>/pdf-atolyesi/pdf-layout"')
    must_contain("yazklinik_web.py", 'id="editableProjectBtn"')
    must_contain("yazklinik_web.py", 'id="blankProjectBtn"')
    must_contain("yazklinik_web.py", 'Projeyi PDF olarak olustur ve kaydet')
    must_contain("mobile_shell/android/app/build.gradle", "versionName \"D104\"")
    must_contain("mobile_shell/README_MOBILE_D104.txt", "PDF Studio")

    print("SONUC: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
