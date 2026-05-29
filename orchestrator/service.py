"""
Minimaler Service-Layer — extrahiert aus planner_router / core_router / project_registry.
Kein FastAPI, keine HTTPException. Desktop und (später) Router können hier importieren.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from config import Settings, get_settings
from git_manager import GitManager, GitOperationError
from models import (
    ApprovePlanRequest,
    ApproveTaskRequest,
    HumanApproval,
    ModelBackend,
    PlanRequest,
    PlanResult,
    SubmitTaskRequest,
    SubmitTaskResponse,
    TaskPayload,
    TaskState,
    TaskStatus,
    TaskStatusResponse,
    WorkerType,
)
from planner import Planner, PlannerError
from project_registry import get_active_project_name, load_projects, resolve_project_path
from task_store import get_store

logger = logging.getLogger("echo.orchestrator_service")

# Flüchtige Laufzeit-State (wie in core_router / planner_router)
_pending_plans: dict[str, PlanResult] = {}
_task_branches: dict[str, str] = {}
_task_diffs: dict[str, str] = {}


class OrchestratorError(RuntimeError):
    """Business- oder Pipeline-Fehler ohne HTTP-Semantik."""


ServiceError = OrchestratorError


# ── Complexity / Worker (aus core_router) ─────────────────────────────────────

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


def _get_git_manager(settings: Settings) -> GitManager | None:
    try:
        return GitManager(repo_path=settings.project_root)
    except GitOperationError as exc:
        logger.warning("GitManager nicht verfügbar: %s", exc)
        return None


class OrchestratorService:
    """Direkte Orchestrierung für Desktop-UI (ein Task zur Zeit)."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    # ── Projekte ──────────────────────────────────────────────────────────────

    def list_projects(self) -> dict[str, str]:
        return load_projects()

    def get_active_project(self) -> dict[str, str | None]:
        return {
            "name": get_active_project_name(),
            "path": self.settings.project_root,
        }

    def set_active_project(self, name: str) -> dict[str, str | None]:
        try:
            path = resolve_project_path(name)
        except KeyError as exc:
            raise OrchestratorError(str(exc)) from exc
        except ValueError as exc:
            raise OrchestratorError(str(exc)) from exc
        self.settings = get_settings()
        return {"name": name, "path": path}

    # ── Planner (Gate 0) ──────────────────────────────────────────────────────

    async def create_plan(self, request: PlanRequest) -> PlanResult:
        planner = Planner(self.settings)
        try:
            result = await planner.create_plan(request)
        except PlannerError as exc:
            raise OrchestratorError(str(exc)) from exc
        finally:
            await planner.close()

        _pending_plans[result.plan_id] = result
        logger.info("Plan %s gespeichert (%d Tasks).", result.plan_id, len(result.tasks))
        return result

    def get_plan(self, plan_id: str) -> PlanResult:
        plan = _pending_plans.get(plan_id)
        if plan is None:
            raise OrchestratorError(f"Plan '{plan_id}' nicht gefunden oder bereits ausgeführt.")
        return plan

    async def approve_plan(
        self,
        plan_id: str,
        request: ApprovePlanRequest,
    ) -> list[SubmitTaskResponse]:
        plan = _pending_plans.get(plan_id)
        if plan is None:
            raise OrchestratorError(f"Plan '{plan_id}' nicht gefunden oder bereits ausgeführt.")

        if not request.approved:
            _pending_plans.pop(plan_id, None)
            logger.info("Plan %s abgelehnt von %s.", plan_id, request.reviewer)
            return []

        indices = request.selected_task_indices
        if indices is not None:
            tasks = [plan.tasks[i] for i in indices if 0 <= i < len(plan.tasks)]
            if not tasks:
                raise OrchestratorError("selected_task_indices enthält keine gültigen Indizes.")
        else:
            tasks = plan.tasks

        submitted: list[SubmitTaskResponse] = []
        for planned in tasks:
            submit_req = SubmitTaskRequest(
                title=planned.title,
                description=planned.description,
                worker_type=planned.worker_type,
                priority=planned.priority,
                context=planned.context,
                files=planned.files,
            )
            submitted.append(await self.submit_task(submit_req))

        _pending_plans.pop(plan_id, None)
        logger.info(
            "Plan %s freigegeben von %s — %d Task(s) eingereicht.",
            plan_id,
            request.reviewer,
            len(submitted),
        )
        return submitted

    # ── Tasks ─────────────────────────────────────────────────────────────────

    async def submit_task(self, request: SubmitTaskRequest) -> SubmitTaskResponse:
        payload = TaskPayload(**request.model_dump())
        score = _compute_complexity(payload)
        backend = _assign_backend(score, self.settings)

        git = _get_git_manager(self.settings)
        branch_name: str | None = None

        if git is not None:
            try:
                branch_name = await asyncio.to_thread(
                    git.create_feature_branch, payload.task_id
                )
                _task_branches[payload.task_id] = branch_name
            except GitOperationError as exc:
                raise OrchestratorError(f"Git-Fehler beim Branch-Erstellen: {exc}") from exc

        initial_status = (
            TaskStatus.APPROVED
            if self.settings.bypass_human_gate
            else TaskStatus.AWAITING_APPROVAL
        )
        state = TaskState(
            payload=payload,
            status=initial_status,
            model_backend=backend,
            complexity_score=score,
        )
        get_store().set(payload.task_id, state)

        msg = (
            "Task wurde auf Feature-Branch isoliert und wartet auf Freigabe."
            if not self.settings.bypass_human_gate
            else f"Task auto-approved. Branch: {branch_name or 'n/a'}."
        )
        return SubmitTaskResponse(
            task_id=payload.task_id,
            status=state.status,
            message=msg,
        )

    async def approve_task(
        self,
        task_id: str,
        request: ApproveTaskRequest,
    ) -> SubmitTaskResponse:
        state = get_store().get(task_id)
        if state is None:
            raise OrchestratorError(f"Task '{task_id}' nicht gefunden.")
        if state.status not in (TaskStatus.AWAITING_APPROVAL, TaskStatus.APPROVED):
            raise OrchestratorError(
                f"Task hat Status '{state.status}' und kann nicht freigegeben werden."
            )

        approval = HumanApproval(
            task_id=task_id,
            approved=request.approved,
            reviewer=request.reviewer,
            comment=request.comment,
        )
        state.approval = approval

        if not request.approved:
            state.status = TaskStatus.REJECTED
            get_store().set(task_id, state)

            git = _get_git_manager(self.settings)
            branch_name = _task_branches.get(task_id)
            if git is not None and branch_name:
                try:
                    await asyncio.to_thread(git.discard_and_delete_branch, branch_name)
                except GitOperationError as exc:
                    logger.error("Branch '%s' konnte nicht gelöscht werden: %s", branch_name, exc)

            return SubmitTaskResponse(
                task_id=task_id,
                status=state.status,
                message=f"Task von {request.reviewer} abgelehnt. Feature-Branch verworfen.",
            )

        state.status = TaskStatus.IN_PROGRESS
        get_store().set(task_id, state)

        try:
            worker = _get_worker(
                state.payload.worker_type,
                state.model_backend,  # type: ignore[arg-type]
                self.settings,
            )
            result = await worker.execute(state.payload)
            state.result = result
            get_store().set(task_id, state)
        except Exception as exc:
            state.status = TaskStatus.FAILED
            get_store().set(task_id, state)

            git = _get_git_manager(self.settings)
            branch_name = _task_branches.get(task_id)
            if git is not None and branch_name:
                try:
                    await asyncio.to_thread(git.discard_and_delete_branch, branch_name)
                except GitOperationError as cleanup_exc:
                    logger.error("Branch-Cleanup fehlgeschlagen: %s", cleanup_exc)
            raise OrchestratorError(f"Worker-Ausführung fehlgeschlagen: {exc}") from exc

        git = _get_git_manager(self.settings)
        diff = ""
        if git is not None:
            try:
                diff = await asyncio.to_thread(git.get_code_diff)
            except GitOperationError as exc:
                logger.warning("git diff fehlgeschlagen: %s", exc)

        if diff:
            _task_diffs[task_id] = diff
            state.status = TaskStatus.PENDING_DIFF
            get_store().set(task_id, state)
            return SubmitTaskResponse(
                task_id=task_id,
                status=state.status,
                message=(
                    f"Worker erfolgreich. {len(diff.splitlines())} Diff-Zeilen "
                    "warten auf Gate-2-Freigabe."
                ),
            )

        if result.success:
            state.status = TaskStatus.COMPLETED
        else:
            state.status = TaskStatus.FAILED
        get_store().set(task_id, state)

        return SubmitTaskResponse(
            task_id=task_id,
            status=state.status,
            message="Task abgeschlossen. Keine Code-Änderungen im Working Tree.",
        )

    async def approve_diff(
        self,
        task_id: str,
        request: ApproveTaskRequest,
    ) -> SubmitTaskResponse:
        state = get_store().get(task_id)
        if state is None:
            raise OrchestratorError(f"Task '{task_id}' nicht gefunden.")
        if state.status != TaskStatus.PENDING_DIFF:
            raise OrchestratorError(
                f"Task hat Status '{state.status}'. "
                "Diff-Freigabe nur im Status PENDING_DIFF möglich."
            )

        git = _get_git_manager(self.settings)
        branch_name = _task_branches.get(task_id)

        if not request.approved:
            state.status = TaskStatus.REJECTED
            get_store().set(task_id, state)

            if git is not None and branch_name:
                try:
                    await asyncio.to_thread(git.discard_and_delete_branch, branch_name)
                except GitOperationError as exc:
                    logger.error("Discard fehlgeschlagen: %s", exc)

            _task_diffs.pop(task_id, None)
            return SubmitTaskResponse(
                task_id=task_id,
                status=state.status,
                message=f"Diff von {request.reviewer} abgelehnt. Branch verworfen.",
            )

        commit_message = (
            f"feat(echo): {state.payload.title}\n\n"
            f"Task-ID: {task_id}\n"
            f"Worker: {state.payload.worker_type}\n"
            f"Backend: {state.model_backend}\n"
            f"Freigegeben von: {request.reviewer}\n"
            + (f"Kommentar: {request.comment}" if request.comment else "")
        )

        commit_hash = ""
        if git is not None:
            try:
                commit_hash = await asyncio.to_thread(git.commit_and_push, commit_message)
            except GitOperationError as exc:
                state.status = TaskStatus.FAILED
                get_store().set(task_id, state)
                raise OrchestratorError(f"Commit/Push fehlgeschlagen: {exc}") from exc

        state.status = TaskStatus.COMPLETED
        get_store().set(task_id, state)
        _task_diffs.pop(task_id, None)

        return SubmitTaskResponse(
            task_id=task_id,
            status=state.status,
            message=(
                f"Code committed und gepusht. "
                f"Commit: {commit_hash[:12] if commit_hash else 'n/a'} | "
                f"Branch: {branch_name or 'n/a'}"
            ),
        )

    def get_task_diff(self, task_id: str) -> dict[str, Any]:
        state = get_store().get(task_id)
        if state is None:
            raise OrchestratorError(f"Task '{task_id}' nicht gefunden.")
        diff = _task_diffs.get(task_id, "")
        return {
            "task_id": task_id,
            "status": state.status,
            "diff": diff,
            "diff_lines": len(diff.splitlines()) if diff else 0,
            "branch": _task_branches.get(task_id),
        }

    def get_task_status(self, task_id: str) -> TaskStatusResponse:
        state = get_store().get(task_id)
        if state is None:
            raise OrchestratorError(f"Task '{task_id}' nicht gefunden.")
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

    async def get_task(self, task_id: str) -> TaskStatusResponse:
        return self.get_task_status(task_id)

    async def get_diff(self, task_id: str) -> dict[str, Any]:
        return self.get_task_diff(task_id)
