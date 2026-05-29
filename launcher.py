"""
ECHO Orchestrator — Unified Desktop Launcher

================================================================================
DEPRECATED — nicht für den Alltag / Enterprise-Betrieb verwenden.
Empfohlener Start: start_desktop.cmd (PySide6, ein Prozess, kein HTTP).
Siehe SECURITY_RUNTIME.md.
================================================================================

Startet FastAPI (:8020) und Gradio Control UI (:7860) als Subprozesse.
Dünner Orchestrator — keine Business-Logik.

Verwendung (Legacy / Debug):
    python launcher.py
    python launcher.py --dry-run
    python launcher.py --no-browser
"""

from __future__ import annotations

import argparse
import atexit
import ctypes
import json
import os
import re
import signal
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.error import URLError
from urllib.request import urlopen

LAUNCHER_VERSION = "1.1.0"

BACKEND_PORT = 8020
UI_PORT = 7860
BACKEND_URL = f"http://127.0.0.1:{BACKEND_PORT}"
UI_URL = f"http://127.0.0.1:{UI_PORT}"

DEFAULT_HEALTH_TIMEOUT = float(os.environ.get("ECHO_HEALTH_TIMEOUT", "120"))
DEFAULT_HEALTH_INTERVAL = float(os.environ.get("ECHO_HEALTH_INTERVAL", "0.5"))

_children: list[subprocess.Popen] = []
_child_names: dict[int, str] = {}
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
_shutting_down = False
_console_handler_ref = None
_launcher_log: "LauncherLog | None" = None
_state_path: Path | None = None
_lock_path: Path | None = None
_session_start: float = 0.0
_started_backend = False
_started_ui = False


class LauncherLog:
    """Append-only launcher log with session headers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                f"\n--- launcher session {stamp} "
                f"v{LAUNCHER_VERSION} pid={os.getpid()} ---\n"
            )

    def write(self, level: str, msg: str, **fields: Any) -> None:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        extra = ""
        if fields:
            extra = " " + json.dumps(fields, ensure_ascii=False)
        line = f"{ts} [{level}] {msg}{extra}\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line)
        print(msg, flush=True)


def _log(msg: str, level: str = "INFO", **fields: Any) -> None:
    if _launcher_log is not None:
        _launcher_log.write(level, msg, **fields)
    else:
        print(msg, flush=True)


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def _read_project_root_file(path: Path) -> Path | None:
    if not path.is_file():
        return None
    line = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    if not line:
        return None
    root = Path(line).expanduser().resolve()
    if _looks_like_project(root):
        return root
    raise SystemExit(f"{path.name} ungültig (main.py/control_ui.py fehlen): {root}")


def resolve_project_root() -> Path:
    env_root = os.environ.get("ECHO_PROJECT_ROOT")
    if env_root:
        root = Path(env_root).expanduser().resolve()
        if _looks_like_project(root):
            return root
        raise SystemExit(f"ECHO_PROJECT_ROOT ungültig: {root}")

    sidecar = Path(sys.executable).resolve().parent / "echo_project_root.txt"
    from_sidecar = _read_project_root_file(sidecar)
    if from_sidecar is not None:
        return from_sidecar

    if not _is_frozen():
        root = Path(__file__).resolve().parent
        if _looks_like_project(root):
            return root
        raise SystemExit(f"Projektverzeichnis nicht erkannt: {root}")

    exe_dir = Path(sys.executable).resolve().parent
    for candidate in [exe_dir, *exe_dir.parents]:
        if _looks_like_project(candidate):
            return candidate.resolve()

    raise SystemExit(
        "Projektverzeichnis nicht gefunden.\n"
        "Setze ECHO_PROJECT_ROOT, lege echo_project_root.txt neben die EXE,\n"
        "oder starte die EXE aus dist/ im Projektordner."
    )


def _looks_like_project(root: Path) -> bool:
    return (root / "main.py").is_file() and (root / "control_ui.py").is_file()


def venv_python(project_root: Path) -> Path:
    python = project_root / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        raise SystemExit(
            f"Python venv fehlt: {python}\n"
            f"Im Projekt ausführen: cd {project_root} && uv sync"
        )
    return python


def is_port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def check_echo_backend() -> bool:
    try:
        with urlopen(f"{BACKEND_URL}/health", timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload.get("status") == "ok" and "version" in payload
    except (URLError, OSError, ValueError, json.JSONDecodeError):
        return False


def check_gradio_ui() -> bool:
    try:
        with urlopen(UI_URL, timeout=2) as response:
            if not (200 <= response.status < 400):
                return False
            body = response.read(16384).decode("utf-8", errors="replace").lower()
            return "gradio" in body
    except (URLError, OSError):
        return False


def _process_commandline(pid: int) -> str:
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                [
                    "wmic",
                    "process",
                    "where",
                    f"processid={pid}",
                    "get",
                    "commandline",
                    "/format:list",
                ],
                capture_output=True,
                text=True,
                timeout=8,
                creationflags=CREATE_NO_WINDOW,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    if line.lower().startswith("commandline="):
                        return line.split("=", 1)[1].strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        return ""
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
        return raw.decode("utf-8", errors="replace").replace("\x00", " ")
    except OSError:
        return ""


def is_echo_backend_pid(pid: int, project_root: Path) -> bool:
    cmd = _process_commandline(pid).lower()
    return "uvicorn" in cmd and "main:app" in cmd


def is_echo_ui_pid(pid: int, project_root: Path) -> bool:
    cmd = _process_commandline(pid).lower()
    return "control_ui.py" in cmd


def is_pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    if sys.platform == "win32":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid
        )
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def get_listening_pid(port: int) -> int | None:
    """PID des Prozesses, der auf port lauscht (Windows: netstat -ano)."""
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        needle = f":{port}"
        for line in result.stdout.splitlines():
            upper = line.upper()
            if "LISTENING" not in upper or needle not in line:
                continue
            parts = line.split()
            if not parts:
                continue
            try:
                return int(parts[-1])
            except ValueError:
                continue
        return None

    try:
        result = subprocess.run(
            ["ss", "-ltnp"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        pattern = re.compile(rf":{port}\b.*pid=(\d+)")
        for line in result.stdout.splitlines():
            match = pattern.search(line)
            if match:
                return int(match.group(1))
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def load_state(state_path: Path) -> dict[str, Any] | None:
    if not state_path.is_file():
        return None
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_state(state_path: Path, payload: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def clear_state(state_path: Path, reason: str) -> None:
    if state_path.is_file():
        _log("State-Datei gelöscht.", shutdown_reason=reason)
        try:
            state_path.unlink()
        except OSError as exc:
            _log(f"State-Datei konnte nicht gelöscht werden: {exc}", level="WARN")


def acquire_launcher_lock(lock_path: Path) -> bool:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.is_file():
        try:
            data = json.loads(lock_path.read_text(encoding="utf-8"))
            old_pid = int(data.get("launcher_pid", 0))
            if is_pid_alive(old_pid):
                _log(
                    f"Ein anderer Launcher läuft bereits (PID {old_pid}). "
                    "Bitte zuerst beenden oder logs/launcher/.launcher.lock prüfen.",
                    level="ERROR",
                )
                return False
            _log(
                f"Verwaiste Lock-Datei (PID {old_pid} tot) — wird ersetzt.",
                level="WARN",
                stale_lock_pid=old_pid,
            )
        except (OSError, ValueError, json.JSONDecodeError):
            _log("Ungültige Lock-Datei — wird ersetzt.", level="WARN")
        try:
            lock_path.unlink()
        except OSError:
            pass

    payload = {
        "launcher_pid": os.getpid(),
        "started": datetime.now(timezone.utc).isoformat(),
        "launcher_version": LAUNCHER_VERSION,
    }
    lock_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return True


def release_launcher_lock(lock_path: Path | None) -> None:
    if lock_path is None or not lock_path.is_file():
        return
    try:
        data = json.loads(lock_path.read_text(encoding="utf-8"))
        if int(data.get("launcher_pid", -1)) == os.getpid():
            lock_path.unlink()
    except (OSError, ValueError, json.JSONDecodeError):
        pass


def _prepare_service_log(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n--- service session {stamp} ---\n")


def spawn_service(
    *,
    name: str,
    cmd: list[str],
    cwd: Path,
    log_path: Path,
) -> subprocess.Popen:
    _prepare_service_log(log_path)
    log_handle = log_path.open("a", encoding="utf-8", buffering=1)
    flags = CREATE_NO_WINDOW
    if sys.platform == "win32":
        flags |= subprocess.CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd),
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        creationflags=flags,
    )
    proc.echo_log_handle = log_handle  # type: ignore[attr-defined]
    proc.echo_service_name = name  # type: ignore[attr-defined]
    _log(f"[{name}] gestartet (PID {proc.pid})", service=name, pid=proc.pid, log=str(log_path))
    _children.append(proc)
    _child_names[proc.pid] = name
    return proc


def wait_for(
    condition: Callable[[], bool],
    label: str,
    timeout: float = DEFAULT_HEALTH_TIMEOUT,
    interval: float = DEFAULT_HEALTH_INTERVAL,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            elapsed = time.monotonic() - _session_start
            _log(f"{label} bereit.", startup_duration_s=round(elapsed, 2))
            return True
        time.sleep(interval)
    _log(
        f"Timeout: {label} nicht bereit nach {timeout:.0f}s. "
        "Bei langsamen Systemen ECHO_HEALTH_TIMEOUT erhöhen (z. B. 180).",
        level="ERROR",
        timeout_s=timeout,
    )
    return False


def _terminate_pid(pid: int, label: str) -> None:
    if not is_pid_alive(pid):
        return
    _log(f"Beende verwaisten {label} (PID {pid}) …", shutdown_reason="orphan_cleanup")
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
        )
    else:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            if is_pid_alive(pid):
                os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _cleanup_orphan_from_state(
    state: dict[str, Any],
    *,
    service_key: str,
    health_check: Callable[[], bool],
) -> dict[str, Any]:
    """Beendet State-PID wenn Health fehlschlägt; bereinigt State."""
    pid = state.get(f"{service_key}_pid")
    if not pid:
        return state
    pid = int(pid)
    if health_check():
        return state
    if is_pid_alive(pid):
        _log(
            f"ECHO-{service_key} PID {pid} antwortet nicht auf Health — wird beendet.",
            level="WARN",
            orphan_pid=pid,
        )
        _terminate_pid(pid, service_key)
    state = dict(state)
    state.pop(f"{service_key}_pid", None)
    return state


def terminate_children(reason: str = "shutdown") -> None:
    global _shutting_down
    if _shutting_down:
        return
    _shutting_down = True
    _log("Beende Kindprozesse …", shutdown_reason=reason)

    for proc in reversed(_children):
        if proc.poll() is not None:
            continue
        name = _child_names.get(proc.pid, "service")
        _log(f"Beende {name} (PID {proc.pid}) …", shutdown_reason=reason)
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                capture_output=True,
                check=False,
            )
        else:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    for proc in _children:
        handle = getattr(proc, "echo_log_handle", None)
        if handle and not handle.closed:
            handle.close()

    _children.clear()
    _child_names.clear()


def _maybe_clear_state(state_path: Path | None, reason: str) -> None:
    if state_path is None:
        return
    if _started_backend or _started_ui:
        clear_state(state_path, reason)


def _register_shutdown_handlers(state_path: Path | None, lock_path: Path | None) -> None:
    def _handler(signum=None, frame=None) -> None:  # noqa: ARG001
        reason = "signal" if signum is not None else "console"
        _log("\nShutdown — stoppe Dienste …", shutdown_reason=reason)
        terminate_children(reason=reason)
        _maybe_clear_state(state_path, reason)
        release_launcher_lock(lock_path)
        sys.exit(0)

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)
    if sys.platform == "win32":
        signal.signal(signal.SIGBREAK, _handler)
        try:
            handler_type = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_uint)

            @handler_type
            def _console_handler(event: int) -> bool:
                if event in (0, 2, 5, 6):
                    _handler()
                    return True
                return False

            global _console_handler_ref
            _console_handler_ref = _console_handler
            ctypes.windll.kernel32.SetConsoleCtrlHandler(_console_handler_ref, True)
        except OSError:
            pass

    def _atexit() -> None:
        terminate_children(reason="atexit")
        _maybe_clear_state(state_path, "atexit")
        release_launcher_lock(lock_path)

    atexit.register(_atexit)


def _state_matches_project(state: dict[str, Any], project_root: Path) -> bool:
    stored = state.get("project_root")
    if not stored:
        return False
    try:
        return Path(stored).resolve() == project_root.resolve()
    except OSError:
        return False


def classify_port(
    port: int,
    *,
    project_root: Path,
    health_check: Callable[[], bool],
    state: dict[str, Any] | None,
    service_key: str,
) -> tuple[str, int | None]:
    """
    Returns (status, owner_pid):
      free — port offen
      echo — ECHO-Dienst erreichbar (Health)
      echo_stale — Port offen, State-PID tot
      foreign — fremder Prozess
    """
    owner_pid = get_listening_pid(port)
    if health_check():
        if owner_pid and state:
            stored_pid = state.get(f"{service_key}_pid")
            if stored_pid and int(stored_pid) == owner_pid:
                _log(
                    f"Port {port}: ECHO-{service_key} wiederverwendet (PID {owner_pid}).",
                    port_reuse="state+health",
                    pid=owner_pid,
                )
            else:
                _log(
                    f"Port {port}: ECHO-{service_key} erkannt (Health), PID {owner_pid}.",
                    port_reuse="health",
                    pid=owner_pid,
                )
        return "echo", owner_pid

    if not is_port_open("127.0.0.1", port):
        return "free", None

    if state and _state_matches_project(state, project_root):
        stored_pid = state.get(f"{service_key}_pid")
        if stored_pid and is_pid_alive(int(stored_pid)):
            spid = int(stored_pid)
            verify = (
                is_echo_backend_pid(spid, project_root)
                if service_key == "backend"
                else is_echo_ui_pid(spid, project_root)
            )
            if not verify:
                return "foreign", owner_pid or spid
            if owner_pid and spid != owner_pid:
                return "foreign", owner_pid
            return "echo_stale", owner_pid or spid

    return "foreign", owner_pid


def inspect_ports(project_root: Path, state: dict[str, Any] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for port, key, checker in (
        (BACKEND_PORT, "backend", check_echo_backend),
        (UI_PORT, "ui", check_gradio_ui),
    ):
        status, owner = classify_port(
            port,
            project_root=project_root,
            health_check=checker,
            state=state,
            service_key=key,
        )
        if status == "echo_stale":
            _log(
                f"Port {port}: Prozess lauscht, Health fehlgeschlagen — "
                f"vermutlich kein ECHO (PID {owner}).",
                level="WARN",
                port=port,
                pid=owner,
            )
            result[str(port)] = "foreign"
        else:
            result[str(port)] = status
    return result


def _describe_foreign_process(port: int, owner_pid: int | None) -> str:
    detail = f"PID {owner_pid}" if owner_pid else "PID unbekannt"
    if owner_pid and sys.platform == "win32":
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {owner_pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
                check=False,
            )
            line = result.stdout.strip().splitlines()
            if line:
                detail = line[0]
        except (OSError, subprocess.TimeoutExpired):
            pass
    return detail


def run_launcher(
    *,
    dry_run: bool = False,
    open_browser: bool = True,
    health_timeout: float = DEFAULT_HEALTH_TIMEOUT,
    health_interval: float = DEFAULT_HEALTH_INTERVAL,
) -> int:
    global _launcher_log, _state_path, _lock_path, _session_start
    global _started_backend, _started_ui, _shutting_down

    _started_backend = False
    _started_ui = False
    _shutting_down = False
    _session_start = time.monotonic()
    project_root = resolve_project_root()
    python = venv_python(project_root)

    logs_launcher = project_root / "logs" / "launcher"
    logs_backend = project_root / "logs" / "backend"
    logs_ui = project_root / "logs" / "ui"
    launcher_log_path = logs_launcher / "launcher.log"
    backend_log = logs_backend / "backend.log"
    ui_log = logs_ui / "ui.log"
    state_path = logs_launcher / "launcher_state.json"
    lock_path = logs_launcher / ".launcher.lock"

    _launcher_log = LauncherLog(launcher_log_path)
    _state_path = state_path
    _lock_path = lock_path

    if not dry_run and not acquire_launcher_lock(lock_path):
        return 1

    prior_state = load_state(state_path)
    if prior_state and not _state_matches_project(prior_state, project_root):
        _log(
            "State-Datei gehört zu anderem Projekt — wird ignoriert.",
            level="WARN",
            stored_root=prior_state.get("project_root"),
        )
        prior_state = None

    # Clean stale / unhealthy PIDs from prior session
    if prior_state:
        for key, checker in (
            ("backend", check_echo_backend),
            ("ui", check_gradio_ui),
        ):
            pid = prior_state.get(f"{key}_pid")
            if pid and not is_pid_alive(int(pid)):
                _log(f"State: {key}_pid={pid} nicht mehr aktiv.", level="WARN", stale_pid=pid)
        prior_state = _cleanup_orphan_from_state(
            prior_state, service_key="backend", health_check=check_echo_backend
        )
        prior_state = _cleanup_orphan_from_state(
            prior_state, service_key="ui", health_check=check_gradio_ui
        )
        if not prior_state.get("backend_pid") and not prior_state.get("ui_pid"):
            clear_state(state_path, "empty_after_cleanup")
            prior_state = None

    ports = inspect_ports(project_root, prior_state)
    _log(f"Projekt: {project_root}")
    _log(f"Python:  {python}")
    _log(f"Launcher v{LAUNCHER_VERSION}")
    _log(f"Ports:   backend={ports[str(BACKEND_PORT)]}, ui={ports[str(UI_PORT)]}")

    if ports[str(BACKEND_PORT)] == "foreign":
        owner = get_listening_pid(BACKEND_PORT)
        detail = _describe_foreign_process(BACKEND_PORT, owner)
        _log(
            f"FEHLER: Port {BACKEND_PORT} ist belegt von einem fremden Prozess ({detail}).\n"
            "Kein ECHO-Backend unter /health erreichbar. Prozess beenden oder Port freigeben.",
            level="ERROR",
        )
        release_launcher_lock(lock_path)
        return 1

    if ports[str(UI_PORT)] == "foreign":
        owner = get_listening_pid(UI_PORT)
        detail = _describe_foreign_process(UI_PORT, owner)
        _log(
            f"FEHLER: Port {UI_PORT} ist belegt von einem fremden Prozess ({detail}).\n"
            "Keine ECHO Control UI (Gradio) erreichbar. Prozess beenden oder Port freigeben.",
            level="ERROR",
        )
        release_launcher_lock(lock_path)
        return 1

    start_backend = ports[str(BACKEND_PORT)] != "echo"
    start_ui = ports[str(UI_PORT)] != "echo"

    if dry_run:
        _log("Dry-run — kein Start.")
        _log(f"  Backend starten: {start_backend}")
        _log(f"  UI starten:      {start_ui}")
        will_open = open_browser and (
            ports[str(BACKEND_PORT)] == "echo" or start_backend
        ) and (ports[str(UI_PORT)] == "echo" or start_ui)
        _log(f"  Browser öffnen:  {will_open} (nur nach Health-Check)")
        release_launcher_lock(lock_path)
        return 0

    _register_shutdown_handlers(state_path, lock_path)

    backend_proc: subprocess.Popen | None = None
    ui_proc: subprocess.Popen | None = None

    def _wait(cond: Callable[[], bool], label: str) -> bool:
        return wait_for(cond, label, timeout=health_timeout, interval=health_interval)

    if start_backend:
        _started_backend = True
        backend_proc = spawn_service(
            name="backend",
            cmd=[
                str(python),
                "-m",
                "uvicorn",
                "main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(BACKEND_PORT),
            ],
            cwd=project_root,
            log_path=backend_log,
        )
        if not _wait(check_echo_backend, "Backend /health"):
            terminate_children(reason="backend_health_timeout")
            clear_state(state_path, "backend_health_timeout")
            release_launcher_lock(lock_path)
            return 1
    else:
        _log(f"Backend läuft bereits auf {BACKEND_URL} — wiederverwendet.", port_reuse=True)

    if start_ui:
        _started_ui = True
        ui_proc = spawn_service(
            name="ui",
            cmd=[str(python), "control_ui.py", "--port", str(UI_PORT)],
            cwd=project_root,
            log_path=ui_log,
        )
        if not _wait(check_gradio_ui, "Gradio UI"):
            terminate_children(reason="ui_health_timeout")
            clear_state(state_path, "ui_health_timeout")
            release_launcher_lock(lock_path)
            return 1
    else:
        _log(f"Control UI läuft bereits auf {UI_URL} — wiederverwendet.", port_reuse=True)

    if not check_echo_backend() or not check_gradio_ui():
        _log(
            "FEHLER: Health-Check vor Browser-Öffnung fehlgeschlagen.",
            level="ERROR",
        )
        terminate_children(reason="pre_browser_health_failed")
        clear_state(state_path, "pre_browser_health_failed")
        release_launcher_lock(lock_path)
        return 1

    state_payload: dict[str, Any] = {
        "launcher_version": LAUNCHER_VERSION,
        "project_root": str(project_root.resolve()),
        "start_time": datetime.now(timezone.utc).isoformat(),
        "backend_port": BACKEND_PORT,
        "ui_port": UI_PORT,
        "backend_pid": (
            backend_proc.pid
            if backend_proc
            else (prior_state or {}).get("backend_pid")
            or get_listening_pid(BACKEND_PORT)
        ),
        "ui_pid": (
            ui_proc.pid
            if ui_proc
            else (prior_state or {}).get("ui_pid") or get_listening_pid(UI_PORT)
        ),
    }
    save_state(state_path, state_payload)
    _log("launcher_state.json geschrieben.", state_file=str(state_path))

    if open_browser:
        _log(f"Öffne Browser: {UI_URL}")
        try:
            webbrowser.open(UI_URL)
        except Exception as exc:  # noqa: BLE001 — Browser-Fehler nicht fatal
            _log(f"Browser konnte nicht geöffnet werden: {exc}", level="WARN")

    elapsed = time.monotonic() - _session_start
    _log("")
    _log("ECHO Orchestrator läuft.", startup_duration_s=round(elapsed, 2))
    _log(f"  API : {BACKEND_URL}")
    _log(f"  UI  : {UI_URL}")
    _log(f"  Logs: {launcher_log_path}")
    _log(f"        {backend_log}")
    _log(f"        {ui_log}")
    _log("Beenden: Ctrl+C oder Fenster schließen.")

    health_tick = 0
    try:
        while True:
            for proc in list(_children):
                rc = proc.poll()
                if rc is None:
                    continue
                name = getattr(proc, "echo_service_name", None) or _child_names.get(
                    proc.pid, "service"
                )
                if name == "backend":
                    _log(
                        "ECHO-Backend ist abgestürzt oder wurde beendet "
                        f"(Exit-Code {rc}).\n"
                        f"Details: {backend_log}\n"
                        "Launcher wird beendet.",
                        level="ERROR",
                        crash_reason="backend_exit",
                        exit_code=rc,
                    )
                else:
                    _log(
                        "ECHO Control UI ist abgestürzt oder wurde beendet "
                        f"(Exit-Code {rc}).\n"
                        f"Details: {ui_log}\n"
                        "Launcher wird beendet.",
                        level="ERROR",
                        crash_reason="ui_exit",
                        exit_code=rc,
                    )
                terminate_children(reason=f"{name}_crash")
                clear_state(state_path, f"{name}_crash")
                release_launcher_lock(lock_path)
                return rc if rc else 1

            health_tick += 1
            if health_tick % 4 == 0:
                if not check_echo_backend():
                    _log(
                        "ECHO-Backend antwortet nicht mehr (/health). Launcher beendet.",
                        level="ERROR",
                        crash_reason="backend_unreachable",
                    )
                    release_launcher_lock(lock_path)
                    return 1
                if not check_gradio_ui():
                    _log(
                        "ECHO Control UI antwortet nicht mehr. Launcher beendet.",
                        level="ERROR",
                        crash_reason="ui_unreachable",
                    )
                    release_launcher_lock(lock_path)
                    return 1

            time.sleep(0.5)
    except KeyboardInterrupt:
        _log("\nCtrl+C — stoppe Dienste …", shutdown_reason="keyboard_interrupt")
        terminate_children(reason="keyboard_interrupt")
        _maybe_clear_state(state_path, "keyboard_interrupt")
        release_launcher_lock(lock_path)
        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="ECHO Orchestrator Launcher")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Projekt/Ports prüfen, nichts starten",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Browser nicht automatisch öffnen",
    )
    parser.add_argument(
        "--health-timeout",
        type=float,
        default=DEFAULT_HEALTH_TIMEOUT,
        help=f"Health-Check Timeout in Sekunden (Default: {DEFAULT_HEALTH_TIMEOUT})",
    )
    parser.add_argument(
        "--health-interval",
        type=float,
        default=DEFAULT_HEALTH_INTERVAL,
        help=f"Health-Check Intervall (Default: {DEFAULT_HEALTH_INTERVAL})",
    )
    args = parser.parse_args()
    sys.exit(
        run_launcher(
            dry_run=args.dry_run,
            open_browser=not args.no_browser,
            health_timeout=args.health_timeout,
            health_interval=args.health_interval,
        )
    )


if __name__ == "__main__":
    main()
