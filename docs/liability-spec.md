# Liability spec: driverless-car crash data, competent-driver threshold, who pays

_Reference document. Read the section you need; do not load all of it every session. Code that implements it: see CLAUDE.md._

## Status of claims in this file
- **[Verified]**: found in a source listed at the bottom.
- **[Knowledge]**: from general knowledge, not checked this session. Verify before relying on it.
- **[Design]**: our own proposal for the prototype. Not an industry standard.

All numbers marked "illustrative" are placeholders. This is decision support, not legal or financial advice.

---

## 1. Data required after a crash

Evidence must be **time-synchronised** (one clock, e.g. GPS/UTC) and **tamper-evident** (hashes or signatures, chain of custody). Without both, no source can be trusted to decide fault.

### 1.1 Vehicle data store (the "black box")
| Data | Why it matters |
|---|---|
| Automation mode and **every mode change**, with timestamps | Who was in control at the moment of the crash [Verified: DSSAD purpose] |
| Handover events: transition demand issued, how long until the human responded | Tests whether the human was given a fair chance to take over |
| Driver/occupant status: hands on wheel, eyes on road, seat belt, driver-monitoring flags | Human conduct, and the user-in-charge exception below |
| Control inputs: steering, throttle, brake, indicator, both **requested by the system** and **actually applied** | Separates a system decision from a human override |
| Vehicle state: speed, acceleration, yaw rate, gear, ABS/ESC activation | Reconstruct motion; check braking was achievable |
| System health and faults: sensor failures, degraded modes, software version, last update | Product defect vs operational failure |
| Operational design domain (ODD) status: inside or outside the conditions the system is approved for | Was the system used where it was meant to be used? |

Retention: UNECE R157 asks for at least six months for DSSAD data, and the harmonised data elements and access rules are incomplete [Verified]. Treat access and retrieval as a risk, not a given.

### 1.2 Perception and planning data (the car's view of the world)
| Data | Why it matters |
|---|---|
| **Camera** video from all cameras, plus per-frame timestamps | What was visible; what a human would have seen |
| **LiDAR** point clouds, **radar** returns, ultrasonic | What was detectable, including at night or in bad weather |
| **Object list**: detected objects, class, position, velocity, confidence, and the **time each object was first detected** | Core of the "would a human have reacted sooner?" test |
| Prediction output: where the system expected others to go | Was the plan reasonable given its own prediction? |
| Planned trajectory and the **decision log** (why it chose to brake, swerve or hold) | Shows intent and whether the choice was sensible |
| Localisation and map data; map version | Wrong map or lost position can be the root cause |
| Pre-crash window: recommend a rolling buffer of **at least 30 seconds before** and a few seconds after. The NHTSA reporting rule uses 30 seconds [Verified] | Captures the full lead-up |

### 1.3 External evidence
| Source | Use |
|---|---|
| **CCTV** (street, shop, transport, building) | Independent view that doesn't depend on the car's own sensors |
| Other vehicles' dashcams and **witness** statements and phone footage | Corroboration, and the human driver's account |
| Police report, scene photos, skid marks, vehicle damage | Physical reconstruction |
| Road layout, signage, speed limits, lighting, surface | What was reasonable at that spot |
| Weather, time of day, sun position | Visibility |
| Traffic signal timing logs | Right of way |
| **Medical** records (injury severity) | Sizing the payout |
| **Telematics from other parties** (e.g. a cyclist's phone) | Alternative speed and path evidence |

### 1.4 Integrity checks to run on all evidence
- Do the clocks agree? Reconcile with a known event.
- Does the car's account match the CCTV? A mismatch flags tampering or sensor error.
- Is the log complete, or are gaps present around the crash?
- Is the software the **approved** version?
- Who has accessed or exported the data?

---

## 2. The "careful and competent human driver" threshold

### 2.1 Where the standard comes from
- UK Automated Vehicles Act 2024: authorisation relies on safety principles aiming for a level of safety **equivalent to or higher than careful and competent human drivers** [Verified]. The detailed principles were still being developed in the sources I found, so check current status.
- Waymo's industry benchmark, **NIEON** (Non-Impaired, with Eyes ON the conflict): an always-attentive, unimpaired reference driver with a surprise-based reaction time and a defined braking/evasion model [Verified]. It is Waymo's own model and is used for collision-avoidance evaluation. Treat it as one published reference, not the legal test.

### 2.2 How we use it: the counterfactual test [Design]
For each crash, replay the scenario with a **reference human driver model** in place of the system and ask: *would a careful and competent human have avoided it, or reduced its severity?*

1. **Reconstruct** the scenario from section 1 data: positions, speeds, visibility, when each hazard became detectable.
2. **Find the conflict start**: the earliest time a human with normal vision could reasonably have perceived the hazard (use the camera, CCTV and lighting data, not just the car's detection time).
3. **Apply the human model**: reaction time after the conflict starts, then a brake and/or steer response up to a realistic maximum deceleration and jerk, within road limits. Illustrative inputs: reaction time drawn from a range of roughly 0.7 to 1.5 s depending on surprise and visibility [Knowledge, to calibrate]; limited friction on wet roads.
4. **Compare outcomes**: crash/no crash and impact speed, for the system versus the reference human.
5. **Classify**:

| Result | Meaning |
|---|---|
| System avoided, or impact reduced, relative to the human model | Meets the standard |
| Human model avoids the crash, system didn't | **System fell below the competent-driver standard** |
| Neither could avoid it (unavoidable, e.g. a child running out from behind a parked van at close range) | No fault from the driving performance |
| Human model also fails, but the system was outside its ODD or in a known degraded state | Operational/ODD failure: tech company or operator responsible |

6. **Report confidence**, not just a verdict: run the human model across a range of reaction times (e.g. 5th, 50th, 95th percentile) and report how often the human would have avoided the crash. A verdict that flips between percentiles should go to human review.

### 2.3 Other conduct checks
- Did the system break a traffic rule (speed, red light, right of way)?
- Was the manoeuvre one a careful driver would not have attempted?
- Did the system fail to give a **timely, adequate** handover warning?
- Did the human act recklessly (see 3.2)?

---

## 3. Who pays: switching liability between human and tech company

### 3.1 The key variable is **who was in control**
| State at the time of the crash | Primary responsible party | Notes |
|---|---|---|
| Human driving (manual or driver assistance) | **Human driver** and their motor insurer | Normal motor claim |
| Self-driving engaged, human a "user-in-charge", system within its ODD | **Tech company / authorised self-driving entity (ASDE)** | Human has immunity for the driving [Verified, UK] |
| Self-driving engaged, **no human on board** (e.g. robotaxi) | Operator / ASDE | Operator responsible if injury occurs under their operation [Verified, UK] |
| Handover requested and human **failed to respond** after a fair, adequate warning | Shifts back to **human** | Immunity is conditional: it doesn't cover recklessly refusing a transition demand [Verified, UK] |
| Human overrode the system and caused the crash | **Human** | The control-input log decides this |
| System outside its approved ODD, but human insisted on using it | Mixed: depends on warnings given | Needs a documented policy |
| Defect or software bug (design or programming flaw) | **Manufacturer / developer** | Product-liability basis [Verified, UK] |

The user-in-charge immunity does **not** cover non-driving failures such as being uninsured [Verified]. The human still needs insurance for those and for manual driving.

### 3.2 Decision flow [Design]
```
1. Verify evidence integrity (1.4). If it fails -> human review.
2. Determine control state at T-crash (mode log + driver monitoring).
   - Manual -> human claim. Stop.
3. If self-driving engaged:
   a. Was a handover requested?
      - Yes, adequate warning, human did not respond -> human liable (check "reckless").
      - Yes, inadequate/late warning -> tech company liable.
   b. Was the system inside its ODD and on an approved software version?
      - No -> tech company/operator liable (unless human knowingly misused it).
   c. Run the competent-driver counterfactual (section 2).
      - System fell short -> tech company liable.
      - Unavoidable for a competent human -> no driving fault; sort cause (third party, road defect).
   d. Check for system faults/defects -> manufacturer liable (and subrogation, below).
4. Output: liable party, confidence, evidence list, items needing human review.
```

### 3.3 Paying the victim first, then recovering [Verified: see docs/verification.md]
UK Automated and Electric Vehicles Act 2018: s.2 makes the **insurer** liable when a listed automated vehicle driving itself causes an accident in Great Britain. s.5 lets the insurer recover from any other person liable to the injured party, but only once the insurer's liability is **settled**, and never more than that person's liability to the victim. s.3(1) applies contributory negligence; s.3(2) removes cover for the person in charge if the accident was wholly due to their negligence in letting the car drive itself when inappropriate; s.4 allows policy exclusions for unauthorised software changes or missed safety-critical updates.

**Regime caveat (see `docs/legal-basis.md`):** no vehicle is on the AEVA list today, so s.2/s.5 do not yet cover supervised pilots such as the London Uber + Wayve service; today's routes are contribution (1978 Act) or the Consumer Protection Act 1987. This spec models the AEVA s.5 route (the regime once vehicles are listed or authorised); a per-claim `regime` field is a to-do.

Note: "careful and competent human driver" is the AV Act 2024 *authorisation* benchmark, not the civil test under s.5 (which asks who is liable to the injured party). Using our counterfactual as a proxy for that is a modelling assumption.

The practical model: pay the victim fast, then run subrogation against the tech company if the counterfactual and evidence show the system fell short. Jurisdictions differ (US states, EU, Germany), so keep the UK as the default assumption for the prototype and label it.

### 3.4 Moral hazard and disputes to design for
- Tech companies hold the data and have an incentive to present it favourably, so demand **independent access** and integrity checks.
- Humans over-trust the system, and "hands off" behaviour is common, so driver-monitoring data matters.
- Software updates change behaviour, so always record the software version.
- Fleet-wide faults (one bug, many cars) are a **correlated tail risk**, not an isolated claim.

---


## Sources
- [UK Automated Vehicles Act: SCL summary](https://www.scl.org/the-uks-automated-vehicles-act-unlocking-opportunities-for-uk-investment-and-innovation-in-the-automotive-sector/)
- [Ashfords: Automated Vehicles Act 2024](https://www.ashfords.co.uk/insights/articles/automated-vehicles-act-2024-revolutionising-the-future-of-transportation)
- [Slaughter and May: AV Act 2024](https://thelens.slaughterandmay.com/post/102j8ih/the-automated-vehicles-act-2024-becomes-law-in-the-uk)
- [Waymo: Benchmarking AV safety](https://waymo.com/blog/2022/09/benchmarking-av-safety/)
- [Waymo collision avoidance testing paper (arXiv)](https://arxiv.org/pdf/2212.08148)
- [Survey of driver models for AV safety assessment (arXiv)](https://arxiv.org/pdf/2303.14779)
- [German Road Safety Council on EDR and DSSAD](https://dvr.de/ueber-uns/resolutions/statement-by-the-german-road-safety-council-dvr-on-edr-and-dssad)
- [UNECE R157 summary (regulations.ai)](https://regulations.ai/regulations/RAI-IO-UNECE-R157-2021)
- [TRL: regulatory preparation for ADS approval](https://www.trl.co.uk/Uploads/TRL/Brochures/Regulatory%20preparation%20for%20ADS%20approval_Summary.pdf)
- [IEEE 3501 / 1616.1 DSSAD standards](https://standards.ieee.org/ieee/3501/10939/)
- [NHTSA Standing General Order crash reporting](https://www.nhtsa.gov/SGOCrashReporting)
