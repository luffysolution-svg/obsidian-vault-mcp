from __future__ import annotations

from pathlib import Path

from obsidian_vault_mcp.application.verify_service import VerifyService
from obsidian_vault_mcp.config.defaults import default_config
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter


def test_verify_reports_missing_references_orphans_and_affected_keys(tmp_path: Path) -> None:
    note = tmp_path / "Literature" / "ABCD1234.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        compose_frontmatter(
            {
                "title": "Paper",
                "itemType": "journalArticle",
                "zoteroKey": "ABCD1234",
                "attachmentMinerULink": "[[Literature/attachment/MinerU/ABCD1234]]",
            },
            "# Paper\n",
        ),
        encoding="utf-8",
    )
    mineru = tmp_path / "Literature" / "attachment" / "MinerU" / "ABCD1234.md"
    mineru.parent.mkdir(parents=True)
    mineru.write_text(
        compose_frontmatter(
            {"title": "Paper", "zoteroKey": "ABCD1234", "sourcePdf": "../ABCD1234.pdf"},
            (
                "# Paper\n\n"
                "![exists](image/ABCD1234/ABCD1234-fig01.png)\n\n"
                "![missing](image/ABCD1234/ABCD1234-fig02.png)\n"
            ),
        ),
        encoding="utf-8",
    )
    image_dir = mineru.parent / "image" / "ABCD1234"
    image_dir.mkdir(parents=True)
    (image_dir / "ABCD1234-fig01.png").write_bytes(b"one")
    (image_dir / "ABCD1234-fig03.png").write_bytes(b"orphan")

    # Removed manifests are ignored, even if malformed.
    stale_manifest = tmp_path / ".obsidian-vault-mcp" / "cache" / "mineru-assets" / "ABCD1234" / "manifest.json"
    stale_manifest.parent.mkdir(parents=True)
    stale_manifest.write_text("{not-json", encoding="utf-8")

    result = VerifyService(tmp_path, default_config()).verify()

    assert result["missingImageReferences"] == [
        {
            "zoteroKey": "ABCD1234",
            "markdownPath": "Literature/attachment/MinerU/ABCD1234.md",
            "imagePath": "Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig02.png",
        }
    ]
    assert result["orphanImages"] == [
        {
            "zoteroKey": "ABCD1234",
            "imagePath": "Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig03.png",
        }
    ]
    assert result["affectedZoteroKeys"] == ["ABCD1234"]
    assert result["counts"]["byCode"]["missing-mineru-image"] == 1
    assert result["counts"]["byCode"]["orphan-mineru-image"] == 1


def test_verify_image_scan_is_isolated_per_key(tmp_path: Path) -> None:
    mineru_root = tmp_path / "Literature" / "attachment" / "MinerU"
    for key in ("ABCD1234", "WXYZ5678"):
        markdown = mineru_root / f"{key}.md"
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(
            compose_frontmatter(
                {"title": key, "zoteroKey": key, "sourcePdf": f"../{key}.pdf"},
                f"![image](image/{key}/{key}-fig01.png)\n",
            ),
            encoding="utf-8",
        )
        image = mineru_root / "image" / key / f"{key}-fig01.png"
        image.parent.mkdir(parents=True)
        image.write_bytes(key.encode())

    result = VerifyService(tmp_path, default_config()).verify()

    assert result["missingImageReferences"] == []
    assert result["orphanImages"] == []
    assert result["affectedZoteroKeys"] == []


def test_verify_uses_configured_mineru_markdown_folder_and_name(
    tmp_path: Path,
) -> None:
    config = default_config()
    config["mineru"]["markdownFolder"] = "Extracted/Markdown"
    config["mineru"]["imageFolder"] = "Extracted/Assets"
    config["naming"]["mineruMarkdown"] = "parsed-{shortTitle}-{zoteroKey}.md"
    note = tmp_path / "Literature" / "ABCD1234.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        compose_frontmatter(
            {
                "title": "Custom extraction",
                "itemType": "journalArticle",
                "zoteroKey": "ABCD1234",
                "attachmentPdfLink": "[[Literature/attachment/ABCD1234.pdf]]",
                "attachmentMinerULink": (
                    "[[Extracted/Markdown/parsed-Custom extraction-ABCD1234]]"
                ),
            },
            "# Custom extraction\n",
        ),
        encoding="utf-8",
    )
    pdf = tmp_path / "Literature" / "attachment" / "ABCD1234.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"pdf")
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
            "![figure](../Assets/ABCD1234/ABCD1234-fig01.png)\n",
        ),
        encoding="utf-8",
    )
    image = (
        tmp_path
        / "Extracted"
        / "Assets"
        / "ABCD1234"
        / "ABCD1234-fig01.png"
    )
    image.parent.mkdir(parents=True)
    image.write_bytes(b"png")

    result = VerifyService(tmp_path, config).verify()

    assert result["ok"] is True
    assert result["missingImageReferences"] == []
    assert result["orphanImages"] == []
    assert result["affectedZoteroKeys"] == []
