# sim/: owner Vakhtang

Read the root CLAUDE.md first. This file adds rules for `sim/` only.

## What is here
- `vehicle.py`: geometry, state, kinematic bicycle step, SAT collision test. Frame: x along road, y lateral (left +), ego lane centred on y = 0, SI units.
- `scenario.py`: `SimScenario` (point values, one Monte Carlo sample). Other road users are `ScriptedActor`s (accel profile + optional cosine lane change). Only the ego is policy-driven.
- `world.py`: `run(scenario, policy) -> SimResult` (collision, impact type, speeds, trace for `viz/`). Policies implement `reset()` and `act(obs) -> (accel, steer)`.
- `policies/careful_base.py`: `ReactiveBrakingDriver` + `DriverParams`. No values in this file.
- `policies/careful_a.py` / `careful_b.py`: R157 Annex 3 Performance model 1 (CCDM) / 2 (FSM). `PARAMS = None` until Vakhtang fills them from the regulation text; `make_policy()` raises `ParamsMissing` until then.
- `policies/av_replay.py`: replays the AV's reported accel profile.
- `reproduce.py`: Reconstructor check, sim outcome vs reported outcome.

## Rules
- Never put a number in `careful_a.py` / `careful_b.py` that is not quoted from R157 Annex 3 (cite paragraph in a comment). Test fixtures live in `tests/test_sim.py` and are labelled as not-R157.
- Ranges -> samples happens in `montecarlo/`, not here. `sim/` stays deterministic: same scenario + policy = same result.
- Keep one run well under 10 ms (currently ~1.6 ms for a 10 s scenario at dt 0.02). `tests/test_sim.py::test_single_run_is_fast` guards this.
- Run `.venv/bin/python -m pytest -q` before every commit.
