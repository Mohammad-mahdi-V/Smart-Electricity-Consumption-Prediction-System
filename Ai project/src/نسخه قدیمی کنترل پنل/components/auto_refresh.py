"""control_panel/components/auto_refresh.py

Reusable "Auto Refresh" checkbox + interval (sec) control, originally
built only for the Dashboard page. Any page that has its own
``refresh()``/reload method can drop this into its header layout to
get the same periodic-refresh behavior.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from qfluentwidgets import CheckBox, LineEdit


class AutoRefreshControl(QWidget):
    """Checkbox + interval field that calls ``on_refresh`` on a timer
    while checked. Stop the timer (e.g. on page teardown) with ``stop()``.
    """

    def __init__(
        self,
        parent,
        theme,
        on_refresh,
        default_seconds: int = 10,
    ):
        super().__init__(parent)
        self.theme = theme
        self._on_refresh = on_refresh

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_refresh)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.check = CheckBox("Auto Refresh", self)
        self.check.toggled.connect(self._toggle)
        layout.addWidget(self.check)

        self.interval_edit = LineEdit(self)
        self.interval_edit.setText(str(default_seconds))
        self.interval_edit.setFixedWidth(50)
        layout.addWidget(self.interval_edit)

        self.interval_label = QLabel("sec", self)
        self.interval_label.setStyleSheet(
            f"color: {self.theme.colors['text_muted']};"
        )
        layout.addWidget(self.interval_label)

    def _toggle(self, checked: bool) -> None:
        if checked:
            self._schedule()
        else:
            self._timer.stop()

    def _schedule(self) -> None:
        try:
            seconds = max(2, int(self.interval_edit.text()))
        except ValueError:
            seconds = 10

        self._timer.start(seconds * 1000)

    def stop(self) -> None:
        self._timer.stop()

    def refresh_theme(self) -> None:
        self.interval_label.setStyleSheet(
            f"color: {self.theme.colors['text_muted']};"
        )
