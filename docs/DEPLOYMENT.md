# Deployment Guide

This plugin can be published as a normal open-source repository. The repository
root should be the plugin root.

## Repository Layout

```text
obsidian-vault-mcp/
  .codex-plugin/plugin.json
  .mcp.json
  .gitignore
  LICENSE
  README.md
  requirements.txt
  docs/
  scripts/obsidian_vault_mcp.py
  skills/obsidian-vault/SKILL.md
  tests/
```

Do not publish local vault files, generated backups, virtual environments,
`__pycache__`, or ad-hoc scripts that write to a real vault.

## Before Publishing

1. Confirm `.codex-plugin/plugin.json` has the correct `repository`,
   `homepage`, `websiteURL`, `privacyPolicyURL`, and `termsOfServiceURL`.
2. Keep `.mcp.json` portable. It should use `${CLAUDE_PLUGIN_ROOT}` and
   `OBSIDIAN_VAULT_PATH=auto`.
3. Run:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests
```

4. Test with a clean temporary vault and with a real vault path that contains
   non-ASCII characters.
5. Test Zotero tools with Zotero Desktop running. Zotero access should remain
   local to each user's machine.

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

- `python -m unittest discover -s tests` passes.
- `python -m py_compile scripts/obsidian_vault_mcp.py` passes.
- `docs/PRIVACY.md` accurately describes local data access.
- `LICENSE` is present.
- No personal vault path, username, cache path, or Zotero storage path is
  committed.
- Any demo screenshots are sanitized and do not reveal private note contents.
- A fresh clone can install dependencies with `python -m pip install -r
  requirements.txt`.
