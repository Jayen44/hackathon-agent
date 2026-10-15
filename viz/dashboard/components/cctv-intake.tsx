"use client";

// Inline CCTV measurement inside the intake form: upload -> GPU detection (Sim Lab) -> calibrate on the blurred first
// frame -> pick the AV (and optionally the other vehicle) -> Measure fills the form's kinematics with measured values.
// Reads go through the same-origin proxy /api/simlab/*; the upload goes straight to the Sim Lab.
import { useEffect, useRef, useState } from "react";
import { SIMLAB_BASE } from "@/lib/api";
import { flash, sleep, type DemoEntry } from "@/lib/demo";

const MPH = 0.44704;
const P = "/api/simlab/video";

type Track = { id: number; cls: string; n: number; t0: number; t1: number; path: [number, number][]; thumb: boolean };
type Tracks = { width: number; height: number; tracks: Track[] };
type MS = { value: number; sd: number };
type Range = { lo: number; hi: number; source: string };
type Analysis = {
  run_id: string;
  bundle: { conflict: { crash_type: string; t_start: number }; conflict_ranges: Record<string, Range>; outcome: { collided: boolean; impact_speed_mps?: number }; t_crash?: number | null };
  measured: { ego_speed_mps: MS; other_speed_mps: MS; gap_m: MS; ego_speed_before_impact_mps?: MS; min_gap_m?: number; [k: string]: unknown };
  calibration: Record<string, unknown>;
  ego_ids: number[]; other_ids: number[];
};

export type CctvFill = {
  fields: Record<string, string>;
  hints: Record<string, string>;
  cctv: { video_id: string; run_id: string; display: Record<string, unknown> };
};

const input = "w-full rounded-md border border-line bg-panel px-2.5 py-1.5 text-sm num placeholder:text-muted/70";
const btn = "rounded-md border border-line px-3 py-1.5 text-sm hover:border-accent disabled:opacity-40";
const f1 = (x: number) => x.toFixed(1);
const mid = (r?: Range) => (r ? (r.lo + r.hi) / 2 : null);

async function jget<T>(url: string): Promise<T> {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

/** Demo autofill handle: drives the same state a presenter's clicks would. */
export type CctvDemo = { run: (videoId: string, e: DemoEntry, say: (t: string) => void) => Promise<boolean> };

export function CctvIntake({ onMeasured, initialVideoId, demoRef }: { onMeasured: (x: CctvFill) => void; initialVideoId?: string; demoRef?: React.MutableRefObject<CctvDemo | null> }) {
  const [vid, setVid] = useState<string | null>(initialVideoId ?? null);
  const [debugId, setDebugId] = useState(initialVideoId ?? "");
  const [status, setStatus] = useState("");
  const [info, setInfo] = useState<Tracks | null>(null);
  const [clicks, setClicks] = useState<[number, number][]>([]);
  const [L, setL] = useState(""); const [W, setW] = useState("");
  const [ego, setEgo] = useState<number[]>([]); const [other, setOther] = useState<number[]>([]);
  const [contact, setContact] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const [debugOpen, setDebugOpen] = useState(false);
  const live = useRef({ vid, info, status, measure: async () => false as boolean });

  useEffect(() => {
    if (!vid) return;
    let alive = true;
    setInfo(null); setClicks([]); setEgo([]); setOther([]); setDone(null);
    const t0 = Date.now();
    (async () => {
      for (;;) {
        let s: { state: string; error?: string; n_tracks?: number };
        try { s = await jget(`${P}/${vid}/status`); } catch (e) { if (alive) setStatus(`Unknown video: ${(e as Error).message}`); return; }
        if (!alive) return;
        if (s.state === "running") { setStatus(`Detecting vehicles on GPU… ${Math.round((Date.now() - t0) / 1000)} s`); await new Promise((r) => setTimeout(r, 2500)); continue; }
        if (s.state === "error") { setStatus(`Detection failed: ${s.error}`); return; }
        break;
      }
      const t = await jget<Tracks>(`${P}/${vid}/tracks`);
      if (!alive) return;
      setInfo(t);
      setStatus(`${t.tracks.length} vehicle tracks. Click 4 road points: A, B along one lane line (L apart), then C, D on the other line (W apart).`);
    })();
    return () => { alive = false; };
  }, [vid]);

  const upload = async (file: File) => {
    if (file.size > 200 * 1024 * 1024) { setStatus("File is larger than 200 MB."); return; }
    const fd = new FormData(); fd.append("file", file); fd.append("blur_plates", "1");
    setStatus(`Uploading ${(file.size / 1e6).toFixed(1)} MB…`);
    try {
      const r = await fetch(`${SIMLAB_BASE}/api/video/upload`, { method: "POST", body: fd });
      if (!r.ok) throw new Error(await r.text());
      setVid((await r.json()).id);
    } catch (e) { setStatus(`Upload failed: ${(e as Error).message}`); }
  };

  const onFrameClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!info) return;
    const r = e.currentTarget.getBoundingClientRect();
    const p: [number, number] = [((e.clientX - r.left) / r.width) * info.width, ((e.clientY - r.top) / r.height) * info.height];
    setClicks((cur) => (cur.length >= 4 ? cur : [...cur, p]));
  };
  const toggle = (id: number, role: "av" | "oth") => {
    const tog = (a: number[]) => (a.includes(id) ? a.filter((x) => x !== id) : [...a, id]);
    if (role === "av") { setEgo(tog(ego)); setOther(other.filter((x) => x !== id)); }
    else { setOther(tog(other)); setEgo(ego.filter((x) => x !== id)); }
  };

  const ready = !!info && clicks.length === 4 && +L > 0 && +W > 0 && ego.length > 0;

  const measure = async (): Promise<boolean> => {
    if (!vid || !info) return false;
    setBusy(true); setDone(null); setStatus("Measuring trajectories and running the counterfactual on Modal…");
    const calibration = { mode: "rectangle", img_pts: clicks, length_m: +L, width_m: +W, click_sigma_px: 2, world_sigma_m: 0.05 };
    try {
      const r = await fetch(`${P}/${vid}/analyze`, {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ calibration, ego_track: ego, other_track: other.length ? other : null, lane_width_m: +W, crash_type: null,
          collided: contact === "auto" ? null : contact === "yes", n: 2000, seed: 0 }),
      });
      if (!r.ok) { let m = await r.text(); try { m = JSON.parse(m).detail; } catch { /* keep */ } throw new Error(m); }
      const a = (await r.json()) as Analysis;
      setOther(a.other_ids);
      const m = a.measured, b = a.bundle, c = b.conflict, cr = b.conflict_ranges;
      const fields: Record<string, string> = {}, hints: Record<string, string> = {};
      const spd = (k: string, x: MS) => { fields[k] = f1(x.value / MPH); hints[k] = `measured from CCTV: ${f1(x.value / MPH)} ± ${f1(x.sd / MPH)} mph (1σ)`; };
      spd("ego_speed_mph", m.ego_speed_mps);
      spd("other_speed_mph", m.other_speed_mps);
      fields.gap_m = f1(m.gap_m.value); hints.gap_m = `measured from CCTV: ${f1(m.gap_m.value)} ± ${f1(m.gap_m.sd)} m (1σ)`;
      fields.crash_type = c.crash_type; hints.crash_type = "measured from CCTV (lateral motion)";
      if (c.crash_type === "cut_in" && cr.cut_in_start && cr.cut_in_duration) {
        const t = (mid(cr.cut_in_start) ?? 0) + (mid(cr.cut_in_duration) ?? 0);
        fields.cut_in_time_s = t.toFixed(2);
        hints.cut_in_time_s = `measured from CCTV: start ${cr.cut_in_start.lo.toFixed(2)}–${cr.cut_in_start.hi.toFixed(2)} s, duration ${cr.cut_in_duration.lo.toFixed(2)}–${cr.cut_in_duration.hi.toFixed(2)} s`;
      }
      const d = mid(cr.other_decel);
      if (c.crash_type === "lead_vehicle_decel" && d && d > 0.05) {
        fields.lead_decel_mps2 = d.toFixed(2);
        hints.lead_decel_mps2 = `measured from CCTV: ${cr.other_decel.lo.toFixed(2)}–${cr.other_decel.hi.toFixed(2)} m/s²`;
      }
      if (b.t_crash != null) { fields.time_to_impact_s = (b.t_crash - c.t_start).toFixed(2); hints.time_to_impact_s = "measured from CCTV"; }
      if (b.outcome.collided && b.outcome.impact_speed_mps != null) {
        fields.impact_speed_mph = f1(b.outcome.impact_speed_mps / MPH); hints.impact_speed_mph = "measured from CCTV";
      }
      const pathOf = (ids: number[]) => info.tracks.filter((t) => ids.includes(t.id)).flatMap((t) => t.path);
      onMeasured({
        fields, hints,
        cctv: { video_id: vid, run_id: a.run_id, display: {
          measured: m, calibration: a.calibration, calibration_input: { mode: "rectangle", img_pts: clicks },
          ego_ids: a.ego_ids, other_ids: a.other_ids, frame: { width: info.width, height: info.height },
          paths: { av: pathOf(a.ego_ids), other: pathOf(a.other_ids) } } },
      });
      setDone(a.run_id);
      setStatus(`Measured (run ${a.run_id}). Values filled into the Kinematics fields; you can still edit them.`);
      return true;
    } catch (e) { setStatus(`Measure failed: ${(e as Error).message}`); return false; }
    finally { setBusy(false); }
  };
  useEffect(() => { live.current = { vid, info, status, measure }; });

  useEffect(() => {
    if (!demoRef) return;
    demoRef.current = { run: async (id, e, say) => {
      const L0 = live.current;
      if (L0.vid !== id || !L0.info) {
        if (L0.vid !== id) {
          say("Loading the demo CCTV clip…");
          setDebugOpen(true); await sleep(300); flash("debug-id"); setDebugId(id); await sleep(600);
          flash("debug-load"); setVid(id); await sleep(700);
        }
        for (;;) {
          const c = live.current;
          if (c.info && c.vid === id) break;
          if (/^(Unknown video|Detection failed)/.test(c.status)) { say(c.status); return false; }
          say(c.status.startsWith("Detecting") ? c.status : "Waiting for vehicle detection…");
          await sleep(400);
        }
      }
      const info0 = live.current.info!;
      const missing = [...e.avTracks, ...e.otherTracks].filter((t) => !info0.tracks.some((x) => x.id === t));
      if (missing.length) { say(`Demo entry names track(s) ${missing.join(", ")} that this clip does not have.`); return false; }
      setClicks([]); setEgo([]); setOther([]); setDone(null);
      say("Calibrating: four road points A, B, C, D.");
      flash("frame", 2600); await sleep(500);
      for (const p of e.clicks) { setClicks((cur) => (cur.length >= 4 ? cur : [...cur, p])); await sleep(550); }
      say("Real-world size of the rectangle, and contact seen in the video.");
      flash("L"); setL(String(e.L)); await sleep(550);
      flash("W"); setW(String(e.W)); await sleep(550);
      flash("contact"); setContact(e.contact); await sleep(550);
      say(`Pick the AV: track ${e.avTracks.map((t) => `#${t}`).join(", ")}. Other vehicle: ${e.otherTracks.length ? e.otherTracks.map((t) => `#${t}`).join(", ") : "auto"}.`);
      for (const t of e.avTracks) { flash(`track-${t}`); setEgo((a) => [...a, t]); await sleep(600); }
      for (const t of e.otherTracks) { flash(`track-${t}`); setOther((a) => [...a, t]); await sleep(600); }
      flash("measure", 1500); await sleep(500);
      const t0 = Date.now();
      const msg = () => `Measuring speeds on GPU… ${Math.round((Date.now() - t0) / 1000)} s (usually about 45 s)`;
      say(msg());
      const tick = setInterval(() => say(msg()), 1000);
      try { return await live.current.measure(); } finally { clearInterval(tick); }
    } };
    return () => { demoRef.current = null; };
  }, [demoRef]);

  const line = (pts: [number, number][]) => pts.map((p) => p.join(",")).join(" ");
  const sw = info ? Math.max(2, info.width / 450) : 2;

  return (
    <div className="mt-4 space-y-3 rounded-md border border-line p-3">
      <div className="text-xs font-medium text-muted">CCTV footage</div>
      <div className="flex flex-wrap items-center gap-2">
        <input type="file" accept="video/*,.mp4,.mov,.avi,.mkv,.webm,.m4v" className="text-sm" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
        <details className="text-xs text-muted" open={debugOpen} onToggle={(e) => setDebugOpen(e.currentTarget.open)}>
          <summary className="cursor-pointer">use existing video id</summary>
          <div className="mt-1 flex gap-2">
            <input data-demo="debug-id" className={input} value={debugId} onChange={(e) => setDebugId(e.target.value.trim())} placeholder="32 hex characters" />
            <button type="button" data-demo="debug-load" className={btn} disabled={!/^[0-9a-f]{32}$/.test(debugId)} onClick={() => setVid(debugId)}>Load</button>
          </div>
        </details>
      </div>
      {status && <p className="text-xs text-muted">{status}</p>}

      {vid && info && (
        <>
          <div data-demo="frame" className="relative cursor-crosshair overflow-hidden rounded-md bg-black" onClick={onFrameClick}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={`${P}/${vid}/frame0.jpg`} alt="First CCTV frame, privacy-blurred" className="block w-full select-none" draggable={false} />
            <svg viewBox={`0 0 ${info.width} ${info.height}`} className="pointer-events-none absolute inset-0 h-full w-full" preserveAspectRatio="none" aria-hidden>
              {info.tracks.map((t) => (
                <polyline key={t.id} points={line(t.path)} fill="none" stroke="#fff" strokeOpacity={ego.includes(t.id) || other.includes(t.id) ? 1 : 0.45}
                  strokeWidth={ego.includes(t.id) ? sw * 1.6 : sw} strokeDasharray={other.includes(t.id) ? `${sw * 3} ${sw * 2}` : undefined} />
              ))}
              {info.tracks.map((t) => {
                const p = t.path[t.path.length - 1];
                return p ? <text key={t.id} x={p[0] + sw * 3} y={p[1] - sw * 3} fill="#fff" stroke="#000" strokeWidth={sw * 0.6} paintOrder="stroke" fontSize={sw * 9} fontFamily="sans-serif">
                  #{t.id}{ego.includes(t.id) ? " AV" : other.includes(t.id) ? " other" : ""}</text> : null;
              })}
              {clicks.length > 1 && <polyline points={line(clicks.length === 4 ? [...clicks, clicks[0]] : clicks)} fill="none" stroke="#bbb" strokeWidth={sw} strokeDasharray={`${sw * 4} ${sw * 3}`} />}
              {clicks.map((p, i) => (
                <g key={i}><circle cx={p[0]} cy={p[1]} r={sw * 2.5} fill="#fff" stroke="#000" strokeWidth={sw * 0.5} />
                  <text x={p[0] + sw * 4} y={p[1] + sw * 8} fill="#fff" stroke="#000" strokeWidth={sw * 0.6} paintOrder="stroke" fontSize={sw * 9} fontFamily="sans-serif">{"ABCD"[i]}</text></g>
              ))}
            </svg>
          </div>
          <div className="grid gap-3 sm:grid-cols-4">
            <label className="block text-xs text-muted">Length L, A to B (m)<input data-demo="L" className={input} inputMode="decimal" value={L} onChange={(e) => setL(e.target.value)} /></label>
            <label className="block text-xs text-muted">Width W, B to C (m)<input data-demo="W" className={input} inputMode="decimal" value={W} onChange={(e) => setW(e.target.value)} /></label>
            <label className="block text-xs text-muted">Contact in video
              <select data-demo="contact" className={input} value={contact} onChange={(e) => setContact(e.target.value)}><option value="auto">auto</option><option value="yes">yes</option><option value="no">no</option></select>
            </label>
            <div className="flex items-end gap-2">
              <button type="button" className={btn} onClick={() => setClicks((cur) => cur.slice(0, -1))} disabled={!clicks.length}>Undo click</button>
              <span className="pb-1.5 text-xs text-muted">{clicks.length}/4</span>
            </div>
          </div>
          <div>
            <div className="mb-1 text-xs text-muted">Pick the AV (and optionally the other vehicle; blank = auto)</div>
            <div className="grid grid-cols-[repeat(auto-fill,minmax(110px,1fr))] gap-2">
              {info.tracks.map((t) => (
                <div key={t.id} data-demo={`track-${t.id}`} className={`rounded-md border p-1 text-[11px] ${ego.includes(t.id) ? "border-fg" : other.includes(t.id) ? "border-muted" : "border-line"}`}>
                  {t.thumb
                    // eslint-disable-next-line @next/next/no-img-element
                    ? <img src={`${P}/${vid}/track/${t.id}.jpg`} alt={`track ${t.id}`} className="h-14 w-full rounded bg-black object-contain" />
                    : <div className="h-14" />}
                  <div className="mt-0.5">#{t.id} {t.cls} · {t.t0}–{t.t1}s</div>
                  <div className="mt-1 flex gap-1">
                    <button type="button" onClick={() => toggle(t.id, "av")} className={`flex-1 rounded border px-1 ${ego.includes(t.id) ? "border-fg font-semibold" : "border-line"}`}>AV</button>
                    <button type="button" onClick={() => toggle(t.id, "oth")} className={`flex-1 rounded border px-1 ${other.includes(t.id) ? "border-fg font-semibold" : "border-line"}`}>Other</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button type="button" data-demo="measure" disabled={!ready || busy} onClick={() => { void measure(); }} className="rounded-md border border-accent px-3 py-1.5 text-sm text-accent disabled:opacity-40">
              {busy ? "Measuring…" : done ? "Measure again" : "Measure"}
            </button>
            {!ready && <span className="text-xs text-muted">Needs 4 clicks, L, W and the AV.</span>}
          </div>
        </>
      )}
    </div>
  );
}
