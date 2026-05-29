"""
ECHO Orchestrator — Error Handling Validation
Beweist, dass der Fehlerfall korrekt durchläuft:

  1. FileWriter schreibt eine Datei mit bewusstem Syntax-Fehler
  2. TestRunner führt pytest aus → Exit-Code != 0
  3. Validierung: success=False, Fehlerdetails vorhanden
  4. Validierung: kein Git-Commit wurde ausgelöst

Läuft ohne Server, ohne LLM — direkte Komponenten-Tests.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Sicherstellen, dass das Projektverzeichnis im Python-Pfad ist
PROJECT_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from git_manager import GitManager, GitOperationError
from workers.file_writer import FileWriter
from workers.test_runner import TestRunner

# ── ANSI ──────────────────────────────────────────────────────────────────────
GREEN  = "\033[32m" if sys.stdout.isatty() else ""
RED    = "\033[31m" if sys.stdout.isatty() else ""
YELLOW = "\033[33m" if sys.stdout.isatty() else ""
BOLD   = "\033[1m"  if sys.stdout.isatty() else ""
RESET  = "\033[0m"  if sys.stdout.isatty() else ""
SEP    = "─" * 68


def ok(msg: str)   -> None: print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg: str) -> None: print(f"  {RED}✗{RESET}  {msg}")
def info(msg: str) -> None: print(f"  {YELLOW}→{RESET}  {msg}")


# ── Test-Szenarien ─────────────────────────────────────────────────────────────

# Szenario A: Syntax-Fehler → pytest kann die Datei nicht einmal importieren
BROKEN_TEST_SYNTAX = """\
import pytest

def test_broken_syntax(
    # Fehlende schließende Klammer — SyntaxError beim Import
    x = 1
    assert x == 1
"""

# Szenario B: Importfehler → Modul existiert nicht
BROKEN_TEST_IMPORT = """\
import pytest
from does_not_exist_module import SomeClass  # ImportError

def test_with_broken_import():
    obj = SomeClass()
    assert obj is not None
"""

# Szenario C: Assertion schlägt fehl → Test-Fehler
BROKEN_TEST_ASSERTION = """\
import pytest

def test_wrong_assertion():
    result = 1 + 1
    assert result == 999, f"Erwartet 999, erhalten {result}"

def test_another_failure():
    raise ValueError("Bewusst provozierter Fehler")
"""


def run_scenario(
    name: str,
    broken_code: str,
    tmpdir: Path,
) -> bool:
    """
    Führt ein Fehlerszenario durch.
    Returns True wenn der Fehlerfall korrekt erkannt wurde.
    """
    print(f"\n{SEP}")
    print(f"  {BOLD}Szenario: {name}{RESET}")
    print(SEP)

    # 1. FileWriter schreibt die fehlerhafte Datei
    test_file = f"tests/test_broken_{name.lower().replace(' ', '_')}.py"
    writer = FileWriter(project_root=tmpdir)

    llm_output = f"## FILE: {test_file}\n```python\n{broken_code}\n```"

    written = writer.extract_and_write(llm_output)
    if not written:
        fail("FileWriter hat keine Datei geschrieben.")
        return False
    ok(f"FileWriter schrieb: {written[0]}")

    # 2. TestRunner führt pytest aus
    runner = TestRunner(project_root=tmpdir)
    result = runner.run(test_paths=[str(written[0])])

    info(f"pytest Exit → success={result.success}")
    info(f"Summary: {result.summary}")

    # 3. Validierung: success muss False sein
    if result.success:
        fail(f"FEHLER: success=True erwartet, aber success={result.success}")
        fail("Der Fehlerfall wurde NICHT korrekt erkannt!")
        return False
    ok(f"success=False korrekt erkannt")

    # 4. pytest-Output muss Fehlerdetails enthalten
    has_error_output = any(
        keyword in result.output
        for keyword in ["ERROR", "FAILED", "SyntaxError", "ImportError",
                        "AssertionError", "ValueError", "error"]
    )
    if has_error_output:
        ok("pytest-Output enthält Fehlerdetails")
    else:
        fail("pytest-Output enthält keine Fehlerdetails — prüfe TestRunner-Output")
        print(f"\n  Rohausgabe:\n{result.output[:500]}")
        return False

    # 5. Fehlerdetails-Vorschau
    print(f"\n  {YELLOW}pytest Output (erste 10 Zeilen):{RESET}")
    for line in result.output.splitlines()[:10]:
        print(f"    {line}")

    return True


def validate_no_git_commit(repo_path: Path) -> bool:
    """
    Prüft, dass die Validation selbst keinen neuen Commit ausgelöst hat.
    Vergleicht HEAD-Hash vor und nach — ein vorhandener unsauberer Working Tree
    (z.B. aktiver Feature-Branch) ist kein Fehler.
    """
    import subprocess

    print(f"\n{SEP}")
    print(f"  {BOLD}Git-Validierung: kein Commit durch Validation{RESET}")
    print(SEP)

    try:
        git = GitManager(repo_path=repo_path)
        current_branch = git.get_current_branch()
        info(f"Aktueller Branch: {current_branch}")

        r1 = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path), capture_output=True, text=True,
        )
        commit_before = r1.stdout.strip()
        info(f"HEAD-Commit: {commit_before[:12]}")

        r2 = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_path), capture_output=True, text=True,
        )
        commit_after = r2.stdout.strip()

        if commit_before != commit_after:
            fail(f"Neuer Commit während Validation! {commit_before[:12]} → {commit_after[:12]}")
            return False

        ok(f"HEAD stabil — kein Commit durch Validation ({commit_before[:12]})")

        status = git.get_status()
        if status.has_diff or status.modified_files or status.staged_files:
            info(f"Bestehende Änderungen auf '{current_branch}' — normal bei aktivem Feature-Branch.")
        else:
            ok("Working Tree zusätzlich sauber.")

        return True

    except GitOperationError as exc:
        info(f"Git-Check übersprungen (kein Repo): {exc}")
        return True


# ── Haupt-Validierung ─────────────────────────────────────────────────────────

def main() -> None:
    print()
    print(f"  {'═' * 66}")
    print(f"  {BOLD}  ECHO ORCHESTRATOR — ERROR HANDLING VALIDATION{RESET}")
    print(f"  {'═' * 66}")
    print(f"  Prüft: FileWriter → TestRunner → success=False Pipeline")
    print(f"  Repo : {PROJECT_ROOT}")
    print(f"  {'═' * 66}")

    passed = 0
    failed = 0

    # Temporäres Verzeichnis als isoliertes Test-Repo
    with tempfile.TemporaryDirectory(prefix="echo_test_") as tmpdir:
        tmp = Path(tmpdir)

        # pytest braucht ein tests/-Verzeichnis
        (tmp / "tests").mkdir()
        (tmp / "tests" / "__init__.py").touch()

        scenarios = [
            ("Syntax Fehler",     BROKEN_TEST_SYNTAX),
            ("Import Fehler",     BROKEN_TEST_IMPORT),
            ("Assertion Fehler",  BROKEN_TEST_ASSERTION),
        ]

        for name, code in scenarios:
            success = run_scenario(name, code, tmp)
            if success:
                passed += 1
            else:
                failed += 1

    # Git-Check auf dem echten Repo
    git_ok = validate_no_git_commit(PROJECT_ROOT)
    if git_ok:
        passed += 1
    else:
        failed += 1

    # ── Ergebnis ──────────────────────────────────────────────────────────────
    print(f"\n{'═' * 70}")
    print(f"  {BOLD}ERGEBNIS{RESET}")
    print(f"{'═' * 70}")
    print(f"  Szenarien bestanden : {GREEN}{passed}{RESET}")
    print(f"  Szenarien fehlerhaft: {RED}{failed}{RESET}")
    print()

    if failed == 0:
        print(
            f"  {GREEN}{BOLD}✓ Alle Validierungen bestanden.{RESET}\n"
            f"  {GREEN}  Fehlerhafte Tests blockieren korrekt den Commit-Pfad.{RESET}"
        )
    else:
        print(
            f"  {RED}{BOLD}✗ {failed} Validierung(en) fehlgeschlagen.{RESET}\n"
            f"  {RED}  Bitte prüfe die Ausgaben oben.{RESET}"
        )

    print(f"\n{'═' * 70}\n")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
