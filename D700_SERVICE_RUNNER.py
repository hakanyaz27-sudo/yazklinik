"""Run a YazKlinik service without opening an extra console window.

Called by D700_BASLAT.bat through pythonw.exe:
    pythonw.exe D700_SERVICE_RUNNER.py service.py out.log err.log
"""
from __future__ import annotations

import os
import runpy
import site
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parent
LOCK_ROOT = ROOT / "runtime_state" / "service_locks"
_VENV_REEXEC_GUARD = "YAZKLINIK_RUNNER_VENV_ENFORCED"


def _hidden_subprocess_kwargs() -> dict:
    """Keep lock-inspection helper calls from opening Windows Terminal."""
    if os.name != "nt":
        return {}
    kwargs = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def _canonical(path: Path) -> Path:
    try:
        return path.resolve()
    except Exception:
        try:
            return Path(os.path.abspath(str(path)))
        except Exception:
            return path


def _project_venv_root() -> Path:
    return _canonical(ROOT / ".venv")


def _launched_via_project_venv_executable() -> bool:
    """Detect invocation through project .venv executable via orig_argv.

    On Windows redirector builds, ``sys.executable`` can point to base Python
    even when launch actually came from ``.venv\\Scripts\\python[w].exe``.
    """
    try:
        orig = list(getattr(sys, "orig_argv", []) or [])
    except Exception:
        orig = []
    if not orig:
        return False
    raw0 = str(orig[0] or "").strip()
    if not raw0:
        return False
    try:
        launched = str(_canonical(Path(raw0))).lower().replace("/", "\\")
    except Exception:
        launched = raw0.lower().replace("/", "\\")
    if "\\.venv\\scripts\\" in launched:
        return True
    try:
        markers = _project_venv_markers()
    except Exception:
        markers = ()
    return any(launched == marker for marker in markers)


def _current_executable_in_project_venv() -> bool:
    try:
        current = str(_canonical(Path(sys.executable))).lower().replace("/", "\\")
    except Exception:
        current = str(Path(sys.executable)).lower().replace("/", "\\")
    if "\\.venv\\scripts\\" in current:
        return True
    try:
        markers = _project_venv_markers()
    except Exception:
        markers = ()
    return any(current == marker for marker in markers)


def _current_venv_matches_project() -> bool:
    """Detect project venv reliably on Windows redirector Python builds.

    Python 3.12+ on Windows can run with `sys.executable` pointing to the base
    interpreter even when the active runtime context is the venv redirector.
    Therefore we primarily trust `sys.prefix` / `sys.exec_prefix`, then
    executable path markers. `VIRTUAL_ENV` alone is not enough because leaked
    environment variables can make global Python look like project venv.
    """
    project_venv = _project_venv_root()
    candidates = []
    for raw in (getattr(sys, "prefix", ""), getattr(sys, "exec_prefix", "")):
        text = str(raw or "").strip()
        if not text:
            continue
        try:
            candidates.append(_canonical(Path(text)))
        except Exception:
            continue
    if any(one == project_venv for one in candidates):
        return True
    if _current_executable_in_project_venv():
        return True
    if _launched_via_project_venv_executable():
        return True
    raw_virtual_env = str(os.environ.get("VIRTUAL_ENV", "") or "").strip()
    if raw_virtual_env:
        try:
            return (
                _canonical(Path(raw_virtual_env)) == project_venv
                and _current_executable_in_project_venv()
            )
        except Exception:
            return False
    return False


def _ensure_local_venv_runner() -> int | None:
    """Re-exec runner with project .venv Python when invoked via system Python.

    In D700 field setups, startup helpers can occasionally call
    D700_SERVICE_RUNNER.py with global Python, which then misses packages
    (waitress/psycopg/PyMuPDF) and destabilizes web boot. This guard makes the
    runner self-heal to the project virtualenv.
    """
    # D700 2026-05-27: keep re-exec opt-in. In real Windows sessions a
    # pythonw redirector can recursively mirror runner trees and delay
    # health/boot loops. Launcher already starts runner from project .venv.
    raw_force = str(os.environ.get("YAZKLINIK_RUNNER_FORCE_VENV_REEXEC", "0")).strip().lower()
    if raw_force not in {"1", "true", "yes", "on"}:
        return None

    if os.name != "nt":
        return None

    venv_scripts = ROOT / ".venv" / "Scripts"
    venv_py = venv_scripts / "python.exe"
    venv_pyw = venv_scripts / "pythonw.exe"
    if not venv_py.exists():
        return None

    if _current_venv_matches_project():
        return None

    if _launched_via_project_venv_executable():
        return None

    current_fold = str(Path(sys.executable)).lower().replace("/", "\\")
    if "\\.venv\\scripts\\" in current_fold:
        return None

    # Fail-closed policy: when not running inside project venv, never continue
    # service execution in system Python. This prevents twin runner trees.
    if os.environ.get(_VENV_REEXEC_GUARD) == "1":
        os._exit(0)

    target_exe = venv_pyw if venv_pyw.exists() else venv_py
    env = dict(os.environ)
    env[_VENV_REEXEC_GUARD] = "1"
    args = [str(target_exe), str(Path(__file__).resolve()), *sys.argv[1:]]
    try:
        subprocess.Popen(
            args,
            cwd=str(ROOT),
            env=env,
            **_hidden_subprocess_kwargs(),
        )
    except Exception:
        # Do not run with global interpreter when venv handoff fails.
        pass
    os._exit(0)


def _force_local_venv_packages() -> None:
    """Fallback: inject local .venv site-packages into sys.path."""
    try:
        venv_root = ROOT / ".venv"
        site_packages = venv_root / "Lib" / "site-packages"
        scripts_dir = venv_root / "Scripts"
        if site_packages.exists():
            site.addsitedir(str(site_packages))
            if str(site_packages) not in sys.path:
                sys.path.insert(0, str(site_packages))
        if scripts_dir.exists():
            os.environ["PATH"] = str(scripts_dir) + os.pathsep + os.environ.get("PATH", "")
        os.environ.setdefault("VIRTUAL_ENV", str(venv_root))
    except Exception:
        pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, int(pid))  # PROCESS_QUERY_LIMITED_INFORMATION
            if not handle:
                return False
            code = ctypes.c_ulong()
            try:
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return False
                return code.value == 259  # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


def _pid_command_line(pid: int) -> str:
    if pid <= 0 or os.name != "nt":
        return ""
    try:
        cmd = (
            "$p=Get-CimInstance Win32_Process -Filter "
            f"'ProcessId={int(pid)}' -ErrorAction SilentlyContinue; "
            "if($p){$p.CommandLine}"
        )
        return subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
            **_hidden_subprocess_kwargs(),
        ).strip()
    except Exception:
        return ""


def _pid_parent_id(pid: int) -> int:
    if pid <= 0 or os.name != "nt":
        return 0
    try:
        cmd = (
            "$p=Get-CimInstance Win32_Process -Filter "
            f"'ProcessId={int(pid)}' -ErrorAction SilentlyContinue; "
            "if($p){$p.ParentProcessId}"
        )
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
            **_hidden_subprocess_kwargs(),
        ).strip()
        return int(raw or "0")
    except Exception:
        return 0


def _project_venv_markers() -> tuple[str, ...]:
    scripts_dir = _canonical(ROOT / ".venv" / "Scripts")
    return (
        str((scripts_dir / "pythonw.exe")).lower(),
        str((scripts_dir / "python.exe")).lower(),
    )


def _current_is_project_venv() -> bool:
    if _current_venv_matches_project():
        return True
    try:
        current = str(_canonical(Path(sys.executable))).lower()
    except Exception:
        current = str(Path(sys.executable)).lower()
    return any(current == marker for marker in _project_venv_markers())


def _pid_is_project_venv(pid: int) -> bool:
    cmd = _pid_command_line(pid).lower()
    if not cmd:
        return False
    if any(marker in cmd for marker in _project_venv_markers()):
        return True
    if "D700_service_runner.py" in cmd:
        parent_pid = _pid_parent_id(pid)
        if parent_pid > 0:
            parent_cmd = _pid_command_line(parent_pid).lower()
            if any(marker in parent_cmd for marker in _project_venv_markers()):
                return True
    return False


def _allow_lock_takeover() -> bool:
    """Keep lock ownership conservative by default.

    Aggressive lock takeovers can kill healthy child workers in the
    pythonw.exe(parent)->python.exe(child) chain used on some Windows setups.
    Enable only when explicitly requested.
    """
    raw = str(os.environ.get("YAZKLINIK_LOCK_TAKEOVER", "")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _should_force_takeover(pid: int) -> bool:
    """Take over only when explicitly enabled and ownership is clearly foreign."""
    if not _allow_lock_takeover():
        return False
    if os.name != "nt" or pid <= 0 or not _current_is_project_venv():
        return False
    if _pid_is_project_venv(pid):
        return False
    cmd = _pid_command_line(pid).lower()
    if not cmd:
        return False
    if str(ROOT).lower() in cmd and "D700_service_runner.py" in cmd:
        return False
    return True


def _stop_pid_tree(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            **_hidden_subprocess_kwargs(),
        )
    except Exception:
        return False
    time.sleep(0.2)
    return not _pid_alive(pid)


def _lock_owner_matches_script(pid: int, script: Path, owner_script: str = "") -> bool:
    """Return true only when the lock PID still belongs to this script."""
    if not _pid_alive(pid):
        return False
    expected = str(script.resolve()).lower()
    if owner_script:
        try:
            return str(Path(owner_script).resolve()).lower() == expected
        except Exception:
            return owner_script.strip().lower() == expected
    cmd = _pid_command_line(pid).lower()
    if not cmd:
        # If the lock did not store an owner script and Windows hides the
        # command line, do not treat the PID as a valid owner. This prevents an
        # old/protected process from blocking a clean D700 restart forever.
        return False
    return script.name.lower() in cmd or expected in cmd


def _acquire_service_lock(script: Path) -> Path | None:
    """Keep one hidden runner per service script.

    D700_BASLAT can be double-clicked or a health monitor can race startup.
    The atomic lock prevents duplicate SIP/TTS/ASR workers from talking at once.
    """
    LOCK_ROOT.mkdir(parents=True, exist_ok=True)
    safe_name = script.stem.replace(" ", "_")
    lock_path = LOCK_ROOT / f"{safe_name}.lock"
    pid_text = f"{os.getpid()}\n{script.resolve()}\n"
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="ascii") as fh:
                fh.write(pid_text)
            return lock_path
        except FileExistsError:
            lock_age_sec = 0.0
            try:
                lock_age_sec = max(0.0, time.time() - float(lock_path.stat().st_mtime))
            except Exception:
                lock_age_sec = 0.0
            try:
                lock_lines = (
                    lock_path.read_text(encoding="ascii", errors="ignore")
                    .splitlines()
                )
                old_pid = int((lock_lines[0] if lock_lines else "0").strip() or "0")
                old_script = lock_lines[1].strip() if len(lock_lines) > 1 else ""
            except Exception:
                old_pid = 0
                old_script = ""
            # Race fix: a sibling runner may create the lock file milliseconds
            # before it writes PID/script lines. Never delete a very fresh lock
            # with incomplete content; wait and retry.
            if old_pid <= 0 and lock_age_sec < 5.0:
                time.sleep(0.2)
                continue
            if _lock_owner_matches_script(old_pid, script, old_script):
                # If a stale/global Python owner holds the lock, allow the
                # project-venv runner to take over deterministically.
                if (
                    _should_force_takeover(old_pid)
                    and _stop_pid_tree(old_pid)
                ):
                    try:
                        lock_path.unlink()
                        continue
                    except Exception:
                        return None
                return None
            # If owner PID is alive but ownership probe is inconclusive, keep a
            # fresh lock instead of stealing it. This blocks twin service boots.
            if old_pid > 0 and _pid_alive(old_pid):
                if lock_age_sec < 5.0:
                    time.sleep(0.2)
                    continue
                return None
            removed = False
            for _ in range(3):
                try:
                    lock_path.unlink()
                    removed = True
                    break
                except FileNotFoundError:
                    removed = True
                    break
                except PermissionError:
                    time.sleep(0.15)
                except Exception:
                    break
            if removed:
                continue
            return None


def _load_config_env() -> None:
    path = ROOT / "config.env"
    if not path.exists():
        return
    try:
        for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key:
                os.environ[key] = value.strip()
    except Exception:
        pass
    try:
        from yazklinik_support_paths import apply_support_paths

        apply_support_paths()
    except Exception:
        pass


def _safe_int(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return int(default)


def _apply_web_waitress_floor(script: Path) -> None:
    """Force a minimum waitress thread count for web service startup."""
    try:
        if script.name.lower() != "yazklinik_web.py":
            return
        floor = _safe_int(os.environ.get("YAZKLINIK_WAITRESS_THREADS_FLOOR", "12"), 12)
        current = _safe_int(os.environ.get("YAZKLINIK_WAITRESS_THREADS", "0"), 0)
        if current < floor:
            os.environ["YAZKLINIK_WAITRESS_THREADS"] = str(floor)
    except Exception:
        pass


def _apply_web_launch_guard_bypass(script: Path) -> None:
    """Allow controlled web launches via D700 service runner."""
    try:
        if script.name.lower() != "yazklinik_web.py":
            return
        if not str(os.environ.get("YAZKLINIK_ALLOW_DIRECT_WEB", "")).strip():
            os.environ["YAZKLINIK_ALLOW_DIRECT_WEB"] = "manual-dev-ok"
    except Exception:
        pass


def _child_python_executable() -> str:
    """Prefer the project venv launcher for supervised child services."""
    scripts_dir = _project_venv_root() / "Scripts"
    candidate = scripts_dir / ("python.exe" if os.name == "nt" else "python")
    if candidate.exists():
        return str(candidate)
    return sys.executable


def _run_as_supervised_child(script: Path) -> bool:
    """Run the huge web app in a fresh child so silent exits can be restarted."""
    if script.name.lower() != "yazklinik_web.py":
        return False
    # D700 2026-05-27: child-supervise modu sahada orphan/cift-runner dalgasi
    # uretebiliyor. Yanlis/kalinti env ile acilmamasi icin cift onay ister:
    # FORCE + ALLOW birlikte verilmedikce mode KAPALI kalir.
    raw_force = str(
        os.environ.get("YAZKLINIK_RUNNER_WEB_CHILD_FORCE", "")
    ).strip().lower()
    raw_allow = str(
        os.environ.get("YAZKLINIK_RUNNER_WEB_CHILD_ALLOW", "")
    ).strip().lower()
    force_on = raw_force in {"1", "true", "yes", "on", "force-web-child", "evet", "aktif"}
    allow_on = raw_allow in {"1", "true", "yes", "on", "allow-web-child", "evet", "aktif"}
    return bool(force_on and allow_on)


def _tcp_port_accepts(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", int(port)), timeout=1.0):
            return True
    except Exception:
        return False


def _supervise_child(script: Path, out, err) -> int:
    """Restart long-running child services if they return unexpectedly."""
    restart_delay = max(
        2,
        _safe_int(os.environ.get("YAZKLINIK_RUNNER_WEB_RESTART_DELAY_SEC", "8"), 8),
    )
    max_restarts = max(
        0,
        _safe_int(os.environ.get("YAZKLINIK_RUNNER_WEB_MAX_RESTARTS", "0"), 0),
    )
    web_port = _safe_int(os.environ.get("YAZKLINIK_WEB_PORT", "5052"), 5052)
    attempt = 0
    last_rc = 0
    while True:
        attempt += 1
        cmd = [_child_python_executable(), str(script)] + sys.argv[4:]
        print(
            f"[D700-RUNNER] child start {script} attempt={attempt}",
            flush=True,
        )
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=str(ROOT),
                env=os.environ.copy(),
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                **_hidden_subprocess_kwargs(),
            )
            last_rc = int(proc.wait())
        except Exception:
            last_rc = 1
            traceback.print_exc(file=err)
            err.flush()
        print(
            f"[D700-RUNNER] child exit {script} rc={last_rc} attempt={attempt}",
            flush=True,
        )
        if _tcp_port_accepts(web_port):
            print(
                f"[D700-RUNNER] child restart atlandi: port {web_port} zaten acik",
                flush=True,
            )
            return 0
        if max_restarts and attempt >= max_restarts:
            print(
                f"[D700-RUNNER] child restart limiti doldu: {max_restarts}",
                flush=True,
            )
            return last_rc
        time.sleep(restart_delay)


def main() -> int:
    reexec_code = _ensure_local_venv_runner()
    if reexec_code is not None:
        return int(reexec_code)
    if len(sys.argv) < 4:
        return 2
    _force_local_venv_packages()
    script = Path(sys.argv[1])
    if not script.is_absolute():
        script = ROOT / script
    out_log = Path(sys.argv[2])
    err_log = Path(sys.argv[3])
    lock_path = _acquire_service_lock(script.resolve())
    if lock_path is None:
        return 0
    out_log.parent.mkdir(parents=True, exist_ok=True)
    err_log.parent.mkdir(parents=True, exist_ok=True)
    os.chdir(ROOT)
    _load_config_env()
    _apply_web_waitress_floor(script.resolve())
    _apply_web_launch_guard_bypass(script.resolve())
    os.environ["YAZKLINIK_D700_SERVICE_RUNNER"] = "1"
    os.environ["YAZKLINIK_D700_SERVICE_SCRIPT"] = str(script.resolve())
    with out_log.open("a", encoding="utf-8", buffering=1) as out, err_log.open(
        "a", encoding="utf-8", buffering=1
    ) as err:
        sys.stdout = out
        sys.stderr = err
        print(f"[D700-RUNNER] start {script}", flush=True)
        if _run_as_supervised_child(script):
            return _supervise_child(script, out, err)
        old_argv = sys.argv[:]
        try:
            sys.argv = [str(script)] + old_argv[4:]
            runpy.run_path(str(script), run_name="__main__")
        except SystemExit:
            raise
        except BaseException:
            traceback.print_exc(file=err)
            err.flush()
            raise
        finally:
            sys.argv = old_argv
            try:
                lock_lines = lock_path.read_text(
                    encoding="ascii", errors="ignore"
                ).splitlines()
                owner_pid = lock_lines[0].strip() if lock_lines else ""
                if lock_path.exists() and owner_pid == str(os.getpid()):
                    lock_path.unlink()
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

