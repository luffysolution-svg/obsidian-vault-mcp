---
name: obsidian-views
description: "Build visual and query views for an Obsidian vault. Use when the user needs to create or update JSON Canvas maps, Obsidian Bases files, or Dataview notes. 当用户提到 Canvas、Bases、Dataview、视图、图谱布局、表格卡片视图或查询笔记时使用。"
---

# Obsidian Views

Use `obsidian_write_file` to write Canvas (`.canvas`), Bases (`.base`), and Dataview (`.md`) files. Use `obsidian_search` and `obsidian_read_file` to gather vault content first.

## Canvas (JSON Canvas)

A `.canvas` file is a JSON object with `nodes` and `edges` arrays.

**Minimal Canvas structure:**
```json
{
  "nodes": [
    {"id": "a", "type": "file", "file": "notes/A.md", "x": 0, "y": 0, "width": 250, "height": 60},
    {"id": "b", "type": "file", "file": "notes/B.md", "x": 300, "y": 0, "width": 250, "height": 60}
  ],
  "edges": [
    {"id": "e1", "fromNode": "a", "toNode": "b", "toEnd": "arrow"}
  ]
}
```

**Node types:** `file` (vault note), `text` (inline text), `link` (URL), `group` (container).

**Kepano detection:** Before generating any Canvas, check whether `skills/json-canvas/SKILL.md` (project) or `.claude/skills/json-canvas.md` (user) exists. If found, invoke that skill instead of the built-in section below.

**Layouts — coordinate formulas:**
- **Grid:** `x = col * (nodeWidth + 60)`, `y = row * (nodeHeight + 40)`. Fill columns first, max 4 nodes per row.
- **Radial:** `x = cx + r * cos(2π * i / n)`, `y = cy + r * sin(2π * i / n)`. Radius `r = max(200, n * 60)`.
- **Layered (DAG):** Topological sort to get depth `d`; `x = d * 320`; nodes at same depth share `y` evenly. Recommended for 5+ nodes with a clear dependency direction.
- **Grouped:** Place group nodes first; constrain member coordinates within group bounds with 30 px inner padding.

**Overlap detection:** After placing all nodes, check every pair for bounding-box intersection:
`overlap = !(ax+aw ≤ bx || bx+bw ≤ ax || ay+ah ≤ by || by+bh ≤ ay)`
If overlap found, shift the later node right by `overlapWidth + 40`.

**Colors:**

| Preset | Color | Preset | Color |
|--------|-------|--------|-------|
| `"1"` | Red | `"4"` | Green |
| `"2"` | Orange | `"5"` | Cyan |
| `"3"` | Yellow | `"6"` | Purple |

Omit the `color` field entirely when no colour is needed.

**Node size guidelines:**

| Type | width | height |
|------|-------|--------|
| Small text / label | 200–300 | 80–150 |
| Normal note card | 250–400 | 150–250 |
| Large card / file preview | 400–500 | 250–400 |

**ID generation:** 16-character lowercase hex string, e.g. `"6f0ad84f44ce9c17"`. Never reuse an existing node or edge id.

**Steps to create a Canvas from vault links:**
1. `obsidian_search` with `query=""` to get all notes.
2. `obsidian_read_file` each note to extract `[[wikilinks]]`.
3. Build node list (one node per note) and edge list (one edge per link).
4. Apply layout using the coordinate formulas above.
5. Run overlap detection; adjust positions if needed.
6. `obsidian_write_file` the JSON to `<path>.canvas`.

**Visual validation (pure JSON — after writing the file):**
1. `obsidian_read_file` the written `.canvas` file.
2. Output a position summary table for quick scan:
   ```
   id       type   x     y     w    h
   ──────────────────────────────────
   a1b2c3   file     0     0   300  150
   d4e5f6   file   360     0   300  150
   ```
3. Run bounding-box overlap check on all node pairs; report any overlapping pairs.
4. Check total canvas span: `(max_x − min_x)` and `(max_y − min_y)` should be < 3000 px.
5. Verify every edge `fromNode`/`toNode` exists in the node list.

**Validation checklist:**
1. All `id` values unique across nodes and edges.
2. Every `fromNode`/`toNode` references an existing node id.
3. `type` is one of `text`, `file`, `link`, `group`.
4. `fromSide`/`toSide` is one of `top`, `right`, `bottom`, `left`.
5. `fromEnd`/`toEnd` is one of `none`, `arrow`.
6. Color presets are `"1"`–`"6"` or valid hex (e.g. `"#FF0000"`).
7. JSON is valid and parseable.

## Obsidian Bases

A `.base` file is YAML that defines a database-style table over vault notes.

**Standard structure:**
```yaml
filters:
  and:
    - file.ext == "md"
    - file.inFolder("sources")
views:
  - type: table
    name: Main
    columns:
      - property: title
        width: 200
      - property: tags
        width: 120
      - property: status
        width: 100
    order: file.name
    groupBy:
      property: status
      direction: ASC
```

**Literature Base template:**
```yaml
filters:
  and:
    - file.ext == "md"
    - file.inFolder("01-literature")
views:
  - type: table
    name: Literature
    columns:
      - {property: title, width: 240}
      - {property: authors, width: 160}
      - {property: year, width: 60}
      - {property: doi, width: 120}
      - {property: tags, width: 120}
    order: file.mtime
```

Write the YAML using `obsidian_write_file` to `<name>.base`.

## Dataview

A Dataview note is a standard Markdown file containing one or more `dataview` code fences.

**Standard DQL query block:**
````markdown
```dataview
TABLE title, authors, year, doi
FROM #chemistry AND "01-literature"
WHERE file.ext = "md"
SORT file.mtime DESC
```
````

**Steps:**
1. Confirm the user has the Dataview plugin installed.
2. Identify the target folder and tag filter.
3. Build the DQL query.
4. `obsidian_write_file` a `.md` file containing the query block.

## Validation

After writing a Canvas or Base file, use `obsidian_read_file` to confirm the file was written correctly. For Bases, check that all required `type`, `filters`, and `views` keys are present.

---

## 中文说明

Canvas 文件是 JSON，Bases 文件是 YAML，Dataview 是 Markdown 中的代码块。使用 `obsidian_write_file` 写入目标路径，使用 `obsidian_search` + `obsidian_read_file` 收集 vault 内容后再构建视图。
