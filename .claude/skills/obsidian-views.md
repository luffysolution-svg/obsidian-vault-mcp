---
name: obsidian-views
description: "Create Canvas maps, Obsidian Bases, or Dataview notes. 创建 Canvas、Bases 或 Dataview 视图时使用。"
---

Use `obsidian_write_file` to write views. Use `obsidian_search` + `obsidian_read_file` first to gather vault data.

- **Canvas**: write JSON `{nodes:[...], edges:[...]}` to `<name>.canvas`. **Kepano detection first**: if `skills/json-canvas/SKILL.md` or `.claude/skills/json-canvas.md` exists, invoke that skill. Built-in fallback: Grid `x=col*(w+60), y=row*(h+40)`; Radial `x=cx+r*cos(2πi/n), y=cy+r*sin(2πi/n)` r=max(200,n*60); Layered (DAG) topo-sort → `x=d*320`; Grouped 30px padding. Overlap check: `!(ax+aw≤bx||bx+bw≤ax||ay+ah≤by||by+bh≤ay)`, shift right by `overlapW+40`. Colors: "1"=Red "2"=Orange "3"=Yellow "4"=Green "5"=Cyan "6"=Purple. Node sizes: small 200–300×80–150, card 250–400×150–250, large 400–500×250–400. IDs: 16-char lowercase hex. After writing: read back → position table → overlap check → span < 3000px → edge refs valid.
- **Bases**: write YAML `{filters:{and:[...]}, views:[{type:table, columns:[...]}]}` to `<name>.base`.
- **Dataview**: write a `.md` file with ` ```dataview TABLE ... FROM ... ``` ` blocks.
