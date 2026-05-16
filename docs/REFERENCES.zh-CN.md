# 参考与致谢

本插件是一个原创的本地 Codex 插件，用于 Obsidian vault 操作；设计上明确参考了几个公开项目和官方文档。

## Kepano Obsidian Skills

参考：<https://github.com/kepano/obsidian-skills>

借鉴点：

- 把 Obsidian 工作拆成多个小而可组合的 skill，而不是一个巨大的提示词文件。
- 将 Markdown、wikilinks、JSON Canvas、Bases、CLI、提取工作流视为不同概念面。
- 优先使用 Obsidian 原生格式，让生成文件不依赖自定义运行时也能使用。

本插件的改造：

- 随插件发布一组可组合的 skills，分别覆盖通用 vault 操作、Zotero 导入、MinerU 提取、视图构建和 Obsidian CLI 工作流。
- MCP server 提供 list、read、write、frontmatter、wikilink、graph、Canvas、Base 和 CLI 工具。
- `obsidian-markdown`、`json-canvas`、`obsidian-bases` 等技能仍可作为格式权威。
- MinerU 作为可选外部解析器；插件可导入已有 Markdown，也可调用本地 `mineru-open-api` CLI。

## Karpathy LLM Wiki

参考：<https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>

借鉴点：

- 把 Obsidian 当作持久化、持续复利的知识库 IDE。
- 让 LLM 维护交叉引用、主题页、来源摘要、索引页、日志和图谱健康。
- 把有价值的回答写回 wiki，而不是只留在聊天历史里。

本插件的改造：

- 笔记可以带稳定 YAML properties 和 wikilinks。
- 可从 vault 构建图谱，发现 backlinks、dead ends、orphans、unresolved links 和 tags。
- Canvas 文件可以可视化主题聚类。
- Bases 文件可以把 frontmatter 和文件元数据变成可筛选视图。

## 操作文档参考

安装、配置和集成文档依赖以下官方资料：

- Obsidian CLI: https://help.obsidian.md/cli
- Codex Skills: https://developers.openai.com/codex/skills
- Codex Plugins: https://developers.openai.com/codex/plugins
- Codex plugin authoring: https://developers.openai.com/codex/plugins/build
- Zotero connector HTTP server: https://www.zotero.org/support/dev/client_coding/connector_http_server
- Zotero Web API v3 basics: https://www.zotero.org/support/dev/web_api/v3/basics
- MinerU Open API CLI: https://pkg.go.dev/github.com/opendatalab/MinerU-Ecosystem/cli
- MinerU Ecosystem: https://github.com/opendatalab/MinerU-Ecosystem

## 演示截图

本版本暂不内置截图，后续版本可能会添加。
