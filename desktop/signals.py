"""Qt-Signals für Orchestrator-Fortschritt (Main Thread)."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class OrchestratorSignals(QObject):
    """Signale vom Background-Worker zum MainWindow."""

    log_message = Signal(str)
    status_changed = Signal(str)
    plan_ready = Signal(object)  # PlanResult
    plan_failed = Signal(str)
    tasks_submitted = Signal(list)  # list[SubmitTaskResponse]
    task_response = Signal(object)  # SubmitTaskResponse
    task_status = Signal(object)  # TaskStatusResponse
    diff_ready = Signal(object)  # dict
    diff_updated = Signal(str)
    task_updated = Signal(object)
    busy_changed = Signal(bool)
    operation_failed = Signal(str)
    operation_finished = Signal()
