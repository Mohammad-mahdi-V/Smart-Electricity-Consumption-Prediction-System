"""
scheduler.py

Daily/Nightly scheduler for the electricity prediction system.

The systemd timer runs this file EVERY NIGHT.

Flow:

                    systemd
                       │
                       ▼
                 scheduler.py
                       │
           Is the global learning cycle due?
                 /           \
               YES            NO
                │              │
                ▼              ▼
global_learning_cycle.py   predicton code
                │
                ▼
      global learning cycle done

IMPORTANT:

If the global learning cycle is due, it has priority.

When the global learning cycle runs:
    - If promoted successfully:
        nightly prediction is NOT executed.
    - If candidate is rejected:
        nightly prediction IS executed.
    - If the global learning cycle fails:
        nightly prediction is NOT executed.

The important point is that candidate rejection is NOT
considered a scheduler failure.
"""

from __future__ import annotations

import json
import subprocess
import sys

from datetime import datetime
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

SRC_DIR = Path(__file__).resolve().parent

BASE_DIR = SRC_DIR.parent

# Global Learning Cycle replaces the 3-day-only monthly_retrainer for
# scheduled retraining. monthly_retrainer.py remains available for
# emergency single-horizon recovery but is no longer the scheduler path.
GLOBAL_CYCLE_PATH = (
    SRC_DIR / "global_learning_cycle.py"
)


NIGHTLY_PREDICTOR_PATH = (
    SRC_DIR / "nightly_predictor.py"
)

DAILY_ACTUAL_WRITER_PATH = (
    SRC_DIR / "daily_actual_writer.py"
)

WEEKLY_PREDICTION_JOB_PATH = (
    SRC_DIR / "weekly_prediction_job.py"
)

MONTHLY_PREDICTION_JOB_PATH = (
    SRC_DIR / "monthly_prediction_job.py"
)

STATE_DIR = (
    BASE_DIR
    / "processed"
    / "diagnostics"
    / "scheduler"
)

STATE_PATH = (
    STATE_DIR / "scheduler_state.json"
)

LOG_PATH = (
    STATE_DIR / "scheduler.log"
)


# ============================================================
# CONFIG
# ============================================================
#
# The global learning cycle is calendar-gated (1st of the month --
# see is_global_cycle_due()), not interval-gated, so there is no
# "days between runs" constant to configure here anymore.


# ============================================================
# LOGGING
# ============================================================

def log(message: str) -> None:

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().isoformat(
        timespec="seconds"
    )

    line = f"[{timestamp}] {message}"

    print(
        line,
        flush=True,
    )

    with LOG_PATH.open(
        "a",
        encoding="utf-8",
    ) as file:

        file.write(
            line + "\n"
        )


# ============================================================
# STATE
# ============================================================

def default_state() -> dict:

    return {

        # ----------------------------------------------------
        # Scheduler
        # ----------------------------------------------------

        "last_run": None,

        # IMPORTANT:
        # This is the timestamp used to determine whether
        # the global learning cycle is due.
        "last_completed": None,

        "last_promotion": None,

        "last_failure": None,

        "last_exit_code": None,

        "last_result": None,

        # ----------------------------------------------------
        # Nightly prediction
        # ----------------------------------------------------

        "last_prediction": None,

        "last_prediction_exit_code": None,

        "last_prediction_result": None,

        # ----------------------------------------------------
        # Daily actuals (previous day's real peak hour + segments)
        # ----------------------------------------------------

        "last_actuals": None,

        "last_actuals_exit_code": None,

        "last_actuals_result": None,

        # ----------------------------------------------------
        # Weekly total-consumption prediction (Shamsi Sat→Fri)
        # ----------------------------------------------------

        "last_weekly_prediction": None,

        "last_weekly_prediction_exit_code": None,

        "last_weekly_prediction_result": None,

        # ISO date (YYYY-MM-DD) of the week_start last successfully
        # predicted. Used for repeated-execution protection: if the
        # scheduler runs again on the same Saturday, skip re-work.
        "last_weekly_week_start": None,

        # ----------------------------------------------------
        # Monthly total-consumption prediction (Jalali / Shamsi month)
        # ----------------------------------------------------

        "last_monthly_prediction": None,

        "last_monthly_prediction_exit_code": None,

        "last_monthly_prediction_result": None,

        # ISO date (YYYY-MM-DD) of the month_start last successfully
        # predicted. Repeated runs on the same 1st are skipped.
        "last_monthly_month_start": None,

    }


def load_state() -> dict:

    if not STATE_PATH.exists():

        log(
            "No scheduler state file found."
        )

        return default_state()

    try:

        state = json.loads(
            STATE_PATH.read_text(
                encoding="utf-8"
            )
        )

        defaults = default_state()

        for key, value in defaults.items():

            state.setdefault(
                key,
                value,
            )

        return state

    except Exception as exc:

        log(
            "WARNING: Could not read scheduler "
            f"state: {exc}"
        )

        return default_state()


def save_state(
    state: dict,
) -> None:

    STATE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    STATE_PATH.write_text(
        json.dumps(
            state,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ============================================================
# GLOBAL LEARNING CYCLE CHECK
# ============================================================
#
# Calendar-based (Jalali / Shamsi), mirroring should_run_weekly_prediction /
# should_run_monthly_prediction: the global learning cycle (3-day +
# weekly + monthly retraining) is only attempted on the 1st of the
# **Jalali** month -- never on elapsed-day count. Whether the outcome
# is "promoted" or "rejected", that counts as this month's cycle
# being done (last_completed is stamped either way -- see run_cycle()),
# so the next attempt is the 1st of the following Jalali month. A "failed"
# outcome does NOT stamp last_completed, so it is retried on the very
# next scheduler run instead of waiting for next month.

def is_global_cycle_due(
    state: dict,
    today=None,
) -> bool:

    if today is None:
        today = datetime.now().date()

    from jalali_calendar import to_jalali, jalali_month_start

    # --------------------------------------------------------
    # ONLY THE 1ST OF THE JALALI (SHAMSI) MONTH
    # --------------------------------------------------------

    jy, jm, jd = to_jalali(today)
    if jd != 1:

        log(
            "Global learning cycle is NOT due "
            f"(not the 1st of the Jalali month; today is {jy}/{jm}/{jd})."
        )

        return False

    last_completed = state.get(
        "last_completed"
    )

    # --------------------------------------------------------
    # FIRST RUN
    # --------------------------------------------------------

    if not last_completed:

        log(
            "No previous completed global learning cycle found."
        )

        log(
            "Global learning cycle is DUE."
        )

        return True

    # --------------------------------------------------------
    # PARSE TIMESTAMP
    # --------------------------------------------------------

    try:

        last_time = datetime.fromisoformat(
            last_completed
        )

    except (ValueError, TypeError):

        log(
            "WARNING: Invalid last_completed "
            f"timestamp: {last_completed}"
        )

        log(
            "Global learning cycle will be treated as DUE."
        )

        return True

    log(
        "Last completed global learning cycle: "
        f"{last_completed}"
    )

    # --------------------------------------------------------
    # ALREADY DONE FOR THIS JALALI MONTH
    # --------------------------------------------------------

    last_date = last_time.date() if hasattr(last_time, "date") else last_time
    last_jy, last_jm, _ = to_jalali(last_date)

    if last_jy == jy and last_jm == jm:

        log(
            "Global learning cycle already completed "
            f"for this Jalali month ({jy}/{jm}); NOT due."
        )

        return False

    # --------------------------------------------------------
    # DUE -- NEW JALALI MONTH
    # --------------------------------------------------------

    log(
        f"Global learning cycle is DUE (new Jalali month {jy}/{jm})."
    )

    return True


# ============================================================
# RUN GLOBAL LEARNING CYCLE
# ============================================================

def run_global_cycle() -> tuple[str, int]:

    if not GLOBAL_CYCLE_PATH.exists():

        log(
            "ERROR: Global learning cycle script not found: "
            f"{GLOBAL_CYCLE_PATH}"
        )

        return (
            "failed",
            -1,
        )

    command = [
        sys.executable,
        str(GLOBAL_CYCLE_PATH),
        "--promote",
    ]

    log(
        "Starting GLOBAL LEARNING CYCLE "
        "(3-day + weekly + monthly)..."
    )

    log(
        "Command: "
        + " ".join(command)
    )

    try:

        result = subprocess.run(
            command,
            cwd=BASE_DIR,
            check=False,
        )

    except Exception as exc:

        log(
            "ERROR: Failed to start global learning cycle: "
            f"{exc}"
        )

        return (
            "failed",
            -1,
        )

    exit_code = result.returncode

    log(
        "Global learning cycle exited with code: "
        f"{exit_code}"
    )

    # --------------------------------------------------------
    # PROMOTED
    # --------------------------------------------------------

    if exit_code == 0:

        log(
            "Global Learning Cycle completed "
            "(independent per-horizon promotion applied)."
        )

        return (
            "promoted",
            exit_code,
        )

    # --------------------------------------------------------
    # REJECTED
    # --------------------------------------------------------

    if exit_code == 1:

        log(
            "Candidate was rejected."
        )

        log(
            "Production model was preserved."
        )

        return (
            "rejected",
            exit_code,
        )

    # --------------------------------------------------------
    # FAILURE
    # --------------------------------------------------------

    log(
        "Global Learning Cycle FAILED."
    )

    return (
        "failed",
        exit_code,
    )


# ============================================================
# RUN NIGHTLY PREDICTOR
# ============================================================

def run_nightly_predictor() -> tuple[str, int]:

    if not NIGHTLY_PREDICTOR_PATH.exists():

        log(
            "ERROR: Nightly predictor not found: "
            f"{NIGHTLY_PREDICTOR_PATH}"
        )

        return (
            "failed",
            -1,
        )

    command = [
        sys.executable,
        str(NIGHTLY_PREDICTOR_PATH),
    ]

    log(
        "Starting NIGHTLY PREDICTION..."
    )

    log(
        "Command: "
        + " ".join(command)
    )

    try:

        result = subprocess.run(
            command,
            cwd=BASE_DIR,
            check=False,
        )

    except Exception as exc:

        log(
            "ERROR: Failed to start nightly "
            f"predictor: {exc}"
        )

        return (
            "failed",
            -1,
        )

    exit_code = result.returncode

    log(
        "Nightly predictor exited with code: "
        f"{exit_code}"
    )

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    if exit_code == 0:

        log(
            "Nightly prediction completed."
        )

        return (
            "completed",
            exit_code,
        )

    # --------------------------------------------------------
    # FAILURE
    # --------------------------------------------------------

    log(
        "Nightly prediction FAILED."
    )

    return (
        "failed",
        exit_code,
    )


# ============================================================
# RUN DAILY ACTUALS WRITER
# ============================================================

def run_daily_actual_writer() -> tuple[str, int]:

    if not DAILY_ACTUAL_WRITER_PATH.exists():

        log(
            "ERROR: Daily actuals writer not found: "
            f"{DAILY_ACTUAL_WRITER_PATH}"
        )

        return (
            "failed",
            -1,
        )

    command = [
        sys.executable,
        str(DAILY_ACTUAL_WRITER_PATH),
    ]

    log(
        "Starting DAILY ACTUALS WRITER..."
    )

    log(
        "Command: "
        + " ".join(command)
    )

    try:

        result = subprocess.run(
            command,
            cwd=BASE_DIR,
            check=False,
        )

    except Exception as exc:

        log(
            "ERROR: Failed to start daily "
            f"actuals writer: {exc}"
        )

        return (
            "failed",
            -1,
        )

    exit_code = result.returncode

    log(
        "Daily actuals writer exited with code: "
        f"{exit_code}"
    )

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    if exit_code == 0:

        log(
            "Daily actuals writer completed."
        )

        return (
            "completed",
            exit_code,
        )

    # --------------------------------------------------------
    # FAILURE
    # --------------------------------------------------------

    log(
        "Daily actuals writer FAILED."
    )

    return (
        "failed",
        exit_code,
    )


# ============================================================
# WEEKLY / MONTHLY SCHEDULE DECISIONS
# ============================================================
#
# The systemd timer invokes scheduler.py every night. Weekly and
# monthly jobs are therefore gated by calendar day, not by a
# separate cron. Application timezone = whatever datetime.now()
# uses (same as the rest of this scheduler — do not hard-code UTC).
#
# Weekly (Shamsi):  run on the first day of the week = Saturday;
#                   target = that Sat → Fri week.
# Monthly (Shamsi): run on the first day of the Jalali month;
#                   target = that complete Jalali month.
#
# Repeated-execution protection: state stores the last successful
# target week_start / month_start. If the job already succeeded for
# that period, it is skipped. DB UNIQUE constraints provide a second
# line of defence (upsert, never duplicate rows).

def _today() -> "date":
    from datetime import date as _date
    return datetime.now().date()


def should_run_weekly_prediction(state: dict, today=None) -> tuple[bool, str | None]:
    """
    Returns (should_run, target_week_start_iso or None).

    True only when today is Saturday (first day of Shamsi week)
    AND we have not already successfully predicted that week.
    """
    from jalali_calendar import next_complete_week

    if today is None:
        today = _today()

    # First day of Shamsi week = Saturday (weekday 5 in Python)
    # if today.weekday() != 5:
    #     return False, None

    week_start, _week_end = next_complete_week(today)
    week_start_iso = week_start.isoformat()

    # last = state.get("last_weekly_week_start")
    # if last == week_start_iso:
    #     return False, week_start_iso

    return True, week_start_iso


def should_run_monthly_prediction(state: dict, today=None) -> tuple[bool, str | None]:
    """
    Returns (should_run, target_month_start_iso or None).

    True only when today is the 1st of a Jalali (Shamsi) month
    AND we have not already successfully predicted that month.
    """
    from jalali_calendar import (
        next_complete_jalali_month,
        to_jalali,
    )

    if today is None:
        today = _today()

    # First day of Jalali month only
    # _jy, _jm, jd = to_jalali(today)
    # if jd != 1:
    #     return False, None

    month_start, _month_end = next_complete_jalali_month(today)
    month_start_iso = month_start.isoformat()

    # last = state.get("last_monthly_month_start")
    # if last == month_start_iso:
    #     return False, month_start_iso

    return True, month_start_iso


# ============================================================
# RUN WEEKLY PREDICTION JOB
# ============================================================

def run_weekly_prediction_job() -> tuple[str, int]:

    if not WEEKLY_PREDICTION_JOB_PATH.exists():

        log(
            "ERROR: Weekly prediction job not found: "
            f"{WEEKLY_PREDICTION_JOB_PATH}"
        )

        return (
            "failed",
            -1,
        )

    command = [
        sys.executable,
        str(WEEKLY_PREDICTION_JOB_PATH),
    ]

    log(
        "Starting WEEKLY PREDICTION..."
    )

    log(
        "Command: "
        + " ".join(command)
    )

    try:

        result = subprocess.run(
            command,
            cwd=BASE_DIR,
            check=False,
        )

    except Exception as exc:

        log(
            "ERROR: Failed to start weekly "
            f"prediction job: {exc}"
        )

        return (
            "failed",
            -1,
        )

    exit_code = result.returncode

    log(
        "Weekly prediction job exited with code: "
        f"{exit_code}"
    )

    if exit_code == 0:

        log(
            "Weekly prediction completed."
        )

        return (
            "completed",
            exit_code,
        )

    log(
        "Weekly prediction FAILED."
    )

    return (
        "failed",
        exit_code,
    )


# ============================================================
# RUN MONTHLY PREDICTION JOB
# ============================================================

def run_monthly_prediction_job() -> tuple[str, int]:

    if not MONTHLY_PREDICTION_JOB_PATH.exists():

        log(
            "ERROR: Monthly prediction job not found: "
            f"{MONTHLY_PREDICTION_JOB_PATH}"
        )

        return (
            "failed",
            -1,
        )

    command = [
        sys.executable,
        str(MONTHLY_PREDICTION_JOB_PATH),
    ]

    log(
        "Starting MONTHLY PREDICTION..."
    )

    log(
        "Command: "
        + " ".join(command)
    )

    try:

        result = subprocess.run(
            command,
            cwd=BASE_DIR,
            check=False,
        )

    except Exception as exc:

        log(
            "ERROR: Failed to start monthly "
            f"prediction job: {exc}"
        )

        return (
            "failed",
            -1,
        )

    exit_code = result.returncode

    log(
        "Monthly prediction job exited with code: "
        f"{exit_code}"
    )

    if exit_code == 0:

        log(
            "Monthly prediction completed."
        )

        return (
            "completed",
            exit_code,
        )

    log(
        "Monthly prediction FAILED."
    )

    return (
        "failed",
        exit_code,
    )


# ============================================================
# ONE DAILY / NIGHTLY CYCLE
# ============================================================

def run_cycle() -> int:

    state = load_state()

    now = datetime.now().isoformat(
        timespec="seconds"
    )

    state["last_run"] = now

    log("=" * 70)

    log(
        "ELECTRICITY MODEL — NIGHTLY SCHEDULER"
    )

    log("=" * 70)

    # ========================================================
    # 1. DAILY ACTUALS (previous day's real peak hour + segments)
    #
    # Runs unconditionally, every cycle, before the monthly
    # global learning cycle / nightly prediction branching below. It has
    # nothing to do with the model, so it must never be skipped
    # just because the global learning cycle ran or was promoted.
    # ========================================================

    actuals_result, actuals_exit_code = (
        run_daily_actual_writer()
    )

    state["last_actuals"] = (
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    state["last_actuals_exit_code"] = (
        actuals_exit_code
    )

    state["last_actuals_result"] = (
        actuals_result
    )

    save_state(state)

    if actuals_result == "completed":

        log(
            "✅ Daily actuals finished."
        )

    else:

        log(
            "❌ Daily actuals failed. "
            "Continuing with the rest of the cycle anyway."
        )

    # ========================================================
    # 1b. WEEKLY TOTAL-CONSUMPTION PREDICTION (Shamsi week)
    #
    # Runs only on Saturday = first day of Shamsi week
    # (application local date). Independent of the global learning
    # cycle / nightly 3-day prediction. Upserts into weekly_predictions;
    # state tracks last_weekly_week_start so a second run the same day
    # does not re-execute.
    # ========================================================

    weekly_due, weekly_target = should_run_weekly_prediction(state)

    if weekly_due:

        log(
            f"📅 Weekly prediction is due "
            f"(target week_start={weekly_target})."
        )

        weekly_result, weekly_exit_code = (
            run_weekly_prediction_job()
        )

        state["last_weekly_prediction"] = (
            datetime.now().isoformat(timespec="seconds")
        )
        state["last_weekly_prediction_exit_code"] = weekly_exit_code
        state["last_weekly_prediction_result"] = weekly_result

        if weekly_result == "completed" and weekly_target is not None:
            state["last_weekly_week_start"] = weekly_target
            log(
                f"✅ Weekly prediction finished "
                f"(week_start={weekly_target})."
            )
        else:
            log(
                "❌ Weekly prediction failed. "
                "Continuing with the rest of the cycle."
            )

        save_state(state)

    else:

        if weekly_target is not None:
            log(
                f"Weekly prediction already completed for "
                f"week_start={weekly_target}; skipping."
            )
        else:
            log(
                "Weekly prediction not due today "
                "(not Saturday)."
            )


    monthly_due, monthly_target = should_run_monthly_prediction(state)

    if monthly_due:

        log(
            f"📅 Monthly prediction is due "
            f"(target month_start={monthly_target})."
        )

        monthly_result, monthly_exit_code = (
            run_monthly_prediction_job()
        )

        state["last_monthly_prediction"] = (
            datetime.now().isoformat(timespec="seconds")
        )
        state["last_monthly_prediction_exit_code"] = monthly_exit_code
        state["last_monthly_prediction_result"] = monthly_result

        if monthly_result == "completed" and monthly_target is not None:
            state["last_monthly_month_start"] = monthly_target
            log(
                f"✅ Monthly prediction finished "
                f"(month_start={monthly_target})."
            )
        else:
            log(
                "❌ Monthly prediction failed. "
                "Continuing with the rest of the cycle."
            )

        save_state(state)

    else:

        if monthly_target is not None:
            log(
                f"Monthly prediction already completed for "
                f"month_start={monthly_target}; skipping."
            )
        else:
            log(
                "Monthly prediction not due today "
                "(not the 1st of the Jalali month)."
            )

    # ========================================================
    # 2. CHECK GLOBAL LEARNING CYCLE
    # ========================================================

    global_cycle_due = is_global_cycle_due(
        state
    )

    # ========================================================
    # 3. GLOBAL LEARNING CYCLE
    # ========================================================

    if global_cycle_due:

        log(
            "🧠 Global learning cycle is due."
        )

        log(
            "Starting the global learning cycle FIRST."
        )

        result, exit_code = run_global_cycle()

        # ----------------------------------------------------
        # PROMOTED
        # ----------------------------------------------------

        if result == "promoted":

            completed_at = datetime.now().isoformat(
                timespec="seconds"
            )

            state["last_completed"] = (
                completed_at
            )

            state["last_promotion"] = (
                completed_at
            )

            state["last_exit_code"] = (
                exit_code
            )

            state["last_result"] = (
                "promoted"
            )

            state["last_failure"] = None

            save_state(state)

            log(
                "✅ Global learning cycle completed."
            )

            log(
                "Last completed global learning cycle updated to: "
                f"{completed_at}"
            )

            log(
                "Global learning cycle had priority."
            )

            log(
                "Nightly prediction will NOT run "
                "in this cycle."
            )

            return 0

        # ----------------------------------------------------
        # REJECTED
        # ----------------------------------------------------

        if result == "rejected":

            # The global learning cycle DID run successfully.  A rejected
            # candidate only means that the existing production model remains
            # better; it must not cause the scheduler to run the global
            # learning cycle again on every subsequent run.  Record the
            # completed cycle; the next attempt is gated to the 1st of
            # next month by is_global_cycle_due().
            completed_at = datetime.now().isoformat(
                timespec="seconds"
            )

            state["last_completed"] = completed_at
            state["last_exit_code"] = exit_code
            state["last_result"] = "rejected"
            state["last_failure"] = None

            save_state(state)

            log(
                "⚠️ Candidate rejected; existing production model kept."
            )

            log(
                "Global learning cycle completed at: "
                f"{completed_at}"
            )

            log(
                "Next global learning cycle check is on the "
                "1st of next month."
            )

            log(
                "Nightly prediction will continue."
            )

        # ----------------------------------------------------
        # FAILURE
        # ----------------------------------------------------

        elif result == "failed":

            state["last_exit_code"] = (
                exit_code
            )

            state["last_result"] = (
                "failed"
            )

            state["last_failure"] = (
                datetime.now().isoformat(
                    timespec="seconds"
                )
            )

            save_state(state)

            log(
                "❌ Global learning cycle failed."
            )

            log(
                "Nightly prediction will NOT run."
            )

            return 1

    # ========================================================
    # 4. NIGHTLY PREDICTION
    # ========================================================

    else:

        log(
            "Global learning cycle is not due."
        )

        log(
            "Starting nightly prediction..."
        )

    prediction_result, prediction_exit_code = (
        run_nightly_predictor()
    )

    # --------------------------------------------------------
    # SAVE PREDICTION STATE
    # --------------------------------------------------------

    state["last_prediction"] = (
        datetime.now().isoformat(
            timespec="seconds"
        )
    )

    state["last_prediction_exit_code"] = (
        prediction_exit_code
    )

    state["last_prediction_result"] = (
        prediction_result
    )

    save_state(state)

    # ========================================================
    # 5. PREDICTION SUCCESS
    # ========================================================

    if prediction_result == "completed":

        log(
            "✅ Nightly prediction finished."
        )

        return 0

    # ========================================================
    # 6. PREDICTION FAILURE
    # ========================================================

    log(
        "❌ Nightly prediction failed."
    )

    return 1


# ============================================================
# MAIN
# ============================================================

def main() -> None:

    try:

        exit_code = run_cycle()

    except Exception as exc:

        log(
            "FATAL: Scheduler crashed: "
            f"{exc}"
        )

        exit_code = 1

    sys.exit(
        exit_code
    )


if __name__ == "__main__":

    main()