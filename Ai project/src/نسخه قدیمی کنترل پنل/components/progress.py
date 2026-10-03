"""control_panel/components/progress.py"""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from qfluentwidgets import IndeterminateProgressBar, ProgressBar


class ProgressView(QWidget):
    """Indeterminate or determinate progress bar with a status label,
    for any long-running operation (build, script run, test run, ...)."""

    def __init__(self, parent, theme, label: str = "Working..."):
        super().__init__(parent)
        self.theme = theme

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(6)

        self.label = QLabel(label, self)
        self.label.setFont(theme.font_body)
        layout.addWidget(self.label)

        self._indeterminate = IndeterminateProgressBar(self)
        self._determinate = ProgressBar(self)
        self._determinate.setRange(0, 100)
        layout.addWidget(self._indeterminate)
        layout.addWidget(self._determinate)
        self.label.hide()
        self._indeterminate.hide()
        self._determinate.hide()

        self.theme.themeChanged.connect(self._on_theme_changed)

    def _on_theme_changed(self, mode: str) -> None:
        self.label.setStyleSheet(
            f"color: {self.theme.colors["text"]}; background: transparent;"
        )

    def start(self, label: str | None = None) -> None:
        if label:
            self.label.setText(label)
        self.label.show()
        self._determinate.hide()
        self._indeterminate.show()
        self._indeterminate.start()

    def stop(self, label: str | None = None) -> None:
        self._indeterminate.stop()
        self._indeterminate.hide()
        self._determinate.hide()
        if label:
            self.label.setText(label)
            self.label.show()
        else:
            self.label.hide()

    def set_determinate(self, value: float, label: str | None = None) -> None:
        self._indeterminate.stop()
        self._indeterminate.hide()
        self._determinate.show()
        self._determinate.setValue(int(max(0, min(100, value))))
        if label:
            self.label.setText(label)
        self.label.show()