---
layout: default
title: 本地优先的文献研究工作流
lang: zh-CN
description: 连接 Zotero、MinerU、Obsidian 与 AI Agent 的本地优先文献研究工作流。
---

# Obsidian Vault MCP

<p class="lead">连接 Zotero、MinerU、Obsidian 与 AI Agent 的本地优先文献研究工作流。</p>

<span class="badge">Version {{ site.release_version }}</span>

[快速开始](quickstart/){:.button} [完整安装](installation/){:.button} [GitHub](https://github.com/luffysolution-svg/obsidian-vault-mcp){:.button} [更新日志](changelog/){:.button}

{% include release-notice.html %}

## 从文献到知识库

```text
Zotero Desktop → 稳定 zoteroKey → Markdown 主笔记 + PDF
→ MinerU 全文、图片与公式 → 31 MCP Tools → 7 Agent Skills
→ 5 类 Analysis → Obsidian Base 与知识库
```

<div class="grid"><div class="card"><div class="metric">31</div>MCP Tools</div><div class="card"><div class="metric">7</div>Agent Skills</div><div class="card"><div class="metric">5</div>Analysis Types</div><div class="card"><div class="metric">1</div>Analysis Base</div></div>

## 核心能力

<div class="grid"><div class="card"><h3>Zotero 与附件</h3>以父条目 `zoteroKey` 作为稳定身份，导入、同步并管理 PDF。</div><div class="card"><h3>MinerU</h3>解析全文、图片和公式，并写入按论文隔离的相对路径。</div><div class="card"><h3>Analysis 与 Wiki</h3>五类结构化分析、Literature/Analysis Base 与可追溯 Wiki。</div><div class="card"><h3>可恢复写入</h3>dry-run、事务、备份、冲突保护、原子替换和 rollback。</div><div class="card"><h3>Agent 工作流</h3>支持 Codex、Claude Code、OpenCode、Pi、Hermes 与 WorkBuddy。</div></div>

## 快速安装（发布后）

```bash
uv tool install "zotero-obsidian-mcp==3.0.1"
obsidian-vault-mcp --help
obsidian-vault-mcp call literature_version --json '{}'
```

```bash
uvx --from "zotero-obsidian-mcp==3.0.1" obsidian-vault-mcp --help
```

## 文档

<div class="grid"><div class="card"><h3><a href="installation/">完整安装</a></h3>环境、包管理器、Vault、Zotero、MinerU、验证与隐私。</div><div class="card"><h3><a href="configuration/">用户配置</a></h3>唯一 Vault 配置文件、Schema 与 Skill 自定义区域。</div><div class="card"><h3><a href="zotero/">Zotero 导入与同步</a></h3>父条目、附件和同步策略。</div><div class="card"><h3><a href="mineru/">MinerU 解析</a></h3>全文章节、图片、公式与事务输出。</div><div class="card"><h3><a href="analysis/">Analysis 与 Skills</a></h3>五类输出、Analysis.base 和七个工作流。</div><div class="card"><h3><a href="agents/">Agent 客户端</a></h3>实际安装器支持的客户端与方式。</div><div class="card"><h3><a href="tools/">MCP Tools</a></h3>由运行时注册表生成的 31 工具参考。</div><div class="card"><h3><a href="troubleshooting/">故障排查</a></h3>doctor、verify、路径和客户端问题。</div><div class="card"><h3><a href="development/">开发与贡献</a></h3>Pages 来源、测试和贡献方式。</div></div>

## 实际界面

![Obsidian 中的 Literature Base](assets/screenshots/v2/literature-base.png)

[English documentation](en/)
