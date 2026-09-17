[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Split-Path -Parent $scriptDirectory
$backendRoot = Join-Path $projectRoot "backend"
$runtimeRoot = Join-Path $backendRoot "runtime"
$pidPath = Join-Path $runtimeRoot "server.pid"

if (-not (Test-Path -LiteralPath $pidPath)) {
    Write-Output "Nenhum servidor iniciado pelo Torus foi encontrado."
    exit 0
}

$serverPid = [int](Get-Content -Raw -LiteralPath $pidPath)
$serverProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $serverPid"
if ($null -eq $serverProcess) {
    Remove-Item -LiteralPath $pidPath -Force
    Write-Output "O servidor do Torus já estava encerrado."
    exit 0
}

$expectedPython = Join-Path $backendRoot ".venv\Scripts\python.exe"
$parentProcess = Get-CimInstance Win32_Process `
    -Filter "ProcessId = $($serverProcess.ParentProcessId)"
$processPathMatches = $serverProcess.ExecutablePath.Equals(
    $expectedPython,
    [System.StringComparison]::OrdinalIgnoreCase
)
$parentPathMatches = $null -ne $parentProcess -and $parentProcess.ExecutablePath.Equals(
    $expectedPython,
    [System.StringComparison]::OrdinalIgnoreCase
)
if (-not ($processPathMatches -or $parentPathMatches)) {
    throw "O processo registrado não pertence ao ambiente local do Torus. Nada foi encerrado."
}

Stop-Process -Id $serverPid -Force
Remove-Item -LiteralPath $pidPath -Force
Write-Output "Servidor do Torus encerrado."
