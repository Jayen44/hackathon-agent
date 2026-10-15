# Business case: Recovery Engine

**One line:** after a crash involving an automated vehicle (AV), the insurer that paid out needs to know whether it has a recovery case against someone else, and what it is worth. Recovery Engine gives a per-claim recovery decision in money, with the evidence behind it.

Status key: **[Sourced]** cited below · **[Engine]** our own model on synthetic data · **[Assumption]** illustrative.
**One set of numbers:** market sizing and financials live in [`market/MARKET.md`](https://github.com/Jayen44/hackathon-agent/blob/sim/market/MARKET.md) (Vakhtang, sourced). This document quotes those figures and does not add its own.
**Say carefully:** follow issue #32 and [`sim/LEGAL_BASIS.md`](https://github.com/Jayen44/hackathon-agent/blob/sim/sim/LEGAL_BASIS.md). Say "recovery case" and "triage evidence"; never "liable", "defective" or "caused" about a named company.

## 1. Positioning: US first, UK when the AV Act regime is live
- **US now.** Driverless fleets already run at scale. Waymo gives about 500k paid rides a week and drives about 200M driverless miles a year, roughly 5 times the miles of a private car. Recovery between insurers is an existing workflow: US inter-company subrogation demands of almost **$27bn** in 2025, with recovery firms charging 15–33% [Sourced, via MARKET.md].
- **UK when the regime is live.** No vehicle is on the AEVA 2018 self-driving list yet. The London Uber and Wayve service (launched September 2026, about 15 vehicles) runs as private hire with a safety driver responsible. So the AEVA "insurer pays, then recovers" route (s.2 and s.5) does **not** apply today. Today's UK routes are a contribution claim (Civil Liability (Contribution) Act 1978) or the Consumer Protection Act 1987 [Sourced, LEGAL_BASIS.md]. The Automated Vehicles Act 2024 framework is expected from late 2027 [Sourced]. That is when the AEVA route opens and the UK becomes our second market.
- **Benchmark:** the AV Act 2024 s.2(2)(a) wording, "careful and competent human drivers". We use the UN R157 Annex 3 reference driver models (A and B, always quoted together) as guidance, not as a legal standard.

## 2. Customer and problem
**Customers:**
- Motor and fleet insurers, and MGAs, whose policyholders are hit by, or involved with, AVs.
- AV operators' own insurers, recovering from *human* drivers. Those drivers were at fault in about 87% of crashes in one sample of AV crashes [Sourced, small sample, via MARKET.md].
- AV operators themselves (defence, reserving, incident review).

The fleet market is moving: Admiral bought the fleet MGA Flock for £80m (Feb 2026), and Allianz is building claims infrastructure for Waymo in Europe [Sourced].

**Problem:** deciding whether a single AV crash is a recovery case is slow, opaque and data-starved. The insurer rarely has the vehicle's data. AV companies publish fleet-level safety benchmarks they commissioned themselves, but nothing applies an independent careful-driver test to *one* claim and turns it into a money decision.

## 3. Evidence the industry needs this [Sourced]
- **Thatcham Research and the ABI** (2024): "Timely and unhindered access to data is required."
- **Thatcham Research** (Insurance Times, 23 Apr 2026): "there is no mandate for access to data for insurers in the event of an incident"; "an insurer needs to get access to the data just to understand the extreme basics of liability."
- **HCR Law** (same article): "Without access to the vehicle's data, building a case for recovery becomes much harder."
- **IUA, director of claims** (same article): supports making data provision mandatory.
- **Fitch Ratings** (Sept 2026): cover is moving from personal motor towards commercial product liability.

Insurers have **no legal right** to AV data today. In the UK the route is a pre-action disclosure application (CPR 31.16). Our "pull the logs first" output names exactly which data to ask for and why.

These quotes show the problem, not purchase intent. See section 9.

## 4. What we sell
For every claim, triage evidence for a human claims handler:
1. **Reconstruction:** the crash rebuilt from the evidence the insurer has (CCTV, police, dashcam, reports). It is checked against what happened; the sim reproduces 88% of real crashes in the 100-Car study.
2. **Careful-driver test:** UN R157 careful drivers A and B in the AV's place, with 90% intervals.
3. **Money:** expected recovery (low, central, high) after legal costs, with sourced claim values and costs.
4. **A decision with a self-challenge:** pursue, get the logs first, or don't pursue. A defence-counsel agent attacks the result, the adjuster answers, and contested claims go to a human.

**Proof on real crashes** [Sourced, eval/REAL_CRASH_EVAL.md on `sim`]: on real rear-end crashes from the 100-Car study, careful driver A would avoid 5 of 8 (62%, CI90 35–84%) and careful driver B 8 of 8 (100%, CI90 75–100%).

## 5. Market (from `market/MARKET.md`)
- **Per-claim recovery triage is a small market today.**
  - US ADS + L2 TAM is **$0.4–5.6M in 2026** and **$1.4–45M in 2030** (low to high).
  - In the 2030 base case: TAM about $7.7M, SAM $1.2M, SOM $0.25M.
  - The UK is about zero until late 2027.
- **The scalable revenue is subscriptions.** The engine is sold to the whole AV liability chain: operators (10–15 accounts), their insurers and reinsurers, and fleet MGAs (40–60 target accounts worldwide). At £40–80k a year, 15 accounts give £0.6–1.2M ARR [Assumption].
- **Near-term volume:** Level 2 driver-assist claims (5–30k engaged-system claims a year in the US), priced as screening, because liability arguments are weaker there.
- **Upside:** liability is shifting from drivers to manufacturers (Swiss Re, Accenture). Every extra 10k US robotaxis adds about 240–2,300 claims a year.

## 6. Business model and unit economics (from `market/MARKET.md`)
- **Pricing:** per claim £300 (ADS deep analysis) or £75 (L2 screen); a 10% success fee on recoveries (below recovery firms' 15–33%); a platform subscription at £40–80k a year.
- **Cost per claim:**
  - The Claude agent run costs **about $0.25–0.27, measured** in our prototype, debate included.
  - Human QA (about 1 hour) is roughly 99% of the cost.
  - Gross margin is **about 87%** at £300, and about 89–90% blended.
- **Break-even:** a lean 7-person team (about £1.0M a year) needs about 3,850 ADS claims a year on per-claim fees alone, or **about 14 subscription customers at £80k**.

## 7. Our engine on a synthetic portfolio [Engine]
On 200 synthetic UK-profile claims (DfT STATS19 2024 crash patterns, priced under the AEVA route *as it will apply once vehicles are authorised*):
- The value is concentrated: about 93% of the recoverable money sits in the 19 serious-injury claims.
- A single serious claim recovered is worth more than all the small claims combined.

This shows the *shape* (value concentrated in severe claims), not a forecast.

## 8. Competition
| Who | What they do | Gap we fill |
|---|---|---|
| AV company benchmarks (Waymo Reference Driver, Swiss Re study) | Fleet-level safety claims | Not independent; not per claim; no money decision |
| Crash reconstruction for insurers (e.g. Nexar) | Video reconstruction for human-driver claims | Not the careful-driver test; not a recovery decision |
| Incumbent claims infrastructure (Allianz for Waymo) | Claims handling for one operator's insurer | Sits with one operator; we serve any insurer seeking recovery |
| Recovery firms | Manual, 15–33% contingency | Slow per claim; no counterfactual simulation |

## 9. Risks and what would make this green
**Risks:**
- An AV-only, per-claim, UK-first business does not work before 2030. Hence US first, subscriptions and the L2 wedge.
- AVs crash far less (88–92% fewer claims), which is good for society and lowers per-claim volume.
- Operators control the logs.
- Forecasts have slipped before.
- There is no AV recovery case law yet.

Every output is triage, not a ruling.

**To go green, the missing piece is purchase intent.** One or two conversations today with an insurer, MGA, recovery firm or AV operator:
1. Who decides today whether to pursue a recovery after an AV crash, and on what evidence?
2. Would you pay per claim, a success fee or a subscription?
3. Would you be a design partner?

One named quote on a slide moves this from asserted to validated.

## Sources
- Market, fleet, claims, subrogation and pricing figures: [`market/MARKET.md`](https://github.com/Jayen44/hackathon-agent/blob/sim/market/MARKET.md), sources [1]–[43] listed there.
- Legal positioning: issue #32 and [`sim/LEGAL_BASIS.md`](https://github.com/Jayen44/hackathon-agent/blob/sim/sim/LEGAL_BASIS.md); [AEVA 2018 Part 1](https://www.legislation.gov.uk/ukpga/2018/18/part/1).
- Real-crash evaluation: [`eval/REAL_CRASH_EVAL.md`](https://github.com/Jayen44/hackathon-agent/blob/sim/eval/REAL_CRASH_EVAL.md).
- Industry evidence: [Thatcham Research & ABI (2024)](https://www.thatcham.org/wp-content/uploads/2024/05/Thatcham-Research-Insurer-Requirements-For-Automated-Vehicles.pdf); [Insurance Times (23 Apr 2026)](https://www.insurancetimes.co.uk/analysis/in-focus-are-stronger-rules-on-data-sharing-needed-for-insurers-to-deal-with-driverless-car-claims/1458350.article); [Insurance Business (Sept 2026)](https://www.insurancebusinessmag.com/uk/news/auto-motor/ubers-robotaxis-hit-london-streets-as-insurers-watch-a-new-liability-test-588429.aspx).
- Market moves: [Admiral and Flock (Insurance Age)](https://www.insuranceage.co.uk/commercial/7957968/admiral-group-acquires-ps80m-digital-fleet-mga-flock); [Allianz and Waymo (Insurance Business)](https://www.insurancebusinessmag.com/uk/news/auto-motor/allianzs-waymo-deal-lands-just-as-londons-own-robotaxi-race-heats-up-590103.aspx).
- London launch: [electrive](https://www.electrive.com/2026/09/03/wayve-and-uber-launch-autonomous-rides-in-london/).
