"use client";

// Insurer pricing plug-in on the claim page: which model priced the claim, the profile's rules, and a side-by-side
// comparison of the built-in UK engine with the insurer's model. All text from the insurer's model is shown as plain
// text (React escapes it). Every figure comes from one of the two outputs.
import { useEffect, useState } from "react";
import { DecisionBadge, Panel } from "@/components/ui";
import { getProfiles, repriceClaim, type Claim, type Interval, type PricingOutput, type ProfilesView } from "@/lib/api";
import { decisionText, gbp } from "@/lib/format";

const RULE_TEXT: Record<string, string> = {
  min_net_recovery_gbp: "Minimum net recovery", max_legal_spend_gbp: "Maximum legal spend",
  require_av_logs_above_gbp: "AV logs required above", human_signoff_above_gbp: "Sign-off above",
  flag_if_model_spread_above: "Model spread limit", require_reproduced: "Require reproduction",
  outside_r157_scope_action: "Outside R157 scope",
};
export function ruleValue(rule: string, v: number | boolean | string) {
  if (typeof v === "boolean") return v ? "on" : "off";
  if (typeof v === "number") return rule.endsWith("_gbp") ? gbp(v) : `${Math.round(v * 100)}%`;
  return v.replaceAll("_", " ");
}

function Iv({ iv }: { iv: Interval | null | undefined }) {
  if (!iv) return <span className="text-muted">not priced</span>;
  return <span className="num whitespace-nowrap">{gbp(iv.low)} to {gbp(iv.high)} <span className="text-muted">({gbp(iv.mid)})</span></span>;
}

function overlap(a?: Interval | null, b?: Interval | null) {
  if (!a || !b) return null;
  return a.low <= b.high && b.low <= a.high;
}

function Comparison({ b, i, bFinal, iFinal, insurerLabel }: { b: PricingOutput; i: PricingOutput; bFinal: string; iFinal: string; insurerLabel: string }) {
  const hl = "bg-warn-soft";
  const rows: [string, React.ReactNode, React.ReactNode, boolean][] = [
    ["Claim value", <Iv key="b" iv={b.claim_value_gbp} />, <Iv key="i" iv={i.claim_value_gbp} />, overlap(b.claim_value_gbp, i.claim_value_gbp) === false],
    ["Expected recovery", <Iv key="b" iv={b.expected_recovery_gbp} />, <Iv key="i" iv={i.expected_recovery_gbp} />, overlap(b.expected_recovery_gbp, i.expected_recovery_gbp) === false],
    ["Legal cost", <Iv key="b" iv={b.legal_cost_gbp} />, <Iv key="i" iv={i.legal_cost_gbp} />, false],
    ["Model decision", decisionText(b.decision), decisionText(i.decision), b.decision !== i.decision],
    ["After rules", decisionText(bFinal), decisionText(iFinal), bFinal !== iFinal],
  ];
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-xs text-muted">
          <tr><th className="py-1 pr-3 font-medium"></th><th className="py-1 pr-3 font-medium">Built-in UK engine (finance team)</th><th className="py-1 font-medium">{insurerLabel}</th></tr>
        </thead>
        <tbody>
          {rows.map(([k, x, y, diff]) => (
            <tr key={k} className="border-t border-line">
              <td className="py-1.5 pr-3 text-muted">{k}</td>
              <td className={`py-1.5 pr-3 ${diff ? hl : ""}`}>{x}</td>
              <td className={`py-1.5 ${diff ? hl : ""}`}>{y}</td>
            </tr>
          ))}
          <tr className="border-t border-line align-top">
            <td className="py-1.5 pr-3 text-muted">Key reasons</td>
            <td className="py-1.5 pr-3 text-xs"><ul className="list-disc space-y-0.5 pl-4">{b.reasons.slice(0, 3).map((r, n) => <li key={n}>{r}</li>)}</ul></td>
            <td className="py-1.5 text-xs"><ul className="list-disc space-y-0.5 pl-4">{i.reasons.slice(0, 4).map((r, n) => <li key={n}>{r}</li>)}</ul></td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function PricingPanel({ claim, onClaim }: { claim: Claim; onClaim: (c: Claim) => void }) {
  const [profiles, setProfiles] = useState<ProfilesView | null | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { getProfiles().then(setProfiles).catch(() => setProfiles(null)); }, []);

  const p = claim.pricing;
  if (!p) {
    if (profiles === undefined) return null;
    return (
      <Panel title="Pricing model and rules">
        {profiles ? (
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <span className="text-muted">This claim was assessed before pricing profiles. Price it under:</span>
            <Switcher profiles={profiles} value="" busy={busy} onPick={pick} />
            {err && <span className="text-xs text-bad">{err}</span>}
          </div>
        ) : <p className="text-sm text-muted">Insurer pricing models and rules: not available on this API deployment yet.</p>}
      </Panel>
    );
  }

  async function pick(pid: string) {
    if (!pid) return;
    setBusy(true); setErr(null);
    try { onClaim(await repriceClaim(claim.claim_id, pid)); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  const insurerLabel = p.insurer ? `${p.profile.name} model ${p.webhook_version ?? ""}`.trim() : p.profile.name;
  const fired = (claim.rules_applied ?? []).filter((r) => r.fired);
  const engineDiffers = claim.decision !== claim.engine_decision;
  return (
    <div data-tour="pricing">
      <Panel title="Pricing model and rules" aside={profiles ? <Switcher profiles={profiles} value={p.profile.id} busy={busy} onPick={pick} /> : undefined}>
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            <span><span className="text-muted">Priced by:</span> <span className="font-medium">{p.profile.name}</span> <span className="text-muted">· {p.model_version}</span></span>
            {p.source === "webhook" && p.latency_ms != null && <span className="text-xs text-muted">reply in {p.latency_ms} ms</span>}
            <span className="flex items-center gap-2"><span className="text-muted">Final decision:</span><DecisionBadge decision={claim.decision} label={decisionText(claim.decision)} /></span>
            {engineDiffers && <span className="text-xs text-muted">built-in engine alone: {decisionText(claim.engine_decision)}</span>}
            {err && <span className="text-xs text-bad">{err}</span>}
          </div>
          {p.source === "fallback" && <p className="rounded border border-warn/30 bg-warn-soft p-2 text-xs text-warn">Fallback: {p.fallback_reason}</p>}

          {p.insurer && (
            <div>
              <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
                <h3 className="text-xs font-medium text-muted">Comparison</h3>
                <span className={`text-xs ${p.comparison?.agree ? "text-good" : "text-warn"}`}>{p.comparison?.agree ? "models agree" : "models differ"}</span>
              </div>
              <Comparison b={p.builtin} i={p.insurer} bFinal={p.builtin_final} iFinal={p.insurer_final ?? p.insurer.decision} insurerLabel={insurerLabel} />
              {!!p.comparison?.why.length && (
                <div className="mt-2 text-xs"><span className="text-muted">Where they differ:</span>
                  <ul className="mt-0.5 list-disc space-y-0.5 pl-4">{p.comparison.why.map((w, n) => <li key={n}>{w}</li>)}</ul></div>
              )}
            </div>
          )}

          <div>
            <h3 className="mb-1 text-xs font-medium text-muted">Rules applied {claim.rules_applied?.length ? `(${fired.length} of ${claim.rules_applied.length} fired)` : ""}</h3>
            {claim.rules_applied?.length ? (
              <ul className="space-y-1 text-sm">
                {claim.rules_applied.map((r) => (
                  <li key={r.rule} className={`flex flex-wrap gap-x-2 rounded px-2 py-1 ${r.fired ? "border border-warn/30 bg-warn-soft" : ""}`}>
                    <span className={r.fired ? "font-medium" : "text-muted"}>{r.fired ? "●" : "○"} {RULE_TEXT[r.rule] ?? r.rule} {ruleValue(r.rule, r.value)}</span>
                    <span className={r.fired ? "" : "text-muted"}>{r.reason}</span>
                  </li>
                ))}
              </ul>
            ) : <p className="text-sm text-muted">No rules in this profile.</p>}
          </div>
        </div>
      </Panel>
    </div>
  );
}

function Switcher({ profiles, value, busy, onPick }: { profiles: ProfilesView; value: string; busy: boolean; onPick: (id: string) => void }) {
  return (
    <label className="flex items-center gap-2 text-xs text-muted">
      {busy ? "Re-pricing…" : "Profile"}
      <select value={value} disabled={busy} onChange={(e) => onPick(e.target.value)} className="rounded border border-line bg-panel px-2 py-0.5 text-xs text-fg">
        {!value && <option value="">choose…</option>}
        {profiles.profiles.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
      </select>
    </label>
  );
}
