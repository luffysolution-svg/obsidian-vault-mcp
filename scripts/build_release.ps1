param(
    [string]$Version = "",
    [string]$OutputDir = "dist"
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Push-Location $root
try {
    if (-not $Version) {
        $plugin = Get-Content ".codex-plugin/plugin.json" -Raw | ConvertFrom-Json
        $Version = [string]$plugin.version
    }
    if (-not $Version) {
        throw "Version is required and could not be read from .codex-plugin/plugin.json."
    }

    $dist = Join-Path $root $OutputDir
    $stage = Join-Path $dist "obsidian-vault"
    $zip = Join-Path $dist "obsidian-vault-mcp-$Version.zip"

    if (Test-Path $stage) {
        Remove-Item -Recurse -Force -LiteralPath $stage
    }
    New-Item -ItemType Directory -Path $stage -Force | Out-Null

    $files = @(
        git ls-files
        git ls-files --others --exclude-standard
    ) | Sort-Object -Unique
    foreach ($file in $files) {
        $source = Join-Path $root $file
        $dest = Join-Path $stage $file
        New-Item -ItemType Directory -Path (Split-Path -Parent $dest) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $dest -Force
    }

    if (Test-Path $zip) {
        Remove-Item -Force -LiteralPath $zip
    }
    Compress-Archive -Path $stage -DestinationPath $zip -Force
    Remove-Item -Recurse -Force -LiteralPath $stage

    $required = @(
        "obsidian-vault/scripts/obsidian_vault_mcp.py",
        "obsidian-vault/scripts/smoke_integrations.py",
        "obsidian-vault/scripts/obsidian_vault_mcp/cli.py",
        "obsidian-vault/scripts/obsidian_vault_mcp/tools.py",
        "obsidian-vault/scripts/obsidian_vault_mcp/helpers.py",
        "obsidian-vault/pyproject.toml",
        "obsidian-vault/.codex-plugin/plugin.json",
        "obsidian-vault/.mcp.json",
        "obsidian-vault/skills/obsidian-vault/SKILL.md",
        "obsidian-vault/skills/obsidian-zotero/SKILL.md",
        "obsidian-vault/skills/obsidian-mineru/SKILL.md",
        "obsidian-vault/skills/obsidian-views/SKILL.md",
        "obsidian-vault/skills/obsidian-cli/SKILL.md"
    )
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($zip)
    try {
        $names = @($archive.Entries | ForEach-Object { $_.FullName.Replace("\", "/") })
        foreach ($entry in $required) {
            if ($names -notcontains $entry) {
                throw "Release zip is missing required entry: $entry"
            }
        }
    } finally {
        $archive.Dispose()
    }

    Get-Item $zip
} finally {
    Pop-Location
}
