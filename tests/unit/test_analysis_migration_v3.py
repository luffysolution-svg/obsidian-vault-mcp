from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from obsidian_vault_mcp.adapters.vault.filesystem import VaultPathSafetyError
from obsidian_vault_mcp.application.analysis_migration_service import AnalysisMigrationService
from obsidian_vault_mcp.application.analysis_service import AnalysisService
from obsidian_vault_mcp.domain.analysis import build_analysis_identity
from obsidian_vault_mcp.domain.errors import TransactionError
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter, parse_frontmatter

KEY = "QZBLIATR"
NOW = "2026-07-29T22:00:00+08:00"


def _create_directory_link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            pytest.skip(
                f"could not create a Windows junction: {result.stderr or result.stdout}"
            )
        return
    link.symlink_to(target, target_is_directory=True)


def _remove_directory_link(link: Path) -> None:
    if not os.path.lexists(link):
        return
    if os.name == "nt":
        os.rmdir(link)
    else:
        link.unlink()


def _legacy_fields(service: AnalysisService) -> dict[str, object]:
    fields: dict[str, object] = {
        "analysisType": "passage_qa",
        "analysisProfile": "chemistry",
        "secondaryProfiles": [],
        "title": "Legacy passage answer",
        "status": "ready",
        "analysisFocus": "Locate the claim.",
        "primarySourceKey": KEY,
        "primarySource": f"[[Literature/{KEY}]]",
        "sourceKeys": [KEY],
        "sourceCount": 1,
        "summary": "A short answer.",
        "sourceFingerprint": service.source_fingerprint([KEY]),
        "skillName": "passage-qa",
        "skillVersion": "1.0.0",
        "createdAt": NOW,
        "updatedAt": NOW,
        "tags": ["legacy"],
        "question": "Where is the claim?",
        "answerSummary": "In Results.",
        "sourceSection": "Results",
        "sourceSubsection": "",
        "sourceParagraph": 3,
        "sourceLink": f"[[Literature/attachment/MinerU/{KEY}#Results]]",
        "locatorQuality": "exact",
        "quoteFingerprint": "sha256:quote",
        "evidenceStatus": "partial",
        "uncertaintyCount": 2,
        "reviewer": "Lin",
    }
    return fields


def _vault_with_legacy_analysis(tmp_path: Path) -> tuple[AnalysisMigrationService, Path, Path]:
    source_note = tmp_path / "Literature" / f"{KEY}.md"
    source_note.parent.mkdir(parents=True)
    source_note.write_text(
        compose_frontmatter(
            {
                "title": "Paper",
                "abstract": "Abstract",
                "year": 2026,
                "doi": "10.1000/example",
                "zoteroKey": KEY,
            },
            "# Source\n",
        ),
        encoding="utf-8",
    )
    analysis_service = AnalysisService(tmp_path, now=lambda: NOW)
    legacy = tmp_path / "Literature" / "Analysis" / f"{KEY}.md"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        compose_frontmatter(
            _legacy_fields(analysis_service),
            (
                "<!-- ovm:analysis:start -->\n"
                "Claim [[evidence:E-1]] and image [[asset:A-1]]. ^ev-old\n"
                "<!-- ovm:analysis:end -->\n\n"
                "## User Notes\n\nKeep this user text.\n\n"
                "## Unknown Section\n\nKeep this too.\n"
            ),
        ),
        encoding="utf-8",
    )
    index = legacy.parent / "index.md"
    index.write_text(
        "<!-- ovm:analysis-index:start -->\n"
        "# Literature Analysis Index\n"
        "<!-- ovm:analysis-index:end -->\n",
        encoding="utf-8",
    )
    topic = tmp_path / "Literature" / "Topic" / "ambiguous.md"
    topic.parent.mkdir(parents=True)
    topic.write_text("# Ambiguous topic\n", encoding="utf-8")
    theory = tmp_path / "Literature" / "Theory" / "ambiguous.md"
    theory.parent.mkdir(parents=True)
    theory.write_text("# Ambiguous theory\n", encoding="utf-8")
    return AnalysisMigrationService(tmp_path, now=lambda: NOW), legacy, index


def test_analysis_migration_defaults_to_dry_run_and_reports_ambiguous_notes(tmp_path: Path) -> None:
    service, legacy, index = _vault_with_legacy_analysis(tmp_path)

    report = service.migrate(transaction_id="analysis-migration-preview")

    assert report["status"] == "dry-run"
    assert report["dryRun"] is True
    assert len(report["migratedAnalyses"]) == 1
    assert report["removedEvidenceAnchors"] == 1
    assert report["removedAssetAnchors"] == 1
    assert report["oldIndexRemoved"] is True
    assert report["analysisBaseCreated"] is True
    assert report["topicFilesPending"] == ["Literature/Topic/ambiguous.md"]
    assert report["theoryFilesPending"] == ["Literature/Theory/ambiguous.md"]
    assert legacy.exists()
    assert index.exists()


def test_analysis_migration_preserves_content_is_idempotent_and_rolls_back(tmp_path: Path) -> None:
    service, legacy, index = _vault_with_legacy_analysis(tmp_path)
    fields = _legacy_fields(AnalysisService(tmp_path, now=lambda: NOW))
    identity = build_analysis_identity(fields)
    destination = tmp_path / "Literature" / "Analysis" / "qa" / "passages" / identity.filename

    applied = service.migrate(
        dry_run=False,
        apply=True,
        transaction_id="analysis-migration-apply",
    )
    assert applied["status"] == "committed"
    assert not legacy.exists()
    assert not index.exists()
    assert destination.exists()
    document = parse_frontmatter(destination.read_text(encoding="utf-8"))
    assert document.fields["analysisSchemaVersion"] == 1
    assert document.fields["analysisId"] == identity.analysis_id
    assert document.fields["reviewer"] == "Lin"
    assert "evidenceStatus" not in document.fields
    assert "uncertaintyCount" not in document.fields
    assert "[[evidence:" not in document.body
    assert "[[asset:" not in document.body
    assert "^ev-" not in document.body
    assert "## User Notes\n\nKeep this user text." in document.body
    assert "## Unknown Section\n\nKeep this too." in document.body
    assert (tmp_path / "Literature" / "Topic" / "ambiguous.md").exists()
    assert (tmp_path / "Literature" / "Theory" / "ambiguous.md").exists()
    assert (tmp_path / "Literature" / "Analysis" / "Analysis.base").exists()

    repeated = service.migrate(
        dry_run=False,
        apply=True,
        transaction_id="analysis-migration-noop",
    )
    assert repeated["migratedAnalyses"] == []
    assert repeated["status"] == "noop"

    rolled_back = service.rollback("analysis-migration-apply")
    assert rolled_back["status"] == "rolled-back"
    assert legacy.exists()
    assert index.exists()
    assert not destination.exists()


def test_analysis_migration_preserves_manual_index_that_mentions_project(
    tmp_path: Path,
) -> None:
    source_note = tmp_path / "Literature" / f"{KEY}.md"
    source_note.parent.mkdir(parents=True)
    source_note.write_text(
        compose_frontmatter({"title": "Paper", "zoteroKey": KEY}, "# Source\n"),
        encoding="utf-8",
    )
    index = tmp_path / "Literature" / "Analysis" / "index.md"
    index.parent.mkdir(parents=True)
    index.write_text(
        "# My manual index\n\nNotes about obsidian-vault-mcp behavior.\n",
        encoding="utf-8",
    )

    report = AnalysisMigrationService(tmp_path, now=lambda: NOW).migrate(
        transaction_id="manual-index-preview"
    )

    assert report["status"] == "dry-run"
    assert report["oldIndexRemoved"] is False
    assert any(
        item["path"] == "Literature/Analysis/index.md"
        and "preserved" in item["reasons"][0]
        for item in report["manualReviewRequired"]
    )
    assert index.is_file()


def test_analysis_migration_preserves_existing_custom_base(tmp_path: Path) -> None:
    base = tmp_path / "Literature" / "Analysis" / "Analysis.base"
    base.parent.mkdir(parents=True)
    custom = "filters:\n  and:\n    - custom == true\n"
    base.write_text(custom, encoding="utf-8")

    report = AnalysisMigrationService(tmp_path, now=lambda: NOW).migrate(
        dry_run=False,
        apply=True,
        transaction_id="custom-base-preserved",
    )

    assert report["status"] == "noop"
    assert report["analysisBaseCreated"] is False
    assert base.read_text(encoding="utf-8") == custom
    assert any(
        item["path"] == "Literature/Analysis/Analysis.base"
        and "preserved" in item["reasons"][0]
        for item in report["manualReviewRequired"]
    )


def test_unknown_analysis_note_is_reported_but_never_cleaned_in_place(
    tmp_path: Path,
) -> None:
    note = tmp_path / "Literature" / "Analysis" / "personal.md"
    note.parent.mkdir(parents=True)
    original = compose_frontmatter(
        {
            "owner": "Lin",
            "verificationStatus": "personal-review",
            "uncertaintyCount": 7,
        },
        "# Personal note\n\nKeep every field and line.\n",
    )
    note.write_text(original, encoding="utf-8")
    original_bytes = note.read_bytes()

    report = AnalysisMigrationService(tmp_path, now=lambda: NOW).migrate(
        dry_run=False,
        apply=True,
        transaction_id="unknown-analysis-preserved",
    )

    assert report["status"] == "committed"
    assert report["migratedAnalyses"] == []
    assert note.read_bytes() == original_bytes
    assert any(
        item["path"] == "Literature/Analysis/personal.md"
        and "could not be inferred" in item["reasons"][0]
        for item in report["manualReviewRequired"]
    )


def test_invalid_inferred_legacy_note_is_preserved_without_cleanup_counts(
    tmp_path: Path,
) -> None:
    note = tmp_path / "Literature" / "Analysis" / "PQ-invalid.md"
    note.parent.mkdir(parents=True)
    original = compose_frontmatter(
        {
            "analysisType": "passage_qa",
            "title": "Recognized but incomplete",
            "evidenceStatus": "partial",
            "uncertaintyCount": 2,
        },
        (
            "<!-- ovm:analysis:start -->\n"
            "Legacy [[evidence:E-1]] and [[asset:A-1]]. ^ev-old\n"
            "<!-- ovm:analysis:end -->\n"
        ),
    )
    note.write_text(original, encoding="utf-8")
    original_bytes = note.read_bytes()

    report = AnalysisMigrationService(tmp_path, now=lambda: NOW).migrate(
        dry_run=False,
        apply=True,
        transaction_id="invalid-inferred-analysis-preserved",
    )

    assert report["status"] == "committed"
    assert report["migratedAnalyses"] == []
    assert report["removedEvidenceAnchors"] == 0
    assert report["removedAssetAnchors"] == 0
    assert note.read_bytes() == original_bytes
    assert any(
        item["path"] == "Literature/Analysis/PQ-invalid.md"
        for item in report["manualReviewRequired"]
    )


def test_analysis_migration_cleans_polluted_already_v3_note_and_rolls_back(
    tmp_path: Path,
) -> None:
    source_note = tmp_path / "Literature" / f"{KEY}.md"
    source_note.parent.mkdir(parents=True)
    source_note.write_text(
        compose_frontmatter(
            {
                "title": "Paper",
                "abstract": "Abstract",
                "year": 2026,
                "doi": "10.1000/example",
                "zoteroKey": KEY,
            },
            "# Source\n",
        ),
        encoding="utf-8",
    )
    analysis = AnalysisService(tmp_path, now=lambda: NOW)
    fields = _legacy_fields(analysis)
    fields["analysisSchemaVersion"] = 1
    fields["analysisId"] = build_analysis_identity(fields).analysis_id
    target = (
        tmp_path
        / "Literature"
        / "Analysis"
        / "qa"
        / "passages"
        / f"{fields['analysisId']}.md"
    )
    target.parent.mkdir(parents=True)
    original = compose_frontmatter(
        fields,
        "<!-- ovm:analysis:start -->\n"
        "Legacy [[evidence:E-1]] and [[asset:A-1]]. ^ev-old\n"
        "<!-- ovm:analysis:end -->\n",
        omit_empty=False,
    )
    target.write_text(original, encoding="utf-8")
    service = AnalysisMigrationService(tmp_path, now=lambda: NOW)

    preview = service.migrate(transaction_id="polluted-v3-preview")
    cleaned = next(
        item
        for item in preview["skippedAnalyses"]
        if item["reason"] == "already-v3-cleaned"
    )
    assert cleaned["removedFields"] == ["evidenceStatus", "uncertaintyCount"]
    assert target.read_text(encoding="utf-8") == original

    applied = service.migrate(
        dry_run=False,
        apply=True,
        transaction_id="polluted-v3-apply",
    )
    assert applied["status"] == "committed"
    document = parse_frontmatter(target.read_text(encoding="utf-8"))
    assert "evidenceStatus" not in document.fields
    assert "uncertaintyCount" not in document.fields
    assert "[[evidence:" not in document.body
    assert "[[asset:" not in document.body
    assert "^ev-" not in document.body

    assert service.rollback("polluted-v3-apply")["status"] == "rolled-back"
    assert target.read_text(encoding="utf-8") == original


def test_analysis_migration_rejects_unimplemented_conflict_policies(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="only conflict_policy preserve-user"):
        AnalysisMigrationService(tmp_path).migrate(conflict_policy="fail")


def test_analysis_migration_preserves_removed_anchor_literals_outside_managed_block(
    tmp_path: Path,
) -> None:
    service, legacy, index = _vault_with_legacy_analysis(tmp_path)
    original = legacy.read_text(encoding="utf-8")
    original = original.replace(
        "Keep this user text.",
        "Keep literal [[evidence:USER-1]] and ^ev-user exactly.",
    )
    legacy.write_text(original, encoding="utf-8")

    report = service.migrate(
        dry_run=False,
        apply=True,
        transaction_id="analysis-user-anchor-preserve",
    )

    assert legacy.read_text(encoding="utf-8") == original
    assert index.exists()
    assert report["migratedAnalyses"] == []
    assert report["oldIndexRemoved"] is False
    assert any(
        item["path"] == "Literature/Analysis/QZBLIATR.md"
        and "outside the managed block" in " ".join(item["reasons"])
        for item in report["manualReviewRequired"]
    )


def test_analysis_migration_aborts_when_source_changes_after_planning(
    tmp_path: Path,
) -> None:
    service, legacy, index = _vault_with_legacy_analysis(tmp_path)
    original_recheck = service._recheck_snapshots

    def edit_then_recheck(snapshots: dict[str, str | None]) -> None:
        legacy.write_text(
            legacy.read_text(encoding="utf-8") + "\nConcurrent user edit.\n",
            encoding="utf-8",
        )
        original_recheck(snapshots)

    service._recheck_snapshots = edit_then_recheck  # type: ignore[method-assign]

    with pytest.raises(TransactionError, match="changed after planning"):
        service.migrate(
            dry_run=False,
            apply=True,
            transaction_id="analysis-concurrent-edit",
        )

    assert legacy.exists()
    assert "Concurrent user edit." in legacy.read_text(encoding="utf-8")
    assert index.exists()
    assert not (
        tmp_path / "Literature" / "Analysis" / "qa" / "passages"
    ).exists()


def test_analysis_migration_never_reads_or_writes_through_analysis_junction(
    tmp_path: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    outside = tmp_path / "outside-analysis"
    outside.mkdir()
    sentinel = outside / "FR-OUTSIDE.md"
    sentinel.write_text(
        compose_frontmatter(
            {
                "analysisType": "full_read",
                "zoteroKey": KEY,
                "analysisStatus": "verified",
            },
            "OUTSIDE-SENTINEL\n",
        ),
        encoding="utf-8",
    )
    linked = vault / "Literature" / "Analysis"
    _create_directory_link(linked, outside)
    try:
        with pytest.raises(VaultPathSafetyError):
            AnalysisMigrationService(vault, now=lambda: NOW).migrate(
                transaction_id="analysis-linked-root"
            )

        assert sentinel.read_text(encoding="utf-8").endswith("OUTSIDE-SENTINEL\n")
        assert not (outside / "Analysis.base").exists()
    finally:
        _remove_directory_link(linked)
