"""
schedule_install.py

Install a daily OS-level job that runs scheduler.py at 00:10 local time
(requested as 24:10 — i.e. ten minutes after midnight).

Windows : Task Scheduler (schtasks)
Linux   : user crontab entry (fallback: writes a systemd user unit pair
          when systemd --user is available)
macOS   : user crontab (same as Linux crontab path)
"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
SCHEDULER_SCRIPT = SRC_DIR / "scheduler.py"

# 24:10 → 00:10 next calendar day boundary (daily at 00:10)
SCHEDULE_HOUR = 0
SCHEDULE_MINUTE = 10

TASK_NAME = "AIProject_DailyScheduler"
CRON_TAG = "# AIProject_DailyScheduler"


def _python_exe() -> str:
    return sys.executable


def install_daily_scheduler() -> dict[str, Any]:
    """
    Register daily run of scheduler.py at 00:10 local time.

    Returns a result dict with ok/platform/details/notes.
    """
    if not SCHEDULER_SCRIPT.exists():
        return {
            "ok": False,
            "error": f"scheduler.py not found: {SCHEDULER_SCRIPT}",
            "platform": platform.system(),
        }

    system = platform.system().lower()
    if system == "windows":
        return _install_windows()
    if system in ("linux", "darwin"):
        return _install_posix(system)
    return {
        "ok": False,
        "error": f"Unsupported platform for auto-schedule: {system}",
        "platform": system,
    }


def _install_windows() -> dict[str, Any]:
    """schtasks /Create daily at 00:10."""
    py = _python_exe()
    # Quote paths for cmd
    tr = f'"{py}" "{SCHEDULER_SCRIPT}"'
    # /ST HH:MM  /SC DAILY  /F force replace  /RL LIMITED (current user)
    cmd = [
        "schtasks",
        "/Create",
        "/TN", TASK_NAME,
        "/TR", tr,
        "/SC", "DAILY",
        "/ST", f"{SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}",
        "/F",
        "/RL", "LIMITED",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "platform": "Windows",
            "error": "schtasks not found — run Setup as a normal Windows user with Task Scheduler available.",
        }

    ok = result.returncode == 0
    notes = [
        f"Windows Task Scheduler task: {TASK_NAME}",
        f"Daily at {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d} local time",
        f"Command: {tr}",
    ]
    if result.stdout:
        notes.append(result.stdout.strip())
    if result.stderr:
        notes.append(result.stderr.strip())
    return {
        "ok": ok,
        "platform": "Windows",
        "method": "schtasks",
        "task_name": TASK_NAME,
        "time": f"{SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}",
        "command": tr,
        "returncode": result.returncode,
        "notes": notes,
        "error": None if ok else (result.stderr or result.stdout or f"exit {result.returncode}"),
    }


def _cron_line() -> str:
    py = _python_exe()
    # cd to src so relative processed/ paths inside scheduler resolve via BASE_DIR
    return (
        f"{SCHEDULE_MINUTE} {SCHEDULE_HOUR} * * * "
        f"cd \"{SRC_DIR}\" && \"{py}\" \"{SCHEDULER_SCRIPT}\" "
        f">> \"{PROJECT_ROOT / 'processed' / 'diagnostics' / 'scheduler' / 'cron.log'}\" 2>&1 "
        f"{CRON_TAG}"
    )


def _install_posix(system: str) -> dict[str, Any]:
    """Install via crontab; optionally also write systemd user units on Linux."""
    notes: list[str] = []
    line = _cron_line()
    cron_ok = False
    cron_error = None

    if shutil.which("crontab"):
        try:
            current = subprocess.run(
                ["crontab", "-l"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            existing = current.stdout if current.returncode == 0 else ""
            # Drop any previous tagged lines
            kept = [
                ln for ln in existing.splitlines()
                if CRON_TAG not in ln and ln.strip() != ""
            ]
            kept.append(line)
            new_cron = "\n".join(kept) + "\n"
            proc = subprocess.run(
                ["crontab", "-"],
                input=new_cron,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            cron_ok = proc.returncode == 0
            if not cron_ok:
                cron_error = proc.stderr or proc.stdout or f"crontab exit {proc.returncode}"
            else:
                notes.append(f"crontab installed: {line}")
        except Exception as exc:
            cron_error = str(exc)
    else:
        cron_error = "crontab command not found"

    systemd_notes: list[str] = []
    systemd_ok = False
    if system == "linux":
        systemd_ok, systemd_notes = _try_systemd_user()
        notes.extend(systemd_notes)

    ok = cron_ok or systemd_ok
    return {
        "ok": ok,
        "platform": system,
        "method": "crontab" if cron_ok else ("systemd-user" if systemd_ok else "none"),
        "time": f"{SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}",
        "cron_line": line,
        "cron_ok": cron_ok,
        "systemd_ok": systemd_ok,
        "notes": notes,
        "error": None if ok else (cron_error or "failed to install schedule"),
    }


def _try_systemd_user() -> tuple[bool, list[str]]:
    """Write and enable a systemd --user timer at 00:10 daily."""
    notes: list[str] = []
    if not shutil.which("systemctl"):
        return False, ["systemctl not available; skipped systemd user timer"]

    unit_dir = Path.home() / ".config" / "systemd" / "user"
    try:
        unit_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return False, [f"Cannot create systemd user dir: {exc}"]

    py = _python_exe()
    service = unit_dir / "ai-project-scheduler.service"
    timer = unit_dir / "ai-project-scheduler.timer"

    service.write_text(
        "\n".join([
            "[Unit]",
            "Description=AI Project daily scheduler",
            "",
            "[Service]",
            "Type=oneshot",
            f"WorkingDirectory={SRC_DIR}",
            f"ExecStart={py} {SCHEDULER_SCRIPT}",
            "",
        ]) + "\n",
        encoding="utf-8",
    )
    timer.write_text(
        "\n".join([
            "[Unit]",
            "Description=Run AI Project scheduler daily at 00:10",
            "",
            "[Timer]",
            f"OnCalendar=*-*-* {SCHEDULE_HOUR:02d}:{SCHEDULE_MINUTE:02d}:00",
            "Persistent=true",
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]) + "\n",
        encoding="utf-8",
    )
    notes.append(f"Wrote {service}")
    notes.append(f"Wrote {timer}")

    try:
        subprocess.run(
            ["systemctl", "--user", "daemon-reload"],
            check=False,
            capture_output=True,
        )
        en = subprocess.run(
            ["systemctl", "--user", "enable", "--now", "ai-project-scheduler.timer"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if en.returncode != 0:
            notes.append(en.stderr or en.stdout or f"enable exit {en.returncode}")
            return False, notes
        notes.append("systemd --user timer enabled: ai-project-scheduler.timer (daily 00:10)")
        return True, notes
    except Exception as exc:
        notes.append(str(exc))
        return False, notes
