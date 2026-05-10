# Deployment Guide

This plugin can be published as a normal open-source repository. The repository
root should be the plugin root.

## Repository Layout

```text
obsidian-vault-mcp/
  .codex-plugin/plugin.json
  .mcp.json
  .opencode.json
  .gitignore
  LICENSE
  plugin.json
  pyproject.toml
  README.md
  requirements.txt
  docs/
  scripts/obsidian_vault_mcp.py
  scripts/smoke_integrations.py
  scripts/obsidian_vault_mcp/
    __init__.py
    cli.py
    common.py
    helpers.py
    server.py
    tools.py
  skills/obsidian-vault/SKILL.md
  tests/
```

Do not publish local vault files, generated backups, virtual environments,
`__pycache__`, or ad-hoc scripts that write to a real vault.

`.codex-plugin/plugin.json` is the Codex plugin manifest. `plugin.json` at the
root is the Claude Code plugin manifest. `.opencode.json` is the OpenCode MCP
server configuration. Keep all three checked in so users of each client can
connect without extra setup.

`scripts/obsidian_vault_mcp.py` is a compatibility entrypoint kept alongside
the implementation package. `pyproject.toml` is required for editable installs
and the `obsidian-vault-mcp` console command. `scripts/smoke_integrations.py`
is the read-only local integration smoke checker used before release.

## Local Plugin Placement

During development, keep the source plugin folder under a repository path such
as `$REPO_ROOT/plugins/obsidian-vault` and expose it through
`$REPO_ROOT/.agents/plugins/marketplace.json`. For personal-only testing, keep
the plugin under `~/.codex/plugins/obsidian-vault` and expose it through
`~/.agents/plugins/marketplace.json`.

Codex installs marketplace plugins into
`~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/` and loads the
installed copy from that cache. After changing plugin files, refresh the source
directory used by the marketplace and restart Codex.

Only `.codex-plugin/plugin.json` belongs under `.codex-plugin/`. Keep
`skills/`, `.mcp.json`, `docs/`, `scripts/`, and assets at the plugin root.

## Before Publishing

1. Confirm `.codex-plugin/plugin.json` has the correct `repository`,
   `homepage`, `websiteURL`, `privacyPolicyURL`, and `termsOfServiceURL`.
   Confirm `plugin.json` at the root has matching values for Claude Code.
2. Keep `.mcp.json` portable. It uses the `obsidian-vault-mcp` entry point
   and `OBSIDIAN_VAULT_PATH=auto`. Users must run `pip install -e .` before
   connecting any MCP client.
3. Install in editable mode and run the full local verification set:

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m unittest discover -s tests
python -m py_compile scripts/obsidian_vault_mcp.py scripts/obsidian_vault_mcp/cli.py scripts/obsidian_vault_mcp/common.py scripts/obsidian_vault_mcp/helpers.py scripts/obsidian_vault_mcp/server.py scripts/obsidian_vault_mcp/tools.py
python scripts/obsidian_vault_mcp.py --doctor --vault path/to/test-vault
```

4. Test with a clean temporary vault and with a real vault path that contains
   non-ASCII characters.
5. With Obsidian and Zotero Desktop running, run the optional smoke checks:

```bash
python scripts/smoke_integrations.py --vault path/to/test-vault
```

Zotero and Obsidian CLI failures are warnings in the smoke script so the core
vault checks can still pass when optional apps are closed. Run the smoke script
in an environment where those integrations are available before publishing a
release.
6. Build the release zip and confirm it contains the modular package files:

```powershell
./scripts/build_release.ps1
```

## GitHub CLI Publishing Flow

```powershell
Set-Location "path/to/obsidian-vault-mcp"
git init
git add .
git commit -m "publish obsidian vault mcp plugin"
gh repo create obsidian-vault-mcp --public --source . --remote origin --push
```

If GitHub CLI is unavailable, create the repository on GitHub first, then:

```powershell
Set-Location "path/to/obsidian-vault-mcp"
git init
git add .
git commit -m "publish obsidian vault mcp plugin"
git branch -M main
git remote add origin https://github.com/luffysolution-svg/obsidian-vault-mcp.git
git push -u origin main
```

## Release Checklist

- `python -m ruff check .` passes.
- `python -m unittest discover -s tests` passes.
- `python -m py_compile scripts/obsidian_vault_mcp.py scripts/obsidian_vault_mcp/cli.py scripts/obsidian_vault_mcp/common.py scripts/obsidian_vault_mcp/helpers.py scripts/obsidian_vault_mcp/server.py scripts/obsidian_vault_mcp/tools.py`
  passes.
- `python scripts/obsidian_vault_mcp.py --doctor --vault path/to/test-vault`
  reports the vault and template checks successfully.
- `python scripts/smoke_integrations.py --vault path/to/test-vault` has no
  required-check failures; optional integration warnings are understood.
- `./scripts/build_release.ps1` creates `dist/obsidian-vault-mcp-*.zip` and the
  archive contains `pyproject.toml`, `scripts/smoke_integrations.py`, and the
  `scripts/obsidian_vault_mcp/` package.
- `docs/PRIVACY.md` accurately describes local data access.
- `docs/TECHNICAL_GUIDE.md` stays current with Obsidian CLI, Codex plugin/skill,
  Claude Code plugin, OpenCode MCP, Zotero, and MinerU setup details.
- `LICENSE` is present.
- No personal vault path, username, cache path, or Zotero storage path is
  committed.
- Any demo screenshots are sanitized and do not reveal private note contents.
- A fresh clone can install dependencies with `python -m pip install -e
  ".[dev]"`.
- Optional MinerU tests remain mocked and do not require a MinerU API token.
