---
name: obsidian-views
description: "Create Canvas maps, Obsidian Bases, or Dataview notes. 创建 Canvas、Bases 或 Dataview 视图时使用。"
---

Use `obsidian_write_file` to write views. Use `obsidian_search` + `obsidian_read_file` first to gather vault data.

- **Canvas**: write JSON `{nodes:[...], edges:[...]}` to `<name>.canvas`. Node types: file/text/link/group. Layouts: grid, radial, grouped, layered.
- **Bases**: write YAML `{filters:{and:[...]}, views:[{type:table, columns:[...]}]}` to `<name>.base`.
- **Dataview**: write a `.md` file with ` ```dataview TABLE ... FROM ... ``` ` blocks.
