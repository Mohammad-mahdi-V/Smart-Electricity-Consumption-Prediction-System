"""
model_service.py

All Model Monitor / Model Builder data flows through here. Nothing here
re-implements training or promotion: it shells out to the project's own
monthly_retrainer.py (via a tiny subprocess worker script) so the actual
ElectricityConsumptionModel / MonthlyRetrainer code is what runs.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import paths

WORKER_SCRIPT = Path(__file__).resolve().parent / "_build_model_worker.py"

ALGORITHMS = ["ridge", "linear", "random_forest"]

ALGORITHM_PARAM_SPECS: dict[str, list[dict[str, Any]]] = {
    "ridge": [
        {"name": "alpha", "type": "float", "default": 1.0},
        {"name": "solver", "type": "choice", "default": "auto",
         "choices": ["auto", "svd", "cholesky", "lsqr", "sparse_cg", "sag", "saga"]},
    ],
    "linear": [
        {"name": "fit_intercept", "type": "bool", "default": True},
    ],
    "random_forest": [
        {"name": "n_estimators", "type": "int", "default": 100},
        {"name": "max_depth", "type": "int_or_none", "default": 12},
        {"name": "min_samples_split", "type": "int", "default": 2},
        {"name": "min_samples_leaf", "type": "int", "default": 1},
        {"name": "max_features", "type": "choice", "default": "sqrt",
         "choices": ["sqrt", "log2", "1.0"]},
    ],
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def get_production_info() -> dict[str, Any]:
    """Reads production.json + electricity_model_<type>.json. No mock data:
    if the files are missing, that's surfaced as an error, not guessed."""
    pointer = _read_json(paths.PRODUCTION_JSON)
    if pointer is None:
        return {"available": False, "error": f"production.json not found at {paths.PRODUCTION_JSON}"}

    version = pointer.get("production_version", "unknown")
    model_path_raw = pointer.get("model_path", "")

    # metadata json sits next to the joblib file, same stem
    model_path = Path(model_path_raw) if model_path_raw else None
    metadata_path = model_path.with_suffix(".json") if model_path else None
    metadata = _read_json(metadata_path) if metadata_path else None

    healthy = model_path is not None and model_path.exists()

    info: dict[str, Any] = {
        "available": True,
        "version": version,
        "model_path": model_path_raw,
        "promoted_at": pointer.get("promoted_at"),
        "healthy": healthy,
    }
    if metadata:
        info.update({
            "algorithm": metadata.get("model_type"),
            "n_features": metadata.get("n_features"),
            "n_targets": metadata.get("n_targets"),
            "total_rows": metadata.get("total_rows"),
            "total_users": metadata.get("total_users"),
            "target_columns": metadata.get("target_columns"),
        })
    report = _read_json(paths.MONTHLY_RETRAINING_REPORT)
    if report:
        info["last_training_run_at"] = report.get("run_at")
        info["metrics"] = report.get("production_metrics") or report.get("candidate_metrics")
    return info


def get_candidate_versions() -> list[dict[str, Any]]:
    """Every processed/models/<version>/ folder is a promoted (now historical
    or current) candidate. There is no separate 'pending candidate' artifact
    in the existing pipeline -- a candidate only becomes a persisted model
    once it passes gates and is promoted (see monthly_retrainer.promote)."""
    if not paths.MODELS_DIR.exists():
        return []

    versions = []
    current = None
    pointer = _read_json(paths.PRODUCTION_JSON)
    if pointer:
        current = pointer.get("production_version")

    for entry in sorted(paths.MODELS_DIR.iterdir()):
        if not entry.is_dir():
            continue
        json_files = list(entry.glob("*.json"))
        meta = _read_json(json_files[0]) if json_files else None
        versions.append({
            "version": entry.name,
            "is_current": entry.name == current,
            "algorithm": meta.get("model_type") if meta else None,
            "promoted_at": meta.get("promoted_at") if meta else None,
            "metrics": None,
        })
    versions.sort(key=lambda v: v["version"], reverse=True)
    return versions


def get_last_retraining_report() -> dict[str, Any] | None:
    return _read_json(paths.MONTHLY_RETRAINING_REPORT)


def get_last_validation_report() -> dict[str, Any] | None:
    return _read_json(paths.PRODUCTION_VALIDATION_REPORT)


@dataclass
class BuildRequest:
    algorithm: str
    params: dict[str, Any] = field(default_factory=dict)
    promote: bool = False


@dataclass
class BuildHandle:
    """Returned immediately; caller polls/consumes via callbacks on the
    main thread (see components/progress.py usage in pages/model_builder.py)."""
    process: subprocess.Popen
    thread: threading.Thread


def run_build(
    request: BuildRequest,
    on_line: Callable[[str], None],
    on_done: Callable[[dict[str, Any] | None, int], None],
) -> BuildHandle:
    """
    Runs the build (and optional promotion) in a separate OS process so a
    crash or a long Random Forest fit can never freeze or take down the
    Control Panel GUI. on_line is called (from a background thread) for
    every line of stdout; on_done is called once with (result_dict_or_None,
    exit_code). Callers must marshal these back to the Tk main thread
    (e.g. via widget.after(0, ...)) before touching widgets.
    """
    args = [
        sys.executable,
        str(WORKER_SCRIPT),
        "--algorithm", request.algorithm,
        "--params-json", json.dumps(request.params),
    ]
    if request.promote:
        args.append("--promote")

    process = subprocess.Popen(
        args,
        cwd=str(paths.SRC_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=paths.subprocess_env(),
        bufsize=1,
    )

    def _pump() -> None:
        result: dict[str, Any] | None = None
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip("\n")
            if line.startswith("__RESULT_JSON__:"):
                try:
                    result = json.loads(line[len("__RESULT_JSON__:"):])
                except json.JSONDecodeError:
                    result = None
                continue
            on_line(line)
        process.wait()
        on_done(result, process.returncode)

    thread = threading.Thread(target=_pump, daemon=True)
    thread.start()
    return BuildHandle(process=process, thread=thread)



# ---------------------------------------------------------------------------
# Multi-horizon Global Learning Cycle extensions
# ---------------------------------------------------------------------------

from horizon_model_store import HorizonModelStore, HORIZONS  # noqa: E402


def get_horizon_production_info(horizon: str) -> dict[str, Any]:
    store = HorizonModelStore(horizon, models_root=paths.MODELS_DIR, project_root=paths.PROJECT_ROOT)
    info = store.get_production_metadata()
    if not info:
        return {"available": False, "horizon": horizon, "error": "no production pointer"}
    info["horizon"] = horizon
    return info


def get_all_horizons_info() -> dict[str, Any]:
    return {h: get_horizon_production_info(h) for h in HORIZONS}


def get_horizon_candidates(horizon: str) -> list[dict[str, Any]]:
    store = HorizonModelStore(horizon, models_root=paths.MODELS_DIR, project_root=paths.PROJECT_ROOT)
    return store.list_candidates()


def get_last_global_cycle_report() -> dict[str, Any] | None:
    report = paths.DIAGNOSTICS_DIR / "global_learning_cycle" / "latest_cycle.json"
    return _read_json(report)


@dataclass
class GlobalCycleRequest:
    """Per-horizon algorithm + params for a Global Learning Cycle run."""
    horizon_configs: dict[str, dict[str, Any]] = field(default_factory=dict)
    promote: bool = False
    # Default True: refresh feature_dataset from DB before training.
    # Set False (Control Panel "Skip dataset rebuild") for offline/dev.
    rebuild_datasets: bool = True

    def normalized(self) -> dict[str, dict[str, Any]]:
        out = {}
        for h in HORIZONS:
            cfg = self.horizon_configs.get(h) or {}
            out[h] = {
                "algorithm": str(cfg.get("algorithm", "ridge")).lower(),
                "params": dict(cfg.get("params") or cfg.get("model_params") or {}),
            }
        return out


def run_global_cycle(
    request: GlobalCycleRequest,
    on_line: Callable[[str], None],
    on_done: Callable[[dict[str, Any] | None, int], None],
) -> BuildHandle:
    """Launch Global Learning Cycle in a subprocess (same isolation as run_build)."""
    args = [
        sys.executable,
        str(WORKER_SCRIPT),
        "--algorithm", "ridge",
        "--params-json", "{}",
        "--horizon-configs-json", json.dumps(request.normalized()),
    ]
    if request.promote:
        args.append("--promote")
    if not request.rebuild_datasets:
        args.append("--skip-rebuild")

    process = subprocess.Popen(
        args,
        cwd=str(paths.SRC_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=paths.subprocess_env(),
        bufsize=1,
    )

    def _pump() -> None:
        result: dict[str, Any] | None = None
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip("\n")
            if line.startswith("__RESULT_JSON__:"):
                try:
                    result = json.loads(line[len("__RESULT_JSON__:"):])
                except json.JSONDecodeError:
                    result = None
                continue
            on_line(line)
        process.wait()
        on_done(result, process.returncode)

    thread = threading.Thread(target=_pump, daemon=True)
    thread.start()
    return BuildHandle(process=process, thread=thread)
