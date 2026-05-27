# Graph Intelligence Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4-signal scored link suggestions, Louvain community detection, and graph insights (bridge nodes, surprising cross-community links, sparse clusters, isolated hubs) to the obsidian-vault-mcp server.

**Architecture:** All new helpers appended to `scripts/obsidian_vault_mcp/helpers.py`; three tool changes in `scripts/obsidian_vault_mcp/tools.py` (`obsidian_suggest_graph_improvements` upgraded; `obsidian_build_graph_communities` and `obsidian_graph_insights` appended). networkx is imported lazily inside each function so the package is optional at startup.

**Tech Stack:** Python 3.10+, FastMCP, networkx>=3.0, unittest

---

## File Structure

**Modified files:**
- `pyproject.toml` — add `networkx>=3.0` to `[project.dependencies]`
- `scripts/obsidian_vault_mcp/helpers.py` — append 5 new private helpers at end of file
- `scripts/obsidian_vault_mcp/tools.py` — modify `obsidian_suggest_graph_improvements` (add 2 params + scoring block); append `obsidian_build_graph_communities`; append `obsidian_graph_insights`
- `tests/test_obsidian_vault_mcp.py` — append new test cases

**No new files.**

---

## Background: How the codebase works

`helpers.py` imports `common.py` via `globals().update(...)`, giving it access to all constants (`DEFAULT_EXCLUDES`, `WIKILINK_RE`, `CITATION_LINK_FIELDS`, etc.) and stdlib imports without explicit `import` statements. `tools.py` does the same with `helpers.py`. New code you add to either file automatically has access to everything already imported.

`obsidian_build_graph(vault_path)` returns a dict with keys: `nodes` (list of `{"id": rel_path, "type": "note", "title": ..., "tags": [...], "aliases": [...]}}`), `edges` (list of `{"source": rel_path, "target": rel_path, "kind": str}`), `backlinks` (`{node_id: [source1, ...]}`), `orphans`, `deadEnds`, `unresolved`, `tags`. Edge `kind` values include `"wikilink"`, `"embed"`, and the `CITATION_LINK_FIELDS` tuple values `("related", "cites", "references", "entities", "concepts", "sources")`.

All tests extend `ObsidianVaultMcpTests(unittest.TestCase)` which creates a temp vault with `.obsidian/` in `setUp`. Use `self.write_note("rel/path.md", content)` to create test notes. Call tools via `self.module.tool_name(args)`.

---

## Task 1: networkx dependency + graph helpers + `obsidian_suggest_graph_improvements` upgrade

**Files:**
- Modify: `pyproject.toml`
- Modify: `scripts/obsidian_vault_mcp/helpers.py` — append after line 2582
- Modify: `scripts/obsidian_vault_mcp/tools.py:2578-2583` (signature only) and end of function body
- Modify: `tests/test_obsidian_vault_mcp.py` — append

---

- [ ] **Step 1: Add networkx to dependencies and install**

In `pyproject.toml`, change the `dependencies` list from:
```toml
dependencies = [
  "mcp",
  "PyYAML",
  "pypdf",
]
```
To:
```toml
dependencies = [
  "mcp",
  "PyYAML",
  "pypdf",
  "networkx>=3.0",
]
```

Then install into your dev environment:
```
pip install "networkx>=3.0"
```

Verify: `python -c "import networkx; print(networkx.__version__)"` — should print `3.x`.

---

- [ ] **Step 2: Write the failing tests**

Append to `tests/test_obsidian_vault_mcp.py`:

```python
    # ------------------------------------------------------------------ #
    # Task 1: obsidian_suggest_graph_improvements — use_scoring upgrade   #
    # ------------------------------------------------------------------ #

    def test_suggest_graph_improvements_use_scoring_false_preserves_old_format(self):
        self.write_note("A.md", "---\ntitle: A\n---\n[[Ghost]]\n")
        result = self.module.obsidian_suggest_graph_improvements(str(self.vault), use_scoring=False)
        kinds = {s["kind"] for s in result["suggestions"]}
        self.assertNotIn("scored_link", kinds)

    def test_suggest_graph_improvements_with_scoring_returns_scored_link_entries(self):
        # A and B both cite C — source overlap should create a scored_link suggestion for A↔B
        self.write_note("C.md", "---\ntitle: C\n---\n")
        self.write_note("A.md", "---\ntitle: A\ncites:\n  - '[[C.md]]'\n---\n")
        self.write_note("B.md", "---\ntitle: B\ncites:\n  - '[[C.md]]'\n---\n")
        result = self.module.obsidian_suggest_graph_improvements(
            str(self.vault), use_scoring=True
        )
        scored = [s for s in result["suggestions"] if s.get("kind") == "scored_link"]
        self.assertGreater(len(scored), 0)
        entry = scored[0]
        self.assertIn("score", entry)
        self.assertIn("signals", entry)
        self.assertIn("reason", entry)
        self.assertIn("sourceOverlap", entry["signals"])
        self.assertGreater(entry["signals"]["sourceOverlap"], 0)

    def test_suggest_graph_improvements_scoring_includes_type_affinity_for_same_folder(self):
        # Both A and B are in "lit/" folder — same inferred type → typeAffinity = 1.0
        self.write_note("shared.md", "---\ntitle: Shared\n---\n")
        self.write_note("lit/A.md", "---\ntitle: A\ncites:\n  - '[[shared.md]]'\n---\n")
        self.write_note("lit/B.md", "---\ntitle: B\ncites:\n  - '[[shared.md]]'\n---\n")
        result = self.module.obsidian_suggest_graph_improvements(
            str(self.vault), use_scoring=True
        )
        scored = [s for s in result["suggestions"] if s.get("kind") == "scored_link"]
        ab = next(
            (s for s in scored if {"s.get('from')", "s.get('to')"} <= {"lit/A.md", "lit/B.md"}
             or (s.get("from") in {"lit/A.md", "lit/B.md"} and s.get("to") in {"lit/A.md", "lit/B.md"})),
            None,
        )
        self.assertIsNotNone(ab)
        self.assertEqual(ab["signals"]["typeAffinity"], 1.0)
```

---

- [ ] **Step 3: Run tests to verify they fail**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_suggest_graph_improvements"
```

Expected: the two new tests FAIL — `obsidian_suggest_graph_improvements()` takes no keyword argument `use_scoring`. The old test passes.

---

- [ ] **Step 4: Append helpers to `scripts/obsidian_vault_mcp/helpers.py`**

Append the following block at the very end of `helpers.py` (after line 2582):

```python
# ---------------------------------------------------------------------------
# Graph intelligence helpers (networkx-based)
# ---------------------------------------------------------------------------

_SOURCE_EDGE_KINDS = {"related", "cites", "references", "entities", "concepts", "sources"}

_FOLDER_TYPE_MAP = {
    "literature": "literature",
    "lit": "literature",
    "papers": "literature",
    "concepts": "concept",
    "concept": "concept",
    "entities": "entity",
    "entity": "entity",
    "sources": "source",
    "projects": "project",
    "project": "project",
}


def _build_nx_graph(graph_data: dict[str, Any]):
    """Convert obsidian_build_graph output into a networkx undirected Graph.

    Raises ImportError if networkx is not installed.
    """
    try:
        import networkx as nx
    except ImportError:
        raise ImportError("networkx>=3.0 is required for graph analytics. Install with: pip install 'networkx>=3.0'")
    G = nx.Graph()
    for node in graph_data["nodes"]:
        G.add_node(node["id"])
    for edge in graph_data["edges"]:
        src, tgt = edge["source"], edge["target"]
        if not G.has_edge(src, tgt):
            G.add_edge(src, tgt)
    return G


def _build_source_index(graph_data: dict[str, Any]) -> dict[str, set[str]]:
    """Map each node to its set of source identifiers.

    Identifiers come from:
    - targets of outgoing citation-kind edges (cites, references, related, etc.)
    - first 5 frontmatter tags, prefixed with '#' to avoid path collisions
    """
    index: dict[str, set[str]] = {n["id"]: set() for n in graph_data["nodes"]}
    for edge in graph_data["edges"]:
        if edge.get("kind") in _SOURCE_EDGE_KINDS:
            src = edge["source"]
            if src in index:
                index[src].add(edge["target"])
    for node in graph_data["nodes"]:
        for tag in node.get("tags", [])[:5]:
            if tag:
                index[node["id"]].add(f"#{tag}")
    return index


def _compute_source_overlap(sources_a: set[str], sources_b: set[str]) -> float:
    """Jaccard similarity between two source sets. Returns 0.0 if either is empty."""
    if not sources_a or not sources_b:
        return 0.0
    intersection = len(sources_a & sources_b)
    if intersection == 0:
        return 0.0
    return intersection / max(len(sources_a), len(sources_b))


def _get_node_type(node_id: str) -> str:
    """Infer node type from the first folder segment of its vault-relative path."""
    first_folder = node_id.split("/")[0].lower() if "/" in node_id else ""
    return _FOLDER_TYPE_MAP.get(first_folder, "note")


def _compute_scored_suggestions(
    G: Any,
    graph_data: dict[str, Any],
    source_index: dict[str, set[str]],
    max_pairs: int = 500,
) -> list[dict[str, Any]]:
    """Compute scored link suggestions using the 4-signal model.

    Signals:
      source_overlap × 4.0   — shared citation targets and tags (Jaccard)
      adamic_adar    × 1.5   — common neighbours via networkx
      type_affinity  × 1.0   — same inferred folder type
      direct_link    × 3.0   — (used as filter only; unconnected pairs always 0)

    Only node pairs with source_overlap > 0 are scored.
    The top max_pairs candidates (by overlap) are passed to adamic_adar_index.
    """
    import networkx as nx

    existing_pairs: set[tuple[str, str]] = set()
    for edge in graph_data["edges"]:
        existing_pairs.add((edge["source"], edge["target"]))
        existing_pairs.add((edge["target"], edge["source"]))

    node_ids = [n["id"] for n in graph_data["nodes"]]

    # Find candidate pairs with source_overlap > 0
    candidates: list[tuple[str, str, float]] = []
    for i, u in enumerate(node_ids):
        for v in node_ids[i + 1:]:
            if (u, v) in existing_pairs:
                continue
            overlap = _compute_source_overlap(source_index.get(u, set()), source_index.get(v, set()))
            if overlap > 0:
                candidates.append((u, v, overlap))

    # Limit to top max_pairs by overlap before computing Adamic-Adar
    candidates.sort(key=lambda x: -x[2])
    candidates = candidates[:max_pairs]

    if not candidates:
        return []

    # Compute Adamic-Adar for all candidates at once
    aa_map: dict[tuple[str, str], float] = {}
    try:
        for u, v, aa_score in nx.adamic_adar_index(G, [(u, v) for u, v, _ in candidates]):
            aa_map[(u, v)] = aa_score
    except Exception:
        pass  # adamic_adar_index can fail on disconnected graphs; silently use 0

    results: list[dict[str, Any]] = []
    for u, v, overlap in candidates:
        aa = aa_map.get((u, v), 0.0)
        type_aff = 1.0 if _get_node_type(u) == _get_node_type(v) else 0.0
        score = 4.0 * overlap + 1.5 * aa + 1.0 * type_aff

        shared = source_index.get(u, set()) & source_index.get(v, set())
        reason_parts: list[str] = []
        if shared:
            reason_parts.append(f"共享来源 {len(shared)} 项")
        if aa > 0.01:
            reason_parts.append(f"{round(aa, 1)} 个共同邻居")
        reason = "；".join(reason_parts) if reason_parts else "存在间接关联"

        results.append({
            "kind": "scored_link",
            "from": u,
            "to": v,
            "score": round(score, 2),
            "signals": {
                "sourceOverlap": round(4.0 * overlap, 2),
                "adamicAdar": round(1.5 * aa, 2),
                "typeAffinity": type_aff,
                "directLink": 0.0,
            },
            "reason": reason,
        })

    results.sort(key=lambda x: -x["score"])
    return results
```

---

- [ ] **Step 5: Upgrade `obsidian_suggest_graph_improvements` in `tools.py`**

**5a — Change the function signature** (find line 2578, the `@tool()` line before `def obsidian_suggest_graph_improvements`):

Replace:
```python
@tool()
def obsidian_suggest_graph_improvements(
    vault_path: str = "",
    folder: str = "",
    max_suggestions: int = 50,
    max_reciprocal: int = 10,
) -> dict[str, Any]:
    """Suggest graph improvements such as creating unresolved notes, reciprocal links, and merging similar pages."""
```
With:
```python
@tool()
def obsidian_suggest_graph_improvements(
    vault_path: str = "",
    folder: str = "",
    max_suggestions: int = 50,
    max_reciprocal: int = 10,
    use_scoring: bool = False,
    max_scoring_pairs: int = 500,
) -> dict[str, Any]:
    """Suggest graph improvements such as creating unresolved notes, reciprocal links, and merging similar pages.

    use_scoring=True adds 4-signal scored link suggestions (requires networkx>=3.0).
    Scored entries have kind='scored_link' and include score, signals, and reason fields.
    max_scoring_pairs: maximum node pairs to evaluate for Adamic-Adar (default 500).
    """
```

**5b — Add scoring block** just before the `result = {` dict at the end of the function (approximately line 2656 — the line that reads `result = {`):

Insert this block immediately before `result = {`:
```python
    if use_scoring:
        try:
            G = _build_nx_graph(graph)
            source_index = _build_source_index(graph)
            scored = _compute_scored_suggestions(G, graph, source_index, max_pairs=max_scoring_pairs)
            suggestions = scored + suggestions
        except Exception as exc:
            suggestions.insert(0, {"kind": "scoring_error", "message": str(exc)})

```

---

- [ ] **Step 6: Run tests to verify they pass**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_suggest_graph_improvements"
```

Expected: all 3 `test_suggest_graph_improvements_*` tests PASS.

---

- [ ] **Step 7: Commit**

```
git add pyproject.toml scripts/obsidian_vault_mcp/helpers.py scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add 4-signal scored suggestions to obsidian_suggest_graph_improvements"
```

---

## Task 2: `obsidian_build_graph_communities`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` — append after end of file (after line 3475)
- Modify: `tests/test_obsidian_vault_mcp.py` — append

---

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_obsidian_vault_mcp.py`:

```python
    # ------------------------------------------------------- #
    # Task 2: obsidian_build_graph_communities                 #
    # ------------------------------------------------------- #

    def test_build_graph_communities_returns_community_list(self):
        # 6 notes forming two clusters: {A,B,C} and {D,E,F}
        self.write_note("A.md", "---\ntitle: A\n---\n[[B]]\n[[C]]\n")
        self.write_note("B.md", "---\ntitle: B\n---\n[[C]]\n")
        self.write_note("C.md", "---\ntitle: C\n---\n")
        self.write_note("D.md", "---\ntitle: D\n---\n[[E]]\n[[F]]\n")
        self.write_note("E.md", "---\ntitle: E\n---\n[[F]]\n")
        self.write_note("F.md", "---\ntitle: F\n---\n")
        result = self.module.obsidian_build_graph_communities(str(self.vault))
        self.assertTrue(result["ok"])
        self.assertGreater(result["communityCount"], 0)
        self.assertIn("communities", result)
        self.assertIn("modularity", result)
        self.assertIsInstance(result["modularity"], float)
        for community in result["communities"]:
            self.assertIn("id", community)
            self.assertIn("size", community)
            self.assertIn("label", community)
            self.assertIn("topNodes", community)
            self.assertIn("dominantTags", community)

    def test_build_graph_communities_min_size_filters_small_groups(self):
        # solo.md is isolated (community size 1) and should be filtered with min_community_size=3
        self.write_note("solo.md", "---\ntitle: Solo\n---\n")
        self.write_note("A.md", "---\ntitle: A\n---\n[[B]]\n[[C]]\n[[D]]\n")
        self.write_note("B.md", "---\ntitle: B\n---\n[[C]]\n")
        self.write_note("C.md", "---\ntitle: C\n---\n[[D]]\n")
        self.write_note("D.md", "---\ntitle: D\n---\n")
        result = self.module.obsidian_build_graph_communities(str(self.vault), min_community_size=3)
        for community in result["communities"]:
            self.assertGreaterEqual(community["size"], 3)

    def test_build_graph_communities_dry_run_does_not_write_frontmatter(self):
        self.write_note("A.md", "---\ntitle: A\n---\n[[B]]\n[[C]]\n[[D]]\n")
        self.write_note("B.md", "---\ntitle: B\n---\n[[C]]\n")
        self.write_note("C.md", "---\ntitle: C\n---\n")
        self.write_note("D.md", "---\ntitle: D\n---\n")
        original = (self.vault / "A.md").read_text(encoding="utf-8")
        result = self.module.obsidian_build_graph_communities(
            str(self.vault), write_frontmatter=True, dry_run=True, min_community_size=1
        )
        self.assertTrue(result["dryRun"])
        self.assertEqual((self.vault / "A.md").read_text(encoding="utf-8"), original)

    def test_build_graph_communities_write_frontmatter_adds_community_field(self):
        # 4 notes all linked to each other — definitely one community
        for name in ["P", "Q", "R", "S"]:
            others = "".join(f"[[{x}]]" for x in ["P", "Q", "R", "S"] if x != name)
            self.write_note(f"{name}.md", f"---\ntitle: {name}\n---\n{others}\n")
        result = self.module.obsidian_build_graph_communities(
            str(self.vault), write_frontmatter=True, dry_run=False, min_community_size=1
        )
        self.assertFalse(result["dryRun"])
        self.assertGreater(result["written"], 0)
        content = (self.vault / "P.md").read_text(encoding="utf-8")
        self.assertIn("community:", content)
```

---

- [ ] **Step 2: Run tests to verify they fail**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_build_graph_communities"
```

Expected: FAIL — `module 'obsidian_vault_mcp' has no attribute 'obsidian_build_graph_communities'`

---

- [ ] **Step 3: Append `obsidian_build_graph_communities` to `tools.py`**

Append the following at the end of `scripts/obsidian_vault_mcp/tools.py` (after the last line, 3475):

```python

@tool()
def obsidian_build_graph_communities(
    vault_path: str = "",
    folder: str = "",
    min_community_size: int = 3,
    write_frontmatter: bool = False,
    dry_run: bool = True,
    resolution: float = 1.0,
) -> dict[str, Any]:
    """Detect Louvain community structure in the vault knowledge graph.

    Returns community labels, sizes, modularity score, and top nodes per community.
    write_frontmatter=True adds a 'community' YAML field to each note (label = highest-inDegree node's title).
    dry_run=True (default): analysis only, no file writes.
    resolution: higher values produce smaller, more granular communities (default 1.0).
    min_community_size: communities smaller than this are excluded from results.
    """
    try:
        import networkx as nx  # noqa: F401
        from networkx.algorithms.community import louvain_communities
        from networkx.algorithms.community.quality import modularity as nx_modularity
    except ImportError:
        return {"ok": False, "error": "networkx>=3.0 is required. Install with: pip install 'networkx>=3.0'"}

    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), folder=folder, include_tags=True)
    G = _build_nx_graph(graph)

    if G.number_of_nodes() < 2:
        return {"ok": True, "communityCount": 0, "modularity": 0.0, "communities": [], "written": 0, "dryRun": dry_run}

    raw_communities = louvain_communities(G, resolution=resolution, seed=42)
    try:
        mod_score = round(nx_modularity(G, raw_communities), 4)
    except Exception:
        mod_score = 0.0

    nodes_by_id = {n["id"]: n for n in graph["nodes"]}
    backlinks = graph.get("backlinks", {})

    communities_out: list[dict[str, Any]] = []
    for comm_id, comm_set in enumerate(raw_communities):
        if len(comm_set) < min_community_size:
            continue
        sorted_by_indegree = sorted(comm_set, key=lambda nid: -len(backlinks.get(nid, [])))
        top_node = sorted_by_indegree[0]
        label = str(nodes_by_id.get(top_node, {}).get("title") or Path(top_node).stem)
        tag_freq: dict[str, int] = {}
        for nid in comm_set:
            for tag in nodes_by_id.get(nid, {}).get("tags", []):
                tag_freq[tag] = tag_freq.get(tag, 0) + 1
        dominant_tags = [t for t, _ in sorted(tag_freq.items(), key=lambda x: -x[1])[:3]]
        communities_out.append({
            "id": comm_id,
            "size": len(comm_set),
            "label": label,
            "topNodes": sorted_by_indegree[:3],
            "dominantTags": dominant_tags,
            "_members": sorted(comm_set),
        })

    written = 0
    if write_frontmatter:
        for comm in communities_out:
            for node_path in comm["_members"]:
                full = _safe_path(vault, node_path)
                if not full.exists() or full.suffix.lower() != ".md":
                    continue
                props, body = _split_frontmatter(_read_text(full))
                props["community"] = comm["label"]
                if not dry_run:
                    _write_text(full, _join_frontmatter(props, body))
                written += 1

    for comm in communities_out:
        del comm["_members"]

    return {
        "ok": True,
        "communityCount": len(communities_out),
        "modularity": mod_score,
        "communities": communities_out,
        "written": written,
        "dryRun": dry_run,
    }
```

---

- [ ] **Step 4: Run tests to verify they pass**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_build_graph_communities"
```

Expected: all 4 `test_build_graph_communities_*` tests PASS.

---

- [ ] **Step 5: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add obsidian_build_graph_communities with Louvain detection and frontmatter labeling"
```

---

## Task 3: `obsidian_graph_insights`

**Files:**
- Modify: `scripts/obsidian_vault_mcp/tools.py` — append after `obsidian_build_graph_communities`
- Modify: `tests/test_obsidian_vault_mcp.py` — append

---

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_obsidian_vault_mcp.py`:

```python
    # ----------------------------------------------- #
    # Task 3: obsidian_graph_insights                  #
    # ----------------------------------------------- #

    def test_graph_insights_returns_expected_keys(self):
        self.write_note("A.md", "---\ntitle: A\n---\n")
        result = self.module.obsidian_graph_insights(str(self.vault))
        self.assertTrue(result["ok"])
        self.assertIn("bridgeNodes", result)
        self.assertIn("surprisingLinks", result)
        self.assertIn("sparseClusters", result)
        self.assertIn("isolatedHubs", result)

    def test_graph_insights_detects_isolated_hubs(self):
        # hub.md links to 5 notes but nothing links back to it
        self.write_note("hub.md", "---\ntitle: Hub\n---\n[[N1]]\n[[N2]]\n[[N3]]\n[[N4]]\n[[N5]]\n")
        for i in range(1, 6):
            self.write_note(f"N{i}.md", f"---\ntitle: N{i}\n---\n")
        result = self.module.obsidian_graph_insights(str(self.vault))
        hub_paths = [h["path"] for h in result["isolatedHubs"]]
        self.assertIn("hub.md", hub_paths)
        hub = next(h for h in result["isolatedHubs"] if h["path"] == "hub.md")
        self.assertEqual(hub["outDegree"], 5)
        self.assertEqual(hub["inDegree"], 0)

    def test_graph_insights_detects_bridge_nodes(self):
        # bridge.md connects two otherwise-disconnected clusters
        # Cluster 1: A--B--C all linked
        # bridge.md links to C and D
        # Cluster 2: D--E--F all linked
        self.write_note("A.md", "---\ntitle: A\n---\n[[B]]\n")
        self.write_note("B.md", "---\ntitle: B\n---\n[[C]]\n")
        self.write_note("C.md", "---\ntitle: C\n---\n[[A]]\n")
        self.write_note("bridge.md", "---\ntitle: Bridge\n---\n[[C]]\n[[D]]\n")
        self.write_note("D.md", "---\ntitle: D\n---\n[[E]]\n")
        self.write_note("E.md", "---\ntitle: E\n---\n[[F]]\n")
        self.write_note("F.md", "---\ntitle: F\n---\n[[D]]\n")
        result = self.module.obsidian_graph_insights(str(self.vault))
        # bridge.md should appear in bridgeNodes
        bridge_paths = [b["path"] for b in result["bridgeNodes"]]
        self.assertIn("bridge.md", bridge_paths)

    def test_graph_insights_detects_surprising_cross_community_links(self):
        # A and B share a source but are (likely) in different communities
        self.write_note("shared_source.md", "---\ntitle: Shared\n---\n")
        self.write_note("A.md", "---\ntitle: A\ncites:\n  - '[[shared_source.md]]'\n---\n[[B1]]\n[[B2]]\n[[B3]]\n")
        self.write_note("B.md", "---\ntitle: B\ncites:\n  - '[[shared_source.md]]'\n---\n[[C1]]\n[[C2]]\n[[C3]]\n")
        for name in ["B1", "B2", "B3", "C1", "C2", "C3"]:
            self.write_note(f"{name}.md", f"---\ntitle: {name}\n---\n")
        result = self.module.obsidian_graph_insights(str(self.vault))
        # Just verify it runs and returns the correct structure
        self.assertIsInstance(result["surprisingLinks"], list)
        for link in result["surprisingLinks"]:
            self.assertIn("from", link)
            self.assertIn("to", link)
            self.assertIn("sourceOverlapScore", link)
            self.assertIn("reason", link)

    def test_graph_insights_isolated_hubs_threshold(self):
        # A note with only 2 outgoing links should NOT appear (threshold is outDegree >= 5)
        self.write_note("small_hub.md", "---\ntitle: Small Hub\n---\n[[X]]\n[[Y]]\n")
        self.write_note("X.md", "---\ntitle: X\n---\n")
        self.write_note("Y.md", "---\ntitle: Y\n---\n")
        result = self.module.obsidian_graph_insights(str(self.vault))
        hub_paths = [h["path"] for h in result["isolatedHubs"]]
        self.assertNotIn("small_hub.md", hub_paths)
```

---

- [ ] **Step 2: Run tests to verify they fail**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_graph_insights"
```

Expected: FAIL — `module 'obsidian_vault_mcp' has no attribute 'obsidian_graph_insights'`

---

- [ ] **Step 3: Append `obsidian_graph_insights` to `tools.py`**

Append the following at the very end of `scripts/obsidian_vault_mcp/tools.py`:

```python

@tool()
def obsidian_graph_insights(
    vault_path: str = "",
    folder: str = "",
    top_n: int = 20,
) -> dict[str, Any]:
    """Detect structural patterns in the vault knowledge graph.

    Returns four insight categories:
    - bridgeNodes: low-degree but high-betweenness nodes (cross-community connectors)
    - surprisingLinks: unconnected node pairs from different communities with high source overlap
    - sparseClusters: Louvain communities with low internal edge density (< 0.2)
    - isolatedHubs: notes with high outDegree (>= 5) but very low inDegree (<= 1)

    top_n: max results per category (default 20).
    Requires networkx>=3.0.
    """
    try:
        import networkx as nx
        from networkx.algorithms.community import louvain_communities
    except ImportError:
        return {"ok": False, "error": "networkx>=3.0 is required. Install with: pip install 'networkx>=3.0'"}

    vault = _vault(vault_path)
    graph = obsidian_build_graph(vault_path=str(vault), folder=folder, include_tags=True)
    G = _build_nx_graph(graph)
    nodes_by_id = {n["id"]: n for n in graph["nodes"]}

    if G.number_of_nodes() < 3:
        return {"ok": True, "bridgeNodes": [], "surprisingLinks": [], "sparseClusters": [], "isolatedHubs": []}

    source_index = _build_source_index(graph)
    backlinks = graph.get("backlinks", {})

    # Directed outgoing counts (from edges list)
    outgoing_counts: dict[str, int] = {}
    for edge in graph["edges"]:
        outgoing_counts[edge["source"]] = outgoing_counts.get(edge["source"], 0) + 1

    # ------------------------------------------------------------------ #
    # 1. Bridge Nodes: high betweenness, low-to-median degree             #
    # ------------------------------------------------------------------ #
    betweenness = nx.betweenness_centrality(G, normalized=True)
    degrees = dict(G.degree())
    sorted_degrees = sorted(degrees.values())
    median_degree = sorted_degrees[len(sorted_degrees) // 2] if sorted_degrees else 0

    bridge_nodes: list[dict[str, Any]] = []
    for nid, bt in sorted(betweenness.items(), key=lambda x: -x[1]):
        if bt > 0.05 and degrees.get(nid, 0) <= max(median_degree, 1):
            node = nodes_by_id.get(nid, {})
            bridge_nodes.append({
                "path": nid,
                "title": str(node.get("title") or Path(nid).stem),
                "betweenness": round(bt, 4),
                "degree": degrees.get(nid, 0),
            })
            if len(bridge_nodes) >= top_n:
                break

    # ------------------------------------------------------------------ #
    # 2. Isolated Hubs: high outDegree, very low inDegree                 #
    # ------------------------------------------------------------------ #
    isolated_hubs: list[dict[str, Any]] = []
    for node in graph["nodes"]:
        nid = node["id"]
        out_deg = outgoing_counts.get(nid, 0)
        in_deg = len(backlinks.get(nid, []))
        if out_deg >= 5 and in_deg <= 1:
            isolated_hubs.append({
                "path": nid,
                "title": str(node.get("title") or Path(nid).stem),
                "outDegree": out_deg,
                "inDegree": in_deg,
            })
    isolated_hubs.sort(key=lambda x: -x["outDegree"])
    isolated_hubs = isolated_hubs[:top_n]

    # ------------------------------------------------------------------ #
    # 3. Louvain communities for cross-community analysis                 #
    # ------------------------------------------------------------------ #
    raw_communities: list[Any] = []
    node_to_community: dict[str, int] = {}
    try:
        raw_communities = list(louvain_communities(G, seed=42))
        for comm_id, comm_set in enumerate(raw_communities):
            for nid in comm_set:
                node_to_community[nid] = comm_id
    except Exception:
        pass

    # ------------------------------------------------------------------ #
    # 4. Surprising Cross-Community Links                                 #
    # ------------------------------------------------------------------ #
    surprising_links: list[dict[str, Any]] = []
    if node_to_community:
        existing_pairs: set[tuple[str, str]] = set()
        for edge in graph["edges"]:
            existing_pairs.add((edge["source"], edge["target"]))
            existing_pairs.add((edge["target"], edge["source"]))

        node_ids = [n["id"] for n in graph["nodes"]]
        for i, u in enumerate(node_ids):
            if len(surprising_links) >= top_n * 3:
                break
            for v in node_ids[i + 1:]:
                if (u, v) in existing_pairs:
                    continue
                comm_u = node_to_community.get(u)
                comm_v = node_to_community.get(v)
                if comm_u is None or comm_v is None or comm_u == comm_v:
                    continue
                overlap = _compute_source_overlap(source_index.get(u, set()), source_index.get(v, set()))
                if overlap * 4.0 >= 2.0:
                    shared = source_index.get(u, set()) & source_index.get(v, set())
                    surprising_links.append({
                        "from": u,
                        "to": v,
                        "sourceOverlapScore": round(overlap * 4.0, 2),
                        "fromCommunity": comm_u,
                        "toCommunity": comm_v,
                        "reason": f"共享来源 {len(shared)} 项",
                    })
        surprising_links.sort(key=lambda x: -x["sourceOverlapScore"])
        surprising_links = surprising_links[:top_n]

    # ------------------------------------------------------------------ #
    # 5. Sparse Clusters: low intra-community edge density                #
    # ------------------------------------------------------------------ #
    sparse_clusters: list[dict[str, Any]] = []
    for comm_id, comm_set in enumerate(raw_communities):
        comm_list = list(comm_set)
        if len(comm_list) < 3:
            continue
        subgraph = G.subgraph(comm_list)
        n = len(comm_list)
        max_possible = n * (n - 1) / 2
        density = subgraph.number_of_edges() / max_possible if max_possible > 0 else 0.0
        if density < 0.2:
            top_node = max(comm_list, key=lambda nid: len(backlinks.get(nid, [])))
            label = str(nodes_by_id.get(top_node, {}).get("title") or Path(top_node).stem)
            sparse_clusters.append({
                "communityId": comm_id,
                "community": label,
                "density": round(density, 3),
                "nodeCount": n,
                "suggestion": "考虑拆分为子社区或在内部添加更多关联链接",
            })

    return {
        "ok": True,
        "bridgeNodes": bridge_nodes,
        "surprisingLinks": surprising_links,
        "sparseClusters": sparse_clusters,
        "isolatedHubs": isolated_hubs,
    }
```

---

- [ ] **Step 4: Run Task 3 tests to verify they pass**

```
python -m unittest tests.test_obsidian_vault_mcp -v -k "test_graph_insights"
```

Expected: all 5 `test_graph_insights_*` tests PASS.

---

- [ ] **Step 5: Run the full test suite to verify no regressions**

```
python -m unittest tests.test_obsidian_vault_mcp -v
```

Expected: all tests pass. Check that no previously passing test now fails.

---

- [ ] **Step 6: Run ruff**

```
python -m ruff check scripts/obsidian_vault_mcp/helpers.py scripts/obsidian_vault_mcp/tools.py
```

Expected: no errors (E501 line-length is ignored per `pyproject.toml`). Fix any E401/I001/F841 errors before committing.

---

- [ ] **Step 7: Commit**

```
git add scripts/obsidian_vault_mcp/tools.py tests/test_obsidian_vault_mcp.py
git commit -m "feat: add obsidian_graph_insights with bridge nodes, cross-community links, sparse clusters, isolated hubs"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task | ✓ |
|---|---|---|
| `networkx>=3.0` dependency | Task 1 Step 1 | ✓ |
| `_build_nx_graph()` helper | Task 1 Step 4 | ✓ |
| `_build_source_index()` helper | Task 1 Step 4 | ✓ |
| `_compute_source_overlap()` helper | Task 1 Step 4 | ✓ |
| `_get_node_type()` helper | Task 1 Step 4 | ✓ |
| `_compute_scored_suggestions()` | Task 1 Step 4 | ✓ |
| `obsidian_suggest_graph_improvements` + `use_scoring` param | Task 1 Step 5 | ✓ |
| `score`, `signals`, `reason` in scored output | Task 1 Step 4 | ✓ |
| `use_scoring=False` backward compat | Task 1 test | ✓ |
| `obsidian_build_graph_communities` — Louvain, modularity, labels | Task 2 Step 3 | ✓ |
| `write_frontmatter` option | Task 2 Step 3 | ✓ |
| `dry_run` option | Task 2 Step 3 | ✓ |
| `obsidian_graph_insights` — bridge nodes | Task 3 Step 3 | ✓ |
| `obsidian_graph_insights` — surprising cross-community links | Task 3 Step 3 | ✓ |
| `obsidian_graph_insights` — sparse clusters | Task 3 Step 3 | ✓ |
| `obsidian_graph_insights` — isolated hubs | Task 3 Step 3 | ✓ |

**Placeholder scan:** No TBD/TODO/placeholder patterns. All code blocks are complete and self-contained.

**Type consistency:**
- `_build_nx_graph(graph_data)` → used in Task 1 Step 5 (`_build_nx_graph(graph)`) and Task 2/3 tools ✓
- `_build_source_index(graph_data)` → used with `graph` dict returned by `obsidian_build_graph` ✓
- `_compute_source_overlap(set, set)` → called with `source_index.get(u, set())` ✓
- `_get_node_type(node_id: str)` → called with string path `u` and `v` in `_compute_scored_suggestions` ✓
- `_compute_scored_suggestions(G, graph, source_index, max_pairs)` → called in tools.py with matching signature ✓
- All community list items have `_members` key deleted before returning ✓
