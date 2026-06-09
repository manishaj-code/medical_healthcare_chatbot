# AI Healthcare Assistant — single command to run everything
# Usage:  .\start.ps1

Set-Location $PSScriptRoot

Write-Host ""
Write-Host "  AI Healthcare Assistant - Starting..." -ForegroundColor Cyan
Write-Host ""

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: Docker is not installed or not in PATH." -ForegroundColor Red
    Write-Host "Install Docker Desktop: https://www.docker.com/products/docker-desktop/" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Host "Created .env from .env.example" -ForegroundColor Green
}

Write-Host "Starting Postgres, Redis, API, Frontend..." -ForegroundColor Green
Write-Host ""
Write-Host "  App:      http://localhost:5173" -ForegroundColor White
Write-Host "  API Docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "  Login: john@test.com / Patient@12345" -ForegroundColor Yellow
Write-Host ""
Write-Host "Stop: Ctrl+C then run: docker compose down" -ForegroundColor DarkGray
Write-Host ""

docker compose up --build
