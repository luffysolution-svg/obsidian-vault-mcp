from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

import obsidian_vault_mcp.application.transaction_service as transaction_module
from obsidian_vault_mcp.application.migration_service import MigrationService
from obsidian_vault_mcp.domain.errors import AtomicWriteError, TransactionError
from obsidian_vault_mcp.domain.frontmatter import parse_frontmatter


def _write_v1_fixture(vault: Path) -> None:
    (vault / ".obsidian").mkdir()
    (vault / "literature").mkdir()
    (vault / "assets" / "zotero" / "ABCD1234").mkdir(parents=True)
    (vault / "sources" / "mineru" / "images").mkdir(parents=True)
    (vault / "notes").mkdir()

    (vault / "assets" / "zotero" / "ABCD1234" / "old-paper.pdf").write_bytes(b"%PDF-1.4\noriginal-pdf\n")
    (vault / "sources" / "mineru" / "images" / "chart.png").write_bytes(b"PNG-original")
    (vault / "sources" / "mineru" / "paper.md").write_text(
        "---\n"
        "type: mineru-extraction\n"
        "title: Old extraction\n"
        "zoteroKey: ABCD1234\n"
        "sourcePdf: C:/Users/private/Zotero/paper.pdf\n"
        "mineruStatus: parsed\n"
        "customMineruField: keep-me\n"
        "---\n\n"
        "# Extracted text\n\n"
        "![Performance](images/chart.png)\n",
        encoding="utf-8",
    )
    (vault / "literature" / "Readable Old Name.md").write_text(
        "---\n"
        "type: literature\n"
        "title: Stable Identity Paper\n"
        "authors:\n"
        "  - Smith, Jane\n"
        "year: 2024\n"
        "publicationTitle: Journal of Migration Tests\n"
        "doi: 10.1000/migrate\n"
        "abstract: Migrated abstract.\n"
        "zoteroKey: ABCD1234\n"
        "zoteroVersion: 17\n"
        "zoteroAttachmentPaths:\n"
        "  - C:/Users/private/Zotero/storage/ABCD1234/paper.pdf\n"
        "attachments:\n"
        "  - assets/zotero/ABCD1234/old-paper.pdf\n"
        "attachmentLinks:\n"
        "  - '[[assets/zotero/ABCD1234/old-paper.pdf]]'\n"
        "mineruStatus: parsed\n"
        "mineruMarkdown: sources/mineru/paper.md\n"
        "mineruMarkdownLink: '[[sources/mineru/paper]]'\n"
        "status: reading\n"
        "rating: 5\n"
        "customField: keep-me\n"
        "---\n\n"
        "# Stable Identity Paper\n\n"
        "## Abstract\n\n"
        "Stale body abstract.\n\n"
        "## PDF\n\n"
        "![[assets/zotero/ABCD1234/old-paper.pdf]]\n\n"
        "## MinerU Extraction\n\n"
        "[[sources/mineru/paper]]\n\n"
        "## Zotero Notes & Annotations\n\n"
        "A migrated Zotero child note.\n\n"
        "## BibTeX\n\n"
        "```bibtex\n@article{migrate2024, title={Stable Identity Paper}}\n```\n\n"
        "## Reading Notes\n\n"
        "My durable reading note.\n\n"
        "## Custom Chapter\n\n"
        "This user section must survive.\n",
        encoding="utf-8",
    )
    (vault / "notes" / "Related.md").write_text(
        "# Related\n\nSee [[literature/Readable Old Name|the migrated paper]].\n",
        encoding="utf-8",
    )


def _tree(vault: Path) -> dict[str, bytes]:
    return {
        path.relative_to(vault).as_posix(): path.read_bytes()
        for path in sorted(vault.rglob("*"))
        if path.is_file() and ".obsidian-vault-mcp" not in path.relative_to(vault).parts
    }


def test_dry_run_is_a_zero_write_preview(tmp_path: Path) -> None:
    _write_v1_fixture(tmp_path)
    before = _tree(tmp_path)

    result = MigrationService(tmp_path).migrate(dry_run=True, apply=False, transaction_id="migration-dry")

    assert result["ok"]
    assert result["status"] == "dry-run"
    assert result["dryRun"]
    assert result["canApply"]
    assert result["changeCount"] > 0
    assert _tree(tmp_path) == before
    assert not (tmp_path / ".obsidian-vault-mcp").exists()
    assert not (tmp_path / ".obsidian-vault-mcp.json").exists()


def test_apply_normalizes_assets_frontmatter_state_and_links_then_rolls_back(tmp_path: Path) -> None:
    _write_v1_fixture(tmp_path)
    original = _tree(tmp_path)
    service = MigrationService(tmp_path)

    result = service.migrate(dry_run=False, apply=True, transaction_id="migration-apply")

    assert result["ok"]
    assert result["status"] == "committed"
    assert result["applied"]
    assert not (tmp_path / "literature" / "Readable Old Name.md").exists()
    assert not (tmp_path / "assets" / "zotero" / "ABCD1234" / "old-paper.pdf").exists()
    assert not (tmp_path / "sources" / "mineru" / "paper.md").exists()
    assert not (tmp_path / "sources" / "mineru" / "images" / "chart.png").exists()

    note_path = tmp_path / "Literature" / "ABCD1234.md"
    pdf_path = tmp_path / "Literature" / "attachment" / "ABCD1234.pdf"
    mineru_path = tmp_path / "Literature" / "attachment" / "MinerU" / "ABCD1234.md"
    image_path = (
        tmp_path
        / "Literature"
        / "attachment"
        / "MinerU"
        / "image"
        / "ABCD1234"
        / "ABCD1234-fig01.png"
    )
    assert pdf_path.read_bytes() == b"%PDF-1.4\noriginal-pdf\n"
    assert image_path.read_bytes() == b"PNG-original"

    note_text = note_path.read_text(encoding="utf-8")
    note = parse_frontmatter(note_text)
    assert note.fields["zoteroKey"] == "ABCD1234"
    assert note.fields["journal"] == "Journal of Migration Tests"
    assert note.fields["attachmentPdfLink"] == "[[Literature/attachment/ABCD1234.pdf]]"
    assert note.fields["attachmentMinerULink"] == "[[Literature/attachment/MinerU/ABCD1234]]"
    assert note.fields["status"] == "reading"
    assert note.fields["rating"] == 5
    assert note.fields["customField"] == "keep-me"
    assert "zoteroAttachmentPaths" not in note.fields
    assert "mineruStatus" not in note.fields
    assert "C:/Users/private" not in note_text
    assert "My durable reading note." in note.body
    assert "This user section must survive." in note.body
    assert "![[Literature/attachment/ABCD1234.pdf]]" in note.body
    assert "[[Literature/attachment/MinerU/ABCD1234]]" in note.body
    for section in ("abstract", "pdf", "mineru", "zotero-notes", "bibtex"):
        assert note.body.count(f"<!-- ovm:{section}:start -->") == 1
        assert note.body.count(f"<!-- ovm:{section}:end -->") == 1
    assert note.body.count("## Reading Notes") == 1
    assert "## MinerU Extraction" not in note.body
    assert "Stale body abstract." not in note.body
    assert "Migrated abstract." in note.body
    assert "A migrated Zotero child note." in note.body

    mineru_text = mineru_path.read_text(encoding="utf-8")
    mineru = parse_frontmatter(mineru_text)
    assert mineru.fields["zoteroKey"] == "ABCD1234"
    assert mineru.fields["sourcePdf"] == "../ABCD1234.pdf"
    assert mineru.fields["customMineruField"] == "keep-me"
    assert "mineruStatus" not in mineru.fields
    assert "C:/Users/private" not in mineru_text
    assert "![Performance](image/ABCD1234/ABCD1234-fig01.png)" in mineru.body

    related = (tmp_path / "notes" / "Related.md").read_text(encoding="utf-8")
    assert "[[Literature/ABCD1234|the migrated paper]]" in related

    state = (tmp_path / ".obsidian-vault-mcp" / "state" / "items" / "ABCD1234.json").read_text(encoding="utf-8")
    assert '"notePath": "Literature/ABCD1234.md"' in state
    assert '"zoteroVersion": 17' in state
    assert '"pdfPath": "Literature/attachment/ABCD1234.pdf"' in state
    assert '"mineruPath": "Literature/attachment/MinerU/ABCD1234.md"' in state
    assert "C:/Users/private" not in state
    assert "[[Literature/ABCD1234|Stable Identity Paper]]" in (tmp_path / "Literature" / "index.md").read_text(encoding="utf-8")
    assert (tmp_path / "Literature" / "Literature.base").is_file()
    config = (tmp_path / ".obsidian-vault-mcp.json").read_text(encoding="utf-8")
    assert '"schemaVersion": 2' in config

    repeated = service.migrate(dry_run=True, apply=False, transaction_id="migration-repeat")
    assert repeated["status"] == "noop"
    assert repeated["itemCount"] == 0

    rolled_back = service.rollback(result["transactionId"])

    assert rolled_back["status"] == "rolled-back"
    assert _tree(tmp_path) == original
    assert not (tmp_path / ".obsidian-vault-mcp.json").exists()


def test_duplicate_zotero_key_is_structured_and_apply_is_refused(tmp_path: Path) -> None:
    (tmp_path / ".obsidian").mkdir()
    old = tmp_path / "literature"
    old.mkdir()
    for name in ("First.md", "Second.md"):
        (old / name).write_text(
            f"---\ntitle: {name}\nzoteroKey: DUPL1234\n---\n\n# {name}\n",
            encoding="utf-8",
        )
    before = _tree(tmp_path)

    result = MigrationService(tmp_path).migrate(dry_run=False, apply=True, transaction_id="migration-duplicate")

    assert not result["ok"]
    assert not result["canApply"]
    assert result["status"] == "conflict"
    assert result["duplicates"] == [
        {
            "zoteroKey": "DUPL1234",
            "sources": ["literature/First.md", "literature/Second.md"],
        }
    ]
    assert result["conflicts"][0]["type"] == "duplicate-zotero-key"
    assert _tree(tmp_path) == before
    assert not (tmp_path / ".obsidian-vault-mcp").exists()


def test_apply_failure_automatically_restores_the_entire_v1_tree(tmp_path: Path) -> None:
    _write_v1_fixture(tmp_path)
    before = _tree(tmp_path)
    original_replace = transaction_module._replace_owned
    calls = 0

    def fail_during_commit(
        filesystem: object,
        source: str,
        destination: str,
    ) -> Path:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise AtomicWriteError("injected migration failure")
        return original_replace(filesystem, source, destination)

    with mock.patch.object(
        transaction_module,
        "_replace_owned",
        side_effect=fail_during_commit,
    ):
        with pytest.raises(TransactionError) as caught:
            MigrationService(tmp_path).migrate(dry_run=False, apply=True, transaction_id="migration-failure")

    assert caught.value.details["restored"]
    assert _tree(tmp_path) == before
    assert not (tmp_path / ".obsidian-vault-mcp.json").exists()


def test_existing_v2_target_is_reported_and_preserved_by_default(tmp_path: Path) -> None:
    (tmp_path / ".obsidian").mkdir()
    old = tmp_path / "literature"
    old.mkdir()
    (old / "Old.md").write_text("---\ntitle: Old\nzoteroKey: COLL1234\n---\n\n# Old\n", encoding="utf-8")
    target = tmp_path / "Literature" / "COLL1234.md"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(b"existing-v2")

    result = MigrationService(tmp_path).migrate(dry_run=False, apply=True, transaction_id="migration-collision")

    assert not result["ok"]
    assert any(conflict["type"] == "target-exists" for conflict in result["conflicts"])
    assert target.read_bytes() == b"existing-v2"


def test_rename_policy_uses_a_deterministic_alternate_target(tmp_path: Path) -> None:
    (tmp_path / ".obsidian").mkdir()
    old = tmp_path / "literature"
    old.mkdir()
    source = old / "Old.md"
    source.write_text("---\ntitle: Old\nzoteroKey: RENA1234\n---\n\n# Old\n\n## Reading Notes\n\nKeep.\n", encoding="utf-8")
    target = tmp_path / "Literature" / "RENA1234.md"
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(b"existing-v2")

    result = MigrationService(tmp_path).migrate(
        dry_run=False,
        apply=True,
        transaction_id="migration-rename",
        conflict_policy="rename",
    )

    alternate = tmp_path / "Literature" / "RENA1234-migrated-01.md"
    assert result["ok"]
    assert result["conflicts"] == []
    assert result["items"][0]["targetNote"] == "Literature/RENA1234-migrated-01.md"
    assert target.read_bytes() == b"existing-v2"
    assert parse_frontmatter(alternate.read_text(encoding="utf-8")).fields["zoteroKey"] == "RENA1234"
    repeated = MigrationService(tmp_path).migrate(dry_run=True, transaction_id="migration-rename-repeat")
    assert repeated["status"] == "noop"
