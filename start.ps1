#!/usr/bin/env pwsh
<#
.SYNOPSIS
    AIJAH dev startup script.
    Starts everything in the right order and verifies each service is healthy.

.USAGE
    From the project root:
        .\start.ps1           # Start everything
        .\start.ps1 -Stop     # Stop everything
        .\start.ps1 -Status   # Check status without starting

.SERVICES
    1. Docker (postgres + backend + frontend)   ports 5433, 8000, 3003
    2. Native MCP server                         port  8001  (needs host filesystem access)
    3. Health check                              verifies all services are up
#>

param(
    [switch]$Stop,
    [switch]$Status,
    [switch]$SkipFrontend
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$BackendDir  = Join-Path $ProjectRoot "backend"
$VenvPython  = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

$MCP_PORT     = 8001
$BACKEND_PORT = 8000
$FRONTEND_PORT = 3003

# ─── Helpers ────────────────────────────────────────────────────────────────

function Write-Step([string]$msg) {
    Write-Host "`n  >> $msg" -ForegroundColor Cyan
}

function Write-Ok([string]$msg) {
    Write-Host "  OK  $msg" -ForegroundColor Green
}

function Write-Warn([string]$msg) {
    Write-Host "  !!  $msg" -ForegroundColor Yellow
}

function Write-Fail([string]$msg) {
    Write-Host "  XX  $msg" -ForegroundColor Red
}

function Test-Port([int]$port, [int]$timeoutMs = 2000) {
    try {
        $tcp = [System.Net.Sockets.TcpClient]::new()
        $task = $tcp.ConnectAsync("localhost", $port)
        $done = $task.Wait($timeoutMs)
        $tcp.Close()
        return $done -and $task.Status -eq "RanToCompletion"
    } catch {
        return $false
    }
}

function Wait-ForPort([int]$port, [string]$label, [int]$maxSeconds = 30) {
    Write-Host "     Waiting for $label on :$port" -NoNewline
    for ($i = 0; $i -lt $maxSeconds; $i++) {
        if (Test-Port $port) {
            Write-Host " ready" -ForegroundColor Green
            return $true
        }
        Write-Host "." -NoNewline
        Start-Sleep -Seconds 1
    }
    Write-Host " TIMEOUT" -ForegroundColor Red
    return $false
}

function Get-McpPid {
    $procs = Get-NetTCPConnection -LocalPort $MCP_PORT -ErrorAction SilentlyContinue |
             Where-Object { $_.State -eq "Listen" }
    if ($procs) { return $procs[0].OwningProcess }
    return $null
}

# ─── Status ─────────────────────────────────────────────────────────────────

function Show-Status {
    Write-Host "`nAIJAH Service Status" -ForegroundColor White
    Write-Host "────────────────────────────────────" -ForegroundColor DarkGray

    # Docker
    $dockerPs = docker compose ps --format json 2>$null | ConvertFrom-Json -ErrorAction SilentlyContinue
    @("postgres", "backend", "frontend") | ForEach-Object {
        $name = $_
        $svc  = $dockerPs | Where-Object { $_.Service -eq $name }
        if ($svc -and $svc.Status -match "Up") {
            Write-Ok "Docker $name   ($($svc.Status))"
        } else {
            Write-Warn "Docker $name   not running"
        }
    }

    # MCP server
    $mcpPid = Get-McpPid
    if ($mcpPid) {
        Write-Ok "MCP server     :$MCP_PORT  (pid $mcpPid)"
    } else {
        Write-Warn "MCP server     not running on :$MCP_PORT"
    }

    # Health endpoint
    try {
        $h = Invoke-RestMethod "http://localhost:$BACKEND_PORT/health" -TimeoutSec 3
        Write-Ok "Backend health  status=$($h.status)  db=$($h.db)  model=$($h.model_status)"
    } catch {
        Write-Warn "Backend health  not reachable"
    }

    Write-Host ""
}

# ─── Stop ───────────────────────────────────────────────────────────────────

if ($Stop) {
    Write-Step "Stopping MCP server"
    $mcpPid = Get-McpPid
    if ($mcpPid) {
        Stop-Process -Id $mcpPid -Force
        Write-Ok "MCP server stopped (pid $mcpPid)"
    } else {
        Write-Warn "MCP server was not running"
    }

    Write-Step "Stopping Docker services"
    Set-Location $ProjectRoot
    docker compose stop
    Write-Ok "Docker services stopped"
    exit 0
}

if ($Status) {
    Show-Status
    exit 0
}

# ─── Start ──────────────────────────────────────────────────────────────────

Write-Host "`n╔══════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host   "║       AIJAH Dev Startup              ║" -ForegroundColor Cyan
Write-Host   "╚══════════════════════════════════════╝" -ForegroundColor Cyan

Set-Location $ProjectRoot

# Step 1 — MCP server (must start first — backend needs it)
Write-Step "Starting native MCP server (port $MCP_PORT)"
$existingMcp = Get-McpPid
if ($existingMcp) {
    # Verify it actually responds
    try {
        Invoke-RestMethod "http://localhost:$MCP_PORT/health" -TimeoutSec 3 | Out-Null
        Write-Ok "MCP server already running (pid $existingMcp)"
    } catch {
        Write-Warn "Process on :$MCP_PORT not responding — killing and restarting"
        Stop-Process -Id $existingMcp -Force
        Start-Sleep -Seconds 1
        $existingMcp = $null
    }
}

if (-not $existingMcp) {
    if (-not (Test-Path $VenvPython)) {
        Write-Fail "Python venv not found at $VenvPython"
        Write-Fail "Run: python -m venv .venv && .venv\Scripts\pip install -r backend\requirements.txt"
        exit 1
    }
    Start-Process -FilePath $VenvPython `
                  -ArgumentList "$BackendDir\mcp_server.py" `
                  -WorkingDirectory $BackendDir `
                  -WindowStyle Hidden

    if (-not (Wait-ForPort $MCP_PORT "MCP server" 20)) {
        Write-Fail "MCP server failed to start"
        exit 1
    }
    Write-Ok "MCP server started"
}

# Step 2 — Docker stack (postgres + backend [+ frontend])
Write-Step "Starting Docker services"
$composeArgs = if ($SkipFrontend) { "up", "-d", "postgres", "backend" } else { "up", "-d" }
docker compose @composeArgs

# Step 3 — Wait for backend
if (-not (Wait-ForPort $BACKEND_PORT "backend" 30)) {
    Write-Fail "Backend failed to start — check: docker compose logs backend"
    exit 1
}

# Step 4 — Health check
Write-Step "Verifying services"
Start-Sleep -Seconds 2

try {
    $health = Invoke-RestMethod "http://localhost:$BACKEND_PORT/health" -TimeoutSec 5
    if ($health.status -eq "ok") {
        Write-Ok "Backend health OK  (db=$($health.db)  model=$($health.model_status))"
    } else {
        Write-Warn "Backend health degraded: $($health | ConvertTo-Json -Compress)"
    }
} catch {
    Write-Warn "Could not reach /health — backend may still be initializing"
}

if (-not $SkipFrontend) {
    if (Test-Port $FRONTEND_PORT) {
        Write-Ok "Frontend running on http://localhost:$FRONTEND_PORT"
    } else {
        Write-Warn "Frontend not yet responding on :$FRONTEND_PORT"
    }
}

# Summary
Write-Host "`n────────────────────────────────────" -ForegroundColor DarkGray
Write-Host "  App:      http://localhost:$FRONTEND_PORT" -ForegroundColor White
Write-Host "  Backend:  http://localhost:$BACKEND_PORT" -ForegroundColor White
Write-Host "  MCP:      http://localhost:$MCP_PORT/mcp" -ForegroundColor White
Write-Host "`n  To stop:  .\start.ps1 -Stop" -ForegroundColor DarkGray
Write-Host "  Status:   .\start.ps1 -Status" -ForegroundColor DarkGray
Write-Host ""
