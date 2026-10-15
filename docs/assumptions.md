# Assumptions & scenarios (Finance team owns this)

Marking scheme: [hackathon-marking-rubric.png](hackathon-marking-rubric.png). Calculation details: `finance/CLAUDE.md`.

## Assumptions
| Item | Value | Source |
|---|---|---|
| Insurer pays victim first, recovers from liable party | AEVA 2018 s.2 and s.5 | Automated and Electric Vehicles Act 2018 |
| Standard the AV is judged against | Careful and competent human driver | Automated Vehicles Act 2024 |
| P(careful driver avoids) read as P(AV fell below that standard) | Modelling assumption | Team |
| Other party's fault reduces recovery proportionally | Contributory negligence | Law Reform (Contributory Negligence) Act 1945 |
| Minor injury value | Whiplash tariff GBP 275 to 1,510 (up to 12 months), plus property | SI 2025/615, Table 2 |
| Property damage only | GBP 3,858 average motor claim (proxy) | FCA GI Value Measures 2025 (via secondary source, to verify) |
| Serious injury value | GBP 5,750 to 533,720 general damages only (minor back injury to tetraplegia); care and lost earnings excluded | JCG 18th ed. 7(B)(c)(ii), 2A via Keoghs / Exchange Chambers (verify vs book) |
| Fatal claim value | GBP 15,120 to 46,580: bereavement award + estate PSLA if aware; dependency and funeral excluded | Fatal Accidents Act 1976 s.1A(3) (SI 2020/316); JCG 18th ed. death with full awareness |
| Moderate injury value | TODO | JCG 18th ed. |
| Legal cost of the recovery action (<= £100k) | Fixed recoverable costs, band 2 settled pre-issue to band 4 one-day trial | CPR PD 45 Tables 12 and 14; CPR 26.9 and 26.15 |
| Legal cost above £100k | TODO | Multi-track has no fixed costs |
| Legal cost is spent whether or not recovery succeeds; no cost-shifting modelled | Simplification | Team |

## Crash data
- Demo crashes are SYNTHETIC (`ukcrash/synthetic.py`), sampled from real UK STATS19 2024 injury collisions (`ukcrash/profile_2024.json`): crash-type mix, severity, speed limit, light, surface, area.
- AV facts (engagement, ODD) and paid amounts are made up and labelled; P(avoid) comes from the simulator.
- STATS19 holds injury collisions only, so damage-only crashes are not in the profile.

## Scenarios for the demo
1. Baseline: cut-in, ADS verified engaged, within ODD, both careful drivers avoid it, so pursue with a GBP range.
2. Shock event: the careful-driver models disagree, or Defence counsel's weakest assumption flips the decision, so the agent switches to "pull full vehicle logs first".

## Limitations to state in the demo
- Triage evidence for a claims handler, not a liability ruling or legal advice.
- US crash data (NHTSA SGO) priced with UK figures; claim amounts are estimates unless the insurer supplies its paid amount.
- Simulation-to-real gap: a 2D kinematic replay, not full vehicle logs.
