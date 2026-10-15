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

## 1b. Evidence the industry needs this [Sourced]
Insurers and their advisers are saying, in public, that establishing AV liability and recovering from the tech company is the hard part:
- **Thatcham Research and the ABI** (*Insurer Requirements for Automated Vehicles*, 2024): insurers must meet their obligations under AEVA 2018, and "Timely and unhindered access to data is required."
- **Thatcham Research, principal engineer for ADAS** (Insurance Times, 23 Apr 2026): "there is no mandate for access to data for insurers in the event of an incident"; under the AV Act, insurers "may access the data, it's not a must"; and "an insurer needs to get access to the data just to understand the extreme basics of liability."
- **HCR Law, insurance market analyst** (same article): "Without access to the vehicle's data, building a case for recovery becomes much harder."
- **IUA, director of claims** (same article): "The IUA strongly supports regulation that enshrines the provision of data as a mandatory requirement."
- **Fitch Ratings** (Insurance Business, Sept 2026): AV data plays "a growing role in how underwriters price risk", and cover is moving from personal motor towards commercial product liability.
- **Carpenters Group, claims director** (same article): London's roads "create additional uncertainty for autonomous systems that may make some insurers more cautious."
- **Money moving:** Admiral bought Flock for £80m; Allianz is building claims infrastructure for Waymo in Europe.

**Our answer to that pain:** we give a recovery decision from the evidence an insurer *can* get today (CCTV, police, dashcam, the reported crash), and we say exactly which vehicle data would change it ("pull logs first"). That turns a missing-data problem into a targeted disclosure request.

**What this is not yet:** willingness to pay. These are statements of the problem, not purchase intent. See section 9.

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

## 6b. Addressable market [Sourced anchors, labelled assumptions]
**Anchors.**
- UK motor insurers paid **£11.9bn** of claims in 2025 (ABI) [Sourced].
- The government's CAV market forecast (Transport Systems Catapult, 2017) puts self-driving vehicles (SAE levels 3–5) at **31% of UK new-vehicle sales in 2035** in its central case, with **5%** in the low case and **58%** in the UK-lead case [Sourced; 2017, so dated].
- In the US, insurers recovered **$51.6bn** in auto lines in 2021, and missed subrogation is estimated to cost the industry **$15bn a year** (Bisco & Fier, *Journal of Insurance Regulation*, 2023, citing Harman 2021) [Sourced]. Recovery leakage is a known, large problem before AVs arrive.

**UK fee pool in 2035 [Assumption].** Claims held at 2025 levels.
- AV share of claims is set well below the new-sales share: the fleet turns over slowly, and AVs crash far less per mile (88% and 92% fewer claims in the Swiss Re study).
- The recoverable share is set well below our synthetic engine result (about 70%), on purpose.

| Scenario | AV share of UK motor claims | AV claims paid | Recoverable from AV companies | Recovered for insurers | Our fee | **Fee pool / year** |
|---|---|---|---|---|---|---|
| Low (TSC low case) | 2% | £238m | 20% | £48m | 15% | **£7m** |
| Central | 5% | £595m | 30% | £179m | 17.5% | **£31m** |
| High (TSC UK-lead case) | 10% | £1.19bn | 40% | £476m | 20% | **£95m** |

**How to read it:**
- **The UK alone is a £7m to £95m a year fee pool by 2035,** returning £48m to £476m a year to insurers.
- **The engine is not UK-specific.** Any pay-first-then-recover regime works the same way, so the global wedge is the AV share of a recovery market that is already $51.6bn a year in US auto lines. Each 1% of that is about **$516m recovered a year**.
- **Today is a beachhead, not a market.** About 15 supervised robotaxis in London now, Waymo by end-2026, the full AV Act regime from H2 2027. Revenue in 2026–27 comes from design partners, not volume.

**Go-to-market:**
1. **Design partners now:** a fleet insurer or MGA (e.g. Admiral Pioneer / Flock) and the London company market (IUA members). Free triage on their first AV claims, success fee on recoveries.
2. **Success-fee recoveries** once the regime is live (2027 onwards).
3. **Defence side and reinsurers:** AV companies want to see their own exposure; reinsurers want to price AV portfolios.

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

## 9. What it takes to go green (asks for today)
The problem is documented (1b) and the market is sized (6b). The missing piece is **purchase intent from a buyer**. Two or three conversations on site today would close it:
1. **Who:** a fleet insurer or MGA (Admiral Pioneer / Flock), a London-market claims head (IUA members), Thatcham Research, a claims director (e.g. Carpenters Group), an insurance lawyer (e.g. HCR Law), and any insurer among the judges.
2. **The three questions:**
   - When an AV your client insures causes a crash, who decides today whether to pursue the manufacturer, and on what evidence?
   - Would you pay a success fee on recoveries (we propose 15–20%), a per-claim triage fee, or neither?
   - Would you be a design partner on your first AV claims?
3. **What counts as evidence on stage:** one named quote ("we'd trial this on our first AV claims"), or a design-partner yes. Even one line from a credible insurer turns this section from asserted to validated.

Still open: a UK recovery-agent fee benchmark (none found; US norms are 25–33%), and real paid-claim severities for AV or fleet claims.

## Sources
- Thatcham Research and ABI, *Insurer Requirements for Automated Vehicles* (2024): [PDF](https://www.thatcham.org/wp-content/uploads/2024/05/Thatcham-Research-Insurer-Requirements-For-Automated-Vehicles.pdf)
- Insurance Times, "Are stronger rules on data sharing needed for insurers to deal with driverless car claims?" (23 Apr 2026): [article](https://www.insurancetimes.co.uk/analysis/in-focus-are-stronger-rules-on-data-sharing-needed-for-insurers-to-deal-with-driverless-car-claims/1458350.article)
- ABI 2025 motor claims (£11.9bn): [ABI](https://www.abi.org.uk/news/news-articles/2026/2/11.9-billion-paid-out-in-2025-to-support-motorists-across-2.5-million-claims/)
- Transport Systems Catapult, *Market Forecast for Connected and Autonomous Vehicles* (2017): [GOV.UK PDF](https://assets.publishing.service.gov.uk/media/5a82466aed915d74e3402a89/15780_TSC_Market_Forecast_for_CAV_Report_FINAL.pdf)
- Bisco & Fier, "How's the Recovery? Salvage and Subrogation in the Property Liability Insurance Industry", *Journal of Insurance Regulation* (2023): [NAIC PDF](https://content.naic.org/sites/default/files/cipr-jir-2023-2.pdf)
- Uber and Wayve London launch: [electrive](https://www.electrive.com/2026/09/03/wayve-and-uber-launch-autonomous-rides-in-london/), [The Register](https://www.theregister.com/ai-and-ml/2026/09/04/wayve-and-uber-steal-a-march-on-waymo-with-paid-self-driving-london-rides/5294451), [TechRepublic](https://www.techrepublic.com/article/news-uber-wayve-robotaxi-london-emea-uk/)
- Admiral and Flock, £80m: [Insurance Age](https://www.insuranceage.co.uk/commercial/7957968/admiral-group-acquires-ps80m-digital-fleet-mga-flock), [Osborne Clarke](https://www.osborneclarke.com/news/osborne-clarke-advises-ps80m-acquisition-flock-admiral-group)
- Allianz and Waymo; insurers on the London liability test: [Insurance Business](https://www.insurancebusinessmag.com/uk/news/auto-motor/allianzs-waymo-deal-lands-just-as-londons-own-robotaxi-race-heats-up-590103.aspx), [Insurance Business](https://www.insurancebusinessmag.com/uk/news/auto-motor/ubers-robotaxis-hit-london-streets-as-insurers-watch-a-new-liability-test-588429.aspx)
- AV Act 2024 timeline and safety principles: [GOV.UK consultation](https://www.gov.uk/government/speeches/new-consultation-on-draft-statutory-statement-of-safety-principles-for-automated-vehicles), [Burges Salmon](https://www.burges-salmon.com/articles/102n4rk/automated-vehicles-act-2024-driverless-but-not-directionless-the-dft-consulta/)
- £42bn / 38,000 jobs by 2035: [GOV.UK](https://www.gov.uk/government/news/driving-innovation-38000-jobs-on-the-horizon-as-pilots-of-self-driving-vehicles-fast-tracked)
- Swiss Re / Waymo claims study: [Waymo](https://waymo.com/blog/2024/12/new-swiss-re-study-waymo/), [Repairer Driven News](https://www.repairerdrivennews.com/2025/01/16/waymo-swiss-re-study-finds-waymos-autonomous-driving-safer-than-human-driving/)
- AEVA 2018 ss.2–5: [legislation.gov.uk](https://www.legislation.gov.uk/ukpga/2018/18/part/1)
- Damages-Based Agreements Regulations 2013 reg 4: [legislation.gov.uk](https://www.legislation.gov.uk/uksi/2013/609/regulation/4)
- Recovery fees: [KLS Law (UK, no-win-no-fee)](https://klslaw.co.uk/services/insurance/subrogation/), [MWL (US, 25% / 33%)](https://www.mwl-law.com/faqs/)
- Engine figures: run over `insurance.synth_bundles` seed 11, n=200 on the `insurance` branch (see `finance/` and `docs/assumptions.md` there)
