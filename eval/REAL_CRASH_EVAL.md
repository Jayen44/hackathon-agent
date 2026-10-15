# Real-crash evaluation: R157 careful drivers on 100-Car rear-end crashes

**Headline.** On 8 real rear-end crashes from the 100-Car Naturalistic Driving Study, careful
driver A (R157 PM1, CCDM) avoids 5/8 = 62% (90% CI 35-84%) and careful driver B (R157 PM2,
FSM) avoids 8/8 = 100% (90% CI 75-100%). The sim reproduces the recorded outcome in 7/8 crashes
and 161/172 near-crashes. Main variant: the careful driver controls the brake, and the throttle
follows the recorded human whenever the human was off the brake.

Supporting evidence for the method. These are human drivers in 2001-04 Virginia, not AVs, and
nothing here is a liability ruling or legal advice. Numbers are from `eval/results/real_crash_eval.json`
(seed 0, 100 Monte Carlo samples per event and driver).

## Data and licence
- 100-Car NDS crash and near-crash time series (VTTI), https://doi.org/10.15787/VTT1/CEU6RB.
  The VTTI Dataverse metadata gives the licence as **CC0 1.0**. It lists no terms of access,
  no restricted files and no access request, so no sign-up or data-use agreement is needed.
- On 2026-10-15 the Dataverse file store returned 404 for the data files. We used the copies
  in github.com/Yiru-Jiao/Reconstruct100CarNDSData `RawData/` (code under MIT, data under
  CC0), pinned to commit a9db691 with sha256 checks (`sim/data/hundredcar.fetch`). We ran
  none of that repo's code.
- We never load driver age, gender or distraction fields. Only kinematics and the event codes
  are used.

## Method (`eval/real_crash_eval.py`, loader `sim/data/hundredcar.py`)
1. **Selection.** Event nature is "Conflict with a lead vehicle", incident is "Rear-end,
   striking", and the precipitating event is "Other vehicle ahead - ..." (the R157
   lead-vehicle-deceleration family). This leaves 13 crashes and 288 near-crashes.
   - We could reconstruct 8 crashes and 172 near-crashes.
   - Events were skipped when no in-lane radar target was present during the event (3 crashes,
     48 near-crashes), or when the radar track started less than 2.5 s before the minimum range
     (2 crashes, 68 near-crashes).
2. **Initial conditions.** The reference time is the minimum radar range to the in-lane lead
   (|lateral| < 2 m). The start is 5 s earlier, or as far back as the radar track goes (at
   least 2.5 s).
   - Radar ID hand-overs and dropouts up to 2 s are stitched together when the range and
     lateral position are continuous.
   - Ego speed comes from the composite speed (mph). Lead speed is ego speed plus range rate.
     The gap is the radar range, taken as bumper to bumper.
   - Lead acceleration is piecewise constant per 0.5 s. It comes from the 0.5 s-smoothed lead
     speed, clipped to [-0.9 g, +4 m/s²]. After the radar loses the lead, the lead holds its
     last speed.
3. **Reproduction (rubric B1/B2).** We replay the recorded human acceleration
   (`AVReplayPolicy`) against the lead's measured motion.
   - The accelerometer has a constant bias. We remove it so that the integrated acceleration
     matches the measured change in speed.
   - An event is reproduced when the sim's contact or no-contact result matches the recorded
     crash or near-crash.
   - If it does not match, the reconstructor loop moves the gap, ego speed and lead speed
     toward the recorded outcome. Each step is a fraction of the sensor uncertainty, and the
     loop stops after 5 attempts.
   - The B2 metric is the RMSE of the replayed gap against the radar range.
4. **Counterfactual.** Careful drivers A and B come from `montecarlo.estimate.drivers()` with
   the R157 parameters (`sim/policies/R157_ANNEX3.md`).
   - Each driver runs Monte Carlo over the reconstructed values ± sensor uncertainty, tagged
     `reported`: gap ±0.5 m, ego speed ±0.3 m/s, lead speed ±0.5 m/s.
   - A run that ends still closing at TTC < 2 s counts as not avoided.
   - An event counts as avoided if P(avoid) ≥ 0.5. Shares across events have Wilson 90% CIs.

## Results

| | N | Reproduced (≤5 attempts) | 1st attempt | Median gap RMSE |
|---|---|---|---|---|
| Crashes | 8 | 7/8 = 88% (CI90 59-97%) | 6/8 | 1.2 m |
| Near-crashes | 172 | 161/172 = 94% (CI90 90-96%) | 133/172 | 1.8 m |

Share of events avoided (event avoided if P(avoid) ≥ 0.5, Wilson 90% CI):

| Events | Throttle variant | Careful A (PM1) | Careful B (PM2) |
|---|---|---|---|
| Crashes | human throttle (main) | 5/8 = 62% (35-84%) | 8/8 = 100% (75-100%) |
| Crashes | hold speed (literal R157) | 7/8 = 88% (59-97%) | 8/8 = 100% (75-100%) |
| Crashes, reproduced only | human throttle | 4/7 = 57% (29-81%) | 7/7 = 100% (72-100%) |
| Near-crashes | human throttle (main) | 29/172 = 17% (13-22%) | 168/172 = 98% (95-99%) |
| Near-crashes | hold speed | 40/172 = 23% (18-29%) | 168/172 = 98% (95-99%) |

**How to read this**
- **B passes the sanity check.** B avoids 98% of the near-crashes that the real humans also
  avoided.
- **A does not pass it.** A avoids only 17%. In our implementation PM1 reacts only when the lead
  decelerates harder than 5 m/s² or when the in-lane TTC drops below 2 s (our labelled
  extension). After that it waits 0.4 s + 0.75 s and then ramps the brake over 0.6 s. That is
  too late for most real lead-braking conflicts.
- **This matches the literature.** Olleja et al. 2025 find that one R157 model "brakes too late".
  So A is the lower bound and B the upper bound, and the A-B spread on real data is wide (rubric
  C2: flag the result as model-dependent).
- **On a claim, quote both numbers.** A recovery case built only on B overstates what a careful
  human does. A case built only on A understates it.

## Limits
- **Human drivers, not AVs.** We evaluate the careful-driver bracket against real human
  conflicts, which is the reference R157 is meant to encode. This does not evaluate any AV.
- **Old, local data.** Data is from 2001-04 Northern Virginia / Washington DC. The vehicles,
  brakes (often pre-ABS) and traffic differ from London in 2026.
- **Small crash N, mostly very slow crashes.** 5 of the 8 crashes start at 2.5 m/s or less
  (stop-and-go creep). A crash share with a 75-100% CI is not a precise rate.
- **Radar reconstruction noise.** The 2000s forward radar loses targets, re-labels IDs and
  drops out near contact.
  - Lead acceleration comes from range rate, so it is noisy. It is smoothed and clipped, a
    design assumption.
  - One reproduced crash (8475) still has a gap RMSE of 6.4 m. One crash (8661) is not
    reproduced: radar contact was lost at about 0.4 m.
- **R157 scope.** R157 is guidance for ALKS on motorways. Many of these events are urban, low
  speed and stop-and-go.
  - PM1's in-lane TTC < 2 s extension is not in R157 (see R157_ANNEX3.md item 6).
  - Friction is taken as R157's 1.0 for every event. Wet-road events are not capped.
- **The careful driver only brakes.** It never steers. Some humans in the near-crashes may have
  swerved.
- **Throttle choice matters for A.** Holding speed instead of copying the human throttle raises
  A's crash share from 62% to 88%.

## Reproduce
```
.venv/bin/python -I -c "from sim.data import hundredcar as hc; print(hc.fetch('<data-only dir>'))"
.venv/bin/python -I eval/real_crash_eval.py --data-dir <data-only dir> --n 100   # ~5 min on a laptop CPU
.venv/bin/python -m pytest -q tests/test_real_crash_eval.py                     # synthetic fixtures
```
