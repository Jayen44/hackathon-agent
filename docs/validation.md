# Validation of formulae and assumptions (15 Oct 2026)

Executable checks live in `tests/test_validation.py` (20 tests) and `scripts/sensitivity.py`. Facts and sources are in
`docs/verification.md`; this file is about whether the **maths and modelling choices** hold up.

## 1. What was checked and how
| Formula / assumption | Check | Result |
|---|---|---|
| Stopping-distance model: `v_impact^2 = v_rel^2 - 2 a (gap - v_rel * t_react)` | Two hand-computed cases (no collision at 40 m; 9.43 m/s impact at 20 m); impact at full speed when braking starts too late | Pass |
| Closed form vs an **independent** forward-Euler integrator | Grid of 4 speeds x 4 gaps x 4 reaction times x 2 roads x 2 hazard speeds (256 cases), tolerance 0.6 m/s | Pass |
| Closed form/numeric vs the **sim branch simulator** (separate code, polygon collision) | 7 example conflicts incl. lead braking and cut-in; P(avoid) within 0.15, same fast/slow outcomes | Pass (run against a temporary checkout of `origin/sim`) |
| Braking limit `a = min(mu * g, 9.0)` | mu 0.7 gives 6.87 m/s^2; mu 1.1 is capped at 9.0 | Pass. Physics, **not a cited source** (see section 3) |
| Reaction-time sampler (triangular 0.7 / 1.0 / 1.5 s) | Sample mean 1.067 s and 5/50/95th percentiles match the analytic quantiles to 0.02 s | Pass (sampler is right; the *range* is debated, section 3) |
| P(avoid) behaves sensibly | Increases with gap and friction, decreases with speed; fast reaction never worse than slow | Pass |
| Monte Carlo noise | 12 seeds at n=2000: spread under 2.5x the binomial standard error (~1.1%) | Pass |
| Wilson 90% interval used as `ci90` | Hand-computed (0.4188, 0.5812) for p=0.5, n=100; simulated coverage 86-94% | Pass. **Bug found and fixed:** float rounding gave an upper bound of 0.9999999999999999 when p=1.0, which `finance.Interval` rejects. Now clamped so the interval always contains p |
| Decision thresholds | Inclusive at exactly 0.8 and 0.2; confidence drops to MEDIUM when a slow human would not have avoided it | Pass |
| `finance.av_share` | Hand-computed (0.48 / 0.68 / 0.81) | Pass |
| `finance.expected_recovery` | Hand-computed (-1,080 / 1,400 / 3,860) | Pass |
| "Fault share = P(avoid)" equals P(win) x value in expectation | Monte Carlo of a win/lose outcome matches `p x value - cost` | Pass (same *mean*, but real outcomes are all-or-nothing, so the spread is much wider than the interval suggests) |

## 2. Findings on the finance formulas (Antonio's code; read-only review, no changes made)
The arithmetic is correct. Modelling points to state in the pitch or decide on:
1. **Optimistic by omission: no cost-shifting.** `expected_recovery = share x value - cost` charges our own legal cost but not the other side's if we lose (the loser usually pays). The model's figures are therefore generous. Antonio notes this in `docs/assumptions.md`; it should appear on the demo slide.
2. **Worst-case corners are extreme.** `low = share.low x value.low - cost.high` takes every input at its worst at once, so "pursue only if the worst case clears the threshold" is very conservative. That is a reasonable safety choice, but it explains why almost every claim lands on `pull_logs_first`.
3. **Binary reality.** In court the insurer recovers the contributory-negligence-adjusted amount or nothing. The mean is right; the downside is not shown. A simple win/lose spread would be more honest than a smooth interval.
4. **The `ci90` we feed it covers sampling error only** (Monte Carlo, n=400 to 2000), not model error. The real uncertainty is dominated by the human-driver assumptions (section 3), which no interval currently captures.
5. **Time and delay are ignored.** AEVA s.5 only allows recovery after the insurer's liability is settled, so money arrives years later. No discounting.
6. **US crashes, UK prices.** Already flagged by finance. Synthetic UK crashes (STATS19) reduce but do not remove this.

## 3. Findings on our own assumptions (insurance side)
| Assumption | Status | Direction of bias if wrong |
|---|---|---|
| Reaction time 0.7 / 1.0 / 1.5 s | Plausible lower end; **upper end light**. Field studies of unaware drivers give 85th percentile 1.8-1.9 s | Favours "tech company liable" (human looks too quick) |
| No brake build-up time (full deceleration instantly after reaction) | Simplification; real brakes ramp over roughly 0.1-0.2 s | Same direction |
| Friction: dry 0.7, wet 0.4, snow/ice 0.2; limit 9 m/s^2 | Textbook physics. A search did not return a citable source for these numbers, so they are **Knowledge, not Verified** | Wet-road error is the largest single effect (below) |
| Straight-line braking only; no swerving | Simplification | Favours "tech company liable" (humans can also steer around) |
| Hazard keeps constant speed after the conflict start (except lead braking) | Simplification | Neutral to slightly favours the tech company |
| Conflict start = earliest moment a human could perceive the hazard | **Hardest input to get right.** It comes from the reconstruction, not the car's own log | Depends on the investigator |
| 10 s handover warning, 0.8 / 0.2 thresholds | Illustrative only | Not evidence-based; adjustable in `engine.Policy` |

### How much does it matter? (`python scripts/sensitivity.py`)
Gap needed for the engine to say "tech company liable" (P(human avoids) >= 0.8):

| Speed, road | Current (0.7/1.0/1.5 s) | Wider (0.7/1.2/2.0 s) | Wider + build-up |
|---|---|---|---|
| 20 mph dry | 16.6 m | 19.5 m | 20.4 m |
| 30 mph dry | 29.4 m | 33.8 m | 35.1 m |
| 30 mph wet | 39.2 m | 43.6 m | 44.9 m |
| 45 mph dry | 53.5 m | 60.0 m | 62.0 m |
| 45 mph wet | 75.3 m | 81.9 m | 83.9 m |

- Moving to the wider range raises the required gap by about **4 to 7 m (roughly 15%)**. Crashes with a 29-34 m gap at 30 mph would move from "tech company" to "review".
- **Road surface matters more:** wet vs dry shifts the threshold by about 10 m at 30 mph. Evidence about the road surface (weather, CCTV, skid marks) is therefore worth more than refining the reaction-time range.
- Recommendation: adopt (0.7 / 1.2 / 2.0 s) as the default (issue #11) and say that results are sensitive to it. Not applied yet because it is your call.

## 4. Not validated / still open
- The real **UN R157 Annex 3** driver models (issue #14); until then every P(avoid) uses placeholder humans.
- A **citable source** for friction coefficients and braking limits.
- Calibration against **real crash data**: we have only synthetic bundles, so we cannot say how accurate the verdicts are. `eval/labels.csv` (issue #5) is the route to a first accuracy number.
- The **conflict-start reconstruction**: no tool yet turns CCTV and camera footage into `conflict.t_start` and `gap_m`.
