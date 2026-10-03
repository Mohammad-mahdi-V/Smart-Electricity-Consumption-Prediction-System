"""control_panel/pages/dashboard.py"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import CheckBox, LineEdit, PushButton

from ..components.cards import MetricCard, SectionHeader
from ..components.status_badges import StatusBadge
from ..services import project_service


class DashboardPage(QWidget):
    """Dashboard page.

    The page does not paint its own solid background.
    The FluentWindow controls the main application background while
    cards provide their own surfaces.
    """

    def __init__(self, parent, theme, app):
        super().__init__(parent)

        self.theme = theme
        self.app = app

        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.timeout.connect(self.refresh)

        self._build()
        self.theme.themeChanged.connect(self._on_theme_changed)
        self.refresh()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        # Let the FluentWindow paint the single, shared application
        # background.  QWidget can otherwise use the platform palette
        # (often white), which makes Dashboard look different from the
        # other pages, especially in dark mode.
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.setAutoFillBackground(False)
        self.setStyleSheet("background: transparent;")

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(12)

        # --------------------------------------------------------------
        # Header
        # --------------------------------------------------------------

        header = QHBoxLayout()
        header.setSpacing(8)

        header.addWidget(
            SectionHeader(
                self,
                self.theme,
                "Dashboard",
                "Device metrics from MySQL; model info from project files.",
            )
        )

        header.addStretch(1)

        self.auto_refresh_check = CheckBox(
            "Auto Refresh",
            self,
        )
        self.auto_refresh_check.toggled.connect(
            self._toggle_auto_refresh
        )
        header.addWidget(self.auto_refresh_check)

        self.interval_edit = LineEdit(self)
        self.interval_edit.setText("10")
        self.interval_edit.setFixedWidth(50)
        header.addWidget(self.interval_edit)

        self.interval_label = QLabel(
            "sec",
            self,
        )
        self.interval_label.setStyleSheet(
            f"color: {self.theme.colors['text_muted']};"
        )
        header.addWidget(self.interval_label)

        refresh_button = PushButton(
            "Refresh",
            self,
        )
        refresh_button.clicked.connect(self.refresh)
        header.addWidget(refresh_button)

        main_layout.addLayout(header)

        # --------------------------------------------------------------
        # Scroll area
        # --------------------------------------------------------------

        self.scroll = QScrollArea(self)

        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(
            QScrollArea.Shape.NoFrame
        )
        self.scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        # Important:
        # QScrollArea has its own viewport. Without making the viewport
        # transparent, it can paint the default white background over
        # the FluentWindow background.
        self.scroll.setStyleSheet(
            """
            QScrollArea {
                border: none;
                background: transparent;
            }

            QAbstractScrollArea::viewport {
                background: transparent;
                border: none;
            }
            """
        )

        self.scroll.viewport().setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )

        # --------------------------------------------------------------
        # Scroll content
        # --------------------------------------------------------------

        self.body = QWidget()
        self.body.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.body.setAutoFillBackground(False)
        self.body.setStyleSheet("background: transparent;")

        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(16)

        # --------------------------------------------------------------
        # System status
        # --------------------------------------------------------------

        self.status_container = QWidget()
        self.status_container.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.status_container.setAutoFillBackground(False)
        self.status_container.setStyleSheet("background: transparent;")

        self.status_layout = QHBoxLayout(
            self.status_container
        )
        self.status_layout.setContentsMargins(
            0, 0, 0, 0
        )
        self.status_layout.setSpacing(8)

        body_layout.addWidget(
            self.status_container
        )

        # --------------------------------------------------------------
        # Metrics
        # --------------------------------------------------------------

        self.metrics_container = QWidget()
        self.metrics_container.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )
        self.metrics_container.setAutoFillBackground(False)
        self.metrics_container.setStyleSheet("background: transparent;")

        self.metrics_layout = QHBoxLayout(
            self.metrics_container
        )
        self.metrics_layout.setContentsMargins(
            0, 0, 0, 0
        )
        self.metrics_layout.setSpacing(8)

        body_layout.addWidget(
            self.metrics_container
        )

        # --------------------------------------------------------------
        # Recent errors
        # --------------------------------------------------------------

        errors_section = QWidget()

        errors_layout = QVBoxLayout(
            errors_section
        )
        errors_layout.setContentsMargins(
            0, 0, 0, 0
        )
        errors_layout.setSpacing(8)

        errors_layout.addWidget(
            SectionHeader(
                errors_section,
                self.theme,
                "Recent Errors",
            )
        )

        self.errors_holder = QWidget()

        self.errors_layout = QVBoxLayout(
            self.errors_holder
        )
        self.errors_layout.setContentsMargins(
            0, 0, 0, 0
        )
        self.errors_layout.setSpacing(2)

        errors_layout.addWidget(
            self.errors_holder
        )

        body_layout.addWidget(
            errors_section
        )

        body_layout.addStretch(1)

        self.scroll.setWidget(self.body)

        main_layout.addWidget(
            self.scroll,
            1,
        )

    # ------------------------------------------------------------------
    # Auto refresh
    # ------------------------------------------------------------------

    def _toggle_auto_refresh(
        self,
        checked: bool,
    ) -> None:
        if checked:
            self._schedule_auto_refresh()
        else:
            self._auto_refresh_timer.stop()

    def _schedule_auto_refresh(self) -> None:
        try:
            seconds = max(
                2,
                int(self.interval_edit.text()),
            )
        except ValueError:
            seconds = 10

        self._auto_refresh_timer.start(
            seconds * 1000
        )

    # ------------------------------------------------------------------
    # Layout helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)

            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

            child_layout = item.layout()

            if child_layout is not None:
                while child_layout.count():
                    child_item = child_layout.takeAt(0)

                    child_widget = child_item.widget()

                    if child_widget is not None:
                        child_widget.deleteLater()

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        try:
            snapshot = (
                project_service.get_dashboard_snapshot()
            )
        except Exception as exc:  # noqa: BLE001
            self.app.show_error(
                "Dashboard failed to load",
                str(exc),
            )
            return

        self._clear_layout(
            self.status_layout
        )
        self._clear_layout(
            self.metrics_layout
        )
        self._clear_layout(
            self.errors_layout
        )

        # --------------------------------------------------------------
        # System status
        # --------------------------------------------------------------

        status = snapshot.get(
            "system_status",
            "ERROR",
        )

        badge = StatusBadge(
            self.status_container,
            self.theme,
            status,
            f"System Status: {status}",
            surface=False,
        )

        self.status_layout.addWidget(
            badge
        )

        self.status_layout.addStretch(1)

        # --------------------------------------------------------------
        # Metrics
        # --------------------------------------------------------------

        devices = snapshot.get(
            "devices",
            snapshot.get("users", {}),
        )
        database = snapshot.get(
            "database",
            {},
        )

        # Prefer live DB device count when available
        total_devices = devices.get("total", "—")
        if database.get("available") and database.get("device_count") is not None:
            total_devices = database.get("device_count", total_devices)

        metrics = [
            (
                "Total Devices",
                total_devices,
            ),
            (
                "Ready",
                devices.get(
                    "READY",
                    "—",
                ),
            ),
            (
                "Low Data",
                devices.get(
                    "LOW_DATA",
                    "—",
                ),
            ),
            (
                "No Data",
                devices.get(
                    "NO_DATA",
                    "—",
                ),
            ),
            (
                "Missing Recent",
                devices.get(
                    "MISSING_RECENT_DATA",
                    "—",
                ),
            ),
            (
                "DB Rows",
                (
                    database.get("device_data_rows", "—")
                    if database.get("available")
                    else "—"
                ),
            ),
            (
                "Predictions",
                (
                    database.get("nightly_predictions_rows", "—")
                    if database.get("available")
                    else "—"
                ),
            ),
            (
                "Daily Actuals",
                (
                    database.get("daily_actuals_rows", "—")
                    if database.get("available")
                    else "—"
                ),
            ),
            (
                "Recent Errors",
                snapshot.get(
                    "recent_error_count",
                    0,
                ),
            ),
        ]

        for label, value in metrics:
            card = MetricCard(
                self.metrics_container,
                self.theme,
                label,
                str(value),
            )

            self.metrics_layout.addWidget(
                card,
                1,
            )

        # --------------------------------------------------------------
        # Recent errors
        # --------------------------------------------------------------

        recent_errors = snapshot.get(
            "recent_errors",
            [],
        )

        if not recent_errors:
            label = QLabel(
                "No recent errors.",
                self.errors_holder,
            )

            label.setStyleSheet(
                f"color: {self.theme.colors['text_muted']};"
            )

            self.errors_layout.addWidget(
                label
            )
        else:
            for error in reversed(
                recent_errors
            ):
                self._add_error_row(
                    error
                )

    # ------------------------------------------------------------------
    # Error rows
    # ------------------------------------------------------------------

    def _add_error_row(
        self,
        error: dict,
    ) -> None:
        row = QWidget(
            self.errors_holder
        )

        layout = QHBoxLayout(row)
        layout.setContentsMargins(
            0,
            2,
            0,
            2,
        )
        layout.setSpacing(8)

        timestamp = QLabel(
            error.get(
                "timestamp",
                "",
            ),
            row,
        )

        timestamp.setMinimumWidth(
            180
        )
        timestamp.setStyleSheet(
            f"color: {self.theme.colors['text_muted']};"
        )

        layout.addWidget(
            timestamp
        )

        message = QLabel(
            error.get(
                "message",
                "",
            ),
            row,
        )

        message.setWordWrap(True)
        message.setStyleSheet(
            f"color: {self.theme.colors['text']};"
        )

        layout.addWidget(
            message,
            1,
        )

        self.errors_layout.addWidget(
            row
        )

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def _on_theme_changed(self, mode: str) -> None:
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """Refresh Dashboard text colors after a theme change."""

        self.interval_label.setStyleSheet(
            f"color: {self.theme.colors['text_muted']};"
        )

        self.refresh()