# ECHO Launcher — Lifecycle-Test (lokal ausführen)
# Usage: powershell -ExecutionPolicy Bypass -File scripts\test_launcher_lifecycle.ps1

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

Set-Location $Root
$LogFile = Join-Path $Root "TEST_LAUNCHER_run.txt"
"" | Set-Content $LogFile -Encoding utf8

function Log($msg) {
    $line = "[$(Get-Date -Format o)] $msg"
    Add-Content $LogFile $line
    Write-Host $line
}

Log "=== 1. Dry-run ==="
& uv run python launcher.py --dry-run 2>&1 | ForEach-Object { Log $_ }
Log "EXIT: $LASTEXITCODE"

Log "=== 2. netstat ports ==="
netstat -ano | Select-String "8020|7860" | ForEach-Object { Log $_.Line }

Log "=== 3. Start launcher (no browser) ==="
$proc = Start-Process -FilePath "uv" -ArgumentList "run","python","launcher.py","--no-browser" `
    -WorkingDirectory $Root -PassThru -WindowStyle Hidden
Log "Launcher PID: $($proc.Id)"

$deadline = (Get-Date).AddSeconds(120)
$backendOk = $false
$uiOk = $false
while ((Get-Date) -lt $deadline) {
    try {
        $h = Invoke-WebRequest "http://127.0.0.1:8020/health" -UseBasicParsing -TimeoutSec 3
        if ($h.StatusCode -eq 200) { $backendOk = $true }
    } catch {}
    try {
        $u = Invoke-WebRequest "http://127.0.0.1:7860/" -UseBasicParsing -TimeoutSec 3
        if ($u.StatusCode -ge 200 -and $u.Content -match "gradio") { $uiOk = $true }
    } catch {}
    if ($backendOk -and $uiOk) { break }
    Start-Sleep 2
}
Log "Backend health: $backendOk | UI gradio: $uiOk"

$paths = @(
    "logs\launcher\launcher.log",
    "logs\launcher\launcher_state.json",
    "logs\backend\backend.log",
    "logs\ui\ui.log"
)
foreach ($p in $paths) {
    Log "Log exists ${p}: $(Test-Path (Join-Path $Root $p))"
}

Log "=== 5. Stop launcher ==="
Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
Start-Sleep 3

Log "=== 6. Zombie check ==="
tasklist | Select-String "python" | ForEach-Object { Log $_.Line }
netstat -ano | Select-String "8020|7860" | ForEach-Object { Log $_.Line }

Log "=== 7. Dry-run after shutdown ==="
& uv run python launcher.py --dry-run 2>&1 | ForEach-Object { Log $_ }
Log "EXIT: $LASTEXITCODE"

Log "Done. Full log: $LogFile"
