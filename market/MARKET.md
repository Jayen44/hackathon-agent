# Recovery Engine: market sizing and business case
Prepared 15 Oct 2026. Every figure has a source tag [n] (list at the end) or is marked **ASSUMPTION** or **DERIVED** (arithmetic on sourced numbers). Where sources are secondary they are flagged. FX: GBP 1 = USD 1.33 (**ASSUMPTION**, approximate 2025-26 rate, check before printing).

**Headline honesty note:** the per-claim AV recovery pool is real but **small today**. It reaches one lean team's break-even on its own only in the high-adoption scenario around 2030. The business works before 2030 only if we add (1) a subscription product for AV operators and their insurers, and (2) the Level 2 driver-assist wedge. UK volumes are about zero until the Automated Vehicles Act 2024 regime is live (full framework expected late 2027 [17]). All 2030 numbers depend on forecasts.

---

## 1. Market context

### 1a. Robotaxi fleets and miles (US unless stated)
| Operator | Fleet | Activity | Date | Src |
|---|---|---|---|---|
| Waymo | ~3,500-3,800 vehicles (secondary estimates) | 400k paid rides/week (Feb 2026); 500k/week, 10 cities (Mar 2026); target 1M/week by end-2026 | Feb-May 2026 | [1][2][3] |
| Waymo | rider-only miles, cumulative: 127M (Sep 2025), 170.7M (Dec 2025), 271.3M (Jun 2026) | **DERIVED: about 200M miles/yr run-rate in H1 2026; 53-57k miles per vehicle per year** | Jun 2026 | [4][5] |
| Zoox | about 100 vehicles (exec. statement, single report) | ~2M autonomous miles, 350k riders cumulative; paid rides in Las Vegas from 10 Aug 2026; NHTSA exemption up to 2,500 vehicles/yr | Mar-Aug 2026 | [6][7] |
| Tesla Robotaxi | 20-59 unsupervised vehicles (counts vary); >1M unsupervised miles cumulative | scale-up deferred to FSD v15 (late 2026 / early 2027) | May-Jun 2026 | [8][9] |
| Baidu Apollo Go (China/ME, not our market) | 22M+ cumulative rides; 350k+ weekly peak (Mar 2026); 3.2M driverless rides Q1 2026 | | Q1 2026 | [10] |
| Uber + Wayve London | 15 vehicles, supervised, TfL private-hire licence, safety driver responsible | launched Sep 2026 | Sep 2026 | [11] |
| US commercial robotaxis (Goldman Sachs) | >1,500 in 5 cities (GS count, lower than Waymo estimates above) | | Apr 2026 | [12] |

Compare: an average US registered vehicle drives **11,071 miles/yr** (FHWA 2024) [13]. A robotaxi drives about **5x** that.

### 1b. AV crash and claim rates
- **Swiss Re x Waymo (25.3M rider-only miles, Dec 2024):** 9 property damage (PD) + 2 bodily injury (BI) liability claims, against a human baseline of 78 PD + 26 BI over the same miles. That is 88% fewer PD and 92% fewer BI claims. Against 2018-2021 cars with ADAS: 86% and 90% fewer. Both BI claims were still open. [14]
  - **DERIVED rates:** Waymo 0.36 PD + 0.08 BI = **0.43 liability claims per million miles**. Human baseline 3.08 + 1.03 = **4.11 per million miles**.
- **Waymo Safety Hub (271.3M miles to Jun 2026):** 82% fewer injury crashes, 95% fewer serious-injury-or-worse crashes, 82% fewer airbag-deployment crashes than a human benchmark (Waymo-published). [4]
- **Fault:** a police-report sample of 71 Phoenix crashes found Waymo at fault in about 13% (local TV investigation, small sample) [15]. Most AV crashes are therefore *other party at fault*, which is a recovery opportunity for the AV operator's insurer as well.
- **NHTSA SGO:** NHTSA charts run to 17 Feb 2026. Order amended Apr 2025, effective 16 Jun 2025, with eased reporting [16]. Secondary counts: 2,150 reports analysed (398 ADS, 1,752 ADAS), of which Waymo filed 1,080 (2020 to early 2025) [18]. A law-firm count gives 5,202 ADS+ADAS reports to 17 Nov 2025 [19]. NHTSA's PE24016 Waymo probe counted 367 incidents, 109 of them crashes [20]. **TODO:** take the exact current counts from the SGO CSV in our ingest.

### 1c. Regular-car baseline: claim frequency and severity
| | US | UK |
|---|---|---|
| Vehicle miles/yr | 3.294 trillion (2024) [13] | 336.2bn all motor vehicles; 256.1bn cars and taxis (GB 2024) [21] |
| Registered vehicles | 297.5M (2024) [13] | not retrieved |
| Claim frequency | BI liability 0.80, PD liability 2.50 claims per 100 insured car-years (ISO 2024) [22] | 2.5M private-car claims (2025) [23] |
| Claims per million miles | **4.11 liability claims** (Swiss Re human baseline) [14] | **DERIVED: about 9.8, all claim types** (2.5M / 256.1bn car miles) |
| Liability claims per year | **DERIVED: 9.8M** (3.3% x 297.5M, assumes all insured) **to 13.5M** (4.11 x 3.294T miles) | n/a |
| Average severity | BI liability $28,278; PD liability $6,770 (ISO via III, 2024) [22]. Q2 2025 BI $29,100 per injured party (Verisk, secondary) [24] | **DERIVED: £4,760 per claim** (£11.9bn / 2.5M). Accidental damage claim £3,699 (Q1 2026) [25] |
| Total paid | **DERIVED: about $165bn liability** (13.5M x $12.1k mix) | £11.9bn motor claims paid 2025 (£7.5bn vehicle damage) [23]; record £11.7bn in 2024 [26] |
| Premium | n/a | Motor GWP £22.3bn 2024 (Milliman, from SFCR filings) [27]; average premium £564 (2025) [23] |

### 1d. Subrogation and recovery market
- **Arbitration Forums (2025):** members filed 1.1M arbitration disputes and 2.3M subrogation demands worth almost **$27bn** [28]. Most AF disputes are auto: over 80% (2008 figure) [29].
- **US recoveries across auto lines:** about **$51.6bn** in 2021 (Ethos Risk / Callahan & Blaine, secondary, no primary cited) [30].
- **Missed subrogation:** about 15% of P&C claims closed with a missed subrogation opportunity, $15-20bn per year (vendor estimate) [31]. For auto, 3-5% of claims have unidentified subrogation potential (Afni, 2012) [32].
- **Recovery-firm fees (contingency):** 15-20% for cut-price vendors; 25% pre-suit and 33⅓% if suit is filed (MWL schedule) [33][34]; UK example 15% pre-proceedings plus disbursements (Clyde & Co) [35]. **Benchmark range: 15-33%.**

### 1e. Forecasts to 2030 (wide range: show it)
- **Goldman Sachs (Apr 2026):** US commercial robotaxis about **35,000 by 2030**, about 8% of US rideshare, US robotaxi market $7bn revenue (Insights), with research raising the 2030 US market to $19bn. Global $415bn by 2035, about 6M vehicles [12][36].
- Other figures attributed to GS: 500k robotaxis (TipRanks) and 1M (Daily Upside, scope unclear). Treat these as unverified [36].
- **McKinsey AV survey (Jan 2025, 91 experts):** robotaxis at scale globally slip to **2030** (from 2029) [37].
- **Our scenarios (ASSUMPTION, anchored on GS):** US robotaxis in 2030: **low 20,000 / base 35,000 / high 100,000**. Per-vehicle miles 55k/yr (DERIVED from Waymo). That gives 1.1 / 1.93 / 5.5bn AV miles in 2030.
- UK: DfT says AV Act full rollout from the second half of 2027 [38]. A June 2026 ministerial letter says the full framework is expected by late 2027 [17]. DfT estimates the UK industry at "up to" £42bn by 2035 [38].
- Insurance shift: Swiss Re expects automation to cut about $600bn from motor premiums by 2040 [39]. Accenture/Stevens expect personal motor GWP down 40% and product liability up 14% by 2040 [40]. Liability is moving toward manufacturers, which is our thesis.

### 1f. Level 2 ADAS (near-term wedge)
- Over 50% of new US vehicles have adaptive cruise and lane centering (PARTS/MITRE, Oct 2024) [41]. L2 was 46.5% of US new-car sales in H1 2022 (Counterpoint) [42].
- Tesla FSD (Supervised): 8bn cumulative miles by Feb 2026, about 10bn miles/yr pace. Tesla reports 830 "major collisions" on FSD in 12 months to Feb 2026, one per 5.3M miles, against a US average of one per 0.66M miles. These are Tesla's own figures [43].
- An L2 crash is reportable to the SGO only if it involved a vulnerable road user, a fatality, a tow-away, an airbag deployment or hospital transport [16]. Liability sits mainly with the supervising driver, so **product-liability recovery arguments are weaker**. The wedge is triage and screening, not guaranteed recovery.

---

## 2. AV claim volume by analogy with regular cars

**Formula:** AV claims/yr = AV miles x liability-claim rate per million miles. Recoverable pool = claims x average claim value x P(pursue) x P(success).
- Rate (a), human baseline, **upper bound**: 4.11 per million miles [14]. Value mix $12,147 (DERIVED from 78 PD / 26 BI at ISO severities [22]).
- Rate (b), AV observed, Swiss Re/Waymo: 0.43 per million miles [14]. Value mix $10,681 (DERIVED from 9 PD / 2 BI).
- P(pursue) 40% x P(success) 70% = 28% (**ASSUMPTION**: a contested, novel liability area, with a careful-driver test favourable on clear cut-in and lead-braking cases).

| | US regular cars (2024) | US AVs 2026 (base) | US AVs 2030 low / base / high | UK AVs 2026 |
|---|---|---|---|---|
| Fleet | 297.5M [13] | ~4,000 (ASSUMPTION from [1][6][8][12]) | 20k / 35k / 100k | 15 supervised [11] |
| Miles/yr | 3.294T [13] | ~0.21bn (DERIVED [4]) | 1.10 / 1.93 / 5.5bn | ~0 |
| Claims per million miles | 4.11 [14] | 0.43 (b) to 4.11 (a) | same | n/a |
| Liability claims/yr | 9.8-13.5M (DERIVED) | **91 (b) to 863 (a)** | (b) 478 / 836 / 2,391; (a) 4,521 / 7,913 / 22,608 | ~0 (PHV licence, safety driver) |
| Claim value/yr | ~$165bn (DERIVED) | $1.0M (b) to $10.5M (a) | (b) $5.1M / $8.9M / $25.5M; (a) $55M / $96M / $275M | ~0 |
| Recoverable pool (x28%) | AF demands $27bn [28] | **$0.27M (b) to $2.9M (a)** | (b) $1.4M / $2.5M / $7.2M; (a) $15M / $27M / $77M | ~0 |

**Level 2 wedge (US), clearly weaker liability:**
- L2-engaged miles (ASSUMPTION): 2026 at 10 / 20 / 30bn (Tesla FSD about 10bn [43], plus other OEMs). 2030 at 20 / 60 / 150bn.
- Claim rate while engaged (ASSUMPTION): 0.5 / 0.75 / 1.0 per million miles. Tesla's major-collision rate is about 0.19 per million miles [43]; minor claims are taken as 3-5x that.
- L2 claims/yr: **2026 at 5k / 15k / 30k. 2030 at 10k / 45k / 150k.**
- Recoverable pool at P(pursue) 10% x P(success) 40% (ASSUMPTION): 2026 at $2.4M / $7.3M / $14.6M. 2030 at $4.9M / $22M / $73M.
- **Today the L2 pool is about 15-20x the ADS pool by claim count.**

---

## 3. TAM / SAM / SOM (annual revenue to us, US; UK about 0 until late 2027)
- **Prices:** ADS claim $200 / $400 / $1,000. L2 screen $50 / $100 / $150 (ASSUMPTION; low / base / high scenario uses matching price).
- **TAM** = ADS claims at rate (a) x price + all L2 claims x price.
- **SAM** = ADS claims at rate (b) x price (claims actually filed against AVs) + 20% of L2 claims with a plausible product-defect angle (ASSUMPTION) x price.
- **SOM** = our share of SAM: 2026 at 0 / 2% / 5%; 2030 at 10 / 20 / 30% (ASSUMPTION).

| | TAM | SAM | SOM |
|---|---|---|---|
| 2026 low / base / high | $0.37M / $1.85M / $5.6M | $0.06M / $0.34M / $1.0M | $0 / $7k / $51k |
| 2030 low / base / high | $1.4M / $7.7M / $45M | $0.2M / $1.2M / $6.9M | $20k / $0.25M / $2.1M |

**Top-down cross-check (ADS only):** AV share of US vehicle miles x AF subrogation demands $27bn [28] x recovery-firm fee 15-33% [33-35].
- 2026: 0.21bn / 3.294T = 0.006% of miles, so about $1.7M of demands and **$0.26-0.57M of fees**. Bottom-up ADS TAM is $0.35M, which agrees.
- 2030 base: 0.059% of miles, so $15.8M of demands and **$2.4-5.2M of fees**. Bottom-up ADS TAM is $3.2M, which agrees.
- 2030 high: $6.8-14.9M of fees, against a bottom-up figure of $22.6M.

**Reading:** a pure per-claim product is a **single-digit-million-dollar market in 2030** (tens of millions in the high case). The scalable revenue is **platform subscriptions**: AV operators (Waymo, Zoox, Tesla, May Mobility, Nuro, Avride, Wayve, Pony/WeRide international, about 10-15 accounts), their insurers and reinsurers, and fleet MGAs (ASSUMPTION: 40-60 target accounts worldwide). At £40-80k/yr each, 15 accounts give £0.6-1.2M ARR. This uses the same reconstruction engine for defence, reserving and incident review on *every* AV incident, not only claims. Waymo alone files hundreds of SGO reports a year [18].

---

## 4. Business model and unit economics
- **Pricing options:**
  - (1) Per-claim fee: ADS deep analysis £300 (about $400); L2 screen £75.
  - (2) Success fee of 10% of the amount recovered. This undercuts recovery firms' 15-33% [33-35] because we are the triage and evidence layer, not litigation counsel.
  - (3) Platform subscription £40-80k/yr: trace, evidence packs, a reserving/recoverability map, and use by AV operators for defence.
- **Cost per claim (ADS):**
  - Claude agent run **$0.27, measured in our prototype today, including the defence-counsel debate** (about £0.20).
  - Monte Carlo on Modal CPU: about $0.01-0.05 (ASSUMPTION, cents).
  - Human claims-analyst QA: 1 hr at £40 loaded (ASSUMPTION), which is about 99% of the cost.
  - Total about **£40.3**, so **gross margin 87%** at £300.
- **Cost per L2 screen:** 10 min QA, about £7.3, so **GM 90%** at £75.
- **Subscription:** 10% hosting and support (ASSUMPTION), so GM 90%.
- **Blended GM about 89-90%.** AI compute is negligible; the cost driver is human review, which we keep because responsible design requires a human in the loop.

---

## 5. Three-year projection (GBP, ASSUMPTIONS throughout)
| | 2027 | 2028 | 2029 |
|---|---|---|---|
| Paying customers (subscription) | 3 at £40k | 8 at £60k | 15 at £80k |
| ADS claims analysed (at £300) | 150 | 400 | 900 |
| L2 claims screened (at £75) | 1,000 | 4,000 | 10,000 |
| **Revenue** | **£240k** | **£900k** | **£2.22M** |
| of which subscription | 50% | 53% | 54% |
| Gross margin | 89% | 90% | 90% |
| Headcount (£110k loaded) | 6 | 8 | 11 |
| Opex (staff + £250-400k other: legal, PI cover, SOC 2, travel) | £910k | £1.18M | £1.61M |
| **Burn** (opex − gross profit) | **£695k** | **£373k** | **−£381k (profit)** |

Sanity checks:
- ADS 900 claims in 2029 is about 18% of the 2029 base upper-bound pool (4,974). L2 10,000 claims is about 27% of the 2029 base L2 pool. Both are aggressive but feasible with 2-3 large carriers.
- If subscriptions slip one year, break-even moves to 2030.

**Seed GBP 2.0M (range 1.5-2.5M)** covers cumulative burn of about £1.07M to the end of 2028, plus Q4-2026 build (about £0.2M) and a buffer of about 30%. That is about 30 months of runway.

**Milestones:**
- (1) Q1 2027: 3 paid US pilots (a fleet insurer or MGA, a recovery firm, an AV-operator insurer).
- (2) Back-test against 500+ SGO crashes, with eval accuracy at or above 85% against adjuster labels.
- (3) First recovered dollar attributed to an evidence pack.
- (4) UK readiness for the AV Act regime (late 2027), including insurer data-sharing.
- (5) £1M ARR by end-2028, then Series A.

---

## 6. VERDICT: does the model work?
- **Break-even:** a lean 7-person team costs about £1.0M/yr (ASSUMPTION). Covering it on ADS per-claim fees alone needs **about 3,850 claims/yr** at £300 and 87% GM (DERIVED). With subscriptions it needs **about 14 customers at £80k**, or a mix.

When does the US ADS pool alone (no subscriptions, no L2) reach 3,850 claims/yr? (Fleet path is an ASSUMPTION interpolated to the GS 2030 figure.)

| Scenario (fleet 2026 to 2030) | Rate (b) AV-observed | Rate (a) human upper bound, 100% share | (a) at a realistic 25% share |
|---|---|---|---|
| Low (3k to 20k) | never by 2030 (478 in 2030) | 2030 (4,522) | never by 2030 (1,130) |
| Base (4k to 35k) | never by 2030 (837) | 2029 (4,974) | never by 2030 (1,978) |
| High (4.5k to 100k) | never by 2030 (2,392) | 2028 (6,330) | 2030 (5,652) |

**Blunt answer:**
1. **An AV-only, per-claim, UK-first business does not work before 2030.** In 2026 the US ADS pool is about 90-860 claims and $0.3-2.9M recoverable. The UK pool is about zero: 15 supervised vehicles under private-hire licensing, and the AV Act authorisation regime is not in force.
2. **It works if we do three things:**
   - (a) **US first**, where about 4,000 driverless vehicles already drive about 200M miles/yr.
   - (b) **Sell the engine as a subscription** to the whole AV liability chain. That includes AV operators' own insurers recovering from *human* drivers, who are at fault in most AV crashes (about 87% in one sample [15]), plus defence, reserving and incident review.
   - (c) **Use the L2 wedge for volume today**: 5-30k engaged-system claims/yr. Liability arguments are weaker there, so it is priced as screening.
3. **The upside is structural.** Liability is shifting from drivers to manufacturers (Swiss Re, Accenture [39][40]). Robotaxis drive about 5x the miles of private cars. Every 10k extra US robotaxis add about 2,300 claims/yr at the human-baseline rate, or about 240 at the observed rate. The high case (GS-plus, 100k vehicles) makes ADS-only viable around 2029-30.
4. **Key risks:**
   - Low AV claim frequency is good for society and bad for per-claim volume. The Waymo data shows 88-92% fewer claims.
   - Operators control the logs.
   - Fault data is sparse.
   - The forecasts have slipped before (McKinsey, one to two years [37]).

---

## 7. Slide-ready headlines
1. **Robotaxis are here at scale:** Waymo does 500k paid rides a week and about 200M driverless miles a year; about 5x the miles of a private car.¹
2. **The liability shift is the opportunity:** a careful human would have caused about 8-10x more claims (Swiss Re/Waymo: 88% fewer PD, 92% fewer BI). The few AV claims that remain are contested and high-stakes.²
3. **Recovery is already a $27bn workflow:** US inter-company subrogation demands in 2025; recovery firms charge 15-33%.³
4. **The 2030 pool:** 35k US robotaxis (GS) means about 0.8-7.9k AV liability claims/yr and a $2.5-27M recoverable pool. In the high case it is up to $77M.⁴
5. **Unit economics:** $0.27 of AI compute per claim (measured), about 89% gross margin, priced at £300 a claim or 10% of recovery, about a third of recovery-firm fees.⁵
6. **Plan:** US first, UK when the AV Act regime goes live (late 2027). £2M seed to £2.2M revenue and break-even in 2029.⁶

¹ [2][4][13] ² [14] ³ [28][33][34] ⁴ [12][14][22], DERIVED ⁵ prototype measurement, [33-35] ⁶ ASSUMPTIONS §5, [17]

### Chart-ready CSV
```csv
year,scenario,tam_usd_m,sam_usd_m,som_usd_m
2026,low,0.37,0.06,0.00
2026,base,1.85,0.34,0.007
2026,high,5.57,1.01,0.05
2030,low,1.40,0.20,0.02
2030,base,7.67,1.24,0.25
2030,high,45.11,6.89,2.07
```
```csv
year,revenue_gbp_k,subscription_gbp_k,ads_claims_gbp_k,l2_screen_gbp_k,gross_margin_pct,opex_gbp_k,burn_gbp_k,customers,headcount
2027,240,120,45,75,89.4,910,695,3,6
2028,900,480,120,300,89.6,1180,373,8,8
2029,2220,1200,270,750,89.7,1610,-381,15,11
```
```csv
year,scenario,av_miles_bn,claims_obs_rate,claims_human_rate,recoverable_obs_usd_m,recoverable_human_usd_m
2026,base,0.21,91,863,0.27,2.9
2030,low,1.10,478,4521,1.43,15.4
2030,base,1.93,836,7913,2.50,26.9
2030,high,5.50,2391,22608,7.15,76.9
```

---

## Sources (accessed 15 Oct 2026; "secondary" = not the primary publisher)
1. Claims Journal, Waymo co-CEO, 400k weekly rides, 1M target (12 Feb 2026): https://amp.claimsjournal.com/news/national/2026/02/12/335668.htm
2. 500k weekly rides, 10 cities (secondary): https://www.noqta.tn/en/news/waymo-500k-weekly-rides-robotaxi-10-cities-2026
3. Fleet about 3,791 by May 2026 (forecasting site, secondary): https://futuresearch.ai/app/p/a/waymo-weekly-paid-rides-q4-2026
4. Waymo Safety Impact hub (271.3M rider-only miles to Jun 2026): https://waymo.com/safety/impact/
5. Waymo hub earlier snapshots, 127M to Sep 2025 and 170.7M to Dec 2025 (via search of the same page): https://waymo.com/safety/impact/
6. Zoox expansion, about 100 vehicles, 2M miles (Mar 2026): https://techcrunch.com/2026/03/24/zoox-brings-its-robotaxis-to-austin-and-miami
7. Zoox paid rides from 10 Aug 2026: https://lasvegassun.com/news/2026/aug/06/free-rides-no-more-zoox-robotaxi-service-to-begin/
8. Tesla robotaxi fleet 42 in Texas (Jun 2026): https://www.electrive.com/2026/06/02/tesla-robotaxi-fleet-in-texas-reaches-only-42-vehicles/
9. Tesla 1M unsupervised miles: https://driveteslacanada.ca/news/tesla-robotaxi-1-million-miles-unsupervised-driving/
10. Apollo Go Q1 2026 (secondary): https://aiwiki.ai/wiki/apollo_go
11. Uber + Wayve London supervised launch: https://www.techrepublic.com/article/news-uber-wayve-robotaxi-london-emea-uk/ and https://www.thestar.com.my/tech/tech-news/2026/08/06/uber-wayve-win-licenses-for-supervised-robotaxis-in-london
12. Goldman Sachs Insights, robotaxis $400bn by 2035, 35k US by 2030: https://www.goldmansachs.com/insights/articles/robotaxis-to-become-a-400-billion-dollar-market-in-2035
13. FHWA Highway Statistics 2024 VM-1: https://www.fhwa.dot.gov/policyinformation/statistics/2024/vm1.cfm
14. Waymo blog, Swiss Re study (Dec 2024): https://waymo.com/blog/2024/12/new-swiss-re-study-waymo/
15. InvestigateTV / Gray TV, Waymo at fault in 13% of 71 Phoenix crashes (Jan 2026): https://www.wafb.com/2026/01/09/crashes-involving-self-driving-cars-raise-questions-about-safety-accountabiity
16. NHTSA SGO crash reporting: https://www.nhtsa.gov/SGOCrashReporting
17. DfT ministerial correspondence, full framework late 2027 (24 Jun 2026, secondary host): https://www.beyondthevote.co.uk/committee-publication/709463cc-74fd-4f6b-884a-3eda065f8469
18. Bumper analysis of NHTSA reports (Dec 2025, secondary): https://www.bumper.ca/analysis/self-driving-car-crashes-triple-in-2025/
19. Craft Law Firm SGO tally (secondary): https://www.craftlawfirm.com/autonomous-vehicle-accidents-2019-2024-crash-data/
20. NHTSA PE24016 closing: https://static.nhtsa.gov/odi/inv/2024/INCLA-PE24016-72139.pdf
21. DfT road traffic estimates GB 2024: https://www.gov.uk/government/statistics/road-traffic-estimates-in-great-britain-2024/road-traffic-estimates-in-great-britain-2024-headline-figures
22. Triple-I auto facts and statistics (ISO frequency and severity): https://www.iii.org/fact-statistic/facts-statistics-auto-insurance
23. ABI, £11.9bn paid in 2025, 2.5M claims (11 Feb 2026): https://www.abi.org.uk/media-hub/news-post/119-billion-paid-out-in-2025-to-support-motorists-across-25-million-claims
24. MoneyGeek citing Verisk BI severity (secondary): https://www.moneygeek.com/insurance/auto/auto-claims-down-injury-costs-rising/
25. ABI Q1 2026 accidental damage claim £3,699 (via LBC/ABI coverage): https://www.lbc.co.uk/business/315a9f5eac9c45fa828a7539ae546ace/
26. LBC/ABI, record £11.7bn 2024: https://www.lbc.co.uk/business/f52f07d3ff8a4ce49ec58b766f8b28a4
27. Milliman UK motor profitability YE2024 (GWP £22.3bn): https://www.milliman.com/en/insight/uk-motor-insurance-profitability-year-end-2024
28. Arbitration Forums, about us (2025 volumes): https://homedev06.arbfile.org/about-us
29. PropertyCasualty360 (2008), over 80% of disputes are auto: https://propertycasualty360.com/2008/11/12/arbitration-could-save-insurers-millions
30. Callahan & Blaine, $51.6bn recoveries 2021 (secondary, no primary cited): https://www.callahan-law.com/amount-recovered-through-subrogation-annually-us/
31. PropertyCasualty360 (Jan 2026), 15% missed, $15-20bn: https://www.propertycasualty360.com/amp/2026/01/26/the-hidden-drain-on-casualty-claims/
32. Ethos Risk / Afni subrogation stats: https://ethosrisk.com/blog/claims-investigations-and-subrogation-recoveries/
33. MWL, fee arrangement 25% / 33⅓%: https://www.mwl-law.com/faqs/what-fee-arrangement-does-mwl-use-for-subrogation/
34. MWL, cut-rate vendors 15-20%: https://www.mwl-law.com/when-cheaper-feels-better-but-isnt-the-psychology-behind-subrogations-costliest-mistake/
35. Clyde & Co subrogated recoveries, 15% pre-proceedings: https://www.clydeco.com/getattachment/88a04f79-d400-4ace-9ef9-6705e6aed9fd/Clyde-Co-Westlink-JLV-Subrogated-Recoveries_English_05-07-22.pdf?lang=en-GB
36. GS figures reported elsewhere (unverified scope): https://www.tipranks.com/news/tesla-or-pony-ai-goldman-sachs-chooses-the-superior-robotaxi-stock-to-buy and https://www.thedailyupside.com/technology/artificial-intelligence/uber-waymo-and-tesla-accelerate-into-an-autonomous-future/
37. McKinsey AV survey 2025 (via summary): https://movemnt.net/latest-mckinsey-report-concludes-autonomous-technology-is-developing-rapidly-but-the-future-is-still-in-flux/
38. DfT, pilots fast-tracked, Act from second half of 2027, £42bn by 2035: https://www.gov.uk/government/news/driving-innovation-38000-jobs-on-the-horizon-as-pilots-of-self-driving-vehicles-fast-tracked
39. Swiss Re sigma 2040, motor premiums about -$600bn from automation (via Insurance Journal): https://www.insurancejournal.com/news/international/2021/09/08/630635.htm
40. GlobalData citing Accenture/Stevens: https://www.globenewswire.com/news-release/2024/05/15/2882130/0/en/Autonomous-Vehicles-in-Insurance-Thematic-Intelligence-Report-2024-Product-Liability-Market-Projected-to-Surge-14-by-2040-Amid-Autonomous-Vehicle-Boom.html
41. PARTS/MITRE ADAS penetration (Oct 2024): https://www.repairerdrivennews.com/2024/10/04/ten-adas-features-surpass-50-newer-vehicle-market-share/
42. Counterpoint, L2 46.5% H1 2022: https://www.counterpointresearch.com/insight/adas-penetration-crosses-70-us-h1-2022-level-2-share-46-5
43. Tesla FSD safety stats, 8.2bn miles (Tesla-reported, secondary): https://driveteslacanada.ca/news/tesla-releases-new-fsd-safety-stats-after-crossing-8-2-billion-miles-driven/

**Not verified / TODO before the slide goes out:** exact current SGO ADS and L2 counts (take from our ingest CSV); Waymo's official fleet size; Baidu Q2 2026 ride count (sources conflict, so it is omitted); UK licensed-vehicle count; GBP/USD rate.
