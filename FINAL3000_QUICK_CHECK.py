import os
import py_compile
import shutil
import tempfile
import uuid
import atexit
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _compile(path: Path) -> None:
    target_dir = Path(tempfile.mkdtemp(prefix="yk_final3000_compile_"))
    try:
        py_compile.compile(
            str(path),
            cfile=str(target_dir / (path.name + ".pyc")),
            doraise=True,
        )
    finally:
        shutil.rmtree(target_dir, ignore_errors=True)


def main() -> int:
    os.environ.setdefault("YAZKLINIK_TESTING", "1")
    os.environ.setdefault("YAZKLINIK_WEB_PORT", "5051")
    quick_runtime_root = Path(tempfile.mkdtemp(prefix="yk_final3000_runtime_"))
    quick_db_root = quick_runtime_root / "db"
    quick_data_root = quick_runtime_root / "data"
    quick_db_root.mkdir(parents=True, exist_ok=True)
    quick_data_root.mkdir(parents=True, exist_ok=True)
    os.environ["YAZKLINIK_DB_ROOT"] = str(quick_db_root)
    os.environ["YAZKLINIK_DB_PATH"] = str(quick_db_root / "quickcheck.sqlite3")
    os.environ["YAZKLINIK_DATA_ROOT"] = str(quick_data_root)
    os.environ["YAZKLINIK_NAS_ROOT"] = str(quick_data_root)
    os.environ["YAZKLINIK_MULTIMEDIA_ROOT"] = str(quick_runtime_root / "media")
    os.environ["YAZKLINIK_TEMP_DIR"] = str(quick_runtime_root / "temp")
    os.environ["YAZKLINIK_EXPORT_ROOT"] = str(quick_runtime_root / "export")
    os.environ["YAZKLINIK_BACKUP_ROOT"] = str(quick_runtime_root / "backup")
    atexit.register(lambda: shutil.rmtree(quick_runtime_root, ignore_errors=True))

    for name in (
        "yazklinik_web.py",
        "yazklinik_feature_sync.py",
        "yazklinik_pdf_patient_extract.py",
        "yazklinik_config.py",
        "yazklinik_runtime_cleanup.py",
        "yazklinik_whatsapp_local_helper.py",
    ):
        _compile(ROOT / name)

    secret_path = ROOT / ".secret_key"
    had_secret = secret_path.exists()

    import yazklinik_web as y
    from yazklinik_runtime_cleanup import run_startup_cleanup

    cleanup_root = Path(tempfile.mkdtemp(prefix="yk_final3000_cleanup_"))
    try:
        (cleanup_root / "__pycache__").mkdir()
        (cleanup_root / "__pycache__" / "old.pyc").write_bytes(b"x")
        (cleanup_root / "old.pyc").write_bytes(b"x")
        (cleanup_root / "server_stdout.log").write_text("old", encoding="utf-8")
        (cleanup_root / "uploads").mkdir()
        (cleanup_root / "uploads" / "keep.txt").write_text("keep", encoding="utf-8")
        (cleanup_root / "yazklinik_wa_share").mkdir()
        result = run_startup_cleanup(
            app_root=cleanup_root,
            temp_root=cleanup_root,
            version="quickcheck",
            stop_stale_servers=False,
        )
        assert result.get("ok") is True, result
        assert not (cleanup_root / "__pycache__").exists(), result
        assert not (cleanup_root / "old.pyc").exists(), result
        assert not (cleanup_root / "server_stdout.log").exists(), result
        assert not (cleanup_root / "yazklinik_wa_share").exists(), result
        assert (cleanup_root / "uploads" / "keep.txt").exists(), result
    finally:
        shutil.rmtree(cleanup_root, ignore_errors=True)

    payload = {}
    y._apply_ollama_think_policy(payload, "deepseek-r1:70b")
    assert payload.get("think") is True, "deepseek-r1:70b think:true olmali"
    payload = {}
    y._apply_ollama_think_policy(payload, "deepseek-r1:70b2")
    assert payload.get("think") is True, "deepseek-r1:70b2 think:true olmali"
    payload = {}
    y._apply_ollama_think_policy(payload, "deepseek-r1:32b")
    assert payload.get("think") is None, "32b icin zorunlu think alani beklenmez"

    assert y._patient_data_canonical_key("yas") == "age"
    assert y._patient_data_canonical_key("Yaş") == "age"
    assert y._patient_data_canonical_key("patient_age") == "age"

    test_key = "__quickcheck_age_patient_" + uuid.uuid4().hex + "__"
    try:
        y.save_patient_demographics(test_key, {"age": 30})
        decision = y._patient_data_suggest_value(
            test_key,
            "yas",
            31,
            source="quick_check_pdf",
            source_ref="unit",
            auto_apply_empty=True,
        )
        assert decision.get("status") == "queued", decision
        demo = y.load_patient_demographics(test_key)
        assert int(demo.get("age")) == 30, demo
        y._patient_data_apply_value(test_key, "age", "32")
        demo = y.load_patient_demographics(test_key)
        assert int(demo.get("age")) == 32, demo
    finally:
        try:
            with y.db_conn() as con:
                y._web_ensure_patient_demographics_schema_v1000(con)
                y._ensure_patient_data_conflict_schema(con)
                con.execute(
                    "DELETE FROM patient_data_conflicts WHERE patient_key=?",
                    (test_key,),
                )
                con.execute(
                    "DELETE FROM patient_demographics WHERE patient_key=?",
                    (test_key,),
                )
                con.commit()
        except Exception:
            pass
        if not had_secret and secret_path.exists():
            try:
                secret_path.unlink()
            except Exception:
                pass

    print("FINAL3000_QUICK_CHECK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
