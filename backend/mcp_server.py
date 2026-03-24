from __future__ import annotations

from typing import Any

from fastmcp import FastMCP
from starlette.responses import JSONResponse

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
)


@mcp.tool(
    name="scan_folder",
    description=(
        "Scan a directory inside SANDBOX_ROOT and write file/folder metadata into the database. "
        "Choose scan_depth based on what you need:\n"
        "  ROOT    — immediate children only, no file content. Fast. Use first to orient: "
        "            'what folders exist here and how big are they?'\n"
        "  DEEP    — full recursive walk, all file metadata (name, size, date, category). "
        "            No content reading. The full inventory without opening files.\n"
        "  CONTENT — same as DEEP plus text previews from supported file types. "
        "            Slower. Use when you need to understand what is inside specific files.\n"
        "Always start with ROOT on an unfamiliar path, then decide where to go DEEP or CONTENT."
    ),
)
async def scan_folder_tool(
    path: str,
    session_id: str = "",
    scan_depth: str = "DEEP",
    recursive: bool = True,
) -> dict[str, Any]:
    return await scan_folder(
        path=path,
        recursive=recursive,
        session_id=session_id,
        scan_depth=scan_depth,
    )


@mcp.tool(
    name="read_file_metadata",
    description="Read metadata for a single file inside SANDBOX_ROOT without reading file contents.",
)
async def read_file_metadata_tool(path: str) -> dict[str, Any]:
    return await read_file_metadata(path=path)


@mcp.tool(
    name="propose_plan",
    description=(
        "Create a file reorganization plan. Call this AFTER scan_folder. "
        "Each action in the actions list must be a dict with these keys: "
        "action_type (one of: RENAME, MOVE, CREATE_FOLDER, ARCHIVE, CLASSIFY), "
        "target_type ('file' or 'folder'), "
        "target_path (absolute path of the target), "
        "action_payload (dict with operation-specific fields: "
        "RENAME/MOVE need 'from_path' and 'to_path'; "
        "CREATE_FOLDER needs 'path'; "
        "ARCHIVE needs 'from_path'). "
        "All paths must be absolute and inside the sandbox root."
    ),
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


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Any) -> JSONResponse:
    """Docker healthcheck endpoint."""
    return JSONResponse({"status": "ok", "service": "mcp-server"})


# For in-process use (backend when MCP_URL is unset) and ASGI deployment
mcp_http_app = mcp.http_app(stateless_http=True)


if __name__ == "__main__":
    # Standalone HTTP server for Docker extraction. Serves at http://0.0.0.0:8001/mcp
    mcp.run(transport="http", host="0.0.0.0", port=8001)
