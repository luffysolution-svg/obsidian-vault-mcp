# 隐私说明

本插件通过本地 MCP stdio server 运行。插件本身不会主动把 vault 文件、Zotero 元数据、PDF 文本或 Obsidian CLI 输出发送到外部服务。

使用该 MCP server 的 host 应用可以读取工具返回的数据。请确认你信任该 host，并阅读它自己的隐私政策。

## 本地数据访问范围

插件可能访问：

- 配置的 Obsidian vault 内文件。
- Zotero Desktop 本地 API：`http://127.0.0.1:23119/api`，仅当 Zotero 正在运行且可访问时。
- Zotero 附件引用的本地 PDF 文件。
- 安装并调用 Obsidian CLI 时的 CLI 输出。
- 安装并调用 MinerU Open API CLI 时的 CLI 输出。

## 配置隐私

仓库中不包含任何绝对 vault 路径。默认 `OBSIDIAN_VAULT_PATH=auto`，会通过本地 Obsidian CLI 获取当前活动 vault。用户可以在自己的本地 `.mcp.json` 或 host 配置中设置显式 vault 路径。

默认拒绝非 vault 文件夹，除非用户明确设置：

```text
OBSIDIAN_ALLOW_NON_VAULT=true
```

导入已有 MinerU Markdown 或使用 `flash-extract` 不需要 MinerU token。精确解析 `extract` 可能使用本地 CLI 配置、环境变量或显式工具参数中的 token。
