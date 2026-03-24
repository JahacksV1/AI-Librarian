#!/usr/bin/env bash
# start-mcp.sh — Start the AIJAH MCP server natively on Mac or Linux
#
# Run this once before (or alongside) docker compose up.
# The MCP server must run natively so it can access your local filesystem.
#
# Usage:
#   chmod +x scripts/start-mcp.sh
#   ./scripts/start-mcp.sh
#
# To scan your real files instead of the sandbox, update SANDBOX_ROOT in .env:
#   SANDBOX_ROOT=/Users/<you>

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"
VENV_PYTHON="$PROJECT_ROOT/.venv/bin/python"

# Verify the virtual environment exists.
if [[ ! -x "$VENV_PYTHON" ]]; then
    echo "ERROR: Virtual environment not found at $VENV_PYTHON"
    echo "Run: python3 -m venv .venv && .venv/bin/pip install -r backend/requirements.txt"
    exit 1
fi

echo "Starting AIJAH MCP server on port 8001..."
echo "  Backend dir : $BACKEND_DIR"
echo "  Python      : $VENV_PYTHON"
echo ""
echo "Press Ctrl+C to stop."
echo ""

# Run from the backend directory so that relative imports resolve correctly.
cd "$BACKEND_DIR"
exec "$VENV_PYTHON" mcp_server.py
