---
name: obsidian-views
description: "Create research Canvas, Bases, or Dataview views from Obsidian literature notes. 从文献笔记生成研究视图时使用。"
---

- Role: turn literature notes, MinerU outputs, `## Reading Notes`, and `## AI Summary` into research views.
- First check format skills: `skills/json-canvas/SKILL.md` or `.claude/skills/json-canvas.md`; `skills/obsidian-bases/SKILL.md` or `.claude/skills/obsidian-bases.md`; `skills/obsidian-markdown/SKILL.md` or `.claude/skills/obsidian-markdown.md`.
- If missing and network is allowed, clone `https://github.com/kepano/obsidian-skills` and copy needed `SKILL.md` files into `.claude/skills/<name>.md`.
- Workflow: `obsidian_search` candidate papers → `obsidian_read_file` metadata/summary sections → choose `.canvas`, `.base`, or Dataview `.md` → use dedicated format skill → `obsidian_write_file` → read back and validate.
- Fallback only when format skills are unavailable: Canvas JSON with unique ids/file nodes; Bases YAML with `filters`/`views`; Dataview Markdown code fence.
- Do not invent missing metadata; leave absent DOI/year/authors blank.
- Evals: Canvas paper map must use vault files; literature Base must use existing frontmatter; Dataview dashboard must only write requested dashboard file.
