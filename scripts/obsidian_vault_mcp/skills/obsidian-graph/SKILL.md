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

## Knowledge Gap Detection

Run after building the graph (see "Citation Network" above). Identifies notes and clusters that are under-connected.

```python
import networkx as nx

# 1. Isolated nodes — no edges at all
gaps = [n for n in G.nodes if G.degree(n) == 0]
print(f"Isolated notes ({len(gaps)}):", gaps[:20])

# 2. Sparse communities — single-node or two-node clusters after community detection
sparse = [list(c) for c in communities if len(c) <= 2]
print(f"Sparse communities ({len(sparse)}):", sparse)

# 3. Bridge nodes — their removal would disconnect the graph
bridges = list(nx.bridges(G.to_undirected()))
bridge_nodes = {u for u, v in bridges} | {v for u, v in bridges}
print(f"Bridge nodes ({len(bridge_nodes)}):", list(bridge_nodes)[:10])
```

**Report to the user:**
- **Isolated notes** → suggest `obsidian_search` by tag overlap to find candidate notes to link, or ask whether to delete.
- **Sparse single-paper communities** → these topics have no neighbors; suggest importing related Zotero items.
- **Bridge notes** → held two clusters together; flag as candidates to expand into proper index notes with `obsidian_write_file`.

## Surprising Connections

Run after community detection. Finds high-value cross-community edges that may represent unexpected interdisciplinary links.

```python
# Map each node to its community index
node_to_community = {}
for i, c in enumerate(communities):
    for n in c:
        node_to_community[n] = i

# Cross-community edges
cross_edges = [
    (u, v) for u, v in G.edges()
    if node_to_community.get(u) != node_to_community.get(v)
]

# Rank by combined degree — high-degree cross-community links are most surprising
cross_edges.sort(
    key=lambda e: G.degree(e[0]) + G.degree(e[1]),
    reverse=True
)

print("Top surprising connections:")
for u, v in cross_edges[:10]:
    print(f"  [{node_to_community[u]}] {u}  →  [{node_to_community[v]}] {v}")
```

**Report to the user:** For each of the top 10 cross-community connections, describe which two thematic clusters they bridge (using community member note names as cluster labels). Suggest:
- Adding a wikilink annotation explaining the connection, or
- Creating a new bridge note that synthesizes the two lines of work.

## Eval Scenarios

- **Trigger:** "Find isolated literature notes." Expected: build a wikilink graph from vault Markdown and report isolated nodes. Must not delete or edit notes.
- **Trigger:** "Where are the knowledge gaps in this research vault?" Expected: compute isolated notes, sparse communities, and bridge nodes, then recommend candidate links or new index notes. Must mark recommendations as suggestions unless the user asks to apply them.
- **Trigger:** "Show surprising interdisciplinary links." Expected: detect cross-community edges and explain why they bridge clusters. Must not invent relationships that are not supported by existing links/tags.
