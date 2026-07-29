param(
    [string]$Version = "",
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$pythonCommand = if ($env:PYTHON) { $env:PYTHON } else { "python" }
$builder = Join-Path $PSScriptRoot "build_release.py"
$builderArguments = @($builder, "--output-dir", $OutputDir)
if ($Version) {
    $builderArguments += @("--version", $Version)
}

& $pythonCommand @builderArguments
if ($LASTEXITCODE -ne 0) {
    throw "Release bundle builder failed with exit code $LASTEXITCODE."
}
