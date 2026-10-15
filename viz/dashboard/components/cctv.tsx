"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Panel } from "@/components/ui";
import { cctvUploadUrl, SIMLAB_BASE, type CctvEvidence, type Measured } from "@/lib/api";

/** "Upload CCTV" entry: opens the Sim Lab CCTV page, which sends the finished claim back here. */
export function UploadCctvButton({ className = "" }: { className?: string }) {
  const [href, setHref] = useState(cctvUploadUrl());
  useEffect(() => setHref(cctvUploadUrl(window.location.origin)), []);
  return (
    <a href={href} className={className || "rounded-md border border-accent px-3 py-2 text-sm font-medium text-accent hover:bg-accent-soft"}>
      Upload CCTV
    </a>
  );
}

const kmh = (mps: number) => (mps * 3.6).toFixed(0);

function MeasuredRow({ label, m, unit = "speed" }: { label: string; m?: Measured; unit?: "speed" | "m" }) {
  if (!m || m.value == null) return null;
  const sd = m.sd ?? 0;
  return (
    <div className="flex items-baseline justify-between gap-3 border-t border-line py-1.5 text-sm first:border-0">
      <span className="text-muted">{label}</span>
      <span className="num">
        {unit === "speed"
          ? <>{kmh(m.value)} km/h <span className="text-muted">± {kmh(sd)} (1σ) · {m.value.toFixed(1)} ± {sd.toFixed(1)} m/s</span></>
          : <>{m.value.toFixed(1)} m <span className="text-muted">± {sd.toFixed(1)} (1σ)</span></>}
      </span>
    </div>
  );
}

/** First frame (privacy-blurred by the Sim Lab) with the calibration rectangle and the AV / other vehicle paths. */
function AnnotatedFrame({ c }: { c: CctvEvidence }) {
  const [failed, setFailed] = useState(false);
  const w = c.frame.width ?? 1280, h = c.frame.height ?? 720;
  const sw = Math.max(2, w / 400);
  const line = (pts: [number, number][]) => pts.map((p) => p.join(",")).join(" ");
  if (failed) return <p className="text-sm text-muted">First frame not available (video deleted from the Sim Lab volume).</p>;
  return (
    <div className="relative overflow-hidden rounded-md bg-black">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={`${SIMLAB_BASE}/api/video/${c.video_id}/frame0.jpg`} alt="First CCTV frame, privacy-blurred" className="block w-full" onError={() => setFailed(true)} />
      <svg viewBox={`0 0 ${w} ${h}`} className="absolute inset-0 h-full w-full" preserveAspectRatio="none" aria-hidden>
        {c.calibration.img_pts.length >= 3 && (
          <polygon points={line(c.calibration.img_pts)} fill="#ffd40022" stroke="#ffd400" strokeWidth={sw} strokeDasharray={`${sw * 4} ${sw * 3}`} />
        )}
        {c.paths.other.length > 1 && <polyline points={line(c.paths.other)} fill="none" stroke="#5bb8ff" strokeWidth={sw * 1.6} />}
        {c.paths.av.length > 1 && <polyline points={line(c.paths.av)} fill="none" stroke="#ef5a5a" strokeWidth={sw * 1.6} />}
      </svg>
      <div className="absolute bottom-2 left-2 flex gap-2 text-[11px]">
        <span className="rounded bg-black/70 px-1.5 py-0.5 text-[#ef5a5a]">AV #{c.ego_ids.join("+")}</span>
        <span className="rounded bg-black/70 px-1.5 py-0.5 text-[#5bb8ff]">other #{c.other_ids.join("+")}</span>
        <span className="rounded bg-black/70 px-1.5 py-0.5 text-[#ffd400]">calibration</span>
      </div>
    </div>
  );
}

export function CctvEvidencePanel({ c }: { c: CctvEvidence }) {
  const m = c.measured;
  return (
    <Panel
      title={`Evidence source: CCTV (tier 1), video ${c.video_id.slice(0, 8)}, measured speeds ±σ`}
      aside={<a className="text-[11px] text-accent hover:underline" href={`${SIMLAB_BASE}/cctv?v=${c.video_id}`} target="_blank" rel="noopener noreferrer">open in Sim Lab ↗</a>}
    >
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <AnnotatedFrame c={c} />
        <div className="space-y-3">
          <div>
            <MeasuredRow label="AV speed at conflict start" m={m.ego_speed_mps} />
            <MeasuredRow label="AV speed just before impact" m={m.ego_speed_before_impact_mps} />
            <MeasuredRow label="Other vehicle speed" m={m.other_speed_mps} />
            <MeasuredRow label="Gap when the hazard appeared" m={m.gap_m} unit="m" />
          </div>
          <ul className="list-disc space-y-1 pl-4 text-xs text-muted">
            <li>Measured from video by the Sim Lab: detection + tracking, road-plane calibration ({c.calibration.mode ?? "?"}{c.calibration.reprojection_rms_m != null ? `, reprojection RMS ${c.calibration.reprojection_rms_m.toFixed(2)} m` : ", exact 4-point fit"}). Ranges fed to the Monte Carlo are ± 2σ.</li>
            <li>Tier 1: no AV decision log, so engagement is <b>alleged</b>, not verified. Obtaining the AV logs is the tier-2 upgrade.</li>
            <li>Video SHA-256 {c.sha256 ? <span className="font-mono">{c.sha256.slice(0, 16)}…</span> : "not recorded"}. Frame shown privacy-blurred; raw video stays in the Sim Lab volume.</li>
          </ul>
        </div>
      </div>
    </Panel>
  );
}

export function cctvViewerSrc(c: CctvEvidence) {
  return `${SIMLAB_BASE}/viewer/?data=/api/replay/${c.video_id}/${c.run_id}&cam=chase`;
}

export function NewClaimTabs({ active }: { active: "form" | "cctv" }) {
  return (
    <div className="flex flex-wrap gap-2" role="tablist" aria-label="How to start a claim">
      <Link href="/new" role="tab" aria-selected={active === "form"}
        className={`rounded-full border px-3 py-1 text-sm ${active === "form" ? "border-accent bg-accent-soft text-accent" : "border-line text-muted hover:text-fg"}`}>
        Claim form
      </Link>
      <UploadCctvButton className="rounded-full border border-line px-3 py-1 text-sm text-muted hover:border-accent hover:text-accent" />
    </div>
  );
}
