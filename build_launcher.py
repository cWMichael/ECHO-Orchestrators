"""
ECHO Orchestrator — Launcher Builder

Kompiliert launcher.py via PyInstaller zu einer Desktop-EXE.
Die EXE ist ein dünner Orchestrator: startet Backend + Gradio über die
Projekt-.venv (uv sync muss im Projekt einmal gelaufen sein).

Verwendung:
    uv run python build_launcher.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent.resolve()
LAUNCHER_PATH = PROJECT_DIR / "launcher.py"
EXE_NAME = "ECHO_Orchestrator_Start"
DESKTOP_DIR = Path(os.path.expanduser("~\\Desktop"))


def _log(msg: str) -> None:
    print(f"  {msg}")


def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _err(msg: str) -> None:
    print(f"  ✗  {msg}", file=sys.stderr)


def _sep() -> None:
    print("  " + "─" * 68)


def _check_pyinstaller() -> str:
    if shutil.which("pyinstaller"):
        return "pyinstaller"

    uv = shutil.which("uv")
    if uv:
        _log("PyInstaller nicht gefunden — installiere via uv ...")
        result = subprocess.run(
            [uv, "tool", "install", "pyinstaller"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            _ok("PyInstaller via uv installiert.")
            return f"{uv} tool run pyinstaller"
        _err(f"uv-Installation fehlgeschlagen:\n{result.stderr.strip()}")

    _log("Versuche pip install pyinstaller ...")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "pyinstaller", "--quiet"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        _err(f"pip-Installation fehlgeschlagen:\n{result.stderr.strip()}")
        raise RuntimeError(
            "PyInstaller konnte nicht installiert werden. "
            "Bitte manuell: pip install pyinstaller"
        )
    _ok("PyInstaller via pip installiert.")
    return "pyinstaller"


def _build_exe(pyinstaller_cmd: str) -> Path:
    dist_dir = PROJECT_DIR / "dist"
    build_dir = PROJECT_DIR / "build"

    cmd_parts = pyinstaller_cmd.split() + [
        str(LAUNCHER_PATH),
        "--onefile",
        "--console",
        f"--name={EXE_NAME}",
        f"--distpath={dist_dir}",
        f"--workpath={build_dir}",
        f"--specpath={PROJECT_DIR}",
        "--clean",
        "--noconfirm",
    ]

    _log("Starte PyInstaller ...")
    _log(f"Befehl: {' '.join(cmd_parts)}")
    print()

    result = subprocess.run(cmd_parts, cwd=str(PROJECT_DIR))
    if result.returncode != 0:
        raise RuntimeError(
            f"PyInstaller fehlgeschlagen (rc={result.returncode}). "
            "Output oben prüfen."
        )

    exe_path = dist_dir / f"{EXE_NAME}.exe"
    if not exe_path.is_file():
        raise FileNotFoundError(f"Erwartete .exe nicht gefunden: {exe_path}")

    _ok(f"Executable erstellt: {exe_path}")
    return exe_path


def _deploy_to_desktop(exe_path: Path) -> Path:
    if not DESKTOP_DIR.is_dir():
        raise FileNotFoundError(
            f"Desktop nicht gefunden: {DESKTOP_DIR}\n"
            "Zielpfad in build_launcher.py anpassen."
        )

    target = DESKTOP_DIR / exe_path.name
    shutil.copy2(exe_path, target)
    _ok(f"Executable auf Desktop kopiert: {target}")

    sidecar = DESKTOP_DIR / "echo_project_root.txt"
    sidecar.write_text(f"{PROJECT_DIR}\n", encoding="utf-8")
    _ok(f"Projekt-Pfad geschrieben: {sidecar}")

    return target


def _cleanup_build_artifacts() -> None:
    for path in (PROJECT_DIR / "build", PROJECT_DIR / f"{EXE_NAME}.spec"):
        try:
            if path.is_dir():
                shutil.rmtree(path)
                _ok(f"Ordner entfernt: {path.name}/")
            elif path.is_file():
                path.unlink()
                _ok(f"Datei entfernt: {path.name}")
        except OSError as exc:
            _log(f"Konnte '{path.name}' nicht entfernen: {exc}")


def main() -> None:
    print()
    print("  ════════════════════════════════════════════════════════════════════")
    print("    ECHO ORCHESTRATOR — Launcher Builder")
    print("  ════════════════════════════════════════════════════════════════════")
    print(f"  Projektverzeichnis : {PROJECT_DIR}")
    print(f"  Launcher           : {LAUNCHER_PATH}")
    print(f"  Ziel-Desktop       : {DESKTOP_DIR}")
    print(f"  Executable-Name    : {EXE_NAME}.exe")
    _sep()
    print()

    if not LAUNCHER_PATH.is_file():
        _err(f"launcher.py fehlt: {LAUNCHER_PATH}")
        sys.exit(1)

    try:
        pyinstaller_cmd = _check_pyinstaller()
        _sep()

        exe_path = _build_exe(pyinstaller_cmd)
        _sep()

        desktop_exe = _deploy_to_desktop(exe_path)
        _sep()

        _log("Räume PyInstaller-Artefakte auf ...")
        _cleanup_build_artifacts()
        _sep()

        print()
        print("  ════════════════════════════════════════════════════════════════════")
        print("    BUILD ERFOLGREICH")
        print("  ════════════════════════════════════════════════════════════════════")
        print(f"  Desktop: {desktop_exe}")
        print(f"  Dist:    {exe_path}")
        print()
        print("  Doppelklick startet Backend (:8020) + Control UI (:7860).")
        print("  Voraussetzung: uv sync im Projekt, .venv vorhanden.")
        print("  Projekt-Pfad: echo_project_root.txt (Desktop), ECHO_PROJECT_ROOT, oder dist/ im Projekt.")
        print("  Logs: logs/launcher/, logs/backend/, logs/ui/")
        print()

    except (RuntimeError, FileNotFoundError) as exc:
        print()
        _sep()
        _err(f"BUILD FEHLGESCHLAGEN: {exc}")
        _sep()
        sys.exit(1)

    except KeyboardInterrupt:
        print()
        _err("Build abgebrochen (Ctrl+C).")
        sys.exit(1)


if __name__ == "__main__":
    main()
