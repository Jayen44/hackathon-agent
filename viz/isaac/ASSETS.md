# viz/isaac assets: sources and licences

Every asset the Isaac render can pull, in the order `render_trace.py` tries it.
URLs are catalogued in `assets.py`; `python -m viz.isaac.assets --check` HEAD-checks
all of them (no downloads). All were HTTP 200 on 2026-10-15.
Nothing is vendored into this repo: assets are streamed at render time inside the
Modal container.

**Not legal advice. A human must read the licences below before the video is shown
publicly.** Open items are marked TODO.

## 1. NVIDIA content served for Isaac Sim 5.1 (primary)

Asset root: `https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/5.1`
(resolved at runtime with `isaacsim.storage.native.get_assets_root_path()`, falling
back to this constant).

| use | path under asset root |
|---|---|
| ego car | `/NVIDIA/dsready_content/nv_content/common_assets/vehicles/tri/auto_01/2023/main.usd` |
| other cars | `.../vehicles/honey/grand/2024/main.usd`, `.../vehicles/tri/security_01/2023/main.usd` (police livery deliberately not used, to avoid implying blame) |
| road | `/NVIDIA/Materials/2023_1/Base/Natural/Asphalt.mdl` (alt: `vMaterials_2/Ground/Asphalt_Fine.mdl`) |
| verge | `/NVIDIA/Materials/2023_1/Base/Natural/Grass_Countryside.mdl` |
| sky (dome light) | `/NVIDIA/Assets/Skies/Cloudy/kloofendal_48d_partly_cloudy_4k.hdr` (alts: `Clear/noon_grass_4k.hdr`, `Evening/evening_road_01_4k.hdr`) |

Not used yet but available: a UK road scene,
`/NVIDIA/dsready_content/nv_content/uk/scene_multilane_solid_and_dashed_markings/levels/main/main.usd`
(about 8 MB top layer plus a 23 MB terrain sublayer). Its road layout and coordinates are unknown, so
fitting our straight-road trace onto it needs a human pass in the Isaac GUI.

**Licence: NVIDIA Omniverse License Agreement.** This is the `LICENSE.txt` shipped in
`nvcr.io/nvidia/isaac-sim:5.1.0` (read by `gpu_check`). It points to the latest version at
https://docs.omniverse.nvidia.com/dev-guide/latest/common/NVIDIA_Omniverse_License_Agreement.html
Summary of the parts that matter here (paraphrased, read the original):
- 3D assets are "Content" under s.1.4. Under s.2.1 you may modify Content and distribute it as part
  of your own product or service, but **not on a stand-alone basis**. So we stream the assets; we do
  not re-host or commit them.
- s.2.1 also allows distributing user-generated output such as **video, stills and screen captures**.
  The rendered mp4 falls under this.
- **TODO (human), team size:** the individual-use clause and s.6.2 say an individual licence covers up to two people in an
  entity working together on Project Content. Three or more need Omniverse Enterprise subscription
  licences. Our team is 3-4 people. Decide who "uses" Isaac (e.g. only Vakhtang runs the renderer)
  or confirm the hackathon is covered.
- s.2.2: Third-Party Published Content falls under its own licence. The DS-ready vehicles come from
  NVIDIA's own content tree. **TODO (human):** confirm none of them is third-party published
  content. The folder names `tri/` and `honey/` may be vendor prefixes.
- Privacy: the data-collection clause says the software may collect usage and diagnostic data. `modal_app.py` passes
  `PRIVACY_CONSENT=N`.
- vMaterials (`vMaterials_2/...`) may have their own NVIDIA vMaterials terms. **TODO (human):**
  check before switching the road to `Asphalt_Fine`. The default `Base/Natural/Asphalt.mdl` is plain
  Omniverse Content.
- HDRIs in `/NVIDIA/Assets/Skies` share filenames with Poly Haven CC0 HDRIs (e.g.
  `kloofendal_48d_partly_cloudy`). Provenance is not stated on the server, so treat them as NVIDIA
  Content (above) unless confirmed.

## 2. Poly Haven, CC0 1.0 (fallback sky and asphalt)

Used when the Isaac asset root is unreachable or `--assets procedural` is set.
Licence: CC0 1.0 (public domain dedication), https://polyhaven.com/license. No attribution
required. We credit them anyway.

| use | URL |
|---|---|
| sky | https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/4k/kloofendal_48d_partly_cloudy_puresky_4k.hdr |
| asphalt diffuse | https://dl.polyhaven.org/file/ph-assets/Textures/jpg/2k/asphalt_02/asphalt_02_diff_2k.jpg |
| asphalt normal (GL) | https://dl.polyhaven.org/file/ph-assets/Textures/jpg/2k/asphalt_02/asphalt_02_nor_gl_2k.jpg |
| asphalt roughness | https://dl.polyhaven.org/file/ph-assets/Textures/jpg/2k/asphalt_02/asphalt_02_rough_2k.jpg |

## 3. Local CC0 cars (optional fallback, not fetched automatically)

If NVIDIA vehicles fail to load, the renderer tries any `*.usd*` file in
`accel-isaac` volume `/assets/cars/` (`/vol/assets/cars` in the container), one per actor.
To use it, a human downloads one of the packs below, converts the glTF to USD (Isaac's
`omni.kit.asset_converter`, or Blender export), and uploads the result with
`modal volume put accel-isaac car.usd /assets/cars/car.usd`.
- Kenney Car Kit, https://kenney.nl/assets/car-kit. CC0 (per kenney.nl).
- Quaternius cars, https://quaternius.com/packs/cars.html. CC0 (per quaternius.com).

Record which files were added here (file, pack, licence) when that happens.

## 4. Procedural (always available)

Primitive box cars (body, glasshouse, wheels), brake-light quads, the ego halo and lane lines are
generated in `render_trace.py`. They are our own work and carry no third-party licence.
