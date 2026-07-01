$port = 8000
$targetRepoDir = "F:\code\20w-lemming-core"

Write-Host "[SYSTEM] Scanning for processes blocking port $port..." -ForegroundColor Yellow

$processInfo = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue

if ($processInfo) {
    $pidToKill = $processInfo.OwningProcess
    Write-Host "  -> Port $port is held by process PID: $pidToKill" -ForegroundColor Red
    Write-Host "  -> Terminating process..." -ForegroundColor Yellow
    Stop-Process -Id $pidToKill -Force
    Write-Host "  -> Process $pidToKill terminated successfully." -ForegroundColor Green
} else {
    Write-Host "  -> No processes found blocking port $port. Everything is clear." -ForegroundColor Green
}

Write-Host "`n[SYSTEM] Relaunching Docker Compose stack..." -ForegroundColor Cyan
Set-Location -Path $targetRepoDir
docker compose down --remove-orphans | Out-Null
docker compose up -d

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host " SUCCESS: Port $port cleared. Cockpit services redeployed." -ForegroundColor Green
