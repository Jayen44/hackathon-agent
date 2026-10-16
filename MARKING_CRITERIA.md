# Marking criteria

Two layers: how the judges score us, and our own internal rubric (the spec for `/claude-api build-eval` and `hillclimb`).

## 1. Judges (Accel)
| Criterion | Weight | What wins it for us |
|---|---|---|
| Real output | 20% | Judges open a live link: real crashes, real video, GBP per claim |
| Agent design and architecture | 15% | Long portfolio run; visible hand-offs; defence counsel vs adjuster |
| Business viability | 20% | UK AV insurers, AEVA 2018 s.5 recovery, priced value of evidence |
| Demo and pitch | 15% | Tier 0 → 1 → 2 story with the 3D side-by-side replay |
| Demo clarity | 15% | One event, one number with its range, one decision |
| Responsible design | 15% | Uncertainty everywhere, red-team agent, triage not ruling, honest label counts |

## 2. Internal rubric
Score automatically wherever possible. No single number without its spread. Each criterion lists its owner.

### A. Data sufficiency: do we know enough to predict? (sim)
- **A1** Required-facts checklist per scenario type (cut-in, lead brake, cut-out). Metric: coverage %.
- **A2** Data sufficiency score (0..1). Below the threshold the output is "get more evidence", never a GBP figure.
- **A3** Every parameter tagged reported / measured / inferred / prior. Pass: majority of decisive params are not prior.

### B. Reconstruction fidelity: does the sim reproduce what happened? (sim)
- **B1** Reproduction rate within 5 attempts (collision, impact type, speed band).
- **B2** Trajectory error vs CitySim ground truth: ADE/FDE in metres. Automatic, no hand labels.
- **B3** Video→trajectory error vs CitySim ground truth (tier 1 quality), metres.

### C. Counterfactual precision: is P(avoid) stable? (sim)
- **C1** Monte Carlo n until CI90 half-width ≤ 0.05.
- **C2** A–B spread reported; a wide spread is flagged as model-dependent.
- **C3** Sensitivity: the single fact that most moves the answer.
- **C4** CI width per evidence tier. Pass: narrows from tier 0 → 1 → 2 on the same event.

### D. Prediction accuracy: are we right? (sim + insurance)
- **D1** External benchmark: published attentive-human reference results on reconstructed real crashes (Waymo / Scanlon et al. 2021; SAE 2026-01-0520 NIEON comparison: 10/16 prevented). TODO: check whether the scenario data is public.
- **D2** SGO weak labels: rules (e.g. AV stationary + struck from rear = not AV-preventable) + Claude labeller, marked as triage, not ground truth.
- **D3** Calibration (Brier score) wherever labels exist.
- **D4** Label quantity honesty: report the 95% CI on accuracy itself (e.g. 20 labels at 75% ≈ 53–89%).

### E. Money (insurance)
- **E1** Every GBP figure is a range with cited claim-value and legal-cost sources.
- **E2** Value of information: GBP value of moving up one evidence tier vs its cost.
- **E3** Decision agreement with labels (pursue / don't / get more evidence).
