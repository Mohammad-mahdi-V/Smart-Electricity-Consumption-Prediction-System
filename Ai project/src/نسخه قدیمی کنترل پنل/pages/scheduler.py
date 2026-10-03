"""control_panel/pages/scheduler.py"""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from qfluentwidgets import PushButton

from ..components.auto_refresh import AutoRefreshControl
from ..components.cards import Card, SectionHeader
from ..components.terminal import TerminalOutput
from ..services import scheduler_service


class SchedulerPage(QWidget):
    def __init__(self, parent, theme, app):
        super().__init__(parent)
        self.theme = theme
        self.app = app
        self._build()
        self.theme.themeChanged.connect(self._on_theme_changed)
        self.refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        top = QHBoxLayout()
        top.addWidget(SectionHeader(
            self, self.theme, "Scheduler",
            "Status is read from scheduler_state.json / scheduler.log -- never guessed.",
        ))
        top.addStretch(1)
        self.auto_refresh = AutoRefreshControl(self, self.theme, self.refresh)
        top.addWidget(self.auto_refresh)
        refresh_btn = PushButton("Refresh", self)
        refresh_btn.clicked.connect(self.refresh)
        top.addWidget(refresh_btn)
        outer.addLayout(top)

        # card_holder mirrors the old ttk.Frame that the single status
        # Card was repacked into on every refresh() -- here it's a plain
        # container widget whose layout is cleared and rebuilt the same
        # way system_log.py rebuilds its timeline rows.
        self.card_holder = QWidget(self)
        self.card_holder_layout = QVBoxLayout(self.card_holder)
        self.card_holder_layout.setContentsMargins(0, 0, 0, 0)
        self.card_holder_layout.setSpacing(0)
        outer.addWidget(self.card_holder)

        outer.addWidget(SectionHeader(self, self.theme, "Recent scheduler.log"))
        self.log_output = TerminalOutput(self, self.theme, height=18)
        outer.addWidget(self.log_output, 1)

    def refresh(self) -> None:
        while self.card_holder_layout.count():
            item = self.card_holder_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        state = scheduler_service.get_scheduler_state()
        systemd_status = scheduler_service.get_systemd_status()

        card = Card(self.card_holder, self.theme, padding=16)
        body = card.body

        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(2)

        if not state.get("available"):
            no_state_label = QLabel(
                "No scheduler_state.json found yet -- the scheduler has not run.", body,
            )
            no_state_label.setStyleSheet(f"color: {self.theme.colors['text']};")
            body_layout.addWidget(no_state_label)
        else:
            fields = [
                ("Last Run", state.get("last_run")),
                ("Last Completed (retraining)", state.get("last_completed")),
                ("Last Promotion", state.get("last_promotion")),
                ("Last Failure", state.get("last_failure")),
                ("Last Exit Code", state.get("last_exit_code")),
                ("Last Result", state.get("last_result")),
                ("Last Prediction", state.get("last_prediction")),
                ("Last Prediction Exit Code", state.get("last_prediction_exit_code")),
                ("Last Prediction Result", state.get("last_prediction_result")),
            ]

            grid = QGridLayout()
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(4)
            for row_index, (label, value) in enumerate(fields):
                label_widget = QLabel(label, body)
                label_widget.setMinimumWidth(220)
                label_widget.setStyleSheet(f"color: {self.theme.colors['text_muted']};")
                grid.addWidget(label_widget, row_index, 0)

                value_widget = QLabel(str(value) if value is not None else "—", body)
                value_widget.setStyleSheet(f"color: {self.theme.colors['text']};")
                grid.addWidget(value_widget, row_index, 1)
            grid.setColumnStretch(1, 1)
            body_layout.addLayout(grid)

        systemd_row = QHBoxLayout()
        systemd_row.setContentsMargins(0, 10, 0, 0)
        systemd_label = QLabel("systemd", body)
        systemd_label.setMinimumWidth(220)
        systemd_label.setStyleSheet(f"color: {self.theme.colors['text_muted']};")
        systemd_row.addWidget(systemd_label)
        systemd_value = QLabel(systemd_status, body)
        systemd_value.setStyleSheet(f"color: {self.theme.colors['text']};")
        systemd_row.addWidget(systemd_value)
        systemd_row.addStretch(1)
        body_layout.addLayout(systemd_row)

        card.finalize()
        self.card_holder_layout.addWidget(card)

        self.log_output.clear()
        for line in scheduler_service.get_recent_log_lines(300):
            self.log_output.append_line(line)

    def _on_theme_changed(self, mode: str) -> None:
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """Optional hook the main window calls after a light/dark toggle
        (see app.py's _on_theme_changed), same pattern as errors.py and
        system_log.py -- labels here use raw hex from theme.colors, so
        just rebuild the card and log."""
        self.auto_refresh.refresh_theme()
        self.refresh()