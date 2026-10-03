#!/usr/bin/env python
"""
prepare_lcl.py  -  Low Carbon London (LCL) half-hourly CSV partitions  ->  benchmark inputs

Streams the partitioned LCL CSV files (columns: LCLid, stdorToU, DateTime,
KWH/hh (per half hour)) chunk by chunk, so RAM stays low no matter how large the
dataset is, and writes the two inputs that `benchmark.py --source csv` expects:

    <output-dir>/electricity_data.csv   hourly:  device_id, timestamp, consumption_kwh   (--raw-data)
    <output-dir>/daily_dataset.csv      daily :  device_id, day, seg0..seg3              (--data)
                                        (only with --build-daily; built with the project's
                                         own DataProcessor + DatasetBuilder, same as
                                         build_full_daily_dataset.py)

Extra files written for traceability:
    lcl_scan_cache.csv / lcl_scan_meta.json   pass-1 statistics (re-used, so changing the
                                              window or the number of homes is instant)
    lcl_selected_households.csv               LCLid -> device_id map + quality stats
    lcl_summary.json                          every count printed in the data summary
    prepare_lcl.log                           full log

Pipeline
    PASS 1 (scan)   : for every (household, month) count rows / valid half-hours / Std rows.
                      Nothing is kept in RAM except these small counters.
    selection       : Std households only (dToU homes had dynamic prices in 2013 and
                      behave differently), coverage >= --min-coverage inside the window,
                      deterministic random sample of --max-devices (seed).
    PASS 2 (collect): re-read the files, keep only selected households inside the window,
                      aggregate half-hours -> hours (an hour is kept ONLY if both
                      half-hours are present; it is never "half filled").
    quality filter  : hourly coverage and longest gap per household (<= --max-gap-hours,
                      default 6 = DataProcessor.MAX_INTERPOLATION_GAP).
    sanity report   : duplicates, Null, negatives, off-grid timestamps, DST signature,
                      units (kWh/day), extreme values.

Timezone: if check_lcl_timezone.py reports UTC_LIKE, pass --local-tz Europe/London so that
    timestamps become local wall-clock time (people live by the wall clock, the daily
    segments seg0..seg3 must mean the same clock hours all year).

Not verified (please check against the LCL documentation / your own extract):
    * whether `DateTime` is local time (GMT/BST) or UTC, and whether it marks the start
      or the end of the half-hour.  The script keeps timestamps exactly as given and
      prints a DST signature that tells you which it is.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

LOG = logging.getLogger("prepare_lcl")

COLS = ["LCLid", "stdorToU", "DateTime", "kwh"]
FILE_RE = re.compile(r"_(\d+)\.csv$", re.IGNORECASE)
ID_RE = re.compile(r"^[A-Za-z]+0*(\d+)$")
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
HOURLY_NAME = "electricity_data.csv"
DAILY_NAME = "daily_dataset.csv"
SCAN_CACHE = "lcl_scan_cache.csv"
SCAN_META = "lcl_scan_meta.json"


class PrepareError(RuntimeError):
    pass


# ============================================================================
# small helpers
# ============================================================================
def list_files(input_dir: Path, pattern: str) -> list[Path]:
    files = list(input_dir.glob(pattern))
    if not files:
        raise PrepareError(f"No files match {pattern!r} in {input_dir}")

    def key(p: Path):
        m = FILE_RE.search(p.name)
        return (int(m.group(1)) if m else 10 ** 9, p.name)

    return sorted(files, key=key)


def read_chunks(path: Path, chunk_rows: int):
    """Yield DataFrames with columns COLS, every column kept as raw string.

    keep_default_na=False keeps the literal 'Null' as text (handled later by
    to_numeric(errors='coerce')), so nothing is silently reinterpreted.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        first = fh.readline()
    has_header = first.lower().lstrip("\ufeff").startswith("lclid")
    yield from pd.read_csv(
        path,
        header=0 if has_header else None,
        names=COLS,
        usecols=[0, 1, 2, 3],
        dtype=str,
        chunksize=chunk_rows,
        keep_default_na=False,
        na_filter=False,
    )


def to_kwh(series: pd.Series) -> pd.Series:
    """'  0.046' -> 0.046, 'Null'/'' -> NaN."""
    return pd.to_numeric(series, errors="coerce")


def longest_false_run(valid: np.ndarray) -> int:
    """Longest run of False in a 1-D boolean array (leading/trailing runs count)."""
    valid = np.asarray(valid, dtype=bool)
    if valid.size == 0:
        return 0
    if valid.all():
        return 0
    padded = np.concatenate(([True], valid, [True]))
    true_pos = np.flatnonzero(padded)
    return int((np.diff(true_pos) - 1).max())


def month_bounds(start_month: str, end_month: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    if not (MONTH_RE.match(start_month) and MONTH_RE.match(end_month)):
        raise PrepareError("--start-month / --end-month must look like YYYY-MM")
    start = pd.Timestamp(f"{start_month}-01")
    end_excl = pd.Timestamp(f"{end_month}-01") + pd.offsets.MonthBegin(1)
    if end_excl <= start:
        raise PrepareError("--end-month must not be before --start-month")
    return start, end_excl


def months_in(start: pd.Timestamp, end_excl: pd.Timestamp) -> list[str]:
    return [p.strftime("%Y-%m") for p in pd.period_range(start, end_excl - pd.Timedelta(days=1), freq="M")]


# ============================================================================
# PASS 1: scan
# ============================================================================
def scan_files(files: list[Path], chunk_rows: int) -> tuple[pd.DataFrame, dict]:
    """Per (LCLid, month): rows, valid half-hours, Std rows, non-Std rows."""
    parts: list[pd.DataFrame] = []
    meta = Counter()
    t0 = time.time()
    for fi, path in enumerate(files, 1):
        for chunk in read_chunks(path, chunk_rows):
            meta["rows"] += len(chunk)
            month = chunk["DateTime"].str.slice(0, 7)
            kwh = to_kwh(chunk["kwh"])
            tag = chunk["stdorToU"].str.strip().str.lower()
            g = pd.DataFrame({
                "LCLid": chunk["LCLid"].str.strip(),
                "month": month,
                "n_valid": ((kwh >= 0) & kwh.notna()).astype(np.int64),
                "n_std": (tag == "std").astype(np.int64),
            })
            agg = g.groupby(["LCLid", "month"], sort=False).agg(
                n_rows=("n_valid", "size"), n_valid=("n_valid", "sum"), n_std=("n_std", "sum")
            ).reset_index()
            parts.append(agg)
        if fi % 10 == 0 or fi == len(files):
            LOG.info("  scan: %d/%d files  (%.0f s, %s rows so far)",
                     fi, len(files), time.time() - t0, f"{meta['rows']:,}")
    scan = pd.concat(parts, ignore_index=True)
    scan = scan.groupby(["LCLid", "month"], as_index=False)[["n_rows", "n_valid", "n_std"]].sum()
    bad = ~scan["month"].str.match(MONTH_RE.pattern)
    meta["rows_bad_month"] = int(scan.loc[bad, "n_rows"].sum())
    scan = scan.loc[~bad].reset_index(drop=True)
    scan["n_other"] = scan["n_rows"] - scan["n_std"]
    return scan, dict(meta)


def load_or_scan(files: list[Path], out_dir: Path, chunk_rows: int, rescan: bool) -> tuple[pd.DataFrame, dict]:
    cache, meta_path = out_dir / SCAN_CACHE, out_dir / SCAN_META
    names = [f.name for f in files]
    if cache.exists() and meta_path.exists() and not rescan:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        if meta.get("files") == names:
            LOG.info("PASS 1: re-using %s (same %d files; use --rescan to redo)", cache.name, len(names))
            return pd.read_csv(cache, dtype={"LCLid": str, "month": str}), meta
        LOG.info("PASS 1: cache exists but the file list changed -> rescanning")
    LOG.info("PASS 1: scanning %d files (chunk=%s rows) ...", len(files), f"{chunk_rows:,}")
    scan, meta = scan_files(files, chunk_rows)
    meta["files"] = names
    scan.to_csv(cache, index=False)
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return scan, meta


# ============================================================================
# selection
# ============================================================================
def household_table(scan: pd.DataFrame, months: list[str], expected_half_hours: int) -> pd.DataFrame:
    """One row per household: Std flag over the WHOLE dataset, coverage inside the window."""
    whole = scan.groupby("LCLid").agg(n_std=("n_std", "sum"), n_other=("n_other", "sum"))
    whole["is_std"] = (whole["n_std"] > 0) & (whole["n_other"] == 0)
    whole["mixed_tariff"] = (whole["n_std"] > 0) & (whole["n_other"] > 0)
    win = scan[scan["month"].isin(months)].groupby("LCLid")["n_valid"].sum()
    whole["window_valid_half_hours"] = win.reindex(whole.index).fillna(0).astype(np.int64)
    whole["window_coverage"] = (whole["window_valid_half_hours"] / expected_half_hours).clip(upper=1.0)
    return whole.reset_index()


def suggest_windows(scan: pd.DataFrame, std_ids: set[str], min_coverage: float) -> list[str]:
    """How many Std households reach `min_coverage` for every contiguous month window."""
    sub = scan[scan["LCLid"].isin(std_ids)]
    piv = sub.pivot_table(index="LCLid", columns="month", values="n_valid", aggfunc="sum", fill_value=0)
    all_months = [p.strftime("%Y-%m") for p in pd.period_range(piv.columns.min(), piv.columns.max(), freq="M")]
    piv = piv.reindex(columns=all_months, fill_value=0)
    lines = []
    for length in (6, 9, 12):
        if len(all_months) < length:
            continue
        best = []
        for i in range(len(all_months) - length + 1):
            ms = all_months[i:i + length]
            start = pd.Timestamp(f"{ms[0]}-01")
            end_excl = pd.Timestamp(f"{ms[-1]}-01") + pd.offsets.MonthBegin(1)
            exp = (end_excl - start).days * 48
            cov = piv[ms].sum(axis=1) / exp
            best.append((int((cov >= min_coverage).sum()), ms[0], ms[-1]))
        best.sort(reverse=True)
        lines.append(f"  {length:>2} months: " + " | ".join(f"{a}..{b}: {n} Std homes" for n, a, b in best[:3]))
    return lines


def choose_households(hh: pd.DataFrame, min_coverage: float, max_devices: int,
                      oversample: float, seed: int) -> pd.DataFrame:
    cand = hh[hh["is_std"] & (hh["window_coverage"] >= min_coverage)].sort_values("LCLid").reset_index(drop=True)
    rng = np.random.default_rng(seed)
    order = rng.permutation(len(cand))
    cand = cand.iloc[order].reset_index(drop=True)
    if max_devices and max_devices > 0:
        cand = cand.iloc[: int(math.ceil(max_devices * oversample))]
    return cand


# ============================================================================
# PASS 2: collect + hourly aggregation
# ============================================================================
def collect_hourly(files: list[Path], ids: set[str], start: pd.Timestamp, end_excl: pd.Timestamp,
                   chunk_rows: int) -> tuple[pd.DataFrame, Counter]:
    """Return hourly (LCLid, hour, kwh) for `ids`, plus data-quality counters."""
    parts: list[pd.DataFrame] = []
    c: Counter = Counter()
    t0 = time.time()
    for fi, path in enumerate(files, 1):
        for chunk in read_chunks(path, chunk_rows):
            sub = chunk.loc[chunk["LCLid"].str.strip().isin(ids)]
            if sub.empty:
                continue
            ts = pd.to_datetime(sub["DateTime"].str.slice(0, 19), format="%Y-%m-%d %H:%M:%S", errors="coerce")
            c["rows_selected_homes"] += len(sub)
            c["rows_bad_timestamp"] += int(ts.isna().sum())
            inwin = ts.notna() & (ts >= start) & (ts < end_excl)
            sub, ts = sub.loc[inwin], ts.loc[inwin]
            c["rows_in_window"] += len(sub)
            if sub.empty:
                continue
            kwh = to_kwh(sub["kwh"])
            c["rows_null_kwh"] += int(kwh.isna().sum())
            c["rows_negative_kwh"] += int((kwh < 0).sum())
            ok = kwh.notna() & (kwh >= 0)
            df = pd.DataFrame({"LCLid": sub["LCLid"].str.strip().to_numpy(),
                               "ts": ts.to_numpy(), "kwh": kwh.to_numpy()})[ok.to_numpy()]
            c["rows_off_grid_minute"] += int((~pd.DatetimeIndex(df["ts"]).minute.isin([0, 30])).sum())
            before = len(df)
            df = df.drop_duplicates(subset=["LCLid", "ts"], keep="first")
            c["rows_duplicate_within_chunk"] += before - len(df)
            df["hour"] = pd.DatetimeIndex(df["ts"]).floor("h")
            g = df.groupby(["LCLid", "hour"], sort=False)["kwh"].agg(["sum", "count"]).reset_index()
            parts.append(g)
        if fi % 10 == 0 or fi == len(files):
            LOG.info("  collect: %d/%d files  (%.0f s)", fi, len(files), time.time() - t0)
    if not parts:
        raise PrepareError("No rows found for the selected households inside the window.")
    allh = pd.concat(parts, ignore_index=True)
    # an hour can be split across two chunks/files -> add the partial sums and counts
    allh = allh.groupby(["LCLid", "hour"], as_index=False)[["sum", "count"]].sum()
    c["hours_seen"] = len(allh)
    c["hours_one_half_hour_only"] = int((allh["count"] == 1).sum())
    c["hours_more_than_two_readings"] = int((allh["count"] > 2).sum())
    good = allh[allh["count"] == 2].rename(columns={"sum": "kwh"})[["LCLid", "hour", "kwh"]]
    return good.reset_index(drop=True), c


def quality_filter(hourly: pd.DataFrame, start: pd.Timestamp, end_excl: pd.Timestamp,
                   min_coverage: float, max_gap_hours: int, max_hourly_kwh: float) -> tuple[pd.DataFrame, pd.DataFrame, Counter]:
    """Drop absurd hours, then drop households with too little coverage / too long a gap."""
    c: Counter = Counter()
    n_hours = int((end_excl - start) // pd.Timedelta(hours=1))
    too_big = hourly["kwh"] > max_hourly_kwh
    c["hours_above_max_kwh_dropped"] = int(too_big.sum())
    hourly = hourly.loc[~too_big]
    idx = ((hourly["hour"] - start) // pd.Timedelta(hours=1)).to_numpy().astype(np.int64)
    in_range = (idx >= 0) & (idx < n_hours)
    hourly, idx = hourly.loc[in_range], idx[in_range]

    rows = []
    for lcl, sub_idx in pd.Series(np.arange(len(hourly))).groupby(hourly["LCLid"].to_numpy()):
        valid = np.zeros(n_hours, dtype=bool)
        valid[idx[sub_idx.to_numpy()]] = True
        rows.append({"LCLid": lcl, "hourly_coverage": float(valid.mean()),
                     "max_gap_hours": longest_false_run(valid), "n_hours": int(valid.sum())})
    q = pd.DataFrame(rows)
    if q.empty:
        raise PrepareError("No household has any valid hour in the window.")
    q["pass_coverage"] = q["hourly_coverage"] >= min_coverage
    q["pass_gap"] = q["max_gap_hours"] <= max_gap_hours
    q["keep"] = q["pass_coverage"] & q["pass_gap"]
    c["homes_failed_hourly_coverage"] = int((~q["pass_coverage"]).sum())
    c["homes_failed_max_gap"] = int((~q["pass_gap"]).sum())
    return hourly, q, c


def to_local_wallclock(hourly: pd.DataFrame, tz: str) -> tuple[pd.DataFrame, dict]:
    """Convert hourly UTC timestamps (column `hour`) to naive local wall-clock time in `tz`.

    Quality filtering (coverage / gaps) is done BEFORE this on the continuous UTC grid, so
    it is unaffected.  After the conversion:
      * spring-forward: the local hour 01:00-02:00 does not exist  -> a normal 1-hour gap
        (DataProcessor interpolates it, like any other short gap)
      * fall-back: two different UTC hours map to the same local hour -> their kWh are
        AVERAGED into one row (the pipeline needs one row per (device, hour))
    """
    loc = (pd.DatetimeIndex(hourly["hour"]).tz_localize("UTC").tz_convert(tz).tz_localize(None))
    out = hourly.assign(hour=loc)
    n_before = len(out)
    dup = out.duplicated(["LCLid", "hour"], keep=False)
    info = {"local_tz": tz, "hours_merged_fall_back": int(dup.sum() - out.loc[dup].drop_duplicates(["LCLid", "hour"]).shape[0])}
    out = out.groupby(["LCLid", "hour"], as_index=False, sort=False)["kwh"].mean()
    info["rows_after_local_conversion"] = int(len(out))
    info["rows_before_local_conversion"] = int(n_before)
    return out, info


# ============================================================================
# sanity report
# ============================================================================
def dst_signature(out: pd.DataFrame) -> dict:
    """Dates where most homes do not have exactly 24 hourly values (DST if local time)."""
    day = out["timestamp"].dt.normalize()
    per = out.groupby(["device_id", day]).size().rename("n").reset_index()
    frac24 = per.groupby("timestamp")["n"].apply(lambda s: float((s == 24).mean()))
    odd = frac24[frac24 < 0.5]
    hrs = per[per["timestamp"].isin(odd.index)].groupby("timestamp")["n"].agg(lambda s: int(s.mode().iloc[0]))
    return {str(d.date()): int(h) for d, h in hrs.items()}


def sanity_report(out: pd.DataFrame, n_hours_window: int) -> dict:
    k = out["consumption_kwh"]
    daily = out.groupby(["device_id", out["timestamp"].dt.normalize()])["consumption_kwh"].sum()
    per_dev_days = out.groupby("device_id")["timestamp"].agg(lambda s: s.dt.normalize().nunique())
    rep = {
        "devices": int(out["device_id"].nunique()),
        "hourly_rows": int(len(out)),
        "first_timestamp": str(out["timestamp"].min()),
        "last_timestamp": str(out["timestamp"].max()),
        "days_per_device_min_median_max": [int(per_dev_days.min()), int(per_dev_days.median()), int(per_dev_days.max())],
        "hourly_kwh_mean": round(float(k.mean()), 4),
        "hourly_kwh_median": round(float(k.median()), 4),
        "hourly_kwh_p99": round(float(k.quantile(0.99)), 4),
        "hourly_kwh_max": round(float(k.max()), 4),
        "daily_kwh_per_home_median": round(float(daily.groupby("device_id").mean().median()), 3),
        "daily_kwh_per_home_p5_p95": [round(float(x), 3) for x in daily.groupby("device_id").mean().quantile([0.05, 0.95])],
        "zero_hours_share": round(float((k == 0).mean()), 4),
        "window_hours": n_hours_window,
        "dst_signature_dates_with_non24h": dst_signature(out),
    }
    med = rep["daily_kwh_per_home_median"]
    rep["units_plausible"] = bool(1.0 <= med <= 60.0)
    return rep


def print_summary(title: str, d: dict) -> None:
    LOG.info("=" * 72)
    LOG.info(title)
    LOG.info("=" * 72)
    for key, val in d.items():
        LOG.info("  %-38s %s", key, val)


# ============================================================================
# daily segment dataset (project's own code)
# ============================================================================
def _daily_worker(user_df: pd.DataFrame, src_dir: str) -> pd.DataFrame:
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)
    from dataset_builder import DatasetBuilder  # project module

    return DatasetBuilder().build_daily_segments(user_df)


def build_daily(hourly_csv: Path, daily_csv: Path, project_src: Path, n_jobs: int) -> None:
    """Same steps as build_full_daily_dataset.py, but paths are explicit and devices run in parallel."""
    if str(project_src) not in sys.path:
        sys.path.insert(0, str(project_src))
    try:
        from data_processor import CSVDataSource, DataProcessor
        import dataset_builder  # noqa: F401  (fail early if the project code is not importable)
    except ImportError as exc:
        raise PrepareError(
            f"Cannot import the project's data_processor/dataset_builder from {project_src}: {exc}\n"
            "  -> use --project-src PATH_TO_src_FOLDER") from exc

    LOG.info("DAILY: preprocessing %s with the project's DataProcessor ...", hourly_csv.name)
    proc = DataProcessor(CSVDataSource(str(hourly_csv)))
    proc.preprocess()
    devices = sorted(int(d) for d in proc.df["device_id"].unique())
    LOG.info("DAILY: %d devices after preprocessing; building segments (n_jobs=%d) ...", len(devices), n_jobs)
    if n_jobs == 1:
        frames = []
        for i, d in enumerate(devices, 1):
            frames.append(_daily_worker(proc.get_device_data(d), str(project_src)))
            if i % 25 == 0:
                LOG.info("  daily: %d/%d devices", i, len(devices))
    else:
        from joblib import Parallel, delayed

        frames = Parallel(n_jobs=n_jobs, verbose=5)(
            delayed(_daily_worker)(proc.get_device_data(d), str(project_src)) for d in devices)
    frames = [f for f in frames if f is not None and not f.empty]
    if not frames:
        raise PrepareError("DatasetBuilder returned no rows (need > 30 days of clean data per device).")
    daily = pd.concat(frames, ignore_index=True).sort_values(["device_id", "day"]).reset_index(drop=True)
    daily.to_csv(daily_csv, index=False)
    LOG.info("DAILY: wrote %s  shape=%s devices=%d days=%d", daily_csv, daily.shape,
             daily["device_id"].nunique(), daily["day"].nunique())


# ============================================================================
# main
# ============================================================================
def make_device_ids(lcl_ids: list[str]) -> dict[str, int]:
    """MAC004221 -> 4221 when every id has that shape and the numbers are unique; else 1..N."""
    nums = []
    for s in lcl_ids:
        m = ID_RE.match(s)
        nums.append(int(m.group(1)) if m else None)
    if all(n is not None for n in nums) and len(set(nums)) == len(nums):
        return dict(zip(lcl_ids, nums))
    LOG.warning("LCLid values are not of the form MACxxxxxx (unique numbers) -> using sequential ids 1..N")
    return {s: i for i, s in enumerate(sorted(lcl_ids), 1)}


def run(args: argparse.Namespace) -> dict:
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    hourly_csv, daily_csv = out_dir / HOURLY_NAME, out_dir / DAILY_NAME
    project_src = Path(args.project_src).resolve()
    n_jobs = args.n_jobs if args.n_jobs else max(1, (os.cpu_count() or 2) - 1)

    if args.daily_only:
        if not hourly_csv.exists():
            raise PrepareError(f"--daily-only needs {hourly_csv} (run without it first)")
        build_daily(hourly_csv, daily_csv, project_src, n_jobs)
        return {"daily_only": True}

    start, end_excl = month_bounds(args.start_month, args.end_month)
    months = months_in(start, end_excl)
    expected_hh = int((end_excl - start).days * 48)
    n_hours_window = int((end_excl - start) // pd.Timedelta(hours=1))
    files = list_files(Path(args.input_dir), args.pattern)
    LOG.info("Input: %d files, %s .. %s", len(files), files[0].name, files[-1].name)
    LOG.info("Window: %s -> %s (exclusive), %d months, %d days", start.date(), end_excl.date(), len(months), (end_excl - start).days)

    scan, scan_meta = load_or_scan(files, out_dir, args.chunk_rows, args.rescan)
    hh = household_table(scan, months, expected_hh)
    summary: dict = {
        "rows_scanned": int(scan_meta.get("rows", 0)),
        "rows_with_unparseable_month": int(scan_meta.get("rows_bad_month", 0)),
        "households_total": int(len(hh)),
        "households_std_only": int(hh["is_std"].sum()),
        "households_non_std_dropped": int((~hh["is_std"] & ~hh["mixed_tariff"]).sum()),
        "households_mixed_tariff_dropped": int(hh["mixed_tariff"].sum()),
        "std_with_coverage>=min": int((hh["is_std"] & (hh["window_coverage"] >= args.min_coverage)).sum()),
        "window": f"{args.start_month}..{args.end_month}",
    }
    LOG.info("Std households with >= %.0f%% coverage per window length (best windows):", args.min_coverage * 100)
    sugg = suggest_windows(scan, set(hh.loc[hh["is_std"], "LCLid"]), args.min_coverage)
    for line in sugg or ["  (the data spans fewer than 6 months - no window suggestions)"]:
        LOG.info(line)
    print_summary("SELECTION SUMMARY (pass 1)", summary)
    if args.stats_only:
        return summary

    cand = choose_households(hh, args.min_coverage, args.max_devices, args.oversample, args.seed)
    if cand.empty:
        raise PrepareError("No Std household reaches the coverage threshold in this window. "
                           "Use a shorter window or --min-coverage lower (see the window suggestions above).")
    LOG.info("PASS 2: collecting %d candidate households (target %s) ...", len(cand), args.max_devices or "all")
    hourly, c2 = collect_hourly(files, set(cand["LCLid"]), start, end_excl, args.chunk_rows)
    hourly, q, c3 = quality_filter(hourly, start, end_excl, args.min_coverage,
                                   args.max_gap_hours, args.max_hourly_kwh)
    kept = [lcl for lcl in cand["LCLid"] if lcl in set(q.loc[q["keep"], "LCLid"])]
    if args.max_devices and args.max_devices > 0:
        kept = kept[: args.max_devices]
    if not kept:
        raise PrepareError("All candidate households failed the hourly quality filter.")
    if args.max_devices and len(kept) < args.max_devices:
        LOG.warning("Only %d households survived (requested %d). Raise --oversample or relax --min-coverage.",
                    len(kept), args.max_devices)

    id_map = make_device_ids(kept)
    hourly = hourly[hourly["LCLid"].isin(kept)].copy()
    tz_info: dict = {}
    if args.local_tz:
        hourly, tz_info = to_local_wallclock(hourly, args.local_tz)
        LOG.info("Converted UTC -> %s wall-clock: %s", args.local_tz, tz_info)
    out = pd.DataFrame({
        "device_id": hourly["LCLid"].map(id_map).astype("int64"),
        "timestamp": hourly["hour"],
        "consumption_kwh": hourly["kwh"].astype("float64").round(3),
    }).sort_values(["device_id", "timestamp"]).reset_index(drop=True)
    if out.duplicated(["device_id", "timestamp"]).any():
        raise PrepareError("Internal error: duplicate (device_id, timestamp) in the output")
    if (out["consumption_kwh"] < 0).any() or out["consumption_kwh"].isna().any():
        raise PrepareError("Internal error: negative or NaN consumption in the output")

    out.to_csv(hourly_csv, index=False, date_format="%Y-%m-%d %H:%M:%S", float_format="%.3f")
    sel = q[q["LCLid"].isin(kept)].copy()
    sel["device_id"] = sel["LCLid"].map(id_map)
    sel.merge(hh[["LCLid", "window_coverage"]].rename(columns={"window_coverage": "pass1_half_hour_coverage"}),
              on="LCLid").sort_values("device_id").to_csv(out_dir / "lcl_selected_households.csv", index=False)

    san = sanity_report(out, n_hours_window)
    quality = {**{k: int(v) for k, v in c2.items()}, **{k: int(v) for k, v in c3.items()},
               "candidates_requested": int(len(cand)), "households_kept": int(len(kept)),
               **{k: v for k, v in tz_info.items() if isinstance(v, int)}}
    print_summary("DATA QUALITY COUNTERS (pass 2)", quality)
    print_summary("OUTPUT SUMMARY", san)
    if not san["units_plausible"]:
        LOG.warning("Median daily kWh per home = %.2f is outside 1..60 -> check the units of the source file!",
                    san["daily_kwh_per_home_median"])
    if san["dst_signature_dates_with_non24h"] and args.local_tz:
        LOG.info("Days without 24 hourly values after the %s conversion (expected: 2013-03-31 = 23 h; a last "
                 "partial day after the window end is just the +1 h summer shift): %s",
                 args.local_tz, san["dst_signature_dates_with_non24h"])
    elif san["dst_signature_dates_with_non24h"]:
        LOG.warning("Dates where most homes do not have 24 hourly values: %s  (23 -> spring-forward, 25 -> "
                    "fall-back: timestamps are LOCAL time. If you see no such dates, they are probably UTC.)",
                    san["dst_signature_dates_with_non24h"])
    LOG.info("Wrote %s", hourly_csv)

    full = {"selection": summary, "quality": quality, "output": san,
            "parameters": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()}}
    (out_dir / "lcl_summary.json").write_text(json.dumps(full, indent=2, default=str), encoding="utf-8")

    if args.build_daily:
        build_daily(hourly_csv, daily_csv, project_src, n_jobs)
    else:
        LOG.info("Next: add --daily-only to build %s with the project's DatasetBuilder "
                 "(or re-run with --build-daily).", DAILY_NAME)
    return full


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--input-dir", type=Path, help="folder with LCL-June2015v2_*.csv")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--pattern", default="LCL-June2015v2_*.csv")
    p.add_argument("--start-month", default="2013-01", help="first month of the window, YYYY-MM")
    p.add_argument("--end-month", default="2013-12", help="last month of the window (inclusive), YYYY-MM")
    p.add_argument("--max-devices", type=int, default=500, help="0 = every household that passes the filters")
    p.add_argument("--min-coverage", type=float, default=0.97,
                   help="min share of valid half-hours (pass 1) and of valid hours (pass 2) inside the window")
    p.add_argument("--max-gap-hours", type=int, default=6, help="longest allowed run of missing hours "
                   "(6 = DataProcessor.MAX_INTERPOLATION_GAP)")
    p.add_argument("--max-hourly-kwh", type=float, default=25.0, help="hours above this are treated as invalid")
    p.add_argument("--oversample", type=float, default=1.3, help="collect this many times --max-devices candidates, "
                   "because some fail the hourly gap filter")
    p.add_argument("--local-tz", default=None, metavar="TZ",
                   help="treat the file's DateTime as UTC and write local wall-clock time in this zone "
                        "(e.g. Europe/London). Use it when check_lcl_timezone.py says UTC_LIKE. "
                        "Default: keep timestamps as given.")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--chunk-rows", type=int, default=1_000_000)
    p.add_argument("--rescan", action="store_true", help="ignore the pass-1 cache")
    p.add_argument("--stats-only", action="store_true", help="run pass 1 only and print window suggestions")
    p.add_argument("--build-daily", action="store_true", help="also build daily_dataset.csv with the project's code")
    p.add_argument("--daily-only", action="store_true", help="only build daily_dataset.csv from an existing hourly csv")
    p.add_argument("--project-src", type=Path, default=Path(__file__).resolve().parent,
                   help="folder that contains data_processor.py / dataset_builder.py / segmenter.py")
    p.add_argument("--n-jobs", type=int, default=0, help="workers for --build-daily (0 = cpu count - 1)")
    args = p.parse_args(argv)
    if not args.daily_only and args.input_dir is None:
        p.error("--input-dir is required (unless --daily-only)")
    if not 0.0 < args.min_coverage <= 1.0:
        p.error("--min-coverage must be in (0, 1]")
    return args


def setup_logging(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    LOG.setLevel(logging.INFO)
    LOG.handlers.clear()
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s")
    for h in (logging.StreamHandler(sys.stdout), logging.FileHandler(out_dir / "prepare_lcl.log", encoding="utf-8")):
        h.setFormatter(fmt)
        LOG.addHandler(h)


def main(argv=None) -> int:
    args = parse_args(argv)
    setup_logging(Path(args.output_dir))
    t0 = time.time()
    try:
        run(args)
    except PrepareError as exc:
        LOG.error("%s", exc)
        return 2
    else:
        LOG.info("Done in %.1f min", (time.time() - t0) / 60)
        return 0
    finally:
        # release prepare_lcl.log (Windows cannot delete a folder that holds an open log file)
        for h in list(LOG.handlers):
            h.close()
            LOG.removeHandler(h)


if __name__ == "__main__":
    sys.exit(main())