from __future__ import annotations

from pathlib import Path

import pandas as pd

PROFILES = [
    {
        "client_name": "Aanya Sharma",
        "preferred_airline": "AI",
        "meal_preference": "vegetarian",
        "visa_country_held": "India",
        "visa_expiration_date": "2027-03-15",
        "approved_cabin_class": "business",
        "timing_preference": "morning",
    },
    {
        "client_name": "Marcus Bellweather",
        "preferred_airline": "UA",
        "meal_preference": "standard",
        "visa_country_held": "USA",
        "visa_expiration_date": "2028-07-22",
        "approved_cabin_class": "first",
        "timing_preference": "redeye",
    },
    {
        "client_name": "Priya Nandakumar",
        "preferred_airline": "6E",
        "meal_preference": "vegan",
        "visa_country_held": "India",
        "visa_expiration_date": "2026-11-30",
        "approved_cabin_class": "economy",
        "timing_preference": "midday",
    },
    {
        "client_name": "Otto Freiberg",
        "preferred_airline": "LH",
        "meal_preference": "standard",
        "visa_country_held": "Schengen",
        "visa_expiration_date": "2029-05-10",
        "approved_cabin_class": "business",
        "timing_preference": "morning",
    },
    {
        "client_name": "Fatima Al-Rashidi",
        "preferred_airline": "EK",
        "meal_preference": "halal",
        "visa_country_held": "UAE",
        "visa_expiration_date": "2030-01-18",
        "approved_cabin_class": "first",
        "timing_preference": "evening",
    },
    {
        "client_name": "Cassandra Whitmore",
        "preferred_airline": "BA",
        "meal_preference": "gluten-free",
        "visa_country_held": "UK",
        "visa_expiration_date": "2027-09-04",
        "approved_cabin_class": "premium_economy",
        "timing_preference": "morning",
    },
    {
        "client_name": "Yusuf Tanaka",
        "preferred_airline": "SQ",
        "meal_preference": "standard",
        "visa_country_held": "Singapore",
        "visa_expiration_date": "2028-12-01",
        "approved_cabin_class": "business",
        "timing_preference": "redeye",
    },
    {
        "client_name": "Brigitte Moreau",
        "preferred_airline": "AF",
        "meal_preference": "vegan",
        "visa_country_held": "Schengen",
        "visa_expiration_date": "2026-06-20",
        "approved_cabin_class": "economy",
        "timing_preference": "midday",
    },
    {
        "client_name": "Devraj Pillai",
        "preferred_airline": "AI",
        "meal_preference": "vegetarian",
        "visa_country_held": "India",
        "visa_expiration_date": "2029-08-14",
        "approved_cabin_class": "premium_economy",
        "timing_preference": "morning",
    },
    {
        "client_name": "Eleanor Voss",
        "preferred_airline": "DL",
        "meal_preference": "kosher",
        "visa_country_held": "USA",
        "visa_expiration_date": "2027-02-28",
        "approved_cabin_class": "business",
        "timing_preference": "evening",
    },
    {
        "client_name": "Tariq Okonkwo",
        "preferred_airline": "EK",
        "meal_preference": "halal",
        "visa_country_held": "UAE",
        "visa_expiration_date": "2030-10-05",
        "approved_cabin_class": "economy",
        "timing_preference": "midday",
    },
    {
        "client_name": "Seren Llewellyn",
        "preferred_airline": "BA",
        "meal_preference": "standard",
        "visa_country_held": "UK",
        "visa_expiration_date": "2028-04-17",
        "approved_cabin_class": "first",
        "timing_preference": "morning",
    },
]

def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "data"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "traveler_profiles.xlsx"
    df = pd.DataFrame(PROFILES)
    df.to_excel(out_path, index=False, engine="openpyxl")
    print(f"Wrote 12 profiles to data/traveler_profiles.xlsx")

if __name__ == "__main__":
    main()
