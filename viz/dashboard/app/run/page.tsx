"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { DecisionBadge, Panel } from "@/components/ui";
import { fetchPortfolio, fetchTrace, FLEET_MOCK, LANES, laneOf, listRuns, type FleetEvent, type Portfolio, type Run } from "@/lib/fleet";
import { CRASH_LABEL, gbp } from "@/lib/format";

const LANE_H = 52, LEFT = 150, W = 1000;

function fmtDur(s: number) {
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  return h ? `${h}h ${String(m).padStart(2, "0")}m` : `${m}m ${String(sec).padStart(2, "0")}s`;
}

function Swimlanes({ events, t0, now, selected, onSelect }: { events: FleetEvent[]; t0: number; now: number; selected: string | null; onSelect: (id: string) => void }) {
  const span = Math.max(10_000, now - t0);
  const x = (ts: number) => LEFT + ((ts - t0) / span) * (W - LEFT - 16);
  const y = (lane: number) => lane * LANE_H + LANE_H / 2 + 8;
  const byId = new Map(events.map((e) => [e.id, e]));
  const H = LANES.length * LANE_H + 28;
  return (
    <div className="overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="min-w-[720px] w-full" role="img" aria-label="Agent lanes over time with hand-offs">
        <defs>
          <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
            <path d="M0,0 L8,4 L0,8 z" fill="var(--accent)" />
          </marker>
        </defs>
        {LANES.map((l, i) => (
          <g key={l.key}>
            <rect x={0} y={i * LANE_H + 8} width={W} height={LANE_H} fill={i % 2 ? "var(--sunk)" : "transparent"} />
            <text x={10} y={y(i) + 4} fontSize="12" fill="var(--fg)">{l.label}</text>
          </g>
        ))}
        {events.map((e) => {
          const p = e.parent ? byId.get(e.parent) : undefined;
          if (!p || laneOf(p.agent) === laneOf(e.agent)) return null;
          return <line key={`h${e.id}`} x1={x(p.ts)} y1={y(laneOf(p.agent))} x2={x(e.ts)} y2={y(laneOf(e.agent))} stroke="var(--accent)" strokeOpacity="0.35" strokeWidth="1.2" markerEnd="url(#arrow)" />;
        })}
        {events.map((e) => {
          const sel = e.id === selected;
          return (
            <circle key={e.id} cx={x(e.ts)} cy={y(laneOf(e.agent))} r={sel ? 6 : 4} fill={sel ? "var(--accent)" : "var(--fg)"} fillOpacity={sel ? 1 : 0.7}
              className="cursor-pointer" onClick={() => onSelect(e.id)}>
              <title>{`${e.agent} · ${e.type}: ${e.summary}`}</title>
            </circle>
          );
        })}
        <text x={LEFT} y={H - 4} fontSize="11" fill="var(--muted)">start</text>
        <text x={W - 16} y={H - 4} fontSize="11" fill="var(--muted)" textAnchor="end">now · {fmtDur(span / 1000)}</text>
      </svg>
    </div>
  );
}

function PortfolioMap({ p }: { p: Portfolio | null }) {
  const rows = Object.entries(p?.recoverable_by_crash_type ?? {}).sort((a, b) => b[1].mid - a[1].mid);
  const max = Math.max(1, ...rows.map(([, v]) => v.high));
  if (!rows.length) return <p className="text-sm text-muted">No recoverable claims priced yet.</p>;
  return (
    <div className="space-y-3">
      {rows.map(([k, v]) => (
        <div key={k}>
          <div className="mb-1 flex justify-between gap-2 text-sm">
            <span>{CRASH_LABEL[k] ?? k}</span>
            <span className="num">{gbp(v.low)} to {gbp(v.high)} <span className="text-muted">central {gbp(v.mid)}</span></span>
          </div>
          <div className="relative h-3 rounded bg-sunk" role="img" aria-label={`${k}: ${gbp(v.low)} to ${gbp(v.high)}`}>
            <div className="absolute inset-y-0 rounded bg-accent/40" style={{ left: `${(v.low / max) * 100}%`, width: `${Math.max(0.5, ((v.high - v.low) / max) * 100)}%` }} />
            <div className="absolute inset-y-0 w-0.5 bg-accent" style={{ left: `${(v.mid / max) * 100}%` }} />
          </div>
        </div>
      ))}
      <p className="text-[11px] text-muted">Claims the engine says to pursue or investigate further; each range sums the claim-level ranges, negative ends counted as zero.</p>
    </div>
  );
}

export default function AgentRun() {
  const [runs, setRuns] = useState<Run[] | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [events, setEvents] = useState<FleetEvent[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const cursor = useRef<string | null>(null);

  useEffect(() => {
    listRuns().then((r) => { setRuns(r); if (r.length) setRunId(r[0].id); }).catch((e) => setErr(e.message));
  }, []);

  useEffect(() => {
    if (!runId) return;
    let alive = true;
    cursor.current = null;
    setEvents([]);
    const tick = async () => {
      try {
        const r = await fetchTrace(runId, cursor.current);
        if (!alive) return;
        cursor.current = r.cursor;
        if (r.events.length) setEvents((cur) => { const seen = new Set(cur.map((e) => e.id)); return [...cur, ...r.events.filter((e) => !seen.has(e.id))]; });
        setErr(null);
      } catch (e) {
        if (alive) setErr((e as Error).message);
      }
    };
    tick();
    const a = setInterval(tick, 2000), b = setInterval(() => setNow(Date.now()), 1000);
    return () => { alive = false; clearInterval(a); clearInterval(b); };
  }, [runId]);

  const priced = useMemo(() => new Set(events.filter((e) => laneOf(e.agent) === 4 && e.type === "price" && e.claim_id).map((e) => e.claim_id as string)), [events]);
  useEffect(() => {
    if (!runId) return;
    fetchPortfolio(runId, FLEET_MOCK ? priced : undefined).then(setPortfolio).catch(() => { /* keep last */ });
  }, [runId, priced, FLEET_MOCK ? events.length : Math.floor(now / 5000)]); // eslint-disable-line react-hooks/exhaustive-deps

  const t0 = events.length ? Math.min(...events.map((e) => e.ts)) : now;
  const sel = events.find((e) => e.id === selected) ?? null;
  const feed = [...events].reverse().slice(0, 40);
  const run = runs?.find((r) => r.id === runId);
  const total = portfolio?.claims_total ?? run?.claims_total;
  // Wall-clock run time from the run's own start (not from the first event loaded); finished runs stop at their last step.
  const runStart = run?.started_at ? Date.parse(run.started_at) : events.length ? t0 : null;
  const lastTs = events.length ? Math.max(...events.map((e) => e.ts)) : now;
  const runEnd = !run?.status || run.status === "running" ? now : lastTs;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Agent run</h1>
          <p className="mt-1 max-w-3xl text-sm text-muted">
            A long portfolio run: the Portfolio lead hands each crash to a team of agents. Investigator builds the scenario,
            Reconstructor checks the sim reproduces the crash, Counterfactual analyst runs careful drivers A and B, Adjuster
            prices the recovery, Defence counsel attacks it.
          </p>
        </div>
        {runs && runs.length > 1 && (
          <select className="rounded-md border border-line bg-panel px-2 py-1.5 text-sm" value={runId ?? ""} onChange={(e) => setRunId(e.target.value)}>
            {runs.map((r) => <option key={r.id} value={r.id}>{r.label ?? r.id}</option>)}
          </select>
        )}
      </div>

      {FLEET_MOCK && (
        <p className="rounded border border-warn/30 bg-warn-soft p-2 text-xs text-warn">
          Replay mode: the live fleet API is not connected. Numbers are real stored assessments of the synthetic example
          claims; event timing is simulated.
        </p>
      )}
      {err && <p className="rounded border border-bad/30 bg-bad-soft p-2 text-xs text-bad">Fleet API: {err}</p>}

      <div className="grid gap-3 sm:grid-cols-4">
        {[
          ["Status", run?.status ?? (events.length ? "running" : "waiting")],
          ["Running time", runStart ? fmtDur(Math.max(0, (runEnd - runStart) / 1000)) : "–"],
          ["Claims processed", `${portfolio?.claims_processed ?? priced.size}${total ? ` / ${total}` : ""}`],
          ["Agent steps", String(events.length)],
        ].map(([k, v]) => (
          <div key={k} className="rounded-lg border border-line bg-panel px-4 py-3">
            <div className="text-xs text-muted">{k}</div>
            <div className="num mt-0.5 text-lg font-semibold">{v}</div>
          </div>
        ))}
      </div>

      <div data-tour="lanes">
      <Panel title="Agents and hand-offs" aside={<span className="text-[11px] text-muted">click a step for detail</span>}>
        <Swimlanes events={events} t0={t0} now={now} selected={selected} onSelect={setSelected} />
        {sel && (
          <div className="mt-3 rounded-md border border-line bg-sunk p-3 text-sm">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="font-semibold">{LANES[laneOf(sel.agent)].label} · {sel.type}</span>
              <time className="num text-xs text-muted">{new Date(sel.ts).toLocaleTimeString("en-GB")}</time>
            </div>
            <p className="mt-1">{sel.summary}</p>
            {sel.tool && <p className="mt-1 text-xs text-muted">Tool: <span className="font-mono">{sel.tool}</span></p>}
            {sel.input_summary && <p className="mt-1 text-xs"><span className="text-muted">In:</span> {sel.input_summary}</p>}
            {sel.output_summary && <p className="mt-1 text-xs"><span className="text-muted">Out:</span> {sel.output_summary}</p>}
            {sel.claim_id && <Link href={`/claims/${encodeURIComponent(sel.claim_id)}`} className="mt-2 inline-block text-xs text-accent hover:underline">Open claim {sel.claim_id} →</Link>}
          </div>
        )}
      </Panel>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_420px]">
        <Panel title="Live trace">
          {feed.length ? (
            <ol className="max-h-[520px] space-y-2 overflow-y-auto pr-1">
              {feed.map((e) => (
                <li key={e.id} className="rounded-md border border-line p-2.5 text-sm">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <button onClick={() => setSelected(e.id)} className="font-medium hover:text-accent">{LANES[laneOf(e.agent)].label} <span className="font-normal text-muted">· {e.type}</span></button>
                    <time className="num text-[11px] text-muted">{new Date(e.ts).toLocaleTimeString("en-GB")}</time>
                  </div>
                  <p className="mt-0.5">{e.summary}</p>
                  {e.output_summary && !/^[[{]/.test(e.output_summary) && <p className="mt-0.5 text-xs text-muted">{e.output_summary}</p>}
                  {e.claim_id && <Link href={`/claims/${encodeURIComponent(e.claim_id)}`} className="text-xs text-accent hover:underline">{e.claim_id}</Link>}
                </li>
              ))}
            </ol>
          ) : <p className="text-sm text-muted">Waiting for the first agent step…</p>}
        </Panel>
        <div className="space-y-5">
          <Panel title="Recoverability map (GBP)">
            <PortfolioMap p={portfolio} />
          </Panel>
          <Panel title="Claims">
            {portfolio?.claims?.length ? (
              <ul className="max-h-[320px] space-y-1.5 overflow-y-auto text-sm">
                {portfolio.claims.map((c) => (
                  <li key={c.claim_id} className="flex items-center justify-between gap-2">
                    <Link href={`/claims/${encodeURIComponent(c.claim_id)}`} className="truncate font-mono text-[13px] text-accent hover:underline">{c.claim_id}</Link>
                    <DecisionBadge decision={c.decision} label={c.decision_label ?? c.decision} />
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">None yet.</p>}
          </Panel>
        </div>
      </div>
    </div>
  );
}
