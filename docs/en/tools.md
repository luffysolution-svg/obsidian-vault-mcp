---
layout: default
title: MCP Tools reference
lang: en
---
# MCP Tools reference

This is the 31-tool table constrained by the runtime registry. `uv run python scripts/check_docs.py --check` verifies the names and counts on both language pages. Write tools accept `--dry-run` for preview; “Changes Vault” means a non-dry-run call can write inside the Vault.

## Version, system, and configuration

| Tool | Access / primary use | Core parameters | dry-run | Changes Vault |
|---|---|---|---|---|
| `literature_version` | Read; version and capability contract | none | No | No |
| `literature_doctor` | Read; diagnose configuration and dependencies | `vault_path` | No | No |
| `literature_config_get` | Read; effective configuration | `vault_path` | No | No |
| `literature_config_validate` | Read; validate configuration | `config_json`, `vault_path` | No | No |
| `literature_config_initialize` | Write; initialize configuration | `vault_path`, `conflict_policy` | Yes | Yes |

## Zotero

| Tool | Access / primary use | Core parameters | dry-run | Changes Vault |
|---|---|---|---|---|
| `zotero_ping` | Read; probe the local API | `api_base` | No | No |
| `zotero_search_items` | Read; search items | `query`, `item_type`, `tag` | No | No |
| `zotero_list_collections` | Read; list collections | `api_base` | No | No |
| `zotero_get_item` | Read; retrieve one item | `key` | No | No |
| `zotero_get_children` | Read; retrieve children/attachments | `parent_key` | No | No |
| `zotero_get_bibtex` | Read; retrieve BibTeX | `key`, `provider` | No | No |

## Import and sync

| Tool | Access / primary use | Core parameters | dry-run | Changes Vault |
|---|---|---|---|---|
| `literature_import_item` | Write; import a parent item | `zotero_key`, `vault_path` | Yes | Yes |
| `literature_import_collection` | Write; import a collection | `collection_key`, `vault_path` | Yes | Yes |
| `literature_sync_item` | Write; synchronize a parent item | `zotero_key`, `vault_path` | Yes | Yes |
| `literature_sync_collection` | Write; synchronize a collection | `collection_key`, `vault_path` | Yes | Yes |

## MinerU

| Tool | Access / primary use | Core parameters | dry-run | Changes Vault |
|---|---|---|---|---|
| `literature_parse_mineru` | Write; parse one PDF | `zotero_key`, `vault_path` | Yes | Yes |
| `literature_parse_mineru_batch` | Write; batch parsing | `zotero_keys`, `vault_path` | Yes | Yes |
| `literature_remove_mineru_output` | Write; remove derived output | `zotero_key`, `vault_path` | Yes | Yes |

## Navigation and verification

| Tool | Access / primary use | Core parameters | dry-run | Changes Vault |
|---|---|---|---|---|
| `literature_rebuild_index` | Write; rebuild Literature index | `vault_path` | Yes | Yes |
| `literature_rebuild_base` | Write; rebuild Literature Base | `vault_path` | Yes | Yes |
| `literature_verify` | Read; verify identities, links, assets | `vault_path` | No | No |
| `literature_paper_read` | Read; bounded single-paper reading | `zotero_key`, `mode`, `query` | No | No |
| `literature_retrieve` | Read; cross-paper retrieval | `query`, `intent`, `depth` | No | No |

## Analysis

| Tool | Access / primary use | Core parameters | dry-run | Changes Vault |
|---|---|---|---|---|
| `literature_analysis_get` | Read; query by stable ID or question | `analysis_id`, `analysis_type`, `source_key` | No | No |
| `literature_analysis_write` | Write; safely write Analysis | `fields`, `managed_content`, `vault_path` | Yes | Yes |
| `literature_rebuild_analysis_base` | Write; rebuild Analysis.base | `vault_path` | Yes | Yes |

## Wiki

| Tool | Access / primary use | Core parameters | dry-run | Changes Vault |
|---|---|---|---|---|
| `literature_wiki_context` | Read; collect local context | `topic`, `vault_path` | No | No |
| `literature_wiki_write` | Write; write a traceable topic | `topic`, `content`, `zotero_keys` | Yes | Yes |
| `literature_wiki_list` | Read; list topic metadata | `vault_path` | No | No |

## Transactions

| Tool | Access / primary use | Core parameters | dry-run | Changes Vault |
|---|---|---|---|---|
| `literature_preview_transaction` | Read; read a transaction manifest | `transaction_id`, `vault_path` | No | No |
| `literature_rollback_transaction` | Write; preview or roll back a transaction | `transaction_id`, `vault_path` | Yes | Yes |
