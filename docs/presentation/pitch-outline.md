> **Note (decision #32):** the deck is now United States first. Slide-by-slide content below predates that change for the timing, customer and business-case slides; the current deck has 19 slides (a three-year plan slide was added) and uses the sourced figures in `market/MARKET.md`.

# Pitch outline: 5 minutes, live demo

**One line:** when a self-driving car crashes, the UK insurer pays the victim first and may recover from the tech company later. We give the claims team a fast, auditable first read on every crash: who is at fault, how much is recoverable (a GBP range), what to do next, and which deadline is running.

**Customer:** a UK motor insurer's claims and recoveries team (the people who handle subrogation under AEVA 2018 s.5). **Problem:** the evidence sits with the manufacturer, claims are expensive to litigate, and a missed 2-year deadline loses the claim.

## Slide by slide (time, what is shown, rubric criterion)

| # | Time | Slide | Show | Scores on |
|---|---|---|---|---|
| 1 | 0:00 to 0:30 | **The problem.** Insurer pays first (s.2), recovers later (s.5). Evidence held by the AV company, no legal right to the logs, 2-year clock. | One sentence, one crash photo | Business viability, pitch |
| 2 | 0:30 to 1:00 | **Who pays for this.** Insurer recoveries team; value = recovered GBP minus wasted litigation, plus deadlines not missed. Honest timing: no vehicle is on the AEVA list yet; AV Act 2024 regime expected 2027; supervised pilots recover via contribution or CPA. | `docs/legal-basis.md` safe-to-say table | Business viability, responsible design |
| 3 | 1:00 to 1:30 | **How a crash flows (architecture).** Bundle -> integrity -> liability engine -> sim counterfactual (R157 careful drivers A and B) -> finance pricing -> outcome + next steps. Deterministic code makes every number; agents only challenge. | One diagram (use the workflow block in `docs/system-overview.md`) | Agent design, demo clarity |
| 4 | 1:30 to 3:30 | **LIVE DEMO** (below) | Dashboard, then one CLI command | Real output, demo, demo clarity |
| 5 | 3:30 to 4:15 | **The agent team.** Fleet: Lead + Investigator + Reconstructor + Counterfactual analyst work a queue (hand-offs, retries on reconstruction, budget cap, trace). Debate: adjuster vs defence counsel vs rebuttal; a rejected challenge that would flip the decision marks the claim CONTESTED for a human. | Agent run page, one debate | Agent design |
| 6 | 4:15 to 4:45 | **Responsible by construction.** Ranges not points; refuses to price unsourced figures (`cannot_price`); never a liability finding, always "triage evidence"; human sign-off roles; evidence integrity gate; claim text treated as data, never instructions; synthetic data only; no right-to-data claimed. | The disclaimer and a `CONTESTED` or `HUMAN_REVIEW` example | Responsible design |
| 7 | 4:45 to 5:00 | **Ask and next step.** Pilot with one insurer on real settled claims; counsel's multi-track cost budget; wire the live R157 scope tags. | One slide | Business viability |

## Live demo script (about 2 minutes, nothing pre-recorded)

1. **Claims inbox** (dashboard https://accel-claims-dashboard.vercel.app): 27 claims ranked, grouped by decision. Say: "every claim ends in a GBP range and an action."
2. **Open the clean pursue claim** (e.g. the cut-in example): P(avoid) with its interval for careful drivers A and B, AV share, expected recovery low / mid / high, and why.
3. **Open an evidence-gated claim:** show it refuses to pursue yet and names what to request (preservation letter for the logs, then CPR 31.16).
4. **Agent run page:** the Investigator, Reconstructor and Counterfactual analyst hand-offs and the trace. Point at a retry (reconstruction not reproduced, ranges revised).
5. **Debate:** defence counsel's strongest attack ("assume trial-level legal costs"), the rebuttal, and the final decision; show how CONTESTED is triggered.
6. **One terminal command** as proof it is real code, not a mock-up:
   `python -m insurance insurance/examples/21_pursue_cut_in.json --price`
   shows verdict, GBP range, outcome, next steps, deadline and provenance.
7. **Deadline watch** (optional, 15 s): `python -m insurance.watch --dir insurance/examples`.

Rehearse with the sim snapshot already fetched (`python -m insurance.sim_link`) and have the dashboard tab open before you start.

## Marking scheme: how we score on each criterion

| Criterion | Weight | What we claim and show | Gap to close before the pitch |
|---|---|---|---|
| Real output | 20% | End-to-end run on 22 reproducible example bundles (the sim reproduces all of them), live dashboard, CLI command, pytest green | Run the full portfolio live once with the real sim and keep the output as run proof |
| Agent design and architecture | 15% | Two agent systems: fleet team (planning, hand-offs, reconstruction retries, budget cap, trace) and debate (challenge, rebuttal, CONTESTED rule in code). Deterministic engines own all numbers | Fleet still uses its own decision labels: issue #29 switches it to the shared outcomes and `insurance.api.price_claim` |
| Business viability | 20% | Named customer (insurer recoveries team), real problem (s.5 recovery, evidence access, 2-year clock), worked GBP ranges with the legal-cost floor | No demand evidence yet: talk to one insurer or counsel; state timing risk (AEVA list empty) openly. Revenue model unstated: pick one (per-claim fee or portfolio licence) |
| Demo and pitch | 15% | Story arc: problem -> flow -> live crash -> agents -> safeguards -> ask | Time the demo to 2 minutes; one presenter drives, one narrates |
| Demo clarity | 15% | Three numbers per claim (P(avoid), AV share, GBP), one outcome, three next steps | Dashboard still shows old labels (Get more evidence / Don't pursue); say "same as PULL_LOGS / SETTLE" or update after #29 |
| Responsible design | 15% | Ranges, refusal to price unsourced figures, disclaimer on every output, human sign-off roles, integrity gate, prompt-injection rule for claim text, synthetic data, no assumed legal right to data, audit ledger and provenance | Name the misuse risk (using a triage number to deny a claim or pressure a victim) and the control (human decides, outputs are triage evidence) |

## Likely questions (prepare one-line answers)
- **"Is this legal today?"** No vehicle is AEVA-listed, so s.5 pricing is a proxy for pilots; the tool is built for the regime that arrives with the AV Act 2024, and flags the proxy on every claim.
- **"Why trust the number?"** It is a range from published UN R157 reference models, not a legal standard; every result shows its inputs, models and thresholds, and a human signs off.
- **"What if the manufacturer won't share logs?"** The tool says so: it routes to a preservation letter and a CPR 31.16 disclosure request, and shows what the answer would be at a lower evidence tier.
- **"Where does it make money?"** Fewer doomed litigations, faster pursuit of good claims, no missed deadlines; priced per claim or per portfolio (decision pending).
- **"What's synthetic?"** All crash data; the physics and legal figures are sourced and labelled.
