# Legal basis: what we may say, and what the product must do about it

Summary of Vakhtang's research note `sim/LEGAL_BASIS.md` (branch `sim`, status 15 Oct 2026; full quotes and URLs are there). **V** = primary source verified, **S** = secondary, **U** = unverified. Research, not legal advice: a UK lawyer must review before it goes in a customer contract or report.

## 1. Pitch: safe to say / must not say
| Safe to say | Must NOT say (why) |
|---|---|
| UK law sets the benchmark we test against: AV Act 2024 s.2(2)(a), "careful and competent human drivers" (V). | "Today's London robotaxis are covered by the 2018 Act." The AEVA list of self-driving vehicles is empty (gov.uk, V) and the Uber + Wayve service has a safety driver (S), so s.2 does not apply. |
| Under AEVA the insurer pays the victim first (s.2), then recovers from anyone else liable (s.5), within 2 years of settlement (LA 1980 s.10A) (V). | "Our models are the legal standard." R157 Annex 3 is "Guidance", scoped to motorway-type ALKS. Say "a published regulatory reference model". |
| Nobody defines the careful driver as a runnable model; R157 Annex 3 is the only published reference, and we run both models as a bracket (V). | "The AV Act 2024 is in force." Authorisation, safety principles and user-in-charge immunity are still prospective; full implementation expected H2 2027 (S). |
| We use public data only (NHTSA SGO, UK STATS19 profile). | "The AV caused / is liable / was defective." Say "recovery case" and "triage evidence"; every £ figure is an expected value with a spread. |
| | "Insurers have a legal right to the AV's data." None is in force (Law Commission Rec 74 is a recommendation). Route today: pre-action disclosure, CPR 31.16. |
| | "The UN ADS Regulation is in force." Not before late Jan 2027 (V). |

## 2. What this means for the recovery model
- **The recovery case is derivative (s.5):** the insurer must show the other party *would have been liable to the victim*. P(careful driver avoids) is evidence towards that, not the whole answer. Recovery is capped at that party's liability (s.5(4)) and at the payout (s.5(3)). Our AV-share calculation already caps at the claim value; it does not yet model P(liable to the victim) separately.
- **Today's real routes are not s.5.** With no listed vehicles, supervised pilots recover via contribution (Civil Liability (Contribution) Act 1978, 2 years from judgment or agreed payment) or the Consumer Protection Act 1987 (3 years from knowledge, 10-year longstop). s.6(5) bars a 1978 contribution claim where s.5 applies. The legal-cost and limitation maths differ per route.
- **The benchmark is not the civil test.** "Careful and competent" is the AV Act authorisation standard and the RTA ss.2A/3ZA criminal wording; civil negligence uses the common-law reasonable-driver standard (case law not researched, U).
- **R157 scope gap:** Annex 3 covers cut-in, cut-out and lead deceleration on divided, pedestrian-free roads up to 130 km/h. Junctions, pedestrians, cyclists and parking crashes are outside it. PM1 models an alert ADAS-assisted driver, so it is optimistic for a typical driver.
- **Claim-value scope (s.2(3)):** exclude the AV's own damage, goods carried for hire and the insured's property; cap property damage at the RTA s.145(4)(b) amount; for CPA drop non-private property and claims of £275 or less.

## 3. Product to-do, with current status
| # | Change | Status |
|---|---|---|
| 1 | Benchmark wording "careful and competent human driver (AVA 2024 s.2(2)(a)); R157 Annex 3 is guidance" | Docs fixed here; check dashboard/agent prompts |
| 2 | `regime` and `recovery_route` per claim (AEVA_listed / authorised / conventional; s.5 / contribution / CPA / policy s.4) | **Built** (`insurance/legal.py`, bundle `legal.regime` / `legal.recovery_route`; notes on every result; price still uses the s.5 proxy) |
| 3 | P(success) = P(party liable to victim), not only P(avoid) | **Built** as an input: `legal.p_liable_to_victim` [low, mid, high] scales P(avoid) in `bridge.py`; unset = flagged as not assessed. Needs a real source for the value |
| 4 | Claim-value scope (s.2(3), CPA exclusions) | Not built |
| 5 | Tag `r157_scenario_in_scope` / `r157_road_context_in_scope`, lower confidence when false | Not built (sim side) |
| 6 | "Typical driver" sensitivity row for PM1 optimism | Not built; placeholder values need a source |
| 7 | AEVA s.4 checklist (software version, missed safety-critical updates, unauthorised changes) | Built (`software_status`, `not_av_recovery`) |
| 8 | AEVA s.3(2) check (engaged outside ODD by the person in charge) | Built (flagged in verdict exclusions) |
| 9 | Limitation clocks ("days to deadline") per claim | **Built** (`limitation_deadline`; needs `legal.settlement_date` / `knowledge_date`; shown in notes and as first resolution step, URGENT under 90 days) |
| 10 | Data access: preservation letter + CPR 31.16 summary instead of "pull logs" | **Built** (preservation letter, then CPR 31.16, no assumed right to data) |
| 11 | Report disclaimer: AVA 2024 mostly not in force, SGO data unverified, R157 used outside scope where flagged | **Built** (`engine.DISCLAIMER`) |
| 12 | Say "ADS-engaged", not "self-driving", for unauthorised vehicles (AVA s.78) | Done in `insurance/` (report label, engine text); agent prompts not audited |

## 4. Open questions for a lawyer (abridged)
1. Supervised pilots: who is the victim's defendant (driver, PHV operator, Uber, Wayve), and is contribution against the AV developer realistic?
2. Is ADS software, including OTA updates, a "product" under CPA s.1(2), and who is the producer?
3. Does s.5 "any other person liable" survive a time-barred CPA claim by the victim?
4. Can a careful-driver simulation be expert evidence under CPR Part 35?
5. Data protection role once real UK claim files are uploaded (Data (Use and Access) Act 2025).
6. Will the final Statement of Safety Principles adopt a quantitative benchmark?
