# Verification of assumptions (checked 15 Oct 2026)

Status key: **Confirmed** (primary source read), **Confirmed-secondary** (reputable secondary source only),
**Partly** (some of it checked), **Not found** (still a TODO), **Our choice** (a modelling decision, not a fact).
Search summaries were used for several items; anything marked secondary should be checked against the primary before it goes in a pitch.

## Law
| Claim in our docs/code | Status | What the source says | Source |
|---|---|---|---|
| Insurer pays the victim first when an automated vehicle drives itself and causes an accident (AEVA 2018 s.2) | **Confirmed** | s.2(1): the insurer is liable for the damage. Applies to vehicles on the Secretary of State's s.1 list, driving themselves, in Great Britain. Cannot be excluded by the policy, except per s.4. | [AEVA 2018 Part 1](https://www.legislation.gov.uk/ukpga/2018/18/part/1) |
| Insurer can recover from others liable (s.5) | **Confirmed, with limits** | Only after the insurer's liability is *settled* (judgment, award or enforceable agreement). The other person must be *liable to the injured party*; recovery is capped at that liability. No Civil Liability (Contribution) Act 1978 claim. | same |
| Fault reduction for the injured party's own conduct | **Confirmed** | s.3(1): reduce per the Law Reform (Contributory Negligence) Act 1945. | same |
| Person in charge loses cover if the accident was wholly due to their negligence in letting the car drive itself when inappropriate | **Confirmed** (new to our docs) | s.3(2) | same |
| Insurer can exclude/limit for unauthorised software changes or not installing safety-critical updates | **Confirmed** (new to our docs) | s.4 | same |
| AV Act 2024: AVs judged against a "careful and competent human driver" | **Confirmed-secondary** | s.2 requires a statement of safety principles aimed at a level of safety at least equal to careful and competent human drivers. Draft statement consulted on 17 Jun to 9 Sep 2026; to be laid before Parliament in 2027; full framework targeted for H2 2027. | [Burges Salmon](https://www.burges-salmon.com/articles/102n4rk/automated-vehicles-act-2024-driverless-but-not-directionless-the-dft-consulta/), [GOV.UK](https://www.gov.uk/government/speeches/new-consultation-on-draft-statutory-statement-of-safety-principles-for-automated-vehicles) |
| User-in-charge is not liable for the manner of driving while the feature is engaged, except after a transition demand and the transition period ended | **Confirmed-secondary** | AV Act 2024 ss.46-49 | [AV Act 2024](https://www.legislation.gov.uk/ukpga/2024/10/contents) |

**Important caveat (our choice, not a fact):** "careful and competent human driver" is the *regulatory* benchmark for authorising a vehicle. It is not the civil test under AEVA s.5, which asks whether someone is *liable to the injured party* (for example negligence or product liability). Reading P(careful driver avoids) as P(AV fell below the standard) is a proxy. Antonio's `docs/assumptions.md` already flags this as a modelling assumption; keep it in the pitch.

## Money
| Claim | Status | Detail | Source |
|---|---|---|---|
| Whiplash tariff GBP 275 / 565 / 965 / 1,510 / 2,335 / 3,445 / 4,830 (whiplash only, from 31 May 2025) | **Confirmed** | Matches `finance/tables.py` exactly. About a 15% uplift on 2021. Next review due by 22 May 2027. | [SI 2025/615](https://www.legislation.gov.uk/uksi/2025/615/made) |
| Mapping "Minor" SGO severity to the whiplash tariff + average claim | **Our choice** | The tariff covers whiplash pain, suffering and loss of amenity only. Antonio flagged this as an assumption. | |
| FCA average motor claim GBP 3,858 (2025) | **Confirmed-secondary** | Up from GBP 3,764 in 2024. All claim types, so a rough proxy for property damage. | [Insurance Business](https://www.insurancebusinessmag.com/uk/news/property-insurance/motor-insurance-premiums-fall-7-in-2025-as-claims-costs-eat-into-a-bigger-share-of-the-pot-583193.aspx), [FCA data page](https://www.fca.org.uk/data/general-insurance-value-measures-data-2025) |
| JCG 18th edition brackets (Moderate / Serious / Fatality) | **Not found** | Edition published 9 Apr 2026, about 8.26% uplift on the 17th (RPI Aug 2025). The bracket figures were not in any source I could read. Leave as TODO. | [Exchange Chambers](https://www.exchangechambers.co.uk/judicial-college-guidelines-18th-edition-more-than-just-inflation/), [TG Chambers](https://tgchambers.com/2026/04/publication-of-the-18th-edition-of-the-judicial-college-guidelines/) |
| Legal cost of the recovery action from CPR Part 45 fixed recoverable costs | **Partly** | Intermediate track (GBP 25k-100k) is Table 14 of PD 45; original Stage 1 is GBP 1,600 + 3% (Band 1) up to GBP 9,300 + 8% (Band 4), and a later amending PD uprates them. Fast-track Table 12 not retrieved. **Caveat:** FRC are what a winning party can *recover* from the loser, not what an insurer spends suing a manufacturer; large product-liability recoveries are likely multi-track. | [Table 14 copy](https://www.harrison-drury.com/wp-content/uploads/2023/09/Table-14-Fixed-Recoverable-Costs.pdf), [Forbes Solicitors](https://forbessolicitors.co.uk/articles/fixed-recoverable-costs-from-1-october-2023) |

## Data (NHTSA Standing General Order)
Checked against the official [SGO-2021-01 Data Element Definitions](https://static.nhtsa.gov/odi/ffdd/sgo-2021-01/SGO-2021-01_Data_Element_Definitions.pdf) (dictionary dated 17 Aug 2026).

| Field | Status | Detail |
|---|---|---|
| Field 22 engagement status | **Confirmed** | Verified Engaged, Alleged Engaged, Verified Not Engaged, Unknown, see Narrative. Finance's gates use the right strings. **Fixed:** our bridge sent `"Unknown"`; it now sends `"Unknown, see Narrative"`. |
| Field 73 Highest Injury Severity Alleged | **Confirmed** | All 10 keys in `finance/tables.py` match the official values exactly. Now pinned by `tests/test_bridge.py`. |
| Field 113 Within ODD? | **Confirmed** | Yes, No, see Narrative, Unknown, see Narrative, Exiting ODD. **Fixed** the same way. Entries can be `[REDACTED, MAY CONTAIN CONFIDENTIAL BUSINESS INFORMATION]` (CBI), which finance already handles. |
| Reporting rule | **Confirmed-secondary** | Crash reportable if the ADS was in use within 30 s of the crash. NHTSA amended the order (third amendment, April 2025); the current thresholds were not checked. |

## Technical assumptions in `insurance/`
| Assumption | Status | Detail |
|---|---|---|
| Minimum 10 s handover warning (`Policy.min_handover_s`) | **Weakly grounded** | UN R157 says a minimum risk manoeuvre may start *at the earliest* 10 s after a transition demand. That is a rule for the system's fallback timing, not a standard for how long a human needs. R157 also covers ALKS (lane keeping), not urban robotaxis. Treat 10 s as illustrative. Source: [R157 summary](https://regulations.ai/regulations/RAI-IO-UNECE-R157-2021) and a DLR excerpt of the text. |
| DSSAD data kept at least 6 months | **Confirmed-secondary** | R157 / [DVR statement](https://dvr.de/ueber-uns/resolutions/statement-by-the-german-road-safety-council-dvr-on-edr-and-dssad). Harmonised data elements and access rules are incomplete. |
| Human reaction time 0.7 to 1.5 s, mode 1.0 s (`HumanParams`) | **Plausible but on the optimistic side** | Green: about 0.7 s when braking is expected, about 1.5 s for a surprise. Olson and Sivak (1986): unexpected object, mean about 1.1 s, 85th percentile 1.35 to 1.5 s. Field studies of unaware drivers: mean 1.2 to 1.3 s, 85th percentile 1.8 to 1.9 s. Our 95th percentile is about 1.4 s, below the field 85th percentile. A wider range would make "slow human" more common and push borderline cases from "tech company" toward "no fault". Sources: [Green summary via ISDA](https://isdacenter.org/reaction-time/), [SWOV](https://swov.nl/en/publicatie/drivers-brake-reaction-times). Secondary summaries of the original papers. |
| Waymo NIEON as a "competent driver" benchmark | **Confirmed** (it exists) | Waymo's own model; always attentive, so more demanding than a typical human. [Waymo](https://waymo.com/blog/2022/09/benchmarking-av-safety/) |

See `docs/validation.md` for the maths checks and the sensitivity of verdicts to these assumptions. Friction coefficients (dry 0.7, wet 0.4, snow/ice 0.2) and the 9 m/s^2 limit are **Knowledge** (standard physics); a search did not return a citable source.

## Open items
1. Decide whether to widen the human reaction-time range (see above). Not changed yet, because it shifts verdicts.
2. Antonio: JCG brackets and the legal-cost basis (and whether FRC is the right proxy).
3. Vakhtang: R157 Annex 3 parameters; read them from the regulation text, not from summaries.
4. Check current SGO reporting thresholds after the April 2025 amendment.
5. Confirm that the target vehicles are on the AEVA s.1 list (s.2 only applies to listed vehicles).
