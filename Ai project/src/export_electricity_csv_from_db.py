"""
Exports raw device history from the database into
data/electricity_data.csv, in exactly the shape the existing ML
pipeline already expects (device_id, timestamp, consumption_kwh).

Why this exists (and isn't just "read the DB directly everywhere"):
    For now, training (build_full_daily_dataset.py etc.) still reads
    data/electricity_data.csv — that script and everything after it
    is unchanged. This script is the one new step in front of it:
    instead of you exporting/maintaining that CSV by hand, Python
    regenerates it straight from the database each time you run this.

    Later, once the DB pipeline is fully wired up (nightly job etc.),
    this same script is what keeps producing that CSV automatically
    — nothing downstream has to change.

Usage:
    DB_HOST=... DB_DATABASE=... DB_USERNAME=... DB_PASSWORD=... \\
        python export_electricity_csv_from_db.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database.connection import Database
from database.repository import get_all_history
from database import schema


def separator(title: str) -> None:
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def main() -> Path:
    start_time = time.time()

    base_dir = Path(__file__).resolve().parent.parent
    output_path = base_dir / "data" / "electricity_data.csv"
    output_path.parent.mkdir(exist_ok=True, parents=True)

    separator("CONNECT + VALIDATE SCHEMA")
    db = Database()

    with db.connect() as conn:
        schema.validate_required_tables(conn)

        separator("EXPORT RAW HISTORY FROM DATABASE")
        raw_df = get_all_history(conn)

    if raw_df.empty:
        raise RuntimeError(
            "No device_data rows found in the database — "
            "nothing to export."
        )

    print("Total rows:", len(raw_df))
    print("Total devices:", raw_df["device_id"].nunique())

    raw_df.to_csv(output_path, index=False)

    print("Saved:", output_path)

    elapsed = time.time() - start_time
    print(f"Time: {elapsed:.1f}s")

    separator("EXPORT COMPLETE")

    return output_path


if __name__ == "__main__":
    main()
