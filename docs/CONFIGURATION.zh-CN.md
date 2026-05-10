# 配置指南

本文说明如何安装 Obsidian Vault MCP 插件、插件应该放在哪里、Codex 如何发现随插件发布的 skill 和 MCP server，以及如何配置 Obsidian CLI、Zotero 和 MinerU。

所有路径都是示例。请替换成你机器上的真实路径，并且不要把个人路径、API token、Zotero 存储路径、私有 vault 名称或笔记内容提交到仓库。

## 需要准备什么

- Python 3.10 或更高版本。
- Git，或能从 GitHub 下载 ZIP。
- Obsidian Desktop，并且至少有一个本地 vault。
- Codex 或其他支持 stdio MCP server 的 MCP host。
- Zotero Desktop：只在需要 Zotero 搜索/导入时需要。
- Obsidian 1.12.7+：只在需要官方 Obsidian CLI app-backed 操作时需要。
- MinerU Open API CLI：只在需要本插件直接解析 PDF/文档时需要。

检查 Python：

```powershell
python --version
python -m pip --version
```

Windows 找不到 `python` 时，安装 Python 并启用 “Add Python to PATH”。

## 仓库位置和插件安装位置

请区分两个位置：

- 源码 checkout：你编辑这个仓库的地方，例如 `C:/path/to/plugins/obsidian-vault`。
- Codex 安装后的插件副本：Codex 从 marketplace 安装后实际加载的副本，通常在 `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/`。

本地开发推荐使用 repo-scoped marketplace：

```text
your-repo/
  .agents/plugins/marketplace.json
  plugins/obsidian-vault/
    .codex-plugin/plugin.json
    .mcp.json
    README.md
    docs/
    scripts/
    skills/obsidian-vault/SKILL.md
```

个人安装可以使用：

```text
~/.codex/plugins/obsidian-vault/
~/.agents/plugins/marketplace.json
```

Codex 会读取 marketplace 文件，把插件安装到缓存，然后加载缓存中的副本。修改插件后，需要更新 marketplace 指向的源目录并重启 Codex。

## 克隆或下载

Git 克隆：

```powershell
cd C:\path\to\plugins
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git obsidian-vault
cd obsidian-vault
```

下载 ZIP：

1. 打开 `https://github.com/luffysolution-svg/obsidian-vault-mcp`。
2. 点击 `Code` -> `Download ZIP`。
3. 解压到稳定目录。
4. 在插件根目录打开终端。

插件根目录应包含 `.codex-plugin/plugin.json`、`.mcp.json`、`README.md`、`scripts/`、`skills/`。

## 安装 Python 依赖

```powershell
python -m pip install -r requirements.txt
```

开发模式：

```powershell
python -m pip install -e ".[dev]"
```

MCP 入口：

```text
scripts/obsidian_vault_mcp.py
```

实现包：

```text
scripts/obsidian_vault_mcp/
```

发布或复制时二者都要保留。

## 注册到 Codex

插件 manifest 指向 skill 和 MCP 配置：

```json
{
  "skills": "./skills/",
  "mcpServers": "./.mcp.json"
}
```

`.mcp.json` 默认：

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

不要把 `${CLAUDE_PLUGIN_ROOT}` 改成私人路径并提交。如果 host 必须写绝对路径，只在本地配置中覆盖。

### Repo marketplace

创建 `$REPO_ROOT/.agents/plugins/marketplace.json`：

```json
{
  "name": "local-repo",
  "interface": {
    "displayName": "Local Repo Plugins"
  },
  "plugins": [
    {
      "name": "obsidian-vault",
      "source": {
        "source": "local",
        "path": "./plugins/obsidian-vault"
      },
      "policy": {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL"
      },
      "category": "Productivity"
    }
  ]
}
```

插件放在 `$REPO_ROOT/plugins/obsidian-vault`。重启 Codex 后，在插件目录选择本地 marketplace 并安装。

### Personal marketplace

创建 `~/.agents/plugins/marketplace.json`，让其中的 `source.path` 指向个人插件副本。路径应相对 marketplace root，并以 `./` 开头。

## Skill 存放方式

随插件发布的 skill 在：

```text
skills/obsidian-vault/SKILL.md
```

正常插件使用不需要复制它。只有临时开发独立 skill 时才使用：

- repo skill：`$REPO_ROOT/.agents/skills/<skill-name>/SKILL.md`
- user skill：`~/.agents/skills/<skill-name>/SKILL.md`
- admin skill：`/etc/codex/skills/<skill-name>/SKILL.md`

可复用分发时，保持 skill 随插件发布。

## Obsidian Vault 路径

默认：

```json
"OBSIDIAN_VAULT_PATH": "auto"
```

`auto` 会询问 Obsidian CLI 当前活动 vault，也会在当前工作目录包含 `.obsidian` 时使用当前目录。

显式路径：

```json
"OBSIDIAN_VAULT_PATH": "C:/path/to/your-vault"
```

检查：

```powershell
Test-Path "C:\path\to\your-vault\.obsidian"
```

默认拒绝非 Obsidian 文件夹。需要普通 Markdown 文件夹时，设置：

```text
OBSIDIAN_ALLOW_NON_VAULT=true
```

## Vault 内配置文件

推荐把输出目录、模板目录等默认值放在 vault 内：

```text
<vault>/.obsidian-vault-mcp.json
<vault>/.obsidian/obsidian-vault-mcp.json
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

工具参数显式传入时优先级更高。

## Obsidian CLI

Obsidian CLI 是可选项。显式 `OBSIDIAN_VAULT_PATH` 可用时，核心文件工具不依赖 CLI。

CLI 用于：

- 通过 Obsidian app 读取或打开笔记；
- backlinks、outgoing links、unresolved links、orphans、dead ends；
- Base query；
- 通过 Obsidian 修改 properties；
- tasks；
- screenshot、plugin reload；
- move/rename 并遵循 Obsidian 的链接更新设置。

启用官方 CLI：

1. 安装 Obsidian 1.12.7+ installer。
2. 打开 Obsidian。
3. 进入 `Settings` -> `General`。
4. 启用 `Command line interface`。
5. 按提示注册 `obsidian`。
6. 重启终端。

检查：

```powershell
obsidian version
obsidian help
obsidian vault info=path
```

CLI wrapper 的 `vault` 参数是 Obsidian vault 名称或 ID，不是文件系统路径。直接文件工具使用 `vault_path`。

## Zotero 本地 API

Zotero 集成使用 Zotero Desktop 本地 API：

```text
http://127.0.0.1:23119/api
```

使用前打开 Zotero Desktop。Zotero 7+ 中如果本地 API 没有默认开启，请在高级设置中允许其他应用与 Zotero 通信。

本插件使用：

```text
GET /api/users/0/items?limit=1&format=json
GET /api/users/0/items/<itemKey>?format=json
GET /api/users/0/items/<itemKey>/children?format=json
```

只在本地配置中覆盖：

```json
"ZOTERO_LOCAL_API": "http://127.0.0.1:23119/api"
```

检查：

```powershell
curl.exe "http://127.0.0.1:23119/connector/ping"
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault "C:/path/to/your-vault"
python scripts/smoke_integrations.py --vault "C:/path/to/your-vault"
```

导入 Zotero 条目时可写入 `zoteroKey`、`zoteroSelect`、`zoteroLinks`、PDF keys、PDF links、复制后的 vault 附件路径或原始本地 PDF 路径。

如果 Zotero 附件目录不是默认 `~/Zotero/storage`，设置 `ZOTERO_STORAGE_DIR`。

## MinerU API 和 CLI

MinerU 是可选项。已有 Markdown 使用 `obsidian_ingest_mineru_markdown`；需要直接解析 PDF/文档时使用 `obsidian_mineru_extract` 或 `obsidian_mineru_extract_and_ingest`。

Windows 安装：

```powershell
irm https://cdn-mineru.openxlab.org.cn/open-api-cli/install.ps1 | iex
mineru-open-api version
```

Linux/macOS：

```bash
curl -fsSL https://cdn-mineru.openxlab.org.cn/open-api-cli/install.sh | sh
mineru-open-api version
```

`flash-extract` 无需 token，适合小文件、简单文档和首次连通性测试。`extract` 需要 token，适合 OCR、表格、公式、多格式和更大任务。

获取 token：

```text
https://mineru.net/apiManage/token
```

本地保存：

```powershell
mineru-open-api auth
```

或设置：

```powershell
$env:MINERU_TOKEN = "your-token"
```

不要提交 token。CLI token 优先级是 `--token`、`MINERU_TOKEN`、`~/.mineru/config.yaml`。

本插件的 `obsidian_mineru_status` 也会报告 `MINERU_API_TOKEN`，用于兼容旧本地配置；当前 CLI 标准是 `MINERU_TOKEN`。

示例：

```powershell
mineru-open-api flash-extract report.pdf -o ./out/
mineru-open-api flash-extract report.pdf --language en --pages 1-5 -o ./out/
mineru-open-api auth
mineru-open-api extract report.pdf -f md,docx -o ./results/
```

网络检查：

```powershell
curl.exe -I https://mineru.net
curl.exe -I https://cdn-mineru.openxlab.org.cn
Resolve-DnsName cdn-mineru.openxlab.org.cn
```

需要可达的域名：

- `mineru.net`
- `mineru.oss-cn-shanghai.aliyuncs.com`
- `cdn-mineru.openxlab.org.cn`
- `*.openxlab.org.cn`

VPN、代理和 fake-IP DNS 可能导致结果下载失败，尤其是 `cdn-mineru.openxlab.org.cn` 被解析到 `198.18.x.x` 等 fake-IP 地址时。

## 验证

```powershell
python scripts/obsidian_vault_mcp.py --doctor --doctor-format text --vault "C:/path/to/your-vault"
python -m unittest discover -s tests
python scripts/smoke_integrations.py --vault "C:/path/to/your-vault"
```

Zotero、Obsidian CLI、MinerU 和 PDF 提取是可选检查，warning 不代表核心 vault 工具不可用。

## 常见问题

| 现象 | 可能原因 | 处理方式 |
| --- | --- | --- |
| `python` 无法识别 | Python 未安装或不在 PATH | 安装 Python 并启用 PATH |
| `No module named mcp` | 依赖未安装 | 运行 `python -m pip install -r requirements.txt` |
| `Could not resolve an Obsidian vault` | `auto` 找不到 vault | 打开 Obsidian 或显式设置 `OBSIDIAN_VAULT_PATH` |
| `Path does not look like an Obsidian vault root` | 路径缺少 `.obsidian` | 选择 vault 根目录 |
| `Obsidian CLI command not found` | CLI 未启用或不在 PATH | 启用 Obsidian CLI 并重启终端 |
| Zotero API 失败 | Zotero 未打开或本地 API 被禁用/拦截 | 打开 Zotero 并检查 `127.0.0.1:23119` |
| MinerU 检查失败 | 未安装 MinerU CLI | 只有直接解析文档时才安装 `mineru-open-api` |
| MinerU Markdown 下载失败 | 代理或 DNS 路由问题 | 检查 MinerU/OpenXLab 域名和 fake-IP 规则 |
| MCP 工具不出现 | Codex 尚未重新加载插件 | 重启 Codex 或 reload MCP/plugin |
| 写入提示文件已存在 | 默认保护已有文件 | 确认无误后传入 `overwrite=true` |
