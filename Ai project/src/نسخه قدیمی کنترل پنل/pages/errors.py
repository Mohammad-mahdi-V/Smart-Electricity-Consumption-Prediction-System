"""control_panel/pages/errors.py"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from qfluentwidgets import ComboBox, LineEdit, PushButton

from ..components.auto_refresh import AutoRefreshControl
from ..components.cards import Card, SectionHeader
from ..components.dialogs import ConfirmDialog, InfoDialog
from ..components.tables import DataTable
from ..services import log_service


LEVELS = ["ALL", "ERROR", "WARNING", "INFO"]


class ErrorsPage(QWidget):
    def __init__(self, parent, theme, app):
        super().__init__(parent)

        self.theme = theme
        self.app = app
        self._all_events: list[dict] = []

        self._build()

        # Listen for live light/dark theme changes.
        self.theme.themeChanged.connect(self._on_theme_changed)

        self.refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        # ---------------------------------------------------------
        # Header / actions
        # ---------------------------------------------------------
        top = QHBoxLayout()

        top.addWidget(
            SectionHeader(
                self,
                self.theme,
                "Error Monitor",
                "Combined view of Control Panel events and scheduler.log.",
            )
        )

        top.addStretch(1)

        self.auto_refresh = AutoRefreshControl(self, self.theme, self.refresh)
        top.addWidget(self.auto_refresh)

        refresh_btn = PushButton("Refresh", self)
        refresh_btn.clicked.connect(self.refresh)
        top.addWidget(refresh_btn)

        read_all_btn = PushButton("Read All", self)
        read_all_btn.clicked.connect(self._read_all)
        top.addWidget(read_all_btn)

        delete_btn = PushButton("Delete Read Errors", self)
        delete_btn.clicked.connect(self._delete_read)
        top.addWidget(delete_btn)

        outer.addLayout(top)

        # ---------------------------------------------------------
        # Summary card
        # ---------------------------------------------------------
        self.summary_card = Card(self, self.theme, padding=10)

        summary_layout = QHBoxLayout(self.summary_card.body)
        summary_layout.setContentsMargins(4, 0, 0, 0)
        summary_layout.setSpacing(20)

        self.unread_label = QLabel(
            "Unread: 0",
            self.summary_card.body,
        )
        self.unread_label.setFont(self.theme.font_subheading)
        summary_layout.addWidget(self.unread_label)

        self.read_label = QLabel(
            "Read: 0",
            self.summary_card.body,
        )
        summary_layout.addWidget(self.read_label)

        summary_layout.addStretch(1)
        outer.addWidget(self.summary_card)

        # ---------------------------------------------------------
        # Filters
        # ---------------------------------------------------------
        filters = QHBoxLayout()
        filters.setSpacing(4)

        self.search_label = QLabel("Search", self)
        filters.addWidget(self.search_label)

        self.search_edit = LineEdit(self)
        self.search_edit.setFixedWidth(160)
        self.search_edit.textChanged.connect(
            lambda *_: self._apply_filters()
        )
        filters.addWidget(self.search_edit)

        filters.addSpacing(12)

        self.level_label = QLabel("Level", self)
        filters.addWidget(self.level_label)

        self.level_combo = ComboBox(self)
        self.level_combo.addItems(LEVELS)
        self.level_combo.setCurrentText("ALL")
        self.level_combo.setFixedWidth(100)
        self.level_combo.currentTextChanged.connect(
            lambda *_: self._apply_filters()
        )
        filters.addWidget(self.level_combo)

        filters.addSpacing(12)

        self.component_label = QLabel("Component", self)
        filters.addWidget(self.component_label)

        self.component_combo = ComboBox(self)
        self.component_combo.addItems(["ALL"])
        self.component_combo.setFixedWidth(160)
        self.component_combo.currentTextChanged.connect(
            lambda *_: self._apply_filters()
        )
        filters.addWidget(self.component_combo)

        filters.addSpacing(12)

        self.user_label = QLabel("User", self)
        filters.addWidget(self.user_label)

        self.user_edit = LineEdit(self)
        self.user_edit.setFixedWidth(100)
        self.user_edit.textChanged.connect(
            lambda *_: self._apply_filters()
        )
        filters.addWidget(self.user_edit)

        filters.addStretch(1)
        outer.addLayout(filters)

        # ---------------------------------------------------------
        # Table
        # ---------------------------------------------------------
        columns = [
            ("timestamp", "Time", 170),
            ("status", "Status", 80),
            ("level", "Level", 80),
            ("component", "Component", 140),
            ("device_id", "Device ID", 80),
            ("message", "Message", 420),
        ]

        self.table = DataTable(
            self,
            self.theme,
            columns,
            on_double_click=self._show_detail,
        )

        outer.addWidget(self.table, 1)

        # Apply initial colors.
        self.refresh_theme()

    # -------------------------------------------------------------
    # Theme
    # -------------------------------------------------------------

    def _on_theme_changed(self, mode: str) -> None:
        """Called automatically when the application theme changes."""
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """Refresh page-specific colors after a theme change."""

        self.auto_refresh.refresh_theme()

        text = self.theme.colors["text"]
        muted = self.theme.colors["text_muted"]

        # Summary labels
        self.unread_label.setStyleSheet(
            f"color: {text};"
        )

        self.read_label.setStyleSheet(
            f"color: {muted};"
        )

        # Filter labels
        self.search_label.setStyleSheet(
            f"color: {text};"
        )

        self.level_label.setStyleSheet(
            f"color: {text};"
        )

        self.component_label.setStyleSheet(
            f"color: {text};"
        )

        self.user_label.setStyleSheet(
            f"color: {text};"
        )

    # -------------------------------------------------------------
    # Notifications
    # -------------------------------------------------------------

    def _notify(self, title: str, message: str) -> None:
        """Show an informational dialog."""

        InfoDialog(
            self.app.root,
            self.theme,
            title,
            [("", message)],
        )

    # -------------------------------------------------------------
    # Data
    # -------------------------------------------------------------

    def refresh(self) -> None:
        try:
            self._all_events = log_service.all_error_events(
                limit=1000
            )
        except Exception as exc:  # noqa: BLE001
            self.app.show_error(
                "Failed to load errors",
                str(exc),
            )
            self._all_events = []

        self._rebuild_component_menu()
        self._apply_filters()

    def _rebuild_component_menu(self) -> None:
        components = sorted(
            {
                str(e.get("component"))
                for e in self._all_events
                if e.get("component")
            }
        )

        values = ["ALL", *components]

        current = (
            self.component_combo.currentText()
            if self.component_combo.count()
            else "ALL"
        )

        if current not in values:
            current = "ALL"

        self.component_combo.blockSignals(True)

        self.component_combo.clear()
        self.component_combo.addItems(values)
        self.component_combo.setCurrentText(current)

        self.component_combo.blockSignals(False)

    def _apply_filters(self) -> None:
        rows = self._all_events

        level = self.level_combo.currentText()

        if level and level != "ALL":
            rows = [
                r
                for r in rows
                if r.get("level") == level
            ]

        component = self.component_combo.currentText()

        if component and component != "ALL":
            rows = [
                r
                for r in rows
                if r.get("component") == component
            ]

        search = self.search_edit.text().strip().lower()

        if search:
            rows = [
                r
                for r in rows
                if search in str(
                    r.get("message", "")
                ).lower()
            ]

        user = self.user_edit.text().strip()

        if user:
            rows = [
                r
                for r in rows
                if str(r.get("device_id", "")) == user
            ]

        display = []

        for row in reversed(rows):
            item = dict(row)
            item["status"] = (
                "Read"
                if item.get("is_read")
                else "New"
            )
            display.append(item)

        self.table.set_rows(display)

        unread = sum(
            not bool(e.get("is_read"))
            for e in self._all_events
        )

        self.unread_label.setText(
            f"Unread: {unread}"
        )

        self.read_label.setText(
            f"Read: {len(self._all_events) - unread}"
        )

    # -------------------------------------------------------------
    # Read / delete
    # -------------------------------------------------------------

    def _read_all(self) -> None:
        count = log_service.mark_all_errors_read()

        if count == 0:
            self._notify(
                "Error Monitor",
                "There are no unread errors.",
            )
            return

        self.refresh()

        self._notify(
            "Error Monitor",
            f"{count} error(s) marked as read.",
        )

    def _delete_read(self) -> None:
        count = sum(
            bool(event.get("is_read"))
            for event in self._all_events
        )

        if count == 0:
            self._notify(
                "Error Monitor",
                "There are no read errors to delete.",
            )
            return

        ConfirmDialog(
            self.app.root,
            self.theme,
            "Delete Read Errors",
            f"Delete {count} read error(s)?\n\n"
            "Original log files will NOT be modified.",
            on_confirm=self._do_delete_read,
            confirm_text="Delete",
            danger=True,
        )

    def _do_delete_read(self) -> None:
        removed = log_service.delete_read_errors()

        self.refresh()

        self._notify(
            "Error Monitor",
            f"{removed} read error(s) deleted.",
        )

    # -------------------------------------------------------------
    # Details
    # -------------------------------------------------------------

    def _show_detail(self, row: dict) -> None:
        if not row.get("is_read"):
            log_service.mark_error_read(row)
            row["is_read"] = True

            for event in self._all_events:
                if event.get("id") == row.get("id"):
                    event["is_read"] = True
                    break

        extra = row.get("extra")
        traceback_text = ""

        if isinstance(extra, dict):
            traceback_text = "\n".join(
                f"{k}: {v}"
                for k, v in extra.items()
            )

        sections = [
            (
                "Timestamp",
                str(row.get("timestamp", "")),
            ),
            (
                "Component",
                str(row.get("component", "")),
            ),
            (
                "User",
                str(row.get("device_id", "")),
            ),
            (
                "Message",
                str(row.get("message", "")),
            ),
        ]

        if traceback_text:
            sections.append(
                ("Details", traceback_text)
            )

        copy_text = "\n".join(
            f"{label}: {value}"
            for label, value in sections
        )

        InfoDialog(
            self.app.root,
            self.theme,
            "Error Details",
            sections,
            copy_text=copy_text,
        )