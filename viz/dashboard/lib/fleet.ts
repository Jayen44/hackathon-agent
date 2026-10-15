// Client for the fleet read API (Modal app `accel-fleet`): the long portfolio run's live agent trace.
// Without NEXT_PUBLIC_FLEET_API the page replays a static fixture (public/mock-fleet, built by
// viz/api/make_fleet_mock.py from real stored assessments; only its timing is simulated).
import type { Interval } from "@/lib/api";

const RAW = process.env.NEXT_PUBLIC_FLEET_API?.replace(/\/$/, "");
export const FLEET_MOCK = !RAW;
const BASE = RAW ?? "/mock-fleet";

export type Run = { id: string; status?: string; started_at?: string; claims_total?: number; claims_processed?: number; label?: string; dry_run?: boolean };
export type FleetEvent = {
  id: string;
  ts: number; // ms since epoch
  agent: string;
  type: string;
  summary: string;
  tool?: string | null;
  input_summary?: string | null;
  output_summary?: string | null;
  parent?: string | null;
  claim_id?: string | null;
};
export type Portfolio = {
  claims_total?: number;
  claims_processed?: number;
  running_s?: number;
  recoverable_by_crash_type: Record<string, Interval>;
  decisions: Record<string, number>;
  claims?: { claim_id: string; crash_type?: string | null; decision: string; decision_label?: string; expected_recovery?: Interval | null; counts_toward_map?: boolean }[];
  mock_note?: string;
};

type RawEvent = Record<string, unknown>;
const str = (v: unknown) => (v == null ? null : typeof v === "object" ? JSON.stringify(v).slice(0, 400) : String(v));

const clip = (t: string, n = 180) => (t.length > n ? `${t.slice(0, n - 1)}…` : t);
const gbpS = (x: unknown) => (typeof x === "number" ? `£${Math.round(x).toLocaleString("en-GB")}` : "");

/** One-line human summary. Debate steps arrive with a JSON summary; never show raw JSON. */
export function humanSummary(type: string, summary: string): string {
  const t = summary.trim();
  if (!(t.startsWith("{") || t.startsWith("["))) return clip(t);
  let v: unknown;
  try { v = JSON.parse(t); } catch { return clip(t.replace(/[{}"\[\]]/g, " ").replace(/\s+/g, " ").trim()); }
  const o = (Array.isArray(v) ? { items: v } : v) as Record<string, unknown>;
  const out = (o.output && typeof o.output === "object" ? o.output : {}) as Record<string, unknown>;
  const tool = type.startsWith("debate.tool:") ? type.slice("debate.tool:".length) : null;
  if (tool) {
    if (Array.isArray(o.output)) return `${tool}: ${o.output.length} candidate weak assumptions`;
    const er = out.expected_recovery as Record<string, unknown> | undefined;
    const bits = [out.decision && `decision ${String(out.decision).replaceAll("_", " ")}`, er && `central ${gbpS(er.mid)}`].filter(Boolean);
    return `${tool}${bits.length ? `: ${bits.join(", ")}` : ""}`;
  }
  if (typeof o.recommendation === "string") return clip(o.recommendation);
  if (typeof o.verdict === "string") return clip(`${String(o.verdict).replaceAll("_", " ")}: ${String(o.reasoning ?? "")}`);
  if (typeof o.argument === "string") return clip(`${String(o.assumption ?? "Challenge")}: ${o.argument}`);
  if (o.decision != null) return `Final decision: ${String(o.decision).replaceAll("_", " ")}${o.contested ? " (contested)" : ""}`;
  return clip(Object.keys(o).join(", "));
}

function norm(e: RawEvent, t0: number): FleetEvent {
  const tsRaw = e.timestamp ?? e.ts ?? e.time;
  const ts = typeof tsRaw === "number" ? (tsRaw > 1e12 ? tsRaw : tsRaw * 1000)
    : typeof tsRaw === "string" ? Date.parse(tsRaw)
      : t0 + 1000 * Number(e.t_offset_s ?? 0);
  return {
    id: String(e.id ?? e.seq ?? e.event_id),
    ts,
    agent: String(e.agent ?? "unknown"),
    type: String(e.type ?? e.step ?? ""),
    summary: humanSummary(String(e.type ?? e.step ?? ""), String(e.summary ?? "")),
    tool: str(e.tool),
    input_summary: str(e.input_summary ?? e.input),
    output_summary: str(e.output_summary ?? e.output),
    parent: str(e.parent ?? e.parent_step ?? e.parent_id),
    claim_id: str(e.claim_id),
  };
}

async function j<T>(path: string): Promise<T> {
  const r = await fetch(BASE + path, { cache: "no-store" });
  if (!r.ok) throw new Error(`fleet API HTTP ${r.status}`);
  return r.json() as Promise<T>;
}

/** Runs, live ones first: non-dry before dry, then newest first. The live API names the id `run_id`. */
export async function listRuns(): Promise<Run[]> {
  const r = await j<RawEvent[] | { runs: RawEvent[] }>(FLEET_MOCK ? "/runs.json" : "/api/runs");
  const raw = Array.isArray(r) ? r : r.runs;
  const runs: Run[] = raw.map((x) => {
    const cfg = (x.config ?? {}) as Record<string, unknown>;
    return {
      id: String(x.run_id ?? x.id),
      status: str(x.status) ?? undefined,
      started_at: str(x.created_at ?? x.started_at) ?? undefined,
      claims_total: (x.claims_total ?? cfg.claims) as number | undefined,
      label: str(x.label) ?? undefined,
      dry_run: Boolean(x.dry_run ?? cfg.dry_run ?? false),
    };
  });
  if (FLEET_MOCK) return runs;
  const t = (x: Run) => (x.started_at ? Date.parse(x.started_at) : 0);
  return runs.sort((a, b) => Number(a.dry_run) - Number(b.dry_run) || t(b) - t(a));
}

// Mock replay clock: events are revealed as the page's own clock passes their offset.
const mockStart = typeof window !== "undefined" ? Date.now() : 0;

export async function fetchTrace(runId: string, since: string | null): Promise<{ events: FleetEvent[]; cursor: string | null }> {
  if (FLEET_MOCK) {
    const all = (await j<{ events: RawEvent[] }>(`/runs/${encodeURIComponent(runId)}/trace.json`)).events.map((e) => norm(e, mockStart));
    const now = Date.now();
    const visible = all.filter((e) => e.ts <= now);
    const after = since == null ? visible : visible.filter((e) => Number(e.id) > Number(since));
    return { events: after, cursor: visible.length ? visible[visible.length - 1].id : since };
  }
  const q = since != null ? `?since=${encodeURIComponent(since)}` : "";
  const r = await j<{ events: RawEvent[]; cursor?: string | number | null; next?: string | number | null } | RawEvent[]>(`/api/runs/${encodeURIComponent(runId)}/trace${q}`);
  const raw = Array.isArray(r) ? r : r.events;
  const events = raw.map((e) => norm(e, Date.now()));
  const cur = Array.isArray(r) ? null : (r.cursor ?? r.next ?? null);
  return { events, cursor: cur != null ? String(cur) : events.length ? events[events.length - 1].id : since };
}

export async function fetchPortfolio(runId: string, visibleClaims?: Set<string>): Promise<Portfolio> {
  if (FLEET_MOCK) {
    const p = await j<Portfolio>(`/runs/${encodeURIComponent(runId)}/portfolio.json`);
    if (!visibleClaims) return p;
    // Mock replay: only count claims whose Adjuster step has been revealed so far.
    const claims = (p.claims ?? []).filter((c) => visibleClaims.has(c.claim_id));
    const by: Record<string, Interval> = {};
    const dec: Record<string, number> = {};
    for (const c of claims) {
      dec[c.decision] = (dec[c.decision] ?? 0) + 1;
      if (c.expected_recovery && c.counts_toward_map) {
        const a = (by[c.crash_type ?? "other"] ??= { low: 0, mid: 0, high: 0 });
        a.low += Math.max(0, c.expected_recovery.low); a.mid += Math.max(0, c.expected_recovery.mid); a.high += Math.max(0, c.expected_recovery.high);
      }
    }
    return { ...p, claims, claims_processed: claims.length, recoverable_by_crash_type: by, decisions: dec };
  }
  const p = await j<Record<string, unknown>>(`/api/runs/${encodeURIComponent(runId)}/portfolio`);
  type Top = { claim_id: string; crash_type?: string | null; decision: string; expected_recovery_gbp?: Interval | null };
  const top = (p.top_claims as Top[] | undefined)?.map((c) => ({ ...c, expected_recovery: c.expected_recovery_gbp ?? null, counts_toward_map: true }));
  return {
    ...(p as unknown as Portfolio),
    claims_processed: (p.claims_processed ?? p.claims_done) as number | undefined,
    recoverable_by_crash_type: (p.recoverable_by_crash_type ?? p.recoverable_gbp_by_crash_type ?? {}) as Record<string, Interval>,
    decisions: (p.decisions ?? {}) as Record<string, number>,
    claims: (p.claims as Portfolio["claims"]) ?? top,
  };
}

export const LANES: { key: string; label: string; match: string[] }[] = [
  { key: "portfolio_lead", label: "Portfolio lead", match: ["portfolio_lead", "orchestrator", "portfolio", "lead"] },
  { key: "investigator", label: "Investigator", match: ["investigator"] },
  { key: "reconstructor", label: "Reconstructor", match: ["reconstructor"] },
  { key: "counterfactual_analyst", label: "Counterfactual analyst", match: ["counterfactual_analyst", "counterfactual", "analyst"] },
  { key: "adjuster", label: "Adjuster", match: ["adjuster", "adjuster_rebuttal", "rebuttal", "referee"] },
  { key: "defence_counsel", label: "Defence counsel", match: ["defence_counsel", "defence", "defense_counsel"] },
];

export function laneOf(agent: string): number {
  const a = agent.toLowerCase();
  const i = LANES.findIndex((l) => l.match.includes(a));
  if (i >= 0) return i;
  const j2 = LANES.findIndex((l) => l.match.some((m) => a.includes(m)));
  return j2 >= 0 ? j2 : 0;
}
