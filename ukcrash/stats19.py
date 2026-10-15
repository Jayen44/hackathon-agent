"""UK crash foundation: DfT STATS19 police-reported injury collisions -> a compact profile.

The profile (crash-type mix, severity, speed limit, light, surface, urban/rural) is what
synthetic.py samples from, so our made-up demo crashes look like real UK crashes.

    python -m ukcrash.stats19 --year 2024     # downloads ~60 MB to data/stats19/, writes ukcrash/profile_2024.json

Source: Department for Transport, Road Safety Data (STATS19), data.dft.gov.uk.
Contains public sector information licensed under the Open Government Licence v3.0.
Codes: rOpenSci stats19 schema (data-raw/stats19_schema.csv), which mirrors the DfT data guide.
STATS19 covers injury collisions reported to the police only: no damage-only crashes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://data.dft.gov.uk/road-accidents-safety-data/dft-road-casualty-statistics-{table}-{year}.csv"
DATA_DIR = Path("data/stats19")
PROFILE_DIR = Path(__file__).parent

SEVERITY = {1: "Fatal", 2: "Serious", 3: "Slight"}
CAR_TYPES = {8, 9}  # 8 Taxi/Private hire car, 9 Car: the robotaxi analogue
GOING_AHEAD = 19
SLOWING_OR_WAITING = {3, 4}  # 3 Waiting to go ahead, 4 Slowing or stopping
LANE_CHANGE_OR_OVERTAKE = {11, 12, 13, 15}  # changing lane L/R, overtaking moving vehicle offside/nearside
IMPACT_FRONT, IMPACT_BACK = 1, 2
LIGHT = {1: "daylight", 4: "dark_lit", 5: "dark_unlit", 6: "dark_unlit", 7: "dark_unlit"}
SURFACE = {1: "dry", 2: "wet", 3: "snow_ice", 4: "snow_ice"}
URBAN = {1: "urban", 2: "rural"}


def download(year: int, dest: Path = DATA_DIR) -> dict[str, Path]:
    dest.mkdir(parents=True, exist_ok=True)
    out = {}
    for table in ("collision", "vehicle"):
        path = dest / f"{table}-{year}.csv"
        if not path.exists():
            r = requests.get(BASE_URL.format(table=table, year=year), timeout=120)
            r.raise_for_status()
            path.write_bytes(r.content)
        out[table] = path
    return out


def classify(vehicles: pd.DataFrame) -> pd.Series:
    """crash_type per two-vehicle collision with a car/taxi as the ego (the vehicle whose front hits).

    lead_vehicle_decel: ego going ahead, front impact; other slowing/waiting/going ahead, hit in the back.
    cut_in:             ego going ahead, front impact; other changing lane or overtaking.
    Everything else is "other". R157 covers the first two (plus cut-out, not separable in STATS19).
    """
    two = vehicles.groupby("collision_index").filter(lambda g: len(g) == 2)
    types = {}
    for idx, g in two.groupby("collision_index"):
        a, b = g.iloc[0], g.iloc[1]
        types[idx] = "other"
        for ego, other in ((a, b), (b, a)):
            if not (ego.vehicle_type in CAR_TYPES and ego.vehicle_manoeuvre == GOING_AHEAD
                    and ego.first_point_of_impact == IMPACT_FRONT):
                continue
            if other.vehicle_manoeuvre in LANE_CHANGE_OR_OVERTAKE:
                types[idx] = "cut_in"
            elif (other.vehicle_manoeuvre in SLOWING_OR_WAITING | {GOING_AHEAD}
                  and other.first_point_of_impact == IMPACT_BACK):
                types[idx] = "lead_vehicle_decel"
            if types[idx] != "other":
                break
    return pd.Series(types, name="crash_type")


def _shares(s: pd.Series) -> dict[str, float]:
    s = s.dropna()
    return {str(k): round(v, 4) for k, v in s.value_counts(normalize=True).sort_index().items()}


def build_profile(collisions: pd.DataFrame, vehicles: pd.DataFrame, year: int) -> dict:
    ct = classify(vehicles)
    c = collisions.set_index("collision_index").join(ct, how="inner")
    c = c[c.speed_limit > 0]
    profile = {
        "source": "DfT STATS19 Road Safety Data (OGL v3.0), police-reported injury collisions",
        "year": year,
        "universe": "two-vehicle collisions with a car or taxi as one vehicle",
        "n_collisions_total": int(len(collisions)),
        "crash_types": {},
    }
    for name, g in c.groupby("crash_type"):
        profile["crash_types"][name] = {
            "n": int(len(g)),
            "severity": _shares(g.collision_severity.map(SEVERITY)),
            "speed_limit_mph": _shares(g.speed_limit.astype(int)),
            "light": _shares(g.light_conditions.map(LIGHT)),
            "surface": _shares(g.road_surface_conditions.map(SURFACE)),
            "area": _shares(g.urban_or_rural_area.map(URBAN)),
        }
    return profile


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--year", type=int, default=2024)
    a = p.parse_args()
    files = download(a.year)
    collisions = pd.read_csv(files["collision"], low_memory=False)
    vehicles = pd.read_csv(files["vehicle"], low_memory=False,
                           usecols=["collision_index", "vehicle_type", "vehicle_manoeuvre", "first_point_of_impact"])
    profile = build_profile(collisions, vehicles, a.year)
    out = PROFILE_DIR / f"profile_{a.year}.json"
    out.write_text(json.dumps(profile, indent=2) + "\n")
    print(f"wrote {out}: " + ", ".join(f"{k} {v['n']}" for k, v in profile["crash_types"].items()))


if __name__ == "__main__":
    main()
