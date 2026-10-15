"""Made-up robotaxi crashes for the demo, sampled from the real UK STATS19 profile.

Grounded in UK data: crash type mix, severity, speed limit, light, surface, urban/rural.
Made up (labelled SYNTHETIC on every record): the AV facts (engagement, ODD, reproduced)
and the amount the insurer paid, which is drawn inside the sourced range for the severity.
The careful-driver results (P(avoid)) are NOT generated here: they come from sim/ + montecarlo/.

    python -m ukcrash.synthetic --n 20 --seed 7 > data/synthetic_crashes.json
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path

from finance import tables
from finance.recovery import ClaimFacts

PROFILE = Path(__file__).parent / "profile_2024.json"

# Demo knobs for the made-up AV facts (UK codes, see finance.recovery). Not data: change them to stage different stories.
DEMO_KNOBS = {
    "p_engagement_verified": 0.8,   # else "Alleged Engaged"
    "p_within_odd": 0.85,           # else "Unknown, see Narrative"
    "p_reproduced": 0.9,
    "third_party_share": None,      # injured party's contributory negligence; None = not assessed
}


@dataclass
class SyntheticCrash:
    synthetic: bool
    crash_type: str
    stats19_severity: str
    speed_limit_mph: int
    light: str
    surface: str
    area: str
    facts: ClaimFacts

    def to_dict(self) -> dict:
        return asdict(self)


def _pick(rng: random.Random, shares: dict[str, float]) -> str:
    return rng.choices(list(shares), weights=list(shares.values()))[0]


def load_profile(path: Path = PROFILE) -> dict:
    return json.loads(path.read_text())


def generate(n: int, seed: int = 0, profile: dict | None = None,
             crash_types: tuple[str, ...] = ("lead_vehicle_decel", "cut_in"),
             knobs: dict | None = None) -> list[SyntheticCrash]:
    """n crashes, crash type in proportion to its real UK frequency. Same seed, same crashes."""
    profile = profile or load_profile()
    knobs = {**DEMO_KNOBS, **(knobs or {})}
    rng = random.Random(seed)
    types = {t: profile["crash_types"][t] for t in crash_types}
    out = []
    for i in range(n):
        ct = rng.choices(list(types), weights=[t["n"] for t in types.values()])[0]
        p = types[ct]
        sev = _pick(rng, p["severity"])
        row = tables.claim_value_for_severity(sev)  # STATS19 severity is the UK key
        paid = round(rng.uniform(row.low, row.high), -1) if row.priced else None
        facts = ClaimFacts(
            claim_id=f"SYN-{seed}-{i:03d}",
            crash_type=ct,
            injury_severity=sev,
            engagement_status="engaged_verified" if rng.random() < knobs["p_engagement_verified"] else "engaged_alleged",
            within_odd="inside" if rng.random() < knobs["p_within_odd"] else "unknown",
            reproduced=rng.random() < knobs["p_reproduced"],
            third_party_share=knobs["third_party_share"],
            paid_claim_gbp=paid,
        )
        out.append(SyntheticCrash(True, ct, sev, int(_pick(rng, p["speed_limit_mph"])),
                                  _pick(rng, p["light"]), _pick(rng, p["surface"]), _pick(rng, p["area"]), facts))
    return out


def main() -> None:
    a = argparse.ArgumentParser()
    a.add_argument("--n", type=int, default=20)
    a.add_argument("--seed", type=int, default=7)
    args = a.parse_args()
    print(json.dumps([c.to_dict() for c in generate(args.n, args.seed)], indent=2))


if __name__ == "__main__":
    main()
