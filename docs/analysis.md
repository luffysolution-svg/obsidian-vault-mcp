---
layout: default
title: Analysis 与 Skills
lang: zh-CN
---
# Analysis 与 Skills

## 五类 Analysis

| 类型 | 用途 | 输出目录 |
|---|---|---|
| `full_read` | 单篇完整阅读 | `Analysis/full-reads/` |
| `literature_review` | 多篇综述或比较 | `Analysis/reviews/` |
| `passage_qa` | 定位到段落的问题 | `Analysis/qa/passages/` |
| `figure_qa` | 图、表、scheme、公式解释 | `Analysis/qa/figures/` |
| `concept` | 跨论文概念学习 | `Analysis/concepts/` |

`Literature/Analysis/Analysis.base` 是这五类笔记的唯一确定性 Base 视图。profile 可为 `general`、`medicine`、`chemistry`、`materials`、`catalysis`、`physics`、`mathematics`；status 可为 `draft`、`ready`、`reviewed`、`needs_update`、`archived`。稳定 `analysisId`、源指纹和 source key 用于去重与更新检测；源改变只标记 `needs_update`，不会静默重写用户内容。系统仅管理受管理区，用户拥有区会被保留。

## 七个 Skills

| Skill | 典型触发 |
|---|---|
| `paper-qa` | “这篇论文的关键结论是什么？” |
| `full-read` | “完整阅读这篇论文” |
| `passage-qa` | “这段实验条件如何支持结论？” |
| `figure-qa` | “解释图 3 / 这个公式” |
| `compare-papers` | “比较这些论文的方法和结果” |
| `literature-review` | “围绕该主题做文献综述” |
| `concept-learning` | “跨论文学习这个概念” |

Skills 编排科研工作流；读取、检索和写入仍由正式 MCP Tools 执行。它们不是独立数据库或独立 Agent。
