// Same-origin proxy to the Sim Lab CCTV endpoints (viz/lab/cctv.py) for the intake form.
// Only the read/analyze routes the form needs; the path is checked against fixed patterns.
// Video upload goes straight to the Sim Lab (large files; Vercel caps request bodies).
import { SIMLAB_BASE } from "@/lib/api";

export const maxDuration = 120;

const GET_OK = [
  /^video\/[0-9a-f]{32}\/(status|tracks|frame0\.jpg)$/,
  /^video\/[0-9a-f]{32}\/track\/\d{1,6}\.jpg$/,
];
const POST_OK = [/^video\/[0-9a-f]{32}\/analyze$/];

async function forward(req: Request, parts: string[], allowed: RegExp[]) {
  const path = parts.join("/");
  if (!allowed.some((re) => re.test(path))) return new Response("not found", { status: 404 });
  const init: RequestInit = { method: req.method, cache: "no-store" };
  if (req.method === "POST") {
    const body = await req.text();
    if (body.length > 20_000) return new Response("body too large", { status: 413 });
    init.body = body;
    init.headers = { "content-type": "application/json" };
  }
  const r = await fetch(`${SIMLAB_BASE}/api/${path}`, init);
  const headers = new Headers({ "content-type": r.headers.get("content-type") ?? "application/octet-stream", "cache-control": "no-store" });
  return new Response(r.body, { status: r.status, headers });
}

type Ctx = { params: Promise<{ path: string[] }> };
export async function GET(req: Request, ctx: Ctx) { return forward(req, (await ctx.params).path, GET_OK); }
export async function POST(req: Request, ctx: Ctx) { return forward(req, (await ctx.params).path, POST_OK); }
