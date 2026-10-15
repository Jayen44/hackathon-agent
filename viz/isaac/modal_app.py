"""Backup 3D demo visual: render a sim/ trace with NVIDIA Isaac Sim on Modal.

The numbers always come from sim/ (2D kinematic). Isaac Sim only draws them:
boxes on a road, a chase camera, PNG frames, ffmpeg -> mp4.

    # 1. Check the GPU + Vulkan inside the container. Does NOT start Isaac Sim.
    modal run viz/isaac/modal_app.py::gpu_check

    # 2. Render. Starting Isaac Sim requires accepting the NVIDIA Isaac Sim
    #    EULA; only a human may pass --accept-eula.
    modal run viz/isaac/modal_app.py --trace viz/isaac/samples/cut_in_av_replay.json --accept-eula

Writes <trace>.mp4 next to the input JSON and keeps a copy in the Modal
volume `accel-isaac` under renders/<name>/.
"""
from __future__ import annotations

import json
import pathlib

import modal

ISAAC_TAG = "5.1.0"  # pinned: known API (`from isaacsim import SimulationApp`). 6.2.0 is newer but untested.
ISAAC_ROOT = "/isaac-sim"
REMOTE_DIR = "/root/viz_isaac"
VOLUME_PATH = "/vol"

HERE = pathlib.Path(__file__).parent

image = (
    modal.Image.from_registry(f"nvcr.io/nvidia/isaac-sim:{ISAAC_TAG}", add_python="3.11")
    .dockerfile_commands(["USER root"])
    .entrypoint([])
    .apt_install("ffmpeg", "vulkan-tools")
    .env({
        "NVIDIA_DRIVER_CAPABILITIES": "all",
        "NVIDIA_VISIBLE_DEVICES": "all",
        # Deliberately NOT setting ACCEPT_EULA / OMNI_KIT_ACCEPT_EULA here: see render().
    })
    .add_local_file(HERE / "assets.py", f"{REMOTE_DIR}/assets.py")
    .add_local_file(HERE / "render_trace.py", f"{REMOTE_DIR}/render_trace.py")
)

CAPTION = ("ILLUSTRATION of a 2D kinematic sim trace - not video evidence. "
           "Triage aid for a human claims handler, not a liability finding.")
FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

app = modal.App("accel-isaac-render", image=image)
volume = modal.Volume.from_name("accel-isaac", create_if_missing=True)


def _sh(cmd: str, timeout: int = 120) -> str:
    import subprocess
    p = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, timeout=timeout)
    return f"$ {cmd}\n[exit {p.returncode}]\n{p.stdout}{p.stderr}"


@app.function(gpu="L40S", timeout=600)
def gpu_check() -> str:
    """GPU + Vulkan sanity check. Does not start Isaac Sim (no EULA needed)."""
    cmds = [
        "nvidia-smi",
        "vulkaninfo --summary",
        "ls -l /etc/vulkan/icd.d /usr/share/vulkan/icd.d 2>&1",
        "cat /etc/vulkan/icd.d/nvidia_icd.json /usr/share/vulkan/icd.d/nvidia_icd.json 2>&1",
        "ldconfig -p | grep -Ei 'libGLX_nvidia|libnvidia-glcore|libnvidia-rtcore|libEGL_nvidia|libvulkan' ",
        f"ls {ISAAC_ROOT} | head -50",
        "ffmpeg -version | head -1",
        "id; cat /etc/os-release | head -2",
        # licence text shipped in the image (read-only, for ASSETS.md)
        f"head -c 1500 {ISAAC_ROOT}/LICENSE.txt; echo; grep -n -i -E 'asset|content|materials|sample' {ISAAC_ROOT}/LICENSE.txt | head -40",
    ]
    out = "\n".join(_sh(c) for c in cmds)
    print(out)
    return out


@app.function(gpu="L40S", timeout=3600, volumes={VOLUME_PATH: volume})
def render(trace: dict, name: str, accept_eula: bool = False, fps: int = 25,
           width: int = 1920, height: int = 1080, camera: str = "chase",
           renderer: str = "RayTracedLighting", assets: str = "isaac", sky: str = "kloofendal",
           caption: bool = True) -> bytes:
    """Render one trace JSON (see export_trace.py) to mp4 bytes."""
    import os
    import shutil
    import subprocess

    if not accept_eula:
        raise RuntimeError(
            "Starting Isaac Sim requires accepting the NVIDIA Isaac Sim EULA "
            "(https://docs.omniverse.nvidia.com/dev-guide/latest/common/NVIDIA_Omniverse_License_Agreement.html). "
            "A human must read it and pass --accept-eula."
        )

    work = pathlib.Path("/tmp/render")
    frames = work / "frames"
    shutil.rmtree(work, ignore_errors=True)
    frames.mkdir(parents=True)
    trace_path = work / "trace.json"
    trace_path.write_text(json.dumps(trace))

    env = dict(os.environ, ACCEPT_EULA="Y", OMNI_KIT_ACCEPT_EULA="YES", PRIVACY_CONSENT="N")
    cmd = [f"{ISAAC_ROOT}/python.sh", f"{REMOTE_DIR}/render_trace.py", str(trace_path), str(frames),
           "--fps", str(fps), "--width", str(width), "--height", str(height), "--camera", camera,
           "--renderer", renderer, "--assets", assets, "--sky", sky]
    print("$", " ".join(cmd), flush=True)
    p = subprocess.run(cmd, env=env, cwd=ISAAC_ROOT)
    pngs = sorted(frames.glob("frame_*.png"))
    if p.returncode != 0 and not pngs:
        raise RuntimeError(f"Isaac render failed (exit {p.returncode}), no frames written")
    print(f"{len(pngs)} frames (isaac exit {p.returncode})", flush=True)

    mp4 = work / f"{name}.mp4"
    vf = "pad=ceil(iw/2)*2:ceil(ih/2)*2"
    if caption and pathlib.Path(FONT).exists():
        label = trace.get("meta", {}).get("label") or ""
        (work / "caption.txt").write_text(CAPTION + ("\n" + label if label else ""))
        vf += (f",drawtext=fontfile={FONT}:textfile={work / 'caption.txt'}:fontsize=h/40:fontcolor=white"
               ":box=1:boxcolor=black@0.55:boxborderw=12:x=24:y=h-th-24")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
                    "-i", str(frames / "frame_%05d.png"),
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                    "-vf", vf, str(mp4)], check=True)

    dest = pathlib.Path(VOLUME_PATH) / "renders" / name
    shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True)
    shutil.copy(mp4, dest / mp4.name)
    shutil.copy(trace_path, dest / "trace.json")
    if pngs:
        shutil.copy(pngs[len(pngs) // 2], dest / "poster.png")
    volume.commit()
    return mp4.read_bytes()


@app.local_entrypoint()
def main(trace: str, accept_eula: bool = False, camera: str = "chase", fps: int = 25,
         renderer: str = "RayTracedLighting", assets: str = "isaac", sky: str = "kloofendal"):
    src = pathlib.Path(trace)
    data = json.loads(src.read_text())
    name = data.get("name") or src.stem
    out = render.remote(data, name, accept_eula=accept_eula, fps=fps, camera=camera,
                        renderer=renderer, assets=assets, sky=sky)
    dst = src.with_suffix(".mp4")
    dst.write_bytes(out)
    print(f"wrote {dst} ({len(out) / 1e6:.1f} MB)")
