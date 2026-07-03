# Start a temporary cloudflared tunnel to the local MCP port (8001).
# Prints the public HTTPS URL. Requires cloudflared on PATH.
# Install: winget install --id Cloudflare.cloudflared
$port = 8001
Write-Host "Starting cloudflared tunnel -> http://localhost:$port"
Write-Host "Look for the line: 'https://<random>.trycloudflare.com'"
Write-Host "OpenClaw MCP URL = https://<random>.trycloudflare.com/mcp"
cloudflared tunnel --url http://localhost:$port
