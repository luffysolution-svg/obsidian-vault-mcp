---
name: obsidian-graph
description: "Analyse Obsidian vault citation networks, communities, connectivity, knowledge gaps, and surprising cross-topic links. 引用网络分析、社区检测、知识空白检测、意外关联发现时使用。"
---

1. `obsidian_search` (all `.md`) → `obsidian_read_file` each → extract `[[links]]` with regex.
2. Run Python/networkx via `Bash` for community detection (`nx.community.greedy_modularity_communities`).
3. Compute hubs (high in-degree), orphans (no links), weak components.
4. Suggest: create stub notes for dead links; convert `[text](file.md)` to `[[file]]`; link isolated clusters.
- **Knowledge gaps**: `[n for n in G.nodes if G.degree(n)==0]` (isolated) + communities of size ≤ 2 (sparse) + `nx.bridges(G.to_undirected())` (bridge nodes → expand into index notes).
- **Surprising connections**: find cross-community edges, rank by combined degree, report top 10 as potential interdisciplinary links; suggest wikilink annotation or new bridge note.
