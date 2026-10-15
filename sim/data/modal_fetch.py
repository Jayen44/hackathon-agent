"""Modal app `accel-data`: CitySim event extraction next to the data, not on a laptop.

Volume `accel-data` is mounted at /data; CitySim CSVs go under /data/citysim/.

NO DOWNLOAD FUNCTION ON PURPOSE. CitySim is not freely downloadable: access is
by a signed request form emailed to the UCF SST lab, non-commercial use only,
no redistribution (asset/MainPage/Data_Request_Form.pdf in
github.com/UCF-SST-Lab/UCF-SST-CitySim1-Dataset). Once a human has been granted
access, they upload the files themselves, e.g.:
    modal volume put accel-data ./FreewayC-01.csv /citysim/FreewayC-01.csv

Run (examples):
    modal run sim/data/modal_fetch.py::list_files
    modal run sim/data/modal_fetch.py --csv FreewayC-01.csv --location "Freeway C" --kind cut_in
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


@app.local_entrypoint()
def main(csv: str, location: str, kind: str = "cut_in", limit: int = 20):
    for e in extract_events.remote(csv, location, kind, limit=limit):
        print(e["kind"], e["ego"]["id"], e["other"]["id"], e["min_ttc_s"], e["min_gap_m"])
