"""Read-only Diff-Anzeige (monospace)."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget


class DiffPanel(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._title = QLabel("Git Diff (Gate 2)")
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlaceholderText("Diff erscheint nach Worker-Lauf …")
        font = QFont("Consolas")
        if not font.exactMatch():
            font = QFont("Courier New")
        self.text.setFont(font)

        layout = QVBoxLayout(self)
        layout.addWidget(self._title)
        layout.addWidget(self.text, stretch=1)

    def set_diff(self, diff_data: dict) -> None:
        diff = diff_data.get("diff", "") or ""
        if not diff:
            self.text.setPlainText("Kein Diff — Worker hat keine Dateien verändert.")
            return
        branch = diff_data.get("branch") or "?"
        lines_count = diff_data.get("diff_lines", len(diff.splitlines()))
        header = f"Branch: {branch}  |  {lines_count} Zeilen\n{'─' * 60}\n"
        self.text.setPlainText(header + diff)

    def clear(self) -> None:
        self.text.clear()
