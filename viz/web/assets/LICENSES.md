# Asset licences for viz/web

This lists every third-party file the replay page loads: name, author, source and licence.

## Currently used

| Asset | Author | Source | Licence | Use |
|---|---|---|---|---|
| three.js 0.160.0 (`build/three.module.js`) | mrdoob and three.js authors | https://cdn.jsdelivr.net/npm/three@0.160.0/ (npm mirror of https://github.com/mrdoob/three.js) | MIT | WebGL renderer, loaded from the CDN at runtime |
| `examples/jsm/environments/RoomEnvironment.js` | three.js authors | same CDN, three@0.160.0 | MIT | Neutral studio image-based lighting for the clay vehicle materials |
| Inter typeface | Rasmus Andersson | https://fonts.google.com/specimen/Inter (Google Fonts CSS) | SIL Open Font License 1.1 | UI and label typography; falls back to the system sans if offline |
| Procedural sedan, road markings, kerbs, footway, metric ground grid, trajectory trails, markers, text decals | Recovery Engine team, generated in `index.html` | this repo | same as this repo | Vehicles and scene. Always procedural |

### Downloaded files (all CC0 1.0, https://creativecommons.org/publicdomain/zero/1.0/)

Downloaded 15 Oct 2026. Poly Haven files were checked against the MD5 published by https://api.polyhaven.com/files/<id>.

| File | Name | Author | Source URL | Licence | Use |
|---|---|---|---|---|---|
| `asphalt/asphalt_02_diff_1k.jpg` | Asphalt 02, diffuse, 1K | Rob Tuytel | https://polyhaven.com/a/asphalt_02 (file: https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/asphalt_02/asphalt_02_diff_1k.jpg) | CC0 | Road colour (3 m tile) |
| `asphalt/asphalt_02_nor_gl_1k.jpg` | Asphalt 02, normal (OpenGL), 1K | Rob Tuytel | https://polyhaven.com/a/asphalt_02 (file: https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/asphalt_02/asphalt_02_nor_gl_1k.jpg) | CC0 | Road normal map |
| `asphalt/asphalt_02_rough_1k.jpg` | Asphalt 02, roughness, 1K | Rob Tuytel | https://polyhaven.com/a/asphalt_02 (file: https://dl.polyhaven.org/file/ph-assets/Textures/jpg/1k/asphalt_02/asphalt_02_rough_1k.jpg) | CC0 | Road roughness map |

Removed 15 Oct 2026 (restyle to a forensic reconstruction look): Kenney Car Kit GLBs and texture, and the Poly Haven Kloofendal HDRI. They are no longer in the repo or loaded by the page.

## Adding downloaded assets (get the team's OK before downloading)

Use only the official sites: polyhaven.com and github.com/mrdoob/three.js. Check each asset's own licence page. CC0 is preferred. CC-BY is acceptable only with visible attribution on screen.

1. Put the file in this folder. Never execute downloaded files.
2. Reference it in `manifest.json` (currently only `asphalt` is read).
3. Add a row to the table above.

Deliberately not used: `examples/models/gltf/ferrari.glb` from the three.js repo. Its credited source, Sketchfab model 57bf6cc56931426e87494f554df1dab6, is now disabled, so its licence could not be confirmed.
