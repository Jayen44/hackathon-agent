"""How far do the human-driver assumptions move the verdict? Prints the gap (m) at which the engine flips.

    python scripts/sensitivity.py

For each ego speed and road, finds the smallest gap where P(competent human avoids) reaches the
'tech company liable' threshold (0.8) and the 'unavoidable' threshold (0.2), under alternative reaction-time
assumptions. A bigger required gap = a more demanding human = fewer crashes blamed on the tech company.
"""
import dataclasses
import sys

sys.path.insert(0, ".")
from insurance.bundle import Conflict  # noqa: E402
from insurance.counterfactual import HumanParams, KinematicEstimator  # noqa: E402

SCENARIOS = {
    "current   (0.7/1.0/1.5 s)": HumanParams(),
    "wider     (0.7/1.2/2.0 s)": dataclasses.replace(HumanParams(), reaction_mode_s=1.2, reaction_high_s=2.0),
    "wider+0.1s brake build-up": dataclasses.replace(HumanParams(), reaction_low_s=0.8, reaction_mode_s=1.3,
                                                     reaction_high_s=2.1),
}


def gap_for(p_target: float, v: float, mu: float, hp: HumanParams) -> float:
    est = KinematicEstimator(hp, n=600)
    lo, hi = 0.0, 200.0
    for _ in range(18):                       # bisection on gap: p_avoid is monotone increasing in gap
        mid = (lo + hi) / 2
        c = Conflict("h", 0.0, v, mid, 0.0, mu)
        if est.estimate(c).p_avoid >= p_target:
            hi = mid
        else:
            lo = mid
    return hi


if __name__ == "__main__":
    print(f"{'assumption':28} {'speed':>9} {'road':>5} | gap for P>=0.8 (tech liable) | gap for P>0.2 (not unavoidable)")
    for v, label in ((8.9, "20 mph"), (13.4, "30 mph"), (20.0, "45 mph")):
        for mu, road in ((0.7, "dry"), (0.4, "wet")):
            for name, hp in SCENARIOS.items():
                g80, g20 = gap_for(0.8, v, mu, hp), gap_for(0.2 + 1e-9, v, mu, hp)
                print(f"{name:28} {label:>9} {road:>5} | {g80:27.1f} m | {g20:27.1f} m")
            print()
