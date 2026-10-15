# Business case: Recovery Engine

**One line:** when a robotaxi crashes in the UK, the insurer pays the victim first. Recovery Engine tells the insurer which claims it can recover from the AV company, and for how much.

Status key: **[Sourced]** cited below · **[Engine]** our own model on synthetic UK data · **[Assumption]** illustrative, change it freely. Nothing here is a forecast.

## 1. Customer and problem
**Customer:** UK motor and fleet insurers covering automated vehicles, and the MGAs that write them. The fleet market is consolidating: Admiral bought the digital fleet MGA Flock (insures Uber, Bolt, Amazon and DPD fleets) for **£80m in February 2026** [Sourced]. Allianz has agreed to build insurance and claims infrastructure for Waymo's European robotaxi fleet [Sourced]: insurers are moving now.

**Problem:** under the Automated and Electric Vehicles Act 2018 the insurer pays the injured party when a self-driving vehicle causes a crash (s.2). It can then recover from the AV company (s.5), but only once its own liability is settled, and only if the AV company is liable to the victim [Sourced, legislation.gov.uk]. Today an insurer has three bad options for each claim:
- **Pursue blind:** legal costs with no view of the odds.
- **Pursue nothing:** write off recoverable money.
- **Rely on the AV company's own safety benchmark:** Waymo's "Reference Driver" and the Swiss Re study were commissioned by Waymo [Sourced]. That's a conflict of interest.

**The test in law:** the Automated Vehicles Act 2024 sets the safety standard as a careful and competent human driver [Sourced]. Nobody sells an independent tool that applies that test to a specific crash and turns it into a £ decision.

## 2. What we sell
For every claim, an evidence pack for a human claims handler. It contains:
1. **Who is liable:** human, tech company, no fault, or needs review. Built from the vehicle data, evidence integrity checks, and the AEVA and AV Act rules (s.3(1), s.3(2), s.4, transition demands).
2. **Would a careful and competent driver have avoided it:** two careful-driver models (UN R157), Monte Carlo replays, with a 90% interval.
3. **What it's worth:** expected recovery in £ (low, central, high), net of UK legal costs (CPR PD 45 fixed recoverable costs), with sourced claim values (whiplash tariff, Judicial College Guidelines, Fatal Accidents Act).
4. **A decision:** pursue / pull the vehicle logs first / don't pursue. The agents argue against their own result (adjuster vs defence counsel), and contested claims go to a human.

## 3. Why now
- **London robotaxis are live.** Uber and Wayve began paid, supervised robotaxi rides in London on about **3 September 2026**, with about 15 cars and 140,000+ riders opted in; Wayve expects thousands of rides a week. Waymo plans London by end-2026 [Sourced].
- **The legal regime is arriving.** The Automated Vehicles Act 2024 is due to be fully in force in **H2 2027**, after the statement of safety principles goes to Parliament [Sourced]. Insurers need recovery capability before the first contested claims, not after.
- **Policy backing:** the government estimates the self-driving sector could be worth up to **£42bn to the UK economy by 2035** [Sourced].

## 4. The money: what our engine finds [Engine]
200 synthetic UK robotaxi claims, built from real DfT STATS19 2024 crash profiles. The engine runs two placeholder careful-driver models and real UK legal and claim-value rules.

| | Claims | Central recoverable | Note |
|---|---|---|---|
| Total paid out by the insurer | 200 | £8.27m paid | synthetic paid amounts |
| **Pursue now** | 73 (70 slight, 1 serious, 2 fatal) | £0.45m recovered, **£0.17m net** of our legal costs | small claims barely clear their costs |
| **Serious claims over £100k** | 19 | **£5.87m** before legal costs (avg £309k) | the real prize; needs a counsel budget, since there are no fixed costs above £100k |
| Pull logs first / review | 43 | n/a | the engine names the missing evidence |
| Don't pursue (no driving fault) | 21 | £0 | saves wasted legal spend |

**Reading:** the value is concentrated. About **93% of the recoverable money sits in serious-injury claims** (19 of 200). A single serious claim recovered (about £300k) is worth more than every small claim in the portfolio combined. The product earns its keep on the high-severity tail, plus avoided legal spend on claims that shouldn't be pursued.

*Caveats:* synthetic claims; placeholder driver models that are on the optimistic side (so 113 of 200 come out tech-liable); serious and fatal values are general damages only, so real claims run higher. Treat the shape (value concentrated in severe claims) as the finding, not the totals.

## 5. Business model
- **Success fee on recoveries** (primary). Recovery work in the UK is commonly no-win-no-fee [Sourced: KLS Law]. A damages-based agreement may take at most **50% of sums recovered** for non-injury claims (SI 2013/609 reg 4(3)) [Sourced]; US subrogation norms are 25% before suit and 33% after [Sourced, US]. **We'd price at 15–20%** [Assumption], below law-firm contingency, because our cost per claim is software, not hours.
  - On the engine portfolio: 20% of the £5.87m serious-claim pool would be about **£1.2m** of fees per 200 claims [Assumption × Engine].
- **Per-claim triage fee** (secondary), for insurers who want every claim triaged, including those we tell them not to pursue. £X per claim [Assumption], to be set after insurer interviews.
- **Expansion:**
  - AV companies and operators, defence side: the same engine shows them their exposure.
  - Reinsurers: pricing AV portfolios.
  - Regulators: incident review under the AV Act 2024.

## 6. Unit economics at fleet scale [Assumption, labelled]
- **Claim frequency:** the Swiss Re study found Waymo had 9 property-damage and 2 bodily-injury liability claims over 25.3m autonomous miles, about **0.43 claims per million miles**, 88% and 92% below human benchmarks [Sourced; Waymo-commissioned].
- **At 50,000 miles a year per robotaxi** [Assumption], 1,000 robotaxis would generate about **22 liability claims a year**. At our synthetic average paid of about £41k per claim [Engine], that's about £0.9m paid a year.
- **What that means:** the early UK market is small in claim count. The pitch is not volume. It is that each claim is high-stakes, contested and opaque (the insurer has no vehicle data). Value per claim is high and grows with fleet size and with the 2027 regime.

## 7. Competition
| Who | What they do | Gap we fill |
|---|---|---|
| AV company benchmarks (Waymo Reference Driver, Swiss Re study) | Fleet-level safety claims | Not independent; not per claim; no £ decision |
| Crash reconstruction for insurers (e.g. Nexar) | Video reconstruction for human-driver claims | Not the AV careful-driver test; not a recovery decision |
| Incumbent claims infrastructure (Allianz for Waymo) | Claims handling for the AV operator's insurer | Sits with one operator; we serve the victim's insurer seeking recovery |
| Recovery law firms | Manual, hourly or no-win-no-fee | Slow and expensive per claim; no counterfactual simulation |

## 8. Risks and how we answer them
- **Small early volume.** We focus on severe claims and price on success, so revenue tracks value. We expand to defence-side and reinsurer use.
- **No access to vehicle data before 2027.** We work from what an insurer has (CCTV, police, dashcam) at a lower evidence tier, and say what the vehicle logs would change ("pull logs first" is a product output, not a failure).
- **Untested law.** There is no UK AV recovery case law yet. Every output is triage, not a ruling. The proxy (careful-driver avoidance standing in for liability) is stated.
- **Model validity.** UN R157 careful-driver models with intervals, both models shown. Defence-counsel agent attacks our own result. Calibration roadmap against real claims.

## 9. What we still need (asks for today)
1. **Two or three insurer conversations on site.** Would you pay a success fee or a per-claim fee? What share of AV claims would you pursue today? Who decides?
2. **Confirm the success-fee level** against UK recovery-agent terms (no UK figure found yet).
3. **Real paid-claim severities** for AV or fleet claims, to replace the synthetic portfolio.

## Sources
- Uber and Wayve London launch: [electrive](https://www.electrive.com/2026/09/03/wayve-and-uber-launch-autonomous-rides-in-london/), [The Register](https://www.theregister.com/ai-and-ml/2026/09/04/wayve-and-uber-steal-a-march-on-waymo-with-paid-self-driving-london-rides/5294451), [TechRepublic](https://www.techrepublic.com/article/news-uber-wayve-robotaxi-london-emea-uk/)
- Admiral and Flock, £80m: [Insurance Age](https://www.insuranceage.co.uk/commercial/7957968/admiral-group-acquires-ps80m-digital-fleet-mga-flock), [Osborne Clarke](https://www.osborneclarke.com/news/osborne-clarke-advises-ps80m-acquisition-flock-admiral-group)
- Allianz and Waymo; insurers on the London liability test: [Insurance Business](https://www.insurancebusinessmag.com/uk/news/auto-motor/allianzs-waymo-deal-lands-just-as-londons-own-robotaxi-race-heats-up-590103.aspx), [Insurance Business](https://www.insurancebusinessmag.com/uk/news/auto-motor/ubers-robotaxis-hit-london-streets-as-insurers-watch-a-new-liability-test-588429.aspx)
- AV Act 2024 timeline and safety principles: [GOV.UK consultation](https://www.gov.uk/government/speeches/new-consultation-on-draft-statutory-statement-of-safety-principles-for-automated-vehicles), [Burges Salmon](https://www.burges-salmon.com/articles/102n4rk/automated-vehicles-act-2024-driverless-but-not-directionless-the-dft-consulta/)
- £42bn / 38,000 jobs by 2035: [GOV.UK](https://www.gov.uk/government/news/driving-innovation-38000-jobs-on-the-horizon-as-pilots-of-self-driving-vehicles-fast-tracked)
- Swiss Re / Waymo claims study: [Waymo](https://waymo.com/blog/2024/12/new-swiss-re-study-waymo/), [Repairer Driven News](https://www.repairerdrivennews.com/2025/01/16/waymo-swiss-re-study-finds-waymos-autonomous-driving-safer-than-human-driving/)
- AEVA 2018 ss.2–5: [legislation.gov.uk](https://www.legislation.gov.uk/ukpga/2018/18/part/1)
- Damages-Based Agreements Regulations 2013 reg 4: [legislation.gov.uk](https://www.legislation.gov.uk/uksi/2013/609/regulation/4)
- Recovery fees: [KLS Law (UK, no-win-no-fee)](https://klslaw.co.uk/services/insurance/subrogation/), [MWL (US, 25% / 33%)](https://www.mwl-law.com/faqs/)
- Engine figures: `python -m insurance.portfolio`-style run over `insurance.synth_bundles` seed 11, n=200 (see `finance/`, `docs/assumptions.md`)
