from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from tools.execute_action import execute_action
from tools.get_task_state import get_task_state
from tools.propose_plan import propose_plan
from tools.read_file_metadata import read_file_metadata
from tools.scan_folder import scan_folder
from tools.update_task_state import update_task_state


# Thin MCP wrapper: registration lives here, tool logic stays in tools/*.py.
mcp = FastMCP(
    name="AIJAH",
    instructions=(
        "You are the AIJAH Phase 1 MCP server. "
        "All filesystem actions must stay inside SANDBOX_ROOT. "
        "Plans must be proposed before execution, and execution only applies to APPROVED actions."
    ),
    stateless_http=True,
)


@mcp.tool(
    name="scan_folder",
    description="Scan a directory inside SANDBOX_ROOT and write file/folder metadata into the database.",
)
async def scan_folder_tool(path: str, recursive: bool = True, session_id: str = "") -> dict[str, Any]:
    return await scan_folder(path=path, recursive=recursive, session_id=session_id)


@mcp.tool(
    name="read_file_metadata",
    description="Read metadata for a single file inside SANDBOX_ROOT without reading file contents.",
)
async def read_file_metadata_tool(path: str) -> dict[str, Any]:
    return await read_file_metadata(path=path)


@mcp.tool(
    name="propose_plan",
    description="Write a proposed plan and its actions to the database, then return the new plan ID.",
)
async def propose_plan_tool(
    session_id: str,
    goal: str,
    rationale_summary: str,
    actions: list[dict[str, Any]],
) -> dict[str, Any]:
    return await propose_plan(
        session_id=session_id,
        goal=goal,
        rationale_summary=rationale_summary,
        actions=actions,
    )


@mcp.tool(
    name="execute_action",
    description="Execute a single APPROVED plan action, then write the result and memory event to the database.",
)
async def execute_action_tool(action_id: str) -> dict[str, Any]:
    return await execute_action(action_id=action_id)


@mcp.tool(
    name="get_task_state",
    description="Read the current working-memory state for a session.",
)
async def get_task_state_tool(session_id: str) -> dict[str, Any]:
    return await get_task_state(session_id=session_id)


@mcp.tool(
    name="update_task_state",
    description="Update the current working-memory state for a session.",
)
async def update_task_state_tool(
    session_id: str,
    goal: str | None = None,
    current_step: str | None = None,
    active_plan_id: str | None = None,
    scratchpad_summary: str | None = None,
) -> dict[str, Any]:
    return await update_task_state(
        session_id=session_id,
        goal=goal,
        current_step=current_step,
        active_plan_id=active_plan_id,
        scratchpad_summary=scratchpad_summary,
    )


mcp_http_app = mcp.streamable_http_app()
