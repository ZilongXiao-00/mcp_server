# Start a temporary cloudflared tunnel to the local MCP port (8001).
# Prints the public HTTPS URL.
# Install: winget install --id Cloudflare.cloudflared
$port = 8001

function Get-CloudflaredExe {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }

    $candidates = @(
        "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
        "$env:ProgramFiles\cloudflared\cloudflared.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\cloudflared.exe"
    )
    foreach ($path in $candidates) {
        if (Test-Path $path) { return $path }
    }
    return $null
}

$cloudflared = Get-CloudflaredExe
if (-not $cloudflared) {
    Write-Error "cloudflared not found. Install with: winget install --id Cloudflare.cloudflared`nThen reopen PowerShell or run: `$env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [System.Environment]::GetEnvironmentVariable('Path','User')"
    exit 1
}

Write-Host "Using cloudflared: $cloudflared"
Write-Host "Starting cloudflared tunnel -> http://127.0.0.1:$port"
Write-Host "Look for the line: 'https://<random>.trycloudflare.com'"
Write-Host "OpenClaw MCP URL = https://<random>.trycloudflare.com/mcp"
Write-Host ""
Write-Host "Tip: keep this window open. Ctrl+C stops the tunnel."
Write-Host ""

$maxAttempts = 3
for ($i = 1; $i -le $maxAttempts; $i++) {
    if ($i -gt 1) {
        Write-Host "Retry $i/$maxAttempts after quick-tunnel API error..."
        Start-Sleep -Seconds 3
    }
    & $cloudflared tunnel --url "http://127.0.0.1:$port"
    if ($LASTEXITCODE -eq 0) { exit 0 }
    Write-Host "cloudflared exited with code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Tunnel failed after $maxAttempts attempts."
Write-Host "Common fixes:"
Write-Host "  1. Ensure MCP is running: netstat -ano | findstr :8001"
Write-Host "  2. Wait 10s and run .\scripts\start_tunnel.ps1 again"
Write-Host "  3. If on corporate network/VPN, try another network or disable VPN briefly"
exit 1
