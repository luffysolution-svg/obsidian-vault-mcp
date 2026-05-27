# Design: Graph Intelligence Upgrade (4-Signal Model + Louvain)

**Date:** 2026-05-27
**Status:** Approved
**Scope:** Upgrade `obsidian_suggest_graph_improvements`; add `obsidian_build_graph_communities` and `obsidian_graph_insights`
**Inspired by:** [llm_wiki](https://github.com/nashsu/llm_wiki) — 4-signal relevance model, Louvain community detection, graph insights

---

## Problem

`obsidian_suggest_graph_improvements` currently uses only unresolved-link detection and simple reciprocal-link suggestions. There is no scoring, no awareness of shared academic sources, and no community structure. For academic vaults with Zotero citations, MinerU extractions, and entity/concept notes, this misses high-value connections.

---

## Architecture Overview

### New Dependency

- `pyproject.toml`: add `networkx>=3.0` to `[project.dependencies]`
  - Louvain community detection is built into networkx 3.x (`networkx.algorithms.community.louvain_communities`)
  - No additional `python-louvain` package required

### Tool Changes

| Tool | Change Type | Description |
|---|---|---|
| `obsidian_suggest_graph_improvements` | Upgrade | Add `use_scoring: bool = False` parameter; when `True`, each suggestion includes `score` and `signals` breakdown |
| `obsidian_build_graph_communities` | **New** | Louvain community detection; optionally writes `community` field to note frontmatter |
| `obsidian_graph_insights` | **New** | Detects bridge nodes, surprising cross-community links, sparse clusters, isolated hubs |

### New Internal Helpers (helpers.py)

- `_build_nx_graph(graph_data) -> nx.Graph` — converts `obsidian_build_graph` output to a networkx Graph; reuses existing mtime-based cache
- `_build_source_index(vault) -> dict[str, set[str]]` — maps each note path to its set of "sources" (see below)
- `_compute_source_overlap(sources_a, sources_b) -> float` — Jaccard similarity between two source sets
- `_get_node_type(props) -> str` — extracts `type` frontmatter field, defaults to `"note"`

### Architecture Principles

- The networkx Graph object is **not cached separately** — it is rebuilt from the already-cached `obsidian_build_graph` data on each call (low cost)
- Source overlap is extracted from frontmatter fields: `zoteroKey`, `cites`, `references`, `mineru_markdown`, `entities`, `concepts`, and the first 5 `tags`
- Type affinity: `type: literature` ↔ `type: literature` gets ×1.0 bonus; cross-type gets 0 (no penalty)

---

## Section 1: 4-Signal Scoring Engine

### `_compute_node_scores(G, source_index, max_pairs)` Logic

For each unconnected node pair `(u, v)` with source overlap > 0:

```
score(u, v) =
    3.0 * link_signal(u, v)         # 1 if already linked, else 0 (used as filter, not for suggestions)
  + 4.0 * source_overlap(u, v)      # Jaccard similarity of source sets
  + 1.5 * adamic_adar(u, v)         # networkx adamic_adar_index
  + 1.0 * type_affinity(u, v)       # 1 if same type, 0 otherwise
```

### Signal Calculation Details

**source_overlap(u, v):**
```
Jaccard = |sources(u) ∩ sources(v)| / max(|sources(u)|, |sources(v)|, 1)
result  = 4.0 * Jaccard
```

**Sources set for a node:**
```
sources(node) =
  { zoteroKey value }
  ∪ { targets extracted from cites wikilinks }
  ∪ { targets extracted from references wikilinks }
  ∪ { targets extracted from mineru_markdown wikilinks }
  ∪ { entities field values }
  ∪ { concepts field values }
  ∪ { first 5 tags }
```

**adamic_adar(u, v):**
- Uses `networkx.adamic_adar_index(G, [(u, v)])`
- Only computed for node pairs where `source_overlap > 0` (reduces computation space from O(N²) to O(source-connected pairs))
- Performance guard: `max_pairs=500` default; if candidate pairs exceed this, top `max_pairs` by source overlap are taken first

**type_affinity(u, v):**
- `1.0` if `_get_node_type(props_u) == _get_node_type(props_v)`, else `0.0`

### Output Format (upgraded `obsidian_suggest_graph_improvements` entry)

```json
{
  "from": "literature/chen2023.md",
  "to": "concepts/gibbs-free-energy.md",
  "score": 7.23,
  "signals": {
    "sourceOverlap": 4.0,
    "adamicAdar": 2.12,
    "typeAffinity": 1.0,
    "directLink": 0.0
  },
  "reason": "共享来源 4 项；2 个共同邻居"
}
```

### Backward Compatibility

`use_scoring=False` (default) preserves existing output format exactly — no breaking change.

---

## Section 2: `obsidian_build_graph_communities`

### Interface

```python
obsidian_build_graph_communities(
    vault_path: str = "",
    folder: str = "",
    min_community_size: int = 3,       # ignore communities smaller than N nodes
    write_frontmatter: bool = False,   # if True, writes community: field to each note
    dry_run: bool = True,
    resolution: float = 1.0,           # Louvain resolution; higher = smaller communities
) -> dict[str, Any]
```

### Return Structure

```json
{
  "ok": true,
  "communityCount": 8,
  "modularity": 0.47,
  "communities": [
    {
      "id": 0,
      "size": 23,
      "label": "化工热力学",
      "topNodes": ["thermodynamics.md", "entropy.md", "gibbs-free-energy.md"],
      "dominantTags": ["thermodynamics", "heat-transfer"]
    }
  ],
  "written": 23,
  "dryRun": true
}
```

### Key Design Decisions

- **`modularity`** score reflects partition quality (0.3–0.7 is the typical meaningful range); surfaced to help users tune `resolution`
- **`label`** is automatically derived from the highest-inDegree node's `title` frontmatter within the community
- **`write_frontmatter=True`** writes `community: <label>` to each note's YAML frontmatter — enables Dataview queries and Obsidian Bases views filtered by community
- **`dry_run=True`** (default): analysis only, no file writes
- **`dominantTags`**: top 3 most frequent tags across community members, for quick human inspection

---

## Section 3: `obsidian_graph_insights`

### Interface

```python
obsidian_graph_insights(
    vault_path: str = "",
    folder: str = "",
    top_n: int = 20,
) -> dict[str, Any]
```

### Four Insight Categories

**1. Bridge Nodes**
- Low degree centrality but high betweenness centrality
- These are cross-community connectors that are under-linked and easily missed
- Detection: `betweenness > 0.1` and `degree < median_degree`

**2. Surprising Cross-Community Links**
- Node pairs from different Louvain communities with high `source_overlap` score (> 2.0)
- Indicates knowledge affinity not reflected in the vault's category structure
- These are the most actionable: suggested links the user hasn't made yet

**3. Sparse Clusters**
- Louvain communities with internal edge density < 0.2
- Signal: community members were grouped together but are weakly connected internally
- Suggestion: consider splitting or adding more cross-links within the cluster

**4. Isolated Hubs**
- Notes with high `outDegree` (≥ 5) but very low `inDegree` (≤ 1)
- They reference many other pages but nothing points to them
- These are important concept nodes that need backlinks

### Return Structure

```json
{
  "ok": true,
  "bridgeNodes": [
    {
      "path": "concepts/gibbs-free-energy.md",
      "betweenness": 0.43,
      "degree": 4,
      "community": "热力学",
      "title": "Gibbs Free Energy"
    }
  ],
  "surprisingLinks": [
    {
      "from": "literature/chen2023.md",
      "to": "concepts/catalysis.md",
      "sourceOverlapScore": 3.8,
      "fromCommunity": "反应工程",
      "toCommunity": "催化剂设计",
      "reason": "共享来源 4 项"
    }
  ],
  "sparseClusters": [
    {
      "community": "传质传热",
      "density": 0.12,
      "nodeCount": 8,
      "suggestion": "考虑拆分为子社区或在内部添加更多关联链接"
    }
  ],
  "isolatedHubs": [
    {
      "path": "literature/zhang2024.md",
      "outDegree": 12,
      "inDegree": 0,
      "title": "Zhang 2024"
    }
  ]
}
```

---

## Files to Change

| File | Change |
|---|---|
| `pyproject.toml` | Add `networkx>=3.0` to `[project.dependencies]` |
| `scripts/obsidian_vault_mcp/helpers.py` | Add `_build_nx_graph()`, `_build_source_index()`, `_compute_source_overlap()`, `_get_node_type()`, `_compute_node_scores()` |
| `scripts/obsidian_vault_mcp/tools.py` | Add `obsidian_build_graph_communities`, `obsidian_graph_insights`; upgrade `obsidian_suggest_graph_improvements` with `use_scoring` parameter |
| `tests/test_obsidian_vault_mcp.py` | New test cases (12 tests) |

No new files required beyond the spec.

---

## Testing Plan

Tests follow TDD order (write failing test → implement → pass):

### Task 1: Core helpers + `obsidian_suggest_graph_improvements` upgrade

```
test_suggest_graph_improvements_with_scoring_returns_score_field
test_suggest_graph_improvements_source_overlap_boosts_score
test_suggest_graph_improvements_use_scoring_false_preserves_old_format
test_source_index_extracts_zotero_key
test_source_index_extracts_cites_wikilinks
test_source_overlap_jaccard_correct
```

### Task 2: `obsidian_build_graph_communities`

```
test_build_graph_communities_returns_community_list
test_build_graph_communities_min_size_filters_small_groups
test_build_graph_communities_dry_run_does_not_write_frontmatter
test_build_graph_communities_write_frontmatter_adds_community_field
```

### Task 3: `obsidian_graph_insights`

```
test_graph_insights_detects_bridge_nodes
test_graph_insights_detects_isolated_hubs
test_graph_insights_detects_surprising_cross_community_links
test_graph_insights_sparse_clusters_flagged
```

---

## Implementation Order

1. **Task 1** — helpers + `obsidian_suggest_graph_improvements` upgrade (foundation for Tasks 2 and 3)
2. **Task 2** — `obsidian_build_graph_communities` (depends on `_build_nx_graph`)
3. **Task 3** — `obsidian_graph_insights` (depends on both Task 1 scoring + Task 2 community labels)
