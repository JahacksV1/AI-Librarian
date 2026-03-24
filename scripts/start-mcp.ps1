# start-mcp.ps1 — Start the AIJAH MCP server natively on Windows
#
# Run this once before (or alongside) docker compose up.
# The MCP server must run natively so it can access your local filesystem.
#
# Usage:
#   .\scripts\start-mcp.ps1
#
# To scan your real files instead of the sandbox, update SANDBOX_ROOT in .env:
#   SANDBOX_ROOT=C:/Users/<you>

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackendDir  = Join-Path $ProjectRoot "backend"
$VenvPython  = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

# Verify the virtual environment exists.
if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtual environment not found at $VenvPython`nRun: python -m venv .venv && .venv\Scripts\pip install -r backend\requirements.txt"
    exit 1
}

# Check if port 8001 is already in use and give a clear message.
$existing = Get-NetTCPConnection -LocalPort 8001 -ErrorAction SilentlyContinue | Select-Object -First 1
if ($existing) {
    $pid8001 = $existing.OwningProcess
    Write-Warning "Port 8001 is already in use by PID $pid8001."
    Write-Host "To kill it: Stop-Process -Id $pid8001 -Force" -ForegroundColor Yellow
    exit 1
}

Write-Host "Starting AIJAH MCP server on port 8001..." -ForegroundColor Cyan
Write-Host "  Backend dir : $BackendDir"
Write-Host "  Python      : $VenvPython"
Write-Host ""
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow
Write-Host ""

# Run from the backend directory so that relative imports resolve correctly.
Set-Location $BackendDir
& $VenvPython mcp_server.py
