from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class GateButtons(QWidget):
    plan_approve = Signal()
    plan_reject = Signal()
    gate1_approve = Signal()
    gate1_reject = Signal()
    gate2_approve = Signal()
    gate2_reject = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._plan_ok = QPushButton("Plan freigeben (Gate 0)")
        self._plan_no = QPushButton("Plan ablehnen")
        self._g1_ok = QPushButton("Gate 1: Worker starten")
        self._g1_no = QPushButton("Gate 1: Ablehnen")
        self._g2_ok = QPushButton("Gate 2: Commit + Push")
        self._g2_no = QPushButton("Gate 2: Verwerfen")

        self._plan_ok.clicked.connect(self.plan_approve.emit)
        self._plan_no.clicked.connect(self.plan_reject.emit)
        self._g1_ok.clicked.connect(self.gate1_approve.emit)
        self._g1_no.clicked.connect(self.gate1_reject.emit)
        self._g2_ok.clicked.connect(self.gate2_approve.emit)
        self._g2_no.clicked.connect(self.gate2_reject.emit)

        row0 = QHBoxLayout()
        row0.addWidget(QLabel("Gate 0:"))
        row0.addWidget(self._plan_ok)
        row0.addWidget(self._plan_no)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Gate 1:"))
        row1.addWidget(self._g1_ok)
        row1.addWidget(self._g1_no)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Gate 2:"))
        row2.addWidget(self._g2_ok)
        row2.addWidget(self._g2_no)

        layout = QVBoxLayout(self)
        layout.addLayout(row0)
        layout.addLayout(row1)
        layout.addLayout(row2)

        self.set_gate_enabled("idle")

    def set_gate_enabled(self, phase: str) -> None:
        self._plan_ok.setEnabled(phase == "plan_pending")
        self._plan_no.setEnabled(phase == "plan_pending")
        self._g1_ok.setEnabled(phase == "task_gate1")
        self._g1_no.setEnabled(phase == "task_gate1")
        self._g2_ok.setEnabled(phase == "task_gate2")
        self._g2_no.setEnabled(phase == "task_gate2")
