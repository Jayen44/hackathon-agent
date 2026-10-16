// Client for the Modal claims API (viz/api/app.py). The dashboard never computes a result itself.
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "https://termvato--accel-claims-api-web.us-east.modal.run").replace(/\/$/, "");

// Sim Lab (viz/lab on Modal): CCTV upload -> measured speeds -> "Send to claims desk" -> /claims/<id> here.
export const SIMLAB_BASE = (process.env.NEXT_PUBLIC_SIMLAB_BASE ?? "https://termvato--accel-simlab-web.us-east.modal.run").replace(/\/$/, "");

export type Measured = { value: number | null; sd: number | null };
export type CctvEvidence = {
  video_id: string; run_id: string; tier: number; sha256: string | null;
  measured: Partial<Record<"ego_speed_mps" | "other_speed_mps" | "gap_m" | "ego_speed_before_impact_mps", Measured>>;
  min_gap_m: number | null; ranges_used?: string[]; overridden_by_insurer?: string[]; ego_ids: number[]; other_ids: number[];
  frame: { width: number | null; height: number | null };
  calibration: { mode: string | null; img_pts: [number, number][]; reprojection_rms_m: number | null };
  paths: { av: [number, number][]; other: [number, number][] };
};

export type Interval = { low: number; mid: number; high: number };
export type DriverResult = {
  p_avoid: number;
  ci90: [number, number];
  n_samples: number;
  avoids_at_p50: boolean;
  median_impact_speed_mps: number;
  model: string;
  notes: string[];
};
export type SensRow = {
  param: string; source: string; lo: number; hi: number; swing: number;
  p_at_lo: Record<string, number>; p_at_hi: Record<string, number>;
};
export type InfoRequest = {
  id: string; title: string; why: string; expected_effect: string; impact: number;
  blocks_pricing: boolean; category: string; rank: number;
};
export type Recovery = {
  claim_id: string; crash_type: string; decision: string; reasons: string[];
  p_avoid: Interval; av_share: Interval; claim_value: Interval | null; legal_cost: Interval | null;
  expected_recovery: Interval | null; sources: string[]; disclaimer: string;
};
export type Verdict = {
  liable: string; confidence: string; summary: string; recovery_case: boolean;
  steps: { name: string; outcome: string; detail: string; code: string }[];
  findings: string[]; evidence_missing: string[]; review_items: string[]; exclusions: string[];
};
export type Claim = {
  claim_id: string;
  synthetic: boolean | null;
  source: "form" | "bundle" | "cctv";
  origin?: string;
  cctv?: CctvEvidence | null;
  crash_type: string | null;
  evidence_tier: number;
  sim: null | {
    drivers: Record<string, DriverResult>;
    paired?: Record<string, unknown>;
    reproduction: null | { rate: number; ci90: [number, number]; n: number; reproduced_flag: boolean; mismatches: Record<string, number> };
    data_sufficiency: { score: number; decisive: string[]; reported: string[]; narrative: string[]; prior: string[] };
    ranges: Record<string, { lo: number; hi: number; source: string }>;
    sensitivity: SensRow[];
    go_get: string | null;
    evidence_band: [number, number] | null;
    scenario_type: string;
  };
  sim_error: string | null;
  timeline_check: null | { consistent: boolean | null; reason?: string | null; time_to_close_at_constant_speed_s?: number; reported_time_to_crash_s?: number };
  data_sufficiency: { score: number; decisive: string[]; reported: string[]; narrative: string[]; prior: string[] } | null;
  sufficiency_gate: { threshold: number; score: number | null; applied: boolean };
  projection: null | { tier: number; band_now: [number, number] | null; next: Record<string, { band: [number, number] | null; data_sufficiency: number }> };
  gbp: { available: boolean; decision: string; reason: string | null; notes: string[]; verdict?: Verdict; recovery: Recovery | null };
  decision: string;
  decision_label: string;
  engine_decision: string;
  expected_recovery_gbp: Interval | null;
  information_requests: InfoRequest[];
  unknowns: string[];
  assumptions: string[];
  disclaimer: string;
  has_replay?: boolean;
  debate?: import("@/components/debate").Debate;
  // Insurer pricing plug-in (viz/api/pricing.py). Absent on claims assessed before the feature was deployed.
  pricing?: Pricing;
  rules_applied?: RuleApplied[];
  decision_final?: string;
};

// ---------------------------------------------------------------- insurer profiles, pricing plug-in, rules
export type PricingOutput = {
  claim_value_gbp: Interval | null; expected_recovery_gbp: Interval | null; legal_cost_gbp?: Interval | null;
  decision: string; reasons: string[]; model_version: string;
};
export type Pricing = {
  profile: { id: string; name: string };
  source: "builtin" | "webhook" | "fallback";
  model_version: string;
  output: PricingOutput;
  builtin: PricingOutput;
  builtin_final: string;
  insurer: PricingOutput | null;
  insurer_final: string | null;
  fallback_reason: string | null;
  latency_ms: number | null;
  webhook_version?: string | null;
  comparison: null | { agree: boolean; decision_differs: boolean; claim_value_overlap: boolean | null; expected_recovery_overlap: boolean | null; why: string[] };
};
export type RuleApplied = { rule: string; value: number | boolean | string; fired: boolean; changed?: boolean; reason: string };
export type Rule = { rule: string; value: number | boolean | string };
export type Profile = {
  id: string; name: string;
  pricing: { type: "builtin" } | { type: "webhook"; url: string; version: string };
  rules: Rule[];
};
export type RuleSpec = { type: "gbp" | "fraction" | "bool" | "enum"; label: string; help: string; options?: string[] };
export type ProfilesView = {
  active: string; profiles: Profile[]; rule_specs: Record<string, RuleSpec>;
  allowed_webhook_hosts: string[]; demo_model_url: string;
};
export type PortfolioComparison = {
  profile_id: string; n_priced: number; n_compared: number; n_fallback: number; agree: number; differ: number;
  decisions_differ: number; pursue_builtin: number; pursue_insurer: number;
  builtin_total_gbp: (Interval & { n: number }) | null; insurer_total_gbp: (Interval & { n: number }) | null;
};
export type InboxRow = {
  claim_id: string; crash_type?: string | null; evidence_tier?: number; synthetic?: boolean; source?: string; origin?: string;
  p_avoid?: Record<string, { p: number; ci90: [number, number] }>;
  evidence_band?: [number, number] | null;
  expected_recovery_gbp?: Interval | null;
  decision: string | null; decision_label: string; reason?: string | null;
  pricing?: null | { profile: { id: string; name: string }; source: string; model_version: string; agree: boolean | null };
};

async function j<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(API_BASE + path, { cache: "no-store", ...init });
  if (!r.ok) {
    let msg = `HTTP ${r.status}`;
    try { const b = await r.json(); const d = b.detail ?? b.error; if (d) msg = typeof d === "string" ? d : JSON.stringify(d); } catch { /* keep */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export const listClaims = () => j<InboxRow[]>("/api/claims");
export const assessExample = (id: string) => j<{ claim_id: string; status: string }>(`/api/examples/${encodeURIComponent(id)}/assess`, { method: "POST" });
export const submitAssessment = (body: { form?: unknown; bundle?: unknown; cctv?: unknown }) =>
  j<{ claim_id: string; status: string }>("/api/assess", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) });
export const replayUrl = (id: string) => `${API_BASE}/api/replay/${encodeURIComponent(id)}`;

/** Poll until the assessment is stored. Returns the claim, or throws with the backend's error. */
export async function getClaim(id: string): Promise<{ status: "done"; claim: Claim } | { status: "running"; started?: number } | { status: "missing" }> {
  const r = await fetch(`${API_BASE}/api/claims/${encodeURIComponent(id)}`, { cache: "no-store" });
  if (r.status === 404) return { status: "missing" };
  if (r.status === 202) { const b = await r.json(); return { status: "running", started: b.started }; }
  const b = await r.json();
  if (!r.ok) throw new Error(b.error ?? `HTTP ${r.status}`);
  return { status: "done", claim: b as Claim };
}

const JSON_HDR = { "content-type": "application/json" };
/** null when the deployed API does not have the pricing plug-in yet (the dashboard then hides the feature). */
export async function getProfiles(): Promise<ProfilesView | null> {
  const r = await fetch(API_BASE + "/api/profiles", { cache: "no-store" });
  if (r.status === 404 || r.status === 405) return null;
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}
export const putProfiles = (body: { profile?: Profile; active?: string; delete?: string; reset?: boolean }) =>
  j<ProfilesView>("/api/profiles", { method: "PUT", headers: JSON_HDR, body: JSON.stringify(body) });
export const testWebhook = (url: string) =>
  j<{ ok: boolean; error?: string; latency_ms?: number; output?: PricingOutput }>("/api/profiles/test", { method: "POST", headers: JSON_HDR, body: JSON.stringify({ url }) });
export const repriceClaim = (id: string, profile_id: string) =>
  j<Claim>(`/api/claims/${encodeURIComponent(id)}/reprice`, { method: "POST", headers: JSON_HDR, body: JSON.stringify({ profile_id }) });
export const repriceAll = (profile_id: string) =>
  j<{ repriced: number; of: number; comparison: PortfolioComparison }>(`/api/profiles/${encodeURIComponent(profile_id)}/reprice-all`, { method: "POST" });
export const portfolioComparison = (profile_id: string) =>
  j<PortfolioComparison>(`/api/portfolio-comparison?profile_id=${encodeURIComponent(profile_id)}`);
