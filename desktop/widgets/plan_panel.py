from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget


class PlanPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = QLabel("Plan / Task output")
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addWidget(self._text, stretch=1)

    def set_text(self, text: str) -> None:
        self._text.setPlainText(text)


class DiffView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = QLabel("Diff (read-only)")
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        font = QFont("Consolas")
        if not font.family():
            font = QFont("Courier New")
        self._text.setFont(font)
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addWidget(self._text, stretch=1)

    def set_diff(self, diff: str) -> None:
        if not diff:
            self._text.setPlainText("(kein Diff)")
        else:
            self._text.setPlainText(diff)


class LogView(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = QLabel("Live Log")
        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        font = QFont("Consolas")
        if not font.family():
            font = QFont("Courier New")
        self._text.setFont(font)
        layout = QVBoxLayout(self)
        layout.addWidget(self._label)
        layout.addWidget(self._text, stretch=1)

    def append(self, line: str) -> None:
        self._text.appendPlainText(line)
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())
