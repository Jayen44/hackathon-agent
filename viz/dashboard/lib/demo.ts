// Demo-mode CCTV autofill, one entry per demo clip (add another clip, e.g. an Isaac Sim render, with one entry).
// Calibration clicks are in source-frame pixels (same space as manual clicks). Speeds, gap and crash type are never
// listed here: they come from Measure. The claim block holds demo claim-file values, labelled as such in the UI.

export type DemoClaim = {
  av_engaged: "yes" | "no" | "unknown"; within_odd: "yes" | "no" | "unknown";
  injury_severity: string; claim_paid_gbp: string;
  injured_party_share_low_pct: string; injured_party_share_high_pct: string;
  software_verified: "yes" | "no" | "unknown";
};
export type DemoEntry = {
  clicks: [number, number][]; L: number; W: number; contact: "auto" | "yes" | "no";
  avTracks: number[]; otherTracks: number[]; claim: DemoClaim;
  // Optional: stored real measurement of this clip (public/demo/...) used instead of the live ~45 s analysis.
  cached?: { url: string; waitMs: number };
  // Optional: claim already assessed from this same clip; the tour shows it after Assess instead of waiting 30-90 s.
  assessedClaim?: string;
};

export const DEMO_CCTV: Record<string, DemoEntry> = {
  // Blender render (viz/render) of the cut-in -> rear-end trace from a fixed CCTV pole; ground truth in
  // viz/isaac/samples/cctv_cut_in_truth.json. Track 3 = AV (white), track 1 = cutter (blue).
  d741ae8d0d8c4bc482ae242222eaa610: {
    clicks: [[1047.2, 589.09], [740.86, 259.97], [848.81, 251.63], [1245.4, 555.34]],
    L: 24, W: 3.5, contact: "yes", avTracks: [3], otherTracks: [1],
    cached: { url: "/demo/d741ae8d0d8c4bc482ae242222eaa610_805a3509f51f.json", waitMs: 10000 },
    assessedClaim: "CHECK-blender",
    claim: {
      av_engaged: "yes", within_odd: "yes", injury_severity: "Serious", claim_paid_gbp: "60000",
      injured_party_share_low_pct: "0", injured_party_share_high_pct: "10", software_verified: "unknown",
    },
  },
  ce5730a6facc4e34885a1a4f5c405fbc: {
    clicks: [[623.8, 570.4], [632.4, 288.5], [526.6, 288.5], [397.4, 570.4]],
    L: 27, W: 3.5, contact: "yes", avTracks: [4], otherTracks: [],
    claim: {
      av_engaged: "yes", within_odd: "yes", injury_severity: "Serious", claim_paid_gbp: "60000",
      injured_party_share_low_pct: "0", injured_party_share_high_pct: "10", software_verified: "unknown",
    },
  },
};

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));

/** Scroll to and briefly outline the element marked data-demo="key", so the audience sees what is being filled. */
export function flash(key: string, ms = 900) {
  const el = document.querySelector<HTMLElement>(`[data-demo="${key}"]`);
  if (!el) return;
  el.scrollIntoView({ block: "center", behavior: "smooth" });
  const prev = el.style.outline, prevOff = el.style.outlineOffset;
  el.style.outline = "3px solid var(--accent)"; el.style.outlineOffset = "2px";
  setTimeout(() => { el.style.outline = prev; el.style.outlineOffset = prevOff; }, ms);
}

export type DemoProgress = { text: string; target?: string; state: "running" | "done" | "error" };
export const DEMO_FILL = "accel-demo-fill", DEMO_PROGRESS = "accel-demo-progress";
export function sayDemo(p: DemoProgress) { window.dispatchEvent(new CustomEvent<DemoProgress>(DEMO_PROGRESS, { detail: p })); }
