export const DRIVER_LABEL: Record<string, string> = {
  careful_a: "Careful driver A (UN R157 Annex 3, PM1)",
  careful_b: "Careful driver B (UN R157 Annex 3, PM2)",
};
export const DRIVER_SHORT: Record<string, string> = { careful_a: "A", careful_b: "B" };

export const CRASH_LABEL: Record<string, string> = {
  cut_in: "Cut-in",
  lead_vehicle_decel: "Lead vehicle braking",
  cut_out: "Cut-out",
  other: "Other / stationary hazard",
};

export function pct(x: number | null | undefined, digits = 0): string {
  if (x == null || !Number.isFinite(x)) return "–";
  // Keep small but non-zero values visible (a CI bound of 0.27% must not read as 0%).
  const d = x > 0 && x < 0.01 ? 1 : x < 1 && x > 0.99 ? 1 : digits;
  return `${(100 * x).toFixed(d)}%`;
}

export function gbp(x: number): string {
  const s = `£${Math.abs(Math.round(x)).toLocaleString("en-GB")}`;
  return x < 0 ? `−${s}` : s;
}

export type Tone = "pursue" | "dont" | "evidence" | "cannot" | "none";
export function decisionTone(d: string | null | undefined): Tone {
  switch (d) {
    case "pursue": return "pursue";
    case "dont_pursue":
    case "not_av_recovery": return "dont";
    case "pull_logs_first":
    case "get_more_evidence": return "evidence";
    case "cannot_price": return "cannot";
    default: return "none";
  }
}

export const TIER_LABEL = ["Tier 0 · report only", "Tier 1 · video", "Tier 2 · AV logs"];
