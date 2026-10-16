"""Insurer pricing plug-ins and policy rules. Pure Python (no Modal, no FastAPI), unit-tested in tests/test_pricing.py.

An insurer profile says WHO prices a claim and WHICH house rules apply:

    {"id": "demo-insurer", "name": "Demo Insurer Ltd",
     "pricing": {"type": "builtin"} | {"type": "webhook", "url": "https://...", "version": "v3"},
     "rules": [{"rule": "min_net_recovery_gbp", "value": 5000}, ...]}

We supply the evidence (P(avoid) for careful drivers A and B, reproduction, evidence tier, R157 scope, ...) and the
built-in UK engine's reference assessment (finance/recovery.py, finance team, consumed read-only). The insurer's own
model (a webhook) returns its GBP figures and decision. The rules engine then applies the insurer's declarative rules.
Rules never execute code, never create a figure and can only make a decision MORE conservative.

Webhook responses are untrusted data: strictly validated, size-limited, never rendered as HTML, never executed. Any
failure falls back to the built-in engine and says so. See PRICING_PLUGIN.md.
"""
from __future__ import annotations

import ipaddress
import json
import math
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable

# ------------------------------------------------------------------ decisions and their order

# Higher = more conservative. Rules may only move a decision up this scale.
DECISION_RANK = {"pursue": 0, "pursue_after_signoff": 1, "pull_logs_first": 2, "get_more_evidence": 2,
                 "cannot_price": 3, "dont_pursue": 3, "not_av_recovery": 3}
WEBHOOK_DECISIONS = ("pursue", "dont_pursue", "pull_logs_first", "cannot_price")
DECISION_LABEL = {"pursue": "Pursue", "pursue_after_signoff": "Pursue after sign-off", "dont_pursue": "Don't pursue",
                  "pull_logs_first": "Get more evidence", "get_more_evidence": "Get more evidence",
                  "not_av_recovery": "Don't pursue", "cannot_price": "Cannot price"}


def more_conservative(a: str, b: str) -> str:
    """The more conservative of two decisions (a wins ties)."""
    return b if DECISION_RANK.get(b, 3) > DECISION_RANK.get(a, 3) else a


# ------------------------------------------------------------------ profiles

# Every rule: value type and what it does. Declarative only.
RULE_SPECS: dict[str, dict] = {
    "min_net_recovery_gbp": {"type": "gbp", "label": "Minimum net recovery (GBP)",
                             "help": "Below this expected net recovery: don't pursue (best case) or get more evidence (central case)."},
    "max_legal_spend_gbp": {"type": "gbp", "label": "Maximum legal spend without sign-off (GBP)",
                            "help": "If the high legal cost exceeds this, a pursue needs human sign-off."},
    "require_av_logs_above_gbp": {"type": "gbp", "label": "Require AV logs above claim value (GBP)",
                                  "help": "Claims worth more than this are held until the AV's data logs (tier 2) are in."},
    "human_signoff_above_gbp": {"type": "gbp", "label": "Human sign-off above claim value (GBP)",
                                "help": "Claims worth more than this need a named handler's sign-off to pursue."},
    "flag_if_model_spread_above": {"type": "fraction", "label": "Flag if careful-driver models differ by more than",
                                   "help": "|P(avoid) A - P(avoid) B| above this: pursue needs sign-off."},
    "require_reproduced": {"type": "bool", "label": "Require the sim to reproduce the reported crash",
                           "help": "If the reconstruction did not reproduce the crash, hold for more evidence."},
    "outside_r157_scope_action": {"type": "enum", "options": ["flag", "dont_pursue"],
                                  "label": "Crash type outside UN R157 scenarios",
                                  "help": "R157 covers cut-in, cut-out and lead-vehicle braking. flag = sign-off; dont_pursue = drop."},
}
R157_SCOPE = ("cut_in", "cut_out", "lead_vehicle_decel")
MAX_GBP = 1e9
MAX_PROFILES = 20
PROFILE_KEYS = {"id", "name", "pricing", "rules"}

OWN_API_HOST = "termvato--accel-claims-api-web.us-east.modal.run"
DEMO_MODEL_URL = f"https://{OWN_API_HOST}/api/demo-insurer-model"


def allowed_hosts() -> set[str]:
    """Webhook host allowlist: our own Modal API (demo model) + ACCEL_WEBHOOK_ALLOWED_HOSTS (comma-separated, set by an
    operator when onboarding an insurer). Claim facts are only ever sent to hosts on this list."""
    extra = os.environ.get("ACCEL_WEBHOOK_ALLOWED_HOSTS", "")
    return {OWN_API_HOST} | {h.strip().lower() for h in extra.split(",") if h.strip()}


def check_webhook_url(url: Any) -> str:
    if not isinstance(url, str) or len(url) > 300:
        raise ValueError("webhook url must be a string of at most 300 characters")
    u = urllib.parse.urlparse(url)
    if u.scheme != "https":
        raise ValueError("webhook url must use https")
    if u.username or u.password or u.port not in (None, 443):
        raise ValueError("webhook url must not carry credentials or a non-standard port")
    host = (u.hostname or "").lower()
    if host not in allowed_hosts():
        raise ValueError(f"webhook host {host!r} is not on the allowlist (ask an operator to add it to "
                         "ACCEL_WEBHOOK_ALLOWED_HOSTS)")
    return url


def _num(v, lo: float, hi: float, what: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
        raise ValueError(f"{what} must be a number between {lo:g} and {hi:g}")
    return float(v)


def validate_rule(r: Any) -> dict:
    if not isinstance(r, dict) or set(r) != {"rule", "value"}:
        raise ValueError("each rule must be exactly {'rule': name, 'value': ...}")
    name, v = r["rule"], r["value"]
    spec = RULE_SPECS.get(name) if isinstance(name, str) else None
    if spec is None:
        raise ValueError(f"unknown rule {name!r}; allowed: {', '.join(RULE_SPECS)}")
    t = spec["type"]
    if t == "gbp":
        v = _num(v, 0, MAX_GBP, name)
    elif t == "fraction":
        v = _num(v, 0, 1, name)
    elif t == "bool":
        if not isinstance(v, bool):
            raise ValueError(f"{name} must be true or false")
    elif t == "enum":
        if v not in spec["options"]:
            raise ValueError(f"{name} must be one of {spec['options']}")
    return {"rule": name, "value": v}


def validate_profile(p: Any) -> dict:
    """Strict: unknown keys anywhere are rejected. Returns a clean copy."""
    if not isinstance(p, dict):
        raise ValueError("profile must be a JSON object")
    extra = set(p) - PROFILE_KEYS
    if extra:
        raise ValueError(f"unknown profile keys: {sorted(extra)}")
    if set(p) != PROFILE_KEYS:
        raise ValueError(f"profile needs {sorted(PROFILE_KEYS)}")
    pid, name = p["id"], p["name"]
    if not isinstance(pid, str) or not pid or len(pid) > 40 or not all(c.isalnum() or c in "-_" for c in pid):
        raise ValueError("id: 1-40 letters, digits, - or _")
    if not isinstance(name, str) or not name.strip() or len(name) > 80:
        raise ValueError("name: 1-80 characters")
    pr = p["pricing"]
    if not isinstance(pr, dict) or pr.get("type") not in ("builtin", "webhook"):
        raise ValueError("pricing.type must be 'builtin' or 'webhook'")
    if pr["type"] == "builtin":
        if set(pr) != {"type"}:
            raise ValueError("builtin pricing takes no other keys")
        pricing = {"type": "builtin"}
    else:
        if set(pr) != {"type", "url", "version"}:
            raise ValueError("webhook pricing needs exactly type, url, version")
        ver = pr["version"]
        if not isinstance(ver, str) or not ver.strip() or len(ver) > 40:
            raise ValueError("pricing.version: 1-40 characters")
        pricing = {"type": "webhook", "url": check_webhook_url(pr["url"]), "version": ver}
    rules = p["rules"]
    if not isinstance(rules, list) or len(rules) > len(RULE_SPECS):
        raise ValueError("rules must be a list")
    clean = [validate_rule(r) for r in rules]
    names = [r["rule"] for r in clean]
    if len(set(names)) != len(names):
        raise ValueError("each rule may appear once")
    return {"id": pid, "name": name.strip(), "pricing": pricing, "rules": clean}


DEFAULT_PROFILES = [
    {"id": "builtin", "name": "Built-in UK engine", "pricing": {"type": "builtin"}, "rules": []},
    {"id": "demo-insurer", "name": "Demo Insurer Ltd",
     "pricing": {"type": "webhook", "url": DEMO_MODEL_URL, "version": "v3"},
     "rules": [{"rule": "require_av_logs_above_gbp", "value": 50000},
               {"rule": "human_signoff_above_gbp", "value": 100000},
               {"rule": "flag_if_model_spread_above", "value": 0.3},
               {"rule": "min_net_recovery_gbp", "value": 5000}]},
]
DEFAULT_ACTIVE = "builtin"


# ------------------------------------------------------------------ webhook contract

def evidence_from_claim(r: dict) -> dict:
    """The evidence block we send: everything the sim measured, nothing priced."""
    sim = r.get("sim") or {}
    ds = sim.get("drivers") or {}
    rep = sim.get("reproduction") or {}
    ct = r.get("crash_type")
    return {
        "p_avoid": {k: {"p": ds[k]["p_avoid"], "ci90": list(ds[k]["ci90"])} for k in ("careful_a", "careful_b") if k in ds},
        "reproduced": bool(rep.get("reproduced_flag")) if rep else None,
        "reproduction_rate": rep.get("rate"),
        "evidence_tier": r.get("evidence_tier"),
        "data_sufficiency": (r.get("data_sufficiency") or {}).get("score"),
        "r157_scope": None if ct is None else ct in R157_SCOPE,
        "crash_type": ct,
        "timeline_check": (r.get("timeline_check") or {}).get("consistent"),
    }


def builtin_output(gbp: dict) -> dict:
    """The finance engine's assessment in the webhook response shape (figures copied, never computed here)."""
    rec = gbp.get("recovery") or {}
    return {"claim_value_gbp": rec.get("claim_value"), "expected_recovery_gbp": rec.get("expected_recovery"),
            "legal_cost_gbp": rec.get("legal_cost"), "decision": gbp.get("decision", "cannot_price"),
            "reasons": list(rec.get("reasons") or ([gbp["reason"]] if gbp.get("reason") else [])),
            "model_version": "finance.recovery (insurance branch)"}


def build_payload(r: dict, facts: dict | None) -> dict:
    return {"claim_id": r["claim_id"], "claim_facts": facts or {}, "evidence": evidence_from_claim(r),
            "our_reference_assessment": builtin_output(r.get("gbp") or {})}


RESPONSE_KEYS = {"claim_value_gbp", "expected_recovery_gbp", "decision", "reasons", "model_version"}
OPTIONAL_RESPONSE_KEYS = {"legal_cost_gbp"}
MAX_RESPONSE_BYTES = 32_000
MAX_REQUEST_BYTES = 64_000
TIMEOUT_S = 10.0


def _interval(v: Any, what: str, allow_negative: bool) -> dict:
    if not isinstance(v, dict) or set(v) != {"low", "mid", "high"}:
        raise ValueError(f"{what} must be {{low, mid, high}}")
    lo = -MAX_GBP if allow_negative else 0
    a, b, c = (_num(v[k], lo, MAX_GBP, f"{what}.{k}") for k in ("low", "mid", "high"))
    if not a <= b <= c:
        raise ValueError(f"{what} must satisfy low <= mid <= high")
    return {"low": a, "mid": b, "high": c}


def validate_response(obj: Any) -> dict:
    """Strict validation of the insurer model's reply. Unknown keys rejected. Strings are kept as plain text."""
    if not isinstance(obj, dict):
        raise ValueError("response must be a JSON object")
    extra = set(obj) - RESPONSE_KEYS - OPTIONAL_RESPONSE_KEYS
    if extra:
        raise ValueError(f"unknown response keys: {sorted(extra)}")
    missing = RESPONSE_KEYS - set(obj)
    if missing:
        raise ValueError(f"missing response keys: {sorted(missing)}")
    d = obj["decision"]
    if d not in WEBHOOK_DECISIONS:
        raise ValueError(f"decision must be one of {WEBHOOK_DECISIONS}")
    out: dict = {"decision": d}
    for k, neg in (("claim_value_gbp", False), ("expected_recovery_gbp", True), ("legal_cost_gbp", False)):
        v = obj.get(k)
        if v is None:
            if k != "legal_cost_gbp" and d != "cannot_price":
                raise ValueError(f"{k} is required unless decision is cannot_price")
            out[k] = None
        else:
            out[k] = _interval(v, k, neg)
    rs = obj["reasons"]
    if not isinstance(rs, list) or len(rs) > 20 or not all(isinstance(x, str) and len(x) <= 500 for x in rs):
        raise ValueError("reasons must be a list of at most 20 strings of at most 500 characters")
    out["reasons"] = [x.strip() for x in rs]
    mv = obj["model_version"]
    if not isinstance(mv, str) or not mv.strip() or len(mv) > 80:
        raise ValueError("model_version: 1-80 characters")
    out["model_version"] = mv.strip()
    return out


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def _public_host(host: str) -> None:
    """Refuse hosts that resolve to private / loopback / link-local addresses (SSRF guard)."""
    for info in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP):
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("webhook host resolves to a non-public address")


def http_post_json(url: str, payload: dict, timeout: float = TIMEOUT_S) -> Any:
    """POST JSON, no redirects, size-capped read. Returns parsed JSON (still untrusted)."""
    check_webhook_url(url)
    _public_host(urllib.parse.urlparse(url).hostname or "")
    body = json.dumps(payload).encode()
    if len(body) > MAX_REQUEST_BYTES:
        raise ValueError("request payload too large")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"content-type": "application/json", "accept": "application/json",
                                          "user-agent": "accel-recovery-desk/1"})
    opener = urllib.request.build_opener(_NoRedirect)
    with opener.open(req, timeout=timeout) as resp:
        raw = resp.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("response too large")
    return json.loads(raw)


def call_webhook(url: str, payload: dict, post: Callable[[str, dict], Any] | None = None) -> dict:
    """-> {"ok": True, "output": validated, "latency_ms"} or {"ok": False, "error": short reason}."""
    t0 = time.time()
    try:
        raw = (post or http_post_json)(url, payload)
        out = validate_response(raw)
    except ValueError as e:     # validation, url, size, JSON decode
        return {"ok": False, "error": f"invalid: {e}"[:300], "latency_ms": round(1000 * (time.time() - t0))}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return {"ok": False, "error": f"unreachable ({type(e).__name__})", "latency_ms": round(1000 * (time.time() - t0))}
    except Exception as e:  # anything else from an untrusted endpoint: fall back, say so
        return {"ok": False, "error": f"failed ({type(e).__name__})", "latency_ms": round(1000 * (time.time() - t0))}
    return {"ok": True, "output": out, "latency_ms": round(1000 * (time.time() - t0))}


# ------------------------------------------------------------------ demo insurer model (labelled mock)

DEMO_MODEL_VERSION = "Demo Insurer Ltd pricing v3 (DEMO MODEL, not a real insurer)"
# DEMO MODEL internal legal budget by severity, GBP. Invented for the demo insurer; not sourced, not used by our engine.
DEMO_LEGAL_BUDGET_GBP = {"Damage only": 8_000, "Slight": 15_000, "Serious": 40_000, "Fatal": 60_000, "Unknown": 40_000}
DEMO_PURSUE_ABOVE_GBP = 10_000
# DEMO MODEL reserves: invented for the demo insurer, not sourced. Loading on paid amounts for claims handling.
DEMO_HANDLING_LOADING = 0.12
DEMO_RESERVE_BY_SEVERITY = {"Damage only": 3_000, "Slight": 6_500, "Serious": 95_000, "Fatal": 250_000, "Unknown": None}


def demo_insurer_model(payload: dict) -> dict:
    """Deterministic mock of an insurer's own pricing model, served at POST /api/demo-insurer-model.

    value = its own reserve (paid_gbp); share = lower of careful drivers A and B x (1 - injured party's CN high end);
    expected = value x share - fixed legal budget by severity."""
    facts = payload.get("claim_facts") or {}
    ev = payload.get("evidence") or {}
    pa = ev.get("p_avoid") or {}
    paid = facts.get("paid_gbp")
    sev = facts.get("severity") if facts.get("severity") in DEMO_LEGAL_BUDGET_GBP else "Unknown"
    reasons = ["DEMO MODEL: not a real insurer's pricing"]
    if isinstance(paid, (int, float)) and not isinstance(paid, bool) and paid > 0:
        reserve = paid * (1 + DEMO_HANDLING_LOADING)
        how = (f"values the claim at its own reserve: amount paid £{paid:,.0f} plus "
               f"{DEMO_HANDLING_LOADING:.0%} claims-handling loading")
    elif DEMO_RESERVE_BY_SEVERITY.get(sev):
        reserve = DEMO_RESERVE_BY_SEVERITY[sev]
        how = f"values the claim at its own {sev} reserve £{reserve:,.0f} (no amount paid on file)"
    else:
        reserve = None
    if reserve is None or not pa:
        return {"claim_value_gbp": None, "expected_recovery_gbp": None, "decision": "cannot_price",
                "reasons": reasons + ["no reserve for this severity or no careful-driver result"],
                "model_version": DEMO_MODEL_VERSION}
    paid = reserve
    ps = list(pa.values())
    p_lo, p_mid, p_hi = (min(x["ci90"][0] for x in ps), min(x["p"] for x in ps), min(x["ci90"][1] for x in ps))
    cn = facts.get("cn_range")
    cn_hi = float(cn[1]) if isinstance(cn, (list, tuple)) and len(cn) == 2 else 0.25
    budget = DEMO_LEGAL_BUDGET_GBP[sev]
    k = paid * (1 - cn_hi)
    exp = {"low": k * p_lo - budget, "mid": k * p_mid - budget, "high": k * p_hi - budget}
    if exp["mid"] > DEMO_PURSUE_ABOVE_GBP:
        decision = "pursue"
    elif exp["high"] > 0:
        decision = "pull_logs_first"
    else:
        decision = "dont_pursue"
    reasons += [how + ", not a tariff",
                "uses the LOWER of careful drivers A and B only (more cautious than a bracket)",
                f"applies the injured party's contributory negligence at its high end ({cn_hi:.0%})"
                + ("" if isinstance(cn, (list, tuple)) else ", assumed because not assessed"),
                f"fixed internal legal budget £{budget:,.0f} for a {sev} claim",
                f"pursues when the central net recovery exceeds £{DEMO_PURSUE_ABOVE_GBP:,.0f}"]
    return {"claim_value_gbp": {"low": paid, "mid": paid, "high": paid}, "expected_recovery_gbp": exp,
            "legal_cost_gbp": {"low": budget, "mid": budget, "high": budget},
            "decision": decision, "reasons": reasons, "model_version": DEMO_MODEL_VERSION}


SAMPLE_PAYLOAD = {
    "claim_id": "SAMPLE-0001",
    "claim_facts": {"severity": "Serious", "paid_gbp": 60000, "cn_range": [0.0, 0.1],
                    "engagement": "engaged_verified", "odd": "inside", "software": "unknown"},
    "evidence": {"p_avoid": {"careful_a": {"p": 0.82, "ci90": [0.79, 0.85]}, "careful_b": {"p": 0.95, "ci90": [0.93, 0.96]}},
                 "reproduced": True, "reproduction_rate": 0.9, "evidence_tier": 1, "data_sufficiency": 0.8,
                 "r157_scope": True, "crash_type": "lead_vehicle_decel", "timeline_check": True},
    "our_reference_assessment": {"claim_value_gbp": None, "expected_recovery_gbp": None, "legal_cost_gbp": None,
                                 "decision": "cannot_price", "reasons": ["sample payload for a connection test"],
                                 "model_version": "sample"},
}


# ------------------------------------------------------------------ rules engine (pure)

def _fmt(x: float) -> str:
    return f"-£{-x:,.0f}" if x < 0 else f"£{x:,.0f}"


def apply_rules(decision: str, output: dict, evidence: dict, rules: list[dict]) -> tuple[str, list[dict]]:
    """Apply declarative rules to a pricing output + evidence. Returns (final decision, [{rule, value, fired, reason}]).

    Only compares figures already in `output` / `evidence`; never creates one. The final decision is never less
    conservative than `decision` (DECISION_RANK)."""
    cv, er, lc = output.get("claim_value_gbp"), output.get("expected_recovery_gbp"), output.get("legal_cost_gbp")
    final, applied = decision, []

    def push(rule: dict, fired: bool, reason: str, to: str | None = None):
        nonlocal final
        before = final
        if fired and to:
            final = more_conservative(final, to)
        applied.append({"rule": rule["rule"], "value": rule["value"], "fired": fired, "reason": reason,
                        "changed": final != before})

    pursuing = lambda: final in ("pursue", "pursue_after_signoff")  # noqa: E731
    for r in rules:
        name, v = r["rule"], r["value"]
        if name == "min_net_recovery_gbp":
            if not er:
                push(r, False, "not checked: no expected recovery figure")
            elif er["high"] <= v:
                push(r, True, f"best case {_fmt(er['high'])} is not above the minimum {_fmt(v)}: don't pursue", "dont_pursue")
            elif er["mid"] <= v:
                push(r, True, f"central case {_fmt(er['mid'])} is not above the minimum {_fmt(v)}: get more evidence",
                     "pull_logs_first")
            else:
                push(r, False, f"central case {_fmt(er['mid'])} clears the minimum {_fmt(v)}")
        elif name == "max_legal_spend_gbp":
            if not lc:
                push(r, False, "not checked: no legal cost figure")
            elif lc["high"] > v and pursuing():
                push(r, True, f"legal cost up to {_fmt(lc['high'])} exceeds the {_fmt(v)} budget: needs sign-off",
                     "pursue_after_signoff")
            else:
                push(r, False, f"legal cost up to {_fmt(lc['high'])} within the {_fmt(v)} budget"
                     if lc["high"] <= v else "not pursuing, budget not engaged")
        elif name == "require_av_logs_above_gbp":
            tier = evidence.get("evidence_tier")
            if not cv:
                push(r, False, "not checked: no claim value figure")
            elif cv["mid"] > v and (tier is None or tier < 2):
                push(r, True, f"claim value {_fmt(cv['mid'])} above {_fmt(v)} and AV logs not yet obtained (tier "
                     f"{tier if tier is not None else 'unknown'}): get the logs first", "pull_logs_first")
            else:
                push(r, False, f"claim value {_fmt(cv['mid'])} at or below {_fmt(v)}" if cv["mid"] <= v
                     else "AV logs already obtained (tier 2)")
        elif name == "human_signoff_above_gbp":
            if not cv:
                push(r, False, "not checked: no claim value figure")
            elif cv["mid"] > v and pursuing():
                push(r, True, f"claim value {_fmt(cv['mid'])} above {_fmt(v)}: needs a named handler's sign-off",
                     "pursue_after_signoff")
            else:
                push(r, False, f"claim value {_fmt(cv['mid'])} at or below {_fmt(v)}" if cv["mid"] <= v
                     else "not pursuing, sign-off not needed")
        elif name == "flag_if_model_spread_above":
            pa = evidence.get("p_avoid") or {}
            if "careful_a" not in pa or "careful_b" not in pa:
                push(r, False, "not checked: needs both careful-driver models")
            else:
                spread = abs(pa["careful_a"]["p"] - pa["careful_b"]["p"])
                if spread > v:
                    push(r, True, f"careful drivers A and B differ by {spread:.0%} (limit {v:.0%}): "
                         + ("pursue needs sign-off" if pursuing() else "flagged for the handler"),
                         "pursue_after_signoff" if pursuing() else None)
                else:
                    push(r, False, f"A and B differ by {spread:.0%}, within {v:.0%}")
        elif name == "require_reproduced":
            rep = evidence.get("reproduced")
            if v and rep is not True:
                push(r, True, "the reconstruction did not reproduce the reported crash: get more evidence"
                     if rep is False else "reproduction not checked: get more evidence", "pull_logs_first")
            else:
                push(r, False, "rule off" if not v else "reconstruction reproduces the reported crash")
        elif name == "outside_r157_scope_action":
            scope = evidence.get("r157_scope")
            if scope is False:
                if v == "dont_pursue":
                    push(r, True, f"crash type {evidence.get('crash_type')} is outside the UN R157 scenarios: don't pursue",
                         "dont_pursue")
                else:
                    push(r, True, f"crash type {evidence.get('crash_type')} is outside the UN R157 scenarios: "
                         + ("pursue needs sign-off" if pursuing() else "flagged"),
                         "pursue_after_signoff" if pursuing() else None)
            else:
                push(r, False, "inside R157 scenarios" if scope else "not checked: crash type unknown")
    assert DECISION_RANK.get(final, 3) >= DECISION_RANK.get(decision, 3)
    return final, applied


# ------------------------------------------------------------------ comparison (built-in vs insurer model)

def _overlap(a: dict | None, b: dict | None) -> bool | None:
    if not a or not b:
        return None
    return a["low"] <= b["high"] and b["low"] <= a["high"]


def compare(builtin: dict, insurer: dict | None, builtin_final: str, insurer_final: str | None) -> dict | None:
    """Side-by-side of the two outputs. Every figure is copied from one of them; explanations only compare."""
    if insurer is None:
        return None
    why: list[str] = []
    cv_ov = _overlap(builtin.get("claim_value_gbp"), insurer.get("claim_value_gbp"))
    er_ov = _overlap(builtin.get("expected_recovery_gbp"), insurer.get("expected_recovery_gbp"))
    bcv, icv = builtin.get("claim_value_gbp"), insurer.get("claim_value_gbp")
    if bcv and icv and cv_ov is False:
        why.append(f"claim value: insurer model {_fmt(icv['low'])}–{_fmt(icv['high'])} vs built-in "
                   f"{_fmt(bcv['low'])}–{_fmt(bcv['high'])} (ranges do not overlap)")
    elif bool(bcv) != bool(icv):
        why.append("only one model could value the claim")
    blc, ilc = builtin.get("legal_cost_gbp"), insurer.get("legal_cost_gbp")
    if blc and ilc and abs(blc["mid"] - ilc["mid"]) > 0.25 * max(blc["mid"], ilc["mid"], 1):
        why.append(f"legal cost: insurer model {_fmt(ilc['mid'])} vs built-in {_fmt(blc['mid'])} (central)")
    if er_ov is False:
        why.append("expected recovery ranges do not overlap")
    dec_differs = builtin["decision"] != insurer["decision"]
    final_differs = insurer_final is not None and builtin_final != insurer_final
    if dec_differs:
        why.append(f"model decisions differ: built-in {DECISION_LABEL.get(builtin['decision'], builtin['decision'])}, "
                   f"insurer model {DECISION_LABEL.get(insurer['decision'], insurer['decision'])}")
    if final_differs and not dec_differs:
        why.append("the insurer's rules changed the decision")
    return {"agree": not (dec_differs or final_differs) and cv_ov is not False and er_ov is not False,
            "decision_differs": dec_differs or final_differs, "claim_value_overlap": cv_ov,
            "expected_recovery_overlap": er_ov, "why": why}


# ------------------------------------------------------------------ one claim under one profile

def price_claim(r: dict, facts: dict | None, profile: dict, gate: Callable[[str], str] = lambda d: d,
                post: Callable[[str, dict], Any] | None = None) -> dict:
    """Price an assessed claim (claims.assess_claim output) under an insurer profile.

    Returns {"pricing": {...}, "rules_applied": [...], "decision_final": str}. The built-in engine always runs as the
    reference; with a webhook profile the insurer's model is called too and both are compared."""
    gbp = r.get("gbp") or {}
    evidence = evidence_from_claim(r)
    builtin = builtin_output(gbp)
    engine_decision = builtin["decision"]

    def guarded(d: str) -> str:
        d = gate(d)
        # Evidence guard: if the liability verdict is not an AV recovery, no pricing model can turn it into one.
        return more_conservative(d, "not_av_recovery") if engine_decision == "not_av_recovery" else d

    rules = profile.get("rules") or []
    b_final, b_rules = apply_rules(guarded(builtin["decision"]), builtin, evidence, rules)
    pricing = {"profile": {"id": profile["id"], "name": profile["name"]}, "source": "builtin",
               "model_version": builtin["model_version"], "output": builtin, "builtin": builtin,
               "builtin_final": b_final, "insurer": None, "insurer_final": None, "fallback_reason": None,
               "latency_ms": None, "comparison": None, "webhook_version": None}
    final, applied = b_final, b_rules
    pr = profile.get("pricing") or {}
    if pr.get("type") == "webhook":
        pricing["webhook_version"] = pr.get("version")
        res = call_webhook(pr["url"], build_payload(r, facts), post)
        pricing["latency_ms"] = res.get("latency_ms")
        if res["ok"]:
            out = res["output"]
            i_final, i_rules = apply_rules(guarded(out["decision"]), out, evidence, rules)
            pricing.update(source="webhook", model_version=out["model_version"], output=out, insurer=out,
                           insurer_final=i_final, comparison=compare(builtin, out, b_final, i_final))
            final, applied = i_final, i_rules
        else:
            pricing.update(source="fallback", fallback_reason=f"insurer model {pr.get('version', '')} "
                           f"{res['error']}; priced by the built-in UK engine instead")
    return {"pricing": pricing, "rules_applied": applied, "decision_final": final}

