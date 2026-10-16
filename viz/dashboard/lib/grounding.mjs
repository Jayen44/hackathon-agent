// Number grounding for AI commentary: every number an agent writes must already be in the backend JSON.
// A sentence with any number we cannot find (allowing rounding, and 0..1 shown as a percentage) is dropped.

const NUM_RE = /(?<![A-Za-z_\d])[-−]?£?\d[\d,]*(?:\.\d+)?/g;
// Labels, not data: "90% CI".
const ALWAYS_ALLOWED = [90];

/** All numbers in a JSON value, including numbers written inside strings. */
export function collectNumbers(value, out = []) {
  if (typeof value === "number" && Number.isFinite(value)) out.push(value);
  else if (typeof value === "string") for (const n of extractNumbers(value)) out.push(n.value);
  else if (Array.isArray(value)) for (const v of value) collectNumbers(v, out);
  else if (value && typeof value === "object") for (const v of Object.values(value)) collectNumbers(v, out);
  return out;
}

/** Numbers in free text with their written precision (decimals). */
export function extractNumbers(text) {
  const res = [];
  for (const m of String(text).matchAll(NUM_RE)) {
    const raw = m[0].replace(/[−]/g, "-").replace(/[£,]/g, "");
    const v = Number(raw);
    if (!Number.isFinite(v)) continue;
    const dec = raw.includes(".") ? raw.split(".")[1].length : 0;
    res.push({ raw: m[0], value: v, decimals: dec });
  }
  return res;
}

export function allowedValues(source) {
  const base = collectNumbers(source).concat(ALWAYS_ALLOWED);
  const set = new Set();
  for (const x of base) {
    set.add(Math.abs(x));
    if (Math.abs(x) <= 1) set.add(Math.abs(x * 100));
  }
  return [...set];
}

export function isGrounded(n, allowed) {
  const tol = 0.5 * Math.pow(10, -n.decimals) + 1e-9;
  const t = Math.abs(n.value);
  return allowed.some((a) => Math.abs(a - t) <= tol);
}

export function splitSentences(text) {
  return String(text).split(/(?<=[.!?])\s+(?=[A-Z0-9"'(£−-])/).map((s) => s.trim()).filter(Boolean);
}

/** Keep only sentences whose numbers all appear in `source`. */
export function groundText(text, allowed) {
  const kept = [], dropped = [];
  for (const s of splitSentences(text)) {
    const bad = extractNumbers(s).filter((n) => !isGrounded(n, allowed));
    (bad.length ? dropped : kept).push(s);
  }
  return { text: kept.join(" "), dropped };
}

/** Ground every string field of an agent output object (recursively). */
export function groundObject(obj, allowed, dropped = []) {
  if (typeof obj === "string") {
    const g = groundText(obj, allowed);
    dropped.push(...g.dropped);
    return g.text;
  }
  if (Array.isArray(obj)) return obj.map((v) => groundObject(v, allowed, dropped));
  if (obj && typeof obj === "object") {
    const o = {};
    for (const [k, v] of Object.entries(obj)) o[k] = groundObject(v, allowed, dropped);
    return o;
  }
  return obj;
}
