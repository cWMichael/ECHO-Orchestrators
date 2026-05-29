"""
ECHO Orchestrator — Launcher Builder
Generiert launcher.py, kompiliert es via PyInstaller zu einer .exe
und legt die fertige Executable auf dem Windows-Desktop ab.

Verwendung:
    uv run build_launcher.py
    python build_launcher.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path


# ── Konfiguration ─────────────────────────────────────────────────────────────

PROJECT_DIR   = Path(__file__).parent.resolve()
LAUNCHER_NAME = "launcher.py"
EXE_NAME      = "ECHO_Orchestrator_Start"
DESKTOP_DIR   = Path(os.path.expanduser("~\\Desktop"))

# Inhalt des generierten Mini-Skripts
LAUNCHER_SOURCE = textwrap.dedent(f"""\
    \"\"\"
    ECHO Orchestrator — Launcher
    Öffnet zwei eigenständige Windows-Konsolen parallel:
      1. uvicorn (FastAPI-Server)
      2. run_pipeline.py (Interaktiver Pipeline-Test)
    \"\"\"

    import subprocess
    import sys
    import time
    from pathlib import Path

    PROJECT_DIR = r"{PROJECT_DIR}"

    def open_console(title: str, command: str) -> subprocess.Popen:
        \"\"\"Öffnet eine neue cmd.exe-Konsole mit eigenem Titel.\"\"\"
        full_cmd = (
            f'start "{{title}}" cmd.exe /K '
            f'"cd /D {{PROJECT_DIR}} && {{command}}"'
        )
        return subprocess.Popen(
            full_cmd,
            shell=True,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )

    def main() -> None:
        print("ECHO Orchestrator wird gestartet ...")
        print(f"Projektverzeichnis: {{PROJECT_DIR}}")
        print()

        # Fenster 1: uvicorn Server
        open_console(
            title="ECHO | uvicorn Server",
            command="uv run uvicorn main:app --reload --port 8020",
        )
        print("[1/2] uvicorn-Konsole geöffnet.")

        # Kurz warten damit der Server hochfahren kann
        time.sleep(3)

        # Fenster 2: run_pipeline.py
        open_console(
            title="ECHO | Pipeline Runner",
            command='uv run python run_pipeline.py --reviewer "Michael" --worker backend_worker',
        )
        print("[2/2] Pipeline-Konsole geöffnet.")
        print()
        print("Beide Fenster laufen unabhängig. Dieses Fenster kann geschlossen werden.")

    if __name__ == "__main__":
        main()
""")


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    print(f"  {msg}")


def _ok(msg: str) -> None:
    print(f"  ✓  {msg}")


def _err(msg: str) -> None:
    print(f"  ✗  {msg}", file=sys.stderr)


def _sep() -> None:
    print("  " + "─" * 68)


def _check_pyinstaller() -> str:
    """
    Gibt den Pfad zum PyInstaller-Binary zurück.
    Versucht zuerst 'uv run pyinstaller', dann 'pyinstaller' direkt.
    Installiert PyInstaller via uv falls nicht vorhanden.
    """
    # Prüfen ob pyinstaller direkt verfügbar ist
    if shutil.which("pyinstaller"):
        return "pyinstaller"

    # Via uv prüfen/installieren
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
        else:
            _err(f"uv-Installation fehlgeschlagen:\n{result.stderr.strip()}")

    # Fallback: pip
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
            "Bitte manuell ausführen: pip install pyinstaller"
        )
    _ok("PyInstaller via pip installiert.")
    return "pyinstaller"


def _write_launcher(path: Path) -> None:
    """Schreibt den generierten launcher.py-Quellcode."""
    path.write_text(LAUNCHER_SOURCE, encoding="utf-8")
    _ok(f"launcher.py generiert: {path}")


def _build_exe(launcher_path: Path, pyinstaller_cmd: str) -> Path:
    """
    Kompiliert launcher.py via PyInstaller zu einer standalone .exe.
    Gibt den Pfad zur generierten .exe zurück.
    """
    dist_dir = PROJECT_DIR / "dist"
    build_dir = PROJECT_DIR / "build"

    cmd_parts = pyinstaller_cmd.split() + [
        str(launcher_path),
        "--onefile",
        "--noconsole",
        f"--name={EXE_NAME}",
        f"--distpath={dist_dir}",
        f"--workpath={build_dir}",
        f"--specpath={PROJECT_DIR}",
        "--clean",
        "--noconfirm",
    ]

    _log(f"Starte PyInstaller ...")
    _log(f"Befehl: {' '.join(cmd_parts)}")
    print()

    result = subprocess.run(
        cmd_parts,
        cwd=str(PROJECT_DIR),
        capture_output=False,   # PyInstaller-Output direkt durchreichen
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"PyInstaller fehlgeschlagen (rc={result.returncode}). "
            "Prüfe den Output oben auf Fehlerdetails."
        )

    exe_path = dist_dir / f"{EXE_NAME}.exe"
    if not exe_path.exists():
        raise FileNotFoundError(
            f"Erwartete .exe nicht gefunden: {exe_path}\n"
            "PyInstaller hat möglicherweise einen anderen Output-Pfad verwendet."
        )

    _ok(f"Executable erstellt: {exe_path}")
    return exe_path


def _deploy_to_desktop(exe_path: Path) -> Path:
    """Kopiert die .exe auf den Windows-Desktop."""
    if not DESKTOP_DIR.exists():
        raise FileNotFoundError(
            f"Desktop-Verzeichnis nicht gefunden: {DESKTOP_DIR}\n"
            "Bitte den Zielpfad in build_launcher.py manuell anpassen."
        )

    target = DESKTOP_DIR / exe_path.name
    shutil.copy2(exe_path, target)
    _ok(f"Executable auf Desktop kopiert: {target}")
    return target


def _cleanup(launcher_path: Path) -> None:
    """Entfernt temporäre PyInstaller-Artefakte."""
    to_remove: list[Path] = [
        launcher_path,
        PROJECT_DIR / "build",
        PROJECT_DIR / "dist",
        PROJECT_DIR / f"{EXE_NAME}.spec",
    ]
    for path in to_remove:
        try:
            if path.is_dir():
                shutil.rmtree(path)
                _ok(f"Ordner entfernt: {path.name}/")
            elif path.is_file():
                path.unlink()
                _ok(f"Datei entfernt: {path.name}")
        except OSError as exc:
            _log(f"Konnte '{path.name}' nicht entfernen: {exc}")


# ── Einstiegspunkt ────────────────────────────────────────────────────────────

def main() -> None:
    print()
    print("  ════════════════════════════════════════════════════════════════════")
    print("    ECHO ORCHESTRATOR — Launcher Builder")
    print("  ════════════════════════════════════════════════════════════════════")
    print(f"  Projektverzeichnis : {PROJECT_DIR}")
    print(f"  Ziel-Desktop       : {DESKTOP_DIR}")
    print(f"  Executable-Name    : {EXE_NAME}.exe")
    _sep()
    print()

    launcher_path = PROJECT_DIR / LAUNCHER_NAME

    try:
        # 1. PyInstaller sicherstellen
        pyinstaller_cmd = _check_pyinstaller()
        _sep()

        # 2. launcher.py generieren
        _write_launcher(launcher_path)
        _sep()

        # 3. .exe kompilieren
        exe_path = _build_exe(launcher_path, pyinstaller_cmd)
        _sep()

        # 4. Auf Desktop deployen
        desktop_exe = _deploy_to_desktop(exe_path)
        _sep()

        # 5. Aufräumen
        _log("Räume temporäre Artefakte auf ...")
        _cleanup(launcher_path)
        _sep()

        print()
        print("  ════════════════════════════════════════════════════════════════════")
        print("    BUILD ERFOLGREICH")
        print("  ════════════════════════════════════════════════════════════════════")
        print(f"  Desktop: {desktop_exe}")
        print()
        print("  Doppelklick auf 'ECHO_Orchestrator_Start.exe' startet:")
        print("    → Fenster 1: uv run uvicorn main:app --reload --port 8020")
        print("    → Fenster 2: python run_pipeline.py --reviewer 'Mica'")
        print()

    except (RuntimeError, FileNotFoundError) as exc:
        print()
        _sep()
        _err(f"BUILD FEHLGESCHLAGEN: {exc}")
        _sep()
        # Aufräumen auch im Fehlerfall
        if launcher_path.exists():
            _cleanup(launcher_path)
        sys.exit(1)

    except KeyboardInterrupt:
        print()
        _err("Build abgebrochen (Ctrl+C).")
        if launcher_path.exists():
            _cleanup(launcher_path)
        sys.exit(1)


if __name__ == "__main__":
    main()
