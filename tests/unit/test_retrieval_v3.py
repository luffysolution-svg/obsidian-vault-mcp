from __future__ import annotations

import json
from pathlib import Path

from obsidian_vault_mcp.application.retrieval_service import RetrievalService
from obsidian_vault_mcp.config.defaults import default_config
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter


def _write_record(
    vault: Path,
    key: str,
    *,
    title: str,
    abstract: str,
    tags: list[str],
    full_text: str | None,
) -> None:
    note = vault / "Literature" / f"{key}.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        compose_frontmatter(
            {
                "title": title,
                "itemType": "journalArticle",
                "zoteroKey": key,
                "abstract": abstract,
                "tags": tags,
            },
            f"# {title}\n",
        ),
        encoding="utf-8",
    )
    if full_text is not None:
        mineru = vault / "Literature" / "attachment" / "MinerU" / f"{key}.md"
        mineru.parent.mkdir(parents=True, exist_ok=True)
        mineru.write_text(
            compose_frontmatter(
                {"title": title, "zoteroKey": key, "sourcePdf": f"../{key}.pdf"},
                f"# {title}\n\n## Results\n\n{full_text}\n",
            ),
            encoding="utf-8",
        )


def test_retrieve_uses_transient_passages_and_basic_coverage_only(tmp_path: Path) -> None:
    _write_record(
        tmp_path,
        "ABCD1234",
        title="Visible-light catalyst",
        abstract="Catalyst overview.",
        tags=["catalysis"],
        full_text="The cobalt catalyst produced hydrogen under visible light.",
    )
    _write_record(
        tmp_path,
        "WXYZ5678",
        title="Battery separator",
        abstract="Electrochemical separator.",
        tags=["battery"],
        full_text="The separator reduced dendrite growth.",
    )
    poison = tmp_path / ".obsidian-vault-mcp" / "state" / "evidence" / "ABCD1234.json"
    poison.parent.mkdir(parents=True)
    poison.write_text("{not-json", encoding="utf-8")
    before = poison.read_bytes()

    result = RetrievalService(tmp_path, default_config()).retrieve(
        "hydrogen",
        depth="evidence",
        max_candidate_papers=5,
        max_snippet_papers=5,
        per_paper_top_k=2,
        max_total_snippets=5,
    )

    assert result["ok"]
    assert [paper["zoteroKey"] for paper in result["paperMatches"]] == ["ABCD1234"]
    assert result["snippets"]
    assert result["snippets"][0]["paragraphIndex"] == 1
    assert "evidenceId" not in result["snippets"][0]
    assert "coverage" not in result and "coverageLedger" not in result
    assert result["basicCoverage"]["poolTotal"] == 2
    assert result["basicCoverage"]["fullTextScanned"] == 2
    assert poison.read_bytes() == before
    assert not (tmp_path / ".obsidian-vault-mcp" / "state" / "coverage").exists()


def test_retrieve_scope_metadata_depth_and_budgets_are_deterministic(tmp_path: Path) -> None:
    _write_record(
        tmp_path,
        "ABCD1234",
        title="Catalyst A",
        abstract="Hydrogen evolution.",
        tags=["catalysis", "visible-light"],
        full_text="Result A.",
    )
    _write_record(
        tmp_path,
        "WXYZ5678",
        title="Catalyst B",
        abstract="Hydrogen evolution.",
        tags=["catalysis"],
        full_text=None,
    )

    result = RetrievalService(tmp_path, default_config()).retrieve(
        "",
        scope={"tags": ["visible-light"]},
        intent="enumerate",
        depth="metadata",
        max_candidate_papers=1,
    )

    assert [paper["zoteroKey"] for paper in result["paperMatches"]] == ["ABCD1234"]
    assert result["snippets"] == []
    assert result["basicCoverage"]["metadataChecked"] == 1
    assert result["basicCoverage"]["fullTextScanned"] == 0
    assert result["basicCoverage"]["exhaustive"] is True


def test_retrieve_collection_scope_uses_item_state_membership(tmp_path: Path) -> None:
    _write_record(
        tmp_path,
        "ABCD1234",
        title="Collection paper",
        abstract="Scoped through internal item state.",
        tags=[],
        full_text=None,
    )
    state_path = tmp_path / ".obsidian-vault-mcp" / "state" / "items" / "ABCD1234.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "schemaVersion": 2,
                "zoteroKey": "ABCD1234",
                "collectionKeys": ["COLLECTION-A"],
            }
        ),
        encoding="utf-8",
    )

    result = RetrievalService(tmp_path, default_config()).retrieve(
        "",
        scope={"collection_key": "COLLECTION-A"},
        intent="enumerate",
        depth="metadata",
    )

    assert [paper["zoteroKey"] for paper in result["paperMatches"]] == ["ABCD1234"]
    assert result["warnings"] == []


def test_retrieve_accepts_documented_compare_intent(tmp_path: Path) -> None:
    _write_record(
        tmp_path,
        "ABCD1234",
        title="Catalyst comparison",
        abstract="Compare catalyst mechanisms.",
        tags=["catalysis"],
        full_text="Catalyst A follows a radical pathway.",
    )

    result = RetrievalService(tmp_path, default_config()).retrieve(
        "catalyst",
        intent="compare",
        depth="evidence",
    )

    assert result["ok"] is True
    assert result["intent"] == "compare"
    assert result["paperMatches"][0]["zoteroKey"] == "ABCD1234"


def test_retrieve_uses_configured_mineru_markdown_path(tmp_path: Path) -> None:
    _write_record(
        tmp_path,
        "ABCD1234",
        title="Custom extraction",
        abstract="Metadata does not contain the target phrase.",
        tags=[],
        full_text=None,
    )
    config = default_config()
    config["mineru"]["markdownFolder"] = "Extracted/Markdown"
    config["naming"]["mineruMarkdown"] = "parsed-{shortTitle}-{zoteroKey}.md"
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
            "## Results\n\nA quasicrystal signal appears only in full text.\n",
        ),
        encoding="utf-8",
    )

    result = RetrievalService(tmp_path, config).retrieve(
        "quasicrystal",
        depth="evidence",
    )

    assert [paper["zoteroKey"] for paper in result["paperMatches"]] == [
        "ABCD1234"
    ]
    assert result["paperMatches"][0]["fullTextAvailable"] is True
    assert result["snippets"][0]["text"] == (
        "A quasicrystal signal appears only in full text."
    )
    assert result["snippets"][0]["sourceLink"] == (
        "[[Extracted/Markdown/parsed-Custom extraction-ABCD1234.md#Results]]"
    )
