"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { AgentTraceList, type TraceEntry } from "@/components/agent-trace";
import { NewClaimTabs } from "@/components/cctv";
import { Panel } from "@/components/ui";
import { submitAssessment } from "@/lib/api";

type Tri = "yes" | "no" | "unknown";
type Form = {
  claim_ref: string; incident_datetime: string; location_type: string;
  av_engaged: Tri; within_odd: Tri; crash_type: string;
  ego_speed_mph: string; other_speed_mph: string; gap_m: string; time_to_impact_s: string;
  lead_decel_mps2: string; cut_in_time_s: string; impact_speed_mph: string;
  injury_severity: string; claim_paid_gbp: string;
  injured_party_share_low_pct: string; injured_party_share_high_pct: string;
  software_verified: Tri; evidence_secured: Tri;
  evidence: { cctv: boolean; dashcam: boolean; av_logs: boolean; police_report: boolean; witnesses: boolean };
};

const EMPTY: Form = {
  claim_ref: "", incident_datetime: "", location_type: "unknown", av_engaged: "unknown", within_odd: "unknown",
  crash_type: "unknown", ego_speed_mph: "", other_speed_mph: "", gap_m: "", time_to_impact_s: "", lead_decel_mps2: "",
  cut_in_time_s: "", impact_speed_mph: "", injury_severity: "Unknown", claim_paid_gbp: "",
  injured_party_share_low_pct: "", injured_party_share_high_pct: "", software_verified: "unknown", evidence_secured: "unknown",
  evidence: { cctv: false, dashcam: false, av_logs: false, police_report: false, witnesses: false },
};

const EVIDENCE: [keyof Form["evidence"], string][] = [
  ["cctv", "CCTV"], ["dashcam", "Dashcam"], ["av_logs", "AV data logs"], ["police_report", "Police report"], ["witnesses", "Witnesses"],
];

const input = "w-full rounded-md border border-line bg-panel px-2.5 py-1.5 text-sm num placeholder:text-muted/70";

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-muted">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-muted">{hint}</span>}
    </label>
  );
}

export default function NewClaim() {
  const [f, setF] = useState<Form>(EMPTY);
  const [narrative, setNarrative] = useState("");
  const [trace, setTrace] = useState<TraceEntry[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const router = useRouter();
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((x) => ({ ...x, [k]: v }));
  const num = (k: keyof Form, label: string, unit: string, hint?: string) => (
    <Field label={`${label} (${unit})`} hint={hint}>
      <input className={input} inputMode="decimal" placeholder="unknown" value={f[k] as string} onChange={(e) => set(k, e.target.value as never)} />
    </Field>
  );
  const tri = (k: keyof Form, label: string) => (
    <Field label={label}>
      <select className={input} value={f[k] as string} onChange={(e) => set(k, e.target.value as never)}>
        <option value="unknown">Unknown</option><option value="yes">Yes</option><option value="no">No</option>
      </select>
    </Field>
  );

  const investigate = async () => {
    setBusy("Investigator reading the narrative…"); setErr(null);
    const started = new Date().toISOString();
    try {
      const r = await fetch("/api/agents/investigator", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ narrative }) });
      const b = await r.json();
      if (!r.ok) throw new Error(b.error ?? `HTTP ${r.status}`);
      if (!b.ok) {
        setTrace((t) => [...t, { agent: "Investigator", ts: started, input_summary: b.trace?.input_summary ?? "claim narrative", error: b.error }]);
        return;
      }
      const x = b.fields;
      const s = (v: number | null) => (v == null ? "" : String(v));
      setF((cur) => ({
        ...cur,
        location_type: x.location_type, av_engaged: x.av_engaged, within_odd: x.within_odd, crash_type: x.crash_type,
        ego_speed_mph: s(x.ego_speed_mph), other_speed_mph: s(x.other_speed_mph), gap_m: s(x.gap_m), time_to_impact_s: s(x.time_to_impact_s),
        injury_severity: x.injury_severity, evidence: x.evidence,
      }));
      setTrace((t) => [...t, {
        agent: "Investigator", ts: b.trace.started, model: b.trace.model, input_summary: b.trace.input_summary,
        output: { "Fields filled": Object.entries(x).filter(([k, v]) => !["unknown_fields", "notes", "evidence"].includes(k) && v != null && v !== "unknown" && v !== "Unknown").map(([k, v]) => `${k}: ${v}`).join(", ") || "none",
                  "Unknown": x.unknown_fields.join(", ") || "none", "Notes": x.notes.join(" ") || "none",
                  ...(b.trace.dropped?.length ? { "Dropped (number not in narrative)": b.trace.dropped.join(", ") } : {}) },
      }]);
    } catch (e) {
      setErr(String((e as Error).message ?? e));
    } finally {
      setBusy(null);
    }
  };

  const submit = async (body: { form?: unknown; bundle?: unknown }) => {
    setBusy("Submitting to the simulator…"); setErr(null);
    try {
      const r = await submitAssessment(body);
      router.push(`/claims/${encodeURIComponent(r.claim_id)}`);
    } catch (e) {
      setErr(String((e as Error).message ?? e)); setBusy(null);
    }
  };

  const onUpload = async (file: File) => {
    try {
      const bundle = JSON.parse(await file.text());
      await submit({ bundle });
    } catch (e) {
      setErr(`Could not read the bundle: ${(e as Error).message}`);
    }
  };

  const formBody = () => {
    const { evidence, ...rest } = f;
    const out: Record<string, unknown> = { evidence };
    for (const [k, v] of Object.entries(rest)) out[k] = v === "" ? null : v;
    return out;
  };

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">New claim</h1>
        <p className="mt-1 max-w-3xl text-sm text-muted">
          Enter what is known. Leave anything you do not know blank: unknowns become wide, clearly labelled ranges, lower the
          data-sufficiency score, and turn into information requests. Nothing is guessed silently.
        </p>
        <div className="mt-3"><NewClaimTabs active="form" /></div>
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        <div className="space-y-5">
          <Panel title="Narrative (optional)" aside={<span className="text-[11px] text-muted">AI-assisted extraction, review before submitting</span>}>
            <textarea className={`${input} h-28 font-sans`} maxLength={4000} value={narrative} onChange={(e) => setNarrative(e.target.value)}
              placeholder="e.g. Robotaxi in automated mode at 28 mph on an urban road. A van cut in about 9 m ahead and the AV braked late. Dashcam footage and a police report are available. Slight injury to the van driver." />
            <div className="mt-2 flex items-center gap-3">
              <button type="button" disabled={!narrative.trim() || !!busy} onClick={investigate}
                className="rounded-md border border-accent px-3 py-1.5 text-sm text-accent disabled:opacity-40">Extract fields with Investigator</button>
              <span className="text-[11px] text-muted">Do not paste names, plates or addresses.</span>
            </div>
          </Panel>

          <Panel title="Incident">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Claim reference" hint="Letters, digits, - _ ."><input className={input} value={f.claim_ref} onChange={(e) => set("claim_ref", e.target.value)} placeholder="auto" /></Field>
              <Field label="Date and time"><input type="datetime-local" className={input} value={f.incident_datetime} onChange={(e) => set("incident_datetime", e.target.value)} /></Field>
              <Field label="Location type">
                <select className={input} value={f.location_type} onChange={(e) => set("location_type", e.target.value)}>
                  <option value="unknown">Unknown</option><option value="urban">Urban</option><option value="a_road">A-road</option><option value="motorway">Motorway</option>
                </select>
              </Field>
              <Field label="Crash type">
                <select className={input} value={f.crash_type} onChange={(e) => set("crash_type", e.target.value)}>
                  <option value="unknown">Unknown</option><option value="cut_in">Cut-in</option><option value="lead_vehicle_decel">Lead vehicle braking</option><option value="stationary_hazard">Stationary hazard</option>
                </select>
              </Field>
              {tri("av_engaged", "Self-driving engaged?")}
              {tri("within_odd", "Within ODD?")}
            </div>
          </Panel>

          <Panel title="Kinematics">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {num("ego_speed_mph", "AV speed", "mph")}
              {num("other_speed_mph", "Other vehicle speed", "mph")}
              {num("gap_m", "Gap when hazard appeared", "m")}
              {num("time_to_impact_s", "Hazard to impact", "s", "Enables the timeline check")}
              {f.crash_type === "lead_vehicle_decel" && num("lead_decel_mps2", "Lead vehicle braking", "m/s²")}
              {f.crash_type === "cut_in" && num("cut_in_time_s", "Cut-in duration", "s")}
              {num("impact_speed_mph", "AV speed at impact", "mph", "Used for the reproduction check")}
            </div>
          </Panel>

          <Panel title="Claim and evidence">
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <Field label="Injury severity (STATS19)">
                <select className={input} value={f.injury_severity} onChange={(e) => set("injury_severity", e.target.value)}>
                  {["Unknown", "Damage only", "Slight", "Serious", "Fatal"].map((s) => <option key={s}>{s}</option>)}
                </select>
              </Field>
              {num("claim_paid_gbp", "Claim paid", "GBP")}
              <Field label="Injured party's contributory negligence (%)" hint="Leave blank if not assessed">
                <div className="flex gap-2">
                  <input className={input} inputMode="decimal" placeholder="low" value={f.injured_party_share_low_pct} onChange={(e) => set("injured_party_share_low_pct", e.target.value)} />
                  <input className={input} inputMode="decimal" placeholder="high" value={f.injured_party_share_high_pct} onChange={(e) => set("injured_party_share_high_pct", e.target.value)} />
                </div>
              </Field>
              {tri("software_verified", "Software confirmed compliant (AEVA s.4)?")}
              {tri("evidence_secured", "Evidence tamper-evident (hashed, custody)?")}
            </div>
            <fieldset className="mt-4">
              <legend className="mb-2 text-xs font-medium text-muted">Evidence available</legend>
              <div className="flex flex-wrap gap-2">
                {EVIDENCE.map(([k, label]) => (
                  <label key={k} className={`flex cursor-pointer items-center gap-2 rounded-md border px-3 py-1.5 text-sm ${f.evidence[k] ? "border-accent bg-accent-soft" : "border-line"}`}>
                    <input type="checkbox" checked={f.evidence[k]} onChange={(e) => set("evidence", { ...f.evidence, [k]: e.target.checked })} />
                    {label}
                  </label>
                ))}
              </div>
            </fieldset>
          </Panel>

          {err && <p className="rounded border border-bad/30 bg-bad-soft p-3 text-sm text-bad">{err}</p>}
          <div className="flex flex-wrap items-center gap-3">
            <button type="button" disabled={!!busy} onClick={() => submit({ form: formBody() })}
              className="rounded-md bg-accent px-4 py-2 text-sm font-medium text-on-accent disabled:opacity-50">Assess claim</button>
            <label className="cursor-pointer rounded-md border border-line px-4 py-2 text-sm hover:border-accent">
              Upload crash bundle JSON
              <input type="file" accept="application/json,.json" className="sr-only" onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])} />
            </label>
            {busy && <span className="text-sm text-muted">{busy}</span>}
          </div>
        </div>

        <aside className="space-y-5">
          <Panel title="Agent trace">
            {trace.length ? <AgentTraceList entries={trace} /> : <p className="text-sm text-muted">The Investigator turns a narrative into the fields on the left. You review and correct them before submitting.</p>}
          </Panel>
          <Panel title="How unknowns are handled">
            <ul className="list-disc space-y-1.5 pl-4 text-sm text-muted">
              <li>Blank speeds use a wide prior for the location type; blank gap uses 5–40 m. All tagged “prior”.</li>
              <li>Evidence sets the tier: AV logs = tier 2, CCTV or dashcam = tier 1, else tier 0 (report only).</li>
              <li>Engagement reported here without AV logs counts as alleged, not verified.</li>
              <li>Without tamper-evident evidence the pricing engine will not produce a GBP figure.</li>
            </ul>
          </Panel>
        </aside>
      </div>
    </div>
  );
}
