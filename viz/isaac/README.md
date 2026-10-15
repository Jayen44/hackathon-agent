# viz/isaac: backup 3D render of a sim/ trace (Isaac Sim on Modal)

Backup demo visual only. **All numbers come from `sim/`** (2D kinematic bicycle
model). Isaac Sim just draws the trace: road, lane lines, one box-car per actor
(ego blue), chase or overhead camera, 25 fps PNG frames, ffmpeg to mp4. No
physics runs in Isaac. Primary viz stays the 2D side-by-side replay in `viz/`.

## Files

| file | runs where | what |
|---|---|---|
| `export_trace.py` | local (repo venv) | `export(SimResult, SimScenario, name)` -> renderer JSON; `python -m viz.isaac.export_trace` regenerates `samples/` |
| `render_trace.py` | inside Isaac's `/isaac-sim/python.sh` | builds the USD stage, steps one frame per 1/25 s of the 50 Hz trace, writes `frame_%05d.png` (replicator `rgb` annotator) |
| `modal_app.py` | Modal, `gpu="L40S"` | `gpu_check` (no Isaac), `render(trace, name, accept_eula)`, local entrypoint `main` |
| `samples/*.json` | | ILLUSTRATIVE ONLY: hand-built cut-in (25 m gap, ego 20 m/s, cutter 12 m/s), ego driven by an AV replay with late soft braking (collides, rear_end at 3.4 s) and by the **test-fixture** careful driver from `tests/test_sim.py` (avoids). Not R157 params, not a real crash. |

## Run

```bash
# 0. regenerate samples (or export your own SimResult)
.venv/bin/python -m viz.isaac.export_trace

# 1. GPU + Vulkan check. Pulls the image (~15-20 GB, first time 10+ min). Does NOT start Isaac Sim.
modal run viz/isaac/modal_app.py::gpu_check

# 2. First real render. Starting Isaac Sim = accepting the NVIDIA Isaac Sim EULA.
#    Read it first: https://docs.isaacsim.omniverse.nvidia.com/latest/common/NVIDIA_Omniverse_License_Agreement.html
modal run viz/isaac/modal_app.py --trace viz/isaac/samples/cut_in_av_replay.json --accept-eula
#    -> viz/isaac/samples/cut_in_av_replay.mp4 (+ copy in volume accel-isaac:/renders/<name>/)
#    options: --camera overhead, --fps 25

# 3. Side by side (AV vs careful), pad the shorter clip with its last frame
ffmpeg -i viz/isaac/samples/cut_in_av_replay.mp4 -i viz/isaac/samples/cut_in_careful_test.mp4 \
  -filter_complex "[0:v]tpad=stop_mode=clone:stop_duration=10[a];[1:v]tpad=stop_mode=clone:stop_duration=10[b];[a][b]hstack=shortest=1" \
  -c:v libx264 -pix_fmt yuv420p viz/isaac/samples/side_by_side.mp4
```

Without `--accept-eula`, `render` raises before anything Isaac-related starts.
`ACCEPT_EULA` / `OMNI_KIT_ACCEPT_EULA` are set only in the env of the Isaac
subprocess, never baked into the image.

Your own trace:
```python
from viz.isaac.export_trace import export, write
write(export(result, scenario, "sgo_123_av", policy="av_replay"), "viz/isaac/out/sgo_123_av.json")
```

## Cost (Modal L40S, about USD 1.95/h at time of writing, check modal.com/pricing)

- `gpu_check`: under a minute of GPU, cents. Image build/pull is CPU time and is cached afterwards.
- Render: Isaac cold start (shader cache compile) can take 3-10 min the first time in a fresh
  container, then roughly 0.1-0.5 s per frame at 1280x720 with 4 RTX subframes. A 10 s trace is
  ~300 frames incl. 2 s hold. Expect ~5-15 min, i.e. well under USD 1 per clip. Timeout is 1 h.

## Known risks

1. **Vulkan in Modal containers is the key unknown.** RTX needs the NVIDIA graphics/Vulkan
   driver libs (`libGLX_nvidia`, `nvidia_icd.json`, `libnvidia-rtcore`) injected into the
   container. `gpu_check` tells you whether `vulkaninfo` sees the GPU. If it does not, Isaac will
   not render; fall back to the 2D `viz/` replay (or Blender/matplotlib 3D).
2. Render code (`render_trace.py`) has **not been executed yet** (needs the EULA). API used:
   Isaac Sim 5.1 `SimulationApp`, `omni.replicator.core` render product + `rgb` annotator,
   plain `pxr` USD prims with `UsdPreviewSurface`. Likely first-run fixes: black first frames
   (raise warm-up updates), `rep.orchestrator.step` signature differences, PIL missing (falls
   back to `.npy`, then the ffmpeg step fails).
3. Image is pinned to `nvcr.io/nvidia/isaac-sim:5.1.0`. 6.x is newer but untested here.
4. Shader cache is not persisted between containers, so every cold start pays the compile cost.
5. Sim-to-render gap: boxes, flat road, no occlusion/weather. It is an illustration of the 2D
   trace, not evidence. Label it as such on screen.
