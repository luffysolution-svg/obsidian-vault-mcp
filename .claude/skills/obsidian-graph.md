---
name: obsidian-graph
description: "Analyse Obsidian vault citation networks, graph communities, and connectivity. 引用网络分析、社区检测、图谱指标时使用。"
---

1. `obsidian_search` (all `.md`) → `obsidian_read_file` each → extract `[[links]]` with regex.
2. Run Python/networkx via `Bash` for community detection (`nx.community.greedy_modularity_communities`).
3. Compute hubs (high in-degree), orphans (no links), weak components.
4. Suggest: create stub notes for dead links; convert `[text](file.md)` to `[[file]]`; link isolated clusters.
