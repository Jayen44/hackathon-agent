"""Sim Lab "From CCTV" routes: upload -> GPU detect/track -> calibrate -> measured bundle -> P(avoid).

Uploaded videos and their metadata are UNTRUSTED data: ids are server-generated hex, file
names are never used as paths, sizes are capped while streaming, JSON bodies are validated.
Raw video never leaves the Modal volume; only privacy-blurred stills are served.
"""

import hashlib
import json
import re
import shutil
import time
import uuid
from pathlib import Path

VID_RE = re.compile(r"^[0-9a-f]{32}$")
RID_RE = re.compile(r"^[0-9a-f]{12}$")
CLAIMS_API = "https://termvato--accel-claims-api-web.us-east.modal.run"
LAB_BASE = "https://termvato--accel-simlab-web.us-east.modal.run"


def pixel_paths(tj: dict, ids: list[int]) -> list[list[float]]:
    """Bottom-centre pixel path of one vehicle (all its track fragments, in frame order)."""
    pts = []
    for tid in ids:
        t = (tj.get("tracks") or {}).get(str(int(tid)))
        if t:
            pts += [(f, (b[0] + b[2]) / 2, b[3]) for f, b in zip(t["frames"], t["boxes"])]
    pts.sort()
    step = max(1, len(pts) // 150)
    return [[round(u, 1), round(v, 1)] for _, u, v in pts[::step]]


def add_cctv_routes(api, vol, vol_root: str, detect_fn, map_fn, max_bytes, video_ext, claims_api: str = CLAIMS_API):
    import modal
    from fastapi import File, Form, HTTPException, Request, UploadFile
    from fastapi.responses import FileResponse, JSONResponse

    root = Path(vol_root) / "uploads"

    def vdir(vid: str) -> Path:
        if not VID_RE.match(vid or ""):
            raise HTTPException(404, "unknown video")
        return root / vid

    def reload():
        try:
            vol.reload()
        except Exception:
            pass  # another request has files open; next poll will see the data

    def read_json(p: Path):
        if not p.exists():
            reload()
        if not p.exists():
            return None
        return json.loads(p.read_text())

    @api.get("/cctv")
    def cctv_page():
        return FileResponse("/static/cctv.html")

    @api.post("/api/video/upload")
    async def upload(file: UploadFile = File(...), blur_plates: str = Form("1")):
        ext = Path(file.filename or "").suffix.lower()
        if ext not in video_ext:
            raise HTTPException(400, f"unsupported file type; use one of {sorted(video_ext)}")
        vid = uuid.uuid4().hex
        d = root / vid
        d.mkdir(parents=True, exist_ok=False)
        h = hashlib.sha256()
        size = 0
        dst = d / f"video{ext}"
        with dst.open("wb") as f:
            while chunk := await file.read(1 << 20):
                size += len(chunk)
                if size > max_bytes:
                    f.close()
                    shutil.rmtree(d, ignore_errors=True)
                    raise HTTPException(413, f"video larger than {max_bytes // (1024 * 1024)} MB")
                h.update(chunk)
                f.write(chunk)
        plates = blur_plates not in ("0", "false", "off")
        meta = {"id": vid, "file": dst.name, "bytes": size, "sha256": h.hexdigest(), "uploaded": time.time(),
                "blur_plates": plates}
        (d / "meta.json").write_text(json.dumps(meta))
        vol.commit()
        call = detect_fn.spawn(vid, plates)
        meta["call_id"] = call.object_id
        (d / "meta.json").write_text(json.dumps(meta))
        vol.commit()
        return {"id": vid, "bytes": size, "sha256": meta["sha256"]}

    @api.get("/api/video/{vid}/status")
    def status(vid: str):
        d = vdir(vid)
        st = read_json(d / "status.json")
        if st is None:
            meta = read_json(d / "meta.json")
            if meta is None:
                raise HTTPException(404, "unknown video")
            try:
                st = modal.FunctionCall.from_id(meta["call_id"]).get(timeout=0)
            except TimeoutError:
                return {"state": "running", "elapsed_s": round(time.time() - meta["uploaded"], 1)}
            except Exception as e:
                return {"state": "error", "error": f"{type(e).__name__}: {e}"}
            reload()
        if not st.get("ok"):
            return {"state": "error", "error": st.get("error")}
        return {"state": "done", **{k: v for k, v in st.items() if k != "trace"}}

    @api.get("/api/video/{vid}/tracks")
    def tracks(vid: str):
        tj = read_json(vdir(vid) / "tracks.json")
        if tj is None:
            raise HTTPException(404, "detection not finished")
        fps = tj["fps"]
        out = []
        for tid, t in tj["tracks"].items():
            fr, bx = t["frames"], t["boxes"]
            step = max(1, len(fr) // 120)
            path = [[round((b[0] + b[2]) / 2, 1), round(b[3], 1)] for b in bx[::step]]
            out.append({"id": int(tid), "cls": t["cls"], "n": len(fr), "t0": round(fr[0] / fps, 2),
                        "t1": round(fr[-1] / fps, 2), "path": path, "thumb": tid in tj.get("thumbs", [])})
        out.sort(key=lambda r: -r["n"])
        return {"fps": fps, "width": tj["width"], "height": tj["height"], "model": tj["model"],
                "tracker": tj["tracker"], "plates_blurred": tj.get("plates_blurred"), "tracks": out}

    @api.get("/api/video/{vid}/frame0.jpg")
    def frame0(vid: str):
        p = vdir(vid) / "frame0.jpg"
        if not p.exists():
            reload()
        if not p.exists():
            raise HTTPException(404, "not ready")
        return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @api.get("/api/video/{vid}/track/{tid}.jpg")
    def thumb(vid: str, tid: int):
        p = vdir(vid) / f"track_{int(tid)}.jpg"
        if not p.exists():
            reload()
        if not p.exists():
            raise HTTPException(404, "no thumbnail")
        return FileResponse(p, media_type="image/jpeg")

    @api.post("/api/video/{vid}/analyze")
    def analyze(vid: str, req: dict):
        from sim.video.calibrate import CalibrationError
        from sim.video.pipeline import run
        from sim.video.trajectories import TrajectoryError

        d = vdir(vid)
        tj = read_json(d / "tracks.json")
        meta = read_json(d / "meta.json")
        if tj is None or meta is None:
            raise HTTPException(404, "detection not finished")
        t0 = time.perf_counter()
        try:
            out = run(tj, req, map_fn=map_fn, case_id=f"cctv-{vid[:8]}", video_sha256=meta["sha256"],
                      synthetic=bool(meta.get("synthetic")))
        except (CalibrationError, TrajectoryError, KeyError, ValueError, TypeError) as e:
            raise HTTPException(400, f"{type(e).__name__}: {e}")
        rid = uuid.uuid4().hex[:12]
        (d / f"replay_{rid}.json").write_text(json.dumps(out["replay"], separators=(",", ":")))
        (d / f"bundle_{rid}.json").write_text(json.dumps(out["analysis"]["bundle"], indent=1))
        a = out["analysis"]
        cal = req.get("calibration") or {}
        run_info = {"measured": a["measured"], "calibration": a["calibration"],
                    "calibration_input": {"mode": cal.get("mode"), "img_pts": cal.get("img_pts")},
                    "ego_ids": a["ego_ids"], "other_ids": a["other_ids"],
                    "frame": {"width": tj.get("width"), "height": tj.get("height")},
                    "paths": {"av": pixel_paths(tj, a["ego_ids"]), "other": pixel_paths(tj, a["other_ids"])}}
        (d / f"run_{rid}.json").write_text(json.dumps(run_info, separators=(",", ":"), default=float))
        vol.commit()
        return {"run_id": rid, "replay_url": f"/api/replay/{vid}/{rid}",
                "viewer_url": f"/viewer/?data=/api/replay/{vid}/{rid}&cam=chase",
                "bundle": a["bundle"], "measured": a["measured"], "calibration": a["calibration"],
                "ego": a["ego"], "other": a["other"], "ego_id": a["ego_id"], "other_id": a["other_id"],
                "ego_ids": a["ego_ids"], "other_ids": a["other_ids"],
                "assumptions": a["assumptions"], "estimate": out["estimate"],
                "sim_av": {k: out["replay"]["runs"]["av"][k] for k in ("t", "ego", "other", "result")},
                "timing_s": round(time.perf_counter() - t0, 2)}

    @api.get("/api/replay/{vid}/{rid}")
    def replay(vid: str, rid: str):
        if not RID_RE.match(rid):
            raise HTTPException(404, "unknown run")
        p = vdir(vid) / f"replay_{rid}.json"
        if not p.exists():
            reload()
        if not p.exists():
            raise HTTPException(404, "unknown run")
        return FileResponse(p, media_type="application/json")

    @api.get("/api/bundle/{vid}/{rid}")
    def bundle(vid: str, rid: str):
        if not RID_RE.match(rid):
            raise HTTPException(404, "unknown run")
        p = vdir(vid) / f"bundle_{rid}.json"
        if not p.exists():
            raise HTTPException(404, "unknown run")
        return FileResponse(p, media_type="application/json", filename=f"bundle_{vid[:8]}_{rid}.json")

    @api.post("/api/video/{vid}/claim")
    async def send_claim(vid: str, request: Request):
        """CCTV run + insurer claim file -> full schema 0.1 bundle -> claims API /api/assess (server to server).
        Returns the claim id and the dashboard URL to open (only our dashboards are allowed as return URL)."""
        import asyncio
        import urllib.error
        import urllib.request

        from viz.lab.cctv_claim import ClaimFileError, build_claim_bundle, safe_return_url

        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "body must be JSON")
        if not isinstance(body, dict):
            raise HTTPException(400, "body must be a JSON object")
        rid = str(body.get("run_id") or "")
        if not RID_RE.match(rid):
            raise HTTPException(400, "unknown run")
        d = vdir(vid)
        cb, run_info, meta = (read_json(d / f"bundle_{rid}.json"), read_json(d / f"run_{rid}.json"),
                              read_json(d / "meta.json"))
        if cb is None or meta is None:
            raise HTTPException(404, "unknown run")
        if run_info is None:
            raise HTTPException(409, "this run predates claim export; press 'Measure & run' again")
        try:
            bundle = build_claim_bundle(cb, run_info, meta, body.get("claim_file") or {}, vid, rid, LAB_BASE)
        except (ClaimFileError, KeyError, TypeError, ValueError) as e:
            raise HTTPException(400, str(e))
        data = json.dumps({"bundle": bundle}).encode()

        def post():
            rq = urllib.request.Request(f"{claims_api}/api/assess", data=data, method="POST",
                                        headers={"content-type": "application/json"})
            with urllib.request.urlopen(rq, timeout=60) as r:
                return json.loads(r.read())
        try:
            res = await asyncio.to_thread(post)
        except urllib.error.HTTPError as e:
            raise HTTPException(502, f"claims API refused the bundle: HTTP {e.code} {e.read()[:300].decode(errors='replace')}")
        except (urllib.error.URLError, TimeoutError) as e:
            raise HTTPException(502, f"claims API unreachable: {e}")
        cid = res["claim_id"]
        base = safe_return_url(body.get("return_url"))
        return {"claim_id": cid, "status": res.get("status"), "claim_url": f"{base}/claims/{cid}",
                "bundle_bytes": len(data)}

    @api.delete("/api/video/{vid}")
    def delete(vid: str):
        d = vdir(vid)
        if not d.exists():
            reload()
        if not d.exists():
            raise HTTPException(404, "unknown video")
        shutil.rmtree(d, ignore_errors=True)
        vol.commit()
        return JSONResponse({"deleted": vid})
