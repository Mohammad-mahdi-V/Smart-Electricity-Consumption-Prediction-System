"""control_panel/theme.py

Fluent theming for the Control Panel.

This keeps the exact same public surface the Tkinter version had, because
every page and shared widget in this project reads it directly:

    theme.colors["surface"]        -> hex string
    theme.font_body / font_mono / ... -> a font to hand to a widget
    theme.status_color(status)     -> hex string
    theme.mode                     -> "light" | "dark"
    theme.toggle() / theme.set_mode(mode)

The only two differences from before:
  * font_* attributes are now QFont instances instead of (family, size, style)
    tuples -- Qt widgets take a QFont directly.
  * Theme is a QObject and emits `themeChanged(mode)` so the window and any
    open page can react live, instead of the old approach of destroying and
    rebuilding the entire widget tree on every theme switch.

Palettes (LIGHT / DARK) are unchanged from the Tkinter version.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from qfluentwidgets import Theme as FluentTheme, setTheme, setThemeColor

LIGHT = {
    "bg": "#f3f3f3",
    "surface": "#ffffff",
    "surface_alt": "#fafafa",
    "border": "#e1e1e1",
    "text": "#1a1a1a",
    "text_muted": "#6b6b6b",
    "sidebar_bg": "#fbfbfb",
    "sidebar_selected": "#e6f0fb",
    "sidebar_hover": "#eeeeee",
    "accent": "#0067c0",
    "accent_hover": "#005ba1",
    "success": "#107c10",
    "warning": "#9d5d00",
    "error": "#c42b1c",
    "row_alt": "#f7f7f7",
}


DARK = {
    "bg": "#202020",
    "surface": "#2b2b2b",
    "surface_alt": "#323232",
    "border": "#3d3d3d",
    "text": "#f2f2f2",
    "text_muted": "#a6a6a6",
    "sidebar_bg": "#252525",
    "sidebar_selected": "#0a3d68",
    "sidebar_hover": "#333333",
    "accent": "#4cc2ff",
    "accent_hover": "#69cdff",
    "success": "#6ccb5f",
    "warning": "#f7b03f",
    "error": "#ff99a4",
    "row_alt": "#2f2f2f",
}


class Theme(QObject):
    """Live theme object shared by the main window and every page.

    NOTE: create this *after* a QApplication exists (QFontDatabase and
    QFont both need one), and treat it as a singleton -- construct it once
    in MainWindow and pass the same instance down to every page, exactly
    like the Tkinter version did.
    """

    themeChanged = Signal(str)  # emits "light" or "dark" after apply()

    def __init__(self, mode: str = "light", parent=None) -> None:
        super().__init__(parent)

        self.mode = mode if mode in ("light", "dark") else "light"

        self._build_fonts()
        self._build_colors()
        self.apply()

    def _build_fonts(self) -> None:
        families = set(QFontDatabase.families())

        base_family = "Segoe UI" if "Segoe UI" in families else "Arial"
        mono_family = "Consolas" if "Consolas" in families else "Courier New"

        self.font_body = QFont(base_family, 10)

        self.font_body_bold = QFont(base_family, 10)
        self.font_body_bold.setBold(True)

        self.font_heading = QFont(base_family, 15)
        self.font_heading.setBold(True)

        self.font_subheading = QFont(base_family, 12)
        self.font_subheading.setBold(True)

        self.font_small = QFont(base_family, 9)

        self.font_mono = QFont(mono_family, 10)

    def _build_colors(self) -> None:
        self.colors = (DARK if self.mode == "dark" else LIGHT).copy()

    def apply(self) -> None:
        """(Re)apply the current mode to qfluentwidgets and refresh colors,
        then notify listeners. Safe to call any time, not just at startup.
        """
        setTheme(FluentTheme.DARK if self.mode == "dark" else FluentTheme.LIGHT)

        self._build_colors()
        setThemeColor(self.colors["accent"])
        self._apply_global_styles()

        self.themeChanged.emit(self.mode)

    def _apply_global_styles(self) -> None:
        """Apply one theme-aware Qt stylesheet and palette globally.

        This is the fallback for every native Qt widget in the application,
        so text and scrollbars stay synchronized even when a page/component
        does not explicitly restyle an individual widget.
        """
        app = QApplication.instance()
        if app is None:
            return

        c = self.colors

        palette = QPalette(app.palette())
        palette.setColor(QPalette.ColorRole.Window, QColor(c["bg"]))
        palette.setColor(QPalette.ColorRole.Base, QColor(c["surface"]))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(c["row_alt"]))
        palette.setColor(QPalette.ColorRole.Text, QColor(c["text"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(c["text"]))
        palette.setColor(QPalette.ColorRole.Button, QColor(c["surface"]))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(c["text"]))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(c["surface_alt"]))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(c["text"]))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["text_muted"]))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(c["accent"]))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        app.setPalette(palette)

        global_qss = f"""
            /* ========================================================
               Application backgrounds
               ======================================================== */

            QMainWindow,
            QWidget#controlPanelRoot {{
                background-color: {c["bg"]};
            }}

            QWidget#contentHost,
            QStackedWidget {{
                background: transparent;
            }}

            /* ========================================================
               Native text fallback
               ======================================================== */

            QLabel {{
                color: {c["text"]};
                background: transparent;
            }}

            QGroupBox {{
                color: {c["text"]};
            }}

            QAbstractItemView {{
                color: {c["text"]};
                selection-color: {c["text"]};
                selection-background-color: {c["sidebar_selected"]};
            }}

            QPlainTextEdit, QTextEdit {{
                color: {c["text"]};
            }}

            /* ========================================================
               Global button baseline (Refresh-style)
               ======================================================== */

            QPushButton,
            PushButton {{
                background-color: {c["surface"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
                border-radius: 7px;
                padding: 3px 5px;
                min-height: 15px;
            }}

            QPushButton:hover,
            PushButton:hover {{
                background-color: {c["sidebar_hover"]};
                color: {c["text"]};
            }}

            QPushButton:pressed,
            PushButton:pressed {{
                background-color: {c["surface_alt"]};
                color: {c["text"]};
            }}

            QPushButton:disabled,
            PushButton:disabled {{
                background-color: {c["surface_alt"]};
                color: {c["text_muted"]};
                border-color: {c["border"]};
            }}

            /* ========================================================
               Global modern scrollbar
               ======================================================== */

            QScrollBar:vertical {{
                background: transparent;
                width: 10px;
                margin: 3px 2px 3px 2px;
                border: none;
            }}

            QScrollBar::handle:vertical {{
                background-color: {c["border"]};
                min-height: 30px;
                border-radius: 5px;
                margin: 0px;
                border: none;
            }}

            QScrollBar::handle:vertical:hover {{
                background-color: {c["text_muted"]};
            }}

            QScrollBar::handle:vertical:pressed {{
                background-color: {c["accent"]};
            }}

            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0px;
                background: transparent;
                border: none;
            }}

            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical {{
                background: transparent;
                border: none;
            }}

            QScrollBar:horizontal {{
                background: transparent;
                height: 10px;
                margin: 2px 3px 2px 3px;
                border: none;
            }}

            QScrollBar::handle:horizontal {{
                background-color: {c["border"]};
                min-width: 34px;
                border-radius: 5px;
                margin: 0px;
                border: none;
            }}

            QScrollBar::handle:horizontal:hover {{
                background-color: {c["text_muted"]};
            }}

            QScrollBar::handle:horizontal:pressed {{
                background-color: {c["accent"]};
            }}

            QScrollBar::add-line:horizontal,
            QScrollBar::sub-line:horizontal {{
                width: 0px;
                background: transparent;
                border: none;
            }}

            QScrollBar::add-page:horizontal,
            QScrollBar::sub-page:horizontal {{
                background: transparent;
                border: none;
            }}

            QAbstractScrollArea::viewport {{
                background: transparent;
            }}

            QScrollArea {{
                background: transparent;
            }}

            QToolTip {{
                background-color: {c["surface_alt"]};
                color: {c["text"]};
                border: 1px solid {c["border"]};
            }}
        """

        if not hasattr(app, "_control_panel_base_stylesheet"):
            app._control_panel_base_stylesheet = app.styleSheet()

        app.setStyleSheet(
            app._control_panel_base_stylesheet + "\n" + global_qss
        )

    def toggle(self) -> None:
        self.set_mode("dark" if self.mode == "light" else "light")

    def set_mode(self, mode: str) -> None:
        if mode not in ("light", "dark"):
            raise ValueError("mode must be 'light' or 'dark'")

        self.mode = mode
        self.apply()

    def status_color(self, status: str) -> str:
        status = (status or "").upper()

        if status in ("HEALTHY", "PASSED", "READY", "OK", "SUCCESS", "TRUE"):
            return self.colors["success"]

        if status in ("WARNING", "LOW_DATA", "MISSING_RECENT_DATA", "SKIPPED"):
            return self.colors["warning"]

        if status in ("ERROR", "FAILED", "NO_DATA", "CRITICAL", "FALSE"):
            return self.colors["error"]

        return self.colors["text_muted"]
