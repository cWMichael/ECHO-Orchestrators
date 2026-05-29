"""
Dünner Wrapper: UI → OrchestratorService → bestehende Planner/Worker/Git-Logik.
Kein HTTP, keine neuen Server.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

from PySide6.QtCore import QThread, Signal

from desktop.signals import OrchestratorSignals
from models import (
    ApprovePlanRequest,
    ApproveTaskRequest,
    PlanRequest,
    PlanResult,
    TaskStatus,
)
from orchestrator.service import OrchestratorError, OrchestratorService
from project_registry import load_projects as registry_load_projects

DEFAULT_REVIEWER = os.environ.get("ECHO_REVIEWER", "Michael")

STATUS_LABELS = {
    TaskStatus.PENDING: "planning",
    TaskStatus.AWAITING_APPROVAL: "waiting",
    TaskStatus.APPROVED: "running",
    TaskStatus.IN_PROGRESS: "running",
    TaskStatus.PENDING_DIFF: "waiting",
    TaskStatus.COMPLETED: "completed",
    TaskStatus.FAILED: "failed",
    TaskStatus.REJECTED: "failed",
}


def ui_status(raw: TaskStatus | str) -> str:
    if isinstance(raw, TaskStatus):
        return STATUS_LABELS.get(raw, raw.value)
    return STATUS_LABELS.get(TaskStatus(raw), raw) if raw else "idle"


def format_plan(plan: PlanResult | dict) -> str:
    if isinstance(plan, PlanResult):
        data = plan.model_dump()
    else:
        data = plan
    lines = [
        data.get("plan_title", "?"),
        f"Plan-ID: {data.get('plan_id', '?')}",
        "",
        data.get("summary", ""),
        "",
        f"Geschätzte Tokens: ~{data.get('estimated_total_tokens', 0)}",
        "",
        "Tasks:",
    ]
    for i, t in enumerate(data.get("tasks", []), 1):
        lines.append(
            f"  {i}. {t.get('title', '?')} — {t.get('worker_type', '?')} "
            f"({t.get('priority', '?')})"
        )
        if t.get("rationale"):
            lines.append(f"     {t['rationale']}")
    return "\n".join(lines)


def format_task_summary(task: dict, message: str = "", diff_data: dict | None = None) -> str:
    lines = [
        f"Task: {task.get('title', '?')}",
        f"Status: {task.get('status', '?')}",
        f"Task-ID: {task.get('task_id', '?')}",
        f"Worker: {task.get('worker_type', '?')}",
    ]
    if message:
        lines.append(f"Meldung: {message}")
    if diff_data and diff_data.get("branch"):
        lines.append(f"Branch: {diff_data['branch']}")
        lines.append(f"Diff-Zeilen: {diff_data.get('diff_lines', 0)}")
    result = task.get("result")
    if result:
        artifacts = result.get("artifacts") or []
        if artifacts:
            lines.append(f"Geänderte Dateien: {', '.join(artifacts)}")
        output = str(result.get("output", "")).strip()
        if output:
            preview = "\n".join(output.splitlines()[:12])
            if len(output.splitlines()) > 12:
                preview += "\n… (gekürzt)"
            lines.extend(["", "Worker-Output:", preview])
        if result.get("error"):
            lines.append(f"Fehler: {result['error']}")
    return "\n".join(lines)


@dataclass
class SessionState:
    plan_id: str | None = None
    plan: PlanResult | None = None
    task_ids: list[str] = field(default_factory=list)
    active_task_idx: int = 0
    active_task_id: str | None = None
    phase: str = "idle"
    result_display: str = ""


class AsyncRunner(QThread):
    """Führt eine Coroutine in einem Hintergrund-Thread aus."""

    finished_ok = Signal(object)
    finished_err = Signal(str)

    def __init__(self, coro_factory: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        super().__init__()
        self._coro_factory = coro_factory

    def run(self) -> None:
        try:
            result = asyncio.run(self._coro_factory())
            self.finished_ok.emit(result)
        except Exception as exc:
            self.finished_err.emit(str(exc))


class OrchestratorBridge:
    def __init__(self, signals: OrchestratorSignals, reviewer: str = DEFAULT_REVIEWER) -> None:
        self.signals = signals
        self.reviewer = reviewer
        self.session = SessionState()
        self._service: OrchestratorService | None = None
        self._runner: AsyncRunner | None = None

    def _log(self, msg: str) -> None:
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        self.signals.log_message.emit(f"[{ts}] {msg}")

    def _service_or_create(self) -> OrchestratorService:
        if self._service is None:
            self._service = OrchestratorService()
        return self._service

    def try_list_projects(self) -> dict[str, str]:
        try:
            return registry_load_projects()
        except Exception as exc:
            self._log(f"Projekte laden fehlgeschlagen: {exc}")
            return {}

    def set_project(self, name: str) -> str:
        try:
            info = self._service_or_create().set_active_project(name)
            self._log(f"Zielprojekt: {info['name']} → {info['path']}")
            return str(info.get("path", ""))
        except OrchestratorError as exc:
            self._log(f"Projektwechsel fehlgeschlagen: {exc}")
            self.signals.operation_failed.emit(str(exc))
            return ""

    def _set_busy(self, busy: bool) -> None:
        self.signals.busy_changed.emit(busy)

    def _start_async(
        self,
        coro_factory: Callable[[], Coroutine[Any, Any, Any]],
        on_ok: Callable[[Any], None],
        on_err: Callable[[str], None] | None = None,
    ) -> None:
        if self._runner is not None and self._runner.isRunning():
            self._log("Bereits ein Vorgang aktiv — bitte warten.")
            return

        self._set_busy(True)

        def _ok(result: object) -> None:
            self._set_busy(False)
            on_ok(result)

        def _err(msg: str) -> None:
            self._set_busy(False)
            if on_err:
                on_err(msg)
            else:
                self._log(f"Fehler: {msg}")
                self.signals.operation_failed.emit(msg)

        self._runner = AsyncRunner(coro_factory)
        self._runner.finished_ok.connect(_ok)
        self._runner.finished_err.connect(_err)
        self._runner.start()

    def create_plan(self, intent: str) -> None:
        self.session.phase = "planning"
        self.session.result_display = ""
        self.signals.status_changed.emit("planning")
        self._log(f"Planner startet: {intent[:80]}…")

        async def _run() -> PlanResult:
            svc = self._service_or_create()
            req = PlanRequest(intent=intent, reviewer=self.reviewer, context={})
            return await svc.create_plan(req)

        def on_ok(plan: PlanResult) -> None:
            self.session.plan_id = plan.plan_id
            self.session.plan = plan
            self.session.phase = "plan_pending"
            self._log(f"Plan bereit: {plan.plan_title} ({len(plan.tasks)} Tasks)")
            self.signals.plan_ready.emit(plan)
            self.signals.status_changed.emit("waiting (Gate 0)")

        def on_err(msg: str) -> None:
            self.session.phase = "idle"
            self._log(f"Planner-Fehler: {msg}")
            self.signals.plan_failed.emit(msg)
            self.signals.status_changed.emit("failed")

        self._start_async(_run, on_ok, on_err)

    def approve_plan(self, approved: bool) -> None:
        plan_id = self.session.plan_id
        if not plan_id:
            self._log("Kein Plan zum Freigeben.")
            return

        async def _run() -> list:
            svc = self._service_or_create()
            req = ApprovePlanRequest(
                approved=approved,
                reviewer=self.reviewer,
                comment="via desktop",
            )
            return await svc.approve_plan(plan_id, req)

        def on_ok(submitted: list) -> None:
            if not approved:
                self.session.phase = "done"
                self._log("Plan abgelehnt.")
                self.signals.status_changed.emit("failed")
                return
            task_ids = [r.task_id for r in submitted]
            self.session.task_ids = task_ids
            self.session.active_task_idx = 0
            self.session.active_task_id = task_ids[0] if task_ids else None
            self.session.phase = "task_gate1"
            self.session.result_display = ""
            self._log(f"Plan freigegeben — {len(task_ids)} Task(s) eingereicht.")
            self.signals.tasks_submitted.emit(submitted)
            self.signals.status_changed.emit("waiting (Gate 1)")

        self._start_async(_run, on_ok)

    def approve_task_gate1(self, approved: bool) -> None:
        task_id = self.session.active_task_id
        if not task_id:
            self._log("Kein aktiver Task für Gate 1.")
            return

        async def _run() -> tuple[Any, Any]:
            svc = self._service_or_create()
            req = ApproveTaskRequest(
                approved=approved,
                reviewer=self.reviewer,
                comment="Gate 1 via desktop",
            )
            resp = await svc.approve_task(task_id, req)
            task = svc.get_task_status(task_id)
            diff_data = None
            if task.status == TaskStatus.PENDING_DIFF:
                diff_data = svc.get_task_diff(task_id)
            return resp, task, diff_data

        def on_ok(result: tuple) -> None:
            resp, task, diff_data = result
            task_dict = task.model_dump(mode="json")
            if not approved:
                self._log(f"Gate 1 abgelehnt für {task_id[:8]}.")
                self._advance_task()
                self.signals.task_updated.emit({"task": task_dict, "resp": resp.model_dump()})
                return

            self._log(f"Gate 1 OK — Worker fertig, Status: {task.status.value}")
            if task.status == TaskStatus.PENDING_DIFF:
                self.session.phase = "task_gate2"
                diff_text = diff_data.get("diff", "") if diff_data else ""
                self.signals.diff_updated.emit(diff_text)
                self.signals.status_changed.emit("waiting (Gate 2)")
            elif task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.REJECTED):
                summary = format_task_summary(task_dict, resp.message, diff_data)
                self.session.result_display = summary
                self._advance_task()
                self.signals.status_changed.emit(ui_status(task.status))
            self.signals.task_updated.emit({"task": task_dict, "resp": resp.model_dump()})

        def on_err(msg: str) -> None:
            self._log(f"Gate 1 Fehler: {msg}")
            self.signals.operation_failed.emit(msg)
            self.signals.status_changed.emit("failed")

        self._start_async(_run, on_ok, on_err)

    def approve_diff_gate2(self, approved: bool) -> None:
        task_id = self.session.active_task_id
        if not task_id:
            self._log("Kein aktiver Task für Gate 2.")
            return

        async def _run() -> tuple[Any, Any, Any]:
            svc = self._service_or_create()
            diff_data = svc.get_task_diff(task_id)
            req = ApproveTaskRequest(
                approved=approved,
                reviewer=self.reviewer,
                comment="Gate 2 via desktop",
            )
            resp = await svc.approve_diff(task_id, req)
            task = svc.get_task_status(task_id)
            return resp, task, diff_data

        def on_ok(result: tuple) -> None:
            resp, task, diff_data = result
            task_dict = task.model_dump(mode="json")
            if approved:
                summary = format_task_summary(
                    task_dict, resp.message, diff_data if isinstance(diff_data, dict) else None
                )
                self.session.result_display = summary
                self._log(f"Gate 2: Commit OK — {resp.message}")
            else:
                self._log(f"Gate 2: Diff verworfen — {resp.message}")
            self._advance_task()
            self.signals.task_updated.emit({"task": task_dict, "resp": resp.model_dump()})
            self.signals.status_changed.emit(ui_status(task.status))

        self._start_async(_run, on_ok)

    def refresh_diff(self) -> None:
        task_id = self.session.active_task_id
        if not task_id:
            return

        async def _run() -> str:
            svc = self._service_or_create()
            data = svc.get_task_diff(task_id)
            return data.get("diff", "") or ""

        def on_ok(diff: str) -> None:
            self.signals.diff_updated.emit(diff)

        self._start_async(_run, on_ok)

    def _advance_task(self) -> None:
        idx = self.session.active_task_idx + 1
        ids = self.session.task_ids
        if idx < len(ids):
            self.session.active_task_idx = idx
            self.session.active_task_id = ids[idx]
            self.session.phase = "task_gate1"
            self.session.result_display = ""
            self._log(f"Nächster Task: {ids[idx][:8]} — Gate 1")
            self.signals.status_changed.emit("waiting (Gate 1)")
        else:
            self.session.active_task_id = None
            self.session.phase = "done"
            self.signals.status_changed.emit("completed")
