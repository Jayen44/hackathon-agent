# Demo script (5 min)

Draft. Edit freely. Follows the guided tour: https://accel-claims-dashboard.vercel.app/?demo=1

**Speakers:** Antonio (finance), Jayen (insurance), Vakhtang (sim). **Vakhtang drives the laptop the whole time**; the speaker cue says who talks.
Numbers marked *live* are read off the screen on the day. Every other number below has been produced by the system.

| Time | Section | Speaker | On screen |
|---|---|---|---|
| 0:00-0:40 | The problem | Antonio | Inbox (tour step 1) |
| 0:40-1:20 | Reconstruction | Vakhtang | DEMO-1 claim, 3D replay (steps 2-4) |
| 1:20-1:40 | Decision and money | Antonio | Decision + GBP range (step 2 card) |
| 1:40-2:00 | What to get next | Jayen | Information requests (step 5) |
| 2:00-2:20 | Debate | Antonio | Adjuster vs defence counsel (step 6) |
| 2:20-3:20 | CCTV in | Vakhtang | New claim, CCTV autofill (step 7) |
| 3:20-4:10 | Agent team | Vakhtang | /run (step 8) |
| 4:10-4:25 | Proof on real crashes | Vakhtang | (verbal, or eval/REAL_CRASH_EVAL.md) |
| 4:25-4:40 | Responsible design | Jayen | (verbal) |
| 4:40-5:00 | Business and vision | Antonio | Inbox |

---

### 0:00-0:40 · The problem · **Antonio**
*(Inbox on screen.)*
> "Robotaxis are on London's roads: Uber and Wayve started paid rides in September. When one crashes, the injured person's insurer pays. Then it has to decide whether it can recover that money from the AV company. The UK test, in the Automated Vehicles Act 2024, is whether the car was as safe as a careful and competent human driver. Nobody gives insurers a way to check that on a single claim. That's what we built."

### 0:40-1:20 · Reconstruction · **Vakhtang**
*(Tour steps 2-4: open DEMO-1, 3D replay, press C to change camera.)*
> "This AV approached a stationary queue and braked late. We rebuild the crash from the evidence and replay it with the two careful-driver models published in UN Regulation 157. One is a late braker, one is cautious, so together they bracket a careful human. Here's what the AV did. Here's careful driver A, and B. Both stop in time. And the simulation reproduces the reported crash, so we trust the setup."

### 1:20-1:40 · Decision and money · **Antonio**
> "Decision: Pursue. Expected recovery £10.8k to £53k after legal costs. It's triage for a claims handler, not a ruling."

### 1:40-2:00 · What to get next · **Jayen**
*(Tour step 5.)*
> "Every claim tells the handler what evidence would sharpen the answer, like the AV's own logs, and how much it would narrow the range."

### 2:00-2:20 · Debate · **Antonio**
*(Tour step 6.)*
> "Then the system argues against itself: a defence-counsel agent attacks our weakest assumption, and the adjuster has to answer. Contested claims go to a human."

### 2:20-3:20 · CCTV in · **Vakhtang**
*(Tour step 7: New claim, tick CCTV, autofill runs about 45 s; talk over it, then press **Assess claim**.)*
> "Most of the time the insurer has footage. Upload it right in the claim form. We detect the vehicles, calibrate the road from four points, and measure speeds and gaps with error bars. Nobody types numbers in; they come from the video."

### 3:20-4:10 · Agent team · **Vakhtang**
*(Tour step 8: /run. Point at the lanes.)*
> "Behind this is a team of Claude agents on Anthropic's Managed Agents. It's been running since late morning on our claims queue. A portfolio lead hands each claim to an investigator, a reconstructor, a counterfactual analyst, and the adjuster and defence counsel. So far: *[live: N claims, X Pursue, GBP range]* recoverable."

### 4:10-4:25 · Proof on real crashes · **Vakhtang**
> "On real rear-end crashes from the US 100-Car study, a UN R157 careful driver would have avoided 62% to 100% of them, and our simulation reproduces about 9 in 10 real events from radar data."

### 4:25-4:40 · Responsible design · **Jayen**
> "We always show both careful drivers, ranges and our assumptions. When the two models disagree we flag it instead of picking the convenient one, and the output is triage for a human, never a liability ruling."

### 4:40-5:00 · Business and vision · **Antonio**
> "Customers are motor and fleet insurers. We'd start with US recovery claims, where driverless fleets are already large, and be ready for the UK regime as the Automated Vehicles Act comes in. The vision: insurers bring their own pricing models and rules, and we supply the evidence. Thank you."

---

## Say carefully (from `sim/LEGAL_BASIS.md`)
- Don't say UK robotaxis are covered by AEVA today, or that the AV Act is fully in force.
- Don't say "liable", "defective" or "self-driving" about a named company. Say "recovery case" and "ADS-engaged".
- Quote careful drivers A and B **together**, never B alone.
- Demo claims and the CCTV clip are **synthetic**. The **100-Car** crashes are real.

## Backup
If the network or a live call fails, play the screen recording from the matching timestamp. The agent run keeps going on Modal either way.
