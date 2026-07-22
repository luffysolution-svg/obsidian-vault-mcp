param(
    [string]$Version = "",
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$pluginPath = Join-Path $root ".codex-plugin/plugin.json"
$plugin = Get-Content -LiteralPath $pluginPath -Raw | ConvertFrom-Json
$manifestVersion = [string]$plugin.version

if (-not $Version) {
    $Version = $manifestVersion
}
if ($Version -notmatch '^\d+\.\d+\.\d+$') {
    throw "Version must use MAJOR.MINOR.PATCH: $Version"
}
if ($Version -ne $manifestVersion) {
    throw "Requested version $Version does not match plugin version $manifestVersion."
}

$bundleRoot = "obsidian-literature"
$bundleFiles = @(
    ".codex-plugin/plugin.json",
    ".mcp.json"
)

foreach ($relativePath in $bundleFiles) {
    & git -C $root ls-files --error-unmatch -- $relativePath 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Release bundle input is not tracked by Git: $relativePath"
    }

    $sourcePath = Join-Path $root $relativePath
    if (-not (Test-Path -LiteralPath $sourcePath -PathType Leaf)) {
        throw "Release bundle input is missing: $relativePath"
    }
}

if ([IO.Path]::IsPathRooted($OutputDir)) {
    $dist = [IO.Path]::GetFullPath($OutputDir)
} else {
    $dist = [IO.Path]::GetFullPath((Join-Path $root $OutputDir))
}
New-Item -ItemType Directory -Path $dist -Force | Out-Null

$zipPath = Join-Path $dist "obsidian-vault-mcp-$Version.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem

$archive = [IO.Compression.ZipFile]::Open($zipPath, [IO.Compression.ZipArchiveMode]::Create)
try {
    foreach ($relativePath in $bundleFiles) {
        $sourcePath = Join-Path $root $relativePath
        $entryName = "$bundleRoot/$($relativePath.Replace('\', '/'))"
        $entry = $archive.CreateEntry($entryName, [IO.Compression.CompressionLevel]::Optimal)
        $entry.LastWriteTime = [DateTimeOffset]::new(1980, 1, 1, 0, 0, 0, [TimeSpan]::Zero)

        $inputStream = [IO.File]::OpenRead($sourcePath)
        $outputStream = $entry.Open()
        try {
            $inputStream.CopyTo($outputStream)
        } finally {
            $outputStream.Dispose()
            $inputStream.Dispose()
        }
    }
} finally {
    $archive.Dispose()
}

$expectedEntries = @(
    "$bundleRoot/.codex-plugin/plugin.json",
    "$bundleRoot/.mcp.json"
)
$archive = [IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $actualEntries = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') } | Sort-Object)
    $difference = @(Compare-Object -ReferenceObject ($expectedEntries | Sort-Object) -DifferenceObject $actualEntries)
    if ($difference.Count -ne 0) {
        throw "Release bundle contents differ from the two-file allowlist."
    }
} finally {
    $archive.Dispose()
}

Get-Item -LiteralPath $zipPath
