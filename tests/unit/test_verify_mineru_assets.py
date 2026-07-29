from __future__ import annotations

import hashlib
import json
from pathlib import Path

from obsidian_vault_mcp.application.coverage_service import CoverageService
from obsidian_vault_mcp.application.evidence_service import EvidenceService
from obsidian_vault_mcp.application.verify_service import VerifyService
from obsidian_vault_mcp.config.defaults import default_config
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_asset_vault(vault: Path) -> dict[str, Path | dict]:
    candidate_id = f"IMG-ABCD1234-{_sha(b'candidate')[:12]}"
    note = vault / "Literature" / "ABCD1234.md"
    pdf = vault / "Literature" / "attachment" / "ABCD1234.pdf"
    mineru = vault / "Literature" / "attachment" / "MinerU" / "ABCD1234.md"
    image = vault / "Literature" / "attachment" / "MinerU" / "image" / "ABCD1234-fig01.png"
    candidate = (
        vault
        / ".obsidian-vault-mcp"
        / "cache"
        / "mineru-assets"
        / "ABCD1234"
        / "assets"
        / f"{candidate_id}.webp"
    )
    manifest_path = candidate.parent.parent / "manifest.json"
    note.parent.mkdir(parents=True)
    pdf.parent.mkdir(parents=True)
    mineru.parent.mkdir(parents=True)
    image.parent.mkdir(parents=True)
    candidate.parent.mkdir(parents=True)
    pdf.write_bytes(b"PDF")
    image.write_bytes(b"image")
    candidate.write_bytes(b"candidate")
    mineru_text = compose_frontmatter(
        {"title": "Paper", "zoteroKey": "ABCD1234", "sourcePdf": "../ABCD1234.pdf"},
        "# Paper\n\n![Figure](image/ABCD1234-fig01.png)\n",
    )
    mineru.write_text(mineru_text, encoding="utf-8")
    note.write_text(
        compose_frontmatter(
            {
                "title": "Paper",
                "itemType": "journalArticle",
                "zoteroKey": "ABCD1234",
                "attachmentPdfLink": "[[Literature/attachment/ABCD1234.pdf]]",
                "attachmentMinerULink": "[[Literature/attachment/MinerU/ABCD1234]]",
            },
            "# Paper\n",
        ),
        encoding="utf-8",
    )
    manifest = {
        "schemaVersion": 1,
        "zoteroKey": "ABCD1234",
        "sourceMarkdown": "Literature/attachment/MinerU/ABCD1234.md",
        "sourceMarkdownSha256": _sha(mineru.read_bytes()),
        "generatedAt": "2026-07-29T00:00:00Z",
        "assets": [
            {
                "assetId": f"IMG-ABCD1234-{_sha(b'image')[:12]}",
                "zoteroKey": "ABCD1234",
                "sourceRelativePath": "images/raw.png",
                "sourceRelativePaths": ["images/raw.png"],
                "status": "referenced",
                "extension": "png",
                "sizeBytes": 5,
                "sha256": _sha(b"image"),
                "normalizedPath": "Literature/attachment/MinerU/image/ABCD1234-fig01.png",
                "cachePath": None,
                "references": [{"syntax": "markdown", "alt": "Figure", "sourceOffset": 0, "sourceRelativePath": "images/raw.png"}],
                "visualStatus": "referenced",
            },
            {
                "assetId": candidate_id,
                "zoteroKey": "ABCD1234",
                "sourceRelativePath": "images/candidate.webp",
                "sourceRelativePaths": ["images/candidate.webp"],
                "status": "unlinked_candidate",
                "extension": "webp",
                "sizeBytes": 9,
                "sha256": _sha(b"candidate"),
                "normalizedPath": None,
                "cachePath": f".obsidian-vault-mcp/cache/mineru-assets/ABCD1234/assets/{candidate_id}.webp",
                "references": [],
                "visualStatus": "mineru_candidate",
            },
        ],
        "counts": {"total": 2, "referenced": 1, "unlinkedCandidates": 1, "invalid": 0},
        "warnings": [],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    EvidenceService(vault, default_config()).rebuild(
        "ABCD1234",
        transaction_id="fixture-evidence",
        generated_at="2026-07-29T00:00:00Z",
    )
    return {
        "note": note,
        "mineru": mineru,
        "image": image,
        "candidate": candidate,
        "manifestPath": manifest_path,
        "manifest": manifest,
    }


def _codes(vault: Path) -> list[str]:
    return [issue["code"] for issue in VerifyService(vault, default_config()).verify()["issues"]]


def test_verify_accepts_consistent_manifest_and_unlinked_candidate(tmp_path: Path) -> None:
    _write_asset_vault(tmp_path)
    result = VerifyService(tmp_path, default_config()).verify()
    assert result["ok"]
    assert result["issues"] == []


def test_verify_reports_broken_stale_missing_candidate_and_orphan(tmp_path: Path) -> None:
    paths = _write_asset_vault(tmp_path)
    Path(paths["image"]).write_bytes(b"changed")
    Path(paths["candidate"]).unlink()
    orphan = Path(paths["image"]).parent / "orphan.png"
    orphan.write_bytes(b"orphan")

    codes = _codes(tmp_path)

    assert "stale-image-hash" in codes
    assert "missing-candidate-cache" in codes
    assert "orphan-mineru-image" in codes
    assert "broken-mineru-image-link" not in codes


def test_verify_reports_missing_invalid_duplicate_and_unsafe_manifests(tmp_path: Path) -> None:
    paths = _write_asset_vault(tmp_path)
    manifest_path = Path(paths["manifestPath"])
    manifest_path.unlink()
    assert "missing-image-manifest" in _codes(tmp_path)

    manifest = dict(paths["manifest"])
    manifest["assets"] = [dict(asset) for asset in manifest["assets"]]
    manifest["assets"][0]["normalizedPath"] = "../escape.png"
    manifest["assets"].append(dict(manifest["assets"][1]))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    codes = _codes(tmp_path)
    assert "invalid-asset-path" in codes
    assert "duplicate-mineru-image" in codes

    manifest_path.write_text("{not json", encoding="utf-8")
    assert "invalid-image-manifest" in _codes(tmp_path)


def test_verify_reports_inline_path_errors_missing_entry_and_unsupported_html(tmp_path: Path) -> None:
    paths = _write_asset_vault(tmp_path)
    mineru = Path(paths["mineru"])
    text = mineru.read_text(encoding="utf-8")
    text += "\n![missing](image/missing.png)\n![escape](../../../../outside.png)\n<img src=\"image/html.png\">\n"
    mineru.write_text(text, encoding="utf-8")
    manifest = dict(paths["manifest"])
    manifest["sourceMarkdownSha256"] = _sha(mineru.read_bytes())
    Path(paths["manifestPath"]).write_text(json.dumps(manifest), encoding="utf-8")

    codes = _codes(tmp_path)

    assert "broken-mineru-image-link" in codes
    assert "invalid-mineru-image-link" in codes
    assert "missing-image-manifest-entry" in codes
    assert "unsupported-image-syntax" in codes


def test_verify_reports_duplicate_evidence_broken_source_and_stale_coverage(tmp_path: Path) -> None:
    _write_asset_vault(tmp_path)
    state_path = tmp_path / ".obsidian-vault-mcp" / "state" / "evidence" / "ABCD1234.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    paragraph = next(chunk for chunk in state["chunks"] if chunk["contentType"] == "other")
    CoverageService(tmp_path, default_config()).record(
        "ABCD1234",
        source_kind="evidence_index",
        topic="figure",
        granularity="passage",
        coverage="targeted",
        confidence="high",
        content_hash=_sha(json.dumps({paragraph["evidenceId"]: paragraph["contentHash"]}, sort_keys=True, separators=(",", ":")).encode()),
        tool_name="literature_paper_read",
        evidence_refs=[paragraph["evidenceId"]],
        valid_evidence_ids={paragraph["evidenceId"]},
        now="2026-07-29T00:00:00Z",
    )

    state["chunks"].append(dict(paragraph))
    state_path.write_text(json.dumps(state), encoding="utf-8")
    codes = _codes(tmp_path)
    assert "duplicate-evidence-id" in codes

    state["chunks"] = state["chunks"][:-1]
    state["sourcePath"] = "Literature/attachment/MinerU/missing.md"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    codes = _codes(tmp_path)
    assert "broken-evidence-source-link" in codes

    state["sourcePath"] = "Literature/attachment/MinerU/ABCD1234.md"
    state["chunks"] = []
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assert "stale-coverage-record" in _codes(tmp_path)


def test_verify_reports_a_missing_physical_evidence_block_anchor(tmp_path: Path) -> None:
    paths = _write_asset_vault(tmp_path)
    state_path = tmp_path / ".obsidian-vault-mcp" / "state" / "evidence" / "ABCD1234.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    target = state["chunks"][0]
    mineru = Path(paths["mineru"])
    mineru.write_text(
        mineru.read_text(encoding="utf-8").replace(f"^{target['blockId']}", "", 1),
        encoding="utf-8",
    )
    state["sourceMarkdownSha256"] = _sha(mineru.read_bytes())
    state_path.write_text(json.dumps(state), encoding="utf-8")

    issues = VerifyService(tmp_path, default_config()).verify()["issues"]

    assert any(
        issue["code"] == "broken-evidence-source-link" and issue.get("blockId") == target["blockId"]
        for issue in issues
    )


def test_verify_rebuilds_evidence_and_propagates_source_staleness_to_coverage(tmp_path: Path) -> None:
    paths = _write_asset_vault(tmp_path)
    state_path = tmp_path / ".obsidian-vault-mcp" / "state" / "evidence" / "ABCD1234.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    paragraph = next(chunk for chunk in state["chunks"] if chunk["contentType"] == "other")
    CoverageService(tmp_path, default_config()).record(
        "ABCD1234",
        source_kind="evidence_index",
        topic="figure",
        granularity="passage",
        coverage="targeted",
        confidence="high",
        content_hash=_sha(
            json.dumps(
                {paragraph["evidenceId"]: paragraph["contentHash"]},
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ),
        tool_name="literature_paper_read",
        evidence_refs=[paragraph["evidenceId"]],
        valid_evidence_ids={paragraph["evidenceId"]},
        now="2026-07-29T00:00:00Z",
    )

    state["chunks"][1]["text"] = "tampered derived evidence"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    assert "stale-evidence-index" in _codes(tmp_path)

    state["chunks"][1] = paragraph
    state_path.write_text(json.dumps(state), encoding="utf-8")
    mineru = Path(paths["mineru"])
    mineru.write_text(mineru.read_text(encoding="utf-8") + "\nSource changed.\n", encoding="utf-8")
    codes = _codes(tmp_path)
    assert "stale-evidence-index" in codes
    assert "stale-coverage-record" in codes
