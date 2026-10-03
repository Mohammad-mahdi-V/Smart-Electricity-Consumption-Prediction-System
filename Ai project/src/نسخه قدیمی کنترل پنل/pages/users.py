"""control_panel/pages/users.py — Devices page (route key remains "users")."""

from __future__ import annotations

import shiboken6

from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    ComboBox,
    Flyout,
    FlyoutViewBase,
    LineEdit,
    PushButton,
)

from ..components.auto_refresh import AutoRefreshControl
from ..components.cards import SectionHeader
from ..components.status_badges import StatusBadge
from ..components.tables import DataTable
from ..services import user_service


STATUS_FILTERS = [
    "ALL",
    "READY",
    "LOW_DATA",
    "NO_DATA",
    "MISSING_RECENT_DATA",
]


class _UserDetailFlyoutView(FlyoutViewBase):
    """Custom Flyout content for the Devices page detail popup."""

    def __init__(
        self,
        theme,
        device_id,
        detail: dict,
        on_predict,
        parent=None,
    ):
        super().__init__(parent)

        self.theme = theme
        self.device_id = device_id
        self.detail = detail

        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            20,
            16,
            20,
            16,
        )
        layout.setSpacing(10)

        # ---------------------------------------------------------
        # Title
        # ---------------------------------------------------------
        self.title_label = QLabel(
            f"Device {device_id}",
            self,
        )
        self.title_label.setFont(
            theme.font_subheading
        )
        layout.addWidget(
            self.title_label
        )

        # ---------------------------------------------------------
        # Details
        # ---------------------------------------------------------
        rows = [
            (
                "History",
                f"{detail['history_days']} days",
            ),
            (
                "First Data",
                detail["first_data"],
            ),
            (
                "Last Data",
                detail["last_data"],
            ),
            (
                "Missing Hours",
                str(
                    detail.get(
                        "missing_hours",
                        "—",
                    )
                ),
            ),
        ]

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(3)

        self.detail_labels: list[QLabel] = []
        self.detail_values: list[QLabel] = []

        for i, (label, value) in enumerate(rows):
            label_widget = QLabel(
                label,
                self,
            )

            grid.addWidget(
                label_widget,
                i,
                0,
            )

            self.detail_labels.append(
                label_widget
            )

            value_widget = QLabel(
                value,
                self,
            )

            value_widget.setFont(
                theme.font_body_bold
            )

            grid.addWidget(
                value_widget,
                i,
                1,
            )

            self.detail_values.append(
                value_widget
            )

        layout.addLayout(
            grid
        )

        # ---------------------------------------------------------
        # Status
        # ---------------------------------------------------------
        self.status_badge = StatusBadge(
            self,
            theme,
            detail["status"],
        )

        layout.addWidget(
            self.status_badge
        )

        # ---------------------------------------------------------
        # Buttons
        # ---------------------------------------------------------
        button_row = QHBoxLayout()

        view_btn = PushButton(
            "View Prediction",
            self,
        )

        view_btn.clicked.connect(
            lambda: on_predict(False)
        )

        button_row.addWidget(
            view_btn
        )

        button_row.addStretch(1)

        layout.addLayout(
            button_row
        )

        # ---------------------------------------------------------
        # Initial theme
        # ---------------------------------------------------------
        self.refresh_theme()

        # ---------------------------------------------------------
        # Live theme updates
        # ---------------------------------------------------------
        theme.themeChanged.connect(
            self._on_theme_changed
        )

    def _on_theme_changed(
        self,
        mode: str,
    ) -> None:
        self.refresh_theme()

    def refresh_theme(self) -> None:
        text = self.theme.colors["text"]
        muted = self.theme.colors["text_muted"]

        self.title_label.setStyleSheet(
            f"color: {text};"
        )

        for label in self.detail_labels:
            label.setStyleSheet(
                f"color: {muted};"
            )

        for value in self.detail_values:
            value.setStyleSheet(
                f"color: {text};"
            )


class UsersPage(QWidget):
    def __init__(
        self,
        parent,
        theme,
        app,
    ):
        super().__init__(parent)

        self.theme = theme
        self.app = app

        # Keeps the modeless Flyout reference.
        #
        # IMPORTANT:
        # Qt/qfluentwidgets may delete the underlying C++
        # object while this Python reference still exists.
        self._detail_dialog: QWidget | None = None

        self._build()

        # ---------------------------------------------------------
        # Live theme updates
        # ---------------------------------------------------------
        self.theme.themeChanged.connect(
            self._on_theme_changed
        )

        self.refresh()

    # =============================================================
    # Build UI
    # =============================================================

    def _build(self) -> None:
        outer = QVBoxLayout(
            self
        )

        outer.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        outer.setSpacing(12)

        # ---------------------------------------------------------
        # Header / actions
        # ---------------------------------------------------------
        top = QHBoxLayout()

        top.addWidget(
            SectionHeader(
                self,
                self.theme,
                "Devices",
                "Loaded from database device_data (device_id).",
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

        refresh_btn = PushButton(
            "Refresh",
            self,
        )

        refresh_btn.clicked.connect(
            self.refresh
        )

        top.addWidget(
            refresh_btn
        )

        outer.addLayout(
            top
        )

        # ---------------------------------------------------------
        # Filters
        # ---------------------------------------------------------
        filters = QHBoxLayout()
        filters.setSpacing(4)

        self.search_label = QLabel(
            "Search Device ID",
            self,
        )

        filters.addWidget(
            self.search_label
        )

        self.search_edit = LineEdit(
            self
        )

        self.search_edit.setFixedWidth(
            140
        )

        self.search_edit.textChanged.connect(
            lambda *_: self._apply_filters()
        )

        filters.addWidget(
            self.search_edit
        )

        filters.addSpacing(
            12
        )

        self.status_label = QLabel(
            "Status",
            self,
        )

        filters.addWidget(
            self.status_label
        )

        self.status_combo = ComboBox(
            self
        )

        self.status_combo.addItems(
            STATUS_FILTERS
        )

        self.status_combo.setCurrentText(
            "ALL"
        )

        self.status_combo.setFixedWidth(
            200
        )

        self.status_combo.currentTextChanged.connect(
            lambda *_: self._apply_filters()
        )

        filters.addWidget(
            self.status_combo
        )

        filters.addStretch(
            1
        )

        outer.addLayout(
            filters
        )

        # ---------------------------------------------------------
        # Table
        # ---------------------------------------------------------
        columns = [
            (
                "device_id",
                "Device ID",
                90,
            ),
            (
                "history_days",
                "History Days",
                110,
            ),
            (
                "last_data",
                "Last Data",
                120,
            ),
            (
                "missing_days",
                "Missing Days",
                110,
            ),
            (
                "status",
                "Status",
                160,
            ),
        ]

        self.table = DataTable(
            self,
            self.theme,
            columns,
            on_double_click=self._show_detail,
        )

        outer.addWidget(
            self.table,
            1,
        )

        # ---------------------------------------------------------
        # Initial theme
        # ---------------------------------------------------------
        self.refresh_theme()

    # =============================================================
    # Theme
    # =============================================================

    def _on_theme_changed(
        self,
        mode: str,
    ) -> None:
        self.refresh_theme()

    def refresh_theme(self) -> None:
        self.auto_refresh.refresh_theme()

        text = self.theme.colors["text"]

        self.search_label.setStyleSheet(
            f"color: {text};"
        )

        self.status_label.setStyleSheet(
            f"color: {text};"
        )

        # ---------------------------------------------------------
        # Safely update currently open Flyout.
        #
        # The Python wrapper can remain alive after the underlying
        # Qt C++ object has already been deleted.
        # ---------------------------------------------------------
        dialog = self._detail_dialog

        if dialog is None:
            return

        try:
            if not shiboken6.isValid(
                dialog
            ):
                self._detail_dialog = None
                return

            view = dialog.findChild(
                _UserDetailFlyoutView
            )

            if view is not None:
                view.refresh_theme()

        except RuntimeError:
            # Qt object was deleted between the validity check
            # and the operation.
            self._detail_dialog = None

    # =============================================================
    # Flyout lifecycle
    # =============================================================

    def _close_detail_flyout(self) -> None:
        """
        Safely close the current detail Flyout.

        qfluentwidgets/Qt can destroy the underlying C++ object
        while the Python reference still exists. Therefore we
        must check the Shiboken validity before calling close().
        """

        dialog = self._detail_dialog

        # Clear our reference first.
        #
        # This prevents subsequent code from accidentally trying
        # to use the same deleted object.
        self._detail_dialog = None

        if dialog is None:
            return

        try:
            if shiboken6.isValid(
                dialog
            ):
                dialog.close()

        except RuntimeError:
            # Already deleted by Qt.
            pass

    # =============================================================
    # Data
    # =============================================================

    def refresh(self) -> None:
        self._apply_filters()

    def _apply_filters(self) -> None:
        status = self.status_combo.currentText()

        try:
            rows = user_service.list_devices(
                search=self.search_edit.text().strip(),
                status_filter=(
                    None
                    if status == "ALL"
                    else status
                ),
            )

        except Exception as exc:  # noqa: BLE001
            self.app.show_error(
                "Failed to load devices",
                str(exc),
            )

            rows = []

        self.table.set_rows(
            rows
        )

    # =============================================================
    # Device detail
    # =============================================================

    def _show_detail(
        self,
        row: dict,
    ) -> None:
        device_id = row.get(
            "device_id"
        )

        try:
            detail = user_service.get_device_detail(
                int(device_id)
            )

        except Exception as exc:  # noqa: BLE001
            self.app.show_error(
                "Failed to load device detail",
                str(exc),
            )
            return

        if not detail.get(
            "found"
        ):
            self.app.show_error(
                "Device not found",
                f"No data found for device {device_id}.",
            )
            return

        # ---------------------------------------------------------
        # Close previous Flyout safely.
        # ---------------------------------------------------------
        self._close_detail_flyout()

        # ---------------------------------------------------------
        # Prediction callback
        # ---------------------------------------------------------
        def go_predict(
            force: bool = False,
        ) -> None:
            # Close the detail Flyout safely before navigating.
            self._close_detail_flyout()

            self.app.navigate(
                "predictions",
                context={
                    "device_id": device_id,
                    "force": force,
                },
            )

        # ---------------------------------------------------------
        # Create Flyout content
        # ---------------------------------------------------------
        view = _UserDetailFlyoutView(
            self.theme,
            device_id,
            detail,
            go_predict,
        )

        # ---------------------------------------------------------
        # Create Flyout
        # ---------------------------------------------------------
        self._detail_dialog = Flyout.make(
            view,
            self.table,
            self.app.root,
        )