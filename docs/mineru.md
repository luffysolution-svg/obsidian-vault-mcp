---
layout: default
title: MinerU 解析
lang: zh-CN
---
# MinerU 解析

配置 MinerU Open API CLI 后，解析从隐藏 staging 开始；只有 Markdown 选择、图片改名与相对链接校验都成功，文件才会作为同一事务提交。

```bash
obsidian-vault-mcp mineru parse ABCD1234 --vault-path "<VAULT_PATH>" --dry-run
obsidian-vault-mcp mineru parse-batch ABCD1234 EFGH5678 --vault-path "<VAULT_PATH>" --dry-run
```

标准输出：

```text
Literature/attachment/MinerU/{zoteroKey}.md
Literature/attachment/MinerU/image/{zoteroKey}/{zoteroKey}-figNN.ext
```

Markdown 使用相对链接，如 `![](image/ABCD1234/ABCD1234-fig01.png)`。任何单篇失败不会发布部分输出。
