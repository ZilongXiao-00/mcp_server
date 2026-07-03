# Start the MCP Server in the A2A conda env on 127.0.0.1:8001.
$logDir = Join-Path $PSScriptRoot ".." | Join-Path -ChildPath "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$logFile = Join-Path $logDir "mcp.log"
Write-Host "Starting MCP Server -> $logFile"
conda run -n A2A --no-capture-output python mcp_server.py 2>&1 | Tee-Object -FilePath $logFile
