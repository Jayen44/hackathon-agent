# claimsim: Monte Carlo claim cost simulation (FSD motor claims, UK, GBP)

`simulate_claim_cost` estimates the **distribution** of an insurer's cost for one motor claim involving a
self-driving vehicle, under explicit liability scenarios, so a claims agent (or a person) can see the
expected cost, the tail, what drives it, and which evidence would narrow it.

> **Illustrative prototype.** Every distribution parameter is a synthetic placeholder in
> `default_assumptions.json`. Nothing is calibrated to real UK claims; outputs are not forecasts.

Owner: Antonio (`insurance` branch). Sits next to `finance/`. `finance/` prices the AEVA s.5 recovery
action against the AV company for one claim; `claimsim` models the insurer's whole claim cost (own damage,
third-party losses, injury, the policy layer and recoveries) as a distribution.

## Run it
```
pip install -r requirements.txt            # numpy and pandas; no new dependencies
python -m claimsim.demo                    # illustrative claim, readable summary
python -m claimsim.demo --json             # full machine-readable output
python -m pytest tests/test_claimsim.py    # 31 tests
```
Python:
```python
from claimsim.agent_tools import simulate_claim_cost
out = simulate_claim_cost(claim_dict, n_simulations=10_000, seed=42)   # JSON-ready dict
```

## Concepts kept separate
| Term | Meaning |
|---|---|
| **Gross economic loss** | All losses from the accident, for everyone: both vehicles, injuries, other property, other expenses. The same in every liability scenario. |
| **Attributable loss** | What the insurer answers for before policy terms: its own-damage (first-party) cover plus the insured vehicle's liability share of third-party losses. |
| **Covered loss** | Attributable loss that is eligible and not excluded under the policy. |
| **Insurer payment** | Covered loss after the excess, sublimits and limits. The insured keeps the excess (`insured_retained`). |
| **Legal and handling** | The insurer's own expense, reported separately and kept outside indemnity limits. |
| **Recoveries** | Amounts recovered from the third party's insurer or from the AV manufacturer (AEVA 2018 s.5). They are capped at what is recoverable from each source, which is capped at what was paid. |
| **Net exposure** | Insurer payment + legal and handling − recoveries. |

Factual causation, legal liability, policy coverage and recovery are separate. Liability shares are
**inputs**: the simulation never decides who is at fault, and it never infers liability from FSD engagement.

## Inputs (`claimsim/examples/illustrative_claim.json`)
- **Estimates:** `insured_repair_estimate`, `third_party_repair_estimate`, `third_party_property_estimate`, `other_expenses_estimate`. `null` means unknown and is reported as missing.
- **Injury:** `injury_outcome` is `unknown` (modelled), `none`, or `known` (then `injury_cost_estimate` is required).
- **Collision severity:** `collision_severity` (`low`/`medium`/`high`/`null`) shifts the injury probability.
- **Policy:** excess, own-damage limit (vehicle value), combined third-party property limit, bodily-injury limit, exclusions, sublimits, jurisdiction.
- **Scenarios:** `{name, insured_driver_share, av_system_share, third_party_share}` with shares summing to 1. `probability` is optional but needs a `probability_source`. Probability-weighted results appear only when every scenario has one and they sum to 1; otherwise results are **conditional only**.
- **Recovery:** claim-specific recovery probabilities are optional and need a `recovery_probability_source`; otherwise the synthetic defaults are used and flagged.
- **Thresholds:** `human_review_threshold` and `exceedance_thresholds`.

Unknown input fields, negative amounts, probabilities outside [0, 1], shares that don't sum to 1, and
probabilities without a source are all rejected with `InputError`.

## Example output (illustrative claim, 10,000 simulations, seed 42)
Inputs: insured repair £4,500, third-party repair £7,200, excess £500, injury unknown, liability unresolved.
```
scenario (conditional)          gross   payment  expenses  recovered  NET mean      p50      p90      p95  P(>25k)
A_insured_not_liable          £17,885    £4,141      £586     £3,173    £1,554     £962   £4,053   £5,135     0.0%
B_insured_50pct_liable        £17,885   £10,763    £1,584     £1,587   £10,760   £7,396  £11,399  £14,261     2.8%
C_insured_fully_liable        £17,885   £17,385    £2,581         £0   £19,966  £13,268  £20,491  £25,813     5.4%
D_av_system_fully_liable      £17,885   £17,385    £2,581     £3,120   £16,846  £11,626  £19,260  £23,962     4.5%

What drives scenario B (one-way, expected net exposure):
  liability_allocation     £8,919 -> £12,601   evidence: vehicle event data (DSSAD), CCTV, dashcam, witnesses, police
  injury_probability       £9,245 -> £12,101   evidence: whether any injury is claimed (CNF / claims portal)
  repair_severity          £9,351 -> £12,169   evidence: engineer's assessment or final invoices
  injury_severity          £9,680 -> £11,840   evidence: medical report and prognosis
  legal_expenses           £9,968 -> £11,552   evidence: litigation status, solicitor estimates
  recovery_probability    £11,235 -> £10,483   evidence: third-party insurer's position, manufacturer's response
Human review: REQUIRED (C: p95 £25,813 > £25,000). The tool does not approve, deny or settle claims.
```
- **Scenarios A, B and C** are the conditional results you asked for: insured not liable, 50% liable, fully liable. **D** adds the FSD case, where the insured vehicle is liable but the fault lies with the automated driving system, so the insurer pays and then recovers from the manufacturer.
- **No probabilities were supplied,** so the output says the scenarios must not be averaged.
- **Gross loss exceeds payment** in A and B, because the third party's own insurer bears their share.
- **Expected gross loss (£17,885)** includes the modelled injury and other-property losses, not just the two repair estimates.
- **The full JSON** also reports exceedance probabilities at each threshold, a breakdown by category, recoveries by source, Monte Carlo standard errors, a reconciliation check, rank correlations, missing information and limitations.

## Modelling assumptions (all synthetic unless stated)
1. **Repair:** lognormal, with median equal to the estimate and log-sd 0.25.
2. **Dependence:** one latent collision-severity factor Z ~ N(0, 1) per iteration.
   - It loads on log repair costs (loading 0.5) and shifts the injury probability on the logit scale (0.8).
   - Legal cost scales with the payments it relates to.
   - Everything else is independent given Z.
3. **Injury, two stages:** first P(a third-party injury claim) by collision severity (0.08 / 0.25 / 0.55, 0.25 if unknown), then severity from three lognormal tiers:
   - minor: 85%, median £3k
   - serious: 13%, median £40k
   - catastrophic: 2%, median £500k
   A known injury amount is lognormal around the estimate (log-sd 0.3).
4. **Other third-party property, if unknown:** happens with probability 0.10; size lognormal, median £1,500.
5. **Legal and handling:** £350 fixed, plus a lognormal share of property payments (5%) and of injury payments (25%).
6. **Recovery:** a Bernoulli success, then a Beta fraction of the recoverable amount.
   - Third-party insurer: P = 0.85, Beta(9, 1).
   - Manufacturer: P = 0.30, Beta(6, 4).
7. **Who can be recovered from:**
   - The third-party insurer: the third party's share of the own-damage outlay. The insured's excess is the insured's own loss and isn't part of it.
   - The manufacturer: the AV system's share of the own-damage outlay plus the AV's part of third-party payments.
   - The insured driver's share: nothing.
8. **Policy (UK rules):** the excess applies to own damage only. Third-party vehicle and other property share one combined limit, split pro rata if capped. Bodily injury is capped only if a limit is given (UK compulsory injury cover is unlimited under RTA 1988; general knowledge, not checked here). Exclusions remove a category from cover.

## Validation built in
- **Reconciliation in every scenario and every iteration:**
  - net = payment + expenses − recoveries
  - categories sum to totals
  - payment ≤ covered ≤ attributable
  - recovered ≤ recoverable ≤ payment
  - own-damage payment + retained = covered
- **Monte Carlo error:** the standard error of the mean, plus a batch-means standard error for the 95th percentile. `simulation.stability()` shows both shrinking as iterations grow (tested).
- **Common random numbers:** each random component has its own seeded stream, so scenario comparisons and sensitivity runs aren't blurred by sampling noise.

## Sensitivity
- **One-way (tornado):** each driver is moved to a low and a high value (×0.5–×1.5 depending on the driver; ±10 points of liability moved between the insured and the third party), re-run on the same draws, and ranked by swing in expected net exposure, with the p95 swing alongside. Each driver maps to the evidence that would narrow it.
- **Rank correlation:** Spearman correlation between each sampled driver and net exposure.
- **Limitations:**
  - The perturbation ranges are illustrative.
  - One-way analysis misses interactions.
  - Correlation shows association inside this model, not causation in the world, and depends on the assumed dependence structure.
  - A variance-based (Sobol) analysis would need SciPy or SALib and calibrated input ranges: it's on the roadmap, not here.

## Using it from the AI agent
```python
from claimsim.agent_tools import make_tool
from agents.llm import run_agent
definition, execute = make_tool({"CLM-1": claim_record}, n_simulations=10_000, seed=0)
run_agent(client, name="adjuster", system=..., prompt=..., tools=[definition], execute=execute, schema=..., effort="medium", trace=...)
```
- **What the model can and can't change:** it can only send `claim_ref`, a subset of scenario names, and whether to include sensitivity. Amounts, limits, liability shares, probabilities, the seed and the iteration count are fixed by the host.
- **Errors:** unknown claim refs or scenarios come back to the model as tool errors (tested with `agents.llm.run_agent`).
- **Warnings and missing information** are always in the output, and the tool description tells the model to report them with any figure.
- **Not yet wired** into the adjuster/defence debate (`agents/debate.py`). That needs real policy terms for each claim; inventing them for the synthetic crashes would defeat the purpose.

## Known limitations
- All parameters are synthetic. Nothing is calibrated to real UK claims.
- Only third-party injury is modelled. The insured's own occupants and personal accident cover are not.
- There's no settlement timing, inflation or discounting. AEVA s.5 recovery comes only after settlement.
- Exclusions under compulsory cover aren't modelled; in reality the insurer may have to pay first and recover from the insured.
- Recovery legal costs aren't separated from general legal costs, and the other side's costs (loser pays) aren't modelled.
- Every claim has a single injured-claimant aggregate; there's no per-claimant split.

## Roadmap to real claims
1. **Calibrate repair severity** (estimate-to-final ratios) and **injury frequency and severity** from the insurer's closed claims, with the claims portal and JCG / whiplash tariff as external checks. Fit by maximum likelihood, holding out data for testing.
2. **Fit legal and handling costs** from cost ledgers, by track (CPR Part 45 fixed recoverable costs give a statutory floor).
3. **Estimate recovery probabilities and fractions** from the recovery history, separately for third-party insurers and manufacturers. AV-specific data will be thin, so use credibility weighting.
4. **Replace the single common shock** with a fitted dependence structure, such as a copula estimated from paired claim outcomes.
5. **Supply liability scenario probabilities** from a documented process (claims handler or panel), never the LLM. `finance/` and the agents' P(avoid) can inform the AV-system scenario.
6. **Back-test** against open claims and report calibration (PIT histograms, coverage of the 90% interval). Version every assumptions file.
