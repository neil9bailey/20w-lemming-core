# PowerShell Deployment Script for 20W Digital Twin Cockpit (Containers Only)
# Target Environment: Windows 11 with Docker Desktop (WSL 2)
# Repository Path: F:\code\20w-lemming-core

$ErrorActionPreference = "Stop"
$targetRepoDir = "F:\code\20w-lemming-core"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "         20W DIGITAL TWIN COCKPIT - CONTAINERIZED         " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

Set-Location -Path $targetRepoDir

# Check if Docker Desktop daemon is active
try {
    docker ps | Out-Null
} catch {
    Write-Error "[DOCKER FAILURE] Docker Desktop is not running. Please launch Docker Desktop before executing."
}

# Stop and clean up any single container instances to prevent port allocation errors
Write-Host "[DOCKER] Cleaning up standalone container assets..." -ForegroundColor Yellow
$standaloneCockpit = docker ps -a -q -f name=lemming_cockpit
if ($standaloneCockpit) {
    docker stop lemming_cockpit | Out-Null
    docker rm lemming_cockpit | Out-Null
}

# Spin up the complete Docker Compose multi-container mesh
Write-Host "[DOCKER] Building and launching multi-agent backend + frontend containers..." -ForegroundColor Yellow
docker compose down --remove-orphans | Out-Null
docker compose up -d --build

Write-Host "`n==========================================================" -ForegroundColor Green
Write-Host " SUCCESS: Multi-Container Substrate Active!" -ForegroundColor Green
Write-Host " Frontend Cockpit: http://localhost:8080" -ForegroundColor Cyan
Write-Host " Backend Endpoint: http://localhost:8000/health" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Green
