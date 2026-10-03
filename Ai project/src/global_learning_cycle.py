
"""global_learning_cycle.py - Unified multi-horizon Global Learning Cycle.

When rebuild_datasets=True (default), refreshes source data via
dataset_rebuild.rebuild_datasets_from_db() which runs, in order:

    export_electricity_csv_from_db.py
    build_full_daily_dataset.py
    build_full_feature_dataset.py

Pass --skip-rebuild / rebuild_datasets=False only for local/dev without DB.
Scheduler must never pass --skip-rebuild.
"""
from __future__ import annotations
import argparse, json, traceback, uuid, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parent
BASE_DIR = SRC_DIR.parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from horizon_model_store import HorizonModelStore, HORIZONS
from horizon_trainers import HorizonTrainConfig, get_trainer
from dataset_rebuild import rebuild_datasets_from_db

def _utc_now():
    return datetime.now(timezone.utc).isoformat()

def _default_paths():
    return {
        "feature_dataset": BASE_DIR / "processed" / "feature_dataset.csv",
        "daily_dataset": BASE_DIR / "processed" / "daily_dataset.csv",
        "models_root": BASE_DIR / "processed" / "models",
        "report_dir": BASE_DIR / "processed" / "diagnostics" / "global_learning_cycle",
        "project_root": BASE_DIR,
    }

def run_global_learning_cycle(*, promote: bool = False, horizon_configs: dict | None = None,
                               feature_dataset_path=None, daily_dataset_path=None,
                               models_root=None, project_root=None, report_dir=None,
                               rebuild_datasets: bool = True) -> dict:
    paths = _default_paths()
    if feature_dataset_path: paths["feature_dataset"] = Path(feature_dataset_path)
    if daily_dataset_path: paths["daily_dataset"] = Path(daily_dataset_path)
    if models_root: paths["models_root"] = Path(models_root)
    if project_root: paths["project_root"] = Path(project_root)
    if report_dir: paths["report_dir"] = Path(report_dir)
    paths["report_dir"].mkdir(parents=True, exist_ok=True)

    cycle_id = str(uuid.uuid4())
    started_at = _utc_now()
    print("=" * 72)
    print("GLOBAL LEARNING CYCLE")
    print("=" * 72)
    print(f"cycle_id:  {cycle_id}")
    print(f"started:   {started_at}")
    print(f"promote:   {promote}")
    print(f"rebuild:   {rebuild_datasets}")
    print()

    # Refresh source data from DB before any horizon trains.
    # Failure stops the cycle immediately (no training on stale data).
    rebuild_info = {"requested": bool(rebuild_datasets), "ran": False, "error": None}
    if rebuild_datasets:
        print("-" * 72)
        print("[REBUILD] Refreshing datasets from database...")
        print("-" * 72)
        try:
            rebuild_datasets_from_db()
            rebuild_info["ran"] = True
            print("[REBUILD] Dataset refresh completed successfully.")
            print()
        except Exception as exc:
            rebuild_info["error"] = str(exc)
            finished_at = _utc_now()
            print(f"[REBUILD] FAILED: {exc}")
            print("Global Learning Cycle aborted before training.")
            result = {
                "cycle_id": cycle_id,
                "started_at": started_at,
                "finished_at": finished_at,
                "promote_requested": bool(promote),
                "rebuild": rebuild_info,
                "status": "failed",
                "error": f"dataset rebuild failed: {exc}",
                "models": {},
            }
            try:
                safe = json.loads(json.dumps(result, default=str))
                (paths["report_dir"] / "global_learning_cycle_report.json").write_text(
                    json.dumps(safe, indent=2), encoding="utf-8"
                )
                (paths["report_dir"] / "latest_cycle.json").write_text(
                    json.dumps(safe, indent=2), encoding="utf-8"
                )
            except OSError:
                pass
            return result
    else:
        print("[REBUILD] Skipped (--skip-rebuild / rebuild_datasets=False).")
        print()

    horizon_configs = horizon_configs or {}
    models_result = {}

    for horizon in HORIZONS:
        print("-" * 72)
        print(f"[{horizon.upper()}] Starting...")
        hc = horizon_configs.get(horizon) or {}
        algorithm = str(hc.get("algorithm", "ridge")).lower().strip()
        params = dict(hc.get("params") or hc.get("model_params") or {})
        cfg = HorizonTrainConfig(
            horizon=horizon, algorithm=algorithm, model_params=params,
            feature_dataset_path=paths["feature_dataset"],
            daily_dataset_path=paths["daily_dataset"],
            models_root=paths["models_root"], project_root=paths["project_root"],
            clustered=bool(hc.get("clustered", True)),
            cluster_min_days=int(hc.get("cluster_min_days", 7)),
            cluster_k_min=int(hc.get("cluster_k_min", 2)),
            cluster_k_max=int(hc.get("cluster_k_max", 7)),
            cluster_min_rows=int(hc.get("cluster_min_rows", 20)),
            cluster_min_devices=int(hc.get("cluster_min_devices", 30)),
            cluster_min_frac=float(hc.get("cluster_min_frac", 0.03)),
            cluster_outlier_z=(hc.get("cluster_outlier_z", 12.0) or None),
            # Datasets rebuilt in THIS run -> cluster from scratch.
            # No rebuild (--skip-rebuild) -> keep the current production clustering.
            recluster=bool(hc.get("recluster", rebuild_info["ran"])),
            cluster_fallback_scope=str(hc.get("cluster_fallback_scope", "all")),
        )
        entry = {"status": "pending", "candidate_version": None, "production_version_before": None,
                 "comparison": None, "promotion": "skipped", "metrics": {}, "algorithm": algorithm}
        try:
            trainer = get_trainer(cfg)
            train_result = trainer.train_and_evaluate()
            entry["status"] = train_result.get("status", "success")
            entry["candidate_version"] = train_result.get("candidate_version")
            entry["production_version_before"] = train_result.get("production_version_before")
            entry["comparison"] = train_result.get("comparison")
            entry["metrics"] = train_result.get("metrics") or {}
            entry["production_metrics"] = train_result.get("production_metrics")
            entry["comparison_detail"] = train_result.get("comparison_detail")
            entry["algorithm"] = train_result.get("algorithm", algorithm)
            entry["cluster"] = train_result.get("cluster")
            print(f"[{horizon.upper()}] Candidate: {entry['candidate_version']}")
            print(f"[{horizon.upper()}] Production before: {entry['production_version_before']}")
            _c = (entry.get("cluster") or {}).get("refit") or {}
            if cfg.clustered:
                print(f"[{horizon.upper()}] Clustering mode: "
                      f"{'FRESH (re-clustered from scratch)' if cfg.recluster else 'REUSE current clusterer'}")
                print(f"[{horizon.upper()}] Clustering: status={_c.get('status')} k={_c.get('best_k')} "
                      f"clustered_devices={_c.get('n_clustered_devices')} cluster_models={_c.get('clusters_with_model')}")
            print(f"[{horizon.upper()}] Comparison: {entry['comparison']}")
            m = entry["metrics"]
            if m:
                print(f"[{horizon.upper()}] Metrics  MAE={m.get('mae'):.4f}  RMSE={m.get('rmse'):.4f}  MAPE={m.get('mape'):.2f}  MAAPE={m.get('maape'):.2f}  R2={m.get('r2'):.4f}")
            if cfg.clustered:
                _r = (entry.get("cluster") or {}).get("holdout_routes") or {}
                for _name, _v in _r.items():
                    _g = f"  global_mae={_v['global_mae']:.4f}" if "global_mae" in _v else ""
                    print(f"[{horizon.upper()}]   route {_name:24s} rows={_v['rows']:6d} devices={_v['devices']:4d} mae={_v['mae']:.4f}{_g}")
                _rf = (entry.get("cluster") or {}).get("refit") or {}
                if _rf.get("clustered"):
                    print(f"[{horizon.upper()}] Fallback model: scope={_rf.get('fallback_scope')} "
                          f"train_rows={_rf.get('fallback_train_rows')} clusters_without_model={_rf.get('clusters_without_model')}")
            if promote:
                promo = trainer.promote(train_result)
                if promo.get("promoted"):
                    entry["promotion"] = "promoted"
                    entry["production_version_after"] = promo.get("version")
                    print(f"[{horizon.upper()}] Promotion: PROMOTED")
                else:
                    entry["promotion"] = "rejected"
                    entry["promotion_reason"] = promo.get("reason")
                    print(f"[{horizon.upper()}] Promotion: REJECTED ({promo.get('reason')})")
            else:
                entry["promotion"] = "not_requested"
                print(f"[{horizon.upper()}] Promotion: not requested")
        except Exception as exc:
            entry["status"] = "failed"
            entry["error"] = str(exc)
            entry["traceback"] = traceback.format_exc()
            print(f"[{horizon.upper()}] FAILED: {exc}")
            traceback.print_exc()
        models_result[horizon] = entry
        print()

    finished_at = _utc_now()
    result = {"cycle_id": cycle_id, "started_at": started_at, "finished_at": finished_at,
              "promote_requested": bool(promote), "rebuild": rebuild_info,
              "status": "completed", "models": models_result}
    try:
        safe = json.loads(json.dumps(result, default=str))
        (paths["report_dir"] / "global_learning_cycle_report.json").write_text(json.dumps(safe, indent=2), encoding="utf-8")
        (paths["report_dir"] / "latest_cycle.json").write_text(json.dumps(safe, indent=2), encoding="utf-8")
        hist = paths["report_dir"] / "history"
        hist.mkdir(exist_ok=True)
        (hist / f"{cycle_id}.json").write_text(json.dumps(safe, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"Warning: report write failed: {exc}")

    print("=" * 72)
    print("GLOBAL LEARNING CYCLE COMPLETED")
    for h, e in models_result.items():
        print(f"  {h:8s}  status={e.get('status'):8s}  cmp={str(e.get('comparison')):10s}  promo={e.get('promotion')}")
    print()
    return result

def main(argv=None):
    parser = argparse.ArgumentParser(description="Unified multi-horizon Global Learning Cycle")
    parser.add_argument("--promote", action="store_true")
    parser.add_argument(
        "--skip-rebuild",
        action="store_true",
        help="Skip DB export + daily/feature dataset rebuild (use existing CSVs).",
    )
    parser.add_argument("--algorithm", default=None)
    parser.add_argument("--3day-algorithm", dest="algo_3day", default=None)
    parser.add_argument("--weekly-algorithm", dest="algo_weekly", default=None)
    parser.add_argument("--monthly-algorithm", dest="algo_monthly", default=None)
    parser.add_argument("--params-json", default=None)
    parser.add_argument("--no-clustering", action="store_true")
    parser.add_argument("--cluster-min-days", type=int, default=30)
    parser.add_argument("--cluster-k-min", type=int, default=2)
    parser.add_argument("--cluster-k-max", type=int, default=7)
    parser.add_argument("--cluster-min-devices", type=int, default=30,
                        help="k is chosen so every cluster has at least this many devices")
    parser.add_argument("--cluster-min-frac", type=float, default=0.03,
                        help="...and at least this fraction of the clustered devices")
    parser.add_argument("--cluster-outlier-z", type=float, default=12.0,
                        help="robust-z above which a device skips KMeans and uses the global model (0 = off)")
    parser.add_argument("--cluster-min-rows", type=int, default=20)
    parser.add_argument("--fallback-scope", choices=["all", "uncovered"], default="all",
                        help="Training rows of the global fallback model (default: all).")
    parser.add_argument("--reuse-clustering", action="store_true",
                        help="Keep the current production clusterer even if datasets are rebuilt "
                             "(default: re-cluster from scratch whenever datasets were rebuilt).")
    parser.add_argument("--horizon-configs-json", default=None)
    args = parser.parse_args(argv)

    default_algo = (args.algorithm or "ridge").lower()
    default_params = json.loads(args.params_json) if args.params_json else {}
    horizon_configs = {h: {"algorithm": default_algo, "params": dict(default_params),
                          "clustered": not args.no_clustering,
                          "cluster_min_days": args.cluster_min_days,
                          "cluster_k_min": args.cluster_k_min,
                          "cluster_k_max": args.cluster_k_max,
                          "cluster_min_rows": args.cluster_min_rows,
                          "cluster_min_devices": args.cluster_min_devices,
                          "cluster_min_frac": args.cluster_min_frac,
                          "cluster_outlier_z": args.cluster_outlier_z,
                          "cluster_fallback_scope": args.fallback_scope,
                          **({"recluster": False} if args.reuse_clustering else {})}
                       for h in HORIZONS}
    if args.algo_3day: horizon_configs["3day"]["algorithm"] = args.algo_3day.lower()
    if args.algo_weekly: horizon_configs["weekly"]["algorithm"] = args.algo_weekly.lower()
    if args.algo_monthly: horizon_configs["monthly"]["algorithm"] = args.algo_monthly.lower()
    if args.horizon_configs_json:
        user = json.loads(args.horizon_configs_json)
        for h, cfg in user.items():
            if h in HORIZONS:
                merged = dict(horizon_configs[h])      # keep clustering keys from the CLI flags
                merged["algorithm"] = str(cfg.get("algorithm", horizon_configs[h]["algorithm"])).lower()
                merged["params"] = dict(cfg.get("params") or cfg.get("model_params") or horizon_configs[h]["params"])
                for key in ("clustered", "recluster", "cluster_fallback_scope", "cluster_min_days", "cluster_k_min", "cluster_k_max", "cluster_min_rows", "cluster_min_devices", "cluster_min_frac", "cluster_outlier_z"):
                    if key in cfg:
                        merged[key] = cfg[key]
                horizon_configs[h] = merged
    result = run_global_learning_cycle(promote=args.promote, horizon_configs=horizon_configs, rebuild_datasets=not args.skip_rebuild)
    print("__RESULT_JSON__:" + json.dumps(result, default=str))
    return 1 if any(m.get("status") == "failed" for m in result["models"].values()) else 0

if __name__ == "__main__":
    raise SystemExit(main())
