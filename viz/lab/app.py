"""Sim Lab: interactive control panel for the counterfactual sim, hosted on Modal.

  modal serve viz/lab/app.py     # live-reloading dev URL
  modal deploy viz/lab/app.py    # stable URL for the team / demo

Everything heavy runs on Modal: the web container takes the request, Monte
Carlo chunks fan out to CPU containers, results come back to the browser.
Driver parameters are entered by the user. Until UN R157 Annex 3 values are
filled in (sim/policies/careful_a.py, careful_b.py) the UI labels them PLACEHOLDER.
"""
from __future__ import annotations

import pathlib

import modal

HERE = pathlib.Path(__file__).parent

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("numpy", "fastapi[standard]")
    .add_local_python_source("sim", "montecarlo")
    .add_local_dir(HERE / "static", "/static")
)
app = modal.App("accel-simlab", image=image)


@app.function(cpu=1.0, memory=512, timeout=300)
def eval_chunk(ranges, factories, u):
    from montecarlo.counterfactual import evaluate_chunk
    return evaluate_chunk(ranges, factories, u)


def _modal_map(ranges, factories, chunks):
    return list(eval_chunk.starmap([(ranges, factories, c) for c in chunks], order_outputs=True))


@app.function(cpu=2.0, memory=1024, timeout=600, min_containers=0)
@modal.concurrent(max_inputs=8)
@modal.asgi_app()
def web():
    import functools
    import time

    import numpy as np
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from montecarlo.counterfactual import compare
    from montecarlo.ranges import (PARAM_NAMES, ParamRange, ScenarioRanges, av_replay_policy,
                                   build_scenario, data_sufficiency, values_from_u)
    from montecarlo.sensitivity import tornado
    from sim.policies import careful_a, careful_b
    from sim.policies.careful_base import DriverParams, ReactiveBrakingDriver
    from sim.vehicle import Geometry
    from sim.world import run

    api = FastAPI(title="Sim Lab")

    def driver_factory(p: dict):
        return functools.partial(ReactiveBrakingDriver, DriverParams(**{k: float(v) for k, v in p.items()}))

    def parse(req: dict):
        g = req.get("geometry", {})
        geom = Geometry(float(g.get("length", 4.5)), float(g.get("width", 1.8)), float(g.get("wheelbase", 2.7)))
        rr = {}
        for name, r in req["ranges"].items():
            if name not in PARAM_NAMES:
                raise HTTPException(400, f"unknown param {name}")
            lo, hi = float(r["lo"]), float(r["hi"])
            rr[name] = ParamRange(min(lo, hi), max(lo, hi), source=r.get("source", "prior"))
        try:
            ranges = ScenarioRanges(kind=req["kind"], ego_geometry=geom, other_geometry=geom,
                                    duration=float(req.get("duration", 10.0)), **rr)
        except ValueError as e:
            raise HTTPException(400, str(e))
        drivers = {"careful_a": driver_factory(req["drivers"]["careful_a"]),
                   "careful_b": driver_factory(req["drivers"]["careful_b"])}
        return ranges, drivers

    def trace_json(res):
        return {"t": res.trace["t"][::2], "ego": res.trace["ego"][::2], "other": res.trace["other"][::2],
                "result": {"collided": res.collided, "t_collision": res.t_collision,
                           "impact_type": res.impact_type, "ego_speed_at_impact": res.ego_speed_at_impact,
                           "ended_closing": res.ended_closing}}

    @api.get("/api/meta")
    def meta():
        return {"r157_filled": {"careful_a": careful_a.PARAMS is not None,
                                "careful_b": careful_b.PARAMS is not None},
                "param_names": list(PARAM_NAMES)}

    @api.post("/api/run")
    def run_api(req: dict):
        ranges, drivers = parse(req)
        n = int(min(max(int(req.get("n", 2000)), 100), 50000))
        seed = int(req.get("seed", 0))
        t0 = time.perf_counter()
        res = compare(ranges, drivers, n, seed, map_fn=_modal_map, chunk=max(100, n // 64))
        t_mc = time.perf_counter() - t0
        sens = None
        if req.get("sensitivity", True):
            sens = tornado(ranges, drivers, n=min(n, 1000), seed=seed, map_fn=_modal_map, chunk=100)
        # Replay of the median sample (every range at its midpoint quantile).
        v = values_from_u(ranges, np.full(len(PARAM_NAMES), 0.5))
        scen = build_scenario(ranges, v)
        replays = {"av": trace_json(run(scen, av_replay_policy(ranges, v))),
                   "careful_a": trace_json(run(scen, drivers["careful_a"]())),
                   "careful_b": trace_json(run(scen, drivers["careful_b"]()))}
        return {"montecarlo": res, "sensitivity": sens, "data_sufficiency": data_sufficiency(ranges),
                "median_sample": v, "replays": replays, "geometry": {"length": scen.ego_geometry.length,
                                                                     "width": scen.ego_geometry.width},
                "timing_s": {"montecarlo": round(t_mc, 2), "total": round(time.perf_counter() - t0, 2)}}

    @api.get("/")
    def index():
        return FileResponse("/static/index.html")

    api.mount("/static", StaticFiles(directory="/static"), name="static")
    return api
