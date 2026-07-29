from __future__ import annotations

import json
from pathlib import Path

import pytest

from obsidian_vault_mcp.application.evidence_service import EvidenceService
from obsidian_vault_mcp.application.retrieval_service import RetrievalService
from obsidian_vault_mcp.config.defaults import default_config
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter


def _paper(vault: Path, key: str, *, title: str, abstract: str, tags: list[str], full_text: bool = True) -> None:
    note = vault / "Literature" / f"{key}.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    fields = {
        "title": title,
        "zoteroKey": key,
        "year": 2025,
        "journal": "Journal",
        "abstract": abstract,
        "tags": tags,
    }
    if full_text:
        fields["attachmentMinerULink"] = f"[[Literature/attachment/MinerU/{key}]]"
        mineru = vault / "Literature" / "attachment" / "MinerU" / f"{key}.md"
        mineru.parent.mkdir(parents=True, exist_ok=True)
        mineru.write_text("text", encoding="utf-8")
    note.write_text(compose_frontmatter(fields, f"# {title}\n"), encoding="utf-8")


def _evidence(vault: Path, key: str, chunks: list[dict]) -> list[dict]:
    source = vault / "Literature" / "attachment" / "MinerU" / f"{key}.md"
    blocks = ["# Results"]
    for index, chunk in enumerate(chunks, start=1):
        blocks.append(f"{chunk['text']} ^retrieval-{index}")
    source.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")
    EvidenceService(vault, default_config()).rebuild(key, transaction_id=f"evidence-{key}")
    return [
        chunk
        for chunk in EvidenceService(vault, default_config()).load_verified(key)["chunks"]
        if chunk["contentType"] != "heading"
    ]


def test_retrieve_ranks_metadata_and_original_evidence_with_honest_coverage(tmp_path: Path) -> None:
    _paper(
        tmp_path,
        "ABCD1234",
        title="Nickel cocatalyst on CdS",
        abstract="Photocatalytic hydrogen evolution with a Ni cocatalyst.",
        tags=["photocatalysis"],
    )
    _paper(
        tmp_path,
        "WXYZ5678",
        title="Unrelated adsorption study",
        abstract="Adsorption isotherms.",
        tags=["adsorption"],
        full_text=False,
    )
    evidence = _evidence(
        tmp_path,
        "ABCD1234",
        [
            {
                "evidenceId": "ABCD1234-results-a1",
                "text": "Ni cocatalyst increased photocatalytic hydrogen evolution under visible light.",
                "sectionPath": ["Results"],
                "contentType": "paragraph",
                "page": None,
                "sourceLink": "[[Literature/attachment/MinerU/ABCD1234#^ev-a1]]",
                "contentHash": "hash-a1",
                "sourceFingerprint": "fp-a1",
                "relatedAssetIds": ["IMG-ABCD1234-a1"],
            }
        ],
    )
    result = RetrievalService(tmp_path, default_config()).retrieve(
        "CdS nickel hydrogen evolution",
        query_variants=["Ni cocatalyst CdS"],
        record_coverage=False,
    )

    assert result["paperMatches"][0]["zoteroKey"] == "ABCD1234"
    assert result["snippets"][0]["evidenceId"] == evidence[0]["evidenceId"]
    assert result["snippets"][0]["text"].startswith("Ni cocatalyst")
    assert result["snippets"][0]["relatedAssetIds"] == []
    assert result["coverage"]["exhaustive"] is False
    assert any(item.get("kind") == "claim-boundary" for item in result["frontier"])
    assert "Ni cocatalyst CdS" not in result["snippets"][0]["text"]

    state_path = tmp_path / ".obsidian-vault-mcp" / "state" / "evidence" / "ABCD1234.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["chunks"][-1]["text"] = "forged evidence"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    rejected = RetrievalService(tmp_path, default_config()).retrieve("CdS nickel hydrogen evolution")
    assert rejected["snippets"] == []
    assert any(warning["code"] == "invalid-evidence-state" for warning in rejected["warnings"])


def test_retrieve_can_recall_a_paper_matched_only_by_verified_full_text(tmp_path: Path) -> None:
    _paper(
        tmp_path,
        "ABCD1234",
        title="Generic catalyst study",
        abstract="A general materials investigation.",
        tags=[],
    )
    evidence = _evidence(
        tmp_path,
        "ABCD1234",
        [{"text": "The exclusive provenance marker was observed under controlled conditions."}],
    )

    result = RetrievalService(tmp_path, default_config()).retrieve(
        "exclusive provenance marker",
        methods=["exact"],
        depth="evidence",
        record_coverage=False,
    )

    assert [paper["zoteroKey"] for paper in result["paperMatches"]] == ["ABCD1234"]
    assert result["paperMatches"][0]["matchedFields"] == ["evidence"]
    assert result["paperMatches"][0]["matchReason"] == ["exact:evidence"]
    assert result["snippets"][0]["evidenceId"] == evidence[0]["evidenceId"]
    assert result["coverage"]["fullTextScanned"] == 1
    assert result["coverage"]["exactMatchPapers"] == 1


def test_retrieve_supports_enumeration_scope_tags_and_missing_full_text(tmp_path: Path) -> None:
    _paper(tmp_path, "ABCD1234", title="Alpha", abstract="", tags=["keep"], full_text=False)
    _paper(tmp_path, "WXYZ5678", title="Beta", abstract="Summary", tags=["other"], full_text=False)
    service = RetrievalService(tmp_path, default_config())

    result = service.retrieve(
        "",
        intent="enumerate",
        depth="metadata",
        scope={"tags": ["keep"]},
        record_coverage=False,
    )
    assert [item["zoteroKey"] for item in result["paperMatches"]] == ["ABCD1234"]
    assert result["coverage"]["exhaustive"] is True
    assert result["coverage"]["metadataOnlyPapers"] == ["ABCD1234"]

    scoped = service.retrieve(
        "",
        intent="enumerate",
        depth="pool",
        scope={"zotero_keys": ["WXYZ5678"]},
        record_coverage=False,
    )
    assert scoped["paperMatches"][0]["availableEvidenceLevel"] == "abstract"

    state = tmp_path / ".obsidian-vault-mcp" / "state" / "items" / "ABCD1234.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps({"schemaVersion": 2, "zoteroKey": "ABCD1234", "collectionKeys": ["COLLECTION"]}),
        encoding="utf-8",
    )
    collection = service.retrieve(
        "",
        intent="enumerate",
        depth="metadata",
        scope={"collection_key": "COLLECTION"},
        record_coverage=False,
    )
    assert [item["zoteroKey"] for item in collection["paperMatches"]] == ["ABCD1234"]


def test_retrieve_reports_budgets_and_rejects_invalid_contract(tmp_path: Path) -> None:
    for index in range(3):
        _paper(tmp_path, f"KEY{index}", title=f"Query paper {index}", abstract="query", tags=[])
    service = RetrievalService(tmp_path, default_config())
    result = service.retrieve("query", max_candidate_papers=1, record_coverage=False)
    assert len(result["paperMatches"]) == 1
    assert result["coverage"]["candidateTruncated"] is True

    with pytest.raises(ValueError, match="max_candidate_papers"):
        service.retrieve("query", max_candidate_papers=0)
    with pytest.raises(ValueError, match="unsupported retrieval method"):
        service.retrieve("query", methods=["semantic"])
    with pytest.raises(ValueError, match="unknown retrieval scope"):
        service.retrieve("query", scope={"folder": "Literature"})


def test_retrieve_records_hidden_coverage_without_polluting_notes(tmp_path: Path) -> None:
    _paper(tmp_path, "ABCD1234", title="Alpha query", abstract="query abstract", tags=[])
    note = tmp_path / "Literature" / "ABCD1234.md"
    before = note.read_bytes()

    result = RetrievalService(tmp_path, default_config()).retrieve("query", record_coverage=True)

    assert result["warnings"] == []
    assert result["coverageLedger"][0]["status"] == "committed"
    assert result["coverageLedger"][0]["transactionId"]
    assert note.read_bytes() == before
    ledger = tmp_path / ".obsidian-vault-mcp" / "state" / "coverage" / "ABCD1234.json"
    assert ledger.is_file()


def test_retrieve_returns_coverage_dry_run_transaction_ids(tmp_path: Path) -> None:
    _paper(tmp_path, "ABCD1234", title="Alpha query", abstract="query abstract", tags=[])

    result = RetrievalService(tmp_path, default_config()).retrieve(
        "query",
        record_coverage=True,
        coverage_dry_run=True,
        coverage_transaction_id="retrieve-preview",
    )

    assert result["coverageLedger"][0]["status"] == "dry-run"
    assert result["coverageLedger"][0]["transactionId"] == "retrieve-preview-0001"
    assert not (tmp_path / ".obsidian-vault-mcp" / "state" / "coverage" / "ABCD1234.json").exists()
