"""control_panel/components/cards.py"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QPalette
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from qfluentwidgets import CardWidget


def force_transparent(widget) -> None:
    """Make a widget paint nothing of its own, no matter what.

    QSS "background: transparent" and autoFillBackground(False) can each be
    silently overridden later -- a framework re-theming itself, or Qt
    re-enabling auto-fill on certain widget types. Zeroing out the palette's
    own background roles is the one thing that still holds even if something
    later flips autoFillBackground back on or reapplies its own stylesheet,
    since there's then no opaque color left for it to paint.

    Deliberately does NOT set WA_TranslucentBackground: that flag is meant
    for top-level windows (it asks the platform for an ARGB surface). Set on
    an ordinary child widget it isn't properly composited and instead renders
    as a solid black square -- which is worse than the opaque background it
    was meant to remove.
    """

    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    widget.setAutoFillBackground(False)

    transparent = QColor(0, 0, 0, 0)
    palette = widget.palette()
    for role in (
        QPalette.ColorRole.Window,
        QPalette.ColorRole.Base,
        QPalette.ColorRole.AlternateBase,
        QPalette.ColorRole.Button,
    ):
        palette.setColor(role, transparent)
    widget.setPalette(palette)


def style_scroll_area_transparent(scroll) -> None:
    """Make a QScrollArea and its content fully see-through.

    QScrollArea paints its actual background through the internal viewport
    widget and the content widget passed to setWidget() -- neither is
    reached by a plain "QScrollArea { background: transparent; }" rule
    (the global stylesheet's "QAbstractScrollArea::viewport" selector in
    theme.py is not a real Qt subcontrol, so it silently does nothing).
    This is why Models and Model Builder -- the only two pages that wrap
    their body in a QScrollArea -- showed a solid black container below
    their header while every other (non-scrolling) page looked fine.

    Call this once after creating the QScrollArea; call it again after
    scroll.setWidget(content) once the content widget exists.
    """

    scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    scroll.setAutoFillBackground(False)
    scroll.viewport().setAutoFillBackground(False)
    scroll.viewport().setStyleSheet("background: transparent;")

    content = scroll.widget()
    if content is not None:
        content.setAutoFillBackground(False)
        content.setStyleSheet("background: transparent;")


class Card(CardWidget):
    """A rounded-corner card. CardWidget already draws its own rounded
    border/background (that was the whole point of the old hand-rolled
    Canvas + rounded-polygon code in the Tkinter version), so this class
    is now mostly a thin wrapper that exposes a `.body` container for
    pages to populate -- same as before.

    `radius` is accepted but unused: CardWidget's corner radius is fixed
    by the qfluentwidgets stylesheet, not something call sites configured
    per-instance in practice (every call site here used the default).

    `finalize()` is now a no-op -- Qt layouts size themselves as content
    is added, there's no separate "measure then fix the height" step like
    Tkinter needed. It's kept only so page code doesn't have to change
    when those pages get migrated in a later step.
    """

    def __init__(self, parent, theme, padding: int = 16, radius: int = 12, **kwargs):
        super().__init__(parent)
        self.theme = theme

        self.body = QWidget(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(padding, padding, padding, padding)
        outer.addWidget(self.body)

    def finalize(self) -> None:
        pass

class MetricCard(CardWidget):
    """Compact metric card (label / big value / optional sub-line)."""

    def __init__(
        self,
        parent,
        theme,
        label: str,
        value: str,
        sub: str | None = None,
        status: str | None = None,
    ):
        super().__init__(parent)

        self.theme = theme
        self.status = status

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(4)

        self.label_widget = QLabel(label, self)
        self.label_widget.setFont(theme.font_small)
        layout.addWidget(self.label_widget)

        value_font = QFont(theme.font_body.family(), 20)
        value_font.setBold(True)

        self.value_label = QLabel(value, self)
        self.value_label.setFont(value_font)
        layout.addWidget(self.value_label)

        self.sub_label = None

        if sub:
            self.sub_label = QLabel(sub, self)
            self.sub_label.setFont(theme.font_small)
            layout.addWidget(self.sub_label)

        # تم اولیه
        self.apply_theme(theme)

        # تغییر زنده تم
        theme.themeChanged.connect(self._on_theme_changed)

    def _on_theme_changed(self, mode: str):
        self.apply_theme(self.theme)

    def apply_theme(self, theme):
        self.theme = theme

        self.label_widget.setStyleSheet(
            f"color: {theme.colors['text_muted']};"
        )

        color = (
            theme.status_color(self.status)
            if self.status
            else theme.colors["text"]
        )

        self.value_label.setStyleSheet(
            f"color: {color};"
        )

        if self.sub_label is not None:
            self.sub_label.setStyleSheet(
                f"color: {theme.colors['text_muted']};"
            )
class SectionHeader(QWidget):
    def __init__(self, parent, theme, title: str, subtitle: str | None = None):
        super().__init__(parent)

        self.theme = theme

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.title_label = QLabel(title, self)
        self.title_label.setFont(theme.font_subheading)
        layout.addWidget(self.title_label)

        self.subtitle_label = None

        if subtitle:
            self.subtitle_label = QLabel(subtitle, self)
            self.subtitle_label.setFont(theme.font_small)
            layout.addWidget(self.subtitle_label)

        self.apply_theme(theme)
        theme.themeChanged.connect(self._on_theme_changed)

    def _on_theme_changed(self, mode: str):
        self.apply_theme(self.theme)

    def apply_theme(self, theme):
        self.theme = theme

        self.title_label.setStyleSheet(
            f"color: {theme.colors['text']};"
        )

        if self.subtitle_label is not None:
            self.subtitle_label.setStyleSheet(
                f"color: {theme.colors['text_muted']};"
            )