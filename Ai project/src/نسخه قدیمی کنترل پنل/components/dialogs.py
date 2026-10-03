"""control_panel/components/dialogs.py"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import (
    BodyLabel,
    MessageBoxBase,
    PushButton,
    SubtitleLabel,
)


# ============================================================
# Theme helpers
# ============================================================

def _rgba(hex_color: str, alpha: int) -> str:
    """Convert #RRGGBB to rgba(...)."""

    color = QColor(hex_color)

    return (
        f"rgba("
        f"{color.red()}, "
        f"{color.green()}, "
        f"{color.blue()}, "
        f"{alpha})"
    )


def _modern_scrollbar_qss(theme) -> str:
    """Modern native Qt scrollbar.

    No qfluentwidgets.ScrollBar is used.
    """

    c = theme.colors

    return f"""
    /* ========================================================
       Vertical scrollbar
       ======================================================== */

    QScrollBar:vertical {{
        background: transparent;
        width: 9px;
        margin: 3px 2px 3px 3px;
        border: none;
    }}

    QScrollBar::handle:vertical {{
        background-color: {_rgba(c["text_muted"], 95)};
        min-height: 34px;
        border-radius: 4px;
        border: none;
    }}

    QScrollBar::handle:vertical:hover {{
        background-color: {_rgba(c["text_muted"], 150)};
    }}

    QScrollBar::handle:vertical:pressed {{
        background-color: {_rgba(c["accent"], 190)};
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

    /* ========================================================
       Horizontal scrollbar
       ======================================================== */

    QScrollBar:horizontal {{
        background: transparent;
        height: 9px;
        margin: 2px 3px 2px 3px;
        border: none;
    }}

    QScrollBar::handle:horizontal {{
        background-color: {_rgba(c["text_muted"], 95)};
        min-width: 34px;
        border-radius: 4px;
        border: none;
    }}

    QScrollBar::handle:horizontal:hover {{
        background-color: {_rgba(c["text_muted"], 150)};
    }}

    QScrollBar::handle:horizontal:pressed {{
        background-color: {_rgba(c["accent"], 190)};
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
    """


def _add_shadow(widget: QWidget) -> None:
    """Add a subtle floating shadow."""

    shadow = QGraphicsDropShadowEffect(widget)

    shadow.setBlurRadius(34)
    shadow.setOffset(0, 7)
    shadow.setColor(
        QColor(0, 0, 0, 70)
    )

    widget.setGraphicsEffect(
        shadow
    )


# ============================================================
# Confirm Dialog
# ============================================================

class ConfirmDialog(MessageBoxBase):
    """Modern theme-aware confirmation dialog."""

    def __init__(
        self,
        parent,
        theme,
        title: str,
        message: str,
        on_confirm: Callable[[], None],
        confirm_text: str = "Confirm",
        danger: bool = False,
        detail_rows: list[tuple[str, str]] | None = None,
    ):
        super().__init__(parent)

        self.theme = theme

        # --------------------------------------------------------
        # Transparent outer window
        # --------------------------------------------------------

        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_NoSystemBackground,
            True,
        )

        self.setAutoFillBackground(
            False
        )

        self.setStyleSheet(
            f"""
            MessageBoxBase {{
                background: transparent;
                border: none;
            }}

            QLabel {{
                background: transparent;
            }}

            {_modern_scrollbar_qss(theme)}
            """
        )

        # --------------------------------------------------------
        # Main surface
        # --------------------------------------------------------

        self.widget.setObjectName(
            "dialogCard"
        )

        self.widget.setStyleSheet(
            f"""
            QWidget#dialogCard {{
                background-color: {_rgba(theme.colors["surface"], 230)};
                border: 1px solid {_rgba(theme.colors["border"], 185)};
                border-radius: 16px;
            }}
            """
        )

        _add_shadow(
            self.widget
        )

        # --------------------------------------------------------
        # Title
        # --------------------------------------------------------

        self.titleLabel = SubtitleLabel(
            title,
            self.widget,
        )

        self.titleLabel.setObjectName(
            "dialogTitle"
        )

        self.titleLabel.setFont(
            theme.font_subheading
        )

        self.titleLabel.setStyleSheet(
            f"""
            SubtitleLabel {{
                background: transparent;
                color: {theme.colors["text"]};
                border: none;
            }}
            """
        )

        self.viewLayout.addWidget(
            self.titleLabel
        )

        # --------------------------------------------------------
        # Message
        # --------------------------------------------------------

        message_label = BodyLabel(
            message,
            self.widget,
        )

        message_label.setObjectName(
            "dialogMessage"
        )

        message_label.setWordWrap(
            True
        )

        message_label.setStyleSheet(
            f"""
            BodyLabel {{
                background: transparent;
                color: {theme.colors["text"]};
                border: none;
            }}
            """
        )

        self.viewLayout.addWidget(
            message_label
        )

        # --------------------------------------------------------
        # Detail rows
        # --------------------------------------------------------

        if detail_rows:

            details = QWidget(
                self.widget
            )

            details.setStyleSheet(
                """
                QWidget {
                    background: transparent;
                    border: none;
                }
                """
            )

            details_layout = QVBoxLayout(
                details
            )

            details_layout.setContentsMargins(
                0,
                4,
                0,
                4,
            )

            details_layout.setSpacing(
                3
            )

            for label, value in detail_rows:

                row = QWidget(
                    details
                )

                row.setStyleSheet(
                    """
                    QWidget {
                        background: transparent;
                        border: none;
                    }
                    """
                )

                row_layout = QHBoxLayout(
                    row
                )

                row_layout.setContentsMargins(
                    0,
                    3,
                    0,
                    3,
                )

                row_layout.setSpacing(
                    12
                )

                key_label = QLabel(
                    str(label),
                    row
                )

                key_label.setMinimumWidth(
                    90
                )

                key_label.setStyleSheet(
                    f"""
                    QLabel {{
                        background: transparent;
                        color: {theme.colors["text_muted"]};
                        border: none;
                    }}
                    """
                )

                value_label = QLabel(
                    str(value),
                    row
                )

                value_label.setFont(
                    theme.font_body_bold
                )

                value_label.setWordWrap(
                    True
                )

                value_label.setStyleSheet(
                    f"""
                    QLabel {{
                        background: transparent;
                        color: {theme.colors["text"]};
                        border: none;
                    }}
                    """
                )

                row_layout.addWidget(
                    key_label
                )

                row_layout.addWidget(
                    value_label,
                    1,
                )

                details_layout.addWidget(
                    row
                )

            self.viewLayout.addWidget(
                details
            )

        # --------------------------------------------------------
        # Buttons
        # --------------------------------------------------------

        self.yesButton.setText(
            confirm_text
        )

        self.cancelButton.setText(
            "Cancel"
        )

        # --------------------------------------------------------
        # Cancel button
        # --------------------------------------------------------

        self.cancelButton.setStyleSheet(
            f"""
            PushButton {{
                background-color: transparent;
                color: {theme.colors["text"]};

                border: 1px solid {_rgba(theme.colors["border"], 190)};
                border-radius: 8px;

                padding: 4px 11px;
            }}

            PushButton:hover {{
                background-color:
                    {_rgba(theme.colors["sidebar_hover"], 190)};
            }}

            PushButton:pressed {{
                background-color:
                    {_rgba(theme.colors["surface_alt"], 220)};
            }}
            """
        )

        # --------------------------------------------------------
        # Confirm button
        # --------------------------------------------------------

        if danger:

            self.yesButton.setStyleSheet(
                f"""
                PushButton {{
                    background-color:
                        {theme.colors["error"]};

                    color: white;

                    border: none;
                    border-radius: 8px;

                    padding: 4px 12px;
                    font-weight: 600;
                }}

                PushButton:hover {{
                    background-color:
                        {theme.colors["error"]};
                }}

                PushButton:pressed {{
                    background-color:
                        {theme.colors["error"]};
                }}
                """
            )

        else:

            self.yesButton.setStyleSheet(
                f"""
                PushButton {{
                    background-color: transparent;
                    color: {theme.colors["text"]};

                    border: 1px solid
                        {_rgba(theme.colors["border"], 190)};

                    border-radius: 8px;

                    padding: 4px 12px;
                    font-weight: 600;
                }}

                PushButton:hover {{
                    background-color:
                        {_rgba(theme.colors["sidebar_hover"], 190)};
                }}

                PushButton:pressed {{
                    background-color:
                        {_rgba(theme.colors["surface_alt"], 220)};
                }}
                """
            )

        # --------------------------------------------------------
        # Size
        # --------------------------------------------------------

        self.widget.setMinimumWidth(
            440
        )

        self.widget.setMaximumWidth(
            620
        )

        # --------------------------------------------------------
        # Execute
        # --------------------------------------------------------

        confirmed = self.exec()

        if confirmed and on_confirm:
            on_confirm()


# ============================================================
# Info Dialog
# ============================================================

class InfoDialog(QDialog):
    """Modern theme-aware information/detail dialog.

    The outer window is transparent.
    The inner card uses the current theme's surface color.
    No gradient is used.
    """

    def __init__(
        self,
        parent,
        theme,
        title: str,
        sections: list[tuple[str, str]],
        copy_text: str | None = None,
    ):
        super().__init__(parent)

        self.theme = theme

        # --------------------------------------------------------
        # Window
        # --------------------------------------------------------

        self.setWindowTitle(
            title
        )

        self.resize(
            620,
            470
        )

        self.setMinimumSize(
            500,
            340
        )

        # Completely transparent outer window.
        self.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )

        self.setAttribute(
            Qt.WidgetAttribute.WA_NoSystemBackground,
            True,
        )

        self.setAutoFillBackground(
            False
        )

        self.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.FramelessWindowHint
        )

        self.setStyleSheet(
            """
            QDialog {
                background: transparent;
                border: none;
            }
            """
        )

        # --------------------------------------------------------
        # Outer transparent layout
        # --------------------------------------------------------

        outer = QVBoxLayout(
            self
        )

        outer.setContentsMargins(
            10,
            10,
            10,
            10,
        )

        outer.setSpacing(
            0
        )

        # --------------------------------------------------------
        # Dialog card
        # --------------------------------------------------------

        card = QFrame(
            self
        )

        card.setObjectName(
            "dialogCard"
        )

        card.setAttribute(
            Qt.WidgetAttribute.WA_StyledBackground,
            True,
        )

        card.setAutoFillBackground(
            False
        )

        card.setStyleSheet(
            f"""
            QFrame#dialogCard {{
                background-color: {_rgba(theme.colors["surface"], 230)};
                border:
                    1px solid
                    {_rgba(theme.colors["border"], 185)};

                border-radius: 16px;
            }}
            """
        )

        _add_shadow(
            card
        )

        outer.addWidget(
            card
        )

        # --------------------------------------------------------
        # Card layout
        # --------------------------------------------------------

        card_layout = QVBoxLayout(
            card
        )

        card_layout.setContentsMargins(
            18,
            16,
            18,
            16,
        )

        card_layout.setSpacing(
            10
        )

        # --------------------------------------------------------
        # Header
        # --------------------------------------------------------

        header = QHBoxLayout()

        header.setContentsMargins(
            0,
            0,
            0,
            2,
        )

        header.setSpacing(
            8
        )

        title_label = QLabel(
            title,
            card
        )

        title_label.setObjectName(
            "dialogTitle"
        )

        title_label.setFont(
            theme.font_subheading
        )

        title_label.setStyleSheet(
            f"""
            QLabel {{
                background: transparent;
                color: {theme.colors["text"]};
                border: none;
            }}
            """
        )

        header.addWidget(
            title_label,
            1,
        )

        # --------------------------------------------------------
        # Close button
        # --------------------------------------------------------

        close_btn = PushButton(
            "✕",
            card
        )

        close_btn.setFixedSize(
            34,
            34
        )

        close_btn.setToolTip(
            "Close"
        )

        close_btn.setStyleSheet(
            f"""
            PushButton {{
                background-color:
                    {_rgba(theme.colors["surface_alt"], 210)};

                color:
                    {theme.colors["text"]};

                border:
                    1px solid
                    {_rgba(theme.colors["border"], 200)};

                border-radius:
                    8px;

                font-size:
                    15px;

                font-weight:
                    600;

                padding:
                    0px;
            }}

            PushButton:hover {{
                background-color:
                    {_rgba(theme.colors["sidebar_hover"], 230)};

                color:
                    {theme.colors["text"]};
            }}

            PushButton:pressed {{
                background-color:
                    {_rgba(theme.colors["surface_alt"], 245)};
            }}
            """
        )

        close_btn.clicked.connect(
            self.accept
        )

        header.addWidget(
            close_btn,
            0,
            Qt.AlignmentFlag.AlignTop,
        )

        card_layout.addLayout(
            header
        )

        # --------------------------------------------------------
        # Thin accent divider
        # --------------------------------------------------------

        divider = QFrame(
            card
        )

        divider.setFixedHeight(
            1
        )

        divider.setStyleSheet(
            f"""
            QFrame {{
                background-color:
                    {_rgba(theme.colors["border"], 150)};
                border: none;
            }}
            """
        )

        card_layout.addWidget(
            divider
        )

        # --------------------------------------------------------
        # Scroll area
        # --------------------------------------------------------

        scroll = QScrollArea(
            card
        )

        scroll.setWidgetResizable(
            True
        )

        scroll.setFrameShape(
            QScrollArea.Shape.NoFrame
        )

        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )

        scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        scroll.setStyleSheet(
            f"""
            QScrollArea {{
                background: transparent;
                border: none;
                outline: none;
            }}

            QScrollArea > QWidget {{
                background: transparent;
                border: none;
            }}

            QScrollArea > QWidget > QWidget {{
                background: transparent;
                border: none;
            }}

            {_modern_scrollbar_qss(theme)}
            """
        )

        card_layout.addWidget(
            scroll,
            1
        )

        # --------------------------------------------------------
        # Scroll content
        # --------------------------------------------------------

        inner = QWidget(
            scroll
        )

        inner.setAttribute(
            Qt.WidgetAttribute.WA_TranslucentBackground,
            True,
        )

        inner.setStyleSheet(
            """
            QWidget {
                background: transparent;
                border: none;
            }
            """
        )

        inner_layout = QVBoxLayout(
            inner
        )

        inner_layout.setContentsMargins(
            0,
            2,
            6,
            2,
        )

        inner_layout.setSpacing(
            8
        )

        # --------------------------------------------------------
        # Sections
        # --------------------------------------------------------

        for label, value in sections:

            if label:

                label_widget = QLabel(
                    str(label),
                    inner
                )

                label_widget.setFont(
                    theme.font_small
                )

                label_widget.setStyleSheet(
                    f"""
                    QLabel {{
                        background: transparent;
                        color: {theme.colors["text_muted"]};
                        border: none;
                    }}
                    """
                )

                inner_layout.addWidget(
                    label_widget
                )

            box = QPlainTextEdit(
                inner
            )

            box.setPlainText(
                str(value)
            )

            box.setReadOnly(
                True
            )

            box.setLineWrapMode(
                QPlainTextEdit.LineWrapMode.WidgetWidth
            )

            box.setFont(
                theme.font_mono
            )

            box.setStyleSheet(
                f"""
                QPlainTextEdit {{
                    background-color:
                        {theme.colors["surface_alt"]};

                    color:
                        {theme.colors["text"]};

                    border:
                        1px solid
                        {_rgba(theme.colors["border"], 170)};

                    border-radius:
                        9px;

                    padding:
                        8px 10px;

                    selection-background-color:
                        {theme.colors["accent"]};

                    selection-color:
                        white;
                }}

                QPlainTextEdit:focus {{
                    border:
                        1px solid
                        {theme.colors["accent"]};
                }}

                {_modern_scrollbar_qss(theme)}
                """
            )

            line_count = (
                str(value).count("\n")
                + 2
            )

            box.setFixedHeight(
                min(
                    240,
                    max(
                        44,
                        line_count * 18,
                    ),
                )
            )

            inner_layout.addWidget(
                box
            )

        inner_layout.addStretch(
            1
        )

        scroll.setWidget(
            inner
        )

        # --------------------------------------------------------
        # Bottom buttons
        # --------------------------------------------------------

        button_row = QHBoxLayout()

        button_row.setContentsMargins(
            0,
            2,
            0,
            0,
        )

        button_row.setSpacing(
            8
        )

        button_row.addStretch(
            1
        )

        # --------------------------------------------------------
        # Copy button
        # --------------------------------------------------------

        if copy_text is not None:

            copy_btn = PushButton(
                "Copy",
                card
            )

            copy_btn.setStyleSheet(
                f"""
                PushButton {{
                    background-color: transparent;
                    color: {theme.colors["text"]};

                    border:
                        1px solid
                        {_rgba(theme.colors["border"], 190)};

                    border-radius:
                        8px;

                    padding:
                        4px 12px;
                }}

                PushButton:hover {{
                    background-color:
                        {_rgba(theme.colors["sidebar_hover"], 190)};
                }}

                PushButton:pressed {{
                    background-color:
                        {_rgba(theme.colors["surface_alt"], 230)};
                }}
                """
            )

            copy_btn.clicked.connect(
                lambda:
                    QApplication.clipboard().setText(
                        copy_text
                    )
            )

            button_row.addWidget(
                copy_btn
            )

        # --------------------------------------------------------
        # Close button
        # --------------------------------------------------------

        bottom_close_btn = PushButton(
            "Close",
            card
        )

        bottom_close_btn.setStyleSheet(
            f"""
            PushButton {{
                background-color:
                    {_rgba(theme.colors["surface_alt"], 205)};

                color:
                    {theme.colors["text"]};

                border:
                    1px solid
                    {_rgba(theme.colors["border"], 190)};

                border-radius:
                    8px;

                padding:
                    4px 12px;
            }}

            PushButton:hover {{
                background-color:
                    {_rgba(theme.colors["sidebar_hover"], 220)};
            }}

            PushButton:pressed {{
                background-color:
                    {_rgba(theme.colors["surface_alt"], 245)};
            }}
            """
        )

        bottom_close_btn.clicked.connect(
            self.accept
        )

        button_row.addWidget(
            bottom_close_btn
        )

        card_layout.addLayout(
            button_row
        )

        # --------------------------------------------------------
        # Execute
        # --------------------------------------------------------

        self.exec()

    # ============================================================
    # Keyboard
    # ============================================================

    def keyPressEvent(
        self,
        event,
    ) -> None:

        if event.key() == Qt.Key.Key_Escape:
            self.accept()
            return

        super().keyPressEvent(
            event
        )
