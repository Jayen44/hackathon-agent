# Speaker notes: finance and business (slides 1, 2, 3, 8, 10)

These are the finance speaker's lines for the 5-minute pitch: what to say, how long it takes, what's on screen, and the hand-off to the next speaker.
- **Matches:** the team script ([`DEMO_SCRIPT.md`](https://github.com/Jayen44/hackathon-agent/blob/sim/DEMO_SCRIPT.md) on `sim`) and the deck in this folder. Vakhtang drives the laptop throughout.
- **Product name:** CounterFactual. The deck may still say "Automated Vehicle Recovery Desk"; say the product name.
- **Pace:** about 150 words a minute. Each part below lists its word count. If you run long, cut the sentence marked *(cut if short on time)*.

---

## Slide 1 · Cover · 0:00–0:20 (about 45 words)
> "A robotaxi crashes. The law asks one question: would a careful and competent human driver have avoided it? We answer that, for a single claim, and tell the insurer what it can recover, and whether it's worth chasing. We're CounterFactual."

- **Delivery:** pause after "would a careful and competent human driver have avoided it?" That sentence is the whole product.
- **Hand-off:** go straight on to slide 2.

## Slide 2 · Few claims, high stakes, hidden proof · 0:20–0:45 (about 65 words)
> "Driverless cars crash far less. Swiss Re's study of Waymo found 88% fewer property claims and 92% fewer injury claims than human drivers. So the claims that remain are rare, contested, and the proof sits with the operator. Recovery is already a real business: twenty-seven billion dollars of US subrogation demands last year. The two expensive mistakes are chasing a losing claim and missing a winning one."

- **Emphasise:** "rare, contested, proof with the operator". Those are the three reasons a tool is needed.
- **Don't say** the AV company is "liable" or "caused" anything. Say "recovery case".

## Slide 3 · Sold across the liability chain · 0:45–1:05 (about 55 words)
> "We sell across the liability chain: insurers and reinsurers recovering money, robotaxi operators reviewing their own incidents, and fleet underwriters pricing risk. Driverless claims alone are a small market, about $7.7 million by 2030, so we don't stop there. Driver-assist cars have fifteen to twenty times more claims today. That's our volume."

- **Be honest that the per-claim market is small.** Judges respect it, and the next line shows why the business still works.
- **Hand-off:** "Jayen will show why we start in the US." Then step back.

## During the demo (2:10–3:50, Vakhtang) · you're not speaking
- **Stand where you can see the screen.** When the claim page shows **Decision: Pursue, £X to £Y**, you can add one line if Vakhtang pauses:
  > "Every pound on that screen comes from the finance engine. The AI agents can challenge it, but never write it."
- **Read the figure off the screen; don't memorise it.** The demo claim's range can change after a redeploy.

## Slide 8 · Three ways to charge · 3:50–4:15 (about 60 words)
> "Three ways to charge. Per claim: £300 for a driverless claim, £75 to screen a driver-assist one. A success fee: 10% of what's recovered, below the 15 to 33% recovery firms keep. Or a subscription, £40 to £80 thousand a year for operators and insurers. That's the one that scales. The AI costs about 25 cents a claim, measured, so gross margin is around 87 to 90%."

- **Emphasise "measured".** The 25 to 27 cents is from our own live runs, not an estimate.
- *(Cut if short on time:)* the driver-assist £75 price.

## Slide 10 · Ready for real claims, the ask · 4:35–5:00 (about 60 words)
> "What works today: 22 example crashes, all reproduced; a team of agents that ran for 70 minutes on its own; a live dashboard; and over 200 tests. What doesn't yet: real claims data, a US legal and cost model, and a tested price. Our ask: a £2M seed, one US pilot with an insurer or operator on settled claims, and one US lawyer. Thank you."

- **Say "Thank you" and stop.** Slide 11 opens questions.

---

## Questions you're likely to get (finance and business)
Keep each answer to two or three sentences. The numbers are sourced in [`docs/business-case.md`](../business-case.md) and `market/MARKET.md` on `sim`.

**"How do you know the money figures are right?"**
> "Every figure comes from a published source: in the UK, the whiplash tariff, the Judicial College Guidelines and the court's fixed legal-cost tables. If we can't source a number, the system refuses to price the claim rather than guess. We always show a range, never a single number."

**"Isn't the market too small?"**
> "Driverless-only claims are small before 2030. That's why the business is a subscription across the liability chain, with driver-assist claims for volume. Each extra 10,000 US robotaxis adds hundreds to a few thousand claims a year, and liability is moving from drivers to manufacturers."

**"Why would an insurer pay you rather than a recovery firm?"**
> "Recovery firms charge 15 to 33% and work by hand. We give the triage up front, telling them which claims to chase and which to drop, for 10% or a flat fee. We can sit in front of a recovery firm rather than replace it."

**"What stops the AI making up numbers?"**
> "The agents never write numbers. They can only ask the finance engine 'what if' within limits the evidence allows, and the engine re-prices. If the adjuster rejects a challenge that would change the decision, it goes to a human."

**"What happens when the agents disagree?"**
> "Defence counsel argues for the AV company and the adjuster has to accept, partly accept, or give a reason from the evidence to reject. If they still disagree on the decision, a claims handler decides. In our last batch of ten claims, the challenge changed three decisions."

**"Does this work in the UK today?"**
> "Not under the Automated Vehicles Act yet. London's robotaxis run with a safety driver, and the full regime is expected from late 2027. Today UK recovery runs through other routes. That's why we start in the US and are ready for the UK when the regime goes live."

**"Who owns the vehicle data?"**
> "The operator holds it, and insurers have no automatic right to it. We send a preservation letter, then request disclosure, and our output names exactly which data would change the decision."

**"What's the customer evidence?"**
> "The industry says the problem out loud: Thatcham and the ABI say insurers need timely, unhindered access to data, and an insurance lawyer told Insurance Times that recovery is much harder without it." *If you spoke to an insurer today, add their line here.*

---

## Numbers card (only the ones on the slides)
| Figure | Source |
|---|---|
| 88% fewer property / 92% fewer injury claims | Swiss Re study of Waymo (Waymo-commissioned) |
| $27bn US subrogation demands, 2025 | Arbitration Forums, via `market/MARKET.md` |
| Recovery firms keep 15–33% | US contingency schedules, via `market/MARKET.md` |
| $7.7M driverless market, 2030 (base) | `market/MARKET.md` |
| £300 / £75 / 10% / £40–80k pricing | `market/MARKET.md` (assumptions) |
| About 25–27 cents of AI per claim | Measured in our live runs |
| 70-minute agent run, 4,245 logged events | Live run `20261015-113918-f201`; proof log in `proof/` on `sim` |

## Say carefully
- **Never say** the AV company is "liable", "defective" or "caused" the crash. Say "recovery case" and "triage evidence".
- **Always quote careful drivers A and B together,** never B alone.
- **Demo claims and the CCTV clip are synthetic.** The 100-Car crashes are real.
- **Don't say** UK robotaxis are covered by AEVA today, or that insurers have a legal right to the data.
