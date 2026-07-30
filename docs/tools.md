---
layout: default
title: MCP Tools 参考
lang: zh-CN
---
# MCP Tools 参考

这是由运行时注册表约束的 31 工具表；`uv run python scripts/check_docs.py --check` 会检查中英文页的名称与计数。写入型工具以 `--dry-run` 预览；“修改 Vault”是该工具在非 dry-run 时可能写入 Vault 的含义。

## 版本、系统与配置

| 工具 | 属性 / 主要用途 | 核心参数 | dry-run | 修改 Vault |
|---|---|---|---|---|
| `literature_version` | 读；版本与能力契约 | 无 | 否 | 否 |
| `literature_doctor` | 读；诊断配置和依赖 | `vault_path` | 否 | 否 |
| `literature_config_get` | 读；读取有效配置 | `vault_path` | 否 | 否 |
| `literature_config_validate` | 读；校验配置 | `config_json`, `vault_path` | 否 | 否 |
| `literature_config_initialize` | 写；初始化配置 | `vault_path`, `conflict_policy` | 是 | 是 |

## Zotero

| 工具 | 属性 / 主要用途 | 核心参数 | dry-run | 修改 Vault |
|---|---|---|---|---|
| `zotero_ping` | 读；探测本地 API | `api_base` | 否 | 否 |
| `zotero_search_items` | 读；搜索条目 | `query`, `item_type`, `tag` | 否 | 否 |
| `zotero_list_collections` | 读；列出 collection | `api_base` | 否 | 否 |
| `zotero_get_item` | 读；读取条目 | `key` | 否 | 否 |
| `zotero_get_children` | 读；读取子项/附件 | `parent_key` | 否 | 否 |
| `zotero_get_bibtex` | 读；取得 BibTeX | `key`, `provider` | 否 | 否 |

## 导入与同步

| 工具 | 属性 / 主要用途 | 核心参数 | dry-run | 修改 Vault |
|---|---|---|---|---|
| `literature_import_item` | 写；导入父条目 | `zotero_key`, `vault_path` | 是 | 是 |
| `literature_import_collection` | 写；导入 collection | `collection_key`, `vault_path` | 是 | 是 |
| `literature_sync_item` | 写；同步父条目 | `zotero_key`, `vault_path` | 是 | 是 |
| `literature_sync_collection` | 写；同步 collection | `collection_key`, `vault_path` | 是 | 是 |

## MinerU

| 工具 | 属性 / 主要用途 | 核心参数 | dry-run | 修改 Vault |
|---|---|---|---|---|
| `literature_parse_mineru` | 写；解析一篇 PDF | `zotero_key`, `vault_path` | 是 | 是 |
| `literature_parse_mineru_batch` | 写；批量解析 | `zotero_keys`, `vault_path` | 是 | 是 |
| `literature_remove_mineru_output` | 写；移除派生输出 | `zotero_key`, `vault_path` | 是 | 是 |

## 导航与校验

| 工具 | 属性 / 主要用途 | 核心参数 | dry-run | 修改 Vault |
|---|---|---|---|---|
| `literature_rebuild_index` | 写；重建 Literature index | `vault_path` | 是 | 是 |
| `literature_rebuild_base` | 写；重建 Literature Base | `vault_path` | 是 | 是 |
| `literature_verify` | 读；校验身份、链接和资源 | `vault_path` | 否 | 否 |
| `literature_paper_read` | 读；有界单篇阅读 | `zotero_key`, `mode`, `query` | 否 | 否 |
| `literature_retrieve` | 读；跨论文检索 | `query`, `intent`, `depth` | 否 | 否 |

## Analysis

| 工具 | 属性 / 主要用途 | 核心参数 | dry-run | 修改 Vault |
|---|---|---|---|---|
| `literature_analysis_get` | 读；按稳定 ID 或问题查询 | `analysis_id`, `analysis_type`, `source_key` | 否 | 否 |
| `literature_analysis_write` | 写；安全写入 Analysis | `fields`, `managed_content`, `vault_path` | 是 | 是 |
| `literature_rebuild_analysis_base` | 写；重建 Analysis.base | `vault_path` | 是 | 是 |

## Wiki

| 工具 | 属性 / 主要用途 | 核心参数 | dry-run | 修改 Vault |
|---|---|---|---|---|
| `literature_wiki_context` | 读；收集本地上下文 | `topic`, `vault_path` | 否 | 否 |
| `literature_wiki_write` | 写；写入可追溯主题 | `topic`, `content`, `zotero_keys` | 是 | 是 |
| `literature_wiki_list` | 读；列出主题元数据 | `vault_path` | 否 | 否 |

## 事务

| 工具 | 属性 / 主要用途 | 核心参数 | dry-run | 修改 Vault |
|---|---|---|---|---|
| `literature_preview_transaction` | 读；读取事务 manifest | `transaction_id`, `vault_path` | 否 | 否 |
| `literature_rollback_transaction` | 写；预览或回滚事务 | `transaction_id`, `vault_path` | 是 | 是 |
