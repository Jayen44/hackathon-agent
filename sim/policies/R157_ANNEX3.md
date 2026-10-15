# UN R157 Annex 3: careful-driver reference models (transcription for review)

Status: transcribed by Claude from the official UN document, **needs human review (Vakhtang) before use on stage**.

## Source

- Document: **ECE/TRANS/WP.29/2022/59/Rev.1**, "Proposal for the 01 series of amendments to UN Regulation No. 157 (Automated Lane Keeping Systems)", adopted by GRVA at its 13th session, submitted to WP.29 187th session (Geneva, 21-24 June 2022). It reproduces the full regulation text, including Annex 3 "Guidance on Traffic disturbance critical scenarios for ALKS" (pages 40-60 of the PDF).
- URL (UN Official Document System): https://documents.un.org/api/symbol/access?s=ECE/TRANS/WP.29/2022/59/Rev.1&l=en&t=pdf (resolves to the GE.22-08135 PDF).
- unece.org (R157e.pdf, the consolidated text) returned HTTP 403 to automated download, so the consolidated version was **not** checked. Later supplements to the 01 series could have edited Annex 3; check the consolidated R157e.pdf by hand before relying on it.
- Cross-check: the original regulation (ECE/TRANS/WP.29/2020/81, https://documents.un.org/api/symbol/access?s=ECE/TRANS/WP.29/2020/81&l=en&t=pdf) has the same Performance model 1 values (0.375 m, 0.4 s, 0.75 s, 0.6 s to 0.774G, 2 s, 5 m/s2) and **no** Performance model 2, which arrived with the 01 series.
- Second source, checked by Vakhtang and Claude on 15 Oct 2026 (local copy `R157e.pdf` / `R157e.md`, not committed): **E/ECE/TRANS/505/Rev.3/Add.156**, 4 March 2021, UN Regulation No. 157 original version (in force 22 January 2021; authentic text ECE/TRANS/WP.29/2020/81). There the model sits in **Annex 4, Appendix 3** "Guidance on Traffic disturbance critical scenarios for ALKS", Table 1 and paras 3.4.1-3.4.3 (same wording as Annex 3 paras 3.3.2.1-3.3.2.3 of the 01 series). Every Performance model 1 value above matches, **including** the "0.6 seconds to 0.85G" full-wrap row (derived from UN R152 AEBS), which contradicts the earlier note that the 0.85 g row arrived only with the 01 series. The unexplained "2sec*" asterisk is in the 2021 text too. Performance model 2 (FSM) is absent from the 2021 text, so cite B as "UN R157, 01 series of amendments".
- Formulas in para 3.4 are typeset images; they were read from the rendered PDF pages 57-59, not from text extraction.

## Performance model 1 (careful_a.py, "CCDM")

Para 3.3.1: "the avoidance capability of the driver model is assumed to be only by braking. The driver model is separated into the following three segments: "Perception"; "Decision"; and, "Reaction"."

| Parameter | Value | Unit | Paragraph | Verbatim quote |
|---|---|---|---|---|
| Risk perception point, lane change (cut-in, cut-out) | 0.375 | m | Annex 3 Table 1 | "Deviation of the centre of a vehicle over 0.375m from the centre of the driving lane" |
| Lateral wandering distance (cut-in) | 0.375 | m | 3.3.2.1 | "The lateral wandering distance the vehicle will normally wander within the lane is 0.375m." / "The perceived boundary for cut-in occurs when the vehicle exceeds the normal lateral wandering distance (possibly prior to actual lane change)" |
| Lateral wandering distance (cut-out) | 0.375 | m | 3.3.2.2 | same wording as 3.3.2.1, "The perceived boundary for cut-out occurs when the vehicle exceeds the normal lateral wandering distance" |
| Risk perception point, deceleration | qualitative | - | Table 1 | "Deceleration ratio of preceding vehicle and following distance of ego vehicle" |
| Deceleration trigger | 5 | m/s2 | 3.3.2.3 | "The risk perception time [a] begins when the leading vehicle exceeds a deceleration threshold 5m/s2." |
| Risk evaluation / perception time [a] | 0.4 | s | Table 1; 3.3.2.1-3.3.2.3 | "Risk evaluation time 0.4 seconds"; "a.= lateral movement speed x Risk perception time [a] (0.4sec)"; "The risk perception time [a] is 0.4 seconds" |
| Perception finished to deceleration start | 0.75 | s | Table 1 | "Time duration from having finished perception until starting deceleration 0.75 seconds" (Figure 1: accelerator release + foot transfer) |
| Brake build-up and max decel | 0.6 s to 0.774 g | s, g | Table 1 | "Jerking time to full deceleration (road friction 1.0) 0.6 seconds to 0.774g" |
| Brake after full wrap of cut-in vehicle | 0.6 s to 0.85 g | s, g | Table 1 | "Jerking time to full deceleration (after full wrap of ego vehicle and cut-in vehicle, road friction 1.0) 0.6 seconds to 0.85g" |
| Cut-in danger threshold | TTC 2 | s | 3.3.2.1 | "2sec* is specified as the maximum Time To Collision (TTC) below which it was concluded that there is a danger of collision in the longitudinal direction." |
| Cut-out danger threshold | THW 2 | s | 3.3.2.2 | "The time 2 sec is specified as the maximum Time Head Way (THW) for which it was concluded that there is a danger in longitudinal direction." |
| g | 9.80665 | m/s2 | **not in text** | Standard gravity. Consistent with the text: 0.774 g / 0.6 s = 12.65 m/s3 (PM2 Table 3 jerk) and Annex 5 App. 1 para 1.1(c) "7.6 m/s2". |

Reference results the regulation plots (used as tests): 3.3.4.1 Figure 8 (cut-in at 60 km/h); 3.3.4.2 "It is possible to avoid all the deceleration (stop) vehicles ahead of the preceding vehicle cut-out in the following running condition at THW 2.0 sec."; 3.3.4.3 "It is possible to avoid sudden deceleration of -1.0G or less in the follow-up driving situation at THW 2.0sec."

## Performance model 2 (careful_b.py, "FSM")

Para 3.4.1: "it is assumed that the driver can anticipate the risk of a collision and apply proportionate braking ... "Lateral Safety Check"; "Longitudinal Safety Check"; and, "Reaction". A Reaction is implemented only if the Lateral and Longitudinal Safety Checks identify a risk of imminent collision."

| Parameter | Value | Unit | Paragraph | Verbatim quote |
|---|---|---|---|---|
| Reaction time tau | 0.75 | s | Table 3 | "Reaction time of the ALKS vehicle τ = 0.75 seconds" |
| Max jerk | 12.65 | m/s3 | Table 3 | "Jerking (road friction 1.0) 12.65 m/s3" |
| d1 | 2 | m | Table 3 | "Safety distance when the two vehicles reach complete stop d1 = 2 meters" |
| b_ego,comf | 4 | m/s2 | Table 3 | "Comfortable deceleration of the ALKS vehicle b_ego,comf = 4 m/s2" |
| b_ego,max | 6 | m/s2 | Table 3 | "Maximum deceleration of the ALKS vehicle b_ego,max = 6 m/s2" |
| b_cut-in,max | 7 | m/s2 | Table 3 | "Maximum deceleration of the 'other vehicle' b_cut-in,max = 7 m/s2" |
| Risk perception point | PFS or CFS > 0 | - | Table 3; 3.4.2.2.3 | "The time when either PFS or CFS value is not any longer 0"; "The Longitudinal Safety Check identifies a potential risk if either PFS or CFS are greater than 0." |
| Cut-out wandering zone | 0.375 | m | Table 3; 3.4.3(c) | "The ALKS vehicle is assumed not to be able to start the reaction time before the cutting out vehicle's centre is outside the wandering zone of 0.375 m from the centre of the lane." |
| Lateral check margin | 0.1 | (s, unit not stated) | 3.4.2.1(d) | dist_lat / u_cut-in,lat < (dist_lon + length_ego + length_cut-in) / (u_ego,lon - u_cut-in,lon) + 0.1 |

Formulas (3.4.2.1-3.4.2.3.1, read from the rendered pages):

- Lateral check (3.4.2.1) potential risk if (a) rear of other ahead of front of ALKS, (b) other moving towards ALKS, (c) u_ego,lon > u_cut-in,lon, (d) the inequality above.
- PFS (3.4.2.2.1): with d_safe = u_ego·τ + u_ego²/(2 b_comf) − u_cut²/(2 b_cut,max) + d1 and d_unsafe = u_ego·τ + u_ego²/(2 b_max) − u_cut²/(2 b_cut,max):
  PFS = 1 if 0 < dist_lon − d1 < d_unsafe; 0 if dist_lon − d1 > d_safe; (dist_lon − d_safe − d1)/(d_unsafe − d_safe) if d_unsafe < dist_lon − d1 < d_safe.
- CFS (3.4.2.2.2): a'_ego = max(a_ego, −b_comf); u_NEXT = u_ego + a'_ego·τ; d_new = ((u_ego + u_NEXT)/2 − u_cut)·τ;
  d_safe = (u_ego − u_cut)²/(2 a'_ego) if u_NEXT ≤ u_cut, else d_new + (u_NEXT − u_cut)²/(2 b_comf); d_unsafe the same with b_max.
  CFS = 1 if 0 < dist_lon < d_unsafe; 0 if dist_lon ≥ d_safe; (dist_lon − d_safe)/(d_unsafe − d_safe) if d_unsafe ≤ dist_lon < d_safe.
- Reaction (3.4.2.3): b_reaction = CFS·(b_max − b_comf) + b_comf if CFS > 0; PFS·b_comf if CFS = 0. 3.4.2.3.1: "The deceleration is implemented after a time equal to τ when it starts to increase with a constant rate equal to the maximum jerk."
- Cut-out (3.4.3) and deceleration (3.4.4): lateral check ignored, longitudinal check on the revealed object / preceding vehicle.
- 3.4.5 points to a reference implementation (footnote 9: https://github.com/ec-jrc/JRC-FSM). **Not used here**; worth diffing against for the interpretation items below.

## Ambiguities in the text and what the code does (REVIEW THESE)

1. **"2sec\*" (3.3.2.1)**: the asterisk has no footnote anywhere in the document. Used as TTC < 2 s, checked at and after the end of the 0.4 s perception time.
2. **When the TTC/THW check applies (PM1)**: the text gives the thresholds but not the moment. Code: hazard "decided" at the first step after trigger + 0.4 s where the danger condition holds; braking 0.75 s later.
3. **Cut-out THW 2 s (PM1)**: read as "the ego's THW to the cut-out vehicle at the reveal is ≤ 2 s" (Figure 3 draws THW to that vehicle). If the ego followed further back, the revealed vehicle is handled by item 6.
4. **"Full wrap" (PM1 0.85 g row)**: not defined. Code: the cut-in vehicle's centre is inside the 0.375 m wandering zone of the ego lane. Applied only to cut-in hazards, as the row names the "cut-in vehicle". Figure 1 also shows an AEB stage triggered by "TTC<TTC_AEB" and "xx% Rap"; neither value is given, so that trigger is not implemented.
5. **Figure 2 example "0.72m: Perception time"** is an example (lateral speed × 0.4 s), not a parameter. The formula a = lateral speed × 0.4 s is equivalent to waiting 0.4 s after the 0.375 m boundary, which is what the code does.
6. **Situations outside the three scenarios (PM1)**: a lead braking below 5 m/s2, or a slow/stopped vehicle that is not revealed by a cut-out, never triggers PM1 literally. `in_lane_ttc_extension=True` (default) **extends** the 3.3.2.1 TTC < 2 s rule to in-lane vehicles. This is NOT in R157; set it False for the literal model.
7. **Brake release**: neither model says when braking ends. PM1: braking holds while closing on a confirmed hazard, drops to 0 when not closing (stays alert, no new delay). PM2: demand is re-evaluated each step and the deceleration falls at the same max jerk when demand falls.
8. **PFS/CFS outside the defined cases**: no case for dist_lon − d1 ≤ 0 (PFS) or dist_lon ≤ 0 (CFS); code returns 1 (unsafe). CFS d_safe branch (u_ego − u_cut)²/(2 a'_ego) is negative or 0/0 when a'_ego ≤ 0; code uses |a'_ego| when the ego is decelerating and closing, and 0 when not closing or not decelerating.
9. **PFS formula double-counts d1** (d_safe already includes + d1, and d1 is also subtracted from dist_lon). Transcribed literally; the piecewise function is still continuous.
10. **dist_lat / dist_lon (3.4.2.1)**: "instantaneous lateral/longitudinal distance between the two vehicles" (not centre or edge). Code: dist_lon = bumper gap (consistent with condition (a) and d1), dist_lat = edge-to-edge lateral gap. Vehicles already laterally overlapping the ego skip the lateral check and are treated as in-lane (3.4.3(a)/3.4.4(a) logic).
11. **Lane centres**: the sim has no lane map. Each vehicle's lane centre is its y at the first observation; the ego lane centre is the ego's initial y (= 0 in the sim frame).
12. **Version**: transcribed from the 01 series proposal as adopted by GRVA-13; the consolidated R157e.pdf on unece.org was not reachable (403).

## Behaviour (tests/test_r157.py)

- Regulation reference cases reproduced: PM1 on 3.3.4.1 Figure 8 panel 2 (60 km/h, ΔV 20 km/h, dy0 1.6 m, Vy 2 m/s): collision at dx0 4 m, none at 20 and 40 m (figure: red below about 10 m). PM1 avoids a 1 g lead stop at THW 2 s at 20/40/60 km/h (3.3.4.3). Both models avoid the stopped vehicle revealed by a cut-out at THW 2 s (3.3.4.2). PM2 avoids the 1 g lead stop at 20/40 km/h and touches at 60 km/h (< 1 m/s; b_ego,max = 6 m/s2 < 1 g).
- Cut-in fixture of tests/test_sim.py (ego 20 m/s, cutter 12 m/s, cosine lane change from 0.5 s over 2 s): PM1 avoids from a 23.0 m gap, PM2 from 18.5 m. PM2 starts proportionate braking earlier and so brackets the "over-cautious" side; PM1 the "brakes late" side, consistent with the Olleja et al. 2025 framing.
- PM2 also brakes gently (PFS > 0) when simply following at the same speed closer than about 2.0 s THW at 20 m/s (gap < 40.4 m). That is the model as written (anticipatory), not a bug.

## Amendment check: GRVA-13-43 (13th GRVA, 23-27 May 2022)

Checked by Vakhtang and Claude on 15 Oct 2026 from the human's local copy `GRVA-13-43e.pdf` (base version; Rev.2 not yet checked). It amends ECE/TRANS/WP.29/2022/59 and **does not change any Annex 3 Performance model 1 or 2 value**. It only updates cross-references from "Annex 4 Appendix 3" to "Annex 3". Relevant content:
- 5.1.1.1 (new): ALKS "shall respond whilst active to any collision which requires a response according to national traffic rules ... and which could be expected to be recognised by a competent and careful human driver."
- Annex 5 Appendix 1 (moved from Annex 6), PM2 difficulty classes. Cut-in: Easy PFS <= 0.85; Medium PFS > 0.85 and CFS < 0.9; Difficult CFS >= 0.9. Cut-out and deceleration: Easy PFS = 0; Medium PFS > 0 and CFS < 0.5; Difficult CFS >= 0.5. (Candidate feature: label each claim's scenario with its R157 difficulty class.)
- 8.2.1 / Justification 28: DSSAD data elements on lane changes and lane crossings are recorded "to determine liability of the system and assess its performance". This is the regulatory basis for the tier-2 "obtain AV logs" information request.
- 5.2.3.1: maximum permitted ALKS speed 130 km/h (above 60 km/h only with MRM lane-change capability).
