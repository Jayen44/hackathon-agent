# Pricing plug-in and rules

An insurer can price claims with its own model and apply its own policy rules. We supply the evidence and the
built-in UK engine's reference assessment; the insurer's model returns its figures and decision; the rules engine
applies the insurer's rules. Code: `viz/api/pricing.py`. Tests: `tests/test_pricing.py`.

## Profiles

Stored in the Modal Dict `accel-insurer-profiles` (keys `profiles`, `active`). Defaults when empty:

- `builtin`: "Built-in UK engine" (finance team, `finance/recovery.py`), no rules.
- `demo-insurer`: "Demo Insurer Ltd", webhook = our demo model, rules below. DEMO MODEL, not a real insurer.

```json
{"id": "demo-insurer", "name": "Demo Insurer Ltd",
 "pricing": {"type": "webhook", "url": "https://termvato--accel-claims-api-web.us-east.modal.run/api/demo-insurer-model", "version": "v3"},
 "rules": [{"rule": "require_av_logs_above_gbp", "value": 50000},
           {"rule": "human_signoff_above_gbp", "value": 100000},
           {"rule": "flag_if_model_spread_above", "value": 0.3},
           {"rule": "min_net_recovery_gbp", "value": 5000}]}
```

Validation is strict: unknown keys are rejected at every level, each rule appears at most once, numbers are finite and
in range. `pricing` is `{"type": "builtin"}` or `{"type": "webhook", "url", "version"}`. No code is ever executed.

API:

    GET  /api/profiles                     {active, profiles, rule_specs, allowed_webhook_hosts, demo_model_url}
    GET  /api/profiles/{id}
    PUT  /api/profiles                     {"profile": {...}} upsert, {"active": id}, {"delete": id}, {"reset": true}
    POST /api/profiles/test                {"url"}: send the sample payload, return the validated reply or the error
    POST /api/assess                       optional "profile_id" (default: the active profile)
    POST /api/claims/{id}/reprice          {"profile_id"}: re-price a stored claim (no new simulation)
    POST /api/profiles/{id}/reprice-all    re-price every stored claim under a profile
    GET  /api/portfolio-comparison?profile_id=   agree/differ counts and totals from current claim results

## Rules

All rules are declarative. They compare figures already in the pricing output or the evidence, never create a
figure, and can only move a decision to a more conservative one:

    pursue  <  pursue_after_signoff  <  pull_logs_first / get_more_evidence  <  dont_pursue / cannot_price / not_av_recovery

| rule | value | fires when | effect |
|---|---|---|---|
| `min_net_recovery_gbp` | GBP | best case <= value / central case <= value | dont_pursue / pull_logs_first |
| `max_legal_spend_gbp` | GBP | high legal cost > value while pursuing | pursue_after_signoff |
| `require_av_logs_above_gbp` | GBP | claim value (central) > value and evidence tier < 2 | pull_logs_first |
| `human_signoff_above_gbp` | GBP | claim value (central) > value while pursuing | pursue_after_signoff |
| `flag_if_model_spread_above` | 0..1 | abs(P(avoid) A - P(avoid) B) > value | pursue_after_signoff (flag otherwise) |
| `require_reproduced` | bool | sim did not reproduce the reported crash | pull_logs_first |
| `outside_r157_scope_action` | "flag" or "dont_pursue" | crash type not cut-in, cut-out or lead-vehicle braking | pursue_after_signoff / dont_pursue |

A rule whose figure is missing is reported as "not checked", not fired. Two fixed guards run before the rules: the
data-sufficiency gate (`claims.SUFFICIENCY_MIN`), and if the liability verdict is "not an AV recovery" no pricing
model can turn it into one.

Every claim result lists each rule as `{rule, value, fired, changed, reason}` in `rules_applied`.

## Webhook contract

We `POST` JSON to the profile's URL:

```json
{
  "claim_id": "22_pursue_lead_braking",
  "claim_facts": {"severity": "Serious", "paid_gbp": 80000, "cn_range": [0.0, 0.1],
                  "engagement": "engaged_verified", "odd": "inside", "software": "compliant"},
  "evidence": {
    "p_avoid": {"careful_a": {"p": 0.82, "ci90": [0.79, 0.85]}, "careful_b": {"p": 0.95, "ci90": [0.93, 0.96]}},
    "reproduced": true, "reproduction_rate": 0.9, "evidence_tier": 2, "data_sufficiency": 0.8,
    "r157_scope": true, "crash_type": "lead_vehicle_decel", "timeline_check": true
  },
  "our_reference_assessment": {
    "claim_value_gbp": {"low": 80000, "mid": 80000, "high": 80000},
    "expected_recovery_gbp": {"low": 12391, "mid": 53536, "high": 70038},
    "legal_cost_gbp": {"low": 9000, "mid": 20904, "high": 40000},
    "decision": "pull_logs_first", "reasons": ["..."], "model_version": "finance.recovery (insurance branch)"
  }
}
```

`cn_range` is the injured party's contributory negligence share (null = not assessed). Codes for engagement, ODD and
software are the finance engine's (`finance/recovery.py`).

We expect:

```json
{
  "claim_value_gbp": {"low": 89600, "mid": 89600, "high": 89600},
  "expected_recovery_gbp": {"low": 27901, "mid": 29431, "high": 30804},
  "legal_cost_gbp": {"low": 40000, "mid": 40000, "high": 40000},
  "decision": "pursue",
  "reasons": ["..."],
  "model_version": "pricing v3"
}
```

- `decision`: `pursue` | `dont_pursue` | `pull_logs_first` | `cannot_price`.
- Intervals: finite, `low <= mid <= high`; claim value and legal cost >= 0. `claim_value_gbp` and
  `expected_recovery_gbp` may be null only with `cannot_price`. `legal_cost_gbp` is optional.
- `reasons`: at most 20 strings of at most 500 characters. `model_version`: 1-80 characters.
- No other keys.

Transport:

- https only, port 443, no credentials in the URL, no redirects followed.
- Host must be on the allowlist: our own Modal API host, plus `ACCEL_WEBHOOK_ALLOWED_HOSTS` (comma-separated, set
  by an operator). Hosts resolving to private, loopback or link-local addresses are refused.
- Request at most 64 KB, response at most 32 KB, timeout 10 s.

The response is untrusted data. It is validated as above, shown as plain text (never rendered as HTML, never
executed). On any failure (timeout, network, invalid reply) the claim is priced by the built-in engine and the result
says so: `pricing.source = "fallback"` with `pricing.fallback_reason`.

## Claim result fields

    pricing.profile            {id, name}
    pricing.source             builtin | webhook | fallback
    pricing.model_version      the model that produced pricing.output
    pricing.output             the figures used (insurer model, or built-in)
    pricing.builtin            built-in engine output (always present, the reference)
    pricing.builtin_final      built-in decision after the guards and the profile's rules
    pricing.insurer            insurer model output (webhook only)
    pricing.insurer_final      insurer decision after the guards and the profile's rules
    pricing.comparison         {agree, decision_differs, claim_value_overlap, expected_recovery_overlap, why[]}
    rules_applied              [{rule, value, fired, changed, reason}]
    decision_final             final decision (also in `decision`); `engine_decision` stays the finance engine's

The comparison only compares the two outputs: every figure shown comes from one of them.

## Demo model

`POST /api/demo-insurer-model`: "Demo Insurer Ltd pricing v3 (DEMO MODEL, not a real insurer)". Deterministic:

    claim value  = amount paid x 1.12 (handling loading), or a fixed reserve by severity if nothing paid
    share        = lower of careful drivers A and B (ci90 for low/high) x (1 - injured party's CN high end; 0.25 if not assessed)
    expected     = claim value x share - fixed legal budget by severity
    decision     = pursue if central > 10,000; pull_logs_first if best case > 0; else dont_pursue

All demo numbers are invented for the demo insurer and labelled as such (`pricing.DEMO_*`).

## Design intent

The plug-in runs per insurer: each profile's model and rules are used to price that insurer's claims.
