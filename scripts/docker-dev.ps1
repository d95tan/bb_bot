# Run Docker Compose in dev mode: bot with hot-reload and logs in the foreground.
# Usage: .\scripts\docker-dev.ps1
# Press Ctrl+C to stop.

Set-Location $PSScriptRoot\..

Write-Host "Starting bb_bot in dev mode (hot refresh) with Docker Compose..." -ForegroundColor Cyan
Write-Host "  - bb_bot runs with watchfiles; code changes in src/ or config/ will restart the bot." -ForegroundColor Gray
Write-Host "  - Logs stream below. Press Ctrl+C to stop." -ForegroundColor Gray
Write-Host ""

docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
