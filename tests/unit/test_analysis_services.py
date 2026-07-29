from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from obsidian_vault_mcp.application.analysis_index_service import AnalysisIndexService
from obsidian_vault_mcp.application.analysis_service import AnalysisService
from obsidian_vault_mcp.application.evidence_service import EvidenceService
from obsidian_vault_mcp.application.uncertainty_service import UncertaintyService
from obsidian_vault_mcp.config.defaults import default_config
from obsidian_vault_mcp.domain.analysis import stable_uncertainty_id
from obsidian_vault_mcp.domain.errors import ConfigurationError, IdentityError
from obsidian_vault_mcp.domain.evidence import parse_evidence_markdown
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter, parse_frontmatter

KEY = "ABCD1234"
SOURCE_PATH = f"Literature/attachment/MinerU/{KEY}.md"
RELIABLE_BYTES = b"PNG"
CANDIDATE_BYTES = b"CANDIDATE"
RELIABLE_SHA = hashlib.sha256(RELIABLE_BYTES).hexdigest()
CANDIDATE_SHA = hashlib.sha256(CANDIDATE_BYTES).hexdigest()
ASSET_RELIABLE = f"IMG-{KEY}-{RELIABLE_SHA[:12]}"
ASSET_CANDIDATE = f"IMG-{KEY}-{CANDIDATE_SHA[:12]}"
_ANALYSIS_SOURCE = compose_frontmatter(
    {"title": "Photocatalytic Hydrogen Evolution", "zoteroKey": KEY},
    (
        "# Photocatalytic Hydrogen Evolution\n\n"
        "## Introduction\n\n"
        "The study addresses slow charge transfer. ^analysis-background\n\n"
        "## Materials and Methods\n\n"
        "Samples were tested by spectroscopy. ^analysis-method\n\n"
        "## Results\n\n"
        "Hydrogen evolution increased under illumination. ^analysis-result\n"
    ),
)
_ANALYSIS_CHUNKS = parse_evidence_markdown(
    _ANALYSIS_SOURCE,
    zotero_key=KEY,
    source_path=SOURCE_PATH,
).chunks
EVIDENCE_BACKGROUND = next(
    chunk.evidence_id for chunk in _ANALYSIS_CHUNKS if chunk.block_id == "analysis-background"
)
EVIDENCE_METHOD = next(
    chunk.evidence_id for chunk in _ANALYSIS_CHUNKS if chunk.block_id == "analysis-method"
)
EVIDENCE_RESULT = next(
    chunk.evidence_id for chunk in _ANALYSIS_CHUNKS if chunk.block_id == "analysis-result"
)


@pytest.fixture
def analysis_vault(tmp_path: Path) -> tuple[Path, dict]:
    config = default_config()
    main = tmp_path / "Literature" / f"{KEY}.md"
    main.parent.mkdir(parents=True)
    main.write_text(
        compose_frontmatter(
            {
                "title": "Photocatalytic Hydrogen Evolution",
                "itemType": "journalArticle",
                "year": 2025,
                "zoteroKey": KEY,
                "abstract": "A photocatalysis study.",
            },
            (
                "# Photocatalytic Hydrogen Evolution\n\n"
                "## Zotero Notes\n\n"
                "<!-- ovm:zotero-notes:start -->\n"
                "<!-- ovm:zotero-child-notes:start -->\n"
                "A Zotero child note about experimental design.\n"
                "<!-- ovm:zotero-child-notes:end -->\n\n"
                "<!-- ovm:zotero-annotations:start -->\n"
                "- p. 7: User annotation about charge transfer.\n"
                "<!-- ovm:zotero-annotations:end -->\n"
                "<!-- ovm:zotero-notes:end -->\n"
            ),
        ),
        encoding="utf-8",
    )
    source = tmp_path / SOURCE_PATH
    source.parent.mkdir(parents=True)
    source.write_text(_ANALYSIS_SOURCE, encoding="utf-8")
    image = tmp_path / "Literature" / "attachment" / "MinerU" / "image" / f"{KEY}-fig01.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(RELIABLE_BYTES)
    candidate = tmp_path / ".obsidian-vault-mcp" / "cache" / "mineru-assets" / KEY / "assets" / f"{ASSET_CANDIDATE}.png"
    candidate.parent.mkdir(parents=True)
    candidate.write_bytes(CANDIDATE_BYTES)
    manifest = candidate.parent.parent / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "zoteroKey": KEY,
                "sourceMarkdown": SOURCE_PATH,
                "sourceMarkdownSha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "generatedAt": "2026-07-29T00:00:00Z",
                "assets": [
                    {
                        "assetId": ASSET_RELIABLE,
                        "zoteroKey": KEY,
                        "sourceRelativePath": "images/figure.png",
                        "sourceRelativePaths": ["images/figure.png"],
                        "status": "referenced",
                        "extension": "png",
                        "sizeBytes": len(RELIABLE_BYTES),
                        "sha256": RELIABLE_SHA,
                        "visualStatus": "pdf_crop_available",
                        "normalizedPath": f"Literature/attachment/MinerU/image/{KEY}-fig01.png",
                        "cachePath": None,
                        "references": [],
                    },
                    {
                        "assetId": ASSET_CANDIDATE,
                        "zoteroKey": KEY,
                        "sourceRelativePath": "images/candidate.png",
                        "sourceRelativePaths": ["images/candidate.png"],
                        "status": "unlinked_candidate",
                        "extension": "png",
                        "sizeBytes": len(CANDIDATE_BYTES),
                        "sha256": CANDIDATE_SHA,
                        "visualStatus": "mineru_candidate",
                        "normalizedPath": None,
                        "cachePath": f".obsidian-vault-mcp/cache/mineru-assets/{KEY}/assets/{ASSET_CANDIDATE}.png",
                        "references": [],
                    },
                ],
                "counts": {"total": 2, "referenced": 1, "unlinkedCandidates": 1, "invalid": 0},
                "warnings": [],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    EvidenceService(tmp_path, config).rebuild(
        KEY,
        transaction_id="analysis-fixture-evidence",
        generated_at="2026-07-29T00:00:00Z",
    )
    return tmp_path, config


def test_stable_uncertainty_id_is_order_independent() -> None:
    first = stable_uncertainty_id(KEY, " A  claim ", " Needs evidence ", {"page": 7, "figure": "Figure 3"})
    second = stable_uncertainty_id(KEY, "A claim", "Needs evidence", {"figure": "Figure 3", "page": 7})
    assert first == second
    assert first.startswith(f"U-{KEY}-")


def test_context_returns_thirteen_evidence_mapped_sections(analysis_vault: tuple[Path, dict]) -> None:
    vault, config = analysis_vault
    result = AnalysisService(vault, config).context(KEY, focus="hydrogen")

    assert result["ok"] is True
    assert len(result["templateSections"]) == 13
    by_id = {section["sectionId"]: section for section in result["templateSections"]}
    assert EVIDENCE_METHOD in by_id["research-methods"]["evidenceIds"]
    assert EVIDENCE_RESULT in by_id["findings"]["evidenceIds"]
    assert "experimental design" in result["zoteroNotes"]
    assert "charge transfer" in result["zoteroAnnotations"]
    assert {asset["assetId"] for asset in result["figures"]} == {ASSET_RELIABLE, ASSET_CANDIDATE}
    assert result["coverage"]["availableEvidenceChunks"] == len(_ANALYSIS_CHUNKS)
    assert result["recommendedTargetedQueries"]


def test_analysis_write_preserves_user_content_and_is_dry_run_noop_and_rollback(
    analysis_vault: tuple[Path, dict],
) -> None:
    vault, config = analysis_vault
    analysis_path = vault / "Literature" / "Analysis" / f"{KEY}.md"
    analysis_path.parent.mkdir(parents=True)
    analysis_path.write_text(
        compose_frontmatter({"title": "Old", "zoteroKey": KEY, "reviewer": "Lin"}, "User-owned preface.\n"),
        encoding="utf-8",
    )
    service = AnalysisService(vault, config)
    sections = _sections()
    uncertainties = [_uncertainty()]

    preview = service.write(
        KEY,
        sections,
        uncertainties=uncertainties,
        embed_asset_ids=[ASSET_RELIABLE],
        updated_at="2026-07-29T10:00:00Z",
        dry_run=True,
        transaction_id="analysis-preview",
    )
    assert preview["status"] == "dry-run"
    assert "ovm:analysis:start" not in analysis_path.read_text(encoding="utf-8")

    committed = service.write(
        KEY,
        sections,
        uncertainties=uncertainties,
        embed_asset_ids=[ASSET_RELIABLE],
        updated_at="2026-07-29T10:00:00Z",
        transaction_id="analysis-write",
    )
    assert committed["status"] == "committed"
    document = parse_frontmatter(analysis_path.read_text(encoding="utf-8"))
    assert document.fields["reviewer"] == "Lin"
    assert document.fields["analysisStatus"] == "draft"
    assert document.fields["evidenceStatus"] == "partial"
    assert document.fields["uncertaintyCount"] == 1
    assert "User-owned preface." in document.body
    assert f"[[evidence:{EVIDENCE_METHOD}]]" in document.body
    assert f"![[Literature/attachment/MinerU/image/{KEY}-fig01.png]]" in document.body

    repeated = service.write(
        KEY,
        sections,
        uncertainties=uncertainties,
        embed_asset_ids=[ASSET_RELIABLE],
        updated_at="2026-07-29T10:00:00Z",
        transaction_id="analysis-noop",
    )
    assert repeated["status"] == "noop"
    assert service.rollback("analysis-write")["status"] == "rolled-back"
    restored = parse_frontmatter(analysis_path.read_text(encoding="utf-8"))
    assert restored.fields["reviewer"] == "Lin"
    assert "ovm:analysis:start" not in restored.body


def test_analysis_write_rejects_invalid_sources_and_unsafe_embeds(analysis_vault: tuple[Path, dict]) -> None:
    vault, config = analysis_vault
    service = AnalysisService(vault, config)
    with pytest.raises(ValueError, match="unknown evidenceId"):
        service.write(KEY, {"findings": [_claim("Unknown", evidence_ids=["missing-evidence"])]})
    with pytest.raises(ValueError, match="unlinked_candidate"):
        service.write(KEY, _sections(), embed_asset_ids=[ASSET_CANDIDATE])
    with pytest.raises(ValueError, match="forbidden windows-absolute-path"):
        service.write(KEY, {"findings": [_claim(r"Local C:\Users\name\paper.pdf")]})
    with pytest.raises(ValueError, match="raw image embeds"):
        service.write(KEY, {"findings": [_claim("![[Literature/attachment/MinerU/image/file.png]]")]})
    with pytest.raises(ValueError, match="unknown evidenceId"):
        service.write(KEY, {"findings": [_claim("Invented [[evidence:not-real]]")]} )

    source = vault / SOURCE_PATH
    source.write_text(source.read_text(encoding="utf-8") + "\nChanged after evidence rebuild.\n", encoding="utf-8")
    with pytest.raises(ValueError, match="persisted current EvidenceChunk state"):
        service.write(KEY, _sections(), transaction_id="stale-evidence-write")


def test_uncertainty_resolution_validates_visual_evidence_and_preserves_history(
    analysis_vault: tuple[Path, dict],
) -> None:
    vault, config = analysis_vault
    analysis = AnalysisService(vault, config)
    analysis.write(
        KEY,
        _sections(),
        uncertainties=[_uncertainty(figure="Figure 3")],
        updated_at="2026-07-29T10:00:00Z",
        transaction_id="analysis-for-resolution",
    )
    uncertainty_id = stable_uncertainty_id(
        KEY,
        "The morphology proves a charge-transfer mechanism.",
        "Only a candidate interpretation is available.",
        {"figure": "Figure 3"},
    )
    service = UncertaintyService(vault, config)
    assert service.list(KEY)["pendingCount"] == 1
    with pytest.raises(ValueError, match="unknown evidenceId"):
        service.resolve(KEY, uncertainty_id, "confirmed", evidence_ids=["missing"])
    with pytest.raises(ValueError, match="unlinked_candidate"):
        service.resolve(
            KEY,
            uncertainty_id,
            "confirmed",
            evidence_ids=[EVIDENCE_RESULT],
            asset_ids=[ASSET_CANDIDATE],
        )

    resolved = service.resolve(
        KEY,
        uncertainty_id,
        "confirmed",
        evidence_ids=[EVIDENCE_RESULT],
        asset_ids=[ASSET_RELIABLE],
        resolution_note="The PDF crop and Results text support the claim.",
        resolved_at="2026-07-29T11:00:00Z",
        transaction_id="uncertainty-resolve",
    )
    assert resolved["status"] == "committed"
    assert resolved["uncertainty"]["originalClaim"] == "The morphology proves a charge-transfer mechanism."
    listed = service.list(KEY)
    assert listed["pendingCount"] == 0
    assert len(listed["history"]) == 1
    analysis_document = parse_frontmatter(
        (vault / "Literature" / "Analysis" / f"{KEY}.md").read_text(encoding="utf-8")
    )
    assert analysis_document.fields["uncertaintyCount"] == 0
    assert "No pending review items" in analysis_document.body

    duplicate = service.resolve(
        KEY,
        uncertainty_id,
        "confirmed",
        evidence_ids=[EVIDENCE_RESULT],
        asset_ids=[ASSET_RELIABLE],
        resolution_note="The PDF crop and Results text support the claim.",
        transaction_id="uncertainty-noop",
    )
    assert duplicate["status"] == "noop"
    assert duplicate["historyCount"] == 1
    assert service.rollback("uncertainty-resolve")["status"] == "rolled-back"
    assert service.list(KEY)["pendingCount"] == 1


def test_analysis_index_is_stable_and_scans_only_analysis_folder(analysis_vault: tuple[Path, dict]) -> None:
    vault, config = analysis_vault
    AnalysisService(vault, config).write(
        KEY,
        _sections(),
        updated_at="2026-07-29T10:00:00Z",
        transaction_id="analysis-for-index",
    )
    for relative in (
        "Literature/Wiki/not-analysis.md",
        "Literature/Topic/not-analysis.md",
        "Literature/Theory/not-analysis.md",
        "Literature/attachment/MinerU/not-analysis.md",
    ):
        path = vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(compose_frontmatter({"title": "Wrong", "zoteroKey": "WXYZ5678"}, "# Wrong\n"), encoding="utf-8")

    service = AnalysisIndexService(vault, config)
    preview = service.rebuild(dry_run=True, transaction_id="analysis-index-preview")
    assert preview["status"] == "dry-run"
    assert not (vault / "Literature" / "Analysis" / "index.md").exists()
    committed = service.rebuild(transaction_id="analysis-index")
    assert committed["rowCount"] == 1
    assert committed["rows"][0]["zoteroKey"] == KEY
    text = (vault / "Literature" / "Analysis" / "index.md").read_text(encoding="utf-8")
    assert "agent_synthesis:" in text
    assert "WXYZ5678" not in text
    assert service.rebuild(transaction_id="analysis-index-noop")["status"] == "noop"
    assert service.rollback("analysis-index")["status"] == "rolled-back"
    assert not (vault / "Literature" / "Analysis" / "index.md").exists()

    duplicate = vault / "Literature" / "Analysis" / "duplicate.md"
    source = vault / "Literature" / "Analysis" / f"{KEY}.md"
    duplicate.write_bytes(source.read_bytes())
    with pytest.raises(IdentityError, match="duplicate Analysis zoteroKey"):
        service.rows()


def test_analysis_paths_follow_live_configuration(analysis_vault: tuple[Path, dict]) -> None:
    vault, config = analysis_vault
    config["analysis"].update(
        folder="Research/Reviews",
        index="Research/Reviews/catalog.md",
        topicFolder="Research/Topics",
        theoryFolder="Research/Theories",
    )
    analysis = AnalysisService(vault, config)
    written = analysis.write(
        KEY,
        _sections(),
        updated_at="2026-07-29T10:00:00Z",
        transaction_id="custom-analysis",
    )
    assert written["analysisPath"] == f"Research/Reviews/{KEY}.md"
    assert (vault / "Research" / "Reviews" / f"{KEY}.md").is_file()

    rebuilt = AnalysisIndexService(vault, config).rebuild(transaction_id="custom-analysis-index")
    assert rebuilt["indexPath"] == "Research/Reviews/catalog.md"
    assert (vault / "Research" / "Reviews" / "catalog.md").is_file()


def test_analysis_paths_cannot_overwrite_main_note_or_index(analysis_vault: tuple[Path, dict]) -> None:
    vault, config = analysis_vault
    config["analysis"]["folder"] = config["literature"]["root"]
    with pytest.raises(ConfigurationError, match="analysis.folder"):
        AnalysisService(vault, config)

    config = default_config()
    config["analysis"].update(folder="Research/Reviews", index=f"Research/Reviews/{KEY}.md")
    with pytest.raises(ValueError, match="Analysis index"):
        AnalysisService(vault, config).write(KEY, _sections(), transaction_id="path-conflict")


def test_verified_agent_inference_requires_original_evidence(analysis_vault: tuple[Path, dict]) -> None:
    vault, config = analysis_vault
    sections = {
        "mechanisms": [
            _claim(
                "The mechanism is an Agent inference.",
                claim_type="agent_inference",
                verification="verified",
            )
        ]
    }

    with pytest.raises(ValueError, match="require evidenceIds"):
        AnalysisService(vault, config).write(KEY, sections, transaction_id="unsupported-inference")


def _claim(
    content: str,
    *,
    claim_type: str = "agent_inference",
    verification: str = "unverified",
    evidence_ids: list[str] | None = None,
    asset_ids: list[str] | None = None,
) -> dict:
    return {
        "claimType": claim_type,
        "content": content,
        "evidenceIds": evidence_ids or [],
        "assetIds": asset_ids or [],
        "verificationStatus": verification,
    }


def _sections() -> dict:
    return {
        "research-methods": [
            _claim(
                "The authors used spectroscopy.",
                claim_type="source_fact",
                verification="verified",
                evidence_ids=[EVIDENCE_METHOD],
            )
        ],
        "findings": [
            _claim(
                "Hydrogen evolution increased under illumination.",
                claim_type="source_fact",
                verification="partial",
                evidence_ids=[EVIDENCE_RESULT],
                asset_ids=[ASSET_RELIABLE],
            )
        ],
        "mechanisms": [_claim("A charge-transfer mechanism remains an Agent inference.")],
    }


def _uncertainty(*, figure: str = "") -> dict:
    target = {"figure": figure} if figure else {"section": "Mechanism discussion"}
    return {
        "claim": "The morphology proves a charge-transfer mechanism.",
        "reason": "Only a candidate interpretation is available.",
        "verificationTarget": target,
        "status": "pending",
        "evidenceIds": [],
        "assetIds": [],
    }
