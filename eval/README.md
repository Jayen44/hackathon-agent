# eval/: hand labels for the liability and recovery engine (issue #5)

`labels.csv` has 20 UK crash cases, each labelled for: was it avoidable by a careful and competent driver, who pays, and would we pursue recovery from the tech company. Load and validate it with `eval.labels.load_labels()`.

**Status: reviewed by Antonio (15 Oct 2026).** Claude drafted the labels from each case's facts, without running our engine. Antonio then reviewed them:
- **Confirmed:** pursuing small, clean, tech-liable claims; the outside-ODD call.
- **Not confirmed:** the AEVA s.3(2) case (20) and the marginal miss (SYN-11-176). Both are now `review` / `pull_logs`.

`labeller = antonio` on every row.

## The cases
There are no public UK self-driving crash reports, and the team decided on UK data only, so every case is synthetic:
- **13 designed cases** from `insurance/examples`, one per liability path: 01–10, plus 13 (unapproved software), 19 (AEVA s.4) and 20 (AEVA s.3(2)).
- **7 crashes** from `insurance.synth_bundles` (seed 11, n=200), sampled from real DfT STATS19 2024 crash profiles. They cover:
  - clearly avoidable (SYN-11-000)
  - clearly unavoidable on a wet road (SYN-11-003)
  - borderline, including a fatal one (SYN-11-012, SYN-11-105)
  - a serious cut-in with strong evidence (SYN-11-028)
  - a serious claim with ODD status unknown (SYN-11-036)
  - marginally unavoidable (SYN-11-176)

## How each column was decided
**avoidable_by_careful_driver.** A one-dimensional replay written separately from the engine's code (not imported from it).
- **The careful driver:** reacts 1.0 s (fast) to 1.5 s (slow) after the hazard becomes visible to a human (`conflict.t_start`), then brakes at 0.9 × μ × g. Hazards behave as the case states: lead vehicle braking, cut-in after `t_in_path_s`, or stationary.
- **yes** if even the slow driver stops with more than 0.5 m to spare.
- **no** if even the fast driver hits by more than 0.5 m.
- **unsure** otherwise, and whenever the evidence fails integrity checks.
- The 1.0–1.5 s range follows the field reaction-time evidence in `docs/validation.md` (mean about 1.2–1.3 s, 85th percentile about 1.5 s).

**who_pays.** UK law as recorded in `docs/verification.md`:
- **human:**
  - manual mode at the crash
  - a human override in the last seconds
  - an adequate transition demand ignored (the user-in-charge's immunity ends; AV Act 2024)
  - an unauthorised software change by the insured (AEVA s.4)
  - engaging self-driving when inappropriate (AEVA s.3(2))
- **tech:**
  - automated and avoidable by a careful driver
  - a transition demand too short to act on
  - a critical system fault before the crash
  - operating outside the ODD
  - running unapproved software with no sign the insured did it
- **no_fault:** automated, and not avoidable even for a fast careful driver.
- **review:** avoidability unsure, or evidence integrity failed.

**pursue_recovery** (from the tech company):
- **yes:** tech is liable and the evidence is complete. That means verified engagement, inside the ODD, a decision log, and police, CCTV or witness support. This is a human judgement that small clean claims are worth pursuing before proceedings are issued; the engine's own cost model may disagree, which is exactly what the eval should show.
- **pull_logs:** tech is liable but something material is unconfirmed (ODD status, who let it run outside the ODD), or the case is under review.
- **no:** human or no_fault.

## Limits
- **Not independent of the physics.** The labelling replay and the engine's estimator are both kinematic braking models, so agreement on avoidability is partly built in. The legal and recovery columns are the more independent test.
- **Designed cases** have an intended answer. They make a regression set more than an accuracy measure (Jayen's caveat on his draft in `coord/drafts/`).
- **No real narratives**, so these test the rules, not reading messy reports.
- **20 rows is small.** One disagreement moves accuracy by 5 points.
