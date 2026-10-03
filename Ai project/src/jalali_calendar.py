"""
jalali_calendar.py

Pure-Python Jalali (Shamsi / Solar Hijri) calendar helpers.
No external dependency.

Week: Saturday → Friday (official Iranian week).
Month: full Jalali month (1 Farvardin … 29/30/31 of the month).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Tuple


# ---------------------------------------------------------------------------
# Core conversion (standard algorithm)
# ---------------------------------------------------------------------------

def gregorian_to_jalali(gy: int, gm: int, gd: int) -> Tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    if gy > 1600:
        jy = 979
        gy -= 1600
    else:
        jy = 0
        gy -= 621
    gy2 = gy + 1 if gm > 2 else gy
    days = (365 * gy) + ((gy2 + 3) // 4) - ((gy2 + 99) // 100) + ((gy2 + 399) // 400) - 80 + gd + g_d_m[gm - 1]
    jy += 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm = 1 + days // 31
        jd = 1 + days % 31
    else:
        jm = 7 + (days - 186) // 30
        jd = 1 + (days - 186) % 30
    return jy, jm, jd


def jalali_to_gregorian(jy: int, jm: int, jd: int) -> Tuple[int, int, int]:
    if jy > 979:
        gy = 1600
        jy -= 979
    else:
        gy = 621
    days = (365 * jy) + ((jy // 33) * 8) + (((jy % 33) + 3) // 4) + 78 + jd
    if jm < 7:
        days += (jm - 1) * 31
    else:
        days += ((jm - 7) * 30) + 186
    gy += 400 * (days // 146097)
    days %= 146097
    if days > 36524:
        days -= 1
        gy += 100 * (days // 36524)
        days %= 36524
        if days >= 365:
            days += 1
    gy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        gy += (days - 1) // 365
        days = (days - 1) % 365
    gd = days + 1
    sal_a = [0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if (gy % 4 == 0 and gy % 100 != 0) or (gy % 400 == 0):
        sal_a[2] = 29
    gm = 1
    while gm < 13 and gd > sal_a[gm]:
        gd -= sal_a[gm]
        gm += 1
    return gy, gm, gd


def to_jalali(d: date) -> Tuple[int, int, int]:
    return gregorian_to_jalali(d.year, d.month, d.day)


def from_jalali(jy: int, jm: int, jd: int) -> date:
    gy, gm, gd = jalali_to_gregorian(jy, jm, jd)
    return date(gy, gm, gd)


# ---------------------------------------------------------------------------
# Jalali month helpers
# ---------------------------------------------------------------------------

def jalali_month_start(d: date) -> date:
    """First day (1st) of the Jalali month that contains d."""
    jy, jm, _ = to_jalali(d)
    return from_jalali(jy, jm, 1)


def jalali_month_end(d: date) -> date:
    """Last day of the Jalali month that contains d."""
    jy, jm, _ = to_jalali(d)
    # next month 1st − 1 day
    if jm == 12:
        next_start = from_jalali(jy + 1, 1, 1)
    else:
        next_start = from_jalali(jy, jm + 1, 1)
    return next_start - timedelta(days=1)


def next_complete_jalali_month(as_of: date) -> Tuple[date, date]:
    """
    Return (month_start, month_end) for the next complete Jalali month
    that has not yet started (or the current one if as_of is exactly day 1).

    Semantics mirror the original Gregorian helper:
      - If as_of is the 1st of a Jalali month → that month.
      - Otherwise → the following Jalali month.
    """
    ms = jalali_month_start(as_of)
    if as_of == ms:
        return ms, jalali_month_end(as_of)
    # advance to next Jalali month
    jy, jm, _ = to_jalali(as_of)
    if jm == 12:
        nxt = from_jalali(jy + 1, 1, 1)
    else:
        nxt = from_jalali(jy, jm + 1, 1)
    return nxt, jalali_month_end(nxt)


def iter_complete_jalali_months(first_day: date, last_day: date) -> list[Tuple[date, date]]:
    """Complete Jalali months fully contained in [first_day, last_day]."""
    months: list[Tuple[date, date]] = []
    cur = jalali_month_start(first_day)
    if cur < first_day:
        jy, jm, _ = to_jalali(cur)
        if jm == 12:
            cur = from_jalali(jy + 1, 1, 1)
        else:
            cur = from_jalali(jy, jm + 1, 1)
    while True:
        end = jalali_month_end(cur)
        if end > last_day:
            break
        months.append((cur, end))
        jy, jm, _ = to_jalali(cur)
        if jm == 12:
            cur = from_jalali(jy + 1, 1, 1)
        else:
            cur = from_jalali(jy, jm + 1, 1)
    return months


# ---------------------------------------------------------------------------
# Iranian week helpers (Saturday → Friday) – already Shamsi week
# ---------------------------------------------------------------------------

def saturday_of_week(d: date) -> date:
    """Saturday that starts the Sat–Fri week containing d."""
    offset = (d.weekday() - 5) % 7
    return d - timedelta(days=offset)


def friday_of_week(d: date) -> date:
    return saturday_of_week(d) + timedelta(days=6)


def next_complete_week(as_of: date) -> Tuple[date, date]:
    """
    Next complete Saturday→Friday week.
    If as_of is Saturday → that week; otherwise the following week.
    """
    sat = saturday_of_week(as_of)
    if as_of == sat:
        return sat, sat + timedelta(days=6)
    next_sat = sat + timedelta(days=7)
    return next_sat, next_sat + timedelta(days=6)


def iter_complete_weeks(first_day: date, last_day: date) -> list[Tuple[date, date]]:
    weeks: list[Tuple[date, date]] = []
    cur = saturday_of_week(first_day)
    if cur < first_day:
        cur = cur + timedelta(days=7)
    while True:
        end = cur + timedelta(days=6)
        if end > last_day:
            break
        weeks.append((cur, end))
        cur = cur + timedelta(days=7)
    return weeks
