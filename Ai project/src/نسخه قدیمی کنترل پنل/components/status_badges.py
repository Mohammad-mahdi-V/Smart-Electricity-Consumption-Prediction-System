"""control_panel/components/status_badges.py"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class StatusBadge(QWidget):
    """Colored dot + label, e.g. 'Production Healthy'.

    `surface` is accepted for call-site compatibility with the Tkinter
    version (there it picked between the "surface" and "bg" background
    colors for an opaque canvas square behind the dot). Qt widgets are
    transparent by default here, so it has no visual effect now.
    """

    def __init__(self, parent, theme, status: str, text: str | None = None, surface: bool = True):
        super().__init__(parent)
        self.theme = theme

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self.dot = QLabel(self)
        self.dot.setFixedSize(10, 10)
        layout.addWidget(self.dot)

        self.text_label = QLabel(self)
        self.text_label.setFont(theme.font_body_bold)
        layout.addWidget(self.text_label)

        self._status = status
        self._status_text = text
        self.set_status(status, text)
        self.theme.themeChanged.connect(self._on_theme_changed)

    def _on_theme_changed(self, mode: str) -> None:
        self.set_status(self._status, self._status_text)

    def set_status(self, status: str, text: str | None = None) -> None:
        self._status = status
        self._status_text = text
        color = self.theme.status_color(status)
        self.dot.setStyleSheet(f"background-color: {color}; border-radius: 5px;")
        self.text_label.setText(text or status)
        self.text_label.setStyleSheet(f"color: {self.theme.colors['text']};")
