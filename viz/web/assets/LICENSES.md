# Asset licences for viz/web

This lists every third-party file the replay page loads: name, author, source and licence.

## Currently used

| Asset | Author | Source | Licence | Use |
|---|---|---|---|---|
| three.js 0.160.0 (`build/three.module.js`) | mrdoob and three.js authors | https://cdn.jsdelivr.net/npm/three@0.160.0/ (npm mirror of https://github.com/mrdoob/three.js) | MIT | WebGL renderer, loaded from the CDN at runtime |
| `examples/jsm/objects/Sky.js` (Preetham analytic sky) | three.js authors | same CDN, three@0.160.0 | MIT | Sky dome and image-based lighting through PMREM |
| `examples/jsm/loaders/GLTFLoader.js`, `RGBELoader.js` | three.js authors | same CDN, three@0.160.0 | MIT | Loaded only when `manifest.json` lists GLB cars or an HDRI |
| Procedural cars, road, asphalt, grass, pavement, building facades, trees, street lights, glow sprites | Recovery Engine team, generated in `index.html` | this repo | same as this repo | Fallback when a downloaded asset is missing or fails to load. Grass, pavement, buildings, trees, lights are always procedural |

### Downloaded files (all CC0 1.0, https://creativecommons.org/publicdomain/zero/1.0/)

Downloaded 15 Oct 2026. Poly Haven files were checked against the MD5 published by https://api.polyhaven.com/files/<id>.

| File | Name | Author | Source URL | Licence | Use |
|---|---|---|---|---|---|
| `kenney/taxi.glb` | Car Kit 3.1, "taxi" | Kenney (www.kenney.nl) | https://kenney.nl/assets/car-kit (zip: https://kenney.nl/media/pages/assets/car-kit/1a312ec241-1775131960/kenney_car-kit.zip) | CC0 | Ego vehicle (robotaxi) |
| `kenney/sedan.glb` | Car Kit 3.1, "sedan" | Kenney | same zip | CC0 | Other road user |
| `kenney/suv.glb` | Car Kit 3.1, "suv" | Kenney | same zip | CC0 | Other road user |
| `kenney/van.glb` | Car Kit 3.1, "van" | Kenney | same zip | CC0 | Other road user |
| `kenney/Textures/colormap.png` | Car Kit 3.1 colour atlas | Kenney | same zip | CC0 | Texture referenced by the four GLBs |
| `kenney/License.txt` | Car Kit licence file | Kenney | same zip | CC0 | Licence text shipped with the kit |
| `hdri/kloofendal_48d_partly_cloudy_puresky_2k.hdr` | Kloofendal 48d Partly Cloudy (Pure Sky), 2K | Greg Zaal (original), Jarod Guest (sky edits) | https://polyhaven.com/a/kloofendal_48d_partly_cloudy_puresky (file: https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/2k/kloofendal_48d_partly_cloudy_puresky_2k.hdr) | CC0 | Sky background and image-based lighting in light (day) theme; dusk theme keeps the procedural sky |
| `asphalt/asphalt_02_diff_1k.jpg` | Asphalt 02, diffuse, 1K | Rob Tuytel | https://polyhaven.com/a/asphalt_02 (file: https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/asphalt_02/asphalt_02_diff_1k.jpg) | CC0 | Road colour (3 m tile) |
| `asphalt/asphalt_02_nor_gl_1k.jpg` | Asphalt 02, normal (OpenGL), 1K | Rob Tuytel | https://polyhaven.com/a/asphalt_02 (file: https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/asphalt_02/asphalt_02_nor_gl_1k.jpg) | CC0 | Road normal map |
| `asphalt/asphalt_02_rough_1k.jpg` | Asphalt 02, roughness, 1K | Rob Tuytel | https://polyhaven.com/a/asphalt_02 (file: https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/asphalt_02/asphalt_02_rough_1k.jpg) | CC0 | Road roughness map |

## Adding downloaded assets (get the team's OK before downloading)

Use only the official sites: kenney.nl, quaternius.com, polyhaven.com and github.com/mrdoob/three.js. Check each asset's own licence page. CC0 is preferred. CC-BY is acceptable only with visible attribution on screen.

1. Put the file in this folder, for example `car_ego.glb` or `sky_1k.hdr`. Never execute downloaded files.
2. Reference it in `manifest.json`, for example
   `"cars": {"ego": {"file": "car_ego.glb", "yaw_deg": 90}, "others": [{"file": "sedan.glb"}]}`, `"hdri": {"file": "sky_1k.hdr"}`.
3. Add a row to the table above.

These candidates are stated CC0 by their sites. Re-check each licence when you download:
- Kenney "Car Kit": https://kenney.nl/assets/car-kit
- Quaternius car packs: https://quaternius.com
- Poly Haven HDRIs, 1k `.hdr`: https://polyhaven.com/hdris

Deliberately not used: `examples/models/gltf/ferrari.glb` from the three.js repo. Its credited source, Sketchfab model 57bf6cc56931426e87494f554df1dab6, is now disabled, so its licence could not be confirmed.
