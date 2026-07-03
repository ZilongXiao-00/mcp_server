# Start the FastAPI service in the A2A conda env on 127.0.0.1:8000.
# Pipe stdout to a log file so correlate_logs.py can read it.
$logDir = Join-Path $PSScriptRoot ".." | Join-Path -ChildPath "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$logFile = Join-Path $logDir "fastapi.log"
Write-Host "Starting FastAPI -> $logFile"
conda run -n A2A --no-capture-output python -m uvicorn app:app --host 127.0.0.1 --port 8000 2>&1 | Tee-Object -FilePath $logFile
