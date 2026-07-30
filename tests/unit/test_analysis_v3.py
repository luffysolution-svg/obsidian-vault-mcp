from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_vault_mcp.application.analysis_base_service import AnalysisBaseService
from obsidian_vault_mcp.application.analysis_service import AnalysisService
from obsidian_vault_mcp.config.defaults import CONFIG_FILENAME, default_config
from obsidian_vault_mcp.domain.analysis import (
    AnalysisValidationError,
    build_analysis_identity,
    combined_source_fingerprint,
    markdown_source_fingerprint,
)
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
    else:  # pragma: no cover
        raise AssertionError(analysis_type)
    fields["analysisId"] = build_analysis_identity(fields).analysis_id
    return fields


@pytest.fixture
def analysis_service(tmp_path: Path) -> AnalysisService:
    _write_source(tmp_path, KEY_A)
    _write_source(tmp_path, KEY_B)
    return AnalysisService(tmp_path, now=lambda: NOW)


def test_source_fingerprint_uses_configured_mineru_markdown_path(tmp_path: Path) -> None:
    _write_source(tmp_path, KEY_A, title="Custom source")
    config = default_config()
    config["mineru"]["markdownFolder"] = "Extracted/Markdown"
    config["naming"]["mineruMarkdown"] = "parsed-{year}-{shortTitle}-{zoteroKey}.md"
    mineru = tmp_path / "Extracted" / "Markdown" / f"parsed-2026-Custom source-{KEY_A}.md"
    mineru.parent.mkdir(parents=True)
    mineru_text = compose_frontmatter(
        {"title": "Custom source", "zoteroKey": KEY_A},
        "## Results\n\nFingerprint this configured full text.\n",
    )
    mineru.write_text(mineru_text, encoding="utf-8")

    result = AnalysisService(tmp_path, config).source_fingerprint([KEY_A])
    assert result == combined_source_fingerprint({KEY_A: markdown_source_fingerprint(mineru_text)})


@pytest.mark.parametrize(
    ("analysis_type", "folder"),
    [
        ("full_read", "Literature/Analysis/full-reads"),
        ("literature_review", "Literature/Analysis/reviews"),
        ("passage_qa", "Literature/Analysis/qa/passages"),
        ("figure_qa", "Literature/Analysis/qa/figures"),
        ("concept", "Literature/Analysis/concepts"),
    ],
)
def test_all_analysis_types_write_idempotently_to_their_canonical_folder(
    analysis_service: AnalysisService,
    analysis_type: str,
    folder: str,
) -> None:
    fields = _payload(analysis_service, analysis_type)
    first = analysis_service.write(fields, f"# {analysis_type}\n", transaction_id=f"write-{analysis_type}")

    assert first["status"] == "committed"
    assert first["analysisPath"].startswith(f"{folder}/")
    document = parse_frontmatter(
        analysis_service.vault_path.joinpath(*first["analysisPath"].split("/")).read_text(encoding="utf-8")
    )
    assert document.fields["analysisId"] == fields["analysisId"]
    assert document.fields["sourceCount"] == len(fields["sourceKeys"])
    assert "<!-- ovm:analysis:start -->" in document.body
    assert "<!-- ovm:analysis:end -->" in document.body

    repeated = analysis_service.write(fields, f"# {analysis_type}\n", transaction_id=f"noop-{analysis_type}")
    assert repeated["status"] == "noop"


def test_write_preserves_user_owned_content(analysis_service: AnalysisService) -> None:
    fields = _payload(analysis_service, "passage_qa")
    result = analysis_service.write(fields, "First answer.\n", transaction_id="initial-analysis")
    path = analysis_service.vault_path.joinpath(*result["analysisPath"].split("/"))
    document = parse_frontmatter(path.read_text(encoding="utf-8"))
    document.fields["reviewer"] = "Lin"
    path.write_text(
        compose_frontmatter(document.fields, document.body + "\n## User Notes\n\nKeep this.\n"),
        encoding="utf-8",
    )

    analysis_service.write(fields, "Updated answer.\n", transaction_id="update-analysis")
    after = parse_frontmatter(path.read_text(encoding="utf-8"))
    assert after.fields["reviewer"] == "Lin"
    assert "Updated answer." in after.body
    assert "First answer." not in after.body
    assert "## User Notes\n\nKeep this." in after.body


def test_dry_run_stale_detection_and_rollback(analysis_service: AnalysisService) -> None:
    fields = _payload(analysis_service, "full_read")
    preview = analysis_service.write(fields, "Managed.\n", dry_run=True, transaction_id="preview-analysis")
    assert preview["status"] == "dry-run"

    committed = analysis_service.write(fields, "Managed.\n", transaction_id="commit-analysis")
    path = analysis_service.vault_path.joinpath(*committed["analysisPath"].split("/"))
    assert path.exists()

    source = analysis_service.vault_path / "Literature" / f"{KEY_A}.md"
    source.write_text(source.read_text(encoding="utf-8").replace("Paper QZBLIATR", "Changed title"), encoding="utf-8")
    found = analysis_service.get(analysis_id=str(fields["analysisId"]))
    assert found["analysis"]["sourceChanged"] is True
    assert found["analysis"]["effectiveStatus"] == "needs_update"

    rolled_back = analysis_service.rollback("commit-analysis")
    assert rolled_back["status"] == "rolled-back"
    assert not path.exists()


def test_validation_rejects_removed_fields_and_missing_images(
    analysis_service: AnalysisService,
) -> None:
    fields = _payload(analysis_service, "full_read")
    fields["evidenceStatus"] = "partial"
    with pytest.raises(AnalysisValidationError, match="removed"):
        analysis_service.write(fields, "Managed.")

    figure = _payload(analysis_service, "figure_qa")
    figure["imagePath"] = "Literature/attachment/MinerU/image/missing.png"
    with pytest.raises(AnalysisValidationError, match="imageExists"):
        analysis_service.write(figure, "Managed.")


def test_custom_analysis_paths_are_loaded_without_a_migration_layer(tmp_path: Path) -> None:
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
    (tmp_path / CONFIG_FILENAME).write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    analysis = AnalysisService(tmp_path)
    base = AnalysisBaseService(tmp_path)

    assert analysis.analysis_folder == "Custom/Analysis"
    assert analysis.analysis_path("full_read", "FR-KEY.md") == "Custom/Analysis/full/FR-KEY.md"
    assert base.analysis_folder == "Custom/Analysis"
    assert base.base_path == "Custom/Analysis/Workspace.base"
