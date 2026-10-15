"""Full crash bundles from Antonio's synthetic UK crashes (ukcrash/), for end-to-end portfolio runs.

    python -m insurance.synth_bundles --n 20 --seed 7 [--out DIR]

GROUNDED in ukcrash/ (real UK STATS19 mix): crash type, severity, speed limit, light, surface.
MADE UP here (every bundle has "synthetic": true): the headway/gap, the lead vehicle's braking, the cut-in
timing, how late the system detected the hazard, and the evidence available. Friction by surface is textbook
physics (dry 0.7, wet 0.4, snow/ice 0.2): see docs/verification.md "Knowledge".
We read ukcrash/ and never edit it.
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass
from pathlib import Path

from finance.recovery import engagement_code, odd_code
from insurance.bundle import CrashBundle, load_bundle
from ukcrash.synthetic import SyntheticCrash, generate

MPH = 0.44704
FRICTION = {"dry": 0.7, "wet": 0.4, "snow_ice": 0.2}
WEATHER = {"dry": "dry", "wet": "rain", "snow_ice": "snow_ice"}
KIND = {"lead_vehicle_decel": "lead_braking", "cut_in": "cut_in"}
T_CRASH = 1000.0


@dataclass(frozen=True)
class SynthCase:
    bundle: CrashBundle
    reproduced: bool          # made-up flag from the synthetic generator; passed to the bridge
    source: SyntheticCrash


def to_bundle_dict(sc: SyntheticCrash, rng: random.Random) -> dict:
    f = sc.facts
    v = sc.speed_limit_mph * MPH * rng.uniform(0.8, 1.0)           # travelling a little under the limit
    kind = KIND.get(sc.crash_type, "constant_hazard")
    t_start = T_CRASH - 3.0
    conflict = {"hazard_id": "h1", "kind": kind, "crash_type": sc.crash_type, "t_start": t_start,
                "ego_speed_mps": round(v, 2), "friction_mu": FRICTION.get(sc.surface, 0.7)}
    if kind == "lead_braking":
        conflict.update(gap_m=round(v * rng.uniform(0.8, 2.5), 1), hazard_speed_mps=round(v, 2),
                        hazard_decel_mps2=round(rng.uniform(4.0, 8.0), 1))
    else:   # cut_in
        conflict.update(gap_m=round(v * rng.uniform(0.5, 2.0), 1), hazard_speed_mps=round(v * rng.uniform(0.5, 0.9), 2),
                        t_in_path_s=round(rng.uniform(0.3, 1.5), 2))
    # finance/ owns the codes (UK codes, with legacy SGO strings normalised): use its normalisers, never string compares.
    engaged_verified = engagement_code(f.engagement_status) == "engaged_verified"
    return {
        "schema_version": "0.1", "case_id": f.claim_id, "synthetic": True, "t_crash": T_CRASH, "jurisdiction": "UK",
        "vehicle": {
            "software_version": "synthetic-1.0", "approved_software": ["synthetic-1.0"], "occupant": "none",
            "software_verified": rng.random() < 0.8,   # made up: 80% of claims have the software state confirmed
            "mode_events": [{"t": 0.0, "mode": "automated"}],
            "odd_inside": True if odd_code(f.within_odd) == "inside" else None,
            "control_inputs": [{"t": T_CRASH - 1.0, "source": "system", "brake": 0.9}],
        },
        "perception": {"sensors": ["camera", "lidar", "radar"], "decision_log_present": True,
                       "objects": [{"id": "h1", "cls": "vehicle",
                                    "first_detected_t": round(t_start + rng.uniform(0.2, 2.5), 2), "confidence": 0.9}]},
        "external": {"cctv": ["street_cam"] if rng.random() < 0.6 else [], "witnesses": rng.randint(0, 3),
                     "police_report": rng.random() < 0.8, "weather": WEATHER.get(sc.surface, "unknown"),
                     "lighting": sc.light},
        # "Alleged Engaged" cannot be represented as a trusted mode log: model it as a log gap over the crash, which
        # the integrity check blocks (the right outcome: engagement unverified -> pull the logs).
        "integrity": {"hashes_present": True, "chain_of_custody": True, "clock_offsets_s": {"vehicle_log": 0.0},
                      "log_gaps": [] if engaged_verified else [[T_CRASH - 30.0, T_CRASH + 5.0]],
                      "tamper_flag": False},
        "conflict": conflict,
        "outcome": {"collided": True, "injury_severity": f.injury_severity, "paid_claim_gbp": f.paid_claim_gbp},
    }


def generate_cases(n: int, seed: int = 7, crash_types: tuple[str, ...] = ("lead_vehicle_decel", "cut_in")) -> list[SynthCase]:
    rng = random.Random(f"bundles-{seed}")
    return [SynthCase(load_bundle(to_bundle_dict(sc, rng)), sc.facts.reproduced, sc)
            for sc in generate(n, seed, crash_types=crash_types)]


def main(argv: list[str] | None = None) -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--n", type=int, default=20)
    a.add_argument("--seed", type=int, default=7)
    a.add_argument("--out", type=Path, default=None, help="write one JSON file per bundle here")
    args = a.parse_args(argv)
    rng = random.Random(f"bundles-{args.seed}")
    dicts = [to_bundle_dict(sc, rng) for sc in generate(args.n, args.seed)]
    for d in dicts:
        load_bundle(d)                                   # fail loudly if we ever emit an invalid bundle
    if args.out:
        args.out.mkdir(parents=True, exist_ok=True)
        for d in dicts:
            (args.out / f"{d['case_id']}.json").write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
        print(f"wrote {len(dicts)} bundles to {args.out}")
    else:
        print(json.dumps(dicts[:2], indent=2), f"\n... {len(dicts)} bundles (use --out DIR to write them)")


if __name__ == "__main__":
    main()
