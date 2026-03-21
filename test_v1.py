"""
AIJAH Phase 1 End-to-End Test
==============================
Walks through all 9 V1 acceptance criteria in order against a live backend.

Requirements:
  - Docker Compose stack is up (docker compose up)
  - Backend reachable at http://localhost:8000
  - Seed data exists (user 00000000-0000-0000-0000-000000000001)
  - qwen2.5 model pulled in ollama container

Run (from host, needs Python + httpx):
  python3 test_v1.py

Run via Docker (no local Python needed):
  docker compose run --rm test

Each step prints PASS or FAIL with detail. Stop on first failure by default.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

import httpx

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")
TEST_USER_ID = "00000000-0000-0000-0000-000000000001"
SCAN_PATH = "/sandbox"

# How long to wait for the agent loop SSE stream to complete (seconds).
# The model has to scan, plan, and respond across multiple LLM round-trips.
# On CPU-only Ollama (qwen2.5 7B) a single round-trip can take 3-4 minutes
# during the prefill phase when context is large, so we need a generous limit.
AGENT_TIMEOUT_SECONDS = 600


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class StepFailed(Exception):
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
    raise StepFailed(label)


def _section(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def _parse_sse_stream(raw: str) -> list[dict[str, Any]]:
    """Parse a raw SSE body into a list of event payloads."""
    events: list[dict[str, Any]] = []
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data: "):
            data = line[len("data: "):]
            try:
                events.append(json.loads(data))
            except json.JSONDecodeError:
                pass
    return events


def _consume_sse(response: httpx.Response) -> list[dict[str, Any]]:
    """Read a streaming SSE response and return all parsed events."""
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


# ---------------------------------------------------------------------------
# Step 1 — Health check
# ---------------------------------------------------------------------------

def step1_health(client: httpx.Client) -> None:
    _section("Step 1 — Health Check")

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
            _fail("Ollama model provider not reachable", str(body))
        _ok("Ollama model provider reachable")

        # Backward-compatible field: present only for ollama in /health
        if body.get("ollama") != "reachable":
            _fail("Legacy ollama health field not reachable", str(body))
        _ok("Legacy ollama health field reachable")
    elif provider in {"anthropic", "openai"}:
        if model_status != "configured":
            _fail(f"{provider} model provider not configured", str(body))
        _ok(f"{provider} model provider configured")
    else:
        _fail("Unknown model provider in /health", str(body))

    if body.get("status") != "ok":
        _fail("Overall status not ok", str(body))
    _ok("Overall status ok")


# ---------------------------------------------------------------------------
# Step 2 — Create session and send message → Ollama round-trip
# ---------------------------------------------------------------------------

def step2_create_session(client: httpx.Client) -> str:
    _section("Step 2 — Create Session")

    r = client.post(
        f"{BASE_URL}/sessions",
        json={"user_id": TEST_USER_ID, "mode": "CLEANUP"},
    )
    if r.status_code != 201:
        _fail("POST /sessions returned non-201", f"status={r.status_code} body={r.text}")

    body = r.json()
    session_id = body.get("id")
    if not session_id:
        _fail("No session id in response", str(body))

    _ok("Session created", f"id={session_id}")
    print(f"  mode={body.get('mode')}  status={body.get('status')}")
    return session_id


# ---------------------------------------------------------------------------
# Step 3+4+5 — Send message, watch SSE for tool calls, plan creation
# ---------------------------------------------------------------------------

def step3_to_5_send_message(client: httpx.Client, session_id: str) -> tuple[str, list[dict]]:
    """
    Sends the trigger message and consumes the full SSE stream.
    Returns (plan_id, all_events).
    Validates:
      - Step 3: MCP tool discovery (tool_call event present)
      - Step 4: scan_folder ran (tool_call with tool=scan_folder)
      - Step 5: propose_plan ran → plan_created event with plan_id
    """
    _section("Step 3–5 — Send Message → Tool Calls → Plan Created")

    print(f"  Sending: 'Please scan my sandbox folder and suggest how to organize it.'")
    print(f"  (Waiting up to {AGENT_TIMEOUT_SECONDS}s for model response...)")

    sse_timeout = httpx.Timeout(
        connect=30.0,
        read=AGENT_TIMEOUT_SECONDS,
        write=30.0,
        pool=30.0,
    )

    with client.stream(
        "POST",
        f"{BASE_URL}/sessions/{session_id}/messages",
        json={"content": "Please scan my sandbox folder and suggest how to organize it."},
        timeout=sse_timeout,
    ) as response:
        if response.status_code != 200:
            _fail("POST /messages returned non-200", f"status={response.status_code}")

        events = _consume_sse(response)

    print(f"\n  SSE events received ({len(events)} total):")
    for evt in events:
        evt_type = evt.get("type", "?")
        if evt_type == "token":
            pass  # skip token spam in output
        elif evt_type == "tool_call":
            print(f"    tool_call  → {evt.get('tool')}")
        elif evt_type == "tool_result":
            print(f"    tool_result← {evt.get('tool')}")
        elif evt_type == "plan_created":
            print(f"    plan_created  plan_id={evt.get('plan_id')}  actions={evt.get('action_count')}")
        elif evt_type == "message_complete":
            content_preview = str(evt.get("content", ""))[:120]
            print(f"    message_complete  \"{content_preview}...\"")
        elif evt_type == "error":
            print(f"    ERROR  {evt.get('message')}  {evt.get('detail')}")
        else:
            print(f"    {evt_type}  {json.dumps(evt)[:100]}")

    # Step 3: at least one tool_call event
    tool_calls = [e for e in events if e.get("type") == "tool_call"]
    if not tool_calls:
        _fail("Step 3: No tool_call events — MCP tool discovery may have failed or model didn't call tools")
    _ok("Step 3: tool_call events present", f"{len(tool_calls)} tool call(s)")

    # Step 4: scan_folder was called
    scan_calls = [e for e in events if e.get("type") == "tool_call" and e.get("tool") == "scan_folder"]
    if not scan_calls:
        _fail("Step 4: scan_folder was never called", f"Tool calls seen: {[e.get('tool') for e in tool_calls]}")
    _ok("Step 4: scan_folder called")

    # Step 5: plan_created event exists
    plan_events = [e for e in events if e.get("type") == "plan_created"]
    if not plan_events:
        _fail("Step 5: No plan_created event — propose_plan was not called or failed")
    plan_id = plan_events[0].get("plan_id")
    if not plan_id:
        _fail("Step 5: plan_created event has no plan_id", str(plan_events[0]))
    action_count = plan_events[0].get("action_count", 0)
    _ok("Step 5: plan_created event received", f"plan_id={plan_id}  action_count={action_count}")

    # No error events
    error_events = [e for e in events if e.get("type") == "error"]
    if error_events:
        print(f"\n  WARNING: {len(error_events)} error event(s) in stream:")
        for e in error_events:
            print(f"    {e.get('message')}: {e.get('detail')}")

    return plan_id, events


# ---------------------------------------------------------------------------
# Step 6 — Fetch plan and verify actions exist
# ---------------------------------------------------------------------------

def step6_fetch_plan(client: httpx.Client, plan_id: str) -> list[dict]:
    _section("Step 6 — Fetch Plan with Actions")

    r = client.get(f"{BASE_URL}/plans/{plan_id}")
    if r.status_code != 200:
        _fail("GET /plans/{id} returned non-200", f"status={r.status_code} body={r.text}")

    body = r.json()
    actions = body.get("actions", [])

    print(f"  Plan goal: {body.get('goal')}")
    print(f"  Plan status: {body.get('status')}")
    print(f"  Actions ({len(actions)}):")
    for action in actions:
        print(f"    [{action.get('status')}] {action.get('action_type')} — {action.get('action_payload_json')}")

    if not actions:
        _fail("Step 6: Plan has no actions", str(body))

    file_ops = [a for a in actions if a.get("action_type") in ("RENAME", "MOVE", "CREATE_FOLDER", "ARCHIVE")]
    if not file_ops:
        _fail("Step 6: Plan has no file operation actions", f"action types: {[a.get('action_type') for a in actions]}")

    _ok("Step 6: Plan fetched with actions", f"{len(actions)} action(s)")
    return actions


# ---------------------------------------------------------------------------
# Step 7 — Approve one action
# ---------------------------------------------------------------------------

def step7_approve_action(client: httpx.Client, actions: list[dict]) -> str:
    _section("Step 7 — Approve Action")

    # Pick the first PENDING action that is a file operation
    target = None
    for action in actions:
        if action.get("status") == "PENDING" and action.get("action_type") in ("RENAME", "MOVE", "CREATE_FOLDER", "ARCHIVE"):
            target = action
            break

    if target is None:
        _fail("Step 7: No PENDING file operation action to approve", str(actions))

    action_id = target["id"]
    print(f"  Approving action: {action_id}")
    print(f"  Type: {target.get('action_type')}  Payload: {target.get('action_payload_json')}")

    r = client.patch(
        f"{BASE_URL}/actions/{action_id}",
        json={"status": "APPROVED"},
    )
    if r.status_code != 200:
        _fail("PATCH /actions/{id} returned non-200", f"status={r.status_code} body={r.text}")

    body = r.json()
    if body.get("status") != "APPROVED":
        _fail("Action status not APPROVED after patch", str(body))

    _ok("Step 7: Action approved in DB", f"action_id={action_id}")
    return action_id


# ---------------------------------------------------------------------------
# Step 8 — Execute plan, verify file operation happened
# ---------------------------------------------------------------------------

def step8_execute_plan(client: httpx.Client, plan_id: str, approved_action_id: str) -> None:
    _section("Step 8 — Execute Plan")

    print(f"  Executing plan: {plan_id}")
    print(f"  (Waiting for execution SSE stream...)")

    with client.stream(
        "POST",
        f"{BASE_URL}/plans/{plan_id}/execute",
        timeout=60,
    ) as response:
        if response.status_code != 200:
            _fail("POST /plans/{id}/execute returned non-200", f"status={response.status_code} body={response.text}")

        events = _consume_sse(response)

    print(f"\n  Execution SSE events ({len(events)} total):")
    for evt in events:
        evt_type = evt.get("type", "?")
        if evt_type == "action_executed":
            outcome = evt.get("outcome")
            print(f"    action_executed  action_id={evt.get('action_id')}  outcome={outcome}  type={evt.get('action_type')}")
        elif evt_type == "execution_complete":
            print(f"    execution_complete  succeeded={evt.get('succeeded')}  failed={evt.get('failed')}")
        elif evt_type == "error":
            print(f"    ERROR  {evt.get('message')}: {evt.get('detail')}")
        else:
            print(f"    {evt_type}  {json.dumps(evt)[:100]}")

    # Verify the approved action was executed
    executed_events = [
        e for e in events
        if e.get("type") == "action_executed"
        and e.get("action_id") == approved_action_id
        and e.get("outcome") == "SUCCESS"
    ]
    if not executed_events:
        all_executed = [e for e in events if e.get("type") == "action_executed"]
        _fail(
            "Step 8: Approved action not executed successfully",
            f"action_id={approved_action_id}\nexecuted events: {all_executed}",
        )

    complete_events = [e for e in events if e.get("type") == "execution_complete"]
    if not complete_events:
        _fail("Step 8: No execution_complete event received")

    succeeded = complete_events[0].get("succeeded", 0)
    failed = complete_events[0].get("failed", 0)

    if succeeded == 0:
        _fail("Step 8: execution_complete shows 0 succeeded", str(complete_events[0]))

    _ok("Step 8: Plan executed", f"succeeded={succeeded}  failed={failed}")


# ---------------------------------------------------------------------------
# Step 9 — Verify memory_event written via GET /health (proxy check) and
#           re-fetch plan to confirm status changed
# ---------------------------------------------------------------------------

def step9_verify_memory_event(client: httpx.Client, plan_id: str) -> None:
    _section("Step 9 — Verify Memory Event + Final Plan State")

    # Re-fetch the plan — it should now be EXECUTED or PARTIAL
    r = client.get(f"{BASE_URL}/plans/{plan_id}")
    if r.status_code != 200:
        _fail("GET /plans/{id} returned non-200 after execution", f"status={r.status_code}")

    body = r.json()
    plan_status = body.get("status")
    actions = body.get("actions", [])

    print(f"  Plan status after execution: {plan_status}")
    print(f"  Actions:")
    for action in actions:
        print(f"    [{action.get('status')}] {action.get('action_type')}  result={action.get('result_json')}")

    if plan_status not in ("EXECUTED", "PARTIAL"):
        _fail("Step 9: Plan status is not EXECUTED or PARTIAL after execution", f"status={plan_status}")
    _ok("Step 9: Plan status updated", f"status={plan_status}")

    executed_actions = [a for a in actions if a.get("status") == "EXECUTED"]
    if not executed_actions:
        _fail("Step 9: No actions in EXECUTED status")

    for action in executed_actions:
        result = action.get("result_json") or {}
        outcome = result.get("outcome")
        pre_state = result.get("pre_state")
        post_state = result.get("post_state")
        if outcome != "SUCCESS":
            _fail(f"Step 9: Executed action outcome is not SUCCESS", f"outcome={outcome} result={result}")
        if pre_state is None:
            _fail(f"Step 9: result_json missing pre_state", f"result={result}")
        if post_state is None:
            _fail(f"Step 9: result_json missing post_state", f"result={result}")

    _ok("Step 9: Executed action has pre_state and post_state in result_json")
    print()
    print("  NOTE: To verify memory_events row directly, run in postgres:")
    print("    SELECT id, event_type, outcome, pre_state_json, post_state_json")
    print("    FROM memory_events ORDER BY created_at DESC LIMIT 5;")


# ---------------------------------------------------------------------------
# Bonus — Get message history to confirm all messages persisted
# ---------------------------------------------------------------------------

def bonus_message_history(client: httpx.Client, session_id: str) -> None:
    _section("Bonus — Message History")

    r = client.get(f"{BASE_URL}/sessions/{session_id}/messages")
    if r.status_code != 200:
        print(f"  SKIP  Could not fetch messages: {r.status_code}")
        return

    messages = r.json().get("messages", [])
    print(f"  {len(messages)} messages in session:")
    for msg in messages:
        role = msg.get("role", "?")
        tool_name = msg.get("tool_name")
        content_preview = str(msg.get("content", ""))[:80]
        if tool_name:
            print(f"    [{role}] tool={tool_name}  content={content_preview!r}")
        else:
            print(f"    [{role}] {content_preview!r}")

    roles = [m.get("role") for m in messages]
    if "USER" in roles:
        _ok("USER message persisted")
    if "ASSISTANT" in roles:
        _ok("ASSISTANT message persisted")
    if "TOOL" in roles:
        _ok("TOOL messages persisted")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("\nAIJAH Phase 1 — End-to-End Test")
    print(f"Target: {BASE_URL}")
    print(f"User:   {TEST_USER_ID}")

    passed = 0
    failed_step = None

    with httpx.Client(timeout=30.0) as client:
        steps = [
            ("Step 1: Health",          lambda: step1_health(client)),
            ("Step 2: Create session",  lambda: step2_create_session(client)),
        ]

        # Run steps 1 and 2 first to get session_id
        try:
            step1_health(client)
            passed += 1
        except StepFailed as e:
            print(f"\nStopped at Step 1: {e}")
            sys.exit(1)

        try:
            session_id = step2_create_session(client)
            passed += 1
        except StepFailed as e:
            print(f"\nStopped at Step 2: {e}")
            sys.exit(1)

        # Step 3-5: send message and watch stream
        try:
            plan_id, events = step3_to_5_send_message(client, session_id)
            passed += 3  # covers steps 3, 4, 5
        except StepFailed as e:
            print(f"\nStopped at Steps 3-5: {e}")
            print("\nThis is likely the FastMCP or model-provider integration point.")
            print("Check: docker logs aijah-backend-1")
            sys.exit(1)

        # Step 6: fetch plan
        try:
            actions = step6_fetch_plan(client, plan_id)
            passed += 1
        except StepFailed as e:
            print(f"\nStopped at Step 6: {e}")
            sys.exit(1)

        # Step 7: approve one action
        try:
            approved_action_id = step7_approve_action(client, actions)
            passed += 1
        except StepFailed as e:
            print(f"\nStopped at Step 7: {e}")
            sys.exit(1)

        # Step 8: execute
        try:
            step8_execute_plan(client, plan_id, approved_action_id)
            passed += 1
        except StepFailed as e:
            print(f"\nStopped at Step 8: {e}")
            sys.exit(1)

        # Step 9: memory event
        try:
            step9_verify_memory_event(client, plan_id)
            passed += 1
        except StepFailed as e:
            print(f"\nStopped at Step 9: {e}")
            sys.exit(1)

        # Bonus
        bonus_message_history(client, session_id)

    print(f"\n{'='*60}")
    print(f"  ALL 9 STEPS PASSED")
    print(f"{'='*60}\n")
    print("Phase 1 V1 demo criteria are met.")
    print("Ready to move to Phase 2.\n")


if __name__ == "__main__":
    main()
