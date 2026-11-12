# Runs the backend (uvicorn, port 8000) and the frontend (npm run dev) together.
# Usage: .\scripts\dev.ps1     Stop both with Ctrl+C.

$root = Split-Path $PSScriptRoot -Parent
$frontend = if (Test-Path "$root\frontend") { "$root\frontend" } else { "$root\frontendv2" }
$python = "$root\.venv\Scripts\python.exe"

$backendProc = Start-Process -PassThru -NoNewWindow -WorkingDirectory "$root\backend" `
    -FilePath $python -ArgumentList "-m", "uvicorn", "app.main:app", "--reload", "--port", "8000"

$frontendProc = Start-Process -PassThru -NoNewWindow -WorkingDirectory $frontend `
    -FilePath "cmd.exe" -ArgumentList "/c", "npm run dev"

try {
    while (-not $backendProc.HasExited -and -not $frontendProc.HasExited) {
        Start-Sleep -Milliseconds 500
    }
}
finally {
    foreach ($p in $backendProc, $frontendProc) {
        if ($p -and -not $p.HasExited) { & taskkill /PID $p.Id /T /F | Out-Null }
    }
}
