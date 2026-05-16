"""YazKlinik install/update helper.

This module is intentionally dependency-light because it is imported from the
settings and update pages.  It keeps the web app usable even before the full
installer has run, and provides a guarded ZIP update path with automatic
backups.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


CURRENT_VERSION = "YazKlinik Final D250"
CONFIG_NAME = ".yazklinik_install.json"
VERSION_FILE = "VERSION.json"
MANIFEST_NAMES = {"manifest.json", "update_manifest.json", "VERSION.json"}


DEFAULT_INSTALL_CONFIG: Dict[str, Any] = {
    "version": CURRENT_VERSION,
    "setup_complete": True,
    "install_dir": "",
    "data_dir": r"\\Sam\usg\Hastalar",
    "nas_dir": r"\\Sam\usg\Hastalar",
    "clinic_name": "YazKlinik",
    "doctor_name": "Op. Dr. Hakan YAZ",
    "db_root": r"\\Sam\usg\DATABASE",
    "db_path": r"\\Sam\usg\DATABASE\yazklinik_v68.sqlite3",
    "multimedia_root": r"E:\USG\Multimedia",
    "temp_dir": "E:\\USG\\\u00c7\u0131kt\u0131lar",
    "export_root": "E:\\USG\\\u00c7\u0131kt\u0131lar",
    "backup_root": r"E:\USG\Backup",
    "web_port": "5443",
    "server_url": "https://127.0.0.1:5443",
    "orthanc_host": "127.0.0.1",
    "orthanc_port": "8042",
    "orthanc_url": "http://127.0.0.1:8042",
    "orthanc_user": "",
    "orthanc_pass": "",
    "update_history": [],
}


def _module_dir() -> Path:
    return Path(__file__).resolve().parent


def _home_config_path() -> Path:
    raw = os.environ.get("YAZKLINIK_INSTALL_CONFIG", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / CONFIG_NAME


def _local_config_path() -> Path:
    return _module_dir() / "yazklinik_install.json"


def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
        os.replace(temp_name, path)
    finally:
        try:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        except Exception:
            pass


def _load_runtime_config() -> Dict[str, Any]:
    try:
        from yazklinik_config import load_config

        return load_config()
    except Exception:
        return {}


def _save_runtime_config(cfg: Dict[str, Any]) -> None:
    try:
        from yazklinik_config import load_config, save_config

        current = load_config()
        current.update(
            {
                "web_port": str(cfg.get("web_port") or "5443"),
                "server_url": str(cfg.get("server_url") or ""),
                "nas_root": str(cfg.get("nas_dir") or cfg.get("data_dir") or ""),
                "data_root": str(cfg.get("data_dir") or cfg.get("nas_dir") or ""),
                "db_root": str(cfg.get("db_root") or ""),
                "db_path": str(cfg.get("db_path") or ""),
                "multimedia_root": str(cfg.get("multimedia_root") or ""),
                "temp_dir": str(cfg.get("temp_dir") or ""),
                "export_root": str(cfg.get("export_root") or ""),
                "backup_root": str(cfg.get("backup_root") or ""),
                "orthanc_host": str(cfg.get("orthanc_host") or "192.168.1.148"),
                "orthanc_port": str(cfg.get("orthanc_port") or "8042"),
                "orthanc_url": str(cfg.get("orthanc_url") or ""),
                "orthanc_user": str(cfg.get("orthanc_user") or ""),
                "orthanc_pass": str(cfg.get("orthanc_pass") or ""),
            }
        )
        save_config(current)
    except Exception:
        pass


def _normalize_config(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    runtime = _load_runtime_config()
    cfg = dict(DEFAULT_INSTALL_CONFIG)
    if runtime:
        cfg.update(
            {
                "data_dir": runtime.get("data_root") or cfg["data_dir"],
                "nas_dir": runtime.get("nas_root")
                or runtime.get("data_root")
                or cfg["nas_dir"],
                "db_root": runtime.get("db_root") or cfg["db_root"],
                "db_path": runtime.get("db_path") or cfg["db_path"],
                "multimedia_root": runtime.get("multimedia_root")
                or cfg["multimedia_root"],
                "temp_dir": runtime.get("temp_dir") or cfg["temp_dir"],
                "export_root": runtime.get("export_root") or cfg["export_root"],
                "backup_root": runtime.get("backup_root") or cfg["backup_root"],
                "web_port": runtime.get("web_port") or cfg["web_port"],
                "server_url": runtime.get("server_url") or cfg["server_url"],
                "orthanc_host": runtime.get("orthanc_host")
                or cfg["orthanc_host"],
                "orthanc_port": runtime.get("orthanc_port")
                or cfg["orthanc_port"],
                "orthanc_url": runtime.get("orthanc_url") or cfg["orthanc_url"],
                "orthanc_user": runtime.get("orthanc_user")
                or cfg["orthanc_user"],
                "orthanc_pass": runtime.get("orthanc_pass")
                or cfg["orthanc_pass"],
            }
        )
    if data:
        cfg.update({str(k): v for k, v in data.items() if v is not None})
    if not cfg.get("install_dir"):
        cfg["install_dir"] = str(_module_dir())
    if not cfg.get("version"):
        cfg["version"] = CURRENT_VERSION
    if not isinstance(cfg.get("update_history"), list):
        cfg["update_history"] = []
    port = str(cfg.get("web_port") or "5443")
    if not str(cfg.get("server_url") or "").strip():
        cfg["server_url"] = f"https://127.0.0.1:{port}"
    return cfg


def load_install_config(path: Optional[os.PathLike[str] | str] = None) -> Dict[str, Any]:
    """Load install state from home config, local config and runtime config."""

    cfg_path = Path(path).expanduser() if path else _home_config_path()
    data: Dict[str, Any] = {}
    home_data = _read_json(cfg_path)
    local_data = _read_json(_local_config_path())
    data.update(home_data)
    data.update(local_data)
    if not local_data.get("install_dir"):
        # Each packaged copy should manage the folder it is running from.
        # This prevents an old global config from pointing a fresh install to
        # a stale V1000/V2000 directory.
        data["install_dir"] = str(_module_dir())
        if not local_data.get("version"):
            data["version"] = CURRENT_VERSION
    return _normalize_config(data)


def save_install_config(
    config: Dict[str, Any], path: Optional[os.PathLike[str] | str] = None
) -> Path:
    cfg = _normalize_config(config)
    cfg["updated_at"] = _now_iso()
    cfg_path = Path(path).expanduser() if path else _home_config_path()
    _write_json(cfg_path, cfg)
    try:
        _write_json(_local_config_path(), cfg)
    except Exception:
        pass
    _save_runtime_config(cfg)
    return cfg_path


def is_setup_complete() -> bool:
    cfg = load_install_config()
    return bool(cfg.get("setup_complete") and cfg.get("install_dir"))


def get_install_dir() -> Path:
    return Path(str(load_install_config().get("install_dir") or _module_dir())).expanduser()


def get_backup_dir() -> Path:
    cfg = load_install_config()
    backup = Path(str(cfg.get("backup_root") or r"E:\USG\Backup")).expanduser()
    try:
        backup.mkdir(parents=True, exist_ok=True)
    except Exception:
        backup = _module_dir() / ".updates_backup"
        backup.mkdir(parents=True, exist_ok=True)
    return backup


def _safe_mkdir(path_text: str, messages: List[str]) -> None:
    if not path_text:
        return
    path = Path(path_text).expanduser()
    try:
        path.mkdir(parents=True, exist_ok=True)
        messages.append(f"Klasor hazir: {path}")
    except Exception as ex:
        messages.append(f"Klasor olusturulamadi, elle kontrol edin: {path} ({ex})")


def run_setup(
    install_dir: Optional[str] = None,
    data_dir: Optional[str] = None,
    nas_dir: Optional[str] = None,
    clinic_name: str = "YazKlinik",
    doctor_name: str = "Op. Dr. Hakan YAZ",
    create_dirs: bool = True,
    **extra: Any,
) -> Tuple[bool, str]:
    """Persist the installation paths used by web, terminal and desktop shell."""

    try:
        cfg = load_install_config()
        if install_dir:
            cfg["install_dir"] = str(Path(install_dir).expanduser())
        if data_dir:
            cfg["data_dir"] = data_dir
        if nas_dir:
            cfg["nas_dir"] = nas_dir
        else:
            cfg["nas_dir"] = cfg.get("nas_dir") or cfg.get("data_dir")
        cfg["clinic_name"] = clinic_name or cfg.get("clinic_name") or "YazKlinik"
        cfg["doctor_name"] = doctor_name or cfg.get("doctor_name") or "Op. Dr. Hakan YAZ"
        for key, value in extra.items():
            if value is not None and key not in {"create_dirs"}:
                cfg[str(key)] = value
        cfg["setup_complete"] = True
        cfg["version"] = cfg.get("version") or CURRENT_VERSION
        cfg["configured_at"] = cfg.get("configured_at") or _now_iso()

        messages = [f"YazKlinik kurulum ayarlari kaydedildi: {cfg['install_dir']}"]
        if create_dirs:
            for key in (
                "install_dir",
                "data_dir",
                "nas_dir",
                "db_root",
                "multimedia_root",
                "temp_dir",
                "export_root",
                "backup_root",
            ):
                _safe_mkdir(str(cfg.get(key) or ""), messages)

        save_install_config(cfg)
        _write_version_file(Path(str(cfg["install_dir"])), cfg)
        return True, "\n".join(messages)
    except Exception as ex:
        return False, f"Kurulum ayarlari kaydedilemedi: {ex}"


def _write_version_file(install_dir: Path, cfg: Dict[str, Any]) -> None:
    data = {
        "version": cfg.get("version") or CURRENT_VERSION,
        "updated_at": cfg.get("updated_at") or _now_iso(),
        "install_dir": str(install_dir),
    }
    try:
        _write_json(install_dir / VERSION_FILE, data)
    except Exception:
        try:
            _write_json(_module_dir() / VERSION_FILE, data)
        except Exception:
            pass


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _zip_rel(name: str) -> Optional[str]:
    normalized = name.replace("\\", "/").strip("/")
    if not normalized or normalized.endswith("/"):
        return None
    parts = PurePosixPath(normalized).parts
    if any(part in {"", ".", ".."} for part in parts):
        return None
    drive_like = len(parts[0]) >= 2 and parts[0][1] == ":"
    if normalized.startswith("/") or drive_like:
        return None
    return normalized


def _dest_rel(zip_rel: str) -> str:
    for prefix in ("source/", "app/"):
        if zip_rel.startswith(prefix):
            return zip_rel[len(prefix) :]
    return zip_rel


def validate_update_zip(zip_path: os.PathLike[str] | str) -> Tuple[bool, str, Dict[str, Any]]:
    """Validate an update ZIP and return a normalized manifest."""

    path = Path(zip_path)
    if not path.exists():
        return False, "ZIP dosyasi bulunamadi.", {}
    try:
        manifest: Dict[str, Any] = {}
        files: Dict[str, Dict[str, Any]] = {}
        with zipfile.ZipFile(path, "r") as zf:
            bad = zf.testzip()
            if bad:
                return False, f"ZIP bozuk gorunuyor: {bad}", {}
            for info in zf.infolist():
                rel = _zip_rel(info.filename)
                if rel is None:
                    continue
                if Path(rel).name in MANIFEST_NAMES:
                    try:
                        loaded = json.loads(zf.read(info).decode("utf-8-sig"))
                        if isinstance(loaded, dict):
                            manifest.update(loaded)
                    except Exception:
                        pass
                    continue
                dest = _dest_rel(rel)
                if not dest or dest.startswith((".updates_backup/", "__pycache__/")):
                    continue
                files[dest] = {
                    "zip_name": rel,
                    "size": int(info.file_size),
                    "sha256": hashlib.sha256(zf.read(info)).hexdigest(),
                }
        if not files:
            return False, "ZIP icinde guncellenecek guvenli dosya yok.", manifest
        manifest.setdefault("version", CURRENT_VERSION)
        manifest.setdefault("release_date", datetime.now().date().isoformat())
        manifest.setdefault("changelog", "")
        manifest["files"] = files
        return True, f"{len(files)} dosya dogrulandi.", manifest
    except zipfile.BadZipFile:
        return False, "Bu dosya gecerli bir ZIP degil.", {}
    except Exception as ex:
        return False, f"ZIP okunamadi: {ex}", {}


def _call_progress(callback: Optional[Callable[[str], None]], message: str) -> None:
    if callback:
        try:
            callback(message)
        except Exception:
            pass


def _backup_existing_files(
    install_dir: Path,
    backup_dir: Path,
    manifest: Dict[str, Any],
    on_progress: Optional[Callable[[str], None]],
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_root = backup_dir / f"update_backup_{stamp}"
    files_meta: List[Dict[str, Any]] = []
    backup_root.mkdir(parents=True, exist_ok=True)
    for rel in manifest.get("files", {}):
        src = (install_dir / rel).resolve()
        try:
            src.relative_to(install_dir.resolve())
        except Exception:
            continue
        if not src.exists() or not src.is_file():
            continue
        dest = backup_root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        files_meta.append(
            {
                "path": rel,
                "size": src.stat().st_size,
                "sha256": _hash_file(src),
            }
        )
    meta = {
        "name": backup_root.name,
        "created_at": _now_iso(),
        "version": load_install_config().get("version") or CURRENT_VERSION,
        "files": files_meta,
        "manifest": {
            "version": manifest.get("version"),
            "release_date": manifest.get("release_date"),
            "files_count": len(manifest.get("files", {})),
        },
    }
    _write_json(backup_root / "backup_manifest.json", meta)
    _call_progress(on_progress, f"Yedek hazir: {backup_root.name}")
    return backup_root


def list_backups(backup_dir: Optional[os.PathLike[str] | str] = None) -> List[Dict[str, Any]]:
    root = Path(backup_dir) if backup_dir else get_backup_dir()
    backups: List[Dict[str, Any]] = []
    try:
        for folder in sorted(root.glob("update_backup_*"), reverse=True):
            if not folder.is_dir():
                continue
            meta = _read_json(folder / "backup_manifest.json")
            if not meta:
                meta = {
                    "name": folder.name,
                    "created_at": datetime.fromtimestamp(folder.stat().st_mtime).isoformat(),
                    "version": "?",
                    "files": [],
                }
            meta["name"] = folder.name
            backups.append(meta)
    except Exception:
        pass
    return backups


def apply_update(
    zip_path: os.PathLike[str] | str,
    install_dir: Optional[os.PathLike[str] | str] = None,
    backup_dir: Optional[os.PathLike[str] | str] = None,
    on_progress: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """Apply a validated ZIP update after backing up changed files."""

    ok, msg, manifest = validate_update_zip(zip_path)
    if not ok:
        return False, msg
    install = Path(install_dir) if install_dir else get_install_dir()
    backup = Path(backup_dir) if backup_dir else get_backup_dir()
    install.mkdir(parents=True, exist_ok=True)
    backup.mkdir(parents=True, exist_ok=True)
    install_resolved = install.resolve()
    try:
        backup_root = _backup_existing_files(install, backup, manifest, on_progress)
        with zipfile.ZipFile(zip_path, "r") as zf:
            for rel, info in manifest["files"].items():
                dest = (install / rel).resolve()
                try:
                    dest.relative_to(install_resolved)
                except Exception:
                    return False, f"Guvenlik nedeniyle atlandi: {rel}"
                data = zf.read(info["zip_name"])
                sha = hashlib.sha256(data).hexdigest()
                if info.get("sha256") and sha != info["sha256"]:
                    return False, f"Hash dogrulamasi basarisiz: {rel}"
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
                _call_progress(on_progress, f"Guncellendi: {rel}")
        cfg = load_install_config()
        old_version = cfg.get("version") or CURRENT_VERSION
        cfg["version"] = manifest.get("version") or CURRENT_VERSION
        cfg["updated_at"] = _now_iso()
        cfg.setdefault("update_history", [])
        cfg["update_history"].insert(
            0,
            {
                "applied_at": cfg["updated_at"],
                "from_version": old_version,
                "to_version": cfg["version"],
                "files_count": len(manifest["files"]),
                "changelog": manifest.get("changelog", ""),
                "backup": backup_root.name,
            },
        )
        cfg["update_history"] = cfg["update_history"][:50]
        save_install_config(cfg)
        _write_version_file(install, cfg)
        return True, f"Guncelleme tamamlandi: {old_version} -> {cfg['version']}"
    except Exception as ex:
        return False, f"Guncelleme uygulanamadi: {ex}"


def rollback_to_backup(
    backup_name: str,
    install_dir: Optional[os.PathLike[str] | str] = None,
    backup_dir: Optional[os.PathLike[str] | str] = None,
) -> Tuple[bool, str]:
    """Restore files from a previous update backup."""

    install = Path(install_dir) if install_dir else get_install_dir()
    backup = Path(backup_dir) if backup_dir else get_backup_dir()
    target = (backup / Path(backup_name).name).resolve()
    try:
        target.relative_to(backup.resolve())
    except Exception:
        return False, "Gecersiz yedek adi."
    meta = _read_json(target / "backup_manifest.json")
    if not target.exists() or not target.is_dir() or not meta:
        return False, "Yedek bulunamadi veya manifest eksik."
    try:
        current_backup = _backup_existing_files(
            install,
            backup,
            {"files": {item["path"]: {} for item in meta.get("files", [])}},
            None,
        )
        restored = 0
        install_resolved = install.resolve()
        for item in meta.get("files", []):
            rel = item.get("path")
            if not rel:
                continue
            src = target / rel
            dest = (install / rel).resolve()
            try:
                dest.relative_to(install_resolved)
            except Exception:
                continue
            if src.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                restored += 1
        cfg = load_install_config()
        cfg.setdefault("update_history", [])
        cfg["update_history"].insert(
            0,
            {
                "applied_at": _now_iso(),
                "rollback": True,
                "rolled_back_to": target.name,
                "safety_backup": current_backup.name,
                "files_count": restored,
            },
        )
        cfg["update_history"] = cfg["update_history"][:50]
        save_install_config(cfg)
        return True, f"Rollback tamamlandi: {restored} dosya geri alindi."
    except Exception as ex:
        return False, f"Rollback yapilamadi: {ex}"


def get_version_info(
    install_dir: Optional[os.PathLike[str] | str] = None,
) -> Dict[str, Any]:
    cfg = load_install_config()
    install = Path(install_dir) if install_dir else Path(str(cfg.get("install_dir")))
    version_data = _read_json(install / VERSION_FILE)
    info = {
        "current_version": cfg.get("version") or CURRENT_VERSION,
        "version": cfg.get("version") or CURRENT_VERSION,
        "install_dir": str(install),
        "config_path": str(_home_config_path()),
        "local_config_path": str(_local_config_path()),
        "updated_at": cfg.get("updated_at") or version_data.get("updated_at") or "",
        "update_history": cfg.get("update_history") or [],
        "files": {},
    }
    for name in (
        "yazklinik_web.py",
        "yazklinik_config.py",
        "yazklinik_common.py",
        "yazklinik_updater.py",
    ):
        path = install / name
        if path.exists():
            try:
                info["files"][name] = {
                    "size": path.stat().st_size,
                    "sha256": _hash_file(path),
                    "mtime": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                }
            except Exception:
                pass
    return info


def _print_status() -> int:
    cfg = load_install_config()
    print(json.dumps(get_version_info(cfg.get("install_dir")), ensure_ascii=False, indent=2))
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="YazKlinik updater helper")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status")
    setup_p = sub.add_parser("setup")
    setup_p.add_argument("--install-dir")
    setup_p.add_argument("--data-dir")
    setup_p.add_argument("--nas-dir")
    setup_p.add_argument("--clinic-name", default="YazKlinik")
    setup_p.add_argument("--doctor-name", default="Op. Dr. Hakan YAZ")
    update_p = sub.add_parser("update")
    update_p.add_argument("zip_path")
    rollback_p = sub.add_parser("rollback")
    rollback_p.add_argument("backup_name", nargs="?")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.cmd in (None, "status"):
        return _print_status()
    if args.cmd == "setup":
        ok, msg = run_setup(
            install_dir=args.install_dir,
            data_dir=args.data_dir,
            nas_dir=args.nas_dir,
            clinic_name=args.clinic_name,
            doctor_name=args.doctor_name,
        )
        print(msg)
        return 0 if ok else 1
    if args.cmd == "update":
        ok, msg = apply_update(args.zip_path, on_progress=print)
        print(msg)
        return 0 if ok else 1
    if args.cmd == "rollback":
        backups = list_backups()
        backup_name = args.backup_name or (backups[0]["name"] if backups else "")
        ok, msg = rollback_to_backup(backup_name)
        print(msg)
        return 0 if ok else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())






