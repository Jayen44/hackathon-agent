# Asset licences for viz/web

This lists every third-party file the replay page loads: name, author, source and licence.

## Currently used

| Asset | Author | Source | Licence | Use |
|---|---|---|---|---|
| three.js 0.160.0 (`build/three.module.js`) | mrdoob and three.js authors | https://cdn.jsdelivr.net/npm/three@0.160.0/ (npm mirror of https://github.com/mrdoob/three.js) | MIT | WebGL renderer, loaded from the CDN at runtime |
| `examples/jsm/objects/Sky.js` (Preetham analytic sky) | three.js authors | same CDN, three@0.160.0 | MIT | Sky dome and image-based lighting through PMREM |
| `examples/jsm/loaders/GLTFLoader.js`, `RGBELoader.js` | three.js authors | same CDN, three@0.160.0 | MIT | Loaded only when `manifest.json` lists GLB cars or an HDRI |
| Procedural cars, road, asphalt, grass, pavement, building facades, trees, street lights, glow sprites | Recovery Engine team, generated in `index.html` | this repo | same as this repo | All geometry and textures are generated in code. There are no downloaded models or images |

This folder has no downloaded model, texture or HDRI files yet.

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
