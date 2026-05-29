"""Projekt-Dropdown aus projects.json."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget


class ProjectSelector(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._combo = QComboBox()
        self._combo.setMinimumWidth(200)
        self._path_label = QLabel("")
        self._reload_btn = QPushButton("Neu laden")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Projekt:"))
        layout.addWidget(self._combo)
        layout.addWidget(self._reload_btn)
        layout.addWidget(self._path_label, stretch=1)

    @property
    def combo(self) -> QComboBox:
        return self._combo

    @property
    def reload_button(self) -> QPushButton:
        return self._reload_btn

    def set_projects(self, projects: dict[str, str], active: str | None = None) -> None:
        self._combo.blockSignals(True)
        self._combo.clear()
        for key in projects:
            self._combo.addItem(key, key)
        if active and active in projects:
            idx = self._combo.findData(active)
            if idx >= 0:
                self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(False)

    def current_project(self) -> str:
        return self._combo.currentData() or ""

    def set_path_hint(self, text: str) -> None:
        self._path_label.setText(text)
