"""Minimal Claude tool-use loop shared by the agents.

A manual loop (not the SDK's beta tool runner) so every tool call can be written to the
trace, and tests can drive it with a fake client. Numbers never come from the model: the
model calls our deterministic tools and returns JSON that must match `schema`.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable

MODEL = "claude-opus-5-5"
MAX_TURNS = 8


class AgentError(RuntimeError):
    pass


class ToolInputError(ValueError):
    """Tool input the evidence doesn't allow; returned to the model as an error result."""


def make_client():
    """Anthropic client from ANTHROPIC_API_KEY (or .env); None when no credentials are set."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    if not (os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN")):
        return None
    import anthropic
    return anthropic.Anthropic()


def run_agent(client: Any, *, name: str, system: str, prompt: str, tools: list[dict],
              execute: Callable[[str, dict], Any], schema: dict, effort: str,
              trace: Callable[[str, str, dict], None]) -> dict:
    """Run one agent until it returns schema-valid JSON. trace(agent, step, detail) logs each step."""
    messages: list[dict] = [{"role": "user", "content": prompt}]
    for _ in range(MAX_TURNS):
        resp = client.beta.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=system,
            tools=tools,
            messages=messages,
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
        usage = getattr(resp, "usage", None)
        if usage is not None:
            trace(name, "usage", {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens,
                                  "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0})
        if resp.stop_reason == "refusal":
            raise AgentError(f"{name}: model declined ({getattr(resp, 'stop_details', None)})")
        if resp.stop_reason == "max_tokens":
            raise AgentError(f"{name}: output cut off at max_tokens")
        uses = [b for b in resp.content if b.type == "tool_use"]
        if not uses:
            text = next((b.text for b in resp.content if b.type == "text"), "")
            try:
                out = json.loads(text)
            except json.JSONDecodeError as e:
                raise AgentError(f"{name}: final answer was not JSON: {e}") from e
            trace(name, "answer", out)
            return out
        messages.append({"role": "assistant", "content": resp.content})
        results = []
        for u in uses:
            args = u.input if isinstance(u.input, dict) else json.loads(u.input)
            try:
                result, is_error = execute(u.name, args), False
            except ToolInputError as e:
                result, is_error = {"error": str(e)}, True
            trace(name, f"tool:{u.name}", {"input": args, "output": result, "is_error": is_error})
            results.append({"type": "tool_result", "tool_use_id": u.id,
                            "content": json.dumps(result, default=str), "is_error": is_error})
        messages.append({"role": "user", "content": results})
    raise AgentError(f"{name}: no answer after {MAX_TURNS} turns")
