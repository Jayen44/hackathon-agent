export type TraceEntry = {
  agent: string;
  ts: string;
  model?: string;
  input_summary: string;
  output?: Record<string, string>;
  error?: string;
  running?: boolean;
  dropped?: string[];
};

export function AgentTraceList({ entries }: { entries: TraceEntry[] }) {
  return (
    <ol className="space-y-3">
      {entries.map((e, i) => (
        <li key={i} className="rounded-md border border-line bg-sunk p-3 text-sm">
          <div className="flex items-baseline justify-between gap-2">
            <span className="font-semibold">{e.agent}</span>
            <time className="num text-[11px] text-muted">{new Date(e.ts).toLocaleTimeString("en-GB")}</time>
          </div>
          <div className="mt-0.5 text-xs text-muted">Input: {e.input_summary}{e.model ? ` · ${e.model}` : ""}</div>
          {e.running && <div className="mt-2 text-xs text-muted">Working…</div>}
          {e.error && <div className="mt-2 text-xs text-warn">{e.error}</div>}
          {e.output && (
            <dl className="mt-2 space-y-1.5">
              {Object.entries(e.output).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-[11px] uppercase tracking-wide text-muted">{k}</dt>
                  <dd className="whitespace-pre-line">{v}</dd>
                </div>
              ))}
            </dl>
          )}
          {!!e.dropped?.length && (
            <div className="mt-2 text-[11px] text-muted">{e.dropped.length} sentence(s) removed: contained numbers not in the backend result.</div>
          )}
        </li>
      ))}
    </ol>
  );
}
