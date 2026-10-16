"""Render the synthetic CCTV cut-in clip with Blender (bpy, Cycles) on Modal, then apply a CCTV signal chain.

    modal run viz/render/modal_app.py                       # full clip -> viz/render/out/cctv_cut_in.mp4
    modal run viz/render/modal_app.py --test-frame 130      # one still -> viz/render/out/test_0130.png

SYNTHETIC RENDER of a 2D sim trace (viz/isaac/samples/cctv_cut_in_trace.json). Not real footage, not a
real crash. Camera = viz/isaac/assets.CctvCamera, so cctv_cut_in_truth.json's calibration clicks hold.
Frames + mp4 are kept in Modal volume `accel-isaac` under /renders/blender_cctv_cut_in/.
Assets: Poly Haven CC0 only (asphalt_02 textures, kloofendal_48d_partly_cloudy_puresky HDRI).
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import time

import modal

HERE = pathlib.Path(__file__).parent
REPO = HERE.parent.parent
TRACE = REPO / "viz/isaac/samples/cctv_cut_in_trace.json"
OUT = HERE / "out"
NAME = "blender_cctv_cut_in"
VOL = "/vol"
PH = "https://dl.polyhaven.org/file/ph-assets"
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("ffmpeg", "fonts-dejavu-core", "wget", "libxrender1", "libxxf86vm1", "libxfixes3", "libxi6",
                 "libxkbcommon0", "libsm6", "libgl1", "libegl1", "libx11-6", "libgomp1")
    .pip_install("bpy==4.2.0", "numpy<2")
    .run_commands(
        "mkdir -p /assets",
        f"wget -q -O /assets/sky_2k.hdr {PH}/HDRIs/hdr/2k/kloofendal_48d_partly_cloudy_puresky_2k.hdr",
        f"wget -q -O /assets/asphalt_02_diff_2k.jpg {PH}/Textures/jpg/2k/asphalt_02/asphalt_02_diff_2k.jpg",
        f"wget -q -O /assets/asphalt_02_nor_gl_2k.jpg {PH}/Textures/jpg/2k/asphalt_02/asphalt_02_nor_gl_2k.jpg",
        f"wget -q -O /assets/asphalt_02_rough_2k.jpg {PH}/Textures/jpg/2k/asphalt_02/asphalt_02_rough_2k.jpg",
    )
    .add_local_file(HERE / "keys.py", "/root/render/keys.py")
    .add_local_file(HERE / "blender_scene.py", "/root/render/blender_scene.py")
)

app = modal.App("accel-render", image=image)
volume = modal.Volume.from_name("accel-isaac", create_if_missing=True)


def _render(trace_text: str, start: int, end: int, samples: int, device: str, res: int) -> dict:
    import sys
    sys.path.insert(0, "/root/render")
    work = pathlib.Path("/tmp/work")
    work.mkdir(exist_ok=True)
    (work / "trace.json").write_text(trace_text)
    frames = pathlib.Path(VOL) / "renders" / NAME / "frames"
    t0 = time.time()
    import blender_scene  # noqa: PLC0415
    used = blender_scene.main(["--trace", str(work / "trace.json"), "--assets", "/assets", "--out", str(frames),
                               "--start", str(start), "--end", str(end), "--samples", str(samples),
                               "--device", device, "--res", str(res)])
    volume.commit()
    return {"start": start, "end": end, "device": used, "seconds": round(time.time() - t0, 1)}


@app.function(gpu="L4", volumes={VOL: volume}, timeout=3600, cpu=4, memory=16384)
def render_gpu(trace_text: str, start: int, end: int, samples: int = 96, res: int = 100) -> dict:
    return _render(trace_text, start, end, samples, "GPU", res)


@app.function(volumes={VOL: volume}, timeout=3600, cpu=16, memory=16384)
def render_cpu(trace_text: str, start: int, end: int, samples: int = 48, res: int = 100) -> dict:
    return _render(trace_text, start, end, samples, "CPU", res)


@app.function(volumes={VOL: volume}, timeout=1800, cpu=8)
def assemble(n_frames: int, fps: int = 25, bitrate_kbps: int = 1800) -> bytes:
    import sys
    sys.path.insert(0, "/root/render")
    from keys import CCTV_LABEL, cctv_filtergraph, timestamp_texts, x264_args  # noqa: PLC0415
    volume.reload()
    base = pathlib.Path(VOL) / "renders" / NAME
    frames = base / "frames"
    missing = [f for f in range(n_frames) if not (frames / f"{f:04d}.png").exists()]
    if missing:
        raise RuntimeError(f"missing frames: {missing[:20]}")
    work = pathlib.Path("/tmp/asm")
    work.mkdir(exist_ok=True)
    ts = []
    for k, txt in enumerate(timestamp_texts(n_frames / fps)):
        p = work / f"ts_{k:03d}.txt"
        p.write_text(txt)
        ts.append(str(p))
    lab = work / "label.txt"
    lab.write_text(CCTV_LABEL)
    vf = cctv_filtergraph(ts, str(lab), FONT)
    out = base / "cctv_cut_in.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames / "%04d.png"),
                    "-vf", vf, *x264_args(bitrate_kbps), "-r", str(fps), str(out)], check=True)
    # Clean (no CCTV chain) master for reference.
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(frames / "%04d.png"),
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(base / "clean_master.mp4")], check=True)
    volume.commit()
    return out.read_bytes()


@app.function(volumes={VOL: volume}, timeout=600)
def mp4_still(t: float) -> bytes:
    """One PNG frame of the final (CCTV-processed) mp4 at time t, for review."""
    volume.reload()
    src = pathlib.Path(VOL) / "renders" / NAME / "cctv_cut_in.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(t), "-i", str(src), "-frames:v", "1",
                    "/tmp/still.png"], check=True)
    return pathlib.Path("/tmp/still.png").read_bytes()


@app.local_entrypoint()
def still(t: float = 5.2):
    p = OUT / f"still_{t:.2f}.png"
    p.write_bytes(mp4_still.remote(t))
    print(p)


@app.function(volumes={VOL: volume}, timeout=600)
def fetch_frame(f: int) -> bytes:
    volume.reload()
    return (pathlib.Path(VOL) / "renders" / NAME / "frames" / f"{f:04d}.png").read_bytes()


@app.local_entrypoint()
def main(test_frame: int = -1, device: str = "gpu", samples: int = 0, chunk: int = 8, res: int = 100):
    import sys
    sys.path.insert(0, str(HERE))
    from keys import chunks, n_frames  # noqa: PLC0415
    trace_text = TRACE.read_text()
    n = n_frames(json.loads(trace_text), 25)
    fn = render_gpu if device == "gpu" else render_cpu
    kw = {"res": res}
    if samples:
        kw["samples"] = samples
    OUT.mkdir(exist_ok=True)
    t0 = time.time()
    if test_frame >= 0:
        print(fn.remote(trace_text, test_frame, test_frame, **kw))
        p = OUT / f"test_{test_frame:04d}.png"
        p.write_bytes(fetch_frame.remote(test_frame))
        print(p, f"{time.time() - t0:.0f}s")
        return
    jobs = chunks(n, chunk)
    for r in fn.starmap([(trace_text, s, e) for s, e in jobs], kwargs=kw):
        print(r, flush=True)
    print(f"rendered {n} frames in {time.time() - t0:.0f}s", flush=True)
    data = assemble.remote(n)
    p = OUT / "cctv_cut_in.mp4"
    p.write_bytes(data)
    print(p, len(data), "bytes", f"total {time.time() - t0:.0f}s")


det_image = (modal.Image.debian_slim(python_version="3.11")
             .apt_install("libgl1", "libglib2.0-0")
             .pip_install("torch==2.4.1", "transformers==4.46.3", "opencv-python-headless==4.10.0.84",
                          "numpy<2", "pillow", "timm"))
RTDETR = "PekingU/rtdetr_r50vd_coco_o365"   # same detector as sim/video/detect.py (Apache-2.0)


@app.function(image=det_image, gpu="L4", timeout=1800)
def detect_check(video: bytes, threshold: float = 0.3) -> dict:
    """Run the pipeline's detector (RT-DETR) on every frame of a clip or image; return vehicle detections."""
    import cv2
    import torch
    from transformers import RTDetrForObjectDetection, RTDetrImageProcessor
    p = pathlib.Path("/tmp/clip.mp4")
    p.write_bytes(video)
    proc = RTDetrImageProcessor.from_pretrained(RTDETR)
    model = RTDetrForObjectDetection.from_pretrained(RTDETR).cuda().eval()
    names = {int(k): v.lower() for k, v in model.config.id2label.items()}
    keep = {"car", "truck", "bus", "motorcycle", "van", "suv"}
    cap = cv2.VideoCapture(str(p))
    frames, out = [], []

    def flush():
        if not frames:
            return
        inp = proc(images=frames, return_tensors="pt").to("cuda")
        with torch.no_grad():
            o = model(**inp)
        sizes = torch.tensor([[f.shape[0], f.shape[1]] for f in frames], device="cuda")
        for r in proc.post_process_object_detection(o, target_sizes=sizes, threshold=threshold):
            out.append([{"label": names[int(lb)], "score": round(float(s), 3), "box": [round(float(v), 1) for v in b]}
                        for s, lb, b in zip(r["scores"], r["labels"], r["boxes"]) if names[int(lb)] in keep])
        frames.clear()

    while True:
        ok, f = cap.read()
        if not ok:
            break
        frames.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
        if len(frames) == 16:
            flush()
    flush()
    return {"n": len(out), "dets": out}


@app.local_entrypoint()
def check(video: str = str(OUT / "cctv_cut_in.mp4"), frame0: int = 0):
    """modal run viz/render/modal_app.py::check --video <mp4|png> [--frame0 k]: RT-DETR car detection rate per actor."""
    import sys
    sys.path.insert(0, str(HERE))
    from keys import detection_rate, frame_keys, projected_box  # noqa: PLC0415
    trace = json.loads(TRACE.read_text())
    cam = trace["cctv_camera"]
    r = detect_check.remote(pathlib.Path(video).read_bytes())
    keys = frame_keys(trace, 25)[frame0:]
    n = min(len(keys), r["n"])
    tb = [{a: projected_box(cam, *keys[i][a][:3]) for a in keys[i]} for i in range(n)]
    rate = detection_rate(r["dets"][:n], tb)
    labels = {}
    for d in r["dets"]:
        for x in d:
            if x["score"] >= 0.4:
                labels[x["label"]] = labels.get(x["label"], 0) + 1
    print(json.dumps({"frames": n, "rate": rate, "labels_ge_0.4": labels}, indent=1))
    if n <= 3:
        print(json.dumps(r["dets"][:n]), [tb[i] for i in range(n)])
    pathlib.Path(video).with_suffix(".dets.json").write_text(json.dumps(r))
