"use client";

import { useState } from "react";
import { Panel } from "@/components/ui";
import { API_BASE, type Interval } from "@/lib/api";
import { gbp } from "@/lib/format";

// Output of agents/debate.py (Antonio, insurance branch), run on our sim by the Modal API.
type Pricing = { decision: string; expected_recovery: Interval | null; reasons: string[] };
export type Debate = {
  available: boolean;
  reason?: string;
  mode?: string;
  mode_label?: string;
  original?: Pricing;
  adjuster?: { recommendation: string; key_assumptions: string[] };
  challenge?: { assumption: string; argument: string };
  challenged?: Pricing;
  rebuttal?: { verdict: string; reasoning: string };
  final?: Pricing;
  contested?: boolean;
  fallback_reason?: string;
  duration_s?: number;
  trace?: { agent: string; step: string; detail: Record<string, unknown>; ts?: string }[];
};

const AGENT_NAME: Record<string, string> = {
  adjuster: "Adjuster", defence_counsel: "Defence counsel", adjuster_rebuttal: "Adjuster rebuttal", orchestrator: "Orchestrator",
};

function Range({ p }: { p?: Pricing }) {
  if (!p) return null;
  const e = p.expected_recovery;
  return (
    <span className="num text-xs text-muted">
      {p.decision.replaceAll("_", " ")}{e ? ` · ${gbp(e.low)} to ${gbp(e.high)} (central ${gbp(e.mid)})` : ""}
    </span>
  );
}

function Step({ name, ts, children, priced }: { name: string; ts?: string; children: React.ReactNode; priced?: Pricing }) {
  return (
    <li className="rounded-md border border-line bg-sunk p-3 text-sm">
      <div className="flex items-baseline justify-between gap-2">
        <span className="font-semibold">{name}</span>
        {ts && <time className="num text-[11px] text-muted">{new Date(ts).toLocaleTimeString("en-GB")}</time>}
      </div>
      <div className="mt-1 space-y-1.5">{children}</div>
      {priced && <div className="mt-2 border-t border-line pt-1.5"><span className="text-[11px] text-muted">finance re-price: </span><Range p={priced} /></div>}
    </li>
  );
}

export function DebatePanel({ claimId, initial }: { claimId: string; initial: Debate | undefined }) {
  const [d, setD] = useState<Debate | undefined>(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const rerun = async () => {
    setBusy(true); setErr(null);
    try {
      const r = await fetch(`${API_BASE}/api/debate`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ claim_id: claimId }) });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      // Live Claude agents take minutes: poll until the Modal job stores the result.
      for (let i = 0; i < 300; i++) {
        await new Promise((res) => setTimeout(res, 3000));
        const s = await (await fetch(`${API_BASE}/api/debate/${encodeURIComponent(claimId)}`, { cache: "no-store" })).json();
        if (s.status === "done") { setD(s.debate); return; }
        if (s.status === "error") throw new Error(s.error ?? "debate failed");
      }
      throw new Error("timed out");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const ts = (agent: string) => d?.trace?.find((t) => t.agent === agent && t.step === "answer")?.ts;

  return (
    <Panel
      title="Adjuster vs defence counsel"
      aside={<span className="rounded bg-sunk px-1.5 py-0.5 text-[11px] text-muted">{d?.mode === "claude" ? "AI-generated triage commentary" : "scripted agents"}</span>}
    >
      {!d?.available ? (
        <p className="text-sm text-muted">No debate: {d?.reason ?? "not run"}.</p>
      ) : (
        <>
          <p className="mb-3 text-xs text-muted">
            The system argues against itself. Defence counsel acts for the AV company; the adjuster accepts, partly
            accepts or rejects. Every GBP figure is re-priced by the finance engine, never written by an agent.
            Mode: {d.mode_label}{d.fallback_reason ? ` (${d.fallback_reason})` : ""}{d.duration_s != null ? `, ${d.duration_s} s` : ""}.
          </p>
          <ol className="space-y-3">
            <Step name="Adjuster" ts={ts("adjuster")} priced={d.original}>
              <p>{d.adjuster?.recommendation}</p>
              {!!d.adjuster?.key_assumptions?.length && (
                <ul className="list-disc pl-4 text-xs text-muted">{d.adjuster.key_assumptions.slice(0, 4).map((a, i) => <li key={i}>{a}</li>)}</ul>
              )}
            </Step>
            <Step name="Defence counsel" ts={ts("defence_counsel")} priced={d.challenged}>
              <p className="text-xs text-muted">Attacks: {d.challenge?.assumption}</p>
              <p>{d.challenge?.argument}</p>
            </Step>
            <Step name={`Adjuster rebuttal · ${d.rebuttal?.verdict.replaceAll("_", " ")}`} ts={ts("adjuster_rebuttal")} priced={d.final}>
              <p>{d.rebuttal?.reasoning}</p>
            </Step>
          </ol>
          {d.contested && <p className="mt-3 rounded border border-warn/30 bg-warn-soft p-2 text-sm text-warn">Contested: a human claims handler must review.</p>}
        </>
      )}
      {err && <p className="mt-2 text-xs text-bad">Could not re-run: {err}</p>}
      <button type="button" disabled={busy} onClick={rerun} className="mt-3 rounded-md border border-line px-3 py-1.5 text-xs hover:border-accent hover:text-accent disabled:opacity-50">
        {busy ? "Agents working (can take a few minutes)…" : "Run live debate (Claude agents)"}
      </button>
    </Panel>
  );
}
