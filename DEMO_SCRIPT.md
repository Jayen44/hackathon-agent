# Demo script (5 min), matched to the deck

**One-line pitch:** A robotaxi crashes. The law asks: would a careful human have avoided it? We answer.

Deck: `docs/presentation/` on `main` (11 slides). Live demo: https://accel-claims-dashboard.vercel.app/?demo=1
**Speakers:** Antonio (finance), Jayen (insurance), Vakhtang (sim). **Vakhtang drives the laptop the whole time.**
Note: the deck still says "Automated Vehicle Recovery Desk" on slides 1 and 11; the product name is **CounterFactual**.

| Time | Slide | Speaker |
|---|---|---|
| 0:00-0:20 | 1 Cover | Antonio |
| 0:20-0:45 | 2 Few claims, high stakes, hidden proof | Antonio |
| 0:45-1:05 | 3 Sold across the liability chain | Antonio |
| 1:05-1:25 | 4 Why start in the United States | Jayen |
| 1:25-1:50 | 5 One claim, start to finish | Jayen |
| 1:50-2:10 | 6 Four agents, built to run for hours | Vakhtang |
| 2:10-3:50 | 7 Cue the demo (live site) | Vakhtang |
| 3:50-4:15 | 8 Three ways to charge | Antonio |
| 4:15-4:35 | 9 Risks, and how we address each | Jayen |
| 4:35-5:00 | 10 Ready for real claims, the ask | Antonio |
| after | 11 Any questions? | all |

---

### 1 · Cover · Antonio (0:00-0:20)
> "A robotaxi crashes. The law asks: would a careful human have avoided it? We answer, and tell the insurer what it can recover. We're CounterFactual."

### 2 · Few claims, high stakes, hidden proof · Antonio (0:20-0:45)
> "Driverless cars crash far less: the Swiss Re and Waymo study found 88% fewer property claims and 92% fewer injury claims than human drivers. The claims that remain are contested, and the proof sits with the operator. Recovery is already a real market: $27bn of US subrogation demands in 2025, and recovery firms keep 15 to 33%. The two costly mistakes are chasing a losing claim and missing a winning one."

### 3 · Sold across the liability chain · Antonio (0:45-1:05)
> "We sell across the liability chain: fleet insurers and reinsurers, robotaxi operators for defence and incident review, and fleet managing general agents. The driverless-only market is about $7.7M by 2030, so we don't stop there. There are 15 to 20 times more driver-assist claims than driverless ones today, and that's our volume."

### 4 · Why start in the United States · Jayen (1:05-1:25)
> "We start in the US because that's where the driverless miles are: Waymo does 500,000 paid rides a week and about 200 million driverless miles a year. Federal crash reports are public, and our simulator reproduces 88% of real crashes from the public 100-Car study. The UK is next: we're ready for the Automated Vehicles Act 2024 regime, expected late 2027."

### 5 · One claim, start to finish · Jayen (1:25-1:50)
> "A claim runs in six steps: intake of logs and video with an integrity check, who was in control, a simulation asking whether a careful driver would have avoided it, a recoverable range, an outcome with next steps and the deadline, and a named human who signs off. When new evidence arrives, the claim re-runs and a ledger shows what changed. Code produces every number; the agents only challenge it."

### 6 · Four agents, built to run for hours · Vakhtang (1:50-2:10)
> "The agents run on Claude Managed Agents. A portfolio lead takes the next claim and hands it to an investigator, a reconstructor that retries up to five times until the simulation reproduces the crash, and a counterfactual analyst running careful drivers A and B. Our proof run went for 70 minutes over 58 claims, with 4,245 logged hand-offs, and stopped at its budget cap."

### 7 · Cue the demo · Vakhtang (2:10-3:50)
*(Switch to the site. Use the tour's Next button. Say the demo claims and the CCTV clip are synthetic.)*
1. **The claims inbox** (15 s):
   > "Every claim ends in a decision and a pounds range."
2. **One claim, start to finish** (45 s): open DEMO-1.
   > "The autonomous vehicle braked late on a stationary queue. Here's what it did, and here are careful drivers A and B. Both stop in time." *(Press C for the camera.)* "Both avoid it; the simulation reproduces the crash. Decision: Pursue, £10.8k to £53k after legal costs. And here's what to get next."
   - *Optional, 15 s, if time allows:* open `/claims/CHECK-blender`.
   > "This one came from CCTV: we measured the speeds from the video. Both drivers avoid it, but engagement isn't verified, so pull the logs first."
3. **The agent run** (20 s): `/run`.
   > "The team at work: lanes, hand-offs, the pounds map. 70 minutes, 58 claims."
4. **The debate** (20 s): back on the claim.
   > "Defence counsel attacks our weakest assumption; the adjuster accepts or rejects it. Contested claims go to a human."

### 8 · Three ways to charge · Antonio (3:50-4:15)
> "Three ways to charge: £300 per driverless claim, or £75 for a driver-assist screen; 10% of what's recovered, below the 15 to 33% recovery firms keep; or a £40k to £80k subscription for operators and insurers, the one that scales. Compute is 27 cents a claim, measured, so gross margin is 87 to 90%."

### 9 · Risks, and how we address each · Jayen (4:15-4:35)
> "The market is small before 2030, so we go US first, sell subscriptions, and use driver-assist for volume. The operator holds the evidence, so we send a preservation letter and then request disclosure. The models are guidance, not law, so we always quote drivers A and B together and a human signs off. And victims are paid first: our outputs are triage, never verdicts."

### 10 · Ready for real claims · Antonio (4:35-5:00)
> "Working now: 22 example crashes, all reproduced, agents and a live dashboard, and over 200 tests. Not yet: real crash data, a US legal and cost model, a tested price. The ask: a £2M seed, a US pilot with one insurer or operator on settled claims, and one US counsel. Thank you."

### 11 · Any questions? · all

---

## Say carefully (from `sim/LEGAL_BASIS.md`)
- Don't say UK robotaxis are covered by AEVA today, or that the AV Act is fully in force.
- Don't say "liable", "defective" or "self-driving" about a named company. Say "recovery case" and "ADS-engaged".
- Quote careful drivers A and B **together**, never B alone.
- Demo claims and the CCTV clip are **synthetic**. The **100-Car** crashes are real.

## Backup
If the network fails, play the screen recording from the matching point. The proof log is `proof/agent_run/agent_run_detailed.log`.
