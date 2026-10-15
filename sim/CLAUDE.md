# sim/: owner Vakhtang (branch `sim`)

Read the root CLAUDE.md and MARKING_CRITERIA.md first. This file holds the sim-only detail. Vakhtang owns `sim/`, `montecarlo/` and `viz/`. Do not edit other folders or the `insurance` branch.

## Job
Evidence (tier 0 report / tier 1 video / tier 2 telemetry) → reconstructed scenario → counterfactual P(avoid) for careful drivers A and B with 90% CI → hand-off fields in root CLAUDE.md §5. We own rubric sections A, B, C and the sim half of D.

## Physics: 2D kinematic, on purpose
- Video maps to the ground plane, and R157 driver models are defined in longitudinal/lateral kinematics, so 2D is the right physics layer. 3D is used for sightlines (could a careful driver see the hazard?) and for rendering.
- One 10 s run ≈ 1.6 ms → tens of thousands of Monte Carlo runs per minute. Keep one run well under 10 ms (`test_single_run_is_fast`).
- Frame: x along road, y lateral (left +), ego lane centred y = 0, SI units. Positions are vehicle centres.

## Driver models (UN R157 Annex 3)
- Careful driver A = Performance model 1 (CCDM); B = Performance model 2 (FSM). Olleja et al. 2025 (Chalmers): one brakes too late, one is over-cautious, so run both as lower/upper bounds.
- R157 covers cut-in, cut-out and lead-vehicle deceleration. Prioritise those. Other crash types use a clearly labelled rule-based careful driver (lower confidence).
- Parameters come from the regulation text, entered by Vakhtang, with paragraph cited in a comment. `PARAMS = None` until then; `make_policy()` raises `ParamsMissing`. Never guess them. Test fixtures in tests are labelled "not R157".

## Layout
- `sim/vehicle.py`: geometry, state, kinematic bicycle step, SAT collision.
- `sim/scenario.py`: `SimScenario` (one point sample). Other road users are `ScriptedActor`s (accel profile + cosine lane change); only the ego is policy-driven.
- `sim/world.py`: `run(scenario, policy) -> SimResult` (collision, impact type, speeds, trace).
- `sim/policies/`: `careful_base.py` (no values), `careful_a.py`, `careful_b.py`, `av_replay.py`.
- `sim/reproduce.py`: reconstruction check vs reported outcome.
- `sim/data/`: TGSIM loader (FHWA, US public domain, on Modal volume `accel-data`) = real trajectory ground truth for B2; CitySim loader kept but CitySim is non-commercial + request-form only, so unused.
- `montecarlo/`: ranges with source tags → samples, P(avoid) + Wilson CI90, paired A/B sampling, sensitivity, Modal fan-out.
- `viz/web/`: three.js side-by-side replay (AV vs A vs B), open-licence car/road assets, `assets/LICENSES.md`.
- `viz/isaac/`: Isaac Sim 5.1 render on Modal (backup visual). Starting Isaac requires the human to accept the NVIDIA EULA via `--accept-eula`; Claude never passes it.

## Reconstructor loop
Sample the scenario, simulate the AV's reported behaviour, check it reproduces the reported outcome (collision, impact type, speed band). If not, revise ranges and retry. Stop when reproduced or after 5 attempts, then mark low confidence.

## Rules
- `sim/` stays deterministic: same scenario + policy = same result. Randomness lives in `montecarlo/` with explicit seeds.
- Data: public only. Downloaded datasets go in a gitignored folder and are never executed. Record licence for every dataset and asset.
- Run `pytest -q` before every commit (CI runs bare `pytest`; `pytest.ini` puts the repo root on the path).
