"""control_panel/pages/predictions.py"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import LineEdit, PushButton

from ..components.cards import SectionHeader
from ..components.dialogs import ConfirmDialog
from ..components.progress import ProgressView
from ..components.tables import DataTable
from ..services import log_service, prediction_service
from ..services.period_forecast_display import (
    format_monthly_summary,
    format_weekly_summary,
)
from ..workers.signals import CallbackBridge


class PredictionsPage(QWidget):
    def __init__(self, parent, theme, app):
        super().__init__(parent)

        self.theme = theme
        self.app = app
        self._running = False

        # CallbackBridge is (re)created per run in _run_normal/_run_force
        # and held here so it isn't garbage-collected while a run is
        # still delivering its callback from the background thread.
        self._on_done: CallbackBridge | None = None

        self._build()

        # Live theme updates.
        self.theme.themeChanged.connect(
            self._on_theme_changed
        )

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
                "Predictions",
                "3-day segment forecast (production model) plus stored "
                "weekly and monthly total-consumption forecasts.",
            )
        )

        # --------------------------------------------------------
        # Form
        # --------------------------------------------------------

        form = QGridLayout()

        form.setHorizontalSpacing(
            20
        )

        form.setVerticalSpacing(
            4
        )

        # --------------------------------------------------------
        # Device ID
        # --------------------------------------------------------

        self.device_label = QLabel(
            "Device ID",
            self,
        )

        form.addWidget(
            self.device_label,
            0,
            0,
        )

        self.device_edit = LineEdit(
            self
        )

        self.device_edit.setFixedWidth(
            140
        )

        form.addWidget(
            self.device_edit,
            1,
            0,
        )

        # --------------------------------------------------------
        # Forecast Days (3-day production predictor)
        # --------------------------------------------------------

        self.forecast_label = QLabel(
            "3-Day Forecast",
            self,
        )

        form.addWidget(
            self.forecast_label,
            0,
            1,
        )

        self.forecast_value = QLabel(
            "stored nightly 3-day forecast",
            self,
        )

        form.addWidget(
            self.forecast_value,
            1,
            1,
        )

        # --------------------------------------------------------
        # Run button
        # --------------------------------------------------------

        self.run_btn = PushButton(
            "SHOW PREDICTIONS",
            self,
        )

        self.run_btn.clicked.connect(
            self._on_load_all_clicked
        )

        form.addWidget(
            self.run_btn,
            1,
            2,
        )


        form_row = QHBoxLayout()

        form_row.addLayout(
            form
        )

        form_row.addStretch(
            1
        )

        outer.addLayout(
            form_row
        )

        # --------------------------------------------------------
        # Progress
        # --------------------------------------------------------

        self.progress = ProgressView(
            self,
            self.theme,
        )

        self.progress.setVisible(
            False
        )

        outer.addWidget(
            self.progress
        )

        # --------------------------------------------------------
        # Status
        # --------------------------------------------------------

        self.status_label = QLabel(
            "",
            self,
        )

        self.status_label.setWordWrap(
            True
        )

        outer.addWidget(
            self.status_label
        )

        # --------------------------------------------------------
        # 3-Day Forecast results table
        # --------------------------------------------------------

        outer.addWidget(
            SectionHeader(
                self,
                self.theme,
                "3-Day Forecast",
                "Stored segment-level forecast from the last nightly job.",
            )
        )

        columns = [
            ("date", "Date", 110),
            ("segment", "Segment", 70),
            ("start_hour", "Start Time", 90),
            ("end_hour", "End Time", 90),
            ("prediction", "Prediction (kW)", 140),
            ("peak", "Peak Segment", 100),
        ]

        self.table = DataTable(
            self,
            self.theme,
            columns,
        )

        outer.addWidget(
            self.table,
            1,
        )

        # --------------------------------------------------------
        # Weekly Forecast panel
        # --------------------------------------------------------

        outer.addWidget(
            SectionHeader(
                self,
                self.theme,
                "Weekly Forecast",
                "Total predicted consumption (kWh) for the next complete "
                "Shamsi week (Saturday → Friday, from scheduled job).",
            )
        )

        self.weekly_summary = QLabel(
            "No weekly prediction loaded.",
            self,
        )
        self.weekly_summary.setWordWrap(True)
        outer.addWidget(self.weekly_summary)

        # --------------------------------------------------------
        # Monthly Forecast panel
        # --------------------------------------------------------

        outer.addWidget(
            SectionHeader(
                self,
                self.theme,
                "Monthly Forecast",
                "Total predicted consumption (kWh) for the next complete "
                "Jalali (Shamsi) month (from scheduled job).",
            )
        )

        self.monthly_summary = QLabel(
            "No monthly prediction loaded.",
            self,
        )
        self.monthly_summary.setWordWrap(True)
        outer.addWidget(self.monthly_summary)

        # Initial theme.
        self.refresh_theme()

    # ============================================================
    # Navigation
    # ============================================================

    def on_navigate(
        self,
        context: dict | None,
    ) -> None:
        if not context:
            return

        device_id = context.get(
            "device_id"
        )

        if device_id is not None:
            self.device_edit.setText(
                str(device_id)
            )

        if device_id is not None:
            # Always show stored forecasts (3-day + weekly + monthly)
            self._load_stored_predictions(int(device_id))

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
                "Loading stored predictions..."
            )

        else:
            self.progress.stop()

            self.progress.setVisible(
                False
            )

    # ============================================================
    # Run prediction
    # ============================================================


    def _on_load_all_clicked(
        self,
    ) -> None:
        """Load stored 3-day + weekly + monthly forecasts from MySQL."""
        if self._running:
            return

        raw = self.device_edit.text().strip()
        if not raw.isdigit():
            self.app.show_error(
                "Invalid input",
                "Please enter a numeric Device ID.",
            )
            return

        device_id = int(raw)
        self._load_stored_predictions(device_id)

    def _load_stored_predictions(self, device_id: int) -> None:
        """
        Display existing forecasts only — does not run ElectricityPredictor
        or weekly/monthly jobs.
        """
        self._set_running(True)
        try:
            stored = prediction_service.get_stored_3day_prediction(device_id)

            if not stored.get("found"):
                self.table.set_rows([])
                err = stored.get("error")
                if err:
                    self.status_label.setText(
                        f"Device {device_id}: 3-day forecast unavailable ({err})."
                    )
                else:
                    self.status_label.setText(
                        f"Device {device_id}: no stored 3-day forecast yet.\n"
                        "3-day forecasts are written by the nightly scheduler job."
                    )
            else:
                payload = {
                    "ok": True,
                    "result": {
                        "forecast_days": stored.get("forecast_days") or [],
                        "forced": False,
                        "stored": True,
                        "model_version": stored.get("model_version"),
                        "generated_at": stored.get("generated_at"),
                    },
                }
                self._handle_result(device_id, payload)
                gen = stored.get("generated_at") or ""
                ver = stored.get("model_version") or ""
                extra = ""
                if ver:
                    extra += f" · model {ver}"
                if gen:
                    extra += f" · generated {gen}"
                self.status_label.setText(
                    f"Stored 3-day forecast for device {device_id}{extra}."
                )

            self._refresh_period_forecasts(device_id)
        finally:
            self._set_running(False)


    def _run_normal(
        self,
        device_id: int,
    ) -> None:
        self._set_running(
            True
        )

        self.status_label.setText(
            f"Running normal prediction for device {device_id}..."
        )

        self._on_done = CallbackBridge(
            self
        )

        self._on_done.fired.connect(
            lambda args:
                self._handle_result(
                    device_id,
                    args[0],
                )
        )

        prediction_service.predict_async(
            device_id,
            self._on_done,
        )

    # ============================================================
    # Force prediction
    # ============================================================

    def _run_force(
        self,
        device_id: int,
    ) -> None:
        self._set_running(
            True
        )

        self.status_label.setText(
            f"Running FORCED prediction for device {device_id}..."
        )

        self._on_done = CallbackBridge(
            self
        )

        self._on_done.fired.connect(
            lambda args:
                self._handle_result(
                    device_id,
                    args[0],
                )
        )

        prediction_service.force_predict_async(
            device_id,
            self._on_done,
        )

    # ============================================================
    # Result
    # ============================================================

    def _handle_result(
        self,
        device_id: int,
        payload: dict,
    ) -> None:
        self._set_running(
            False
        )

        if not payload.get("ok"):
            error = payload.get(
                "error"
            )

            self.status_label.setText(
                f"Prediction failed: {error}"
            )

            self.app.show_error(
                "Prediction failed",
                str(error),
            )

            return

        result = payload["result"]

        forced = result.get(
            "forced",
            False,
        )

        rows = []

        # Same None-vs-missing-key issue as "peak"/"segments" below --
        # guard with `or []`, not the .get() default.
        for day in result.get("forecast_days") or []:
            # Use `or` (not the .get default) because "peak"/"segments"
            # can be explicitly present with a value of None in the
            # payload -- .get(key, default) only falls back when the key
            # is *missing*, so `day.get("segments", [])` still returns
            # None in that case and crashes `for seg in None`.
            peak = day.get("peak") or {}

            for seg in day.get("segments") or []:
                is_peak = (
                    seg.get("segment")
                    == peak.get("segment")
                )

                rows.append(
                    {
                        "date": day["date"],
                        "segment": seg["segment"],
                        "start_hour": seg["start_hour"],
                        "end_hour": seg["end_hour"],
                        "prediction": (
                            f"{seg['predicted_consumption_kwh']:.3f}"
                        ),
                        "peak": (
                            "★"
                            if is_peak
                            else ""
                        ),
                    }
                )

        self.table.set_rows(
            rows
        )

        # Also refresh stored weekly / monthly forecasts for this device.
        self._refresh_period_forecasts(device_id)

        if forced:
            padded = result.get(
                "padded_days",
                0,
            )

            self.status_label.setText(
                f"⚠ FORCED 3-day prediction for device {device_id} "
                f"-- history {result.get('history_days')} days "
                f"(padded {padded} synthetic days to meet "
                "the pipeline's requirements). "
                "Treat this result as approximate."
            )

        else:
            self.status_label.setText(
                f"Stored 3-day forecast loaded for device {device_id}."
            )

        if not forced:
            log_service.log_event(
                "DEVICE_PREDICTION",
                component="predictions_page",
                device_id=device_id,
                message="3-day prediction displayed in Control Panel.",
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
        """Refresh all page-specific text colors after theme changes."""

        # Main labels
        self._apply_label_theme(
            self.device_label
        )

        self._apply_label_theme(
            self.forecast_label
        )

        # Forecast value uses muted text.
        self._apply_label_theme(
            self.forecast_value,
            muted=True,
        )

        # Status uses muted text.
        self._apply_label_theme(
            self.status_label,
            muted=True,
        )

        self._apply_label_theme(
            self.weekly_summary,
            muted=True,
        )

        self._apply_label_theme(
            self.monthly_summary,
            muted=True,
        )

        # Refresh progress if it supports theme updates.
        if hasattr(
            self.progress,
            "refresh_theme",
        ):
            self.progress.refresh_theme()

        # Refresh table if it supports theme updates.
        if hasattr(
            self.table,
            "refresh_theme",
        ):
            self.table.refresh_theme()

    # ============================================================
    # Weekly / Monthly stored forecasts
    # ============================================================


    def _refresh_period_forecasts(self, device_id: int) -> None:
        """
        Update the Weekly Forecast and Monthly Forecast panels from
        the service layer (MySQL weekly_predictions / monthly_predictions).
        Never raises — unavailable data is shown as a clear message.
        """
        weekly = prediction_service.get_latest_weekly_prediction(device_id)
        monthly = prediction_service.get_latest_monthly_prediction(device_id)

        self.weekly_summary.setText(
            format_weekly_summary(device_id, weekly)
        )
        self.monthly_summary.setText(
            format_monthly_summary(device_id, monthly)
        )