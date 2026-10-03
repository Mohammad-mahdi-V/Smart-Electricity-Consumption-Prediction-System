"""control_panel/components/terminal.py

Read-only, auto-scrolling output area for live stdout/stderr from
subprocess-run scripts, builds, and tests.

IMPORTANT for step 3 (workers/signals): `append_line` must only ever be
called on the GUI thread. A worker running on a QThread must emit a
Signal(str) that a slot on the page connects to `append_line` -- never
call this directly from the worker thread itself.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import isDarkTheme


class TerminalOutput(QWidget):
    def __init__(
        self,
        parent,
        theme,
        height: int = 16,
    ):
        super().__init__(parent)

        self.theme = theme

        # ---------------------------------------------------------
        # Layout
        # ---------------------------------------------------------
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---------------------------------------------------------
        # Terminal
        # ---------------------------------------------------------
        self.text = QPlainTextEdit(self)

        self.text.setReadOnly(True)

        self.text.setLineWrapMode(
            QPlainTextEdit.LineWrapMode.NoWrap
        )

        self.text.setFont(
            theme.font_mono
        )

        # ---------------------------------------------------------
        # Transparent background
        # ---------------------------------------------------------
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )

        self.text.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )

        self.text.viewport().setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )

        # ---------------------------------------------------------
        # Fluent-like Qt scrollbars
        #
        # QPlainTextEdit requires an actual QScrollBar here.
        # Therefore we style Qt's native scrollbar instead of
        # injecting qfluentwidgets.ScrollBar.
        # ---------------------------------------------------------
        self._apply_theme()

        # ---------------------------------------------------------
        # Height
        # ---------------------------------------------------------
        line_height = (
            self.text.fontMetrics().lineSpacing()
        )

        self.text.setMinimumHeight(
            line_height * height + 16
        )

        layout.addWidget(
            self.text
        )

        # ---------------------------------------------------------
        # Text formats
        # ---------------------------------------------------------
        self._build_formats()

        # ---------------------------------------------------------
        # Live theme updates
        # ---------------------------------------------------------
        self.theme.themeChanged.connect(
            self._on_theme_changed
        )

    # =============================================================
    # Theme
    # =============================================================

    def _apply_theme(self) -> None:
        """Apply the current application theme."""

        text_color = self.theme.colors["text"]
        surface = self.theme.colors["surface"]

        # Use a subtle Fluent-style scrollbar.
        #
        # The terminal itself remains transparent, allowing the
        # page/card background to show through.
        self.setStyleSheet(
            """
            TerminalOutput {
                background: transparent;
                border: none;
            }
            """
        )

        self.text.setStyleSheet(
            f"""
            QPlainTextEdit {{
                background: transparent;
                background-color: transparent;
                color: {text_color};
                border: none;
                padding: 8px 10px;
                selection-color: {text_color};
                selection-background-color: {self.theme.colors["accent"]};
            }}

            QPlainTextEdit::viewport {{
                background: transparent;
                background-color: transparent;
                border: none;
            }}

            """
        )

    def _on_theme_changed(
        self,
        mode: str,
    ) -> None:
        """Refresh terminal after Light/Dark theme changes."""

        self._apply_theme()
        self._build_formats()

    # =============================================================
    # Text formats
    # =============================================================

    def _build_formats(self) -> None:
        """Build terminal text formats from the active theme."""

        self._formats = {
            "error": self._make_format(
                self.theme.colors["error"]
            ),

            "warning": self._make_format(
                self.theme.colors["warning"]
            ),

            "success": self._make_format(
                self.theme.colors["success"]
            ),

            None: self._make_format(
                self.theme.colors["text"]
            ),
        }

    @staticmethod
    def _make_format(
        color: str,
    ) -> QTextCharFormat:
        fmt = QTextCharFormat()

        fmt.setForeground(
            QColor(color)
        )

        return fmt

    # =============================================================
    # Public API
    # =============================================================

    def clear(self) -> None:
        """Clear terminal output."""

        self.text.clear()

    def append_line(
        self,
        line: str,
    ) -> None:
        """Append one line to the terminal.

        This method must only be called from the GUI thread.
        """

        tag = None
        upper = line.upper()

        # ---------------------------------------------------------
        # Error
        # ---------------------------------------------------------
        if (
            "ERROR" in upper
            or "TRACEBACK" in upper
            or "❌" in line
        ):
            tag = "error"

        # ---------------------------------------------------------
        # Warning
        # ---------------------------------------------------------
        elif (
            "WARNING" in upper
            or "⚠" in line
        ):
            tag = "warning"

        # ---------------------------------------------------------
        # Success
        # ---------------------------------------------------------
        elif (
            "PASSED" in upper
            or "✅" in line
        ):
            tag = "success"

        # ---------------------------------------------------------
        # Insert text
        # ---------------------------------------------------------
        cursor = self.text.textCursor()

        cursor.movePosition(
            QTextCursor.MoveOperation.End
        )

        cursor.insertText(
            line + "\n",
            self._formats[tag],
        )

        self.text.setTextCursor(
            cursor
        )

        # ---------------------------------------------------------
        # Auto-scroll
        # ---------------------------------------------------------
        self.text.ensureCursorVisible()