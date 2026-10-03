"""control_panel/pages/system_log.py"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import PushButton

from ..components.auto_refresh import AutoRefreshControl
from ..components.cards import SectionHeader
from ..services import project_service


class SystemLogPage(QWidget):
    def __init__(self, parent, theme, app):
        super().__init__(parent)

        self.theme = theme
        self.app = app

        self._build()

        # Live theme updates
        self.theme.themeChanged.connect(
            self._on_theme_changed
        )

        self.refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(
            20,
            20,
            20,
            20,
        )
        outer.setSpacing(12)

        # ---------------------------------------------------------
        # Header
        # ---------------------------------------------------------
        top = QHBoxLayout()

        top.addWidget(
            SectionHeader(
                self,
                self.theme,
                "System Log",
                "Timeline of recent operations, from real logs.",
            )
        )

        top.addStretch(1)

        self.auto_refresh = AutoRefreshControl(
            self,
            self.theme,
            self.refresh,
        )
        top.addWidget(
            self.auto_refresh
        )

        self.refresh_btn = PushButton(
            "Refresh",
            self,
        )
        self.refresh_btn.clicked.connect(
            self.refresh
        )
        top.addWidget(
            self.refresh_btn
        )

        outer.addLayout(top)

        # ---------------------------------------------------------
        # Scroll area
        # ---------------------------------------------------------
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(
            QScrollArea.NoFrame
        )

        # Completely transparent scroll area.
        self.scroll.setStyleSheet(
            """
            QScrollArea {
                background: transparent;
                border: none;
            }
            """
        )

        # Completely transparent viewport.
        self.scroll.viewport().setStyleSheet(
            "background: transparent;"
        )

        # ---------------------------------------------------------
        # Timeline container
        # ---------------------------------------------------------
        self.timeline_widget = QWidget()

        self.timeline_widget.setStyleSheet(
            "background: transparent;"
        )

        self.timeline_layout = QVBoxLayout(
            self.timeline_widget
        )

        self.timeline_layout.setContentsMargins(
            0,
            12,
            0,
            0,
        )
        self.timeline_layout.setSpacing(3)

        # Keep rows top-aligned.
        self.timeline_layout.addStretch(1)

        self.scroll.setWidget(
            self.timeline_widget
        )

        outer.addWidget(
            self.scroll,
            1,
        )

        # Initial theme
        self.refresh_theme()

    # -------------------------------------------------------------
    # Theme
    # -------------------------------------------------------------

    def _on_theme_changed(
        self,
        mode: str,
    ) -> None:
        """Refresh colors automatically after a theme change."""
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """Keep backgrounds transparent and update text colors."""

        self.auto_refresh.refresh_theme()

        text = self.theme.colors["text"]
        muted = self.theme.colors["text_muted"]

        # ---------------------------------------------------------
        # Main page
        # ---------------------------------------------------------
        self.setStyleSheet(
            """
            QWidget {
                background: transparent;
            }
            """
        )

        # ---------------------------------------------------------
        # Scroll area
        # ---------------------------------------------------------
        self.scroll.setStyleSheet(
            """
            QScrollArea {
                background: transparent;
                border: none;
            }
            """
        )

        self.scroll.viewport().setStyleSheet(
            """
            background: transparent;
            """
        )

        # ---------------------------------------------------------
        # Timeline container
        # ---------------------------------------------------------
        self.timeline_widget.setStyleSheet(
            """
            background: transparent;
            """
        )

        # ---------------------------------------------------------
        # Existing labels
        # ---------------------------------------------------------
        for label in self.timeline_widget.findChildren(
            QLabel
        ):
            # Status dots have their own status color.
            if label.property("systemLogDot"):
                continue

            # Timestamp
            if label.property(
                "systemLogTimestamp"
            ):
                label.setStyleSheet(
                    f"""
                    color: {muted};
                    background: transparent;
                    """
                )
                continue

            # Empty message
            if label.property(
                "systemLogEmpty"
            ):
                label.setStyleSheet(
                    f"""
                    color: {muted};
                    background: transparent;
                    """
                )
                continue

            # Event message
            label.setStyleSheet(
                f"""
                color: {text};
                background: transparent;
                """
            )

    # -------------------------------------------------------------
    # Refresh
    # -------------------------------------------------------------

    def refresh(self) -> None:
        # Remove existing rows while keeping the trailing stretch.
        while self.timeline_layout.count() > 1:
            item = self.timeline_layout.takeAt(0)

            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        events = project_service.get_system_timeline(
            limit=200
        )

        # ---------------------------------------------------------
        # Empty state
        # ---------------------------------------------------------
        if not events:
            label = QLabel(
                "No events recorded yet.",
                self.timeline_widget,
            )

            label.setProperty(
                "systemLogEmpty",
                True,
            )

            label.setStyleSheet(
                f"""
                color: {self.theme.colors["text_muted"]};
                background: transparent;
                """
            )

            self.timeline_layout.insertWidget(
                0,
                label,
            )

            return

        # ---------------------------------------------------------
        # Timeline rows
        # ---------------------------------------------------------
        for event in reversed(events):
            row = QWidget(
                self.timeline_widget
            )

            # Completely transparent row.
            row.setStyleSheet(
                "background: transparent;"
            )

            row_layout = QHBoxLayout(row)

            row_layout.setContentsMargins(
                0,
                3,
                0,
                3,
            )
            row_layout.setSpacing(8)

            # -----------------------------------------------------
            # Status dot
            # -----------------------------------------------------
            color = self.theme.status_color(
                event.get(
                    "level",
                    "INFO",
                )
            )

            dot = QLabel(row)
            dot.setFixedSize(
                10,
                10,
            )

            dot.setProperty(
                "systemLogDot",
                True,
            )

            dot.setStyleSheet(
                f"""
                background-color: {color};
                border-radius: 5px;
                """
            )

            row_layout.addWidget(dot)

            # -----------------------------------------------------
            # Timestamp
            # -----------------------------------------------------
            timestamp_label = QLabel(
                event.get(
                    "timestamp",
                    "",
                ),
                row,
            )

            timestamp_label.setMinimumWidth(
                140
            )

            timestamp_label.setProperty(
                "systemLogTimestamp",
                True,
            )

            timestamp_label.setStyleSheet(
                f"""
                color: {self.theme.colors["text_muted"]};
                background: transparent;
                """
            )

            row_layout.addWidget(
                timestamp_label
            )

            # -----------------------------------------------------
            # Message
            # -----------------------------------------------------
            message = (
                f"[{event.get('event_type', '')}] "
                f"{event.get('message', '')}"
            )

            message_label = QLabel(
                message,
                row,
            )

            message_label.setProperty(
                "systemLogMessage",
                True,
            )

            message_label.setStyleSheet(
                f"""
                color: {self.theme.colors["text"]};
                background: transparent;
                """
            )

            row_layout.addWidget(
                message_label,
                1,
            )

            # Insert before trailing stretch.
            self.timeline_layout.insertWidget(
                self.timeline_layout.count() - 1,
                row,
            )