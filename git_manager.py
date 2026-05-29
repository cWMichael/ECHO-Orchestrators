"""
ECHO Orchestrator — Git Manager
Kapselt alle Git-Operationen über Pythons subprocess-Modul.

Design-Prinzip:
  - Keine autonomen Commits. Jeder schreibende Git-Befehl (commit, push)
    wird nur ausgeführt, nachdem der Core Router eine explizite Freigabe
    (HumanApproval.approved == True) erhalten hat.
  - Alle Operationen sind synchron (subprocess), da Git-Calls kurz sind
    und in async-Kontexten per asyncio.to_thread() aufgerufen werden.
  - Jeder Fehler wirft eine GitOperationError mit dem vollständigen
    stderr-Output — nie stille Fehler.
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("echo.git_manager")

# Branch-Name: nur alphanumerisch + Bindestrich/Schrägstrich, kein Whitespace
_SAFE_BRANCH_RE = re.compile(r"^[a-zA-Z0-9/_\-\.]+$")


class GitOperationError(RuntimeError):
    """Raised when a git subprocess call fails."""


@dataclass
class GitStatus:
    branch: str
    staged_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    untracked_files: list[str] = field(default_factory=list)
    has_diff: bool = False


class GitManager:
    """
    Manages Git operations for ECHO Orchestrator feature branches.

    Usage pattern (enforced by core_router):
      1. create_feature_branch(task_id)   — isoliert jeden Task
      2. [Worker schreibt Dateien]
      3. get_code_diff()                  — Router zeigt Diff zur Freigabe
      4a. commit_and_push(message)        — nach Approval
      4b. discard_changes(delete_branch)  — nach Rejection
    """

    def __init__(self, repo_path: str | Path = ".") -> None:
        self.repo_path = Path(repo_path).resolve()
        self._validate_repo()

    # ── Setup & Validation ────────────────────────────────────────────────────

    def _validate_repo(self) -> None:
        """Stellt sicher, dass der Pfad ein Git-Repository ist."""
        result = self._run(["git", "rev-parse", "--is-inside-work-tree"], check=False)
        if result.returncode != 0:
            raise GitOperationError(
                f"'{self.repo_path}' ist kein Git-Repository. "
                "Bitte führe 'git init' aus oder wähle den richtigen Pfad."
            )

    # ── Branch Management ─────────────────────────────────────────────────────

    def get_current_branch(self) -> str:
        """Gibt den aktuell ausgecheckten Branch zurück."""
        result = self._run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        return result.stdout.strip()

    def create_feature_branch(self, task_id: str) -> str:
        """
        Erstellt und checkt einen isolierten Feature-Branch aus.
        Branch-Name: feature/echo-{task_id[:8]}

        Returns:
            Der Name des neu erstellten Branches.
        Raises:
            GitOperationError: Branch existiert bereits oder Git schlägt fehl.
        """
        safe_id = task_id.replace("-", "")[:8]
        branch_name = f"feature/echo-{safe_id}"

        if not _SAFE_BRANCH_RE.match(branch_name):
            raise GitOperationError(
                f"Ungültiger Branch-Name berechnet: '{branch_name}'. "
                f"Task-ID enthält unerlaubte Zeichen: '{task_id}'"
            )

        # Prüfen ob Branch bereits existiert
        existing = self._run(
            ["git", "branch", "--list", branch_name], check=False
        )
        if existing.stdout.strip():
            raise GitOperationError(
                f"Branch '{branch_name}' existiert bereits. "
                "Task-ID muss eindeutig sein."
            )

        self._run(["git", "checkout", "-b", branch_name])
        logger.info("Feature-Branch erstellt und ausgecheckt: %s", branch_name)
        return branch_name

    def delete_branch(self, branch_name: str, force: bool = False) -> None:
        """
        Löscht einen lokalen Branch.
        force=True verwendet -D (auch bei ungemergten Änderungen).
        """
        flag = "-D" if force else "-d"
        self._run(["git", "branch", flag, branch_name])
        logger.info("Branch gelöscht: %s (force=%s)", branch_name, force)

    def checkout_branch(self, branch_name: str) -> None:
        """Wechselt zu einem bestehenden Branch."""
        self._run(["git", "checkout", branch_name])
        logger.info("Ausgecheckt: %s", branch_name)

    # ── Diff & Status ─────────────────────────────────────────────────────────

    def get_code_diff(self, staged: bool = False) -> str:
        """
        Gibt den aktuellen Git-Diff zurück.

        Args:
            staged: True → git diff --staged (bereits gestagte Änderungen)
                    False → git diff (unstaged working-tree Änderungen)
        Returns:
            Diff-Output als String. Leerer String = keine Änderungen.
        """
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--staged")
        result = self._run(cmd)
        diff = result.stdout.strip()
        if not diff:
            logger.debug("git diff: keine Änderungen gefunden.")
        return diff

    def get_status(self) -> GitStatus:
        """
        Gibt eine strukturierte Zusammenfassung des Repo-Zustands zurück.
        Parst 'git status --porcelain'.
        """
        current_branch = self.get_current_branch()
        result = self._run(["git", "status", "--porcelain"])

        staged, modified, untracked = [], [], []
        for line in result.stdout.splitlines():
            if len(line) < 2:
                continue
            index_status = line[0]
            worktree_status = line[1]
            filepath = line[3:].strip()

            if index_status in ("A", "M", "R", "D"):
                staged.append(filepath)
            if worktree_status == "M":
                modified.append(filepath)
            if index_status == "?" and worktree_status == "?":
                untracked.append(filepath)

        diff_output = self.get_code_diff()
        return GitStatus(
            branch=current_branch,
            staged_files=staged,
            modified_files=modified,
            untracked_files=untracked,
            has_diff=bool(diff_output),
        )

    # ── Commit & Push ─────────────────────────────────────────────────────────

    def stage_all(self) -> None:
        """Staged alle Änderungen im Working Tree (git add -A)."""
        self._run(["git", "add", "-A"])
        logger.info("Alle Änderungen gestaged.")

    def commit_and_push(
        self,
        message: str,
        remote: str = "origin",
        push: bool = True,
    ) -> str:
        """
        Staged alle Änderungen, erstellt einen Commit und pusht optional.
        DARF NUR nach expliziter Human-Freigabe aufgerufen werden.

        Args:
            message: Commit-Message.
            remote:  Git-Remote, default 'origin'.
            push:    True = direkt pushen, False = nur lokaler Commit.
        Returns:
            Der vollständige Commit-Hash.
        Raises:
            GitOperationError: Keine Änderungen vorhanden, oder Git schlägt fehl.
        """
        status = self.get_status()
        if not status.has_diff and not status.staged_files and not status.modified_files:
            raise GitOperationError(
                "Kein Commit möglich: Es gibt keine Änderungen im Working Tree."
            )

        self.stage_all()
        self._run(["git", "commit", "-m", message])

        commit_hash_result = self._run(["git", "rev-parse", "HEAD"])
        commit_hash = commit_hash_result.stdout.strip()
        logger.info("Commit erstellt: %s | Message: %s", commit_hash[:12], message)

        if push:
            current_branch = self.get_current_branch()
            self._run(["git", "push", remote, current_branch])
            logger.info(
                "Branch '%s' nach '%s' gepusht.", current_branch, remote
            )

        return commit_hash

    # ── Discard & Cleanup ─────────────────────────────────────────────────────

    def discard_changes(self) -> None:
        """
        Verwirft alle uncommitteten Änderungen im Working Tree.
        Entspricht: git checkout . && git clean -fd
        NIEMALS für bereits commitete Änderungen verwenden.
        """
        self._run(["git", "checkout", "."])
        # Entfernt ungetrackte Dateien und Verzeichnisse
        self._run(["git", "clean", "-fd"])
        logger.info("Alle uncommitteten Änderungen verworfen.")

    def discard_and_delete_branch(
        self,
        feature_branch: str,
        return_branch: str = "main",
    ) -> None:
        """
        Vollständiges Rollback nach Rejection:
          1. Änderungen verwerfen
          2. Zurück zum return_branch wechseln
          3. Feature-Branch löschen (force, da keine Commits vorhanden)

        Args:
            feature_branch: Der zu löschende Feature-Branch.
            return_branch:  Ziel-Branch nach dem Wechsel (default: 'main').
        """
        logger.info(
            "Rejection-Rollback: verwerfe '%s', kehre zu '%s' zurück.",
            feature_branch,
            return_branch,
        )
        self.discard_changes()
        self.checkout_branch(return_branch)
        self.delete_branch(feature_branch, force=True)
        logger.info("Rollback abgeschlossen.")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(
        self,
        cmd: list[str],
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Führt einen Git-Befehl als Subprocess aus.

        Args:
            cmd:   Vollständiger Befehl als Liste, z.B. ['git', 'diff'].
            check: True = wirft GitOperationError bei non-zero returncode.
        Returns:
            CompletedProcess mit stdout/stderr als Strings.
        Raises:
            GitOperationError: Bei Fehler und check=True.
        """
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except FileNotFoundError as exc:
            raise GitOperationError(
                "Git-Binary nicht gefunden. Ist Git installiert und im PATH?"
            ) from exc

        if check and result.returncode != 0:
            raise GitOperationError(
                f"Git-Befehl fehlgeschlagen: {' '.join(cmd)}\n"
                f"Return Code: {result.returncode}\n"
                f"stderr: {result.stderr.strip()}\n"
                f"stdout: {result.stdout.strip()}"
            )

        logger.debug(
            "Git: %s → rc=%d", " ".join(cmd), result.returncode
        )
        return result
