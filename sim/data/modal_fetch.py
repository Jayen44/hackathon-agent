"""Modal app `accel-data`: dataset download + event extraction next to the data, not on a laptop.

Volume `accel-data` is mounted at /data. CitySim CSVs go under /data/citysim/,
TGSIM (FHWA, US public domain, no sign-up) under /data/tgsim/<dataset>/.

TGSIM (see sim/data/tgsim.py for licence and columns):
    modal run sim/data/modal_fetch.py::fetch_tgsim --dataset i90_94_stationary
    modal run sim/data/modal_fetch.py::tgsim_pipeline --dataset i90_94_stationary
Downloaded files are data only: read with pandas, never executed or unpacked.

CitySim:

NO DOWNLOAD FUNCTION ON PURPOSE. CitySim is not freely downloadable: access is
by a signed request form emailed to the UCF SST lab, non-commercial use only,
no redistribution (asset/MainPage/Data_Request_Form.pdf in
github.com/UCF-SST-Lab/UCF-SST-CitySim1-Dataset). Once a human has been granted
access, they upload the files themselves, e.g.:
    modal volume put accel-data ./FreewayC-01.csv /citysim/FreewayC-01.csv

Run (examples):
    modal run sim/data/modal_fetch.py::list_files
    modal run sim/data/modal_fetch.py::main --csv FreewayC-01.csv --location "Freeway C" --kind cut_in
"""
from __future__ import annotations

import modal

app = modal.App("accel-data")
volume = modal.Volume.from_name("accel-data", create_if_missing=True)
image = (modal.Image.debian_slim(python_version="3.12")
         .pip_install("numpy", "pandas")
         .add_local_python_source("sim"))


@app.function(image=image, volumes={"/data": volume}, timeout=60 * 60)
def list_files() -> list[str]:
    from pathlib import Path
    root = Path("/data/citysim")
    return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file()) if root.exists() else []


@app.function(image=image, volumes={"/data": volume}, timeout=60 * 60, memory=8192)
def extract_events(csv: str, location: str, kind: str, thresholds: dict | None = None,
                   mirror_y: bool = False, limit: int = 50) -> list[dict]:
    """find_events on /data/citysim/<csv>; returns the worst `limit` events as dicts."""
    from sim.data import citysim as cs
    rec = cs.load_recording(csv, location, mirror_y=mirror_y)
    evs = cs.find_events(rec, kind, cs.EventThresholds(**(thresholds or {})))
    return [cs.event_to_dict(e) for e in evs[:limit]]


# ---------------------------------------------------------------- TGSIM

SOCRATA = "https://data.transportation.gov"
TGSIM_ROOT = "/data/tgsim"
# Wheelbase is not in TGSIM. Labelled assumption for the kinematic model only
# (the replayed ego does not steer, so it barely affects B2).
ASSUMED_WHEELBASE_M = 2.7


def _download(url: str, dest, chunk: int = 1 << 20) -> dict:
    import hashlib
    import urllib.request
    h = hashlib.sha256()
    n = 0
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "accel-data/1.0 (research)"})
    with urllib.request.urlopen(req, timeout=600) as r, open(tmp, "wb") as f:
        while True:
            b = r.read(chunk)
            if not b:
                break
            f.write(b)
            h.update(b)
            n += len(b)
    tmp.rename(dest)
    return {"url": url, "path": str(dest), "bytes": n, "sha256": h.hexdigest()}


@app.function(image=image, volumes={"/data": volume}, timeout=60 * 60)
def fetch_tgsim(dataset: str = "i90_94_stationary", include_images: bool = False,
                force: bool = False) -> dict:
    """Download one TGSIM trajectory set (+ csv/xlsx attachments) to /data/tgsim/<dataset>/.

    Public, no sign-up, no terms click-through: plain HTTPS GETs on the
    data.transportation.gov (Socrata) export and attachment endpoints.
    """
    import json
    import time
    import urllib.request
    from pathlib import Path

    from sim.data.tgsim import DATASETS
    info = DATASETS[dataset]
    sid = info["socrata"]
    out = Path(TGSIM_ROOT) / dataset
    out.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(f"{SOCRATA}/api/views/{sid}.json", timeout=60) as r:
        meta = json.loads(r.read())
    (out / "socrata_metadata.json").write_text(json.dumps(meta, indent=1))
    files = []
    main_csv = out / info["file"]
    if force or not main_csv.exists():
        files.append(_download(f"{SOCRATA}/api/views/{sid}/rows.csv?accessType=DOWNLOAD", main_csv))
    att_dir = out / "attachments"
    att_dir.mkdir(exist_ok=True)
    for a in meta.get("metadata", {}).get("attachments", []):
        fn = a["filename"]
        ext = fn.rsplit(".", 1)[-1].lower()
        if ext not in ("csv", "xlsx", "pdf") and not (include_images and ext in ("png", "jpg")):
            continue  # zips are skipped on purpose (never unpacked here)
        dest = att_dir / Path(fn).name
        if dest.exists() and not force:
            continue
        files.append(_download(f"{SOCRATA}/api/views/{sid}/files/{a['assetId']}?download=true", dest))
    cf = meta.get("metadata", {}).get("custom_fields", {})
    manifest = {"dataset": dataset, "socrata_id": sid, "name": meta.get("name"),
                "licence": cf.get("Common Core", {}).get("License"),
                "public_access": cf.get("Common Core", {}).get("Public Access Level"),
                "attribution": meta.get("attribution"), "fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "files": files}
    old = out / "manifest.json"
    if old.exists() and not force:
        prev = json.loads(old.read_text())
        known = {f["path"] for f in files}
        manifest["files"] = files + [f for f in prev.get("files", []) if f["path"] not in known]
    old.write_text(json.dumps(manifest, indent=1))
    volume.commit()
    return manifest


@app.function(image=image, volumes={"/data": volume}, timeout=60 * 60)
def list_tgsim() -> list[tuple[str, int]]:
    from pathlib import Path
    root = Path(TGSIM_ROOT)
    return sorted((str(p.relative_to(root)), p.stat().st_size) for p in root.rglob("*") if p.is_file()) \
        if root.exists() else []


@app.function(image=image, volumes={"/data": volume}, timeout=2 * 60 * 60, memory=16384, cpu=4)
def extract_events_tgsim(dataset: str = "i90_94_stationary", runs: str = "",
                         thresholds_json: str = "") -> dict:
    """Find cut-in and lead-brake events in every run; write them to
    /data/tgsim/<dataset>/events/{cut_in,lead_brake}.json and a summary.json.

    runs: comma-separated run_index values ("" = all); thresholds_json: JSON
    object of EventThresholds overrides (strings so `modal run` can pass them)."""
    import json
    import math
    import time
    from pathlib import Path

    from sim.data import tgsim as tg
    info = tg.DATASETS[dataset]
    out = Path(TGSIM_ROOT) / dataset / "events"
    out.mkdir(parents=True, exist_ok=True)
    th = tg.EventThresholds(**(json.loads(thresholds_json) if thresholds_json else {}))
    run_list = [int(r) for r in runs.split(",") if r.strip()] or None
    events = {"cut_in": [], "lead_brake": []}
    checks = []
    t0 = time.time()
    for rec in tg.load_recordings(Path(TGSIM_ROOT) / dataset / info["file"], dataset, runs=run_list):
        df = tg.prepare(rec, th)
        lo = tg.lane_lateral_order(df)
        checks.append({"run": int(df["run"].iloc[0]), "rows": len(df), "vehicles": int(df["id"].nunique()),
                       "automated_vehicles": int(df.loc[df["automated"], "id"].nunique()),
                       "dropped_rows": int(rec.df.attrs.get("dropped_rows", 0)),
                       "lane_median_y_m": lo.to_dict(orient="records")})
        for kind in events:
            events[kind] += [tg.event_to_dict(e) for e in tg.find_events(rec, kind, th, df=df)]
        print(f"run {checks[-1]['run']}: {len(events['cut_in'])} cut_in, "
              f"{len(events['lead_brake'])} lead_brake so far ({time.time() - t0:.0f}s)", flush=True)

    def summary(evs):
        ttc = [e["min_ttc_s"] for e in evs if e["min_ttc_s"] is not None]
        clean = [e["min_ttc_s"] for e in evs if e["min_ttc_s"] is not None and not e["meta"]["bbox_overlap"]]
        return {"n": len(evs),
                **{f"min_ttc_le_{x}s": sum(t <= x for t in ttc) for x in (1.0, 1.5, 2.0, 3.0)},
                "bbox_overlap": sum(e["meta"]["bbox_overlap"] for e in evs),
                "n_clean": len(clean),
                **{f"clean_min_ttc_le_{x}s": sum(t <= x for t in clean) for x in (1.0, 1.5, 2.0, 3.0)},
                "ego_automated": sum(e["meta"]["ego_automated"] for e in evs),
                "other_automated": sum(e["meta"]["other_automated"] for e in evs)}

    for kind, evs in events.items():
        evs.sort(key=lambda e: math.inf if e["min_ttc_s"] is None else e["min_ttc_s"])
        (out / f"{kind}.json").write_text(json.dumps(evs))
    summ = {"dataset": dataset, "thresholds": th.__dict__, "runs": checks,
            "counts": {k: summary(v) for k, v in events.items()},
            "seconds": round(time.time() - t0, 1)}
    (out / "summary.json").write_text(json.dumps(summ, indent=1))
    volume.commit()
    return summ


@app.function(image=image, volumes={"/data": volume}, timeout=60 * 60, memory=8192)
def reconstruct_tgsim(dataset: str = "i90_94_stationary", n_per_kind: int = 10,
                      accel_segment_s: float = 0.5, lateral_settle_s: float = 0.5,
                      min_lateral_shift_m: float = 1.0, include_bbox_overlap: bool = False) -> dict:
    """Rubric B2: replay the measured ego with AVReplayPolicy on the worst-TTC events
    and compare sim vs measured trajectories (RMSE, ADE/FDE). Writes b2.json.
    Events whose boxes overlap (likely artefacts, see tgsim.py) are skipped by default."""
    import json
    from pathlib import Path

    import numpy as np

    from sim.data import tgsim as tg
    from sim.policies.av_replay import AVReplayPolicy
    from sim.world import run
    root = Path(TGSIM_ROOT) / dataset / "events"
    rows = []
    for kind in ("cut_in", "lead_brake"):
        evs = [d for d in json.loads((root / f"{kind}.json").read_text())
               if include_bbox_overlap or not d["meta"]["bbox_overlap"]]
        for d in evs[:n_per_kind]:
            ev = tg.event_from_dict(d)
            case = tg.to_sim_scenario(ev, wheelbase_m=ASSUMED_WHEELBASE_M, accel_segment_s=accel_segment_s,
                                      lateral_settle_s=lateral_settle_s, min_lateral_shift_m=min_lateral_shift_m)
            res = run(case.scenario, AVReplayPolicy(case.ego_accel_profile))
            rows.append({"kind": kind, "run": ev.meta["run"], "ego": ev.ego.id, "other": ev.other.id,
                         "min_ttc_s": ev.min_ttc_s, "min_gap_m": ev.min_gap_m,
                         "ego_automated": ev.meta["ego_automated"], "sim_collided": bool(res.collided),
                         **tg.trajectory_error(ev, res.trace, case.actor_name),
                         **tg.ade_fde(ev, res.trace, case.actor_name)})
    keys = [k for k in rows[0] if k.endswith("_m")]
    dist = {k: {q: float(np.percentile([r[k] for r in rows], p))
                for q, p in (("p50", 50), ("p90", 90), ("max", 100))} | {"mean": float(np.mean([r[k] for r in rows]))}
            for k in keys}
    out = {"dataset": dataset, "n": len(rows), "assumed_wheelbase_m": ASSUMED_WHEELBASE_M,
           "accel_segment_s": accel_segment_s, "distribution": dist,
           "sim_collisions": sum(r["sim_collided"] for r in rows), "events": rows}
    (root / "b2.json").write_text(json.dumps(out, indent=1))
    volume.commit()
    return out


@app.local_entrypoint()
def tgsim_pipeline(dataset: str = "i90_94_stationary", n_per_kind: int = 10, fetch: bool = True,
                   extract: bool = True, runs: str = ""):
    import json
    if fetch:
        m = fetch_tgsim.remote(dataset)
        print(json.dumps({k: m[k] for k in ("name", "licence", "public_access")}, indent=1))
        for f in m["files"]:
            print(f"{f['bytes']:>12,d}  {f['path']}")
    if extract:
        s = extract_events_tgsim.remote(dataset, runs=runs)
        print(json.dumps({k: v for k, v in s.items() if k != "runs"}, indent=1))
        for r in s["runs"]:
            print(json.dumps(r))
    b2 = reconstruct_tgsim.remote(dataset, n_per_kind=n_per_kind)
    print(json.dumps(b2["distribution"], indent=1))


@app.local_entrypoint()
def tgsim_files():
    for p, n in list_tgsim.remote():
        print(f"{n:>13,d}  /data/tgsim/{p}")


@app.local_entrypoint()
def main(csv: str, location: str, kind: str = "cut_in", limit: int = 20):
    for e in extract_events.remote(csv, location, kind, limit=limit):
        print(e["kind"], e["ego"]["id"], e["other"]["id"], e["min_ttc_s"], e["min_gap_m"])
