"""Configurable random-variable models, driven by a validated assumptions file.

All default parameters live in default_assumptions.json and are SYNTHETIC (not calibrated). Replace the
file, or pass a dict, to change them; nothing numeric is scattered through the simulation code.

Dependence: one latent collision-severity factor Z ~ N(0,1) per iteration raises repair costs (Gaussian
loading on the log scale) and the probability of an injury claim (logit shift). Legal costs depend on
the property and injury payments they relate to. Everything else is independent given Z: a documented
simplification.
"""
from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from claimsim.models import InputError

DEFAULT_PATH = Path(__file__).with_name("default_assumptions.json")


def _p(path: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
        raise InputError(f"{path} must be a probability in [0, 1], got {v!r}")
    return float(v)


def _pos(path: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise InputError(f"{path} must be > 0, got {v!r}")
    return float(v)


def _nonneg(path: str, v) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        raise InputError(f"{path} must be >= 0, got {v!r}")
    return float(v)


@dataclass(frozen=True)
class Assumptions:
    raw: dict

    @property
    def version(self) -> str:
        return self.raw["version"]

    @property
    def synthetic(self) -> bool:
        return bool(self.raw["synthetic"])

    def scaled(self, **changes) -> "Assumptions":
        """Copy with parameters multiplied, for sensitivity analysis: key path -> factor."""
        r = copy.deepcopy(self.raw)
        for path, factor in changes.items():
            node, *rest = path.split(".")
            target = r[node]
            for k in rest[:-1]:
                target = target[int(k)] if isinstance(target, list) else target[k]
            last = rest[-1]
            if isinstance(target, list):
                target[int(last)] *= factor
            elif isinstance(target[last], dict):
                target[last] = {k: v * factor for k, v in target[last].items()}
            else:
                target[last] = target[last] * factor
        # Scaling a probability up can pass 1: cap it there (sensitivity only; inputs are still validated).
        r["injury"]["probability_by_severity"] = {k: min(v, 1.0) for k, v in r["injury"]["probability_by_severity"].items()}
        r["third_party_property"]["probability"] = min(r["third_party_property"]["probability"], 1.0)
        for src in ("third_party_insurer", "manufacturer"):
            r["recovery"][src]["probability"] = min(r["recovery"][src]["probability"], 1.0)
        return validate(r)


def validate(r: dict) -> Assumptions:
    """Check every parameter; raise InputError naming the first bad one."""
    try:
        if not isinstance(r.get("version"), str) or "synthetic" not in r:
            raise InputError("assumptions need 'version' and 'synthetic'")
        _pos("repair.median_to_estimate", r["repair"]["median_to_estimate"])
        _pos("repair.sigma", r["repair"]["sigma"])
        _p("common_shock.repair_loading", r["common_shock"]["repair_loading"])
        _nonneg("common_shock.injury_logit_loading", r["common_shock"]["injury_logit_loading"])
        inj = r["injury"]
        for k in ("low", "medium", "high", "unknown"):
            _p(f"injury.probability_by_severity.{k}", inj["probability_by_severity"][k])
        weights = [_p(f"injury.tiers.{t['name']}.weight", t["weight"]) for t in inj["tiers"]]
        if abs(sum(weights) - 1) > 1e-9:
            raise InputError(f"injury tier weights must sum to 1, got {sum(weights):.6f}")
        for t in inj["tiers"]:
            _pos(f"injury.tiers.{t['name']}.median", t["median"])
            _pos(f"injury.tiers.{t['name']}.sigma", t["sigma"])
        _pos("injury.known_sigma", inj["known_sigma"])
        tp = r["third_party_property"]
        _p("third_party_property.probability", tp["probability"])
        _pos("third_party_property.median", tp["median"])
        _pos("third_party_property.sigma", tp["sigma"])
        _pos("third_party_property.known_sigma", tp["known_sigma"])
        lh = r["legal_and_handling"]
        _nonneg("legal_and_handling.handling_fixed", lh["handling_fixed"])
        _nonneg("legal_and_handling.property_legal_share", lh["property_legal_share"])
        _nonneg("legal_and_handling.injury_legal_share", lh["injury_legal_share"])
        _pos("legal_and_handling.sigma", lh["sigma"])
        for src in ("third_party_insurer", "manufacturer"):
            _p(f"recovery.{src}.probability", r["recovery"][src]["probability"])
            a, b = r["recovery"][src]["fraction_beta"]
            _pos(f"recovery.{src}.fraction_beta[0]", a)
            _pos(f"recovery.{src}.fraction_beta[1]", b)
    except KeyError as e:
        raise InputError(f"assumptions missing key {e.args[0]!r}") from None
    return Assumptions(r)


def load(path: str | Path | None = None, data: dict | None = None) -> Assumptions:
    return validate(copy.deepcopy(data) if data is not None else json.loads(Path(path or DEFAULT_PATH).read_text()))


# ----------------------------------------------------------------------------- samplers
def lognormal_around(rng: np.random.Generator, median: float, sigma: float, n: int,
                     shock: np.ndarray | None = None, loading: float = 0.0) -> np.ndarray:
    """Lognormal with the given median; optional correlation with a common N(0,1) shock."""
    eps = rng.standard_normal(n)
    z = eps if shock is None else loading * shock + math.sqrt(1 - loading ** 2) * eps
    return median * np.exp(sigma * z)


def injury_probability(base: float, shock: np.ndarray, loading: float) -> np.ndarray:
    """Logit-shift the base probability by the common shock; base 0 or 1 stays fixed."""
    if base <= 0 or base >= 1:
        return np.full(shock.shape, float(base))
    logit = math.log(base / (1 - base)) + loading * shock
    return 1 / (1 + np.exp(-logit))


def tiered_lognormal(rng: np.random.Generator, tiers: list[dict], n: int) -> tuple[np.ndarray, np.ndarray]:
    """(amounts, tier index) from a mixture of lognormal tiers."""
    w = np.array([t["weight"] for t in tiers])
    idx = rng.choice(len(tiers), size=n, p=w / w.sum())
    med = np.array([t["median"] for t in tiers])[idx]
    sig = np.array([t["sigma"] for t in tiers])[idx]
    return med * np.exp(sig * rng.standard_normal(n)), idx


def recovery_fraction(rng: np.random.Generator, p_success: float, beta: list[float], n: int) -> np.ndarray:
    """Fraction of the recoverable amount actually recovered: 0 on failure, Beta(a, b) on success."""
    success = rng.random(n) < p_success
    return np.where(success, rng.beta(beta[0], beta[1], n), 0.0)
