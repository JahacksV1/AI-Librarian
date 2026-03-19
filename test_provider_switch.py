"""
AIJAH Provider Smoke Test
=========================
Quick smoke test focused on provider boot + first model/tool round-trip.

Use this for fast validation when switching MODEL_PROVIDER in .env.
It intentionally stops before action approval/execution flows.
"""

from __future__ import annotations

import json
import sys
from typing import Any

import httpx

BASE_URL = "http://localhost:8000"
TEST_USER_ID = "00000000-0000-0000-0000-000000000001"
SMOKE_TIMEOUT_SECONDS = 180


class SmokeFailed(Exception):
    pass


def _ok(label: str, detail: str = "") -> None:
    msg = f"  PASS  {label}"
    if detail:
        msg += f"  ({detail})"
    print(msg)


def _fail(label: str, detail: str = "") -> None:
    msg = f"  FAIL  {label}"
    if detail:
        msg += f"\n        {detail}"
    print(msg)
    raise SmokeFailed(label)


def _section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def _consume_sse(response: httpx.Response) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in response.iter_lines():
        line = line.strip()
        if line.startswith("data: "):
            data = line[len("data: "):]
            try:
                events.append(json.loads(data))
            except json.JSONDecodeError:
                pass
    return events


def step1_health(client: httpx.Client) -> str:
    _section("Step 1 — Provider Health")
    r = client.get(f"{BASE_URL}/health")
    if r.status_code != 200:
        _fail("GET /health returned non-200", f"status={r.status_code} body={r.text}")

    body = r.json()
    print(f"  Response: {json.dumps(body, indent=2)}")

    if body.get("db") != "connected":
        _fail("DB not connected", str(body))
    _ok("DB connected")

    provider = str(body.get("model_provider", "")).lower()
    model_name = str(body.get("model_name", ""))
    model_status = str(body.get("model_status", ""))
    print(f"  Provider: {provider or '(unknown)'}  model={model_name or '(unknown)'}  status={model_status or '(unknown)'}")

    if provider == "ollama":
        if model_status != "reachable":
            _fail("Ollama provider not reachable", str(body))
    elif provider in {"anthropic", "openai"}:
        if model_status != "configured":
            _fail(f"{provider} provider not configured", str(body))
    else:
        _fail("Unknown model provider", str(body))
    _ok("Provider health contract valid")

    if body.get("status") != "ok":
        _fail("Overall status not ok", str(body))
    _ok("Overall status ok")
    return provider


def step2_first_model_round_trip(client: httpx.Client) -> None:
    _section("Step 2 — First Model Round-Trip")

    r = client.post(
        f"{BASE_URL}/sessions",
        json={"user_id": TEST_USER_ID, "mode": "CLEANUP"},
    )
    if r.status_code != 201:
        _fail("POST /sessions returned non-201", f"status={r.status_code} body={r.text}")
    session_id = r.json().get("id")
    if not session_id:
        _fail("No session id in response", str(r.json()))
    _ok("Session created", session_id)

    timeout = httpx.Timeout(connect=30.0, read=SMOKE_TIMEOUT_SECONDS, write=30.0, pool=30.0)
    with client.stream(
        "POST",
        f"{BASE_URL}/sessions/{session_id}/messages",
        json={"content": "Please scan my sandbox folder and suggest how to organize it."},
        timeout=timeout,
    ) as response:
        if response.status_code != 200:
            _fail("POST /messages returned non-200", f"status={response.status_code}")
        events = _consume_sse(response)

    if not events:
        _fail("No SSE events returned", "Model call likely failed before streaming started.")

    errors = [e for e in events if e.get("type") == "error"]
    if errors:
        _fail("Error event received", json.dumps(errors[0], ensure_ascii=True))

    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    if not tool_calls:
        _fail("No tool_call events", "Provider did not complete tool-call round-trip.")
    _ok("Tool-call round-trip works", f"{len(tool_calls)} tool_call event(s)")


def main() -> None:
    print("\nAIJAH Provider Smoke Test")
    print(f"Target: {BASE_URL}")
    with httpx.Client(timeout=30.0) as client:
        step1_health(client)
        step2_first_model_round_trip(client)

    print(f"\n{'='*60}")
    print("  PROVIDER SMOKE PASSED")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    try:
        main()
    except SmokeFailed:
        sys.exit(1)
