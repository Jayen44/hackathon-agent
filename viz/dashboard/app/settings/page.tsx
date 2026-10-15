"use client";

// Pricing & rules: insurer profiles (pricing model + declarative rules), webhook test, portfolio comparison.
import { useCallback, useEffect, useState } from "react";
import { ruleValue } from "@/components/pricing";
import { Panel } from "@/components/ui";
import {
  getProfiles, portfolioComparison, putProfiles, repriceAll, testWebhook,
  type PortfolioComparison, type Profile, type ProfilesView, type Rule,
} from "@/lib/api";
import { decisionText, gbp } from "@/lib/format";

export default function SettingsPage() {
  const [view, setView] = useState<ProfilesView | null | undefined>(undefined);
  const [sel, setSel] = useState<string>("");
  const [err, setErr] = useState<string | null>(null);
  const load = useCallback(() => getProfiles().then((v) => { setView(v); if (v) setSel((s) => s && v.profiles.some((p) => p.id === s) ? s : v.active); })
    .catch((e) => { setErr((e as Error).message); setView(null); }), []);
  useEffect(() => { load(); }, [load]);

  if (view === undefined) return <p className="text-sm text-muted">Loading…</p>;
  if (view === null) {
    return (
      <div className="space-y-4">
        <h1 className="text-lg font-semibold">Pricing & rules</h1>
        <Panel><p className="text-sm text-muted">Pricing profiles are not available on this API deployment yet{err ? ` (${err})` : ""}.</p></Panel>
      </div>
    );
  }
  const profile = view.profiles.find((p) => p.id === sel) ?? view.profiles[0];

  async function setActive(id: string) {
    setErr(null);
    try { setView(await putProfiles({ active: id })); } catch (e) { setErr((e as Error).message); }
  }

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-lg font-semibold">Pricing & rules</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          A profile names the pricing model used for a claim (the built-in UK engine or an insurer&apos;s own model at a
          webhook) and the insurer&apos;s rules. Rules are simple thresholds and can only make a decision more cautious.
          The built-in engine always runs alongside as the reference.
        </p>
      </div>
      {err && <p className="rounded border border-bad/30 bg-bad-soft p-2 text-sm text-bad">{err}</p>}

      <Panel title="Profiles" aside={<button type="button" onClick={async () => { if (confirm("Restore the default profiles?")) { setView(await putProfiles({ reset: true })); } }} className="text-xs text-muted hover:text-fg">Reset to defaults</button>}>
        <ul className="space-y-2">
          {view.profiles.map((p) => (
            <li key={p.id} className={`flex flex-wrap items-center gap-3 rounded border p-2 text-sm ${p.id === sel ? "border-accent" : "border-line"}`}>
              <button type="button" onClick={() => setSel(p.id)} className="min-w-0 flex-1 text-left">
                <span className="font-medium">{p.name}</span>
                <span className="ml-2 text-xs text-muted">{p.pricing.type === "builtin" ? "built-in UK engine" : `webhook · ${p.pricing.version}`} · {p.rules.length} rule{p.rules.length === 1 ? "" : "s"}</span>
                {p.pricing.type === "webhook" && p.pricing.url === view.demo_model_url && <span className="ml-2 rounded bg-sunk px-1.5 py-0.5 text-[11px] text-muted">demo model, not a real insurer</span>}
              </button>
              {p.id === view.active
                ? <span className="rounded bg-accent-soft px-2 py-0.5 text-xs text-accent">active for new claims</span>
                : <button type="button" onClick={() => setActive(p.id)} className="rounded border border-line px-2 py-0.5 text-xs hover:border-accent">Make active</button>}
            </li>
          ))}
        </ul>
      </Panel>

      {profile && <ProfileEditor key={profile.id + JSON.stringify(profile)} profile={profile} view={view} onSaved={setView} />}
      {profile && profile.pricing.type === "webhook" && <PortfolioPanel profile={profile} />}
    </div>
  );
}

function ProfileEditor({ profile, view, onSaved }: { profile: Profile; view: ProfilesView; onSaved: (v: ProfilesView) => void }) {
  const [name, setName] = useState(profile.name);
  const [type, setType] = useState(profile.pricing.type);
  const [url, setUrl] = useState(profile.pricing.type === "webhook" ? profile.pricing.url : view.demo_model_url);
  const [version, setVersion] = useState(profile.pricing.type === "webhook" ? profile.pricing.version : "v1");
  const [rules, setRules] = useState<Record<string, Rule["value"] | undefined>>(Object.fromEntries(profile.rules.map((r) => [r.rule, r.value])));
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [test, setTest] = useState<{ ok: boolean; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const isBuiltin = profile.id === "builtin";
  async function save() {
    setBusy(true); setMsg(null);
    const body: Profile = {
      id: profile.id, name,
      pricing: type === "builtin" ? { type: "builtin" } : { type: "webhook", url, version },
      rules: Object.entries(rules).filter(([, v]) => v !== undefined).map(([rule, value]) => ({ rule, value: value as Rule["value"] })),
    };
    try { onSaved(await putProfiles({ profile: body })); setMsg({ ok: true, text: "Saved." }); }
    catch (e) { setMsg({ ok: false, text: (e as Error).message }); }
    finally { setBusy(false); }
  }
  async function runTest() {
    setTest({ ok: true, text: "Sending sample payload…" });
    try {
      const r = await testWebhook(url);
      setTest(r.ok && r.output
        ? { ok: true, text: `Connected in ${r.latency_ms} ms. Reply valid: ${r.output.model_version}; decision ${decisionText(r.output.decision)}.` }
        : { ok: false, text: `Not usable: ${r.error}` });
    } catch (e) { setTest({ ok: false, text: (e as Error).message }); }
  }

  return (
    <Panel title={`Edit: ${profile.name}`}>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-3 text-sm">
          <label className="block"><span className="text-xs text-muted">Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 w-full rounded border border-line bg-panel px-2 py-1" /></label>
          <div>
            <span className="text-xs text-muted">Pricing model</span>
            <div className="mt-1 flex gap-4">
              <label className="flex items-center gap-1"><input type="radio" checked={type === "builtin"} onChange={() => setType("builtin")} /> Built-in UK engine</label>
              <label className={`flex items-center gap-1 ${isBuiltin ? "opacity-40" : ""}`}><input type="radio" disabled={isBuiltin} checked={type === "webhook"} onChange={() => setType("webhook")} /> Insurer model (webhook)</label>
            </div>
          </div>
          {type === "webhook" && (
            <div className="space-y-2">
              <label className="block"><span className="text-xs text-muted">Webhook URL (https)</span>
                <input value={url} onChange={(e) => setUrl(e.target.value)} className="mt-1 w-full rounded border border-line bg-panel px-2 py-1 font-mono text-xs" /></label>
              <label className="block"><span className="text-xs text-muted">Model version label</span>
                <input value={version} onChange={(e) => setVersion(e.target.value)} className="mt-1 w-40 rounded border border-line bg-panel px-2 py-1" /></label>
              <div className="flex flex-wrap items-center gap-2">
                <button type="button" onClick={runTest} className="rounded border border-accent px-3 py-1 text-xs text-accent">Test connection</button>
                {test && <span className={`text-xs ${test.ok ? "" : "text-bad"}`}>{test.text}</span>}
              </div>
              <p className="text-[11px] text-muted">Allowed hosts: {view.allowed_webhook_hosts.join(", ")}. Timeout 10 s; replies are validated and shown as plain text. On failure the built-in engine prices the claim and the claim page says so. Contract: viz/api/PRICING_PLUGIN.md.</p>
            </div>
          )}
        </div>
        <div className="space-y-2 text-sm">
          <span className="text-xs text-muted">Rules</span>
          {Object.entries(view.rule_specs).map(([k, spec]) => {
            const v = rules[k], on = v !== undefined;
            const set = (x: Rule["value"] | undefined) => setRules({ ...rules, [k]: x });
            return (
              <div key={k} className={`rounded border p-2 ${on ? "border-accent/50" : "border-line"}`}>
                <label className="flex items-center gap-2">
                  <input type="checkbox" checked={on} onChange={(e) => set(e.target.checked ? (spec.type === "bool" ? true : spec.type === "enum" ? spec.options![0] : spec.type === "fraction" ? 0.3 : 5000) : undefined)} />
                  <span className="font-medium">{spec.label}</span>
                  {on && spec.type === "gbp" && <input type="number" min={0} step={1000} value={Number(v)} onChange={(e) => set(Number(e.target.value))} className="ml-auto w-28 rounded border border-line bg-panel px-2 py-0.5 text-right num" />}
                  {on && spec.type === "fraction" && <input type="number" min={0} max={1} step={0.05} value={Number(v)} onChange={(e) => set(Number(e.target.value))} className="ml-auto w-20 rounded border border-line bg-panel px-2 py-0.5 text-right num" />}
                  {on && spec.type === "enum" && (
                    <select value={String(v)} onChange={(e) => set(e.target.value)} className="ml-auto rounded border border-line bg-panel px-2 py-0.5 text-xs">
                      {spec.options!.map((o) => <option key={o} value={o}>{o.replaceAll("_", " ")}</option>)}
                    </select>
                  )}
                  {on && <span className="text-xs text-muted">{spec.type === "enum" || spec.type === "bool" ? "" : ruleValue(k, v as number)}</span>}
                </label>
                <p className="mt-0.5 pl-6 text-[11px] text-muted">{spec.help}</p>
              </div>
            );
          })}
        </div>
      </div>
      <div className="mt-4 flex items-center gap-3 border-t border-line pt-3">
        <button type="button" disabled={busy} onClick={save} className="rounded bg-accent px-3 py-1 text-sm font-medium text-on-accent disabled:opacity-50">{busy ? "Saving…" : "Save profile"}</button>
        {msg && <span className={`text-xs ${msg.ok ? "text-good" : "text-bad"}`}>{msg.text}</span>}
        <span className="ml-auto text-[11px] text-muted">Saved profiles apply to new assessments and re-pricing; existing claims keep their result until re-priced.</span>
      </div>
    </Panel>
  );
}

function PortfolioPanel({ profile }: { profile: Profile }) {
  const [pc, setPc] = useState<PortfolioComparison | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { portfolioComparison(profile.id).then(setPc).catch(() => setPc(null)); }, [profile.id]);
  async function run() {
    setBusy(true); setErr(null);
    try { setPc((await repriceAll(profile.id)).comparison); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }
  const iv = (x: PortfolioComparison["builtin_total_gbp"]) => x ? `${gbp(x.low)} to ${gbp(x.high)} (central ${gbp(x.mid)}, ${x.n} claims)` : "–";
  return (
    <div data-tour="portfolio-comparison">
      <Panel title={`Comparison across claims: built-in UK engine vs ${profile.name}`} aside={
        <button type="button" disabled={busy} onClick={run} className="rounded border border-accent px-3 py-1 text-xs text-accent disabled:opacity-50">{busy ? "Re-pricing all claims…" : `Re-price all claims under ${profile.name}`}</button>}>
        {err && <p className="mb-2 text-sm text-bad">{err}</p>}
        {pc && pc.n_compared > 0 ? (
          <div className="grid gap-4 text-sm md:grid-cols-2">
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
              <dt className="text-muted">Claims compared</dt><dd className="num">{pc.n_compared}{pc.n_fallback ? ` (+${pc.n_fallback} fell back to built-in)` : ""}</dd>
              <dt className="text-muted">Agree / differ</dt><dd className="num">{pc.agree} / {pc.differ}</dd>
              <dt className="text-muted">Decisions differ</dt><dd className="num">{pc.decisions_differ}</dd>
              <dt className="text-muted">Pursue (built-in / insurer)</dt><dd className="num">{pc.pursue_builtin} / {pc.pursue_insurer}</dd>
            </dl>
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5">
              <dt className="text-muted">Total expected recovery, built-in</dt><dd className="num">{iv(pc.builtin_total_gbp)}</dd>
              <dt className="text-muted">Total expected recovery, {profile.name}</dt><dd className="num">{iv(pc.insurer_total_gbp)}</dd>
            </dl>
            <p className="text-[11px] text-muted md:col-span-2">Sums of the per-claim figures each model returned (after rules for decisions). Totals include negative central cases (claims not worth pursuing).</p>
          </div>
        ) : <p className="text-sm text-muted">No claims priced under this profile yet. Use the button to price all stored claims with it.</p>}
      </Panel>
    </div>
  );
}
