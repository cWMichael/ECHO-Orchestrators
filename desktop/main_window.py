"""Hauptfenster — Chat links, Plan/Diff/Log rechts."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from desktop.orchestrator_bridge import OrchestratorBridge, format_plan, format_task_summary
from desktop.signals import OrchestratorSignals
from desktop.widgets.chat_panel import ChatPanel
from desktop.widgets.gate_buttons import GateButtons
from desktop.widgets.plan_panel import DiffView, LogView, PlanPanel
from desktop.widgets.project_selector import ProjectSelector


class MainWindow(QMainWindow):
    def __init__(self, reviewer: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("ECHO Orchestrator — Desktop V1")
        self.resize(1100, 720)

        self._signals = OrchestratorSignals()
        self._bridge = OrchestratorBridge(
            self._signals,
            reviewer=reviewer or os.environ.get("ECHO_REVIEWER", "Michael"),
        )

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        top = QHBoxLayout()
        self._project = ProjectSelector()
        self._status = QLabel("Status: idle")
        self._status.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        top.addWidget(self._project, stretch=1)
        top.addWidget(self._status, stretch=1)
        root.addLayout(top)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        self._chat = ChatPanel()
        splitter.addWidget(self._chat)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        self._plan = PlanPanel()
        self._gates = GateButtons()
        self._diff = DiffView()
        self._log = LogView()
        right_layout.addWidget(self._plan, stretch=2)
        right_layout.addWidget(self._gates)
        right_layout.addWidget(self._diff, stretch=2)
        right_layout.addWidget(self._log, stretch=1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)

        root.addWidget(splitter, stretch=1)

        self._wire_ui()
        self._wire_signals()
        self._load_projects()

    def _wire_ui(self) -> None:
        self._chat.send_btn.clicked.connect(self._on_send)
        self._project.combo.currentTextChanged.connect(self._on_project_changed)
        self._project.reload_button.clicked.connect(self._load_projects)

        self._gates.plan_approve.connect(lambda: self._bridge.approve_plan(True))
        self._gates.plan_reject.connect(lambda: self._bridge.approve_plan(False))
        self._gates.gate1_approve.connect(lambda: self._bridge.approve_task_gate1(True))
        self._gates.gate1_reject.connect(lambda: self._bridge.approve_task_gate1(False))
        self._gates.gate2_approve.connect(lambda: self._bridge.approve_diff_gate2(True))
        self._gates.gate2_reject.connect(lambda: self._bridge.approve_diff_gate2(False))

    def _wire_signals(self) -> None:
        self._signals.log_message.connect(self._log.append)
        self._signals.status_changed.connect(self._on_status)
        self._signals.plan_ready.connect(self._on_plan_ready)
        self._signals.plan_failed.connect(self._on_plan_failed)
        self._signals.tasks_submitted.connect(self._on_tasks_submitted)
        self._signals.diff_updated.connect(self._diff.set_diff)
        self._signals.task_updated.connect(self._on_task_updated)
        self._signals.operation_failed.connect(self._on_operation_failed)
        self._signals.busy_changed.connect(self._on_busy)

    def _load_projects(self) -> None:
        projects = self._bridge.try_list_projects()
        active = None
        try:
            info = self._bridge._service_or_create().get_active_project()
            active = info.get("name")
        except Exception:
            pass
        if not active and projects:
            active = next(iter(projects))
            path = self._bridge.set_project(active)
            if path:
                self._project.set_path_hint(path)
        self._project.set_projects(projects, active)
        if active and active in projects:
            self._project.set_path_hint(projects.get(active, ""))

    def _on_project_changed(self, name: str) -> None:
        if not name:
            return
        path = self._bridge.set_project(name)
        if path:
            self._project.set_path_hint(path)

    def _on_send(self) -> None:
        text = self._chat.input_text()
        if not text:
            return
        if len(text) < 10:
            self._chat.append_assistant("Mindestens 10 Zeichen für den Planner.")
            return
        if not self._project.current_project():
            self._chat.append_assistant("Bitte zuerst ein Zielprojekt wählen.")
            return

        self._chat.append_user(text)
        self._chat.clear_input()
        self._plan.set_text("_Planner läuft (Ollama) …_")
        self._gates.set_gate_enabled("planning")
        self._bridge.create_plan(text)

    def _on_status(self, status: str) -> None:
        self._status.setText(f"Status: {status}")
        phase = self._bridge.session.phase
        self._gates.set_gate_enabled(phase)

    def _on_plan_ready(self, plan) -> None:
        self._plan.set_text(format_plan(plan))
        self._chat.append_assistant(
            f"Plan «{plan.plan_title}» mit {len(plan.tasks)} Task(s). Gate 0: freigeben oder ablehnen."
        )
        self._gates.set_gate_enabled("plan_pending")

    def _on_plan_failed(self, msg: str) -> None:
        self._plan.set_text(f"Planner-Fehler:\n{msg}")
        self._chat.append_assistant(f"Planner-Fehler: {msg}")
        self._gates.set_gate_enabled("idle")

    def _on_tasks_submitted(self, submitted: list) -> None:
        if not submitted:
            return
        ids = ", ".join(r.task_id[:8] for r in submitted)
        self._chat.append_assistant(
            f"{len(submitted)} Task(s) eingereicht ({ids}…). Gate 1: Worker freigeben."
        )
        if self._bridge.session.plan:
            self._plan.set_text(format_plan(self._bridge.session.plan))
        self._gates.set_gate_enabled("task_gate1")

    def _on_task_updated(self, payload: dict) -> None:
        task = payload.get("task", {})
        resp = payload.get("resp", {})
        summary = format_task_summary(task, resp.get("message", ""))
        if self._bridge.session.result_display:
            self._plan.set_text(self._bridge.session.result_display)
        elif summary:
            self._plan.set_text(summary)
        phase = self._bridge.session.phase
        self._gates.set_gate_enabled(phase)
        if phase == "task_gate2":
            self._bridge.refresh_diff()

    def _on_operation_failed(self, msg: str) -> None:
        self._chat.append_assistant(f"Fehler: {msg}")

    def _on_busy(self, busy: bool) -> None:
        self._chat.send_btn.setEnabled(not busy)
        self._project.combo.setEnabled(not busy)
