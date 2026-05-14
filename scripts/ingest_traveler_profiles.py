from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.travel_storage import DEFAULT_DB_PATH, TravelStorage

REQUIRED_COLUMNS = [
    "client_name",
    "preferred_airline",
    "meal_preference",
    "visa_country_held",
    "visa_expiration_date",
    "approved_cabin_class",
    "timing_preference",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", nargs="?", default="data/traveler_profiles.xlsx")
    args = parser.parse_args()

    df = pd.read_excel(args.path, engine="openpyxl")

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        print(f"Error: missing required columns: {missing}", file=sys.stderr)
        sys.exit(1)

    storage = TravelStorage(DEFAULT_DB_PATH)
    count = 0

    for _, row in df.iterrows():
        name = row["client_name"]
        if not isinstance(name, str) or not name.strip():
            continue
        if isinstance(name, float) and math.isnan(name):
            continue

        profile: dict = {}
        for col in REQUIRED_COLUMNS:
            val = row[col]
            if hasattr(val, "item"):
                val = val.item()
            if isinstance(val, float) and math.isnan(val):
                val = None
            # Convert pandas Timestamp to YYYY-MM-DD string
            if hasattr(val, "strftime"):
                val = val.strftime("%Y-%m-%d")
            profile[col] = val

        storage.upsert_traveler_profile(profile)
        count += 1

    print(f"Ingested {count} profile(s) into {DEFAULT_DB_PATH}")


if __name__ == "__main__":
    main()
