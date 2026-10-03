"""control_panel/pages/model_builder.py

Global Learning Cycle UI: three independent horizon configuration blocks
(3-Day / Weekly / Monthly) + one RUN GLOBAL LEARNING CYCLE action.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import CheckBox, ComboBox, LineEdit, PushButton

from ..components.cards import SectionHeader, force_transparent, style_scroll_area_transparent
from ..components.dialogs import ConfirmDialog
from ..components.progress import ProgressView
from ..components.terminal import TerminalOutput
from ..services import log_service, model_service
from ..workers.signals import CallbackBridge

HORIZONS = ("3day", "weekly", "monthly")
HORIZON_LABELS = {
    "3day": "3-Day",
    "weekly": "Weekly",
    "monthly": "Monthly",
}


class _HorizonConfigBlock(QFrame):
    """One independent algorithm + params form for a single horizon."""

    def __init__(self, parent: QWidget, theme, horizon: str):
        super().__init__(parent)
        self.theme = theme
        self.horizon = horizon
        self._param_widgets: dict[str, tuple[dict, QWidget]] = {}
        self._param_labels: list[QLabel] = []

        self.setObjectName(f"horizonBlock_{horizon}")
        # QSS "background: transparent" and autoFillBackground(False) alone
        # weren't holding up -- force_transparent also zeroes the palette's
        # own background colors so there is nothing opaque left to paint.
        force_transparent(self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        title = QLabel(f"{HORIZON_LABELS[horizon]} settings", self)
        title.setStyleSheet(
            f"color: {theme.colors['text']}; font-weight: 600; font-size: 13px;"
        )
        layout.addWidget(title)
        self.title_label = title

        algo_row = QHBoxLayout()
        algo_lbl = QLabel("Algorithm", self)
        algo_lbl.setStyleSheet(f"color: {theme.colors['text']};")
        algo_row.addWidget(algo_lbl)
        self.algorithm_combo = ComboBox(self)
        self.algorithm_combo.addItems(model_service.ALGORITHMS)
        self.algorithm_combo.setCurrentText("ridge")
        self.algorithm_combo.setFixedWidth(180)
        self.algorithm_combo.currentTextChanged.connect(lambda *_: self._render_params())
        algo_row.addWidget(self.algorithm_combo)
        algo_row.addStretch(1)
        layout.addLayout(algo_row)
        self.algo_label = algo_lbl

        self.params_widget = QWidget(self)
        self.params_layout = QGridLayout(self.params_widget)
        self.params_layout.setContentsMargins(0, 0, 0, 0)
        self.params_layout.setHorizontalSpacing(12)
        self.params_layout.setVerticalSpacing(4)
        self.params_layout.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
        )
        layout.addWidget(self.params_widget)

        self._render_params()
        self._apply_frame_style()

    def _apply_frame_style(self) -> None:
        # Re-applied on every theme refresh too, in case anything reset it.
        force_transparent(self)
        border = self.theme.colors.get("border", "#444")
        # Kept transparent (like the app's cards/buttons use for their
        # resting state) instead of a flat fill -- only the border marks
        # the card's edge.
        self.setStyleSheet(
            f"QFrame#horizonBlock_{self.horizon} {{"
            f" border: 1px solid {border}; border-radius: 8px;"
            f" background: transparent !important; }}"
        )

    def _render_params(self) -> None:
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._param_widgets.clear()
        self._param_labels.clear()

        algo = self.algorithm_combo.currentText()
        specs = model_service.ALGORITHM_PARAM_SPECS.get(algo, [])
        for i, spec in enumerate(specs):
            label = QLabel(spec["name"], self.params_widget)
            label.setStyleSheet(f"color: {self.theme.colors['text']};")
            self.params_layout.addWidget(label, 0, i)
            self._param_labels.append(label)

            if spec["type"] == "bool":
                widget = CheckBox(self.params_widget)
                widget.setChecked(bool(spec["default"]))
            elif spec["type"] == "choice":
                widget = ComboBox(self.params_widget)
                widget.addItems(spec["choices"])
                widget.setCurrentText(str(spec["default"]))
                widget.setFixedWidth(140)
            else:
                widget = LineEdit(self.params_widget)
                widget.setFixedWidth(140)
                widget.setText(str(spec["default"]))

            self.params_layout.addWidget(widget, 1, i)
            self._param_widgets[spec["name"]] = (spec, widget)

    def collect(self) -> dict:
        params: dict = {}
        for name, (spec, widget) in self._param_widgets.items():
            if spec["type"] == "bool":
                raw = widget.isChecked()
            elif spec["type"] == "choice":
                raw = widget.currentText()
            else:
                raw = widget.text()

            if spec["type"] == "int":
                params[name] = int(raw)
            elif spec["type"] == "float":
                params[name] = float(raw)
            elif spec["type"] == "int_or_none":
                params[name] = (
                    None
                    if str(raw).strip().lower() in ("", "none")
                    else int(raw)
                )
            elif spec["type"] == "bool":
                params[name] = bool(raw)
            elif spec["type"] == "choice" and name == "max_features":
                params[name] = float(raw) if raw == "1.0" else raw
            else:
                params[name] = raw

        return {
            "algorithm": self.algorithm_combo.currentText(),
            "params": params,
        }

    def refresh_theme(self) -> None:
        self.title_label.setStyleSheet(
            f"color: {self.theme.colors['text']}; font-weight: 600; font-size: 13px;"
        )
        self.algo_label.setStyleSheet(f"color: {self.theme.colors['text']};")
        for label in self._param_labels:
            label.setStyleSheet(f"color: {self.theme.colors['text']};")
        self._apply_frame_style()


class ModelBuilderPage(QWidget):
    def __init__(self, parent, theme, app):
        super().__init__(parent)
        self.theme = theme
        self.app = app
        self._running = False
        self._last_result: dict | None = None
        self._on_line: CallbackBridge | None = None
        self._on_done: CallbackBridge | None = None
        self._horizon_blocks: dict[str, _HorizonConfigBlock] = {}

        self._build()
        self.theme.themeChanged.connect(self._on_theme_changed)

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        outer.addWidget(
            SectionHeader(
                self,
                self.theme,
                "Global Learning Cycle",
                "Configure each horizon independently, then run one unified cycle: "
                "3-Day + Weekly + Monthly. Promotion is per-horizon on the Models page.",
            )
        )

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_body = QWidget()
        scroll_layout = QVBoxLayout(scroll_body)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(10)

        for h in HORIZONS:
            block = _HorizonConfigBlock(scroll_body, self.theme, h)
            self._horizon_blocks[h] = block
            scroll_layout.addWidget(block)

        scroll_layout.addStretch(1)
        scroll.setWidget(scroll_body)
        style_scroll_area_transparent(scroll)
        outer.addWidget(scroll, 0)

        # Actions
        self.action_panel = QWidget(self)
        self.action_panel.setObjectName("modelBuilderActions")
        action_layout = QHBoxLayout(self.action_panel)
        action_layout.setContentsMargins(0, 4, 0, 4)
        action_layout.setSpacing(10)

        self.run_btn = PushButton("RUN GLOBAL LEARNING CYCLE", self.action_panel)
        self.run_btn.setFixedHeight(36)
        self.run_btn.clicked.connect(self._on_run)
        action_layout.addWidget(self.run_btn)

        self.skip_rebuild_cb = CheckBox("Skip dataset rebuild", self.action_panel)
        self.skip_rebuild_cb.setChecked(False)  # default: rebuild from DB
        self.skip_rebuild_cb.setToolTip(
            "When unchecked (default), export DB → daily → feature_dataset before training. "
            "Check only for offline/dev without database access."
        )
        action_layout.addWidget(self.skip_rebuild_cb)

        self.promote_hint = QLabel(
            "Promotion is per-horizon on the Models page (no Promote All).",
            self.action_panel,
        )
        self.promote_hint.setStyleSheet(f"color: {self.theme.colors['text']};")
        action_layout.addWidget(self.promote_hint)
        action_layout.addStretch(1)
        outer.addWidget(self.action_panel)

        self.progress = ProgressView(self, self.theme)
        outer.addWidget(self.progress)

        self.result_label = QLabel("", self)
        self.result_label.setWordWrap(True)
        self.result_label.setStyleSheet(f"color: {self.theme.colors['text']};")
        outer.addWidget(self.result_label)

        self.output = TerminalOutput(self, self.theme, height=14)
        outer.addWidget(self.output, 1)

    def _collect_horizon_configs(self) -> dict:
        return {h: block.collect() for h, block in self._horizon_blocks.items()}

    def _on_run(self) -> None:
        if self._running:
            return
        try:
            configs = self._collect_horizon_configs()
        except (ValueError, TypeError) as exc:
            self.result_label.setText(f"Invalid parameters: {exc}")
            return

        parent = self.app.root if hasattr(self.app, "root") else self

        def _start() -> None:
            self._start_cycle(configs, promote=False)

        ConfirmDialog(
            parent,
            self.theme,
            "Run Global Learning Cycle",
            "Train and validate candidates for 3-Day, Weekly, and Monthly."
            "Candidates are stored but NOT promoted automatically."
            "Promote each horizon independently on the Models page.",
            on_confirm=_start,
            confirm_text="Run Cycle",
        )

    def _start_cycle(self, configs: dict, *, promote: bool) -> None:
        self._running = True
        self.run_btn.setEnabled(False)
        self.output.clear()
        self.result_label.setText("Global Learning Cycle running...")
        self.progress.start("Running Global Learning Cycle...")

        self._on_line = CallbackBridge(self)
        self._on_done = CallbackBridge(self)
        self._on_line.fired.connect(lambda args: self._handle_line(args[0] if args else ""))
        self._on_done.fired.connect(lambda args: self._handle_done(*(args if args else (None, 1))))

        request = model_service.GlobalCycleRequest(
            horizon_configs=configs,
            promote=promote,
            rebuild_datasets=not self.skip_rebuild_cb.isChecked(),
        )
        model_service.run_global_cycle(
            request,
            on_line=self._on_line,
            on_done=self._on_done,
        )

    def _handle_line(self, line: str) -> None:
        self.output.append_line(line)

    def _handle_done(self, result=None, code=1) -> None:

        self._running = False
        self.run_btn.setEnabled(True)
        self.progress.stop()

        if not result or not result.get("ok", True) and result.get("error"):
            error = (result or {}).get("error") or f"exit code {code}"
            self.result_label.setText(f"Cycle failed: {error}")
            self._last_result = None
            return

        report = result.get("report") or result
        models = report.get("models") or {}
        lines = ["GLOBAL LEARNING CYCLE COMPLETE"]
        for h in HORIZONS:
            entry = models.get(h) or {}
            status = entry.get("status", "?")
            cmp_ = entry.get("comparison", "-")
            promo = entry.get("promotion", "-")
            m = entry.get("metrics") or {}
            lines.append(
                f"  [{HORIZON_LABELS[h]}] status={status}  cmp={cmp_}  promo={promo}  "
                f"MAE={m.get('mae', float('nan')):.4f}  R2={m.get('r2', float('nan')):.4f}"
            )
        self.result_label.setText("\n".join(lines))
        self._last_result = report

        log_service.log_event(
            "GLOBAL_LEARNING_CYCLE",
            component="model_builder_page",
            message=f"cycle_id={report.get('cycle_id')} code={code}",
        )

    def _on_theme_changed(self, mode: str) -> None:
        self.refresh_theme()

    def refresh_theme(self) -> None:
        self.result_label.setStyleSheet(f"color: {self.theme.colors['text']};")
        self.promote_hint.setStyleSheet(f"color: {self.theme.colors['text']};")
        for block in self._horizon_blocks.values():
            block.refresh_theme()