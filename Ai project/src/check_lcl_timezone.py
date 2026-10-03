"""
check_lcl_timezone.py - is the LCL hourly clock UTC/GMT-continuous or UK wall-clock time?

Idea: people live by the wall clock.  If the file stores UTC, the typical daily profile in
summer (BST, UTC+1) appears ONE HOUR EARLIER on the file's clock than the winter profile.
If the file stores local time, both seasons line up (shift 0).

We compare the mean weekday profile of Dec-Feb (GMT) with Jun-Aug (BST), after scaling every
home by its own mean, and find the circular hour shift with the highest correlation.

    python src\\check_lcl_timezone.py --hourly "C:\\...\\lcl_data\\electricity_data.csv"
    python src\\check_lcl_timezone.py --self-test

This is evidence, not proof (daylight also changes behaviour a little); the script prints the
correlation at every shift so you can see how clear the decision is.
"""
from __future__ import annotations

import argparse
import sys

import numpy as np
import pandas as pd

WINTER, SUMMER = (12, 1, 2), (6, 7, 8)


def mean_weekday_profile(df: pd.DataFrame, months: tuple[int, ...]) -> np.ndarray:
    sub = df[df["timestamp"].dt.month.isin(months) & (df["timestamp"].dt.dayofweek < 5)]
    if sub.empty:
        raise SystemExit(f"no weekday rows in months {months}: use a window that includes them")
    prof = sub.groupby(sub["timestamp"].dt.hour)["rel"].mean().reindex(range(24))
    if prof.isna().any():
        raise SystemExit("some hours of the day are missing from the profile")
    return prof.to_numpy()


def estimate_shift(df: pd.DataFrame) -> dict:
    """df: device_id, timestamp (naive), consumption_kwh. Returns correlation per shift and a verdict."""
    df = df.copy()
    scale = df.groupby("device_id")["consumption_kwh"].transform("mean")
    df = df[scale > 0]
    df["rel"] = df["consumption_kwh"] / scale[scale > 0]
    w, s = mean_weekday_profile(df, WINTER), mean_weekday_profile(df, SUMMER)
    corr = {k: float(np.corrcoef(np.roll(w, k), s)[0, 1]) for k in range(-3, 4)}
    best = max(corr, key=corr.get)
    c0, cm1 = corr[0], corr[-1]
    if best == -1 and cm1 - c0 > 0.002:
        verdict = "UTC_LIKE"      # summer behaviour appears 1 h earlier on the file's clock
    elif best == 0:
        verdict = "LOCAL_LIKE"    # profiles line up without shifting
    else:
        verdict = "INCONCLUSIVE"
    return {"corr_by_shift": corr, "best_shift": best, "verdict": verdict,
            "winter_peak_hour": int(np.argmax(w)), "summer_peak_hour": int(np.argmax(s)),
            "winter_trough_hour": int(np.argmin(w)), "summer_trough_hour": int(np.argmin(s))}


def report(res: dict) -> None:
    print("shift (h)   correlation   (np.roll(winter, shift) vs summer)")
    for k, v in res["corr_by_shift"].items():
        print(f"  {k:>3}        {v:.4f}{'   <- best' if k == res['best_shift'] else ''}")
    print(f"winter peak/trough hour: {res['winter_peak_hour']}/{res['winter_trough_hour']}   "
          f"summer peak/trough hour: {res['summer_peak_hour']}/{res['summer_trough_hour']}")
    print("VERDICT:", res["verdict"])
    if res["verdict"] == "UTC_LIKE":
        print("  -> the clock looks like UTC/GMT without DST: summer behaviour is 1 h earlier than winter.")
    elif res["verdict"] == "LOCAL_LIKE":
        print("  -> profiles line up: the clock behaves like local wall-clock time.")
    else:
        print("  -> no clear 0 h or -1 h shift; do not convert time zones on this evidence.")


def _synthetic(utc: bool) -> pd.DataFrame:
    rng = np.random.default_rng(0)
    ts = pd.date_range("2013-01-01", "2013-12-31 23:00", freq="h")
    local = ts  # behaviour is defined on the WALL clock
    bst = (ts >= "2013-03-31 01:00") & (ts < "2013-10-27 01:00")
    hod = local.hour.to_numpy()
    base = 0.25 + 0.5 * np.exp(-((hod - 19) ** 2) / 5) + 0.25 * np.exp(-((hod - 7.5) ** 2) / 3)
    rows = []
    for d in range(40):
        v = base * rng.uniform(0.6, 1.6) + rng.normal(0, 0.05, len(ts))
        stamp = ts - pd.to_timedelta(np.where(bst & utc, 1, 0), unit="h")  # UTC = wall clock - 1 h in BST
        rows.append(pd.DataFrame({"device_id": d, "timestamp": stamp, "consumption_kwh": np.clip(v, 0, None)}))
    return pd.concat(rows, ignore_index=True)


def self_test() -> None:
    a = estimate_shift(_synthetic(utc=True))
    b = estimate_shift(_synthetic(utc=False))
    assert a["verdict"] == "UTC_LIKE", a
    assert b["verdict"] == "LOCAL_LIKE", b
    print("self-test passed: UTC-stamped synthetic data -> UTC_LIKE, wall-clock synthetic -> LOCAL_LIKE")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--hourly", help="electricity_data.csv written by prepare_lcl.py")
    p.add_argument("--self-test", action="store_true")
    a = p.parse_args(argv)
    if a.self_test:
        self_test()
        return 0
    if not a.hourly:
        p.error("--hourly is required (or use --self-test)")
    df = pd.read_csv(a.hourly, parse_dates=["timestamp"])
    report(estimate_shift(df))
    return 0


if __name__ == "__main__":
    sys.exit(main())
