---
name: obsidian-graph
description: "Analyse the citation and wikilink graph of an Obsidian vault using networkx. Use when the user needs citation network construction, community detection, connectivity metrics, or graph improvement suggestions. 当用户需要引用网络分析、社区检测、连通性指标或图谱改善建议时使用。"
---

# Obsidian Graph Analysis

Use `obsidian_search` and `obsidian_read_file` to gather vault data, then run Python/networkx analysis via `Bash`.

## Citation Network

**Steps:**
1. `obsidian_search` with `query=""`, `extensions=".md"` — get all notes.
2. For each note, `obsidian_read_file` and extract:
   - Outgoing links: regex `\[\[([^\]|#]+)` on the file body.
   - Zotero citekey from frontmatter `citekey` field.
3. Write a Python script and run with `Bash`:

```python
import json, re, pathlib, sys

vault = sys.argv[1]
notes = {}
for md in pathlib.Path(vault).rglob("*.md"):
    rel = str(md.relative_to(vault))
    text = md.read_text(encoding="utf-8", errors="ignore")
    links = re.findall(r'\[\[([^\]|#\n]+)', text)
    notes[rel] = links

edges = []
for src, targets in notes.items():
    for tgt in targets:
        edges.append({"source": src, "target": tgt + ".md"})

print(json.dumps({"nodeCount": len(notes), "edgeCount": len(edges), "edges": edges[:100]}, indent=2))
```

Run: `python graph_build.py "<vault_path>"`

## Community Detection

```python
import networkx as nx, json, sys

data = json.loads(sys.argv[1])
G = nx.DiGraph()
for e in data["edges"]:
    G.add_edge(e["source"], e["target"])

U = G.to_undirected()
communities = list(nx.community.greedy_modularity_communities(U))
result = [{"community": i, "nodes": list(c)[:10], "size": len(c)}
          for i, c in enumerate(communities)]
print(json.dumps(result, indent=2))
```

## Connectivity Metrics

From the directed graph, compute:
- **Hub nodes**: high in-degree (most-cited notes).
- **Authority nodes**: high out-degree (index/survey notes).
- **Orphans**: in-degree = 0 and out-degree = 0.
- **Weakly connected components**: isolated clusters.

```python
import networkx as nx
hubs = sorted(G.in_degree(), key=lambda x: x[1], reverse=True)[:10]
orphans = [n for n in G.nodes if G.in_degree(n) == 0 and G.out_degree(n) == 0]
components = list(nx.weakly_connected_components(G))
```

## Graph Improvement Suggestions

After computing metrics, suggest:
1. **Create missing notes**: For each dead link target, suggest `obsidian_write_file` to create a stub.
2. **Convert markdown links**: Find `[text](file.md)` patterns → suggest converting to `[[file]]`.
3. **Connect isolated clusters**: Find thematically related notes between clusters (by tag overlap) and suggest wikilinks.
4. **Remove orphans**: List orphan notes and ask the user if they should be linked or deleted.

---

## 中文说明

通过 `obsidian_search` + `obsidian_read_file` 收集 vault 数据，用 Bash 运行 Python/networkx 脚本完成引用网络构建、社区检测和连通性分析。分析结果转化为可操作的 `obsidian_write_file` 建议。
