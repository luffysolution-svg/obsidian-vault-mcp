from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_vault_mcp.application.coverage_service import CoverageService
from obsidian_vault_mcp.domain.coverage import CoverageRecord


def test_coverage_records_are_transactional_incremented_and_staled(tmp_path: Path) -> None:
    service = CoverageService(tmp_path)
    first = service.record(
        "ABCD1234",
        source_kind="mineru",
        topic="catalyst mechanism",
        granularity="passage",
        coverage="targeted",
        confidence="high",
        content_hash="sha-old",
        tool_name="literature_paper_read",
        evidence_refs=["ABCD1234-results-a1"],
        valid_evidence_ids={"ABCD1234-results-a1"},
        now="2026-07-29T00:00:00Z",
    )
    assert first["status"] == "committed"

    repeated = service.record(
        "ABCD1234",
        source_kind="mineru",
        topic="catalyst mechanism",
        granularity="passage",
        coverage="targeted",
        confidence="high",
        content_hash="sha-old",
        tool_name="literature_paper_read",
        evidence_refs=["ABCD1234-results-a1"],
        valid_evidence_ids={"ABCD1234-results-a1"},
        now="2026-07-29T00:00:01Z",
    )
    assert repeated["incremented"] is True
    assert repeated["coverageRecord"]["count"] == 2

    service.record(
        "ABCD1234",
        source_kind="mineru",
        topic="catalyst mechanism",
        granularity="passage",
        coverage="targeted",
        confidence="high",
        content_hash="sha-new",
        tool_name="literature_paper_read",
        now="2026-07-29T00:00:02Z",
    )
    state = service.load("ABCD1234")
    assert len(state["records"]) == 2
    assert next(item for item in state["records"] if item["contentHash"] == "sha-old")["stale"] is True
    assert next(item for item in state["records"] if item["contentHash"] == "sha-new")["stale"] is False


def test_coverage_dry_run_and_invalid_state_degrade_without_touching_user_files(tmp_path: Path) -> None:
    service = CoverageService(tmp_path)
    preview = service.record(
        "ABCD1234",
        source_kind="zotero_metadata",
        topic="",
        granularity="metadata",
        coverage="listed",
        confidence="high",
        content_hash="metadata-hash",
        tool_name="literature_retrieve",
        dry_run=True,
        transaction_id="coverage-preview",
        now="2026-07-29T00:00:00Z",
    )
    assert preview["status"] == "dry-run"
    assert not (tmp_path / ".obsidian-vault-mcp" / "state" / "coverage" / "ABCD1234.json").exists()

    path = tmp_path / ".obsidian-vault-mcp" / "state" / "coverage" / "ABCD1234.json"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    state = service.load("ABCD1234")
    assert state["records"] == []
    assert state["warnings"][0]["code"] == "invalid-coverage-state"


def test_coverage_rejects_false_completeness_and_unknown_references(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="cannot be marked complete"):
        CoverageRecord(
            resource_key="paper:ABCD1234",
            source_kind="abstract",
            topic="",
            granularity="abstract",
            coverage="complete",
            confidence="high",
            content_hash="x",
            tool_name="literature_paper_read",
        )

    service = CoverageService(tmp_path)
    with pytest.raises(ValueError, match="unknown evidenceId"):
        service.record(
            "ABCD1234",
            source_kind="evidence_index",
            topic="query",
            granularity="passage",
            coverage="targeted",
            confidence="high",
            content_hash="x",
            tool_name="literature_paper_read",
            evidence_refs=["made-up"],
            valid_evidence_ids=set(),
        )


def test_coverage_state_is_stable_json(tmp_path: Path) -> None:
    service = CoverageService(tmp_path)
    service.record(
        "ABCD1234",
        source_kind="mineru_image",
        topic="figure",
        granularity="figure",
        coverage="targeted",
        confidence="medium",
        content_hash="asset-sha",
        tool_name="literature_paper_read",
        asset_refs=["IMG-ABCD1234-a1"],
        valid_asset_ids={"IMG-ABCD1234-a1"},
        details={"visualStatus": "mineru_candidate"},
        now="2026-07-29T00:00:00Z",
    )
    path = tmp_path / ".obsidian-vault-mcp" / "state" / "coverage" / "ABCD1234.json"
    parsed = json.loads(path.read_text(encoding="utf-8"))
    assert list(parsed) == ["schemaVersion", "zoteroKey", "records"]
    assert parsed["records"][0]["assetRefs"] == ["IMG-ABCD1234-a1"]
