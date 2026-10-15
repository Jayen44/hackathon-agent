"""Crash bundle: the evidence package for one driverless-car crash.

One JSON file per crash. `load_bundle(dict)` validates it and returns typed
dataclasses. All times are seconds on ONE shared clock (see `clock`); all
distances/speeds are SI (m, m/s). Bundles in `insurance/examples/` are synthetic.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from insurance.legal import REGIMES, ROUTES, Legal

SCHEMA_VERSION = "0.1"
Mode = Literal["manual", "assisted", "automated"]
Occupant = Literal["user_in_charge", "none"]
Source = Literal["system", "human"]
Severity = Literal["info", "warning", "critical"]

MODES = ("manual", "assisted", "automated")
KINDS = ("constant_hazard", "lead_braking", "cut_in")
# finance/ groups crashes by these labels (R157 covers cut_in, cut_out, lead_vehicle_decel)
DEFAULT_CRASH_TYPE = {"constant_hazard": "other", "lead_braking": "lead_vehicle_decel", "cut_in": "cut_in"}


class BundleError(ValueError):
    """The bundle is malformed (not the same thing as failing an integrity check)."""


@dataclass(frozen=True)
class ModeEvent:
    t: float
    mode: Mode


@dataclass(frozen=True)
class Handover:
    demand_t: float | None = None          # when the system asked the human to take over
    human_response_t: float | None = None  # when the human took control (None = never)


@dataclass(frozen=True)
class DriverState:
    t: float
    eyes_on_road: bool
    hands_on_wheel: bool


@dataclass(frozen=True)
class ControlInput:
    t: float
    source: Source
    brake: float = 0.0     # 0..1
    throttle: float = 0.0  # 0..1
    steer: float = 0.0     # rad


@dataclass(frozen=True)
class Fault:
    t: float
    code: str
    severity: Severity


@dataclass(frozen=True)
class Vehicle:
    software_version: str
    approved_software: list[str]
    occupant: Occupant
    mode_events: list[ModeEvent]
    handover: Handover = field(default_factory=Handover)
    driver_monitoring: list[DriverState] = field(default_factory=list)
    control_inputs: list[ControlInput] = field(default_factory=list)
    faults: list[Fault] = field(default_factory=list)
    odd_inside: bool | None = None  # None = unknown
    # AEVA 2018 inputs (set by the investigator from the evidence; default = no such finding)
    unauthorised_software_change: bool = False   # s.4: prohibited software alteration
    safety_update_missed: bool = False           # s.4: safety-critical update the person knew/ought to have known about
    engaged_when_inappropriate: bool = False     # s.3(2): person in charge let the car drive itself when inappropriate
    # True only when someone has POSITIVELY confirmed: no alteration and all safety-critical updates installed.
    # (An approved version alone does not show that. finance/ gets 'compliant' only if this is set.)
    software_verified: bool = False


@dataclass(frozen=True)
class DetectedObject:
    id: str
    cls: str
    first_detected_t: float
    confidence: float = 1.0


@dataclass(frozen=True)
class Perception:
    sensors: list[str] = field(default_factory=list)  # e.g. camera, lidar, radar
    objects: list[DetectedObject] = field(default_factory=list)
    decision_log_present: bool = False


@dataclass(frozen=True)
class External:
    cctv: list[str] = field(default_factory=list)  # ids of CCTV feeds covering the scene
    witnesses: int = 0
    police_report: bool = False
    medical_records: bool = False
    weather: str = "unknown"
    lighting: str = "unknown"


@dataclass(frozen=True)
class Integrity:
    hashes_present: bool
    chain_of_custody: bool
    clock_offsets_s: dict[str, float] = field(default_factory=dict)  # source -> offset vs shared clock
    log_gaps: list[tuple[float, float]] = field(default_factory=list)
    tamper_flag: bool = False


@dataclass(frozen=True)
class Conflict:
    """The reconstructed hazard, as the earliest moment a competent human could perceive it.

    Produced by the reconstruction step (CCTV + camera + lighting), not read from the car's
    own detection time. `gap_m` is bumper-to-bumper distance at `t_start`.
    """
    hazard_id: str
    t_start: float
    ego_speed_mps: float
    gap_m: float
    hazard_speed_mps: float = 0.0
    friction_mu: float = 0.7
    crash_type: str = "other"  # "cut_in" | "cut_out" | "lead_vehicle_decel" | "other" (finance/ uses this)
    # Hazard kind: constant_hazard (stationary or constant speed) | lead_braking | cut_in
    kind: str = "constant_hazard"
    hazard_decel_mps2: float = 0.0   # lead_braking: how hard the vehicle ahead brakes from t_start until it stops
    t_in_path_s: float = 0.0         # cut_in: seconds after t_start until the hazard is in the ego lane


@dataclass(frozen=True)
class Outcome:
    collided: bool
    impact_speed_mps: float | None = None  # ego speed at impact (m/s)
    # UK DfT STATS19 severity as finance/tables.py expects: Fatal | Serious | Slight | Damage only | Unknown
    injury_severity: str = "Unknown"
    paid_claim_gbp: float | None = None    # what the insurer actually paid, if known (beats the tables)
    # Injured party's contributory negligence (AEVA s.3(1)) as a (low, high) share 0..1. None = NOT assessed:
    # finance/ then gates 'pursue'. Do not put 0 here unless someone has actually assessed it as zero.
    third_party_share: tuple[float, float] | None = None


@dataclass(frozen=True)
class CrashBundle:
    case_id: str
    synthetic: bool
    t_crash: float
    jurisdiction: str
    vehicle: Vehicle
    perception: Perception
    external: External
    integrity: Integrity
    conflict: Conflict | None
    outcome: Outcome
    schema_version: str = SCHEMA_VERSION
    legal: Legal = Legal()
    raw: dict | None = field(default=None, compare=False, repr=False)   # the source dict, handed to the sim


# ---------------------------------------------------------------- loading

def _req(d: dict, key: str, where: str):
    if key not in d:
        raise BundleError(f"{where}: missing required field '{key}'")
    return d[key]


def _num(x, where: str) -> float:
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        raise BundleError(f"{where}: expected a number, got {x!r}")
    return float(x)


def load_bundle(d: dict) -> CrashBundle:
    if d.get("schema_version") != SCHEMA_VERSION:
        raise BundleError(f"schema_version must be '{SCHEMA_VERSION}', got {d.get('schema_version')!r}")
    v = _req(d, "vehicle", "bundle")
    modes = [ModeEvent(_num(_req(e, "t", "mode_event"), "mode_event.t"), _req(e, "mode", "mode_event"))
             for e in _req(v, "mode_events", "vehicle")]
    for e in modes:
        if e.mode not in MODES:
            raise BundleError(f"mode_event: unknown mode {e.mode!r}")
    if not modes:
        raise BundleError("vehicle.mode_events must not be empty")
    occupant = _req(v, "occupant", "vehicle")
    if occupant not in ("user_in_charge", "none"):
        raise BundleError(f"vehicle.occupant: unknown value {occupant!r}")
    h = v.get("handover", {})
    vehicle = Vehicle(
        software_version=_req(v, "software_version", "vehicle"),
        approved_software=list(v.get("approved_software", [])),
        occupant=occupant,
        mode_events=sorted(modes, key=lambda e: e.t),
        handover=Handover(h.get("demand_t"), h.get("human_response_t")),
        driver_monitoring=sorted((DriverState(_num(x["t"], "driver_monitoring.t"),
                                              bool(x["eyes_on_road"]), bool(x["hands_on_wheel"]))
                                  for x in v.get("driver_monitoring", [])), key=lambda s: s.t),
        control_inputs=sorted((ControlInput(_num(x["t"], "control_input.t"), x["source"],
                                            x.get("brake", 0.0), x.get("throttle", 0.0), x.get("steer", 0.0))
                               for x in v.get("control_inputs", [])), key=lambda c: c.t),
        faults=[Fault(_num(x["t"], "fault.t"), x["code"], x["severity"]) for x in v.get("faults", [])],
        odd_inside=v.get("odd_inside"),
        unauthorised_software_change=bool(v.get("unauthorised_software_change", False)),
        safety_update_missed=bool(v.get("safety_update_missed", False)),
        engaged_when_inappropriate=bool(v.get("engaged_when_inappropriate", False)),
        software_verified=bool(v.get("software_verified", False)),
    )
    for c in vehicle.control_inputs:
        if c.source not in ("system", "human"):
            raise BundleError(f"control_input: unknown source {c.source!r}")
    p = d.get("perception", {})
    perception = Perception(
        sensors=list(p.get("sensors", [])),
        objects=[DetectedObject(o["id"], o["cls"], _num(o["first_detected_t"], "object.first_detected_t"),
                                o.get("confidence", 1.0)) for o in p.get("objects", [])],
        decision_log_present=bool(p.get("decision_log_present", False)),
    )
    e = d.get("external", {})
    external = External(list(e.get("cctv", [])), e.get("witnesses", 0), bool(e.get("police_report", False)),
                        bool(e.get("medical_records", False)), e.get("weather", "unknown"),
                        e.get("lighting", "unknown"))
    i = _req(d, "integrity", "bundle")
    integrity = Integrity(
        hashes_present=bool(_req(i, "hashes_present", "integrity")),
        chain_of_custody=bool(_req(i, "chain_of_custody", "integrity")),
        clock_offsets_s={k: _num(x, f"integrity.clock_offsets_s.{k}") for k, x in i.get("clock_offsets_s", {}).items()},
        log_gaps=[(_num(a, "log_gap"), _num(b, "log_gap")) for a, b in i.get("log_gaps", [])],
        tamper_flag=bool(i.get("tamper_flag", False)),
    )
    c = d.get("conflict")
    kind = "constant_hazard" if c is None else c.get("kind", "constant_hazard")
    if kind not in KINDS:
        raise BundleError(f"conflict.kind: unknown value {kind!r} (expected one of {KINDS})")
    conflict = None if c is None else Conflict(
        hazard_id=_req(c, "hazard_id", "conflict"),
        t_start=_num(_req(c, "t_start", "conflict"), "conflict.t_start"),
        ego_speed_mps=_num(_req(c, "ego_speed_mps", "conflict"), "conflict.ego_speed_mps"),
        gap_m=_num(_req(c, "gap_m", "conflict"), "conflict.gap_m"),
        hazard_speed_mps=_num(c.get("hazard_speed_mps", 0.0), "conflict.hazard_speed_mps"),
        friction_mu=_num(c.get("friction_mu", 0.7), "conflict.friction_mu"),
        crash_type=c.get("crash_type", DEFAULT_CRASH_TYPE[kind]),
        kind=kind,
        hazard_decel_mps2=_num(c.get("hazard_decel_mps2", 0.0), "conflict.hazard_decel_mps2"),
        t_in_path_s=_num(c.get("t_in_path_s", 0.0), "conflict.t_in_path_s"),
    )
    if conflict and (conflict.gap_m < 0 or conflict.ego_speed_mps < 0 or not 0 < conflict.friction_mu <= 1.2):
        raise BundleError("conflict: gap_m/ego_speed_mps must be >= 0 and friction_mu in (0, 1.2]")
    if conflict and (conflict.hazard_decel_mps2 < 0 or conflict.t_in_path_s < 0):
        raise BundleError("conflict: hazard_decel_mps2 and t_in_path_s must be >= 0")
    if conflict and kind == "lead_braking" and conflict.hazard_decel_mps2 <= 0:
        raise BundleError("conflict: kind 'lead_braking' needs hazard_decel_mps2 > 0")
    o = _req(d, "outcome", "bundle")
    paid = o.get("paid_claim_gbp")
    if paid is not None:
        paid = _num(paid, "outcome.paid_claim_gbp")
    share = o.get("third_party_share")
    if share is not None:
        if (not isinstance(share, (list, tuple)) or len(share) != 2
                or not 0 <= _num(share[0], "outcome.third_party_share") <= _num(share[1], "outcome.third_party_share") <= 1):
            raise BundleError("outcome.third_party_share must be [low, high] with 0 <= low <= high <= 1")
        share = (float(share[0]), float(share[1]))
    outcome = Outcome(bool(_req(o, "collided", "outcome")), o.get("impact_speed_mps"),
                      o.get("injury_severity", "Unknown"), paid, share)
    return CrashBundle(
        case_id=_req(d, "case_id", "bundle"),
        synthetic=bool(d.get("synthetic", True)),
        t_crash=_num(_req(d, "t_crash", "bundle"), "t_crash"),
        jurisdiction=d.get("jurisdiction", "UK"),
        vehicle=vehicle, perception=perception, external=external,
        integrity=integrity, conflict=conflict, outcome=outcome, legal=_parse_legal(d.get("legal")), raw=d,
    )


def _parse_legal(g: dict | None) -> Legal:
    if g is None:
        return Legal()
    from datetime import date
    if g.get("regime", "unspecified") not in REGIMES:
        raise BundleError(f"legal.regime must be one of {REGIMES}")
    if g.get("recovery_route", "unspecified") not in ROUTES:
        raise BundleError(f"legal.recovery_route must be one of {ROUTES}")
    for k in ("settlement_date", "knowledge_date", "supply_date"):
        if g.get(k) is not None:
            try:
                date.fromisoformat(g[k])
            except (TypeError, ValueError):
                raise BundleError(f"legal.{k} must be an ISO date (YYYY-MM-DD)") from None
    q = g.get("p_liable_to_victim")
    if q is not None:
        if (not isinstance(q, (list, tuple)) or len(q) != 3
                or not 0 <= _num(q[0], "legal.p_liable_to_victim") <= _num(q[1], "legal.p_liable_to_victim")
                <= _num(q[2], "legal.p_liable_to_victim") <= 1):
            raise BundleError("legal.p_liable_to_victim must be [low, mid, high] with 0 <= low <= mid <= high <= 1")
        q = (float(q[0]), float(q[1]), float(q[2]))
    return Legal(g.get("regime", "unspecified"), g.get("recovery_route", "unspecified"), g.get("settlement_date"),
                 g.get("knowledge_date"), g.get("supply_date"), q)


def load_bundle_file(path: str | Path) -> CrashBundle:
    return load_bundle(json.loads(Path(path).read_text(encoding="utf-8")))
