"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { CctvEvidencePanel, cctvViewerSrc } from "@/components/cctv";
import { DebatePanel } from "@/components/debate";
import { DecisionBadge, Dl, GbpRange, Meter, Panel, PBar } from "@/components/ui";
import { getClaim, replayUrl, type Claim, type Interval } from "@/lib/api";
import { CRASH_LABEL, DRIVER_LABEL, gbp, pct, TIER_LABEL } from "@/lib/format";

const PARAM_LABEL: Record<string, string> = {
  ego_speed: "AV speed", other_speed: "Other vehicle speed", gap: "Gap", lateral_offset: "Lateral start offset",
  cut_in_start: "Cut-in start", cut_in_duration: "Cut-in duration", other_decel: "Lead braking", other_brake_time: "Lead brake time",
  av_brake_start: "AV brake start", av_decel: "AV braking",
};
const UNIT: Record<string, string> = {
  ego_speed: "m/s", other_speed: "m/s", gap: "m", lateral_offset: "m", cut_in_start: "s", cut_in_duration: "s",
  other_decel: "m/s²", other_brake_time: "s", av_brake_start: "s", av_decel: "m/s²",
};

function useClaim(id: string) {
  const [claim, setClaim] = useState<Claim | null>(null);
  const [state, setState] = useState<{ kind: "loading" | "running" | "missing" | "error"; msg?: string; started?: number }>({ kind: "loading" });
  useEffect(() => {
    let alive = true, timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const r = await getClaim(id);
        if (!alive) return;
        if (r.status === "done") { setClaim(r.claim); return; }
        if (r.status === "missing") { setState({ kind: "missing" }); return; }
        setState({ kind: "running", started: r.started });
        timer = setTimeout(poll, 2500);
      } catch (e) {
        if (alive) setState({ kind: "error", msg: (e as Error).message });
      }
    };
    poll();
    return () => { alive = false; clearTimeout(timer); };
  }, [id]);
  return { claim, state };
}

function Running({ started }: { started?: number }) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => { const t = setInterval(() => setNow(Date.now() / 1000), 1000); return () => clearInterval(t); }, []);
  const secs = started ? Math.max(0, Math.round(now - started)) : null;
  return (
    <Panel>
      <p className="font-medium">Assessing on Modal{secs != null ? ` · ${secs} s` : ""}</p>
      <ol className="mt-3 list-decimal space-y-1 pl-5 text-sm text-muted">
        <li>Evidence to parameter ranges (tier, sources, priors)</li>
        <li>Monte Carlo with careful drivers A and B, fanned out over CPU workers</li>
        <li>Sensitivity: which fact moves P(avoid) most</li>
        <li>Projection: what the next evidence tier would settle</li>
        <li>Liability and GBP from the insurance engine</li>
      </ol>
      <p className="mt-3 text-xs text-muted">Usually 30–90 seconds.</p>
    </Panel>
  );
}

function IvRow({ iv, fmt }: { iv: Interval | null; fmt: (x: number) => string }) {
  if (!iv) return <span className="text-muted">not available</span>;
  return <span>{fmt(iv.low)} to {fmt(iv.high)} <span className="text-muted">(central {fmt(iv.mid)})</span></span>;
}

export default function ClaimPage() {
  const { id } = useParams<{ id: string }>();
  const cid = decodeURIComponent(id);
  const { claim, state } = useClaim(cid);
  const [done, setDone] = useState<Record<string, boolean>>({});
  const [replaySrc, setReplaySrc] = useState<"cctv" | "sim">("cctv");

  if (!claim) {
    return (
      <div className="space-y-4">
        <Link href="/" className="text-sm text-muted hover:text-fg">← Claims</Link>
        <h1 className="font-mono text-lg">{cid}</h1>
        {state.kind === "loading" && <p className="text-sm text-muted">Loading…</p>}
        {state.kind === "running" && <Running started={state.started} />}
        {state.kind === "missing" && <p className="text-sm text-muted">This claim has not been assessed yet.</p>}
        {state.kind === "error" && <p className="rounded border border-bad/30 bg-bad-soft p-3 text-sm text-bad">Assessment failed: {state.msg}</p>}
      </div>
    );
  }

  const s = claim.sim;
  const rec = claim.gbp.recovery;
  const v = claim.gbp.verdict;
  const viewerSrc = `/viewer/index.html?data=${encodeURIComponent(replayUrl(claim.claim_id))}&cam=chase`;
  const band = s?.evidence_band ?? null;
  const cctv = claim.cctv ?? null;
  const showCctvReplay = !!cctv && replaySrc === "cctv";

  return (
    <div className="space-y-5">
      <Link href="/" className="text-sm text-muted hover:text-fg">← Claims</Link>

      {/* Top: decision and money */}
      <section className="rounded-lg border border-line bg-panel p-5">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
              <span className="font-mono text-sm text-fg">{claim.claim_id}</span>
              <span>·</span><span>{claim.crash_type ? CRASH_LABEL[claim.crash_type] ?? claim.crash_type : "crash type unknown"}</span>
              <span>·</span><span>{cctv ? `CCTV (tier 1), video ${cctv.video_id.slice(0, 8)}` : TIER_LABEL[claim.evidence_tier] ?? `Tier ${claim.evidence_tier}`}</span>
              {claim.synthetic && <><span>·</span><span className="rounded bg-sunk px-1.5 py-0.5">synthetic example</span></>}
            </div>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <DecisionBadge decision={claim.decision} label={claim.decision_label} size="lg" />
              {claim.engine_decision !== claim.decision && (
                <span className="text-xs text-muted">engine: {claim.engine_decision.replaceAll("_", " ")}; held by the data-sufficiency gate</span>
              )}
            </div>
            {v && <p className="mt-3 max-w-2xl text-sm">{v.summary} <span className="text-muted">Liability lean: {v.liable.replaceAll("_", " ").toLowerCase()}, {v.confidence.toLowerCase()} confidence.</span></p>}
          </div>
          <div className="text-right">
            <div className="text-xs uppercase tracking-wide text-muted">Expected recovery, net of legal cost</div>
            {claim.expected_recovery_gbp ? (
              <div className="mt-1"><GbpRange iv={claim.expected_recovery_gbp} /></div>
            ) : (
              <div className="mt-1 max-w-sm text-sm"><span className="font-semibold">Not priced.</span> <span className="text-muted">{claim.gbp.reason}</span></div>
            )}
            {claim.sufficiency_gate.applied && <div className="mt-1 text-xs text-warn">Indicative only: data sufficiency below {claim.sufficiency_gate.threshold}</div>}
          </div>
        </div>
        <p className="mt-4 border-t border-line pt-3 text-xs text-muted">
          Triage, not a ruling. {claim.disclaimer}
        </p>
      </section>

      {/* Middle: replay + evidence */}
      <div className="space-y-5">
        {cctv && <CctvEvidencePanel c={cctv} />}
        <Panel title="Replay: reported AV vs careful drivers A and B" className="overflow-hidden" aside={cctv ? (
          <div className="flex gap-1 text-[11px]" role="tablist" aria-label="Replay source">
            {([["cctv", "CCTV"], ["sim", "Sim median"]] as const).map(([k, l]) => (
              <button key={k} role="tab" aria-selected={replaySrc === k} onClick={() => setReplaySrc(k)}
                className={`rounded border px-2 py-0.5 ${replaySrc === k ? "border-accent text-accent" : "border-line text-muted hover:text-fg"}`}>{l}</button>
            ))}
          </div>
        ) : <span className="text-[11px] text-muted">median sample, same scenario</span>}>
          {showCctvReplay ? (
            <div className="-m-4">
              <iframe key="cctv" title="3D replay of the CCTV reconstruction" src={cctvViewerSrc(cctv)} className="block h-[520px] w-full border-0 lg:h-[460px]" allow="fullscreen" />
            </div>
          ) : claim.has_replay ? (
            <div className="-m-4">
              <iframe key="sim" title="3D replay" src={viewerSrc} className="block h-[520px] w-full border-0 lg:h-[460px]" allow="fullscreen" />
            </div>
          ) : (
            <p className="text-sm text-muted">No replay: {claim.sim_error ?? "no reconstructed conflict in this claim."}</p>
          )}
        </Panel>

        <div className="grid gap-5 lg:grid-cols-2">
          <Panel title="Would a careful driver have avoided it?">
            {s ? (
              <div className="space-y-4">
                {(["careful_a", "careful_b"] as const).filter((k) => s.drivers[k]).map((k) => (
                  <PBar key={k} label={DRIVER_LABEL[k]} p={s.drivers[k].p_avoid} ci={s.drivers[k].ci90} band={band} />
                ))}
                <p className="text-[11px] text-muted">
                  Bar: 90% CI from {s.drivers.careful_a?.n_samples ?? "–"} simulated variations per model. Shaded band:
                  P(avoid) range given facts still unknown{band ? ` (${pct(band[0])}–${pct(band[1])})` : ""}.
                </p>
              </div>
            ) : (
              <p className="text-sm text-muted">{claim.sim_error ?? "Not simulated: no reconstructed conflict."}</p>
            )}
          </Panel>
          <Panel title="Reconstruction checks">
            <div className="space-y-4">
              {claim.data_sufficiency && (
                <div>
                  <Meter label="Data sufficiency" value={claim.data_sufficiency.score} threshold={claim.sufficiency_gate.threshold} />
                  <p className="mt-1 text-[11px] text-muted">
                    Reported: {claim.data_sufficiency.reported.join(", ") || "none"}. Assumed (prior): {claim.data_sufficiency.prior.join(", ") || "none"}.
                  </p>
                </div>
              )}
              <Dl rows={[
                ["Reproduction", s?.reproduction ? (
                  <span className={s.reproduction.reproduced_flag ? "text-good" : "text-warn"}>
                    {s.reproduction.reproduced_flag ? "reproduced" : "not reproduced"}: {pct(s.reproduction.rate)} of {s.reproduction.n} runs match the report
                    {Object.keys(s.reproduction.mismatches ?? {}).length ? ` (mismatch: ${Object.keys(s.reproduction.mismatches).join(", ")})` : ""}
                  </span>) : "not checked"],
                ["Timeline", claim.timeline_check ? (
                  claim.timeline_check.consistent === null ? <span className="text-muted">{claim.timeline_check.reason ?? "not checked"}</span>
                    : claim.timeline_check.consistent ? <span className="text-good">consistent</span>
                      : <span className="text-bad">{claim.timeline_check.reason}</span>) : "not checked"],
                ["Most decisive fact", s?.sensitivity?.[0] ? `${PARAM_LABEL[s.sensitivity[0].param] ?? s.sensitivity[0].param} (moves P(avoid) up to ${pct(s.sensitivity[0].swing)})` : "–"],
              ]} />
            </div>
          </Panel>
        </div>
      </div>

      {/* Money breakdown */}
      <Panel title="How the GBP figure is built" aside={<span className="text-[11px] text-muted">finance engine (insurance branch), read-only</span>}>
        {rec ? (
          <div className="grid gap-5 md:grid-cols-2">
            <Dl rows={[
              ["P(avoid) bracket A/B", <IvRow key="p" iv={rec.p_avoid} fmt={(x) => pct(x)} />],
              ["AV company share", <IvRow key="s" iv={rec.av_share} fmt={(x) => pct(x)} />],
              ["Claim value", <IvRow key="v" iv={rec.claim_value} fmt={gbp} />],
              ["Legal cost", <IvRow key="l" iv={rec.legal_cost} fmt={gbp} />],
              ["Expected recovery", <IvRow key="e" iv={rec.expected_recovery} fmt={gbp} />],
            ]} />
            <div className="space-y-3 text-sm">
              <div>
                <div className="text-xs font-medium text-muted">Engine reasons</div>
                <ul className="mt-1 list-disc space-y-1 pl-4">{rec.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </div>
              {!!rec.sources.length && (
                <div>
                  <div className="text-xs font-medium text-muted">Sources</div>
                  <ul className="mt-1 list-disc space-y-1 pl-4 text-muted">{rec.sources.map((r, i) => <li key={i}>{r}</li>)}</ul>
                </div>
              )}
            </div>
          </div>
        ) : (
          <p className="text-sm"><span className="font-semibold">Not priced:</span> {claim.gbp.reason}</p>
        )}
        {!!claim.gbp.notes?.length && (
          <ul className="mt-4 space-y-1 border-t border-line pt-3 text-xs text-muted">{claim.gbp.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        )}
      </Panel>

      {/* Bottom: information requests + agents */}
      <div className="grid gap-5 lg:grid-cols-[1fr_420px]">
        <Panel title="Information requests" aside={<span className="text-[11px] text-muted">ranked: pricing blockers, then expected effect</span>}>
          {claim.information_requests.length ? (
            <ol className="space-y-2">
              {claim.information_requests.map((r) => (
                <li key={r.id} className="flex gap-3 rounded-md border border-line p-3">
                  <input type="checkbox" aria-label={`Mark obtained: ${r.title}`} checked={!!done[r.id]} onChange={(e) => setDone({ ...done, [r.id]: e.target.checked })} className="mt-1" />
                  <div className={`min-w-0 text-sm ${done[r.id] ? "opacity-50" : ""}`}>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="num text-xs text-muted">{r.rank}.</span>
                      <span className="font-medium">{r.title}</span>
                      {r.blocks_pricing && <span className="rounded bg-bad-soft px-1.5 py-0.5 text-[11px] text-bad">blocks pricing</span>}
                    </div>
                    <p className="mt-0.5 text-muted">{r.why}</p>
                    <p className="mt-0.5 num">{r.expected_effect}</p>
                  </div>
                </li>
              ))}
            </ol>
          ) : <p className="text-sm text-muted">Nothing outstanding.</p>}
        </Panel>
        <DebatePanel claimId={claim.claim_id} initial={claim.debate} />
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="Parameter ranges used">
          {s ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted"><tr><th className="py-1 font-medium">Fact</th><th className="py-1 text-right font-medium">Range</th><th className="py-1 pl-4 font-medium">Source</th></tr></thead>
                <tbody>
                  {Object.entries(s.ranges).map(([k, r]) => (
                    <tr key={k} className="border-t border-line">
                      <td className="py-1.5">{PARAM_LABEL[k] ?? k}</td>
                      <td className="py-1.5 text-right num">{r.lo === r.hi ? r.lo.toFixed(2) : `${r.lo.toFixed(2)}–${r.hi.toFixed(2)}`} {UNIT[k] ?? ""}</td>
                      <td className="py-1.5 pl-4"><span className={`rounded px-1.5 py-0.5 text-[11px] ${r.source === "prior" ? "bg-warn-soft text-warn" : "bg-sunk text-muted"}`}>{r.source}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <p className="text-sm text-muted">No simulation.</p>}
        </Panel>
        <Panel title="Assumptions and limits">
          <ul className="list-disc space-y-1 pl-4 text-sm text-muted">
            {claim.assumptions.map((a, i) => <li key={i}>{a}</li>)}
            {s && Object.values(s.drivers).map((d) => <li key={d.model}>Driver model: {d.model}</li>)}
          </ul>
        </Panel>
      </div>
    </div>
  );
}
