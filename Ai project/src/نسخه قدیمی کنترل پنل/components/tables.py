"""control_panel/components/tables.py"""

from __future__ import annotations

from typing import Any, Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QTableWidgetItem, QVBoxLayout, QWidget

from qfluentwidgets import TableWidget

from .cards import force_transparent


class DataTable(QWidget):
    """A Fluent TableWidget with click-to-sort columns (native Qt column
    sorting, toggled by clicking a header -- replaces the old manual
    _sort_by/tag-alternating logic) and a selection callback. Columns are
    defined once; rows are replaced wholesale via set_rows() -- same
    contract as the Tkinter Treeview version.
    """

    def __init__(self, parent, theme, columns: list[tuple[str, str, int]],
                 on_select: Callable[[dict[str, Any]], None] | None = None,
                 on_double_click: Callable[[dict[str, Any]], None] | None = None):
        """columns: list of (key, heading, width)"""
        super().__init__(parent)
        self.theme = theme
        self._columns = columns
        self._keys = [key for key, _, _ in columns]
        self._on_select = on_select
        self._on_double_click = on_double_click

        self.table = TableWidget(self)
        # The visible table background is actually painted by the internal
        # viewport widget (and the header widgets have their own palette
        # too) -- a QSS rule on the "TableWidget" selector alone doesn't
        # reach any of them. Force every one of these transparent.
        for w in (
            self.table,
            self.table.viewport(),
            self.table.horizontalHeader(),
            self.table.verticalHeader(),
        ):
            force_transparent(w)
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels([heading for _, heading, _ in columns])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setStretchLastSection(True)

        for i, (_, _, width) in enumerate(columns):
            self.table.setColumnWidth(i, width)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.table)

        if on_select:
            self.table.itemSelectionChanged.connect(self._handle_select)
        if on_double_click:
            self.table.cellDoubleClicked.connect(lambda *_args: self._handle_double_click())

        self._apply_theme()
        self.theme.themeChanged.connect(self._on_theme_changed)

    def _on_theme_changed(self, mode: str) -> None:
        self._apply_theme()

    def _apply_theme(self) -> None:
        # Kept fully transparent, no fill anywhere -- border/gridlines/header
        # only. Re-applied every call (not just __init__) since a theme
        # switch (setTheme in theme.py) can re-trigger qfluentwidgets' own
        # internal restyling and silently undo this.
        for w in (
            self.table,
            self.table.viewport(),
            self.table.horizontalHeader(),
            self.table.verticalHeader(),
        ):
            force_transparent(w)

        c = self.theme.colors
        self.table.setStyleSheet(
            f"""
            TableWidget, TableWidget::viewport {{
                background-color: transparent !important;
                alternate-background-color: transparent !important;
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 8px;
                gridline-color: {c["border"]};
            }}

            TableWidget::item {{
                background-color: transparent !important;
            }}

            QHeaderView, QHeaderView::section, QTableCornerButton::section {{
                background-color: transparent !important;
                color: {c["text"]};
                border: none;
                border-bottom: 1px solid {c["border"]};
                padding: 4px 6px;
            }}
            """
        )
        self.table.viewport().setStyleSheet("background: transparent !important;")

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        # Sorting fights population if left on while rows are inserted.
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))

        for r, row in enumerate(rows):
            for c, key in enumerate(self._keys):
                value = row.get(key)
                display = "" if value is None else str(value)
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, display)
                # Store numeric values under EditRole too, so clicking a
                # header sorts numeric columns numerically rather than
                # lexicographically ("10" before "9" would be wrong).
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    item.setData(Qt.ItemDataRole.EditRole, value)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.table.setItem(r, c, item)

        self.table.setSortingEnabled(True)

    def _handle_select(self) -> None:
        items = self.table.selectedItems()
        if not items or not self._on_select:
            return
        row = items[0].data(Qt.ItemDataRole.UserRole)
        if row is not None:
            self._on_select(row)

    def _handle_double_click(self) -> None:
        items = self.table.selectedItems()
        if not items or not self._on_double_click:
            return
        row = items[0].data(Qt.ItemDataRole.UserRole)
        if row is not None:
            self._on_double_click(row)