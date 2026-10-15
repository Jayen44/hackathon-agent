import type { Interval } from "@/lib/api";
import { decisionTone, gbp, pct } from "@/lib/format";

const TONE: Record<string, string> = {
  pursue: "bg-good-soft text-good border-good/30",
  dont: "bg-neutral-soft text-fg border-line",
  evidence: "bg-warn-soft text-warn border-warn/30",
  cannot: "bg-bad-soft text-bad border-bad/30",
  none: "bg-sunk text-muted border-line",
};

export function DecisionBadge({ decision, label, size = "sm" }: { decision: string | null | undefined; label: string; size?: "sm" | "lg" }) {
  const t = TONE[decisionTone(decision)];
  return (
    <span className={`inline-flex items-center whitespace-nowrap rounded border font-medium ${t} ${size === "lg" ? "px-3 py-1 text-base" : "px-2 py-0.5 text-xs"}`}>
      {label}
    </span>
  );
}

export function Panel({ title, children, className = "", aside }: { title?: string; children: React.ReactNode; className?: string; aside?: React.ReactNode }) {
  return (
    <section className={`rounded-lg border border-line bg-panel ${className}`}>
      {title && (
        <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
          <h2 className="text-sm font-semibold">{title}</h2>
          {aside}
        </div>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

/** GBP interval: always the range, never a bare number. */
export function GbpRange({ iv, compact = false }: { iv: Interval | null | undefined; compact?: boolean }) {
  if (!iv) return <span className="text-muted">–</span>;
  if (compact) return <span className="num whitespace-nowrap">{gbp(iv.low)} to {gbp(iv.high)}</span>;
  return (
    <span className="num">
      <span className="text-2xl font-semibold">{gbp(iv.low)} to {gbp(iv.high)}</span>
      <span className="ml-2 text-sm text-muted">central {gbp(iv.mid)}</span>
    </span>
  );
}

/** P(avoid) with its 90% CI on a 0-100% track. */
export function PBar({ p, ci, label, band }: { p: number; ci: [number, number]; label: string; band?: [number, number] | null }) {
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
        <span>{label}</span>
        <span className="num font-semibold">{pct(p)} <span className="font-normal text-muted">CI {pct(ci[0])}–{pct(ci[1])}</span></span>
      </div>
      <div className="relative h-3 rounded bg-sunk" role="img" aria-label={`${label}: ${pct(p)}, 90% CI ${pct(ci[0])} to ${pct(ci[1])}`}>
        {band && <div className="absolute inset-y-0 rounded bg-accent-soft" style={{ left: `${band[0] * 100}%`, width: `${Math.max(0.5, (band[1] - band[0]) * 100)}%` }} />}
        <div className="absolute inset-y-0.5 rounded bg-accent/40" style={{ left: `${ci[0] * 100}%`, width: `${Math.max(0.6, (ci[1] - ci[0]) * 100)}%` }} />
        <div className="absolute inset-y-0 w-0.5 bg-accent" style={{ left: `calc(${p * 100}% - 1px)` }} />
      </div>
    </div>
  );
}

export function Meter({ value, threshold, label }: { value: number; threshold?: number; label: string }) {
  const tone = threshold != null && value < threshold ? "bg-warn" : "bg-good";
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm"><span>{label}</span><span className="num font-semibold">{value.toFixed(2)}</span></div>
      <div className="relative h-2 rounded bg-sunk">
        <div className={`absolute inset-y-0 left-0 rounded ${tone}`} style={{ width: `${value * 100}%` }} />
        {threshold != null && <div className="absolute -inset-y-1 w-px bg-fg/60" style={{ left: `${threshold * 100}%` }} title={`threshold ${threshold}`} />}
      </div>
    </div>
  );
}

export function Dl({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted">{k}</dt>
          <dd className="num">{v}</dd>
        </div>
      ))}
    </dl>
  );
}
