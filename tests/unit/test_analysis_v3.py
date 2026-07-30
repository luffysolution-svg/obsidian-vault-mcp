from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from obsidian_vault_mcp.application.analysis_base_service import AnalysisBaseService
from obsidian_vault_mcp.application.analysis_migration_service import AnalysisMigrationService
from obsidian_vault_mcp.application.analysis_service import AnalysisService
from obsidian_vault_mcp.application.transaction_service import Transaction
from obsidian_vault_mcp.config.defaults import CONFIG_FILENAME, default_config
from obsidian_vault_mcp.domain.analysis import (
    AnalysisValidationError,
    build_analysis_identity,
    combined_source_fingerprint,
    markdown_source_fingerprint,
)
from obsidian_vault_mcp.domain.errors import TransactionError
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter, parse_frontmatter

KEY_A = "QZBLIATR"
KEY_B = "ABCD1234"
NOW = "2026-07-29T22:00:00+08:00"


def _write_source(vault: Path, key: str, *, title: str | None = None) -> None:
    source = vault / "Literature" / f"{key}.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        compose_frontmatter(
            {
                "title": title or f"Paper {key}",
                "abstract": f"Abstract for {key}",
                "year": 2026,
                "doi": f"10.1000/{key.lower()}",
                "zoteroKey": key,
            },
            "# Source\n",
        ),
        encoding="utf-8",
    )


def _common(
    service: AnalysisService,
    analysis_type: str,
    *,
    keys: list[str],
    primary: str = "",
) -> dict[str, object]:
    return {
        "analysisSchemaVersion": 1,
        "analysisId": "",
        "analysisType": analysis_type,
        "analysisProfile": "chemistry",
        "secondaryProfiles": ["materials"],
        "title": f"{analysis_type} title",
        "status": "ready",
        "analysisFocus": "Focus on the mechanism.",
        "primarySourceKey": primary,
        "primarySource": f"[[Literature/{primary}]]" if primary else "",
        "sourceKeys": keys,
        "sourceCount": len(keys),
        "summary": f"Short summary for {analysis_type}.",
        "sourceFingerprint": service.source_fingerprint(keys),
        "skillName": f"{analysis_type}-skill",
        "skillVersion": "1.0.0",
        "createdAt": NOW,
        "updatedAt": NOW,
        "tags": ["analysis"],
    }


def _payload(service: AnalysisService, analysis_type: str) -> dict[str, object]:
    if analysis_type == "full_read":
        fields = {
            **_common(service, analysis_type, keys=[KEY_A], primary=KEY_A),
            "paperTitle": "Paper A",
            "year": 2026,
            "journal": "Journal",
            "paperKind": "experimental",
            "researchQuestion": "What is the mechanism?",
            "coreContribution": "A concise contribution.",
            "methodSummary": "A concise method.",
            "mainFinding": "A concise finding.",
            "limitationSummary": "A concise limitation.",
        }
    elif analysis_type == "literature_review":
        fields = {
            **_common(service, analysis_type, keys=[KEY_B, KEY_A]),
            "reviewMode": "comparative",
            "reviewQuestion": "How do the mechanisms compare?",
            "scopeSummary": "Two papers.",
            "timeRange": "2024-2026",
            "taxonomySummary": "Two mechanism classes.",
            "consensusSummary": "Both report transfer.",
            "controversySummary": "The rate-limiting step differs.",
            "gapSummary": "No shared benchmark.",
            "conclusionSummary": "Conditions explain the difference.",
        }
    elif analysis_type == "passage_qa":
        fields = {
            **_common(service, analysis_type, keys=[KEY_A], primary=KEY_A),
            "question": "Where is charge transfer discussed?",
            "answerSummary": "It is discussed in Results.",
            "sourceSection": "Results",
            "sourceSubsection": "Charge transfer",
            "sourceParagraph": 6,
            "sourceLink": f"[[Literature/attachment/MinerU/{KEY_A}#Charge transfer]]",
            "locatorQuality": "exact",
            "quoteFingerprint": "sha256:quote",
        }
    elif analysis_type == "figure_qa":
        image_path = f"Literature/attachment/MinerU/image/{KEY_A}/{KEY_A}-fig02.png"
        image = service.vault_path.joinpath(*image_path.split("/"))
        image.parent.mkdir(parents=True, exist_ok=True)
        image.write_bytes(b"image")
        fields = {
            **_common(service, analysis_type, keys=[KEY_A], primary=KEY_A),
            "question": "What does Figure 2b show?",
            "answerSummary": "It shows faster transfer.",
            "targetType": "figure",
            "targetLabel": "Fig. 2",
            "targetPanel": "b",
            "page": 6,
            "imagePath": image_path,
            "imageExists": True,
            "visualMode": "image",
            "sourceLink": f"[[Literature/attachment/MinerU/{KEY_A}#Figure 2]]",
            "captionSummary": "Transfer comparison.",
        }
    elif analysis_type == "concept":
        fields = {
            **_common(service, analysis_type, keys=[KEY_A, KEY_B]),
            "conceptName": "Medium entropy",
            "conceptKind": "theory",
            "aliases": ["configurational entropy"],
            "definitionSummary": "An operational definition.",
            "relationSummary": "It relates composition to entropy.",
            "useSummary": "It guides material design.",
            "prerequisites": ["entropy"],
            "relatedConcepts": ["high entropy"],
        }
    else:  # pragma: no cover - helper guard
        raise AssertionError(analysis_type)
    identity = build_analysis_identity(fields)
    fields["analysisId"] = identity.analysis_id
    return fields


def test_source_fingerprint_uses_configured_mineru_markdown_path(
    tmp_path: Path,
) -> None:
    _write_source(tmp_path, KEY_A, title="Custom source")
    config = default_config()
    config["mineru"]["markdownFolder"] = "Extracted/Markdown"
    config["naming"]["mineruMarkdown"] = (
        "parsed-{year}-{shortTitle}-{zoteroKey}.md"
    )
    mineru = (
        tmp_path
        / "Extracted"
        / "Markdown"
        / f"parsed-2026-Custom source-{KEY_A}.md"
    )
    mineru.parent.mkdir(parents=True)
    mineru_text = compose_frontmatter(
        {"title": "Custom source", "zoteroKey": KEY_A},
        "## Results\n\nFingerprint this configured full text.\n",
    )
    mineru.write_text(mineru_text, encoding="utf-8")

    result = AnalysisService(tmp_path, config).source_fingerprint([KEY_A])

    assert result == combined_source_fingerprint(
        {KEY_A: markdown_source_fingerprint(mineru_text)}
    )


@pytest.fixture
def analysis_service(tmp_path: Path) -> AnalysisService:
    _write_source(tmp_path, KEY_A)
    _write_source(tmp_path, KEY_B)
    return AnalysisService(tmp_path, now=lambda: NOW)


@pytest.mark.parametrize(
    ("analysis_type", "folder", "prefix"),
    [
        ("full_read", "Literature/Analysis/full-reads", f"FR-{KEY_A}"),
        ("literature_review", "Literature/Analysis/reviews", "RV-how-do-the-mechanisms-"),
        ("passage_qa", "Literature/Analysis/qa/passages", f"PQ-{KEY_A}-"),
        ("figure_qa", "Literature/Analysis/qa/figures", f"FQ-{KEY_A}-FIG02B-"),
        ("concept", "Literature/Analysis/concepts", "CP-medium-entropy-"),
    ],
)
def test_all_analysis_types_use_stable_identity_and_correct_folder(
    analysis_service: AnalysisService,
    analysis_type: str,
    folder: str,
    prefix: str,
) -> None:
    fields = _payload(analysis_service, analysis_type)
    first = analysis_service.write(fields, f"# {analysis_type}\n", transaction_id=f"write-{analysis_type}")

    assert first["status"] == "committed"
    assert first["analysisPath"].startswith(f"{folder}/{prefix}")
    assert first["analysisPath"].endswith(".md")
    document = parse_frontmatter(
        analysis_service.vault_path.joinpath(*first["analysisPath"].split("/")).read_text(encoding="utf-8")
    )
    assert document.fields["analysisId"] == fields["analysisId"]
    assert document.fields["sourceCount"] == len(fields["sourceKeys"])
    assert "<!-- ovm:analysis:start -->" in document.body
    assert "<!-- ovm:analysis:end -->" in document.body

    repeated = analysis_service.write(fields, f"# {analysis_type}\n", transaction_id=f"noop-{analysis_type}")
    assert repeated["status"] == "noop"
    assert repeated["updatedAt"] == NOW


def test_identity_normalization_is_stable(analysis_service: AnalysisService) -> None:
    first = _payload(analysis_service, "passage_qa")
    second = dict(first)
    second["question"] = "  WHERE   is charge transfer discussed?  "

    assert build_analysis_identity(first) == build_analysis_identity(second)


def test_write_preserves_user_owned_body_and_unknown_frontmatter(
    analysis_service: AnalysisService,
) -> None:
    fields = _payload(analysis_service, "passage_qa")
    result = analysis_service.write(fields, "First answer.\n", transaction_id="initial-analysis")
    path = analysis_service.vault_path.joinpath(*result["analysisPath"].split("/"))
    document = parse_frontmatter(path.read_text(encoding="utf-8"))
    document.fields["reviewer"] = "Lin"
    body = document.body + "\n## User Notes\n\nKeep this.\n\n## Custom Section\n\nAlso keep this.\n"
    path.write_text(compose_frontmatter(document.fields, body), encoding="utf-8")

    updated = analysis_service.write(fields, "Updated answer.\n", transaction_id="update-analysis")
    assert updated["status"] == "committed"
    after = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert after.fields["reviewer"] == "Lin"
    assert "Updated answer." in after.body
    assert "First answer." not in after.body
    assert "## User Notes\n\nKeep this." in after.body
    assert "## Custom Section\n\nAlso keep this." in after.body


def test_write_rejects_a_target_changed_after_the_user_snapshot(
    tmp_path: Path,
) -> None:
    _write_source(tmp_path, KEY_A)
    _write_source(tmp_path, KEY_B)
    initial_service = AnalysisService(tmp_path, now=lambda: NOW)
    fields = _payload(initial_service, "passage_qa")
    result = initial_service.write(
        fields,
        "Original managed answer.\n",
        transaction_id="snapshot-initial",
    )
    path = tmp_path.joinpath(*result["analysisPath"].split("/"))

    def concurrent_edit() -> str:
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n## Concurrent User Notes\n\nDo not overwrite this.\n",
            encoding="utf-8",
        )
        return "2026-07-29T23:00:00+08:00"

    guarded_service = AnalysisService(tmp_path, now=concurrent_edit)
    with pytest.raises(TransactionError, match="changed after planning"):
        guarded_service.write(
            fields,
            "Replacement managed answer.\n",
            transaction_id="snapshot-conflict",
        )

    preserved = path.read_text(encoding="utf-8")
    assert "Do not overwrite this." in preserved
    assert "Original managed answer." in preserved
    assert "Replacement managed answer." not in preserved


def test_write_supports_dry_run_rollback_and_stale_source_detection(
    analysis_service: AnalysisService,
) -> None:
    fields = _payload(analysis_service, "full_read")
    identity = build_analysis_identity(fields)
    expected = analysis_service.vault_path / "Literature" / "Analysis" / "full-reads" / identity.filename

    preview = analysis_service.write(fields, "Managed.\n", dry_run=True, transaction_id="preview-analysis")
    assert preview["status"] == "dry-run"
    assert not expected.exists()

    committed = analysis_service.write(fields, "Managed.\n", transaction_id="commit-analysis")
    assert committed["status"] == "committed"
    assert expected.exists()

    source = analysis_service.vault_path / "Literature" / f"{KEY_A}.md"
    source.write_text(source.read_text(encoding="utf-8").replace("Paper QZBLIATR", "Changed title"), encoding="utf-8")
    found = analysis_service.get(analysis_id=str(fields["analysisId"]))
    assert found["analysis"]["sourceChanged"] is True
    assert found["analysis"]["effectiveStatus"] == "needs_update"
    assert "Managed." in found["analysis"]["body"]

    rolled_back = analysis_service.rollback("commit-analysis")
    assert rolled_back["status"] == "rolled-back"
    assert not expected.exists()


def test_write_enforces_reviewed_summary_source_and_image_rules(
    analysis_service: AnalysisService,
) -> None:
    reviewed = _payload(analysis_service, "full_read")
    reviewed["status"] = "reviewed"
    with pytest.raises(AnalysisValidationError, match="explicit user confirmation"):
        analysis_service.write(reviewed, "Managed.")
    assert analysis_service.write(
        reviewed,
        "Managed.",
        reviewed_by_user=True,
        transaction_id="reviewed-by-user",
    )["status"] == "committed"
    reviewed_without_status = dict(reviewed)
    reviewed_without_status.pop("status")
    assert analysis_service.write(
        reviewed_without_status,
        "Managed.",
        transaction_id="reviewed-noop",
    )["status"] == "noop"
    changed_reviewed = analysis_service.write(
        reviewed_without_status,
        "Changed managed content.",
        transaction_id="reviewed-content-change",
    )
    changed_document = parse_frontmatter(
        analysis_service.vault_path.joinpath(
            *changed_reviewed["analysisPath"].split("/")
        ).read_text(encoding="utf-8")
    )
    assert changed_document.fields["status"] == "ready"
    reconfirmed = dict(reviewed)
    assert analysis_service.write(
        reconfirmed,
        "Changed and reconfirmed.",
        reviewed_by_user=True,
        transaction_id="reviewed-reconfirmed",
    )["status"] == "committed"
    source = analysis_service.vault_path / "Literature" / f"{KEY_A}.md"
    source.write_text(
        source.read_text(encoding="utf-8").replace("Paper QZBLIATR", "Changed source"),
        encoding="utf-8",
    )
    stale_reviewed = dict(reviewed_without_status)
    stale_reviewed.pop("sourceFingerprint")
    stale = analysis_service.write(
        stale_reviewed,
        "Changed and reconfirmed.",
        transaction_id="reviewed-source-change",
    )
    stale_document = parse_frontmatter(
        analysis_service.vault_path.joinpath(
            *stale["analysisPath"].split("/")
        ).read_text(encoding="utf-8")
    )
    assert stale_document.fields["status"] == "needs_update"

    too_long = _payload(analysis_service, "concept")
    too_long["summary"] = "中" * 181
    with pytest.raises(AnalysisValidationError, match="180"):
        analysis_service.write(too_long, "Managed.")

    bad_count = _payload(analysis_service, "concept")
    bad_count["sourceCount"] = 1
    with pytest.raises(AnalysisValidationError, match="sourceCount"):
        analysis_service.write(bad_count, "Managed.")

    missing_image = _payload(analysis_service, "figure_qa")
    missing_image["imagePath"] = "Literature/attachment/MinerU/image/missing.png"
    with pytest.raises(AnalysisValidationError, match="imageExists"):
        analysis_service.write(missing_image, "Managed.")

    caption_only = _payload(analysis_service, "figure_qa")
    caption_only["imagePath"] = ""
    caption_only["imageExists"] = False
    caption_only["visualMode"] = "caption_context"
    with pytest.raises(AnalysisValidationError, match="embed"):
        analysis_service.write(caption_only, "![[missing.png]]")
    with pytest.raises(AnalysisValidationError, match="embed"):
        analysis_service.write(caption_only, "![missing][figure-one]\n\n[figure-one]: missing.png")
    with pytest.raises(AnalysisValidationError, match="HTML image"):
        analysis_service.write(caption_only, '<img src="missing.png">')


@pytest.mark.parametrize(
    "removed_field",
    ["evidenceStatus", "coverageLedger", "uncertaintyCount"],
)
def test_write_rejects_removed_v2_system_fields(
    analysis_service: AnalysisService,
    removed_field: str,
) -> None:
    fields = _payload(analysis_service, "full_read")
    fields[removed_field] = "legacy"

    with pytest.raises(AnalysisValidationError, match="removed V2 Analysis field"):
        analysis_service.write(fields, "Managed.")


def test_write_cleans_existing_removed_fields_but_preserves_user_frontmatter(
    analysis_service: AnalysisService,
) -> None:
    fields = _payload(analysis_service, "full_read")
    written = analysis_service.write(
        fields,
        "Managed.",
        transaction_id="write-before-pollution",
    )
    path = analysis_service.vault_path.joinpath(*written["analysisPath"].split("/"))
    document = parse_frontmatter(path.read_text(encoding="utf-8"))
    document.fields["evidenceStatus"] = "partial"
    document.fields["coverageLedger"] = {"legacy": True}
    document.fields["uncertaintyCount"] = 3
    document.fields["reviewer"] = "Lin"
    path.write_text(
        compose_frontmatter(document.fields, document.body),
        encoding="utf-8",
    )

    analysis_service.write(
        fields,
        "Managed.",
        transaction_id="clean-polluted-analysis",
    )
    cleaned = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert "evidenceStatus" not in cleaned.fields
    assert "coverageLedger" not in cleaned.fields
    assert "uncertaintyCount" not in cleaned.fields
    assert cleaned.fields["reviewer"] == "Lin"


def test_same_analysis_target_with_different_source_keys_commits_once(
    analysis_service: AnalysisService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _payload(analysis_service, "full_read")
    second = dict(first)
    second["sourceKeys"] = [KEY_A, KEY_B]
    second["sourceCount"] = 2
    second["sourceFingerprint"] = analysis_service.source_fingerprint(
        [KEY_A, KEY_B]
    )
    ready = threading.Barrier(2)
    original_commit = analysis_service.transactions._commit
    results: list[dict[str, Any]] = []
    errors: list[BaseException] = []

    def synchronized_commit(transaction: Transaction) -> dict[str, Any]:
        ready.wait(timeout=5)
        return original_commit(transaction)

    monkeypatch.setattr(
        analysis_service.transactions,
        "_commit",
        synchronized_commit,
    )

    def write(fields: dict[str, object], content: str, transaction_id: str) -> None:
        try:
            results.append(
                analysis_service.write(
                    fields,
                    content,
                    transaction_id=transaction_id,
                )
            )
        except BaseException as exc:
            errors.append(exc)

    threads = [
        threading.Thread(
            target=write,
            args=(first, "Managed from one source.", "same-target-one-source"),
        ),
        threading.Thread(
            target=write,
            args=(second, "Managed from two sources.", "same-target-two-sources"),
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], TransactionError)
    target = analysis_service.vault_path.joinpath(
        *str(results[0]["analysisPath"]).split("/")
    )
    written = target.read_text(encoding="utf-8")
    assert (
        "Managed from one source." in written
    ) != (
        "Managed from two sources." in written
    )


def test_get_filters_by_type_source_and_duplicate_question(
    analysis_service: AnalysisService,
) -> None:
    passage = _payload(analysis_service, "passage_qa")
    analysis_service.write(passage, "Passage.", transaction_id="query-passage")
    figure = _payload(analysis_service, "figure_qa")
    figure["question"] = passage["question"]
    figure["analysisId"] = build_analysis_identity(figure).analysis_id
    analysis_service.write(figure, "Figure.", transaction_id="query-figure")

    by_source = analysis_service.get(source_key=KEY_A)
    assert by_source["count"] == 2
    by_type = analysis_service.get(analysis_type="passage_qa")
    assert [item["analysisType"] for item in by_type["analyses"]] == ["passage_qa"]
    duplicate = analysis_service.get(question=str(passage["question"]))
    assert duplicate["duplicateQuestion"] is True
    assert len(duplicate["analyses"]) == 2


def test_write_rejects_invalid_managed_markers_and_conflict_policy(
    analysis_service: AnalysisService,
) -> None:
    fields = _payload(analysis_service, "full_read")
    with pytest.raises(AnalysisValidationError, match="managed block marker"):
        analysis_service.write(fields, "<!-- ovm:analysis:start -->")
    with pytest.raises(ValueError, match="conflict_policy"):
        analysis_service.write(fields, "Managed.", conflict_policy="rename")


def test_all_analysis_services_load_custom_vault_paths_when_config_is_omitted(
    tmp_path: Path,
) -> None:
    config = default_config()
    config["analysis"] = {
        "folder": "Custom/Analysis",
        "base": "Custom/Analysis/Workspace.base",
        "fullReadsFolder": "Custom/Analysis/full",
        "reviewsFolder": "Custom/Analysis/reviews",
        "passageQaFolder": "Custom/Analysis/qa/passages",
        "figureQaFolder": "Custom/Analysis/qa/figures",
        "conceptsFolder": "Custom/Analysis/concepts",
    }
    (tmp_path / CONFIG_FILENAME).write_text(
        json.dumps(config, ensure_ascii=False),
        encoding="utf-8",
    )

    analysis = AnalysisService(tmp_path)
    base = AnalysisBaseService(tmp_path)
    migration = AnalysisMigrationService(tmp_path)

    assert analysis.analysis_folder == "Custom/Analysis"
    assert analysis.analysis_path("full_read", "FR-KEY.md") == "Custom/Analysis/full/FR-KEY.md"
    assert base.analysis_folder == "Custom/Analysis"
    assert base.base_path == "Custom/Analysis/Workspace.base"
    assert migration.analysis.analysis_folder == "Custom/Analysis"
