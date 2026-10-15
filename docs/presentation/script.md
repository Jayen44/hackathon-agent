# CounterFactual: pitch script (5 minutes, 11 slides)

**Speakers:** **Jayen** presents every slide. **Vakhtang** runs and narrates the live demo (slide 7) and drives the laptop.
**Before you start:** dashboard open in a second tab (accel-claims-dashboard.vercel.app), example 21 ready, terminal open with `python -m insurance.sim_link` already run.
**Wording:** say "recovery case" and "triage evidence". Never call a named company "liable" or "defective". Always quote careful drivers A and B together. Give ranges, never a single number.

---

### 1. Cover · Jayen · 0:00–0:15
> When a driverless car crashes, someone pays, and the insurer needs to know one thing fast: can we get that money back from the company behind the vehicle? We're CounterFactual. We give claims teams that answer in minutes, with the evidence behind it.

### 2. Why it is needed · Jayen · 0:15–0:45
> Driverless cars crash far less. One insurer study found 88% fewer property claims and 92% fewer injury claims than human drivers. So the claims that remain are few, contested and high-stakes.
> The proof sits with the other side: the driving logs belong to the operator.
> And recovery is real money. US insurers filed about 27 billion dollars of recovery demands last year, and recovery firms keep up to a third of it.
> Insurers make two costly mistakes: chasing a claim they'll lose, and missing one they'd win.

### 3. Target market · Jayen · 0:45–1:10
> We sell across the whole liability chain: fleet insurers and reinsurers, the robotaxi operators themselves for their defence, and the agents who place that cover.
> Honestly, driverless-only claims are a small market today, about 7.7 million dollars a year by 2030. That's why we also screen driver-assist claims, which are 15 to 20 times more common now.

### 4. Why start in the United States · Jayen · 1:10–1:40
> We start where the vehicles and the data are. Waymo runs about 500,000 paid rides a week, about 200 million driverless miles a year. Tesla's driver-assist system has logged 8 billion miles, on Tesla's own figures, which gives us volume to screen.
> The US also publishes crash reports, so we can test ourselves. Our simulator reproduces 88% of real crashes in a public study.
> The UK comes next, when its Automated Vehicles Act regime goes live, expected late 2027.

### 5. One claim, start to finish · Jayen · 1:40–2:15
> Here's what happens to a claim. The crash file comes in and we check it hasn't been tampered with. We work out who was in control. Then the simulator asks the key question: would a careful driver have avoided this? We run two published reference drivers, A and B.
> From that we price what's recoverable as a range, after legal costs. Every claim ends in one of eight outcomes with next steps and the deadline. Then a named person signs off.
> One rule matters most: code produces every number. The agents only challenge it.

### 6. The agent team · Jayen · 2:15–2:40
> Four agents work the queue for hours without supervision. A lead picks each claim and hands it to an investigator, a reconstructor and a counterfactual analyst.
> They're built for long runs: a budget cap, retry limits, and a full trace of every run. If the simulator can't reproduce a crash in five tries, the claim is flagged, not forced.

### 7. Cue the demo · Vakhtang · 2:40–4:00
*(Jayen hands over: "Vakhtang will show you a live claim." Vakhtang switches to the dashboard.)*
- **Inbox (15s):** "27 claims, each with a decision and a pound range."
- **One claim (25s):** open example 21. "Both careful drivers avoid this crash 99 to 100% of the time. Expected recovery is 8.9 to 51.2 thousand pounds, after legal cost. Outcome: pursue, with a letter before action."
- **Agent run (15s):** show the hand-offs and a retry in the trace.
- **Debate (25s):** "Before a human sees it, the system argues with itself. Defence counsel attacks the weakest assumption and the adjuster rebuts. If a rejected challenge would flip the decision, the claim goes to a human, marked contested."

*(Vakhtang switches back to the slides and hands back: "Over to Jayen.")*

### 8. Three ways to charge · Jayen · 4:00–4:20
> Three ways to charge. Per claim, 300 pounds. A 10% success fee, well under what recovery firms take. Or a 40 to 80 thousand pound subscription, which is the one that scales.
> The AI costs 27 cents a claim. Human review is most of the cost, and we keep it on purpose. Margins are around 87 to 90%.

### 9. Risks · Jayen · 4:20–4:45
> We'll name the risks before you do.
> - The market is small before 2030, so we start in the US and sell subscriptions.
> - Our engine models UK law today, so we're building the US model with counsel.
> - The operator holds the evidence, so we send a preservation letter, then a disclosure request.
> - The models are guidance, not law, so a human always signs off.
> - And this must never be used against a victim. Victims are paid first, and our output is triage, never a verdict.

### 10. Ready for real claims · Jayen · 4:45–5:00
> It works today: 22 crashes reproduced, the agents and a live dashboard, over 200 tests. What we need is a 2 million pound seed, one insurer or operator for a US pilot, and one US counsel.

### 11. Any questions? · Jayen (Vakhtang takes demo questions)
> Thank you. Happy to take questions.

---

## Likely questions (one line each)
- **Is this legal today?** "We start in the US. The UK regime isn't live yet, and we flag that on every claim." (Jayen)
- **Why trust the number?** "It comes from published reference models, always shown as a range from drivers A and B, and a human signs off." (Jayen)
- **What if the operator won't share logs?** "A preservation letter, then a court disclosure request. We also show what better evidence would change." (Jayen)
- **How do you make money?** "Per claim, a success fee, or a subscription. The subscription is what scales." (Jayen)
- **What's real?** "22 example crashes reproduced, two agent systems, a live dashboard. The crash data is synthetic." (Vakhtang, who can show it)

## If the demo fails
Stay on slide 7 and run the terminal proof: `python -m insurance insurance/examples/21_pursue_cut_in.json --price`. Then read the outcome, the range and the next steps aloud.
