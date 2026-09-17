[CmdletBinding()]
param(
    [switch]$NoBrowser
)

$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDirectory
$backendRoot = Join-Path $projectRoot "backend"
$runtimeRoot = Join-Path $backendRoot "runtime"
$healthUrl = "http://127.0.0.1:8000/health"
$applicationUrl = "http://127.0.0.1:8000/"
$pidPath = Join-Path $runtimeRoot "server.pid"

function Test-TorusApi {
    try {
        $response = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 2
        return $response.status -eq "ok"
    }
    catch {
        return $false
    }
}

New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null

if (Test-TorusApi) {
    Write-Output "O servidor do Torus já está disponível em $applicationUrl"
    if (-not $NoBrowser) {
        Start-Process $applicationUrl
    }
    exit 0
}

$uvCommand = Get-Command uv -ErrorAction SilentlyContinue
if ($null -eq $uvCommand) {
    throw "O uv não foi encontrado. Instale o uv e execute este inicializador novamente."
}

$standardOutput = Join-Path $runtimeRoot "server.out.log"
$standardError = Join-Path $runtimeRoot "server.err.log"
$serverArguments = @(
    "run",
    "python",
    "-m",
    "uvicorn",
    "app.api:app",
    "--host",
    "127.0.0.1",
    "--port",
    "8000"
)

$serverProcess = Start-Process `
    -FilePath $uvCommand.Source `
    -ArgumentList $serverArguments `
    -WorkingDirectory $backendRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $standardOutput `
    -RedirectStandardError $standardError `
    -PassThru

$serverStarted = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    Start-Sleep -Milliseconds 250
    if (Test-TorusApi) {
        $serverStarted = $true
        break
    }
    if ($serverProcess.HasExited) {
        break
    }
}

if (-not $serverStarted) {
    $details = if (Test-Path $standardError) {
        (Get-Content -Raw $standardError).Trim()
    }
    else {
        "Nenhum detalhe foi registrado."
    }
    throw "O servidor do Torus não iniciou. Detalhes: $details"
}

$listener = Get-NetTCPConnection -LocalPort 8000 -State Listen |
    Select-Object -First 1
if ($null -ne $listener) {
    Set-Content -Path $pidPath -Value $listener.OwningProcess -Encoding ascii
}

Write-Output "Torus iniciado em $applicationUrl"
if (-not $NoBrowser) {
    Start-Process $applicationUrl
}
