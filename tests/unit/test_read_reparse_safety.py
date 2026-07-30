from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from obsidian_vault_mcp.application.analysis_service import AnalysisService
from obsidian_vault_mcp.application.paper_read_service import PaperReadService
from obsidian_vault_mcp.application.retrieval_service import RetrievalService
from obsidian_vault_mcp.application.verify_service import VerifyService
from obsidian_vault_mcp.config.defaults import default_config
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter


def _create_link(link: Path, target: Path, *, directory: bool) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        command = ["cmd", "/c", "mklink"]
        if directory:
            command.append("/J")
        result = subprocess.run(
            [*command, str(link), str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            pytest.skip(f"could not create a Windows link: {result.stderr or result.stdout}")
        return
    link.symlink_to(target, target_is_directory=directory)


def _remove_link(link: Path, *, directory: bool) -> None:
    if not os.path.lexists(link):
        return
    if directory and os.name == "nt":
        os.rmdir(link)
    else:
        link.unlink()


def test_paper_read_does_not_follow_mineru_directory_junction(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = vault / "Literature" / "ABCD1234.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        compose_frontmatter(
            {"title": "Safe metadata", "zoteroKey": "ABCD1234"},
            "# Safe metadata\n",
        ),
        encoding="utf-8",
    )
    outside = vault / "private-mineru"
    outside.mkdir()
    (outside / "ABCD1234.md").write_text(
        "# OUTSIDE-SENTINEL\n\nThis content must never be read.\n",
        encoding="utf-8",
    )
    linked = vault / "Literature" / "attachment" / "MinerU"
    _create_link(linked, outside, directory=True)
    try:
        result = PaperReadService(vault, default_config()).read("ABCD1234", mode="full")

        serialized = json.dumps(result, ensure_ascii=False)
        assert "OUTSIDE-SENTINEL" not in serialized
        assert result["passages"] == []
        assert "mineru" in result["missing"]
        assert any(warning["code"] == "unsafe-vault-path" for warning in result["warnings"])
    finally:
        _remove_link(linked, directory=True)


def test_retrieval_does_not_follow_mineru_directory_junction(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = vault / "Literature" / "ABCD1234.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        compose_frontmatter(
            {"title": "Safe metadata", "zoteroKey": "ABCD1234"},
            "# Safe metadata\n",
        ),
        encoding="utf-8",
    )
    outside = vault / ".private-mineru"
    outside.mkdir()
    (outside / "ABCD1234.md").write_text(
        "# OUTSIDE-SENTINEL\n\nThis content must never be read.\n",
        encoding="utf-8",
    )
    linked = vault / "Literature" / "attachment" / "MinerU"
    _create_link(linked, outside, directory=True)
    try:
        result = RetrievalService(vault, default_config()).retrieve(
            "",
            intent="enumerate",
            depth="metadata",
        )

        serialized = json.dumps(result, ensure_ascii=False)
        assert "OUTSIDE-SENTINEL" not in serialized
        assert result["paperMatches"][0]["fullTextAvailable"] is False
        assert any(warning["code"] == "unsafe-vault-path" for warning in result["warnings"])
    finally:
        _remove_link(linked, directory=True)


def test_retrieval_does_not_follow_item_state_junction(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    note = vault / "Literature" / "ABCD1234.md"
    note.parent.mkdir(parents=True)
    note.write_text(
        compose_frontmatter(
            {"title": "Safe metadata", "zoteroKey": "ABCD1234"},
            "# Safe metadata\n",
        ),
        encoding="utf-8",
    )
    outside = vault / ".private-state"
    outside.mkdir()
    (outside / "ABCD1234.json").write_text(
        json.dumps(
            {
                "zoteroKey": "ABCD1234",
                "collectionKeys": ["OUTSIDE-SENTINEL"],
            }
        ),
        encoding="utf-8",
    )
    linked = vault / ".obsidian-vault-mcp" / "state" / "items"
    _create_link(linked, outside, directory=True)
    try:
        result = RetrievalService(vault, default_config()).retrieve(
            "",
            intent="enumerate",
            depth="metadata",
        )

        serialized = json.dumps(result, ensure_ascii=False)
        assert "OUTSIDE-SENTINEL" not in serialized
        assert [paper["zoteroKey"] for paper in result["paperMatches"]] == ["ABCD1234"]
        assert any(warning["code"] == "unsafe-vault-path" for warning in result["warnings"])
    finally:
        _remove_link(linked, directory=True)


def test_analysis_scan_skips_linked_markdown_candidate(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    outside = vault / "private-analysis"
    outside.mkdir(parents=True)
    (outside / "outside-analysis.md").write_text(
        compose_frontmatter(
            {
                "analysisId": "outside-analysis",
                "analysisType": "full_read",
                "sourceKeys": [],
            },
            "OUTSIDE-SENTINEL\n",
        ),
        encoding="utf-8",
    )
    linked = vault / "Literature" / "Analysis"
    _create_link(linked, outside, directory=True)
    try:
        result = AnalysisService(vault, default_config()).get()

        assert result["count"] == 0
        assert "OUTSIDE-SENTINEL" not in json.dumps(result, ensure_ascii=False)
        assert any(warning["code"] == "unsafe-vault-path" for warning in result["warnings"])
    finally:
        _remove_link(linked, directory=True)


def test_analysis_source_fingerprint_does_not_follow_junction(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    analysis = vault / "Literature" / "Analysis" / "full-reads" / "safe.md"
    analysis.parent.mkdir(parents=True)
    analysis.write_text(
        compose_frontmatter(
            {
                "analysisId": "safe-analysis",
                "analysisType": "full_read",
                "sourceKeys": ["ABCD1234"],
                "sourceFingerprint": "0" * 64,
                "status": "ready",
            },
            "Safe Analysis body.\n",
        ),
        encoding="utf-8",
    )
    outside = vault / ".private-sources"
    outside.mkdir()
    (outside / "ABCD1234.md").write_text(
        compose_frontmatter(
            {"title": "OUTSIDE-SENTINEL", "zoteroKey": "ABCD1234"},
            "This content must never be read.\n",
        ),
        encoding="utf-8",
    )
    linked = vault / "Sources"
    _create_link(linked, outside, directory=True)
    config = default_config()
    config["literature"]["root"] = "Sources"
    try:
        result = AnalysisService(vault, config).get()

        serialized = json.dumps(result, ensure_ascii=False)
        assert "OUTSIDE-SENTINEL" not in serialized
        assert result["analyses"][0]["effectiveStatus"] == "needs_update"
        assert "unsafe source note path" in result["analyses"][0]["sourceError"]
        assert any(warning["code"] == "unsafe-vault-path" for warning in result["warnings"])
    finally:
        _remove_link(linked, directory=True)


def test_verify_reports_link_without_reading_outside_visible_file(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    outside = vault / ".private-visible"
    outside.mkdir(parents=True)
    (outside / "outside-visible.md").write_text(
        "OUTSIDE-SENTINEL\nC:\\Users\\outside\\secret.md\n",
        encoding="utf-8",
    )
    linked = vault / "Literature"
    _create_link(linked, outside, directory=True)
    try:
        result = VerifyService(vault, default_config()).verify()

        serialized = json.dumps(result, ensure_ascii=False)
        assert "OUTSIDE-SENTINEL" not in serialized
        assert "C:\\Users\\outside" not in serialized
        assert result["counts"]["byCode"]["unsafe-vault-path"] == 1
        assert "windows-absolute-path" not in result["counts"]["byCode"]
    finally:
        _remove_link(linked, directory=True)


def test_verify_does_not_enumerate_mineru_image_junction(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    mineru = vault / "Literature" / "attachment" / "MinerU" / "ABCD1234.md"
    mineru.parent.mkdir(parents=True)
    mineru.write_text(
        compose_frontmatter(
            {"title": "Paper", "zoteroKey": "ABCD1234"},
            "![figure](image/ABCD1234/ABCD1234-fig01.png)\n",
        ),
        encoding="utf-8",
    )
    outside = vault / ".private-images"
    outside.mkdir()
    (outside / "ABCD1234-fig01.png").write_bytes(b"referenced")
    (outside / "OUTSIDE-SENTINEL.png").write_bytes(b"private")
    linked = mineru.parent / "image" / "ABCD1234"
    _create_link(linked, outside, directory=True)
    try:
        result = VerifyService(vault, default_config()).verify()

        serialized = json.dumps(result, ensure_ascii=False)
        assert "OUTSIDE-SENTINEL" not in serialized
        assert result["orphanImages"] == []
        assert result["affectedZoteroKeys"] == ["ABCD1234"]
        assert result["counts"]["byCode"]["unsafe-vault-path"] >= 1
    finally:
        _remove_link(linked, directory=True)
