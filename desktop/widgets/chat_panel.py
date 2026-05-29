"""Chat-Panel links: Verlauf + Eingabe."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ChatPanel(QWidget):
    send_requested = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        self.history.setPlaceholderText("Chat-Verlauf …")

        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("Anforderung in natürlicher Sprache …")
        self.input.setMaximumHeight(100)

        self.send_btn = QPushButton("Senden")
        self.send_btn.clicked.connect(self._on_send)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(self.send_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.history, stretch=1)
        layout.addWidget(self.input)
        layout.addLayout(btn_row)

    def append_user(self, text: str) -> None:
        self.history.appendPlainText(f"Du: {text}")

    def append_assistant(self, text: str) -> None:
        self.history.appendPlainText(f"ECHO: {text}")
        self.history.appendPlainText("")

    def clear_input(self) -> None:
        self.input.clear()

    def input_text(self) -> str:
        return self.input.toPlainText().strip()

    def _on_send(self) -> None:
        text = self.input_text()
        if text:
            self.send_requested.emit(text)
