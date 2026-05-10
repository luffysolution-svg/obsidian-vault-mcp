# 安装指南

这份文档说明如何安装 Obsidian Vault MCP 插件。更完整的路径、Codex 插件位置、Obsidian CLI、Zotero、MinerU 配置请看 [配置指南](./CONFIGURATION.zh-CN.md)。

## 环境要求

- Python 3.10 或更高版本。
- 已创建或打开过一个本地 Obsidian vault。
- 如果需要 Zotero 集成，安装并打开 Zotero Desktop。
- 如果需要 app-backed Obsidian 功能，安装 Obsidian 1.12.7+ 并启用官方 `obsidian` CLI。
- 如果需要本插件直接解析 PDF/文档，安装 MinerU Open API CLI。已有 MinerU Markdown 可以直接导入，不需要安装 MinerU CLI。

## 安装插件依赖

在插件根目录运行：

```bash
python -m pip install -r requirements.txt
```

开发模式或需要命令行入口时：

```bash
python -m pip install -e ".[dev]"
obsidian-vault-mcp --doctor --doctor-format text --vault "C:/path/to/your-vault"
```

## 注册为 Codex 插件

插件根目录包含：

```text
.codex-plugin/plugin.json
.mcp.json
skills/obsidian-vault/SKILL.md
scripts/obsidian_vault_mcp.py
```

推荐通过 Codex 本地 marketplace 暴露该插件，或把插件目录复制到本地插件目录。`.mcp.json` 保持可移植配置：

```json
{
  "mcpServers": {
    "obsidian-vault": {
      "type": "stdio",
      "command": "python",
      "args": ["${CLAUDE_PLUGIN_ROOT}/scripts/obsidian_vault_mcp.py"],
      "env": {
        "OBSIDIAN_VAULT_PATH": "auto",
        "OBSIDIAN_CLI_COMMAND": "obsidian"
      }
    }
  }
}
```

不要把 `${CLAUDE_PLUGIN_ROOT}` 改成个人绝对路径并提交到仓库。如果某个 MCP host 必须使用绝对路径，只在本地配置里覆盖。

`scripts/obsidian_vault_mcp.py` 是兼容入口，实际实现位于 `scripts/obsidian_vault_mcp/`。发布或复制插件时，两者都要保留。

## Codex Skill

随插件发布的 skill 位于：

```text
skills/obsidian-vault/SKILL.md
```

Codex 会通过 `.codex-plugin/plugin.json` 自动加载它。正常使用插件时，不需要把这个 skill 复制到 `~/.agents/skills`。

## 配置 Vault 路径

默认：

```json
"OBSIDIAN_VAULT_PATH": "auto"
```

`auto` 会尝试通过 Obsidian CLI 获取当前活动 vault。如果失败，可以在本地配置中设置：

```json
"OBSIDIAN_VAULT_PATH": "C:/path/to/your-vault"
```

vault 根目录应该包含 `.obsidian`：

```powershell
Test-Path "C:\path\to\your-vault\.obsidian"
```

插件默认拒绝普通 Markdown 文件夹。只有明确需要时才设置：

```text
OBSIDIAN_ALLOW_NON_VAULT=true
```

## Vault 默认目录和模板

可以在 vault 内放配置文件：

```text
.obsidian-vault-mcp.json
.obsidian/obsidian-vault-mcp.json
```

示例：

```json
{
  "literatureFolder": "01-literature",
  "mineruSourceFolder": "02-sources/mineru",
  "pdfSourceFolder": "02-sources/pdf",
  "entitiesFolder": "entities",
  "conceptsFolder": "concepts",
  "zoteroAttachmentsFolder": "assets/zotero",
  "zoteroAttachmentNameStrategy": "zotero_key",
  "indexPath": "index.md",
  "logPath": "log.md",
  "templateFolder": "Templates",
  "defaultTemplate": "Literature"
}
```

`obsidian_create_note` 可以使用 `template_path`、`template_name`、`use_template=true` 或配置的 `defaultTemplate` 套用模板。它只做文本替换，不执行 Templater JavaScript。

## Doctor 检查

```bash
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault "C:/path/to/your-vault"
```

默认输出是 JSON，适合自动化；`--doctor-format text` 适合人工检查。

## Obsidian CLI

直接文件工具使用 `vault_path` 文件系统路径。Obsidian CLI 包装工具使用官方 CLI 的 `vault=<name>`，这里的值是 Obsidian 认识的 vault 名称或 ID，不是文件系统路径。

启用官方 CLI：

1. 安装或更新到 Obsidian 1.12.7+ installer。
2. 打开 Obsidian。
3. 进入 `Settings` -> `General`。
4. 启用 `Command line interface`。
5. 按提示注册 `obsidian` 命令。
6. 重启终端。

检查：

```bash
obsidian version
obsidian help
obsidian vault info=path
```

## 批量编辑计划

`obsidian_preview_edit_plan`、`obsidian_apply_edit_plan` 和 `obsidian_rollback_edit_plan` 使用 JSON 计划。计划可以是数组，也可以是带 `operations` 的对象。

```json
{
  "operations": [
    {
      "operation": "write",
      "path": "Inbox/New note.md",
      "content": "# New note\n",
      "overwrite": false
    },
    {
      "operation": "replace",
      "path": "Inbox/Existing note.md",
      "old": "draft",
      "new": "reviewed"
    }
  ]
}
```

支持 `write`、`update_properties`、`append`、`replace`、`delete`。应用前先预览；应用后会在 vault 内 `.obsidian-vault-backups/` 保存回滚备份。

## 本地 Smoke 检查

打开 Obsidian 和 Zotero Desktop 后：

```bash
python scripts/smoke_integrations.py --vault "C:/path/to/your-vault"
```

脚本不会真正写入 vault，只会做 vault 状态检查、dry-run 创建笔记预览、Zotero 本地 API 检查、Zotero 搜索和 Obsidian CLI 检查。Zotero 与 Obsidian CLI 失败会作为 warning，不影响核心 vault 工具。

## Zotero

Zotero 工具默认访问：

```text
http://127.0.0.1:23119/api
```

使用前打开 Zotero Desktop。如果本地 API 暴露在别处，只在本地配置中设置 `ZOTERO_LOCAL_API`。

检查：

```powershell
curl.exe "http://127.0.0.1:23119/connector/ping"
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault "C:/path/to/your-vault"
```

导入的 Zotero 笔记可包含 `zoteroKey`、`zoteroSelect`、`zoteroLinks`、PDF keys、PDF links 和附件路径。如果 Zotero 附件不在默认 `~/Zotero/storage`，设置 `ZOTERO_STORAGE_DIR`。

## MinerU

已有 MinerU Markdown 可以直接用 `obsidian_ingest_mineru_markdown` 导入。只有希望插件直接解析文档时才安装 CLI。

Windows：

```powershell
irm https://cdn-mineru.openxlab.org.cn/open-api-cli/install.ps1 | iex
mineru-open-api version
```

Linux/macOS：

```bash
curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh
mineru-open-api version
```

`flash-extract` 不需要 token，适合小文件和简单 Markdown 预览。`extract` 需要认证，适合更大文件、OCR、表格、公式和多格式输出。

从这里获取 token：

```text
https://mineru.net/apiManage/token
```

本地配置 token：

```bash
mineru-open-api auth
```

或设置环境变量 `MINERU_TOKEN`。不要把 token 写入仓库。

CLI token 优先级：

1. `--token`
2. `MINERU_TOKEN`
3. `~/.mineru/config.yaml`

网络检查：

```powershell
mineru-open-api version
curl.exe -I https://mineru.net
curl.exe -I https://cdn-mineru.openxlab.org.cn
Resolve-DnsName cdn-mineru.openxlab.org.cn
```

如果创建解析任务成功但下载 Markdown 失败，优先检查代理、VPN、DNS 和 fake-IP 规则，尤其是 `cdn-mineru.openxlab.org.cn`。
