---
layout: default
title: 用户配置
lang: zh-CN
---
# 用户配置

唯一运行时配置文件是 `<Vault>/.obsidian-vault-mcp.json`。`schemaVersion` 是独立的数据格式版本，不等于软件包版本 3.0.0。

`config init` 生成、`config get` 读取、`config validate` 校验该文件。它包括以下顶层配置域：

```text
literature  identity  naming  attachments  frontmatter  note
zotero  bibtex  mineru  analysis  index  base  safety
```

```json
{
  "analysis": {
    "folder": "Literature/Analysis",
    "base": "Literature/Analysis/Analysis.base",
    "fullReadsFolder": "Literature/Analysis/full-reads",
    "reviewsFolder": "Literature/Analysis/reviews",
    "passageQaFolder": "Literature/Analysis/qa/passages",
    "figureQaFolder": "Literature/Analysis/qa/figures",
    "conceptsFolder": "Literature/Analysis/concepts"
  }
}
```

所有 Vault 可见路径必须为相对路径并保持在 Vault 内。配置没有 `defaultDryRunForMigration` 字段。

## Analysis 意图

直接用自然语言表达重点，例如：“请重点分析催化机制、表征证据和实验条件，不需要大段复述引言。”工作流会写入如 `analysisFocus` 的结果字段；用户不需要维护复杂模板。

## Skills 自定义

每个 `SKILL.md` 的 `## User Customizations` 区域用于长期偏好。安装器仅替换受管理区域，保留这一区域；同时记录受管理内容和 reference 的哈希，遇到用户改动会拒绝覆盖。OpenCode 的实际目录是 `<project>/.opencode/skills/`；其他客户端的目标由各自 installer 返回，不能靠文档猜测。
