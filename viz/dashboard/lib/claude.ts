import Anthropic from "@anthropic-ai/sdk";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";
import { getVercelOidcToken } from "@vercel/oidc";
import type { z } from "zod";

// Same switch as the buildathon project (src/lib/claude.ts, MIT): with ANTHROPIC_API_KEY set we call Anthropic
// directly; otherwise the same SDK goes through Vercel AI Gateway, authed by AI_GATEWAY_API_KEY or the Vercel
// OIDC token (automatic on Vercel). No key is created or stored by this app.
const DIRECT = !!process.env.ANTHROPIC_API_KEY;
export const MODEL = DIRECT ? "claude-sonnet-5-5" : "anthropic/claude-sonnet-5.5";

export const UNAVAILABLE = "AI commentary unavailable: no model credentials configured";

export class ModelUnavailable extends Error {}

async function getClient(): Promise<Anthropic> {
  if (DIRECT) return new Anthropic();
  let token = process.env.AI_GATEWAY_API_KEY;
  if (!token) {
    try {
      token = await getVercelOidcToken();
    } catch {
      token = undefined;
    }
  }
  if (!token) throw new ModelUnavailable(UNAVAILABLE);
  return new Anthropic({ apiKey: null, authToken: token, baseURL: "https://ai-gateway.vercel.sh", maxRetries: 2 });
}

/** One structured-output call. Throws ModelUnavailable when there are no usable credentials or credit. */
export async function claudeJson<S extends z.ZodType>(opts: {
  schema: S;
  system: string;
  prompt: string;
  effort?: "low" | "medium" | "high";
}): Promise<z.infer<S>> {
  const client = await getClient();
  try {
    const response = await client.messages.parse({
      model: MODEL,
      max_tokens: 8000,
      system: opts.system,
      messages: [{ role: "user", content: opts.prompt }],
      output_config: { effort: opts.effort ?? "low", format: zodOutputFormat(opts.schema) },
    });
    if (response.stop_reason === "refusal") throw new Error("the model declined this request");
    if (response.parsed_output == null) throw new Error(`no structured output (stop_reason: ${response.stop_reason})`);
    return response.parsed_output as z.infer<S>;
  } catch (e) {
    if (e instanceof Anthropic.APIError && [401, 402, 403].includes(e.status ?? 0)) {
      throw new ModelUnavailable(`${UNAVAILABLE} (${e.status})`);
    }
    throw e;
  }
}

export function errorMessage(e: unknown): string {
  if (e instanceof ModelUnavailable) return e.message;
  return `AI commentary unavailable: ${e instanceof Error ? e.message.slice(0, 200) : String(e)}`;
}
