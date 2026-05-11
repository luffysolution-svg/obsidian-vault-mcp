# 安装配置教程

本教程面向普通用户，手把手完成从零安装到第一次使用的全流程。

---

## 目录

1. [前置要求](#1-前置要求)
2. [安装插件](#2-安装插件)
3. [配置 MCP 客户端](#3-配置-mcp-客户端)
   - [Claude Code](#claude-code)
   - [Codex](#codex)
   - [OpenCode](#opencode)
4. [验证安装](#4-验证安装)
5. [可选：配置 Zotero 集成](#5-可选配置-zotero-集成)
6. [可选：配置 MinerU 文档解析](#6-可选配置-mineru-文档解析)
7. [Vault 内默认配置](#7-vault-内默认配置)
8. [常见问题](#8-常见问题)

---

## 1. 前置要求

| 工具 | 版本要求 | 说明 |
|------|----------|------|
| Python | 3.10 或更高 | 运行 `python --version` 确认 |
| Obsidian | 任意版本 | 已有本地 vault |
| Git | 任意版本 | 用于克隆仓库 |

确认 Python 版本：

```bash
python --version
# 应输出 Python 3.10.x 或更高
```

---

## 2. 安装插件

### 2.1 克隆仓库

将插件克隆到本地合适的目录，例如 `~/plugins/`：

```bash
git clone https://github.com/luffysolution-svg/obsidian-vault-mcp.git
cd obsidian-vault-mcp
```

### 2.2 安装 Python 依赖

```bash
python -m pip install -e .
```

安装完成后，`obsidian-vault-mcp` 命令会自动加入 PATH。

### 2.3 验证安装

将下面命令中的路径替换为你的 Obsidian vault 实际路径：

```bash
obsidian-vault-mcp --doctor --doctor-format text --vault /path/to/your-vault
```

**Windows 示例：**

```bash
obsidian-vault-mcp --doctor --doctor-format text --vault "C:/Users/你的用户名/Documents/MyVault"
```

**macOS/Linux 示例：**

```bash
obsidian-vault-mcp --doctor --doctor-format text --vault ~/Documents/MyVault
```

输出中每项显示 `✓` 表示正常，`✗` 表示该可选集成不可用（不影响核心功能）。

---

## 3. 配置 MCP 客户端

### Claude Code

运行以下命令注册 MCP server：

```bash
claude mcp add obsidian-vault obsidian-vault-mcp
```

或手动编辑 `~/.claude/settings.json`，在 `mcpServers` 中添加：

```json
{
  "mcpServers": {
    "obsidian-vault": {
      "type": "stdio",
      "command": "obsidian-vault-mcp",
      "env": {
        "OBSIDIAN_VAULT_PATH": "auto",
        "OBSIDIAN_CLI_COMMAND": "obsidian"
      }
    }
  }
}
```

`OBSIDIAN_VAULT_PATH=auto` 会自动读取 Obsidian 当前打开的 vault。如果自动检测失败，将 `auto` 替换为你的 vault 绝对路径：

```json
"OBSIDIAN_VAULT_PATH": "C:/Users/你的用户名/Documents/MyVault"
```

配置完成后重启 Claude Code，新工具即可使用。

---

### Codex

仓库根目录已包含 `.mcp.json`，将本目录注册为 Codex 本地插件即可。Codex 会自动读取 `.mcp.json` 中的配置。

---

### OpenCode

将仓库根目录的 `.opencode.json` 复制到你的项目目录，或将 `mcp` 块合并到全局 `~/.opencode.json`：

```json
{
  "mcp": {
    "obsidian-vault": {
      "type": "local",
      "command": ["obsidian-vault-mcp"],
      "environment": {
        "OBSIDIAN_VAULT_PATH": "auto",
        "OBSIDIAN_CLI_COMMAND": "obsidian"
      }
    }
  }
}
```

---

## 4. 验证安装

在 MCP 客户端中输入以下提示词，确认工具可用：

```
展示这个 Obsidian vault 的结构。
```

如果返回 vault 文件列表，说明安装成功。

也可以运行单元测试：

```bash
cd obsidian-vault-mcp
python -m unittest discover -s tests
```

46 个测试全部通过即为正常。

---

## 5. 可选：配置 Zotero 集成

Zotero 集成允许直接从 Zotero 文库搜索文献并导入 Obsidian。

### 5.1 安装 Zotero Desktop

从 [zotero.org/download](https://www.zotero.org/download/) 下载并安装 Zotero（当前版本 9.x）。

### 5.2 确认本地 API 可用

打开 Zotero Desktop，在浏览器或终端访问：

```
http://127.0.0.1:23119/api
```

返回 JSON 数据即表示本地 API 正常运行（Zotero 内置，无需额外配置）。

### 5.3 安装推荐的 Zotero 插件

从各插件的 GitHub Releases 页面下载 `.xpi` 文件，在 Zotero 中通过 **工具 → 附加组件 → 从文件安装** 完成安装：

| 插件 | 作用 | 必要性 | 下载地址 |
|------|------|--------|----------|
| **Better BibTeX for Zotero** | 生成稳定 citekey，用于笔记命名和去重 | 强烈推荐 | [GitHub Releases](https://github.com/retorquere/zotero-better-bibtex/releases) |
| **Ethereal Style (ZoteroStyle)** | 为标注颜色设置自定义名称（如背景/实验/结论），导入 Obsidian 后显示用户定义名称 | 可选 | [GitHub Releases](https://github.com/MuiseDestiny/zotero-style/releases) |
| **Zotero PDF Translate** | 自动翻译 PDF 标注，翻译结果导入 Obsidian 笔记的 Note 字段 | 可选 | [GitHub Releases](https://github.com/windingwind/zotero-pdf-translate/releases) |

### 5.4 测试 Zotero 集成

在 MCP 客户端中输入：

```
搜索 Zotero 中关于 machine learning 的文献，列出前 5 条。
```

---

## 6. 可选：配置 MinerU 文档解析

MinerU 用于将 PDF/Word/PPT 等文档解析为 Markdown 后导入 Obsidian。

### 6.1 安装 MinerU

```bash
pip install -U "mineru[full]"
```

### 6.2 Flash 模式（免费，无需 token）

安装后即可直接使用 flash-extract 模式，无需注册或配置 token：

```
用 MinerU flash-extract 解析这个 PDF 并导入 Obsidian：/path/to/paper.pdf
```

### 6.3 精确模式（需要 MinerU token）

如需更高精度（支持最多 600 页），在 [mineru.net](https://mineru.net) 注册并获取 token，然后在本地环境变量中设置：

```bash
# Windows
set MINERU_API_TOKEN=your_token_here

# macOS/Linux
export MINERU_API_TOKEN=your_token_here
```

> **注意：** 不要将 token 提交到 Git 仓库。

### 6.4 Windows 连通性检查

如果在 Windows 上使用 VPN 或代理，MinerU 下载结果时可能遇到 TLS 错误。运行以下命令检查连通性：

```powershell
curl.exe -I https://mineru.net
curl.exe -I https://cdn-mineru.openxlab.org.cn
```

如果 `cdn-mineru.openxlab.org.cn` 解析到 `198.18.x.x`，需要在代理/VPN 中为以下域名配置直连规则：

- `mineru.net`
- `mineru.oss-cn-shanghai.aliyuncs.com`
- `cdn-mineru.openxlab.org.cn`
- `*.openxlab.org.cn`

---

## 7. Vault 内默认配置

在 vault 根目录创建 `.obsidian-vault-mcp.json`，可以为常用路径设置默认值，避免每次工具调用都手动传参：

```json
{
  "literatureFolder": "01-literature",
  "mineruSourceFolder": "02-sources/mineru",
  "pdfSourceFolder": "02-sources/pdf",
  "entitiesFolder": "entities",
  "conceptsFolder": "concepts",
  "zoteroAttachmentsFolder": "assets/zotero",
  "zoteroAttachmentNameStrategy": "citekey",
  "indexPath": "index.md",
  "logPath": "log.md",
  "templateFolder": "Templates",
  "defaultTemplate": "Literature"
}
```

**字段说明：**

| 字段 | 说明 | 默认值 |
|------|------|--------|
| `literatureFolder` | 文献笔记存放目录 | `literature` |
| `mineruSourceFolder` | MinerU 解析结果存放目录 | `sources` |
| `pdfSourceFolder` | PDF 附件来源笔记目录 | `sources` |
| `entitiesFolder` | 实体页面目录 | `entities` |
| `conceptsFolder` | 概念页面目录 | `concepts` |
| `zoteroAttachmentsFolder` | Zotero PDF 附件存放目录 | `assets/zotero` |
| `zoteroAttachmentNameStrategy` | PDF 附件命名策略：`original`、`zotero_key`、`citekey`、`title_year`、`parent_key` | `original` |
| `indexPath` | wiki 索引文件路径 | `index.md` |
| `logPath` | wiki 日志文件路径 | `log.md` |
| `templateFolder` | 模板目录 | — |
| `defaultTemplate` | 默认模板名称 | — |

---

## 8. 常见问题

### vault 路径无法识别

确认路径指向包含 `.obsidian` 文件夹的目录。如果使用普通 Markdown 文件夹（非 Obsidian vault），需要设置环境变量：

```bash
OBSIDIAN_ALLOW_NON_VAULT=true
```

### Zotero API 无法连接

确认 Zotero Desktop 已打开。默认端口是 `23119`，如需修改：

```json
"ZOTERO_LOCAL_API": "http://127.0.0.1:23119/api"
```

### Obsidian CLI 不可用

Obsidian CLI 内置于 Obsidian 1.12.7+，需要在 Obsidian 中手动开启：**设置 → 高级 → 启用 Obsidian CLI**，并确认 `obsidian` 命令在系统 PATH 中。CLI 不可用时，直接文件读写工具（`obsidian_read_file`、`obsidian_create_note` 等）仍然正常工作。

### 颜色标签不显示用户自定义名称

确认已安装 Ethereal Style (ZoteroStyle) 插件，并在插件设置中配置了颜色名称。修改颜色名称后需要重启 MCP server（重启 MCP 客户端）才能刷新缓存。

### Windows 上 Python 命令找不到

部分 Windows 系统需要用 `python` 而非 `python3`。如果 `obsidian-vault-mcp` 命令找不到，检查 pip 安装路径是否在 PATH 中：

```powershell
python -m obsidian_vault_mcp.cli --doctor --doctor-format text --vault "C:/path/to/vault"
```
