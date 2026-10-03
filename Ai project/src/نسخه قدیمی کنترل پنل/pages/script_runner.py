"""control_panel/pages/script_runner.py"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import CheckBox, LineEdit, PushButton

from ..components.cards import Card, SectionHeader
from ..components.dialogs import ConfirmDialog
from ..components.progress import ProgressView
from ..components.terminal import TerminalOutput
from ..services import log_service, script_service
from ..workers.signals import CallbackBridge


DANGEROUS_SCRIPTS = {"Global Learning Cycle"}


class ScriptRunnerPage(QWidget):
    def __init__(self, parent, theme, app):
        super().__init__(parent)

        self.theme = theme
        self.app = app

        self._selected_script: str | None = None

        # value: (kind, widget)
        self._arg_widgets: dict[str, tuple[str, QWidget]] = {}

        self._script_buttons: dict[str, PushButton] = {}

        self._running = False

        # CallbackBridge instances are recreated per run and kept alive
        # while callbacks are being delivered from background threads.
        self._on_line: CallbackBridge | None = None
        self._on_done: CallbackBridge | None = None

        self._build()

        # Live theme updates.
        self.theme.themeChanged.connect(
            self._on_theme_changed
        )

        self._render_script_list()

    # ============================================================
    # Theme helpers
    # ============================================================

    def _apply_label_theme(
        self,
        label: QLabel,
        muted: bool = False,
    ) -> None:
        """Apply the current theme color to a QLabel."""

        color = (
            self.theme.colors["text_muted"]
            if muted
            else self.theme.colors["text"]
        )

        label.setStyleSheet(
            f"""
            QLabel {{
                color: {color};
                background: transparent;
                border: none;
            }}
            """
        )

    # ============================================================
    # Build UI
    # ============================================================

    def _build(self) -> None:
        outer = QVBoxLayout(self)

        outer.setContentsMargins(
            20,
            20,
            20,
            20,
        )

        outer.setSpacing(
            12
        )

        # --------------------------------------------------------
        # Header
        # --------------------------------------------------------

        outer.addWidget(
            SectionHeader(
                self,
                self.theme,
                "Script Runner",
                "Only scripts in the registry can run -- arguments match the real code exactly.",
            )
        )

        # --------------------------------------------------------
        # Main body
        # --------------------------------------------------------

        body = QHBoxLayout()

        body.setSpacing(
            8
        )

        # ========================================================
        # Left card
        # ========================================================

        left_card = Card(
            self,
            self.theme,
            padding=10,
        )

        left_body = left_card.body

        left_layout = QVBoxLayout(
            left_body
        )

        left_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        left_layout.setSpacing(
            4
        )

        self.search_label = QLabel(
            "Search Script",
            left_body,
        )

        self._apply_label_theme(
            self.search_label
        )

        left_layout.addWidget(
            self.search_label
        )

        self.search_edit = LineEdit(
            left_body
        )

        self.search_edit.setFixedWidth(
            220
        )

        self.search_edit.textChanged.connect(
            lambda *_:
                self._render_script_list()
        )

        left_layout.addWidget(
            self.search_edit
        )

        # --------------------------------------------------------
        # Script list
        # --------------------------------------------------------

        self.script_list_layout = QVBoxLayout()

        self.script_list_layout.setContentsMargins(
            0,
            4,
            0,
            0,
        )

        self.script_list_layout.setSpacing(
            1
        )

        self.script_list_layout.addStretch(
            1
        )

        left_layout.addLayout(
            self.script_list_layout,
            1,
        )

        body.addWidget(
            left_card,
            1,
        )

        # ========================================================
        # Right side
        # ========================================================

        right = QWidget(
            self
        )

        right_layout = QVBoxLayout(
            right
        )

        right_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        right_layout.setSpacing(
            8
        )

        # --------------------------------------------------------
        # Description
        # --------------------------------------------------------

        self.description_label = QLabel(
            "Select a script.",
            right,
        )

        self.description_label.setWordWrap(
            True
        )

        self._apply_label_theme(
            self.description_label
        )

        right_layout.addWidget(
            self.description_label
        )

        # --------------------------------------------------------
        # Arguments
        # --------------------------------------------------------

        self.args_widget = QWidget(
            right
        )

        self.args_layout = QGridLayout(
            self.args_widget
        )

        self.args_layout.setContentsMargins(
            0,
            0,
            0,
            0,
        )

        self.args_layout.setHorizontalSpacing(
            8
        )

        self.args_layout.setVerticalSpacing(
            4
        )

        right_layout.addWidget(
            self.args_widget
        )

        # --------------------------------------------------------
        # Run button
        #
        # Same as Dashboard Refresh:
        # plain PushButton, no local stylesheet.
        # --------------------------------------------------------

        self.run_btn = PushButton(
            "Run Script",
            right,
        )

        self.run_btn.clicked.connect(
            self._on_run
        )

        right_layout.addWidget(
            self.run_btn,
            0,
        )

        # --------------------------------------------------------
        # Progress
        # --------------------------------------------------------

        self.progress = ProgressView(
            right,
            self.theme,
        )

        self.progress.setVisible(
            False
        )

        right_layout.addWidget(
            self.progress
        )

        # --------------------------------------------------------
        # Terminal
        # --------------------------------------------------------

        self.output = TerminalOutput(
            right,
            self.theme,
            height=16,
        )

        right_layout.addWidget(
            self.output,
            1,
        )

        body.addWidget(
            right,
            2,
        )

        outer.addLayout(
            body,
            1,
        )

    # ============================================================
    # Script list
    # ============================================================

    def _render_script_list(self) -> None:
        while self.script_list_layout.count() > 1:
            item = self.script_list_layout.takeAt(
                0
            )

            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        self._script_buttons.clear()

        needle = (
            self.search_edit
            .text()
            .strip()
            .lower()
        )

        for name in script_service.registry_names():

            if needle and needle not in name.lower():
                continue

            # Same plain PushButton used by Dashboard Refresh.
            btn = PushButton(
                name,
                self,
            )

            btn.clicked.connect(
                lambda checked=False, n=name:
                    self._select_script(n)
            )

            self.script_list_layout.insertWidget(
                self.script_list_layout.count() - 1,
                btn,
            )

            self._script_buttons[name] = btn

    # ============================================================
    # Script selection
    # ============================================================

    def _select_script(
        self,
        name: str,
    ) -> None:
        self._selected_script = name

        spec = script_service.get_script(
            name
        )

        desc = spec.get(
            "description",
            "",
        )

        if spec.get(
            "requires_db"
        ):
            desc += (
                "\n\n"
                "⚠ Requires DB_HOST/DB_DATABASE/DB_USERNAME/DB_PASSWORD to be configured."
            )

        self.description_label.setText(
            f"{name}\n{desc}"
        )

        # --------------------------------------------------------
        # Clear old arguments
        # --------------------------------------------------------

        while self.args_layout.count():
            item = self.args_layout.takeAt(
                0
            )

            widget = item.widget()

            if widget is not None:
                widget.deleteLater()

        self._arg_widgets.clear()

        # --------------------------------------------------------
        # Build arguments
        # --------------------------------------------------------

        for i, arg in enumerate(
            spec["arguments"]
        ):

            if arg["kind"] == "flag":

                checkbox = CheckBox(
                    arg["label"],
                    self.args_widget,
                )

                checkbox.setChecked(
                    False
                )

                self.args_layout.addWidget(
                    checkbox,
                    i,
                    0,
                    1,
                    2,
                )

                self._arg_widgets[
                    arg["name"]
                ] = (
                    "flag",
                    checkbox,
                )

            else:

                label = QLabel(
                    arg["label"],
                    self.args_widget,
                )

                self._apply_label_theme(
                    label
                )

                self.args_layout.addWidget(
                    label,
                    i,
                    0,
                )

                edit = LineEdit(
                    self.args_widget
                )

                edit.setFixedWidth(
                    160
                )

                edit.setText(
                    str(
                        arg.get(
                            "default",
                            "",
                        )
                    )
                )

                self.args_layout.addWidget(
                    edit,
                    i,
                    1,
                )

                self._arg_widgets[
                    arg["name"]
                ] = (
                    arg["kind"],
                    edit,
                )

    # ============================================================
    # Running state
    # ============================================================

    def _set_running(
        self,
        running: bool,
    ) -> None:
        self._running = running

        self.run_btn.setEnabled(
            not running
        )

        if running:

            self.progress.setVisible(
                True
            )

            self.progress.start(
                "Running..."
            )

        else:

            self.progress.stop()

            self.progress.setVisible(
                False
            )

    # ============================================================
    # Run
    # ============================================================

    def _on_run(self) -> None:
        name = self._selected_script

        if not name or self._running:
            return

        promote_entry = (
            self._arg_widgets.get(
                "promote"
            )
        )

        promote_checked = bool(
            promote_entry
            and promote_entry[0] == "flag"
            and promote_entry[1].isChecked()
        )

        if (
            name in DANGEROUS_SCRIPTS
            and promote_checked
        ):

            ConfirmDialog(
                self.app.root,
                self.theme,
                "WARNING",
                (
                    f"'{name}' is running with promotion enabled "
                    "and may replace the Production Model."
                ),
                on_confirm=lambda:
                    self._execute(name),
                confirm_text="Run Anyway",
                danger=True,
            )

            return

        self._execute(
            name
        )

    # ============================================================
    # Execute
    # ============================================================

    def _execute(
        self,
        name: str,
    ) -> None:
        values = {}

        for key, (
            kind,
            widget,
        ) in self._arg_widgets.items():

            values[key] = (
                widget.isChecked()
                if kind == "flag"
                else widget.text()
            )

        try:

            self._set_running(
                True
            )

            self.output.clear()

            self.output.append_line(
                f"> {name}"
            )

            # CallbackBridge converts background-thread callbacks
            # into queued Qt signals.
            self._on_line = CallbackBridge(
                self
            )

            self._on_line.fired.connect(
                lambda args:
                    self.output.append_line(
                        args[0]
                    )
            )

            self._on_done = CallbackBridge(
                self
            )

            self._on_done.fired.connect(
                lambda args:
                    self._finish(
                        name,
                        args[0],
                    )
            )

            log_service.log_event(
                "SCRIPT_START",
                component="script_runner_page",
                message=name,
            )

            script_service.run_script(
                name,
                values,
                self._on_line,
                self._on_done,
            )

        except Exception as exc:  # noqa: BLE001

            self._set_running(
                False
            )

            log_service.log_event(
                "SCRIPT_FAILURE",
                level="ERROR",
                component="script_runner_page",
                message=f"{name}: {exc}",
            )

            self.app.show_error(
                "Failed to start script",
                str(exc),
            )

    # ============================================================
    # Finish
    # ============================================================

    def _finish(
        self,
        name: str,
        code: int,
    ) -> None:
        self._set_running(
            False
        )

        self.output.append_line(
            f"\nProcess finished. Exit Code: {code}"
        )

        event = (
            "SCRIPT_FINISH"
            if code == 0
            else "SCRIPT_FAILURE"
        )

        log_service.log_event(
            event,
            level=(
                "INFO"
                if code == 0
                else "ERROR"
            ),
            component="script_runner_page",
            message=f"{name} exit_code={code}",
        )

    # ============================================================
    # Theme
    # ============================================================

    def _on_theme_changed(
        self,
        mode: str,
    ) -> None:
        self.refresh_theme()

    def refresh_theme(self) -> None:
        """Refresh page-specific colors after Light/Dark changes."""

        self._apply_label_theme(
            self.search_label
        )

        self._apply_label_theme(
            self.description_label
        )

        # Re-render list so newly created buttons use the
        # current global PushButton style.
        self._render_script_list()

        # Refresh dynamic argument labels.
        for i in range(
            self.args_layout.count()
        ):
            item = self.args_layout.itemAt(
                i
            )

            if item is None:
                continue

            widget = item.widget()

            if isinstance(
                widget,
                QLabel,
            ):
                self._apply_label_theme(
                    widget
                )

        # Terminal
        if hasattr(
            self.output,
            "refresh_theme",
        ):
            self.output.refresh_theme()

        # Progress
        if hasattr(
            self.progress,
            "refresh_theme",
        ):
            self.progress.refresh_theme()