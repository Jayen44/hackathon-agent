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
ROOT = HERE.parent.parent

image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install("numpy", "fastapi[standard]")
    .add_local_python_source("sim", "montecarlo")
    .add_local_file(ROOT / "viz" / "export.py", "/root/viz/export.py")
    .add_local_file(HERE / "cctv.py", "/root/viz/lab/cctv.py")
    .add_local_file(HERE / "cctv_claim.py", "/root/viz/lab/cctv_claim.py")
    .add_local_dir(ROOT / "viz" / "web", "/viewer")
    .add_local_dir(HERE / "static", "/static")
)
app = modal.App("accel-simlab", image=image)

# CCTV uploads, detector outputs and the HF weight cache live ONLY in this Modal volume
# (not in the repo).
video_vol = modal.Volume.from_name("accel-video", create_if_missing=True)
VOL = "/vol"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}

# GPU image: RT-DETR (Apache-2.0) via transformers + ByteTrack via supervision (MIT). No Ultralytics.
gpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("libglib2.0-0", "libgl1")   # supervision pulls full opencv-python
    .pip_install("torch==2.5.1", "transformers==4.46.3", "supervision==0.25.1",
                 "opencv-python-headless==4.10.0.84", "numpy<2.2", "pillow")
    .env({"HF_HOME": f"{VOL}/hf"})
    .add_local_python_source("sim", "montecarlo")
)


@app.function(image=gpu_image, gpu="L4", volumes={VOL: video_vol}, timeout=1800)
def detect_video(vid: str, plates: bool = True) -> dict:
    """Detect + track vehicles in /vol/uploads/<vid>/video.*, write tracks.json + blurred stills."""
    import json
    import traceback

    from sim.video.detect import detect_and_track

    video_vol.reload()
    d = pathlib.Path(VOL) / "uploads" / vid
    meta = json.loads((d / "meta.json").read_text())
    try:
        summary = {"ok": True, **detect_and_track(str(d / meta["file"]), str(d), plates=plates)}
    except Exception as e:  # untrusted video: report the failure, never crash the app
        summary = {"ok": False, "error": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-800:]}
    (d / "status.json").write_text(json.dumps(summary))
    video_vol.commit()
    return summary


@app.function(cpu=1.0, memory=512, timeout=300)
def eval_chunk(ranges, factories, u):
    from montecarlo.counterfactual import evaluate_chunk
    return evaluate_chunk(ranges, factories, u)


def _modal_map(ranges, factories, chunks):
    return list(eval_chunk.starmap([(ranges, factories, c) for c in chunks], order_outputs=True))


@app.function(cpu=2.0, memory=2048, timeout=900, min_containers=0, volumes={VOL: video_vol})
@modal.concurrent(max_inputs=8)
@modal.asgi_app()
def web():
    import functools
    import time

    import numpy as np
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    from viz.lab.cctv import add_cctv_routes

    from montecarlo.counterfactual import compare
    from montecarlo.ranges import (PARAM_NAMES, ParamRange, ScenarioRanges, av_replay_policy,
                                   build_scenario, data_sufficiency, values_from_u)
    from montecarlo.sensitivity import tornado
    from sim.policies import careful_a, careful_b
    from sim.policies.careful_base import DriverParams, ReactiveBrakingDriver
    from sim.vehicle import Geometry
    from sim.world import run

    api = FastAPI(title="Sim Lab")
    from fastapi.middleware.cors import CORSMiddleware
    # The claims dashboard (Vercel) uploads CCTV straight to this app from its intake form.
    api.add_middleware(CORSMiddleware, allow_methods=["GET", "POST"], allow_headers=["content-type"],
                       allow_origin_regex=r"https://accel-claims-dashboard[a-z0-9-]*\.vercel\.app|http://localhost:\d+")

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

    add_cctv_routes(api, video_vol, VOL, detect_video, _modal_map, MAX_UPLOAD_BYTES, VIDEO_EXT)
    api.mount("/static", StaticFiles(directory="/static"), name="static")
    # 3D replay viewer (viz/web): /viewer/?data=/api/replay/<video id>/<run id>
    api.mount("/viewer", StaticFiles(directory="/viewer", html=True), name="viewer")
    return api
