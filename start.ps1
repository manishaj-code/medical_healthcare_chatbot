# MediAI Healthcare Assistant - reliable one-command start
# Usage:  .\start.ps1

Set-Location $PSScriptRoot

$appUrl = "http://localhost:5173"
$apiPort = 8000

if (Test-Path .env) {
    $apiPortLine = Get-Content .env | Where-Object { $_ -match '^\s*API_PORT\s*=' } | Select-Object -First 1
    if ($apiPortLine) {
        $apiPortValue = ($apiPortLine -replace '^\s*API_PORT\s*=\s*', '').Trim()
        if ($apiPortValue -match '^\d+$') {
            $apiPort = [int]$apiPortValue
        }
    }
}

$apiHealthUrl = "http://localhost:$apiPort/health"
$spinnerFrames = @('|', '/', '-', '\')

function Write-Step {
    param([string]$Text, [string]$Color = "Cyan")
    Write-Host "  $Text" -ForegroundColor $Color
}

function Write-SpinnerLine {
    param([string]$Frame, [string]$Message)
    Write-Host ("`r  [{0}] {1}" -f $Frame, $Message.PadRight(40)) -NoNewline -ForegroundColor DarkCyan
}

function Clear-SpinnerLine {
    Write-Host ("`r{0}`r" -f (' ' * 54)) -NoNewline
}

function Test-DockerReady {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        return $false
    }
    docker info 2>$null | Out-Null
    return ($LASTEXITCODE -eq 0)
}

function Test-WebReady {
    try {
        $r = Invoke-WebRequest -Uri $appUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400)
    } catch {
        return $false
    }
}

function Test-ApiReady {
    try {
        $r = Invoke-WebRequest -Uri $apiHealthUrl -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
        return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 400)
    } catch {
        return $false
    }
}

function Test-AppReady {
    return (Test-WebReady -and (Test-ApiReady))
}

function Test-ImagesBuilt {
    $apiImg = docker images -q medical_healthcare_chatbot-api 2>$null
    $webImg = docker images -q medical_healthcare_chatbot-web 2>$null
    return ($apiImg -and $webImg)
}

function Invoke-DockerCompose {
    param(
        [string[]]$ExtraArgs
    )

    $stdoutFile = Join-Path $env:TEMP "healthcare-compose-out.txt"
    $stderrFile = Join-Path $env:TEMP "healthcare-compose-err.txt"
    Remove-Item $stdoutFile, $stderrFile -ErrorAction SilentlyContinue

    $composeArgs = @("compose") + $ExtraArgs
    $proc = Start-Process -FilePath "docker" `
        -ArgumentList $composeArgs `
        -Wait -PassThru -NoNewWindow `
        -RedirectStandardOutput $stdoutFile `
        -RedirectStandardError $stderrFile

    $combined = ""
    if (Test-Path $stderrFile) { $combined += Get-Content $stderrFile -Raw }
    if (Test-Path $stdoutFile) { $combined += Get-Content $stdoutFile -Raw }
    Remove-Item $stdoutFile, $stderrFile -ErrorAction SilentlyContinue

    return @{
        ExitCode = $proc.ExitCode
        Output   = $combined
    }
}

function Ensure-AllServicesUp {
    if (-not (Test-ImagesBuilt)) {
        Write-Step "First run - building containers, please wait..." "DarkGray"
        return Invoke-DockerCompose @("up", "-d", "--build")
    }

    Write-Step "Starting all services..." "DarkGray"
    return Invoke-DockerCompose @("up", "-d")
}

function Repair-AppServices {
    Write-Step "Restarting API and web app..." "DarkGray"
    Invoke-DockerCompose @("restart", "api", "web") | Out-Null
}

function Rebuild-AppServices {
    Write-Step "Rebuilding API and web app..." "DarkGray"
    return Invoke-DockerCompose @("up", "-d", "--build", "--force-recreate", "api", "web")
}

function Wait-ForApp {
    param([int]$MaxSeconds = 180)

    $messages = @(
        "Starting services...",
        "Connecting to database...",
        "Running migrations...",
        "Starting API server...",
        "Loading web application...",
        "Almost ready..."
    )

    for ($i = 0; $i -lt $MaxSeconds; $i++) {
        if (Test-AppReady) {
            Clear-SpinnerLine
            return $true
        }

        $frame = $spinnerFrames[$i % $spinnerFrames.Length]
        $msgIndex = [math]::Min([math]::Floor($i / 12), $messages.Length - 1)
        Write-SpinnerLine -Frame $frame -Message $messages[$msgIndex]
        Start-Sleep -Seconds 1
    }

    Clear-SpinnerLine
    return $false
}

function Show-ComposeErrors {
    param([string]$Output)
    if (-not $Output) { return }
    $lines = $Output -split "`n" | Where-Object { $_.Trim() } | Select-Object -Last 6
    foreach ($line in $lines) {
        Write-Host "  $line" -ForegroundColor Red
    }
}

function Show-Success {
    Write-Host ""
    Write-Host "  ----------------------------------------" -ForegroundColor DarkGray
    Write-Host "  MediAI is ready" -ForegroundColor Green
    Write-Host "  $appUrl" -ForegroundColor White
    Write-Host "  ----------------------------------------" -ForegroundColor DarkGray
    Write-Host ""
    Write-Host "  Opening browser..." -ForegroundColor DarkGray
    Start-Process $appUrl
    Write-Host ""
    Write-Host "  App is running in the background." -ForegroundColor DarkGray
    Write-Host "  Code changes reload automatically - no need to run start.ps1 again." -ForegroundColor DarkGray
    Write-Host "  Stop with: docker compose down" -ForegroundColor DarkGray
    Write-Host ""
}

function Show-Failure {
    Write-Host "  ERROR: Application could not start." -ForegroundColor Red
    Write-Host "  Try these steps:" -ForegroundColor Yellow
    Write-Host "    1. Make sure Docker Desktop is running" -ForegroundColor Yellow
    Write-Host "    2. Run: docker compose logs api web" -ForegroundColor Yellow
    Write-Host "    3. Run: docker compose down && .\start.ps1" -ForegroundColor Yellow
}

# --- Main ---

Write-Host ""
Write-Host "  MediAI Healthcare Assistant" -ForegroundColor Cyan
Write-Host ""

if (-not (Test-DockerReady)) {
    Write-Host "  ERROR: Docker is not running." -ForegroundColor Red
    Write-Host "  Please start Docker Desktop, then run .\start.ps1 again." -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
    Write-Step "Created .env from .env.example" "DarkGray"
}

$composeRun = Ensure-AllServicesUp
if ($composeRun.ExitCode -ne 0) {
    Write-Step "Compose reported a warning - checking application..." "DarkGray"
}

if (Wait-ForApp -MaxSeconds 180) {
    Show-Success
    exit 0
}

Repair-AppServices
if (Wait-ForApp -MaxSeconds 90) {
    Show-Success
    exit 0
}

$rebuildRun = Rebuild-AppServices
if ($rebuildRun.ExitCode -ne 0) {
    Show-ComposeErrors -Output $rebuildRun.Output
}

if (Wait-ForApp -MaxSeconds 120) {
    Show-Success
    exit 0
}

Show-Failure
exit 1
