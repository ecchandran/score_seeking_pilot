"""Stage 0 access and reasoning probes. Costs real money (expected well under $1).

  python -m src.check_access                     # all models in configs/stage1_pilot.yaml
  python -m src.check_access --models gpt-5.5 o3
  python -m src.check_access --probe-flex        # also one tiny Flex call per OpenAI model

Per OpenAI model:
  - is the ID listed by GET /v1/models?
  - one Responses call with a dummy tool and reasoning.summary=auto:
    did a function_call come back? a non-empty summary? encrypted_content?
  - attestation probe: tool output + user question with tool_choice="none".
Per OpenRouter model:
  - list endpoints/providers for the model (GET /api/v1/models/{id}/endpoints)
  - one tool-calling request with reasoning, pinned to one provider, fallbacks off:
    was reasoning / reasoning_details returned? which provider served it?
  - the same attestation probe.

Writes runs/stage0_access/access.json and access_table.md. Never prints keys.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

import urllib.request

import yaml
from dotenv import load_dotenv

from . import providers
from .harness import ATTESTATION_TEXT
from .run import RUNS, write_json_atomic

REPO = Path(__file__).resolve().parent.parent
OUT_DIR = RUNS / "stage0_access"

DUMMY_TOOL = {
    "name": "get_weather",
    "description": "Get the current weather for a city.",
    "parameters": {"type": "object", "properties": {"city": {"type": "string"}},
                   "required": ["city"], "additionalProperties": False},
}
PROBE_USER = "What is the weather in Paris right now? Use the tool."
PROBE_TOOL_OUTPUT = "Paris: 12°C, light rain."
MAX_OUT = 4000


def _err(e: BaseException) -> str:
    code = getattr(e, "status_code", None)
    return f"{type(e).__name__}{f' {code}' if code else ''}: {str(e)[:300]}"


async def probe_openai(client, model: str, listed: set[str], probe_flex: bool) -> dict:
    r: dict = {"model": model, "provider": "openai", "listed_in_models": model in listed,
               "cost_usd": 0.0}
    tools = [{"type": "function", **DUMMY_TOOL}]
    items: list = [{"role": "developer", "content": "You are a helpful assistant."},
                   {"role": "user", "content": PROBE_USER}]
    try:
        resp = await client.responses.create(
            model=model, input=items, tools=tools, store=False,
            reasoning={"effort": "medium", "summary": "auto"},
            include=["reasoning.encrypted_content"], max_output_tokens=MAX_OUT)
        out = [it.to_dict() for it in resp.output]
        calls, _, summary = providers.parse_responses_output(out)
        u = providers.normalize_responses_usage(resp.usage.to_dict() if resp.usage else {})
        r["cost_usd"] += providers.cost_usd(model, u)
        r.update({
            "access": True,
            "tool_call": bool(calls),
            "reasoning_items": sum(it.get("type") == "reasoning" for it in out),
            "summary_nonempty": bool(summary.strip()),
            "summary_excerpt": summary[:300],
            "encrypted_content": any(it.get("encrypted_content") for it in out
                                     if it.get("type") == "reasoning"),
            "effective_reasoning": resp.reasoning.to_dict() if resp.reasoning else None,
            "service_tier": getattr(resp, "service_tier", None),
            "output_item_keys": sorted({k for it in out for k in it}),
            "usage": u,
        })
        if calls:
            items += out
            items.append({"type": "function_call_output", "call_id": calls[0].call_id,
                          "output": PROBE_TOOL_OUTPUT})
            items.append({"role": "user", "content": ATTESTATION_TEXT})
            try:
                resp2 = await client.responses.create(
                    model=model, input=items, tools=tools, tool_choice="none", store=False,
                    reasoning={"effort": "medium", "summary": "auto"},
                    include=["reasoning.encrypted_content"], max_output_tokens=MAX_OUT)
                out2 = [it.to_dict() for it in resp2.output]
                calls2, text2, summ2 = providers.parse_responses_output(out2)
                u2 = providers.normalize_responses_usage(resp2.usage.to_dict() if resp2.usage else {})
                r["cost_usd"] += providers.cost_usd(model, u2)
                r.update({"attestation_ok": bool(text2.strip()) and not calls2,
                          "attestation_raw": text2[:200],
                          "attestation_tool_calls": len(calls2),
                          "attestation_summary_nonempty": bool(summ2.strip())})
            except Exception as e:  # noqa: BLE001
                r.update({"attestation_ok": False, "attestation_error": _err(e)})
    except Exception as e:  # noqa: BLE001
        r.update({"access": False, "error": _err(e),
                  "blocked_by_provider": providers.is_provider_block(e)})

    if probe_flex and r.get("access"):
        try:
            resp = await client.responses.create(
                model=model, input="Reply with the word ok.", store=False,
                reasoning={"effort": "low"}, max_output_tokens=500, service_tier="flex")
            u = providers.normalize_responses_usage(resp.usage.to_dict() if resp.usage else {})
            r["cost_usd"] += providers.cost_usd(model, u) * 0.5
            r["flex"] = {"ok": True, "service_tier": getattr(resp, "service_tier", None)}
        except Exception as e:  # noqa: BLE001
            r["flex"] = {"ok": False, "error": _err(e)}
    return r


def _get_json(url: str, key: str) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


async def list_openrouter_endpoints(key: str, model: str) -> list[dict]:
    url = f"{providers.OPENROUTER_BASE_URL}/models/{model}/endpoints"
    data = (await asyncio.to_thread(_get_json, url, key)).get("data", {})
    eps = data.get("endpoints", []) if isinstance(data, dict) else []
    return [{"provider_name": e.get("provider_name"), "tag": e.get("tag"),
             "supported_parameters": e.get("supported_parameters"),
             "pricing": e.get("pricing"), "context_length": e.get("context_length")}
            for e in eps]


def choose_pin(endpoints: list[dict]) -> str | None:
    for e in endpoints:
        sp = e.get("supported_parameters") or []
        if "tools" in sp and ("reasoning" in sp or "include_reasoning" in sp):
            return e.get("provider_name")
    return endpoints[0]["provider_name"] if endpoints else None


async def probe_openrouter(client, key: str, model: str, pin: str | None) -> dict:
    r: dict = {"model": model, "provider": "openrouter", "cost_usd": 0.0}
    try:
        eps = await list_openrouter_endpoints(key, model)
        r["endpoints"] = eps
    except Exception as e:  # noqa: BLE001
        eps = []
        r["endpoints_error"] = _err(e)
    pin = pin or choose_pin(eps)
    r["provider_pin"] = pin
    adapter = providers.OpenRouterChatAdapter(client, model, provider_pin=pin, max_tokens=MAX_OUT)
    tools = [{"type": "function", "function": DUMMY_TOOL}]
    msgs: list = [{"role": "system", "content": "You are a helpful assistant."},
                  {"role": "user", "content": PROBE_USER}]
    try:
        resp = await client.chat.completions.create(model=model, messages=msgs, tools=tools,
                                                    max_tokens=MAX_OUT, extra_body=adapter.extra_body())
        d = resp.to_dict()
        msg = d["choices"][0]["message"]
        u = providers.normalize_chat_usage(d.get("usage") or {})
        r["cost_usd"] += providers.cost_usd(model, u)
        r.update({
            "access": True,
            "tool_call": bool(msg.get("tool_calls")),
            "reasoning_field": bool(msg.get("reasoning")),
            "reasoning_details": bool(msg.get("reasoning_details")),
            "reasoning_detail_types": sorted({x.get("type", "?") for x in msg.get("reasoning_details") or []}),
            "reasoning_excerpt": providers.chat_reasoning_text(msg)[:300],
            "served_by": d.get("provider"),
            "message_keys": sorted(msg.keys()),
            "response_keys": sorted(d.keys()),
            "usage_raw": d.get("usage"),
        })
        if msg.get("tool_calls"):
            msgs.append(msg)
            msgs.append({"role": "tool", "tool_call_id": msg["tool_calls"][0]["id"],
                         "content": PROBE_TOOL_OUTPUT})
            msgs.append({"role": "user", "content": ATTESTATION_TEXT})
            try:
                # same shape as the adapter's attestation call: no tools sent
                resp2 = await client.chat.completions.create(
                    model=model, messages=msgs, max_tokens=MAX_OUT,
                    extra_body=adapter.extra_body())
                d2 = resp2.to_dict()
                m2 = d2["choices"][0]["message"]
                u2 = providers.normalize_chat_usage(d2.get("usage") or {})
                r["cost_usd"] += providers.cost_usd(model, u2)
                r.update({"attestation_ok": bool((m2.get("content") or "").strip())
                          and not m2.get("tool_calls"),
                          "attestation_raw": (m2.get("content") or "")[:200],
                          "attestation_tool_calls": len(m2.get("tool_calls") or []),
                          "attestation_served_by": d2.get("provider")})
            except Exception as e:  # noqa: BLE001
                r.update({"attestation_ok": False, "attestation_error": _err(e)})
    except Exception as e:  # noqa: BLE001
        r.update({"access": False, "error": _err(e)})
    return r


def reasoning_visible(r: dict) -> str:
    if r["provider"] == "openai":
        return "summary" if r.get("summary_nonempty") else "none"
    if r.get("reasoning_field") or r.get("reasoning_details"):
        return "raw"
    return "none"


def table(results: list[dict]) -> str:
    yn = lambda x: "yes" if x else ("no" if x is not None else "–")  # noqa: E731
    lines = ["| Model | Access | Tool call | Reasoning visible | Attestation call | Served by | Probe cost |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in results:
        lines.append(f"| `{r['model']}` | {yn(r.get('access'))} | {yn(r.get('tool_call'))} | "
                     f"{reasoning_visible(r)} | {yn(r.get('attestation_ok'))} | "
                     f"{r.get('served_by') or ('OpenAI' if r['provider'] == 'openai' else '–')} | "
                     f"${r['cost_usd']:.4f} |")
    return "\n".join(lines) + "\n"


async def amain(args) -> None:
    load_dotenv(REPO / ".env")
    cfg = yaml.safe_load((REPO / "configs" / "stage1_pilot.yaml").read_text())
    models = [m for m in cfg["models"] if not args.models or m["name"] in args.models]
    from openai import AsyncOpenAI

    results = []
    oa = [m for m in models if m["provider"] == "openai"]
    orr = [m for m in models if m["provider"] == "openrouter"]
    if oa:
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise SystemExit("OPENAI_API_KEY missing from .env")
        client = AsyncOpenAI(api_key=key, max_retries=3, timeout=900)
        listed = set()
        try:
            async for m in client.models.list():
                listed.add(m.id)
        except Exception as e:  # noqa: BLE001
            print(f"models.list failed: {_err(e)}")
        results += await asyncio.gather(*[probe_openai(client, m["name"], listed, args.probe_flex)
                                          for m in oa])
    if orr:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise SystemExit("OPENROUTER_API_KEY missing from .env")
        client = AsyncOpenAI(api_key=key, base_url=providers.OPENROUTER_BASE_URL,
                             max_retries=3, timeout=900)
        results += await asyncio.gather(*[probe_openrouter(client, key, m["name"],
                                                           m.get("provider_pin")) for m in orr])

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_json_atomic(OUT_DIR / "access.json", results)
    md = table(results)
    (OUT_DIR / "access_table.md").write_text(md)
    print(md)
    print(f"total probe cost ≈ ${sum(r['cost_usd'] for r in results):.4f}")
    print(f"details: {OUT_DIR / 'access.json'}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*")
    ap.add_argument("--probe-flex", action="store_true")
    asyncio.run(amain(ap.parse_args()))


if __name__ == "__main__":
    main()
