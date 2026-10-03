"""control_panel/pages/setup.py — two-phase Setup (training → production)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from qfluentwidgets import CheckBox, LineEdit, PasswordLineEdit, PushButton

from ..components.cards import SectionHeader
from ..components.dialogs import ConfirmDialog
from ..components.progress import ProgressView
from ..components.terminal import TerminalOutput
from ..services import setup_service
from ..workers.signals import CallbackBridge

DB_FIELDS = [
    ("DB_HOST", "Host"),
    ("DB_PORT", "Port"),
    ("DB_DATABASE", "Database"),
    ("DB_USERNAME", "Username"),
    ("DB_PASSWORD", "Password"),
]


class SetupPage(QWidget):
    def __init__(self, parent, theme, app):
        super().__init__(parent)
        self.theme = theme
        self.app = app
        self._running = False
        self._on_line: CallbackBridge | None = None
        self._on_done: CallbackBridge | None = None
        self._fields: dict[str, LineEdit] = {}
        self._field_labels: dict[str, QLabel] = {}

        self._build()
        self.theme.themeChanged.connect(lambda *_: self.refresh_theme())
        self.refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        outer.addWidget(
            SectionHeader(
                self,
                self.theme,
                "Setup",
                "Phase 1 on a full-data machine (train models). "
                "Phase 2 on the production server (permanent DB env). "
                "Prediction is DB-only — no CSV required at runtime.",
            )
        )

        self.status_label = QLabel("", self)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {self.theme.colors['text']};")
        outer.addWidget(self.status_label)

        # DB form
        form = QGridLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        for row, (key, label) in enumerate(DB_FIELDS):
            lbl = QLabel(label, self)
            lbl.setStyleSheet(f"color: {self.theme.colors['text']};")
            form.addWidget(lbl, row, 0)
            self._field_labels[key] = lbl
            if key == "DB_PASSWORD":
                edit = PasswordLineEdit(self)
            else:
                edit = LineEdit(self)
            edit.setFixedWidth(280)
            if key == "DB_PORT":
                edit.setText("3306")
            self._fields[key] = edit
            form.addWidget(edit, row, 1)
        outer.addLayout(form)

        btn_row = QHBoxLayout()
        self.save_env_btn = PushButton("Save DB Environment", self)
        self.save_env_btn.clicked.connect(self._on_save_env)
        btn_row.addWidget(self.save_env_btn)

        self.permanent_cb = CheckBox("Set permanently (OS user + project file)", self)
        self.permanent_cb.setChecked(False)
        btn_row.addWidget(self.permanent_cb)
        btn_row.addStretch(1)
        outer.addLayout(btn_row)

        phase_row = QHBoxLayout()
        self.train_btn = PushButton("Run Training Phase", self)
        self.train_btn.clicked.connect(lambda: self._on_run_phase("training"))
        phase_row.addWidget(self.train_btn)

        self.prod_btn = PushButton("Run Production Phase", self)
        self.prod_btn.clicked.connect(lambda: self._on_run_phase("production"))
        phase_row.addWidget(self.prod_btn)
        phase_row.addStretch(1)
        outer.addLayout(phase_row)

        self.hint_label = QLabel(
            "Training phase: use the database that already has full history.\n"
            "After it finishes, copy this AI Project folder to the production server,\n"
            "then open Setup there, enter production DB credentials, and run Production phase."
            "Production phase also registers scheduler.py to run daily at 00:10 (24:10) via Task Scheduler (Windows) or crontab/systemd (Linux).",
            self,
        )
        self.hint_label.setWordWrap(True)
        self.hint_label.setStyleSheet(f"color: {self.theme.colors['text']};")
        outer.addWidget(self.hint_label)

        self.progress = ProgressView(self, self.theme)
        outer.addWidget(self.progress)

        self.output = TerminalOutput(self, self.theme, height=14)
        outer.addWidget(self.output, 1)

    def refresh(self) -> None:
        st = setup_service.get_status()
        phase = st.get("phase", "not_started")
        self.status_label.setText(
            f"Setup phase: {phase}\n"
            f"Updated: {st.get('updated_at') or '—'}\n"
            f"Last error: {st.get('last_error') or '—'}"
        )
        env = setup_service.get_db_env()
        for key, edit in self._fields.items():
            if key in env and key != "DB_PASSWORD":
                edit.setText(env[key])
            elif key == "DB_PORT" and not edit.text():
                edit.setText(env.get("DB_PORT", "3306"))

    def _collect_env(self) -> dict:
        values = {}
        for key, edit in self._fields.items():
            values[key] = edit.text().strip()
        missing = [k for k in ("DB_HOST", "DB_DATABASE", "DB_USERNAME", "DB_PASSWORD") if not values.get(k)]
        if missing:
            raise ValueError("Missing: " + ", ".join(missing))
        return values

    def _on_save_env(self) -> None:
        try:
            values = self._collect_env()
        except ValueError as exc:
            self.app.show_error("DB Environment", str(exc))
            return
        permanent = self.permanent_cb.isChecked()
        result = setup_service.save_database_env(values, permanent=permanent)
        self.output.append_line("Saved DB environment.")
        for n in result.get("notes") or []:
            self.output.append_line(str(n))
        self.refresh()

    def _on_run_phase(self, phase: str) -> None:
        if self._running:
            return
        try:
            values = self._collect_env()
        except ValueError as exc:
            self.app.show_error("Setup", str(exc))
            return

        # Always save before running so the worker sees credentials
        setup_service.save_database_env(
            values,
            permanent=(phase == "production") or self.permanent_cb.isChecked(),
        )

        message = (
            "Train on this machine's database, build models + training CSVs, "
            "then copy the project folder to production."
            if phase == "training"
            else
            "Configure permanent DB environment on the production server. "
            "Models should already exist from the training phase transfer."
        )

        def _start() -> None:
            self._start_phase(phase)

        ConfirmDialog(
            self.app.root if hasattr(self.app, "root") else self,
            self.theme,
            f"Setup — {phase.title()} Phase",
            message,
            on_confirm=_start,
            confirm_text="Run",
        )

    def _start_phase(self, phase: str) -> None:
        if self._running:
            return
        self._running = True
        self.train_btn.setEnabled(False)
        self.prod_btn.setEnabled(False)
        self.output.clear()
        self.progress.start(f"Setup {phase} phase...")

        self._on_line = CallbackBridge(self)
        self._on_done = CallbackBridge(self)
        self._on_line.fired.connect(lambda args: self.output.append_line(args[0] if args else ""))
        self._on_done.fired.connect(lambda args: self._handle_done(*(args if args else (None, 1))))

        setup_service.run_setup_phase(phase, on_line=self._on_line, on_done=self._on_done)

    def _handle_done(self, result=None, code=1) -> None:
        self._running = False
        self.train_btn.setEnabled(True)
        self.prod_btn.setEnabled(True)
        self.progress.stop()
        if result and result.get("ok"):
            self.output.append_line(f"\nPhase OK: {result.get('phase')}")
        else:
            err = (result or {}).get("error") or f"exit {code}"
            self.output.append_line(f"\nPhase failed: {err}")
        self.refresh()

    def refresh_theme(self) -> None:
        self.status_label.setStyleSheet(f"color: {self.theme.colors['text']};")
        self.hint_label.setStyleSheet(f"color: {self.theme.colors['text']};")
        # These (Host/Port/Database/Username/Password) were never re-styled
        # on theme toggle before -- they kept their original color and went
        # out of sync with the rest of the page after switching modes.
        for lbl in self._field_labels.values():
            lbl.setStyleSheet(f"color: {self.theme.colors['text']};")

    def on_navigate(self, context=None) -> None:
        self.refresh()