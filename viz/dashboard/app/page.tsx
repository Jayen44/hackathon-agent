"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { UploadCctvButton } from "@/components/cctv";
import { DecisionBadge, GbpRange } from "@/components/ui";
import { assessExample, listClaims, type InboxRow } from "@/lib/api";
import { CRASH_LABEL, decisionTone, pct } from "@/lib/format";

const FILTERS = [
  ["all", "All"],
  ["pursue", "Pursue"],
  ["evidence", "Get more evidence"],
  ["dont", "Don't pursue"],
  ["cannot", "Cannot price"],
] as const;

export default function Inbox() {
  const [rows, setRows] = useState<InboxRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const router = useRouter();

  useEffect(() => {
    listClaims().then(setRows).catch((e) => setErr(String(e.message ?? e)));
  }, []);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const r of rows ?? []) c[decisionTone(r.decision)] = (c[decisionTone(r.decision)] ?? 0) + 1;
    return c;
  }, [rows]);
  const shown = (rows ?? []).filter((r) => filter === "all" || decisionTone(r.decision) === filter);

  const assess = async (id: string) => {
    await assessExample(id);
    router.push(`/claims/${encodeURIComponent(id)}`);
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Claims inbox</h1>
          <p className="mt-1 max-w-2xl text-sm text-muted">
            Claims the insurer has paid under AEVA 2018 s.2 where the AV was driving. For each: would a careful and
            competent driver have avoided the crash, and what can be recovered from the AV company under s.5.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <UploadCctvButton className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:opacity-90" />
          <Link href="/new" className="rounded-md border border-line px-3 py-2 text-sm font-medium hover:border-accent hover:text-accent">
            New claim (form)
          </Link>
        </div>
      </div>

      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Filter by decision">
        {FILTERS.map(([k, label]) => (
          <button
            key={k}
            role="tab"
            aria-selected={filter === k}
            onClick={() => setFilter(k)}
            className={`rounded-full border px-3 py-1 text-xs ${filter === k ? "border-accent bg-accent-soft text-accent" : "border-line text-muted hover:text-fg"}`}
          >
            {label} <span className="num">{k === "all" ? rows?.length ?? 0 : counts[k] ?? 0}</span>
          </button>
        ))}
      </div>

      {err && <p className="rounded border border-bad/30 bg-bad-soft p-3 text-sm text-bad">Could not load claims: {err}</p>}
      {!rows && !err && <p className="text-sm text-muted">Loading claims…</p>}

      {rows && (
        <div className="overflow-x-auto rounded-lg border border-line bg-panel">
          <table className="w-full min-w-[860px] text-sm">
            <thead className="border-b border-line text-left text-xs uppercase tracking-wide text-muted">
              <tr>
                <th className="px-4 py-2.5 font-medium">Claim</th>
                <th className="px-4 py-2.5 font-medium">Crash type</th>
                <th className="px-4 py-2.5 font-medium">Evidence</th>
                <th className="px-4 py-2.5 text-right font-medium">P(avoid) A</th>
                <th className="px-4 py-2.5 text-right font-medium">P(avoid) B</th>
                <th className="px-4 py-2.5 text-right font-medium">Expected recovery</th>
                <th className="px-4 py-2.5 font-medium">Decision</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((r) => {
                const a = r.p_avoid?.careful_a, b = r.p_avoid?.careful_b;
                const assessed = r.decision != null;
                return (
                  <tr key={r.claim_id} className="border-b border-line last:border-0 hover:bg-sunk">
                    <td className="px-4 py-2.5">
                      {assessed ? (
                        <Link href={`/claims/${encodeURIComponent(r.claim_id)}`} className="font-mono text-[13px] text-accent hover:underline">{r.claim_id}</Link>
                      ) : (
                        <span className="font-mono text-[13px]">{r.claim_id}</span>
                      )}
                      <div className="text-xs text-muted">{r.origin === "example" ? "synthetic example" : `submitted${r.source === "cctv" ? " · CCTV" : ""}${r.synthetic ? " · synthetic" : ""}`}</div>
                    </td>
                    <td className="px-4 py-2.5">{r.crash_type ? CRASH_LABEL[r.crash_type] ?? r.crash_type : "–"}</td>
                    <td className="px-4 py-2.5 num">{r.evidence_tier != null ? `Tier ${r.evidence_tier}` : "–"}</td>
                    <td className="px-4 py-2.5 text-right num">{a ? <>{pct(a.p)} <span className="text-xs text-muted">{pct(a.ci90[0])}–{pct(a.ci90[1])}</span></> : "–"}</td>
                    <td className="px-4 py-2.5 text-right num">{b ? <>{pct(b.p)} <span className="text-xs text-muted">{pct(b.ci90[0])}–{pct(b.ci90[1])}</span></> : "–"}</td>
                    <td className="px-4 py-2.5 text-right">
                      {r.expected_recovery_gbp ? <GbpRange iv={r.expected_recovery_gbp} compact /> : <span className="text-xs text-muted">not priced</span>}
                    </td>
                    <td className="px-4 py-2.5">
                      {assessed ? (
                        <DecisionBadge decision={r.decision} label={r.decision_label} />
                      ) : (
                        <button onClick={() => assess(r.claim_id)} className="rounded border border-line px-2 py-0.5 text-xs hover:border-accent hover:text-accent">Assess</button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-muted">
        P(avoid): share of simulated variations in which the careful driver avoids the crash, with its 90% confidence
        interval. A = UN R157 Annex 3 performance model 1, B = performance model 2; the two bracket a careful and
        competent human. Recovery ranges come from the finance engine and include legal cost.
      </p>
    </div>
  );
}
