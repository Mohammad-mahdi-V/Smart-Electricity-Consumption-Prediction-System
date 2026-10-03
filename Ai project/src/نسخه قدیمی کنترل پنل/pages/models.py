"""control_panel/pages/models.py

Models page for 3-Day / Weekly / Monthly.

Select in Version History loads that version into the upper horizon panel
and enables Promote for it (unless it is already the current production).
Manual Promote does not re-check comparison gates.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from qfluentwidgets import PushButton

from ..components.auto_refresh import AutoRefreshControl
from ..components.cards import SectionHeader, force_transparent, style_scroll_area_transparent
from ..components.dialogs import ConfirmDialog
from ..components.tables import DataTable
from ..components.terminal import TerminalOutput
from ..services import log_service, model_service, script_service
from ..workers.signals import CallbackBridge

HORIZONS = ("3day", "weekly", "monthly")
HORIZON_LABELS = {"3day": "3-Day", "weekly": "Weekly", "monthly": "Monthly"}
HORIZON_FROM_LABEL = {v: k for k, v in HORIZON_LABELS.items()}


class ModelsPage(QWidget):
    def __init__(self, parent, theme, app):
        super().__init__(parent)
        self.theme = theme
        self.app = app
        self._running = False
        self._terminal_window: QWidget | None = None
        self._terminal_widget: TerminalOutput | None = None
        self._on_line: CallbackBridge | None = None
        self._on_done: CallbackBridge | None = None
        self._horizon_cards: dict[str, QWidget] = {}
        self._title_labels: dict[str, QLabel] = {}
        self._promote_btns: dict[str, PushButton] = {}
        self._status_labels: dict[str, QLabel] = {}
        self._detail_labels: dict[str, QLabel] = {}
        # Selected version per horizon (from history table Select)
        self._selected: dict[str, dict] = {}

        self._build()
        self.theme.themeChanged.connect(self._on_theme_changed)
        self.refresh()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(12)

        top = QHBoxLayout()
        top.addWidget(
            SectionHeader(
                self,
                self.theme,
                "Models",
                "Independent production / candidate status for 3-Day, Weekly, and Monthly.",
            )
        )
        top.addStretch(1)
        self.auto_refresh = AutoRefreshControl(self, self.theme, self.refresh)
        top.addWidget(self.auto_refresh)
        self.refresh_btn = PushButton("Refresh", self)
        self.refresh_btn.clicked.connect(self.refresh)
        top.addWidget(self.refresh_btn)
        self.promote_best_btn = PushButton("Promote Best (All)", self)
        self.promote_best_btn.clicked.connect(self._on_promote_best_all)
        top.addWidget(self.promote_best_btn)
        outer.addLayout(top)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self.body_layout = QVBoxLayout(body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(14)

        for h in HORIZONS:
            self.body_layout.addWidget(self._make_horizon_section(h))

        self.body_layout.addWidget(
            SectionHeader(self, self.theme, "Version History")
        )
        self.history_table = DataTable(
            self,
            self.theme,
            columns=[
                ("horizon", "Horizon", 90),
                ("version", "Version", 90),
                ("algorithm", "Algorithm", 110),
                ("status", "Status", 100),
                ("promoted_at", "Promoted / Created", 200),
                ("mae", "MAE", 90),
                ("r2", "R²", 90),
                ("actions", "Actions", 180),
            ],
        )
        self.body_layout.addWidget(self.history_table)
        self.body_layout.addStretch(1)
        scroll.setWidget(body)
        style_scroll_area_transparent(scroll)
        outer.addWidget(scroll, 1)

    def _make_horizon_section(self, horizon: str) -> QWidget:
        frame = QFrame(self)
        frame.setObjectName(f"horizonSection_{horizon}")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)

        header = QHBoxLayout()
        title = QLabel(f"{HORIZON_LABELS[horizon]} Model", frame)
        title.setStyleSheet(
            f"color: {self.theme.colors['text']}; font-weight: 600; font-size: 14px;"
        )
        header.addWidget(title)
        header.addStretch(1)
        self._title_labels[horizon] = title

        promote_btn = PushButton(f"Promote {HORIZON_LABELS[horizon]}", frame)
        promote_btn.setEnabled(False)
        promote_btn.clicked.connect(lambda *_ , h=horizon: self._on_promote(h))
        header.addWidget(promote_btn)
        self._promote_btns[horizon] = promote_btn
        layout.addLayout(header)

        detail = QLabel("Loading...", frame)
        detail.setWordWrap(True)
        detail.setStyleSheet(f"color: {self.theme.colors['text']};")
        layout.addWidget(detail)
        self._detail_labels[horizon] = detail

        status = QLabel("", frame)
        status.setStyleSheet(f"color: {self.theme.colors['text']};")
        layout.addWidget(status)
        self._status_labels[horizon] = status

        self._horizon_cards[horizon] = frame
        self._style_horizon_frame(horizon)
        return frame

    def _style_horizon_frame(self, horizon: str) -> None:
        frame = self._horizon_cards[horizon]
        # Re-applied on every theme refresh too, in case anything reset it.
        force_transparent(frame)
        border = self.theme.colors.get("border", "#444")
        # Transparent fill (like the app's cards/buttons use at rest) --
        # only the border marks the card's edge, kept in sync on theme
        # toggle via _on_theme_changed below.
        frame.setStyleSheet(
            f"QFrame#horizonSection_{horizon} {{"
            f" border: 1px solid {border}; border-radius: 8px;"
            f" background-color: transparent !important; }}"
        )

    def refresh(self) -> None:
        last_cycle = None
        try:
            last_cycle = model_service.get_last_global_cycle_report()
        except Exception:
            last_cycle = None
        cycle_models = (last_cycle or {}).get("models") or {}

        history_rows: list[dict] = []
        for h in HORIZONS:
            prod = {}
            try:
                prod = model_service.get_horizon_production_info(h)
            except Exception as exc:
                prod = {"available": False, "error": str(exc)}

            cand_list = []
            try:
                cand_list = model_service.get_horizon_candidates(h)
            except Exception:
                cand_list = []

            cycle_entry = cycle_models.get(h) or {}
            cand_version = cycle_entry.get("candidate_version")
            if not cand_version and cand_list:
                cand_version = cand_list[0].get("version")

            metrics = cycle_entry.get("metrics") or (cand_list[0].get("metrics") if cand_list else {}) or {}
            prod_meta = (prod or {}).get("metadata") or {}
            prod_metrics = prod_meta.get("metrics") or cycle_entry.get("production_metrics") or {}

            prod_ver = (prod or {}).get("production_version") or "—"
            algo = (prod or {}).get("algorithm") or cycle_entry.get("algorithm") or "—"
            cand_meta = cycle_entry.get("metadata") or (cand_list[0] if cand_list else {}) or {}
            n_features = cand_meta.get("n_features") or prod_meta.get("n_features") or "—"
            train_rows = cand_meta.get("training_rows") or "—"
            val_rows = cand_meta.get("validation_rows") or "—"
            created = cand_meta.get("created_at") or prod.get("promoted_at") or "—"

            comparison = cycle_entry.get("comparison")
            promotion = cycle_entry.get("promotion")
            reasons = (cycle_entry.get("comparison_detail") or {}).get("reasons") or []

            # Default panel content (production + cycle candidate)
            default_lines = [
                f"Production Version: {prod_ver}",
                f"Candidate Version:  {cand_version or '—'}",
                f"Algorithm:          {algo}",
                f"Status:             {cycle_entry.get('status') or ('available' if prod.get('available') else 'no production')}",
                f"MAE:    {self._fmt(metrics.get('mae'))}   (prod {self._fmt(prod_metrics.get('mae'))})",
                f"RMSE:   {self._fmt(metrics.get('rmse'))}   (prod {self._fmt(prod_metrics.get('rmse'))})",
                f"MAPE:   {self._fmt(metrics.get('mape'))}   (prod {self._fmt(prod_metrics.get('mape'))})",
                f"MAAPE:  {self._fmt(metrics.get('maape'))}  (prod {self._fmt(prod_metrics.get('maape'))})",
                f"R²:     {self._fmt(metrics.get('r2'))}    (prod {self._fmt(prod_metrics.get('r2'))})",
                f"Training Rows: {train_rows}   Validation Rows: {val_rows}   Features: {n_features}",
                f"Created At: {created}",
            ]

            # Default after Refresh / Promote / Promote Best: selected == production
            # so per-horizon Promote stays disabled until user Select another version.
            if prod_ver and prod_ver != "—":
                self._selected[h] = {
                    "horizon_key": h,
                    "version": prod_ver,
                    "algorithm": algo,
                    "is_candidate": False,
                    "is_current": True,
                    "promoted_at": prod.get("promoted_at"),
                    "metrics": prod_metrics,
                    "raw": prod_meta or prod,
                }
                self._apply_selection_to_panel(
                    h, self._selected[h], prod_ver, prod_metrics
                )
            else:
                self._selected.pop(h, None)
                self._detail_labels[h].setText("\n".join(default_lines))
                self._detail_labels[h].setStyleSheet(
                    f"color: {self.theme.colors['text']};"
                )
                self._status_labels[h].setText(
                    "No production model. Select a version from history to promote."
                )
                self._status_labels[h].setStyleSheet(
                    f"color: {self.theme.colors['text']};"
                )
                self._promote_btns[h].setEnabled(False)

            # History: everything under candidates/ (one row per version)
            try:
                from horizon_model_store import HorizonModelStore
                from ..services import paths

                store = HorizonModelStore(
                    h,
                    models_root=paths.MODELS_DIR,
                    project_root=paths.PROJECT_ROOT,
                )
                for pmeta in store.list_promoted_versions():
                    pm = pmeta.get("metrics") or {}
                    is_current = bool(pmeta.get("is_current"))
                    is_candidate = bool(pmeta.get("is_candidate"))
                    if is_current:
                        status = "production"
                    elif is_candidate:
                        status = "candidate"
                    else:
                        status = "history"
                    history_rows.append({
                        "horizon": HORIZON_LABELS[h],
                        "horizon_key": h,
                        "version": pmeta.get("version", "—"),
                        "algorithm": pmeta.get("algorithm") or pmeta.get("model_type") or "—",
                        "status": status,
                        "is_current": is_current,
                        "is_candidate": is_candidate and not is_current,
                        "promoted_at": pmeta.get("promoted_at") or pmeta.get("created_at") or "—",
                        "mae": self._fmt(pm.get("mae")),
                        "r2": self._fmt(pm.get("r2")),
                        "metrics": pm,
                        "raw": pmeta,
                    })
            except Exception:
                if prod.get("available") and prod_ver and prod_ver != "—":
                    history_rows.append({
                        "horizon": HORIZON_LABELS[h],
                        "horizon_key": h,
                        "version": prod_ver,
                        "algorithm": algo,
                        "status": "production",
                        "is_current": True,
                        "is_candidate": False,
                        "promoted_at": prod.get("promoted_at") or "—",
                        "mae": self._fmt(prod_metrics.get("mae")),
                        "r2": self._fmt(prod_metrics.get("r2")),
                        "metrics": prod_metrics,
                        "raw": prod,
                    })

        # Deduplicate: same horizon+version can exist both as promoted folder
        # and as leftover candidate → show only one row (prefer production > history > candidate).
        history_rows = self._dedupe_history_rows(history_rows)
        self._populate_history(history_rows)

    @staticmethod
    def _dedupe_history_rows(rows: list[dict]) -> list[dict]:
        rank = {"production": 0, "history": 1, "candidate": 2}
        best: dict[tuple[str, str], dict] = {}
        order: list[tuple[str, str]] = []
        for row in rows:
            key = (str(row.get("horizon_key") or row.get("horizon") or ""), str(row.get("version") or ""))
            if not key[0] or not key[1] or key[1] == "—":
                continue
            status = str(row.get("status") or "history")
            if key not in best:
                best[key] = row
                order.append(key)
                continue
            prev = best[key]
            prev_status = str(prev.get("status") or "history")
            if rank.get(status, 9) < rank.get(prev_status, 9):
                best[key] = row
            elif rank.get(status, 9) == rank.get(prev_status, 9):
                # Prefer is_current
                if row.get("is_current") and not prev.get("is_current"):
                    best[key] = row
        return [best[k] for k in order]

    def _apply_selection_to_panel(
        self,
        horizon: str,
        selected: dict,
        prod_ver: str,
        prod_metrics: dict,
    ) -> None:
        """Show selected version details in the upper horizon card."""
        ver = selected.get("version", "—")
        algo = selected.get("algorithm") or "—"
        metrics = selected.get("metrics") or {}
        raw = selected.get("raw") or {}
        is_candidate = bool(selected.get("is_candidate"))
        is_current = bool(selected.get("is_current")) or (
            not is_candidate and str(ver) == str(prod_ver)
        )
        selected["is_current"] = is_current

        kind = "candidate" if is_candidate else ("production (current)" if is_current else "history")
        lines = [
            f"Selected Version:   {ver}  [{kind}]",
            f"Production Version: {prod_ver}",
            f"Algorithm:          {algo}",
            f"MAE:    {self._fmt(metrics.get('mae'))}   (prod {self._fmt(prod_metrics.get('mae'))})",
            f"RMSE:   {self._fmt(metrics.get('rmse'))}   (prod {self._fmt(prod_metrics.get('rmse'))})",
            f"MAPE:   {self._fmt(metrics.get('mape'))}   (prod {self._fmt(prod_metrics.get('mape'))})",
            f"MAAPE:  {self._fmt(metrics.get('maape'))}  (prod {self._fmt(prod_metrics.get('maape'))})",
            f"R²:     {self._fmt(metrics.get('r2'))}    (prod {self._fmt(prod_metrics.get('r2'))})",
            f"Training Rows: {raw.get('training_rows', '—')}   "
            f"Validation Rows: {raw.get('validation_rows', '—')}   "
            f"Features: {raw.get('n_features', '—')}",
            f"Created / Promoted: {raw.get('promoted_at') or raw.get('created_at') or selected.get('promoted_at') or '—'}",
        ]
        self._detail_labels[horizon].setText("\n".join(lines))
        self._detail_labels[horizon].setStyleSheet(f"color: {self.theme.colors['text']};")

        if is_current:
            status = (
                f"Selected v{ver} is the current production model. "
                "Promote is disabled."
            )
            can_promote = False
        else:
            status = (
                f"Selected v{ver} ({kind}). "
                "Press Promote to make this version production "
                "(no gate re-check)."
            )
            can_promote = True

        self._status_labels[horizon].setText(status)
        self._status_labels[horizon].setStyleSheet(f"color: {self.theme.colors['text']};")
        self._promote_btns[horizon].setEnabled(can_promote and not self._running)

    def _populate_history(self, rows: list[dict]) -> None:
        table = self.history_table.table
        table.setSortingEnabled(False)
        table.setRowCount(len(rows))
        keys = self.history_table._keys

        for r, row in enumerate(rows):
            for c, key in enumerate(keys):
                if key == "actions":
                    continue
                value = row.get(key)
                display = "" if value is None else str(value)
                item = QTableWidgetItem()
                item.setData(Qt.ItemDataRole.DisplayRole, display)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    item.setData(Qt.ItemDataRole.EditRole, value)
                item.setData(Qt.ItemDataRole.UserRole, row)
                table.setItem(r, c, item)

            actions_col = keys.index("actions")
            cell = QWidget()
            lay = QHBoxLayout(cell)
            lay.setContentsMargins(4, 2, 4, 2)
            lay.setSpacing(6)

            select_btn = PushButton("Select", cell)
            select_btn.setFixedHeight(28)
            select_btn.clicked.connect(
                lambda *_args, data=row: self._on_select_version(data)
            )
            lay.addWidget(select_btn)

            is_current = bool(row.get("is_current"))
            if not is_current:
                delete_btn = PushButton("Delete", cell)
                delete_btn.setFixedHeight(28)
                delete_btn.clicked.connect(
                    lambda *_args, data=row: self._on_delete_version(data)
                )
                lay.addWidget(delete_btn)
            else:
                badge = QLabel("current", cell)
                badge.setStyleSheet(
                    f"color: {self.theme.colors.get('accent', '#4af')}; font-size: 11px;"
                )
                lay.addWidget(badge)

            lay.addStretch(1)
            table.setCellWidget(r, actions_col, cell)
            dummy = QTableWidgetItem("")
            dummy.setData(Qt.ItemDataRole.UserRole, row)
            table.setItem(r, actions_col, dummy)

        table.setSortingEnabled(True)

    @staticmethod
    def _fmt(v) -> str:
        if v is None:
            return "—"
        try:
            return f"{float(v):.4f}"
        except (TypeError, ValueError):
            return str(v)

    def _on_select_version(self, row: dict) -> None:
        """Load version into the upper horizon panel (no dialog)."""
        horizon = row.get("horizon_key") or HORIZON_FROM_LABEL.get(row.get("horizon", ""), "")
        version = row.get("version")
        if not horizon or not version or version == "—":
            self.app.show_error("Select", "Invalid version row")
            return

        # Enrich metrics from disk if needed
        metrics = dict(row.get("metrics") or {})
        raw = dict(row.get("raw") or {})
        try:
            from horizon_model_store import HorizonModelStore
            from ..services import paths

            store = HorizonModelStore(
                horizon,
                models_root=paths.MODELS_DIR,
                project_root=paths.PROJECT_ROOT,
            )
            is_candidate = bool(row.get("is_candidate"))
            disk_meta = store.load_version_metadata(version, candidate=is_candidate) or {}
            if disk_meta:
                raw = {**raw, **disk_meta}
                metrics = disk_meta.get("metrics") or metrics
            prod = store.get_production_metadata() or {}
            prod_ver = prod.get("production_version") or "—"
            prod_metrics = (prod.get("metadata") or {}).get("metrics") or {}
        except Exception:
            prod_ver = "—"
            prod_metrics = {}

        selected = {
            "horizon_key": horizon,
            "version": version,
            "algorithm": row.get("algorithm") or raw.get("algorithm") or raw.get("model_type") or "ridge",
            "is_candidate": bool(row.get("is_candidate")),
            "is_current": bool(row.get("is_current")),
            "promoted_at": row.get("promoted_at"),
            "metrics": metrics,
            "raw": raw,
        }
        self._selected[horizon] = selected
        self._apply_selection_to_panel(horizon, selected, prod_ver, prod_metrics)

    def _on_promote(self, horizon: str) -> None:
        if self._running:
            return
        selected = self._selected.get(horizon)
        if not selected:
            self.app.show_error("Promote", f"No version selected for {HORIZON_LABELS[horizon]}")
            return
        if selected.get("is_current"):
            self.app.show_error("Promote", "Selected version is already production.")
            return

        parent = self.app.root if hasattr(self.app, "root") else self
        ver = selected.get("version")
        kind = "candidate" if selected.get("is_candidate") else "version"

        def _do_promote() -> None:
            self._promote_selected(horizon)

        ConfirmDialog(
            parent,
            self.theme,
            f"Promote {HORIZON_LABELS[horizon]}",
            f"Promote {kind} v{ver} to production for {HORIZON_LABELS[horizon]}?\n"
            "Only this horizon is affected. No comparison gate re-check.",
            on_confirm=_do_promote,
            confirm_text=f"Promote {HORIZON_LABELS[horizon]}",
        )

    def _promote_selected(self, horizon: str) -> None:
        selected = self._selected.get(horizon)
        if not selected:
            return
        version = selected.get("version")
        algorithm = selected.get("algorithm") or "ridge"
        is_candidate = bool(selected.get("is_candidate"))
        if not version:
            self.app.show_error("Promote failed", "No version selected")
            return
        try:
            from horizon_model_store import HorizonModelStore
            from ..services import paths

            store = HorizonModelStore(
                horizon,
                models_root=paths.MODELS_DIR,
                project_root=paths.PROJECT_ROOT,
            )
            store.activate_version(
                version,
                str(algorithm),
                from_candidate=is_candidate,
            )
            log_service.log_event(
                "MODEL_PROMOTION",
                component="models_page",
                message=(
                    f"horizon={horizon} version={version} "
                    f"candidate={is_candidate} (manual activate)"
                ),
            )
            # Clear selection so panel shows new production state
            self._selected.pop(horizon, None)
            self.refresh()
        except Exception as exc:
            self.app.show_error(f"Promote {HORIZON_LABELS[horizon]} failed", str(exc))

    def _pick_best_version(self, horizon: str) -> dict | None:
        """Best non-current version vs production using horizon_trainers._compare.

        Same gates as Global Learning Cycle:
          - R² gain >= min_r2_gain (default 0)
          - MAE ratio  <= max_mae_ratio (default 1.05)
          - RMSE ratio <= max_rmse_ratio (default 1.05)

        Among versions that pass, pick highest r2_gain (then lowest mae_ratio).
        If no production metrics, first available version is bootstrap-eligible.
        """
        from horizon_model_store import HorizonModelStore
        from horizon_trainers import _compare
        from ..services import paths

        store = HorizonModelStore(
            horizon,
            models_root=paths.MODELS_DIR,
            project_root=paths.PROJECT_ROOT,
        )
        current = store.production_version()
        prod_meta = store.get_production_metadata() or {}
        prod_metrics = (prod_meta.get("metadata") or {}).get("metrics")

        # One entry per version (already unique from list_promoted_versions + dedupe)
        seen: set[str] = set()
        passed_picks: list[dict] = []
        for meta in store.list_promoted_versions():
            ver = str(meta.get("version") or "")
            if not ver or ver == current or ver in seen:
                continue
            seen.add(ver)
            cand_metrics = meta.get("metrics") or {}
            # Need mae/r2/rmse for full compare; skip incomplete
            if prod_metrics is not None:
                need = ("mae", "r2", "rmse")
                if not all(k in cand_metrics and cand_metrics[k] is not None for k in need):
                    continue
                if not all(k in prod_metrics and prod_metrics[k] is not None for k in need):
                    # treat as bootstrap if prod incomplete
                    comparison = _compare(None, cand_metrics)
                else:
                    comparison = _compare(prod_metrics, cand_metrics)
            else:
                comparison = _compare(None, cand_metrics)

            if not comparison.get("passed"):
                continue
            passed_picks.append({
                "version": ver,
                "algorithm": meta.get("algorithm") or meta.get("model_type") or "ridge",
                "metrics": cand_metrics,
                "comparison": comparison,
                "is_candidate": bool(meta.get("is_candidate", True)),
                "r2_gain": comparison.get("r2_gain") if comparison.get("r2_gain") is not None else 0.0,
                "mae_ratio": comparison.get("mae_ratio") if comparison.get("mae_ratio") is not None else 0.0,
            })

        if not passed_picks:
            return None
        # Best = highest R² gain, then lowest MAE ratio
        passed_picks.sort(key=lambda p: (-float(p["r2_gain"]), float(p["mae_ratio"])))
        return passed_picks[0]

    def _on_promote_best_all(self) -> None:
        if self._running:
            return
        parent = self.app.root if hasattr(self.app, "root") else self

        # Preview what will be promoted
        lines = []
        picks: dict[str, dict] = {}
        for h in HORIZONS:
            try:
                best = self._pick_best_version(h)
            except Exception as exc:
                lines.append(f"{HORIZON_LABELS[h]}: error — {exc}")
                continue
            if not best:
                lines.append(f"{HORIZON_LABELS[h]}: no better version than current")
                continue
            picks[h] = best
            mae = self._fmt((best.get("metrics") or {}).get("mae"))
            r2 = self._fmt((best.get("metrics") or {}).get("r2"))
            label = (best.get("comparison") or {}).get("label") or "better"
            gain = best.get("r2_gain")
            gain_s = f"{float(gain):+.4f}" if gain is not None else "—"
            lines.append(
                f"{HORIZON_LABELS[h]}: promote v{best['version']} "
                f"({best.get('algorithm')}) [{label}]  "
                f"MAE={mae}  R²={r2}  ΔR²={gain_s}"
            )

        if not picks:
            self.app.show_error(
                "Promote Best",
                "No version to promote for any horizon "
                "(none beats current production by training gates, "
                "or missing metrics).",
            )
            return

        def _do() -> None:
            self._promote_best_all(picks)

        ConfirmDialog(
            parent,
            self.theme,
            "Promote Best (All Horizons)",
            "Promote the best version per horizon using the same gates as training "
            "(R² gain, MAE ratio ≤ 1.05, RMSE ratio ≤ 1.05). "
            "Only versions that beat current production are promoted.\n\n"
            + "\n".join(lines),
            on_confirm=_do,
            confirm_text="Promote Best",
        )

    def _promote_best_all(self, picks: dict[str, dict]) -> None:
        from horizon_model_store import HorizonModelStore
        from ..services import paths

        errors = []
        ok = []
        for h, pick in picks.items():
            try:
                store = HorizonModelStore(
                    h,
                    models_root=paths.MODELS_DIR,
                    project_root=paths.PROJECT_ROOT,
                )
                store.activate_version(
                    pick["version"],
                    str(pick.get("algorithm") or "ridge"),
                    from_candidate=True,
                )
                log_service.log_event(
                    "MODEL_PROMOTION_BEST",
                    component="models_page",
                    message=f"horizon={h} version={pick['version']}",
                )
                ok.append(f"{HORIZON_LABELS[h]} v{pick['version']}")
                self._selected.pop(h, None)
            except Exception as exc:
                errors.append(f"{HORIZON_LABELS[h]}: {exc}")
        self.refresh()
        if errors:
            self.app.show_error(
                "Promote Best — partial",
                "OK: " + (", ".join(ok) if ok else "none")
                + "\nErrors:\n" + "\n".join(errors),
            )

    def _on_delete_version(self, row: dict) -> None:
        if row.get("is_current"):
            self.app.show_error(
                "Delete",
                "Cannot delete the currently promoted production model.",
            )
            return

        horizon = row.get("horizon_key") or HORIZON_FROM_LABEL.get(row.get("horizon", ""), "")
        version = row.get("version")
        is_candidate = bool(row.get("is_candidate"))
        if not horizon or not version or version == "—":
            self.app.show_error("Delete", "Invalid version row")
            return

        parent = self.app.root if hasattr(self.app, "root") else self
        kind = "candidate" if is_candidate else "historical"

        def _do_delete() -> None:
            try:
                from horizon_model_store import HorizonModelStore
                from ..services import paths

                store = HorizonModelStore(
                    horizon,
                    models_root=paths.MODELS_DIR,
                    project_root=paths.PROJECT_ROOT,
                )
                store.delete_version(version, candidate=is_candidate)
                log_service.log_event(
                    "MODEL_DELETE",
                    component="models_page",
                    message=f"horizon={horizon} version={version} candidate={is_candidate}",
                )
                # Clear selection if it pointed at deleted version
                sel = self._selected.get(horizon)
                if sel and sel.get("version") == version:
                    self._selected.pop(horizon, None)
                self.refresh()
            except Exception as exc:
                self.app.show_error("Delete failed", str(exc))

        ConfirmDialog(
            parent,
            self.theme,
            f"Delete {kind} v{version}",
            f"Delete {HORIZON_LABELS.get(horizon, horizon)} {kind} version {version}?\n"
            "This permanently removes the version folder from disk.",
            on_confirm=_do_delete,
            confirm_text="Delete",
        )

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.refresh_btn.setEnabled(not running)
        self.promote_best_btn.setEnabled(not running)
        for h, btn in self._promote_btns.items():
            if running:
                btn.setEnabled(False)

    def _get_terminal_window(self, title: str):
        if self._terminal_window is None:
            win = QWidget(None)
            win.setWindowTitle(title)
            win.resize(720, 420)
            lay = QVBoxLayout(win)
            term = TerminalOutput(win, self.theme, height=20)
            lay.addWidget(term)
            self._terminal_window = win
            self._terminal_widget = term

            def _on_close(event) -> None:
                self._terminal_window = None
                self._terminal_widget = None
                event.accept()

            win.closeEvent = _on_close  # type: ignore
        else:
            self._terminal_window.setWindowTitle(title)
        assert self._terminal_widget is not None
        self._terminal_widget.clear()
        self._terminal_window.show()
        self._terminal_window.raise_()
        return self._terminal_window, self._terminal_widget

    def _run_validation(self) -> None:
        self._run_script("production_validator")

    def _run_script(self, name: str) -> None:
        if self._running:
            return
        self._set_running(True)
        _, terminal = self._get_terminal_window(name)
        self._on_line = CallbackBridge(self)
        self._on_done = CallbackBridge(self)
        self._on_line.fired.connect(lambda args: terminal.append_line(args[0] if args else ""))
        self._on_done.fired.connect(
            lambda args: self._handle_script_done(terminal, args[0] if args else 1)
        )
        script_service.run_script(name, {}, on_line=self._on_line, on_done=self._on_done)

    def _handle_script_done(self, terminal: TerminalOutput, code: int) -> None:
        self._set_running(False)
        terminal.append_line(f"\n[exit code {code}]")
        self.refresh()

    def _on_theme_changed(self, mode: str) -> None:
        self.auto_refresh.refresh_theme()
        # These were never restyled on theme toggle before, so they kept
        # whatever color/background they were built with -- out of sync
        # with the rest of the UI after switching light/dark.
        for h in HORIZONS:
            self._title_labels[h].setStyleSheet(
                f"color: {self.theme.colors['text']}; font-weight: 600; font-size: 14px;"
            )
            self._style_horizon_frame(h)
        self.refresh()