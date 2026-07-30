from __future__ import annotations

from pathlib import Path

from obsidian_vault_mcp.application.paper_read_service import PaperReadService
from obsidian_vault_mcp.config.defaults import default_config
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter


def _write_paper(vault: Path) -> None:
    note = vault / "Literature" / "ABCD1234.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        compose_frontmatter(
            {
                "title": "Catalyst Study",
                "itemType": "journalArticle",
                "zoteroKey": "ABCD1234",
                "abstract": "A concise metadata abstract.",
                "tags": ["catalysis"],
                "attachmentMinerULink": "[[Literature/attachment/MinerU/ABCD1234]]",
            },
            "# Catalyst Study\n",
        ),
        encoding="utf-8",
    )
    mineru = vault / "Literature" / "attachment" / "MinerU" / "ABCD1234.md"
    mineru.parent.mkdir(parents=True)
    mineru.write_text(
        compose_frontmatter(
            {"title": "Catalyst Study", "zoteroKey": "ABCD1234", "sourcePdf": "../ABCD1234.pdf"},
            (
                "# Catalyst Study\n\n"
                "## Introduction\n\n"
                "The catalyst converts carbon dioxide under visible light.\n\n"
                "## Methods\n\n"
                "Samples were heated at 300 °C before testing.\n\n"
                "![Figure 2a](image/ABCD1234/ABCD1234-fig01.png)\n\n"
                "Figure 2. Reactor schematic (a) before illumination.\n\n"
                "## Results\n\n"
                "Hydrogen production increased by 42 percent.\n"
            ),
        ),
        encoding="utf-8",
    )
    image = vault / "Literature" / "attachment" / "MinerU" / "image" / "ABCD1234" / "ABCD1234-fig01.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"png")

    # These files deliberately contain invalid data. V3 reading must not even
    # try to load the removed state families.
    for family in ("evidence", "coverage", "uncertainties"):
        poison = vault / ".obsidian-vault-mcp" / "state" / family / "ABCD1234.json"
        poison.parent.mkdir(parents=True, exist_ok=True)
        poison.write_text("{not-json", encoding="utf-8")


def test_paper_read_parses_passages_on_demand_without_removed_state(tmp_path: Path) -> None:
    _write_paper(tmp_path)
    before = {path.relative_to(tmp_path).as_posix(): path.read_bytes() for path in (tmp_path / ".obsidian-vault-mcp").rglob("*") if path.is_file()}

    result = PaperReadService(tmp_path, default_config()).read("ABCD1234", mode="full")

    assert result["ok"]
    assert [passage["paragraphIndex"] for passage in result["passages"]] == [1, 2, 3, 4, 5]
    methods = next(passage for passage in result["passages"] if "heated" in passage["text"])
    assert methods["sectionPath"][-1] == "Methods"
    assert methods["sourceLink"] == "[[Literature/attachment/MinerU/ABCD1234.md#Methods]]"
    assert all("evidenceId" not in passage and "assetId" not in passage for passage in result["passages"])
    assert result["basicCoverage"]["totalPassages"] == 5
    assert result["basicCoverage"]["selectedPassages"] == 5
    after = {path.relative_to(tmp_path).as_posix(): path.read_bytes() for path in (tmp_path / ".obsidian-vault-mcp").rglob("*") if path.is_file()}
    assert after == before


def test_paper_read_modes_are_bounded_and_figure_metadata_comes_from_text(tmp_path: Path) -> None:
    _write_paper(tmp_path)
    service = PaperReadService(tmp_path, default_config())

    targeted = service.read("ABCD1234", mode="targeted", query="hydrogen production", top_k=1)
    assert len(targeted["passages"]) == 1
    assert "Hydrogen production" in targeted["passages"][0]["text"]

    sections = service.read("ABCD1234", mode="sections", sections=["methods"])
    assert sections["passages"]
    assert all("Methods" in passage["sectionPath"] for passage in sections["passages"])

    overview = service.read("ABCD1234", mode="overview", max_chars=120)
    assert overview["budget"]["usedChars"] <= 120
    assert overview["basicCoverage"]["selectedPassages"] <= overview["basicCoverage"]["totalPassages"]

    figures = service.read("ABCD1234", mode="figures")
    assert len(figures["figures"]) == 1
    figure = figures["figures"][0]
    assert figure == {
        "targetType": "figure",
        "targetLabel": "Figure 2",
        "targetPanel": "a",
        "page": None,
        "caption": "Figure 2. Reactor schematic (a) before illumination.",
        "sourceLink": "[[Literature/attachment/MinerU/ABCD1234.md#Methods]]",
        "imagePath": "Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig01.png",
        "imageExists": True,
        "visualMode": "image",
        "contentType": "image",
        "content": "![Figure 2a](image/ABCD1234/ABCD1234-fig01.png)",
        "context": "Figure 2. Reactor schematic (a) before illumination.",
    }

    # The filename contains “fig99”, but labels and panels may only come from
    # Markdown alt/caption text.
    mineru = tmp_path / "Literature" / "attachment" / "MinerU" / "ABCD1234.md"
    text = mineru.read_text(encoding="utf-8")
    text = text.replace(
        "![Figure 2a](image/ABCD1234/ABCD1234-fig01.png)",
        "![microscopy](image/ABCD1234/ABCD1234-fig99.png)",
    ).replace(
        "Figure 2. Reactor schematic (a) before illumination.",
        "Microscopy image without an assigned figure number.",
    )
    mineru.write_text(text, encoding="utf-8")
    old_image = tmp_path / "Literature" / "attachment" / "MinerU" / "image" / "ABCD1234" / "ABCD1234-fig01.png"
    renamed = old_image.with_name("ABCD1234-fig99.png")
    old_image.rename(renamed)

    unlabelled = service.read("ABCD1234", mode="figures")["figures"][0]
    assert unlabelled["targetLabel"] is None
    assert unlabelled["targetPanel"] is None


def test_figure_panel_range_uses_the_public_target_fields(tmp_path: Path) -> None:
    _write_paper(tmp_path)
    mineru = tmp_path / "Literature" / "attachment" / "MinerU" / "ABCD1234.md"
    text = mineru.read_text(encoding="utf-8").replace(
        "![Figure 2a](image/ABCD1234/ABCD1234-fig01.png)",
        "![Fig. 2d–i](image/ABCD1234/ABCD1234-fig01.png)",
    )
    mineru.write_text(text, encoding="utf-8")

    figure = PaperReadService(tmp_path, default_config()).read("ABCD1234", mode="figures")["figures"][0]

    assert figure["targetLabel"] == "Figure 2"
    assert figure["targetPanel"] == "d-i"


def test_figures_mode_returns_unified_visual_and_structured_targets(tmp_path: Path) -> None:
    _write_paper(tmp_path)
    mineru = tmp_path / "Literature" / "attachment" / "MinerU" / "ABCD1234.md"
    mineru.write_text(
        mineru.read_text(encoding="utf-8")
        + (
            "\n## Structured targets\n\n"
            "Table 1. Catalyst activity summary.\n\n"
            "| Catalyst | Yield |\n"
            "| --- | ---: |\n"
            "| A | 42% |\n\n"
            "### Scheme 3. Proposed reaction pathway\n\n"
            "![reaction pathway](image/ABCD1234/ABCD1234-pathway.png)\n\n"
            "The proposed pathway joins the measured intermediates.\n\n"
            "Equation 5. Apparent rate law.\n\n"
            "$$\n"
            "r = k C_{\\mathrm{CO_2}}\n"
            "$$\n\n"
            "The fitted rate law describes the measured concentration dependence.\n"
        ),
        encoding="utf-8",
    )
    scheme_image = tmp_path / "Literature" / "attachment" / "MinerU" / "image" / "ABCD1234" / "ABCD1234-pathway.png"
    scheme_image.write_bytes(b"scheme")

    result = PaperReadService(tmp_path, default_config()).read("ABCD1234", mode="figures")
    targets = {target["targetType"]: target for target in result["figures"]}

    assert set(targets) == {"figure", "table", "scheme", "equation"}
    for target in targets.values():
        assert {
            "targetLabel",
            "targetPanel",
            "page",
            "caption",
            "sourceLink",
            "imagePath",
            "imageExists",
            "visualMode",
            "contentType",
            "content",
            "context",
        } <= target.keys()
        assert target["sourceLink"]
    assert targets["figure"]["targetLabel"] == "Figure 2"
    assert targets["figure"]["visualMode"] == "image"
    assert targets["figure"]["imageExists"] is True

    table = targets["table"]
    assert table["targetLabel"] == "Table 1"
    assert table["visualMode"] == "table_text"
    assert table["contentType"] == "table"
    assert table["imagePath"] is None
    assert table["imageExists"] is False
    assert "| Catalyst | Yield |" in table["content"]
    assert "| A | 42% |" in table["context"]

    scheme = targets["scheme"]
    assert scheme["targetLabel"] == "Scheme 3"
    assert scheme["visualMode"] == "image"
    assert scheme["imageExists"] is True
    assert scheme["imagePath"].endswith("/ABCD1234-pathway.png")

    equation = targets["equation"]
    assert equation["targetLabel"] == "Equation 5"
    assert equation["visualMode"] == "equation_text"
    assert equation["contentType"] == "equation"
    assert equation["imagePath"] is None
    assert equation["imageExists"] is False
    assert r"C_{\mathrm{CO_2}}" in equation["content"]
    assert r"C_{\mathrm{CO_2}}" in equation["context"]

    passage_types = {passage.get("contentType") for passage in result["passages"]}
    assert {"image", "table", "equation"} <= passage_types

    scheme_image.unlink()
    missing_scheme = {
        target["targetType"]: target
        for target in PaperReadService(tmp_path, default_config()).read(
            "ABCD1234",
            mode="figures",
        )["figures"]
    }["scheme"]
    assert missing_scheme["imageExists"] is False
    assert missing_scheme["visualMode"] == "caption_context"


def test_paper_read_missing_full_text_is_structured_and_read_only(tmp_path: Path) -> None:
    note = tmp_path / "Literature" / "ABCD1234.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        compose_frontmatter({"title": "Metadata only", "zoteroKey": "ABCD1234"}, "# Metadata only\n"),
        encoding="utf-8",
    )

    result = PaperReadService(tmp_path, default_config()).read("ABCD1234")

    assert result["ok"]
    assert result["passages"] == []
    assert "mineru" in result["missing"]
    assert result["basicCoverage"]["fullTextAvailable"] is False
    assert not (tmp_path / ".obsidian-vault-mcp").exists()


def test_paper_read_uses_configured_mineru_markdown_path(tmp_path: Path) -> None:
    config = default_config()
    config["mineru"]["markdownFolder"] = "Extracted/Markdown"
    config["naming"]["mineruMarkdown"] = "parsed-{shortTitle}-{zoteroKey}.md"
    note = tmp_path / "Literature" / "ABCD1234.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        compose_frontmatter(
            {
                "title": "Custom extraction",
                "zoteroKey": "ABCD1234",
                "attachmentMinerULink": (
                    "[[Extracted/Markdown/parsed-Custom extraction-ABCD1234]]"
                ),
            },
            "# Custom extraction\n",
        ),
        encoding="utf-8",
    )
    mineru = (
        tmp_path
        / "Extracted"
        / "Markdown"
        / "parsed-Custom extraction-ABCD1234.md"
    )
    mineru.parent.mkdir(parents=True)
    mineru.write_text(
        compose_frontmatter(
            {"title": "Custom extraction", "zoteroKey": "ABCD1234"},
            "## Results\n\nConfigured MinerU content is readable.\n",
        ),
        encoding="utf-8",
    )

    result = PaperReadService(tmp_path, config).read("ABCD1234", mode="full")

    assert result["basicCoverage"]["fullTextAvailable"] is True
    assert result["passages"][0]["text"] == "Configured MinerU content is readable."
    assert result["passages"][0]["sourceLink"] == (
        "[[Extracted/Markdown/parsed-Custom extraction-ABCD1234.md#Results]]"
    )
    assert result["warnings"] == []
