"use client";

// Guided demo tour for the stage. Start: header "Demo" button or any URL with ?demo=1. State lives in
// sessionStorage while touring. The page stays fully interactive: the highlight ignores pointer events.
// Step texts read their numbers from the claims API; nothing is hard-coded.
import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { getClaim, type Claim } from "@/lib/api";
import { DEMO_CCTV, DEMO_FILL, DEMO_PROGRESS, type DemoProgress } from "@/lib/demo";
import { gbp, pct } from "@/lib/format";

const KEY = "accel-tour-step", CLAIM_KEY = "accel-tour-claim", VIDEO_KEY = "accel-tour-video", ASSESSED_KEY = "accel-tour-assessed";
const PREFERRED = "22_pursue_lead_braking", FALLBACK = "DEMO-1_queue_late_brake";
export const DEMO_VIDEO_ID = "d741ae8d0d8c4bc482ae242222eaa610"; // Blender CCTV render (was ce5730a6…, the cartoon clip)

type Step = { path: (cid: string) => string; target: string; text: (c: Claim | null) => string };

const claimPath = (cid: string) => `/claims/${encodeURIComponent(cid)}`;
const STEPS: Step[] = [
  { path: () => "/", target: "inbox-table", text: () => "Robotaxi claims the insurer has paid. Which can it recover from the AV company?" },
  {
    path: claimPath, target: "claim-decision",
    text: (c) => !c ? "Each claim ends in a decision and a GBP range. Triage, not a ruling."
      : c.expected_recovery_gbp
        ? `${c.decision_label}: expected recovery ${gbp(c.expected_recovery_gbp.low)} to ${gbp(c.expected_recovery_gbp.high)}, net of legal cost. Triage, not a ruling.`
        : `${c.decision_label}. Not priced: ${c.gbp.reason ?? "see the engine notes"}. Triage, not a ruling.`,
  },
  { path: claimPath, target: "replay", text: () => "3D reconstruction: the AV as reported vs careful drivers A and B (UN R157 Annex 3). Click it, press C to change camera." },
  {
    path: claimPath, target: "pavoid",
    text: (c) => {
      const d = c?.sim?.drivers, rep = c?.sim?.reproduction;
      if (!d?.careful_a || !d?.careful_b) return "Would a careful human have avoided it? P(avoid) with 90% CI, plus reproduction and timeline checks.";
      const a = d.careful_a, b = d.careful_b;
      return `Careful driver A avoids it in ${pct(a.p_avoid)} (CI ${pct(a.ci90[0])}–${pct(a.ci90[1])}), B in ${pct(b.p_avoid)}. ` +
        (rep ? `Sim reproduces the reported crash in ${pct(rep.rate)} of runs.` : "");
    },
  },
  {
    path: claimPath, target: "info-requests",
    text: (c) => `What to obtain next, ranked by how much it narrows the answer.${c && c.evidence_tier >= 2 ? " Already tier 2 (AV logs)." : " AV logs = tier 2."}${c?.information_requests?.[0] ? ` First: ${c.information_requests[0].title}.` : ""}`,
  },
  { path: claimPath, target: "debate", text: () => "Adjuster vs defence counsel: the system argues against itself. Every GBP figure is re-priced by the finance engine, never by a model." },
  {
    path: claimPath, target: "pricing",
    text: (c) => "Vision: insurers bring their own pricing models and rules; the system runs them alongside its own assessment and shows where they differ."
      + (c?.pricing ? ` Priced by: ${c.pricing.profile.name}.` : ""),
  },
  { path: () => `/new?cctv=${demoVideo()}`, target: "cctv", text: () => "New claim with CCTV: calibrate four road points, pick the AV, Measure. Speeds and gap fill the form with ±σ." },
  { path: () => `/claims/${encodeURIComponent(load(ASSESSED_KEY) || "CHECK-blender")}`, target: "claim-decision",
    text: () => "The decision from the video: pursue or not, the recoverable GBP range, and why. Triage for a human, not a ruling." },
  { path: () => "/run", target: "lanes", text: () => "The long-running Managed Agents team, live: one lane per agent, hand-offs between them, recoverable GBP by crash type." },
];

function store(k: string, v: string | null) {
  try { if (v == null) sessionStorage.removeItem(k); else sessionStorage.setItem(k, v); } catch { /* private mode */ }
}
function load(k: string) { try { return sessionStorage.getItem(k); } catch { return null; } }
// ?demo=1&video=<id> picks the DEMO_CCTV entry; default is the stage clip.
function demoVideo() { const v = load(VIDEO_KEY); return v && DEMO_CCTV[v] ? v : DEMO_VIDEO_ID; }
const CCTV_STEP = STEPS.findIndex((x) => x.target === "cctv");

/** Called by the new-claim form after "Assess claim": if the tour is on the CCTV step, move it to the decision step
 * for the claim just submitted (otherwise the tour would send the browser back to the form). */
export function tourActiveOnCctv() { return load(KEY) === String(CCTV_STEP); }

export function tourAfterAssess(claimId: string) {
  store(ASSESSED_KEY, claimId);
  if (load(KEY) === String(CCTV_STEP)) { store(KEY, String(CCTV_STEP + 1)); window.dispatchEvent(new Event("accel-tour")); }
}

export function startTour() {
  store(KEY, "0");
  window.dispatchEvent(new Event("accel-tour"));
}

export function DemoButton() {
  return <button type="button" onClick={startTour} className="rounded border border-line px-2 py-0.5 text-xs text-muted hover:text-fg">Demo</button>;
}

async function pickClaim(): Promise<string> {
  try {
    const r = await getClaim(PREFERRED);
    if (r.status === "done" && r.claim.decision === "pursue") return PREFERRED;
  } catch { /* fall through */ }
  return FALLBACK;
}

export function Tour() {
  const router = useRouter();
  const pathname = usePathname();
  const [step, setStep] = useState<number | null>(null);
  const [cid, setCid] = useState<string | null>(null);
  const [claim, setClaim] = useState<Claim | null>(null);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [demo, setDemo] = useState<DemoProgress | null>(null);

  // Activation: ?demo=1, the Demo button, or a tour already in progress (sessionStorage).
  useEffect(() => {
    const sync = () => { const s = load(KEY); setStep(s == null ? null : Math.max(0, Math.min(STEPS.length - 1, Number(s) || 0))); };
    const q = new URLSearchParams(window.location.search);
    if (q.get("demo") === "1") {
      const v = q.get("video");
      if (v && DEMO_CCTV[v]) store(VIDEO_KEY, v);
      // On /new with ?demo=1 go straight to the CCTV step; elsewhere start at the beginning.
      if (window.location.pathname.startsWith("/new")) store(KEY, String(CCTV_STEP));
      else if (load(KEY) == null) store(KEY, "0");
    }
    sync();
    window.addEventListener("accel-tour", sync);
    return () => window.removeEventListener("accel-tour", sync);
  }, []);

  useEffect(() => {
    if (step == null || cid) return;
    const saved = load(CLAIM_KEY);
    if (saved) { setCid(saved); return; }
    pickClaim().then((c) => { store(CLAIM_KEY, c); setCid(c); });
  }, [step, cid]);

  useEffect(() => {
    if (!cid || step == null || STEPS[step].path !== claimPath) return;
    let alive = true;
    const poll = () => getClaim(cid).then((r) => { if (!alive) return; if (r.status === "done") setClaim(r.claim); else setTimeout(poll, 3000); }).catch(() => {});
    poll();
    return () => { alive = false; };
  }, [cid, step]);

  const go = useCallback((n: number | null) => {
    if (n == null || n < 0 || n >= STEPS.length) { store(KEY, null); store(CLAIM_KEY, null); setStep(null); setCid(null); setRect(null); return; }
    store(KEY, String(n)); setStep(n); setRect(null);
  }, []);

  // Demo autofill progress from the /new page.
  useEffect(() => {
    const on = (e: Event) => setDemo((e as CustomEvent<DemoProgress>).detail);
    window.addEventListener(DEMO_PROGRESS, on);
    return () => window.removeEventListener(DEMO_PROGRESS, on);
  }, []);
  useEffect(() => { setDemo(null); }, [step]);
  const onCctv = step === CCTV_STEP && pathname.startsWith("/new");
  const fill = useCallback(() => {
    setDemo({ text: "Starting…", target: "cctv", state: "running" });
    window.dispatchEvent(new CustomEvent(DEMO_FILL, { detail: { videoId: demoVideo() } }));
  }, []);
  const next = useCallback(() => {
    if (step == null) return;
    // Next on the CCTV step runs the autofill first (once); after it is done, Next moves on.
    if (onCctv && demo?.state !== "done") { if (demo?.state !== "running") fill(); return; }
    go(step + 1 < STEPS.length ? step + 1 : null);
  }, [step, onCctv, demo, fill, go]);
  const target = onCctv && demo?.target ? demo.target : step != null ? STEPS[step].target : "";

  // Navigate to the step's page.
  useEffect(() => {
    if (step == null || !cid) return;
    const want = STEPS[step].path(cid);
    const wantPath = want.split("?")[0];
    if (decodeURIComponent(pathname) !== decodeURIComponent(wantPath)) router.push(want);
  }, [step, cid, pathname, router]);

  // Track the target element (it may appear late: claims load asynchronously).
  useEffect(() => {
    if (step == null) return;
    let scrolled = false, alive = true;
    const tick = () => {
      if (!alive) return;
      const el = document.querySelector(`[data-tour="${target}"]`);
      if (el) {
        if (!scrolled) { el.scrollIntoView({ block: "center", behavior: "smooth" }); scrolled = true; }
        setRect(el.getBoundingClientRect());
      } else setRect(null);
    };
    tick();
    const t = setInterval(tick, 250);
    return () => { alive = false; clearInterval(t); };
  }, [step, pathname, target]);

  useEffect(() => {
    if (step == null) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (e.key === "ArrowRight") next();
      else if (e.key === "ArrowLeft") go(Math.max(0, step - 1));
      else if (e.key === "Escape") go(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [step, go, next]);

  if (step == null) return null;
  const s = STEPS[step];
  const pad = 6;
  return (
    <>
      {rect && (
        <div aria-hidden className="pointer-events-none fixed z-40 rounded-lg transition-all duration-200"
          style={{ left: rect.left - pad, top: rect.top - pad, width: rect.width + 2 * pad, height: rect.height + 2 * pad,
            boxShadow: "0 0 0 2px var(--accent), 0 0 0 9999px rgba(0,0,0,0.45)" }} />
      )}
      <div role="dialog" aria-label="Demo tour" className="fixed bottom-4 right-4 z-50 w-[320px] rounded-lg border border-line bg-panel p-4 text-sm shadow-lg">
        <div className="flex items-center justify-between text-xs text-muted">
          <span>Step {step + 1}/{STEPS.length}</span>
          <button type="button" onClick={() => go(null)} className="hover:text-fg">Exit</button>
        </div>
        <p className="mt-2">{s.text(s.path === claimPath ? claim : null)}</p>
        {onCctv && (
          <div className="mt-2 space-y-2">
            {demo && <p className={`text-xs ${demo.state === "error" ? "text-bad" : demo.state === "done" ? "font-medium" : "text-muted"}`}>{demo.text}</p>}
            {demo?.state !== "done" && (
              <button type="button" disabled={demo?.state === "running"} onClick={fill} className="rounded border border-accent px-3 py-1 text-accent disabled:opacity-50">
                {demo?.state === "running" ? "Filling…" : "Fill demo data"}
              </button>
            )}
          </div>
        )}
        <div className="mt-3 flex justify-between">
          <button type="button" disabled={step === 0} onClick={() => go(step - 1)} className="rounded border border-line px-3 py-1 disabled:opacity-40">Back</button>
          <button type="button" onClick={next} disabled={onCctv && demo?.state === "running"} className="rounded bg-accent px-3 py-1 font-medium text-on-accent disabled:opacity-50">
            {step + 1 < STEPS.length ? "Next" : "Finish"}
          </button>
        </div>
        <p className="mt-2 text-[11px] text-muted">← → to move, Esc to exit</p>
      </div>
    </>
  );
}
