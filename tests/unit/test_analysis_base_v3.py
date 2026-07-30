from __future__ import annotations

from pathlib import Path

import yaml

import obsidian_vault_mcp.application.analysis_base_service as base_module
from obsidian_vault_mcp.adapters.obsidian.analysis_base_renderer import (
    analysis_base_document,
    render_analysis_base,
)
from obsidian_vault_mcp.application.analysis_base_service import AnalysisBaseService


def test_analysis_base_has_recursive_filter_and_all_nine_views() -> None:
    document = analysis_base_document()

    assert 'file.inFolder("Literature/Analysis")' in document["filters"]["and"]
    assert "analysisId != null" in document["filters"]["and"]
    views = {view["name"]: view for view in document["views"]}
    assert list(views) == [
        "Dashboard",
        "Full Reads",
        "Reviews",
        "Passage Q&A",
        "Figure Q&A",
        "Concepts",
        "Needs Attention",
        "By Discipline",
        "Recently Updated",
    ]
    assert views["Dashboard"]["filters"] == {"and": ['status != "archived"']}
    assert views["Full Reads"]["filters"] == {"and": ['analysisType == "full_read"']}
    assert views["Reviews"]["filters"] == {"and": ['analysisType == "literature_review"']}
    assert views["Passage Q&A"]["filters"] == {"and": ['analysisType == "passage_qa"']}
    assert views["Figure Q&A"]["filters"] == {"and": ['analysisType == "figure_qa"']}
    assert views["Concepts"]["filters"] == {"and": ['analysisType == "concept"']}
    assert views["Needs Attention"]["filters"]["or"] == [
        'status == "draft"',
        'status == "ready"',
        'status == "needs_update"',
    ]
    assert views["By Discipline"]["groupBy"]["property"] == "analysisProfile"
    assert views["Recently Updated"]["sort"] == [{"property": "updatedAt", "direction": "DESC"}]
    assert "full body" not in render_analysis_base().lower()


def test_analysis_base_service_is_transactional_and_never_creates_index(tmp_path: Path) -> None:
    service = AnalysisBaseService(tmp_path)
    base_path = tmp_path / "Literature" / "Analysis" / "Analysis.base"
    index_path = tmp_path / "Literature" / "Analysis" / "index.md"

    preview = service.rebuild(dry_run=True, transaction_id="analysis-base-preview")
    assert preview["status"] == "dry-run"
    assert not base_path.exists()

    committed = service.rebuild(transaction_id="analysis-base-write")
    assert committed["status"] == "committed"
    assert yaml.safe_load(base_path.read_text(encoding="utf-8"))["views"][0]["name"] == "Dashboard"
    assert not index_path.exists()
    assert service.rebuild(transaction_id="analysis-base-noop")["status"] == "noop"

    rolled_back = service.rollback("analysis-base-write")
    assert rolled_back["status"] == "rolled-back"
    assert not base_path.exists()


def test_analysis_base_preserves_custom_file_unless_overwrite_is_explicit(
    tmp_path: Path,
) -> None:
    base_path = tmp_path / "Literature" / "Analysis" / "Analysis.base"
    base_path.parent.mkdir(parents=True)
    custom = "filters:\n  and:\n    - custom == true\n"
    base_path.write_text(custom, encoding="utf-8")
    service = AnalysisBaseService(tmp_path)

    preserved = service.rebuild(transaction_id="preserve-custom-base")

    assert preserved["status"] == "noop"
    assert preserved["preservedUserBase"] is True
    assert preserved["warnings"][0]["code"] == "analysis-base-user-content-preserved"
    assert base_path.read_text(encoding="utf-8") == custom

    replaced = service.rebuild(
        transaction_id="replace-custom-base",
        conflict_policy="overwrite-managed",
    )

    assert replaced["status"] == "committed"
    assert replaced["preservedUserBase"] is False
    assert base_path.read_text(encoding="utf-8") == render_analysis_base()


def test_analysis_base_rebuild_and_rollback_share_base_lock(
    tmp_path: Path,
    monkeypatch,
) -> None:
    entered: list[str] = []

    class RecordingGlobalLock:
        def __init__(self, _vault_path: Path, name: str) -> None:
            self.name = name

        def __enter__(self) -> RecordingGlobalLock:
            entered.append(self.name)
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(base_module, "GlobalLock", RecordingGlobalLock)
    service = AnalysisBaseService(tmp_path)
    service.rebuild(transaction_id="shared-base-lock-write")
    service.rollback("shared-base-lock-write")

    assert entered == ["base", "base"]
