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

**Layouts:**
- Grid: place nodes at evenly spaced `(x, y)` positions, e.g. 300px apart.
- Radial: compute angles around a centre point.
- Grouped: create `group` nodes first, position member nodes inside group bounds.
- Layered: arrange by folder depth (x) and index within folder (y).

**Steps to create a Canvas from vault links:**
1. `obsidian_search` with `query=""` to get all notes.
2. `obsidian_read_file` each note to extract `[[wikilinks]]`.
3. Build node list (one node per note) and edge list (one edge per link).
4. Apply layout to assign `x`, `y` coordinates.
5. `obsidian_write_file` the JSON to `<path>.canvas`.

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
