// Copies the 3D replay viewer (viz/web, owned by sim) into public/viewer so the dashboard can iframe it.
// When ../web is not present (e.g. a deploy uploaded from viz/dashboard alone) the committed copy is kept.
import { cpSync, existsSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const src = join(here, "..", "..", "web");
const dst = join(here, "..", "public", "viewer");

if (existsSync(join(src, "index.html"))) {
  rmSync(dst, { recursive: true, force: true });
  cpSync(src, dst, { recursive: true });
  console.log(`copy-viewer: ${src} -> ${dst}`);
} else if (existsSync(join(dst, "index.html"))) {
  console.log("copy-viewer: viz/web not found, using committed public/viewer");
} else {
  console.error("copy-viewer: no viewer source and no committed copy");
  process.exit(1);
}
