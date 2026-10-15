# CounterFactual: pitch script (5 minutes, 11 slides)

**Speakers:** **Jayen** presents every slide. **Vakhtang** runs and narrates the live demo (slide 7) and drives the laptop throughout.
**Before you start:** slides on screen, dashboard open in a second tab (accel-claims-dashboard.vercel.app) with example 21 ready, terminal open with `python -m insurance.sim_link` already run.
**Wording:** say "recovery case" and "triage evidence". Never call a named company "liable" or "defective". Always quote careful drivers A and B together. Give ranges, never a single number.
**Delivery:** *[click]* means Vakhtang advances the slide. Pause briefly at each **bold** line, because those are the lines to land.

---

### 1. Cover · Jayen · 0:00–0:15
> When a driverless car crashes, someone pays. The insurer then needs one answer fast: **can we get that money back from the company behind the vehicle?**
> We're CounterFactual. We give claims teams that answer in minutes, with the evidence behind it. *[click]*

### 2. Why it is needed · Jayen · 0:15–0:45
> Driverless cars crash far less. One insurer study found 88% fewer property claims and 92% fewer injury claims than human drivers. So the claims that remain are rare, contested and expensive.
> The proof sits with the other side, because the operator holds the driving logs.
> And recovery is real money. US insurers filed about 27 billion dollars of recovery demands last year, and recovery firms keep up to a third of it.
> **Insurers make two costly mistakes: chasing claims they'll lose, and missing claims they'd win.** *[click]*

### 3. Target market · Jayen · 0:45–1:10
> Our buyers sit along the whole chain: fleet insurers and reinsurers, robotaxi operators defending their own claims, and the brokers who place that cover.
> To be honest, driverless-only claims are a small market today, about 7.7 million dollars a year by 2030. **So we also screen driver-assist claims, which are 15 to 20 times more common right now.** *[click]*

### 4. Why start in the United States · Jayen · 1:10–1:40
> We start where the vehicles and the data are. Waymo runs about 500,000 paid rides a week, roughly 200 million driverless miles a year. Tesla reports 8 billion miles on its driver-assist system, which gives us volume to screen.
> The US also publishes crash reports, so we can test ourselves against real cases. **Our simulator reproduces 88% of the crashes in a public study.**
> The UK comes next, once its Automated Vehicles Act regime goes live, expected late 2027. *[click]*

### 5. One claim, start to finish · Jayen · 1:40–2:15
> Here's one claim. The crash file arrives and we check it hasn't been tampered with. We establish who was in control. Then the simulator asks the key question: **would a careful driver have avoided this crash?** We test two published reference drivers, A and B.
> From that, we price what's recoverable as a range, after legal costs. Every claim ends in one of eight outcomes, with next steps and a deadline, and a named person signs off.
> **One rule matters most: code produces every number. The agents only challenge it.** *[click]*

### 6. The agent team · Jayen · 2:15–2:40
> Four agents work the queue for hours without supervision. A lead agent picks each claim and hands it to an investigator, a reconstructor and a counterfactual analyst.
> They're built for long runs, with a budget cap, retry limits and a full trace of every step. **If the simulator can't reproduce a crash in five tries, the claim is flagged, not forced.** *[click]*

### 7. Cue the demo · Vakhtang · 2:40–4:00
*(Jayen: "Vakhtang will now show you a live claim." Vakhtang switches to the dashboard tab.)*
- **Inbox (15s):** "This is the claims inbox: 27 claims, each with a decision and a pound range."
- **One claim (25s):** open example 21. "Careful drivers A and B both avoid this crash 99 to 100% of the time. Expected recovery is 8.9 to 51.2 thousand pounds after legal costs. The outcome is pursue, starting with a letter before action."
- **Agent run (15s):** show the hand-offs and one retry in the trace. "Here you can see each agent hand off, and here a retry."
- **Debate (25s):** "Before a human sees it, the system argues with itself. Defence counsel attacks the weakest assumption and the adjuster rebuts. **If a rejected challenge would flip the decision, the claim goes to a human, marked contested.**"

*(Vakhtang switches back to the slides: "Back to Jayen.")* *[click]*

### 8. Three ways to charge · Jayen · 4:00–4:20
> There are three ways to pay us: 300 pounds per claim, a 10% success fee (well below what recovery firms take), or a subscription of 40 to 80 thousand pounds a year. **The subscription is the one that scales.**
> The AI costs about 27 cents a claim. Most of our cost is human review, and we keep it on purpose. Margins are around 87 to 90%. *[click]*

### 9. Risks · Jayen · 4:20–4:45
> We'll name the risks before you do.
> - The market is small before 2030, so we start in the US and sell subscriptions.
> - Our engine models UK law today, so we're building the US model with counsel.
> - The operator holds the evidence, so we send a preservation letter, then a disclosure request.
> - The models are guidance, not law, so a human always signs off.
> - **And this must never be used against a victim. Victims are paid first, and our output is triage evidence, never a verdict.** *[click]*

### 10. Ready for real claims · Jayen · 4:45–5:00
> It works today: 22 crashes reproduced, the agent team, a live dashboard and over 200 tests.
> **What we need: a 2 million pound seed round, one insurer or operator for a US pilot, and one US counsel.** *[click]*

### 11. Any questions? · Jayen (Vakhtang takes demo questions)
> Thank you. We're happy to take questions.

---

## Numbers to have ready
| Point | Figure |
|---|---|
| Fewer claims than human drivers | 88% property, 92% injury (one insurer study) |
| US recovery demands last year | about 27 billion dollars; recovery firms keep up to a third |
| Driverless-only market by 2030 | about 7.7 million dollars a year |
| Driver-assist versus driverless claims | 15 to 20 times more common |
| Waymo | about 500,000 paid rides a week, about 200 million miles a year |
| Simulator on public crash study | reproduces 88% |
| Example 21 | drivers A and B avoid 99 to 100%; 8.9 to 51.2 thousand pounds |
| Pricing | 300 pounds per claim, 10% success fee, 40 to 80 thousand pounds a year |
| AI cost and margin | about 27 cents a claim; 87 to 90% margin (assumption) |
| Ask | 2 million pound seed, one pilot partner, one US counsel |

## Likely questions (one line each)
- **Is this legal today?** "We start in the US. The UK regime isn't live yet, and we flag that on every claim." (Jayen)
- **Why trust the number?** "It comes from published reference models, it's always a range from drivers A and B, and a human signs off." (Jayen)
- **What if the operator won't share logs?** "We send a preservation letter, then a court disclosure request. We also show what better evidence would change." (Jayen)
- **How do you make money?** "Per claim, a success fee, or a subscription. The subscription is what scales." (Jayen)
- **What's real?** "22 example crashes reproduced, two agent systems and a live dashboard. The crash data is synthetic." (Vakhtang, who can show it)

## If the demo fails
Stay on slide 7. Vakhtang runs the terminal proof: `python -m insurance insurance/examples/21_pursue_cut_in.json --price`, then reads out the outcome, the range and the next steps, then hands back to Jayen. Do not spend more than 20 seconds troubleshooting.
