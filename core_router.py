"""
ECHO Orchestrator — Core Router
Zentrale Intelligenz-, Routing- und Kontrollschicht.

Pipeline (Stufe 4):
  1. Task empfangen → TaskState anlegen
  2. Complexity Score → Modell-Backend zuweisen
  3. Feature-Branch erstellen (GitManager)
  4. Human-in-the-Loop Gate 1: Approval für Worker-Ausführung
  5. Worker ausführen
  6. Git-Diff ermitteln → Status PENDING_DIFF setzen
  7. Human-in-the-Loop Gate 2: Diff-Freigabe
     → Approved:  commit_and_push()
     → Rejected:  discard_and_delete_branch()
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException, status

from config import Settings, get_settings
from git_manager import GitManager, GitOperationError
from task_history import save_task
from models import (
    ApproveTaskRequest,
    HumanApproval,
    ModelBackend,
    SubmitTaskRequest,
    SubmitTaskResponse,
    TaskPayload,
    TaskState,
    TaskStatus,
    TaskStatusResponse,
    WorkerType,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger("echo.core_router")

router = APIRouter(tags=["Orchestrator"])

# In-memory task store (replace with Redis / DB in production)
_task_store: dict[str, TaskState] = {}

# Tracks feature-branch names per task_id
_task_branches: dict[str, str] = {}

# Tracks git diffs awaiting second approval per task_id
_task_diffs: dict[str, str] = {}


# ── Complexity Scoring ────────────────────────────────────────────────────────

_WORKER_COMPLEXITY: dict[WorkerType, float] = {
    WorkerType.BACKEND: 0.75,
    WorkerType.FRONTEND: 0.55,
    WorkerType.TEST: 0.40,
    WorkerType.DOCS: 0.30,
    WorkerType.RETRIEVAL: 0.50,
}


def _compute_complexity(payload: TaskPayload) -> float:
    base = _WORKER_COMPLEXITY.get(payload.worker_type, 0.5)
    desc_bonus = min(len(payload.description) / 2000, 0.15)
    ctx_bonus = min(len(payload.context) / 20, 0.10)
    return round(min(base + desc_bonus + ctx_bonus, 1.0), 4)


def _assign_backend(score: float, settings: Settings) -> ModelBackend:
    return ModelBackend.OLLAMA


# ── Worker Registry ───────────────────────────────────────────────────────────

def _get_worker(worker_type: WorkerType, backend: ModelBackend, settings: Settings):
    from workers.backend_worker import BackendWorker
    from workers.docs_worker import DocsWorker
    from workers.frontend_worker import FrontendWorker
    from workers.retrieval_worker import RetrievalWorker
    from workers.test_worker import TestWorker

    mapping = {
        WorkerType.BACKEND: BackendWorker,
        WorkerType.FRONTEND: FrontendWorker,
        WorkerType.TEST: TestWorker,
        WorkerType.DOCS: DocsWorker,
        WorkerType.RETRIEVAL: RetrievalWorker,
    }
    return mapping[worker_type](backend=backend, settings=settings)


# ── Git Manager Factory ───────────────────────────────────────────────────────

def _get_git_manager(settings: Settings) -> GitManager | None:
    """
    Gibt einen GitManager zurück.
    Gibt None zurück wenn das CWD kein Git-Repo ist (z.B. in Tests),
    damit der Server trotzdem startet — mit einer Warnung.
    """
    try:
        return GitManager()
    except GitOperationError as exc:
        logger.warning(
            "GitManager konnte nicht initialisiert werden: %s. "
            "Git-Operationen werden übersprungen.",
            exc,
        )
        return None


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/tasks",
    response_model=SubmitTaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Task einreichen",
)
async def submit_task(
    request: SubmitTaskRequest,
    settings: Settings = Depends(get_settings),
) -> SubmitTaskResponse:
    """
    Nimmt einen Task entgegen, berechnet den Complexity Score,
    weist ein Modell-Backend zu und erstellt einen isolierten Feature-Branch.
    Danach wartet der Task auf Human-Approval (Gate 1).
    """
    payload = TaskPayload(**request.model_dump())
    score = _compute_complexity(payload)
    backend = _assign_backend(score, settings)

    # ── Feature-Branch anlegen ────────────────────────────────────────────────
    git = _get_git_manager(settings)
    branch_name: str | None = None

    if git is not None:
        try:
            branch_name = await asyncio.to_thread(
                git.create_feature_branch, payload.task_id
            )
            _task_branches[payload.task_id] = branch_name
            logger.info(
                "Feature-Branch '%s' für Task %s erstellt.",
                branch_name,
                payload.task_id,
            )
        except GitOperationError as exc:
            logger.error(
                "Feature-Branch für Task %s konnte nicht erstellt werden: %s",
                payload.task_id,
                exc,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Git-Fehler beim Branch-Erstellen: {exc}",
            ) from exc

    # ── TaskState anlegen ─────────────────────────────────────────────────────
    initial_status = (
        TaskStatus.APPROVED
        if settings.bypass_human_gate
        else TaskStatus.AWAITING_APPROVAL
    )
    state = TaskState(
        payload=payload,
        status=initial_status,
        model_backend=backend,
        complexity_score=score,
    )
    _task_store[payload.task_id] = state

    logger.info(
        "Task %s eingereicht | worker=%s | backend=%s | score=%.4f | branch=%s",
        payload.task_id,
        payload.worker_type,
        backend,
        score,
        branch_name or "n/a",
    )

    msg = (
        "Task wurde auf Feature-Branch isoliert und wartet auf Freigabe."
        if not settings.bypass_human_gate
        else f"Task auto-approved (bypass_human_gate=True). Branch: {branch_name or 'n/a'}."
    )
    return SubmitTaskResponse(
        task_id=payload.task_id,
        status=state.status,
        message=msg,
    )


@router.post(
    "/tasks/{task_id}/approve",
    response_model=SubmitTaskResponse,
    summary="Gate 1: Worker-Ausführung freigeben oder ablehnen",
)
async def approve_task(
    task_id: str,
    request: ApproveTaskRequest,
    settings: Settings = Depends(get_settings),
) -> SubmitTaskResponse:
    """
    Human-in-the-Loop Gate 1: Freigabe für die Worker-Ausführung.

    Approved → Worker wird ausgeführt → Diff wird ermittelt → Status PENDING_DIFF.
    Rejected → Feature-Branch wird verworfen und gelöscht → Status REJECTED.
    """
    state = _task_store.get(task_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' nicht gefunden.",
        )
    if state.status not in (TaskStatus.AWAITING_APPROVAL, TaskStatus.APPROVED):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task hat Status '{state.status}' und kann nicht freigegeben werden.",
        )

    approval = HumanApproval(
        task_id=task_id,
        approved=request.approved,
        reviewer=request.reviewer,
        comment=request.comment,
    )
    state.approval = approval

    # ── Rejection: Branch verwerfen ───────────────────────────────────────────
    if not request.approved:
        state.status = TaskStatus.REJECTED
        git = _get_git_manager(settings)
        branch_name = _task_branches.get(task_id)
        if git is not None and branch_name:
            try:
                await asyncio.to_thread(
                    git.discard_and_delete_branch,
                    branch_name,
                )
                logger.info(
                    "Task %s abgelehnt von %s — Branch '%s' gelöscht.",
                    task_id,
                    request.reviewer,
                    branch_name,
                )
            except GitOperationError as exc:
                logger.error(
                    "Branch '%s' konnte nicht gelöscht werden: %s",
                    branch_name,
                    exc,
                )
        return SubmitTaskResponse(
            task_id=task_id,
            status=state.status,
            message=f"Task von {request.reviewer} abgelehnt. Feature-Branch wurde verworfen.",
        )

    # ── Approval: Worker ausführen ────────────────────────────────────────────
    state.status = TaskStatus.IN_PROGRESS
    logger.info(
        "Task %s freigegeben von %s — Worker %s (%s) wird gestartet.",
        task_id,
        request.reviewer,
        state.payload.worker_type,
        state.model_backend,
    )

    try:
        worker = _get_worker(
            state.payload.worker_type,
            state.model_backend,  # type: ignore[arg-type]
            settings,
        )
        result = await worker.execute(state.payload)
        state.result = result
    except Exception as exc:
        state.status = TaskStatus.FAILED
        logger.exception("Worker für Task %s fehlgeschlagen.", task_id)
        # Branch aufräumen
        git = _get_git_manager(settings)
        branch_name = _task_branches.get(task_id)
        rollback_ok = False
        if git is not None and branch_name:
            try:
                await asyncio.to_thread(git.discard_and_delete_branch, branch_name)
                rollback_ok = True
            except GitOperationError as cleanup_exc:
                logger.error("Branch-Cleanup fehlgeschlagen: %s", cleanup_exc)
        # Task History: Fehler dokumentieren
        save_task(
            task_id=task_id,
            worker=str(state.payload.worker_type),
            files_changed=[],
            context_layers=state.payload.context.get("active_layers", []),
            status="failed",
            summary=state.payload.title,
            project_path=state.payload.context.get("project_path", ""),
            error=str(exc),
        )
        # Strukturierte Fehlermeldung
        recovery_info = {
            "error": str(exc),
            "worker": state.payload.worker_type.value,
            "task_id": task_id,
            "files_affected": state.payload.files,
            "rollback": "erfolgreich" if rollback_ok else "fehlgeschlagen",
            "rule_check": _check_rule_violations(str(exc)),
        }
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=recovery_info,
        ) from exc

    # ── Diff ermitteln → Gate 2 vorbereiten ───────────────────────────────────
    # Wenn Worker Dateien geschrieben hat, nutzen wir das direkt als "Diff"
    project_path = state.payload.context.get("project_path", "")
    written_files = result.artifacts if result else []
    diff: str = ""

    if written_files:
        # Synthetischen Diff aus geschriebenen Dateien bauen
        diff_lines = [f"=== Worker Output: {len(written_files)} Datei(en) geschrieben ==="]
        for rel_path in written_files:
            full_path = (Path(project_path) / rel_path) if project_path else Path(rel_path)
            diff_lines.append(f"\n+++ {rel_path}")
            if full_path.exists():
                try:
                    content = full_path.read_text(encoding="utf-8", errors="replace")
                    for line in content.splitlines():
                        diff_lines.append(f"+{line}")
                except OSError:
                    diff_lines.append("+ [Datei nicht lesbar]")
        diff = "\n".join(diff_lines)
    else:
        # Fallback: Git-Diff im Orchestrator-Repo
        git = _get_git_manager(settings)
        if git is not None:
            try:
                diff = await asyncio.to_thread(git.get_code_diff)
            except GitOperationError as exc:
                logger.warning("git diff fehlgeschlagen: %s", exc)

    if diff:
        _task_diffs[task_id] = diff
        state.status = TaskStatus.PENDING_DIFF
        logger.info(
            "Task %s wartet auf Diff-Freigabe (Gate 2). "
            "Diff-Größe: %d Zeichen.",
            task_id,
            len(diff),
        )
        # Diff in der Konsole ausgeben — sichtbar für lokale Entwicklung
        _print_diff_to_console(task_id, diff, state.payload.title)

        return SubmitTaskResponse(
            task_id=task_id,
            status=state.status,
            message=(
                f"Worker erfolgreich. {len(diff.splitlines())} Diff-Zeilen warten "
                f"auf Freigabe via POST /api/v1/tasks/{task_id}/approve-diff"
            ),
        )

    # Kein Diff → direkt abschließen (z.B. Docs-Worker schreibt nichts ins Repo)
    state.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
    return SubmitTaskResponse(
        task_id=task_id,
        status=state.status,
        message="Task abgeschlossen. Keine Code-Änderungen im Working Tree.",
    )


@router.post(
    "/tasks/{task_id}/approve-diff",
    response_model=SubmitTaskResponse,
    summary="Gate 2: Code-Diff freigeben oder verwerfen",
)
async def approve_diff(
    task_id: str,
    request: ApproveTaskRequest,
    settings: Settings = Depends(get_settings),
) -> SubmitTaskResponse:
    """
    Human-in-the-Loop Gate 2: Freigabe des generierten Code-Diffs.

    Approved → git commit + push auf Feature-Branch → Status COMPLETED.
    Rejected → git checkout . (Änderungen verworfen), Branch gelöscht → Status REJECTED.

    Der Reviewer sollte den Diff vorher via GET /api/v1/tasks/{task_id}/diff
    geprüft haben.
    """
    state = _task_store.get(task_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' nicht gefunden.",
        )
    if state.status != TaskStatus.PENDING_DIFF:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Task hat Status '{state.status}'. "
                "Diff-Freigabe nur im Status PENDING_DIFF möglich."
            ),
        )

    git = _get_git_manager(settings)
    branch_name = _task_branches.get(task_id)

    # ── Rejection: Änderungen verwerfen ──────────────────────────────────────
    if not request.approved:
        state.status = TaskStatus.REJECTED
        if git is not None and branch_name:
            try:
                await asyncio.to_thread(
                    git.discard_and_delete_branch, branch_name
                )
                logger.info(
                    "Diff für Task %s abgelehnt von %s — Branch '%s' verworfen.",
                    task_id,
                    request.reviewer,
                    branch_name,
                )
            except GitOperationError as exc:
                logger.error("Discard fehlgeschlagen: %s", exc)
        _task_diffs.pop(task_id, None)
        return SubmitTaskResponse(
            task_id=task_id,
            status=state.status,
            message=(
                f"Diff von {request.reviewer} abgelehnt. "
                "Alle Änderungen wurden verworfen. Feature-Branch gelöscht."
            ),
        )

    # ── Approval: Commit + Push ───────────────────────────────────────────────
    commit_message = (
        f"feat(echo): {state.payload.title}\n\n"
        f"Task-ID: {task_id}\n"
        f"Worker: {state.payload.worker_type}\n"
        f"Backend: {state.model_backend}\n"
        f"Freigegeben von: {request.reviewer}\n"
        + (f"Kommentar: {request.comment}" if request.comment else "")
    )

    commit_hash = ""
    project_path = state.payload.context.get("project_path", "")
    written_files = state.result.artifacts if state.result else []

    if project_path:
        # Dateien wurden ins externe Projektverzeichnis geschrieben — kein Orchestrator-Commit
        logger.info(
            "Task %s: %d Datei(en) ins Projekt geschrieben — kein Orchestrator-Commit.",
            task_id, len(written_files),
        )
        commit_hash = f"project:{len(written_files)}_files"
    elif git is not None:
        # Kein Projektpfad → Änderungen im Orchestrator-Repo committen
        try:
            commit_hash = await asyncio.to_thread(
                git.commit_and_push,
                commit_message,
            )
            logger.info(
                "Task %s committed (%s) und gepusht von %s.",
                task_id,
                commit_hash[:12],
                request.reviewer,
            )
        except GitOperationError as exc:
            state.status = TaskStatus.FAILED
            logger.error("Commit/Push für Task %s fehlgeschlagen: %s", task_id, exc)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Commit/Push fehlgeschlagen: {exc}",
            ) from exc

    state.status = TaskStatus.COMPLETED
    _task_diffs.pop(task_id, None)

    # Task History speichern
    save_task(
        task_id=task_id,
        worker=str(state.payload.worker_type),
        files_changed=state.result.artifacts if state.result else [],
        context_layers=state.payload.context.get("active_layers", []),
        status="completed",
        summary=state.payload.title,
        project_path=state.payload.context.get("project_path", ""),
    )

    return SubmitTaskResponse(
        task_id=task_id,
        status=state.status,
        message=(
            f"Code committed und gepusht. "
            f"Commit: {commit_hash[:12] if commit_hash else 'n/a'} | "
            f"Branch: {branch_name or 'n/a'}"
        ),
    )


@router.get(
    "/tasks/{task_id}/diff",
    summary="Aktuellen Code-Diff für einen Task abrufen",
    response_model=dict,
)
async def get_task_diff(task_id: str) -> dict:
    """
    Gibt den generierten Code-Diff zurück, der auf Freigabe wartet.
    Nur verfügbar wenn Task im Status PENDING_DIFF ist.
    """
    state = _task_store.get(task_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' nicht gefunden.",
        )
    diff = _task_diffs.get(task_id, "")
    # Strukturierte Änderungsinfo aus WorkerResult
    change_info = state.result.extra if state.result else {}
    return {
        "task_id": task_id,
        "status": state.status,
        "diff": diff,
        "diff_lines": len(diff.splitlines()) if diff else 0,
        "branch": _task_branches.get(task_id),
        "worker": state.payload.worker_type.value,
        "created": change_info.get("created", []),
        "modified": change_info.get("modified", []),
        "deleted": change_info.get("deleted", []),
        "summary": state.payload.title,
    }


@router.get(
    "/tasks/{task_id}",
    response_model=TaskStatusResponse,
    summary="Task-Status abfragen",
)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    state = _task_store.get(task_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' nicht gefunden.",
        )
    return TaskStatusResponse(
        task_id=state.payload.task_id,
        title=state.payload.title,
        status=state.status,
        worker_type=state.payload.worker_type,
        model_backend=state.model_backend,
        complexity_score=state.complexity_score,
        result=state.result,
        created_at=state.payload.created_at,
    )


@router.get(
    "/tasks",
    response_model=list[TaskStatusResponse],
    summary="Alle Tasks auflisten (paginiert)",
)
async def list_tasks(skip: int = 0, limit: int = 50) -> list[TaskStatusResponse]:
    all_states = list(_task_store.values())
    return [
        TaskStatusResponse(
            task_id=s.payload.task_id,
            title=s.payload.title,
            status=s.status,
            worker_type=s.payload.worker_type,
            model_backend=s.model_backend,
            complexity_score=s.complexity_score,
            result=s.result,
            created_at=s.payload.created_at,
        )
        for s in all_states[skip : skip + limit]
    ]


# ── Internal Helpers ──────────────────────────────────────────────────────────

def _check_rule_violations(error_msg: str) -> list[str]:
    """Gibt relevante Rule-Verletzungen basierend auf dem Fehlertext zurück."""
    violations = []
    msg = error_msg.lower()
    if "permission" in msg or "access denied" in msg:
        violations.append("SECURITY_RULES: Filesystem-Zugriff verweigert")
    if "timeout" in msg:
        violations.append("PERFORMANCE_RULES: Timeout überschritten")
    if "no file" in msg or "not found" in msg:
        violations.append("DEVELOPMENT_RULES: Datei nicht gefunden — Pfad prüfen")
    if "syntax" in msg or "indentation" in msg:
        violations.append("DEVELOPMENT_RULES: Code-Syntaxfehler im Output")
    if "module" in msg or "import" in msg:
        violations.append("ARCHITECTURE_RULES: Fehlende Abhängigkeit")
    if not violations:
        violations.append("Keine spezifische Rule-Verletzung erkannt — Logs prüfen")
    return violations


def _print_diff_to_console(task_id: str, diff: str, title: str) -> None:
    """
    Gibt den Diff strukturiert auf der Konsole aus.
    Dient als visuelle Unterstützung für lokale Entwicklung und CLI-Workflows.
    """
    separator = "─" * 72
    lines = diff.splitlines()
    preview = "\n".join(lines[:80])
    truncated = len(lines) > 80

    print(f"\n{separator}")
    print(f"  ECHO ORCHESTRATOR — DIFF-FREIGABE ERFORDERLICH")
    print(f"{separator}")
    print(f"  Task-ID : {task_id}")
    print(f"  Titel   : {title}")
    print(f"  Zeilen  : {len(lines)}{' (Vorschau: erste 80)' if truncated else ''}")
    print(f"{separator}\n")
    print(preview)
    if truncated:
        print(f"\n  ... {len(lines) - 80} weitere Zeilen ...")
    print(f"\n{separator}")
    print(f"  Freigabe via: POST /api/v1/tasks/{task_id}/approve-diff")
    print(f"  Diff abrufen: GET  /api/v1/tasks/{task_id}/diff")
    print(f"{separator}\n")
