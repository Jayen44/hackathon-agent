# Assumptions & scenarios (Finance team owns this)

Marking scheme: [hackathon-marking-rubric.png](hackathon-marking-rubric.png). Calculation details: `finance/CLAUDE.md`.

**All data is UK:** UK law, UK claim values and legal costs, and UK crash data (DfT STATS19). No US data is used.

## Assumptions
| Item | Value | Source |
|---|---|---|
| Insurer pays victim first, recovers from liable party | AEVA 2018 s.2 and s.5 | Automated and Electric Vehicles Act 2018 |
| Standard the AV is judged against | Careful and competent human driver | Automated Vehicles Act 2024 |
| P(careful driver avoids) read as P(AV fell below that standard) | Modelling assumption | Team |
| Insurer recovers what the AV company owes the injured party, never more | AEVA s.5(1), s.5(4) | AEVA 2018 (legislation.gov.uk) |
| Only the INJURED PARTY's own fault reduces recovery (`third_party_share`) | Contributory negligence share, a range | AEVA s.3(1); Law Reform (Contributory Negligence) Act 1945 |
| Where that share comes from | The insurer's claim file (agreed or ordered in settling the victim's claim). No default band: unassessed means a 0-100% range and a "pull logs" gate | Decision (issue #7) |
| Applied once only | A paid amount is already net of it (s.3(1)), so it is applied only to table values | AEVA s.3(1) |
| Other drivers' fault does not reduce recovery | AV company liable with them for the whole (reduced) loss | Knowledge: joint and several liability, English tort law |
| Unauthorised software alteration or missed safety-critical update | Not an AV-company recovery: recover from the insured under the policy (`not_av_recovery`); status unknown = flagged before issuing, not a gate | AEVA s.4(1), s.4(4), s.4(6)(b) |
| Severity scale | DfT STATS19: Fatal / Serious / Slight, plus Damage only | DfT reported road casualties definitions |
| Slight injury value | Whiplash tariff GBP 275 to 1,510 (up to 12 months), plus property | SI 2025/615, Table 2 |
| Property damage only | GBP 3,858 average motor claim (proxy) | FCA GI Value Measures 2025 (via secondary source, to verify) |
| Serious injury value | GBP 5,750 to 533,720 general damages only (minor back injury to tetraplegia); care and lost earnings excluded | JCG 18th ed. 7(B)(c)(ii), 2A via Keoghs / Exchange Chambers (verify vs book) |
| Fatal claim value | GBP 15,120 to 46,580: bereavement award + estate PSLA if aware; dependency and funeral excluded | Fatal Accidents Act 1976 s.1A(3) (SI 2020/316); JCG 18th ed. death with full awareness |
| Legal cost of the recovery action (<= £100k) | Fixed recoverable costs, band 2 settled pre-issue to band 4 one-day trial | CPR PD 45 Tables 12 and 14; CPR 26.9 and 26.15 |
| Central legal cost | Band 2, proceedings issued and settled before trial (Table 12 B(2) / Table 14 S4) at the mid claim value, not the average of the two extremes | Design choice: most defended claims settle; no settlement-rate statistic used |
| Legal cost above £100k | TODO | Multi-track has no fixed costs |
| Legal cost is spent whether or not recovery succeeds; no cost-shifting modelled | Simplification | Team |

## Crash data
- Demo crashes are SYNTHETIC (`ukcrash/synthetic.py`), sampled from real UK STATS19 2024 injury collisions (`ukcrash/profile_2024.json`): crash-type mix, severity, speed limit, light, surface, area.
- AV facts (engagement, ODD) and paid amounts are made up and labelled; P(avoid) comes from the simulator.
- There are no public UK self-driving crash reports yet, so STATS19 human-driven crashes are the base and the AV layer is synthetic.
- STATS19 holds injury collisions only, so damage-only crashes are not in the profile.

## Scenarios for the demo
1. Baseline: cut-in, self-driving verified engaged, inside its operating conditions (ODD), both careful drivers avoid it, so pursue with a GBP range.
2. Shock event: the careful-driver models disagree, or Defence counsel's weakest assumption flips the decision, so the agent switches to "pull full vehicle logs first".

## Limitations to state in the demo
- Triage evidence for a claims handler, not a liability ruling or legal advice.
- Synthetic crashes built on UK STATS19; claim amounts are estimates unless the insurer supplies its paid amount.
- Serious and fatal values are general damages only (care, earnings, dependency excluded), so they understate real claims.
- Simulation-to-real gap: a 2D kinematic replay, not full vehicle logs.

Legal regime: the table above assumes the AEVA s.2/s.5 route. No vehicle is listed today, so supervised pilots recover via contribution or CPA instead; see `docs/legal-basis.md` (what we may say in the pitch, and the to-do list).
