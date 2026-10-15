# viz/isaac: backup 3D render of a sim/ trace (Isaac Sim on Modal)

This is a backup demo visual only. **All numbers come from `sim/`** (the 2D kinematic bicycle
model). Isaac Sim only draws the trace:
- real NVIDIA car models on an asphalt road under an HDRI sky
- RTX real-time ray tracing, or path tracing
- a damped chase camera
- brake lights that light up when the trace decelerates
- a blue halo under the ego car, which turns red under both cars on impact

No physics runs in Isaac. Each video carries a burned-in caption saying it is an illustration of a
sim trace, not video evidence. The primary visual is still the 2D side-by-side replay in `viz/`.

## Files

| file | runs where | what |
|---|---|---|
| `export_trace.py` | local (repo venv) | `export(SimResult, SimScenario, name)` returns the renderer JSON. `python -m viz.isaac.export_trace` regenerates `samples/` |
| `assets.py` | local + inside Isaac | asset catalogue and fallbacks, model auto-fit (scale, up-axis, yaw, ground), brake-light flags, damped chase cam. Pure Python, tested in `tests/test_viz_isaac_assets.py`. `python -m viz.isaac.assets --check` HEAD-checks every URL |
| `render_trace.py` | inside Isaac's `/isaac-sim/python.sh` | builds the USD stage, renders one frame per 1/25 s of the 50 Hz trace, writes `frame_%05d.png` (replicator `rgb` annotator) |
| `modal_app.py` | Modal, `gpu="L40S"` | `gpu_check` (does not start Isaac), `render(trace, name, accept_eula, ...)`, local entrypoint `main` |
| `ASSETS.md` | | every asset's source and licence, plus open licence TODOs |
| `samples/*.json` | | ILLUSTRATIVE ONLY: a hand-built cut-in (25 m gap, ego 20 m/s, cutter 12 m/s). Ego as AV replay with late, soft braking: collides, rear_end at 3.4 s. Ego as the **test-fixture** careful driver from `tests/test_sim.py`: avoids. Not R157 parameters, not a real crash |

## Run

```bash
# 0. regenerate samples (or export your own SimResult)
.venv/bin/python -m viz.isaac.export_trace

# 1. GPU + Vulkan check. The first build pulls a ~15-20 GB image (took ~3 min on Modal). Does NOT start Isaac Sim.
modal run viz/isaac/modal_app.py::gpu_check

# 2. First real render. Starting Isaac Sim means accepting the NVIDIA Omniverse License Agreement
#    (the EULA shipped in the Isaac Sim 5.1 image). Read it first, and see ASSETS.md for the team-size TODO:
#    https://docs.omniverse.nvidia.com/dev-guide/latest/common/NVIDIA_Omniverse_License_Agreement.html
modal run viz/isaac/modal_app.py --trace viz/isaac/samples/cut_in_av_replay.json --accept-eula
#    -> viz/isaac/samples/cut_in_av_replay.mp4 (+ copy and poster.png in volume accel-isaac:/renders/<name>/)
#    options: --camera overhead | --renderer PathTracing | --assets procedural | --sky noon_grass|evening_road

# 3. Side by side (AV vs careful), padding the shorter clip with its last frame
ffmpeg -i viz/isaac/samples/cut_in_av_replay.mp4 -i viz/isaac/samples/cut_in_careful_test.mp4 \
  -filter_complex "[0:v]tpad=stop_mode=clone:stop_duration=10[a];[1:v]tpad=stop_mode=clone:stop_duration=10[b];[a][b]hstack=shortest=1" \
  -c:v libx264 -pix_fmt yuv420p viz/isaac/samples/side_by_side.mp4
```

Without `--accept-eula`, `render` raises before anything Isaac-related starts.
`ACCEPT_EULA` and `OMNI_KIT_ACCEPT_EULA` are set only in the environment of the Isaac
subprocess. They are never baked into the image.

To render your own trace:
```python
from viz.isaac.export_trace import export, write
write(export(result, scenario, "sgo_123_av", policy="av_replay"), "viz/isaac/out/sgo_123_av.json")
```

## Asset fallback chain (per item, automatic)

1. NVIDIA content served for Isaac Sim 5.1:
   - DS-ready cars `tri/auto_01` (ego), `honey/grand` and `tri/security_01`
   - MDL `Asphalt` and `Grass_Countryside`
   - HDRI `kloofendal_48d_partly_cloudy`
2. Poly Haven CC0: sky HDRI, plus `asphalt_02` textures as a UsdPreviewSurface material.
3. CC0 cars you drop into the volume at `/assets/cars/` (Kenney or Quaternius, converted to USD).
4. Procedural cars: body, glasshouse and wheels built from primitives.

Each car model is auto-fitted:
- Y-up models are rotated to Z-up
- the long axis is aligned to +x
- the model is scaled uniformly to the sim length (4.5 m) and set on the ground

Nose direction cannot be read from a bounding box. If a car drives backwards on the first render,
set `yaw_offset_deg=180` for that model in `assets.VEHICLES`.

## Cost (Modal L40S, about USD 1.95/h at time of writing, check modal.com/pricing)

- `gpu_check`: under a minute of GPU, cents. The image build is cached after the first run.
- Render: Isaac cold start (extension load and shader compile) is 3-10 min in a fresh container.
  Streaming the car and material assets adds 1-3 min. After that, expect roughly:
  - 0.2-1 s per frame at 1920x1080 with 8 RTX subframes
  - several times that with `--renderer PathTracing` (32 spp)

  A 3.4 s collision clip with 0.5 s lead-in and 2 s hold is about 150 frames. Expect 10-20 min,
  about USD 0.5 per clip. Timeout is 1 h.

## Known risks

1. **Vulkan works in Modal** (confirmed by `gpu_check` on L40S, driver 610.57.04). `vulkaninfo`
   lists the NVIDIA L40S. The NVIDIA ICD, `libGLX_nvidia`, `libnvidia-rtcore` and
   `libnvidia-glcore` are all present. The container is Ubuntu 24.04 running as root.
2. `render_trace.py` has **not been executed yet**, because running it needs the EULA. The APIs
   used are:
   - Isaac Sim 5.1 `SimulationApp`
   - `isaacsim.storage.native.get_assets_root_path`
   - `CreateMdlMaterialPrim`
   - `omni.replicator.core` render product and `rgb` annotator
   - plain `pxr` USD

   Likely first-run fixes:
   - black or low-detail first frames: raise the warm-up count
   - `rep.orchestrator.step` signature differences
   - cars facing backwards: set `yaw_offset_deg`
   - MDL textures streaming late
   - PIL missing: frames fall back to `.npy` and the ffmpeg step then fails
3. The image is pinned to `nvcr.io/nvidia/isaac-sim:5.1.0`. Isaac 6.x is newer but untested here.
4. The shader cache is not persisted between containers, so every cold start pays the compile cost.
5. The render shows a flat straight road with no occlusion or weather. It illustrates the 2D trace
   and is not evidence. The caption says so on screen.
6. Licences: see the TODOs in `ASSETS.md` (team-size clause, provenance of third-party content).
