from __future__ import annotations

import os
import re
from importlib import resources
from pathlib import Path

import pytest
import yaml

from obsidian_vault_mcp.application import skill_service as skill_service_module
from obsidian_vault_mcp.application.analysis_service import AnalysisService
from obsidian_vault_mcp.application.skill_service import (
    MANAGED_END,
    MANAGED_START,
    SKILL_NAMES,
    SKILL_RESOURCE_VERSION,
    SkillResourceService,
    extract_managed_block,
    upgrade_managed_skill,
)
from obsidian_vault_mcp.domain.frontmatter import compose_frontmatter, parse_frontmatter

EXPECTED_REFERENCES = {
    "paper-qa": (),
    "full-read": ("references/discipline-profiles.md", "references/output-contract.md"),
    "passage-qa": ("references/output-contract.md",),
    "figure-qa": ("references/figure-analysis.md",),
    "compare-papers": ("references/comparison-dimensions.md",),
    "literature-review": ("references/discipline-profiles.md", "references/output-contract.md"),
    "concept-learning": ("references/concept-model.md",),
}
FORBIDDEN_SKILL_TEXT = (
    "Evidence ID",
    "Coverage Ledger",
    "Uncertainty",
    "evidenceId",
    "assetId",
    "coverageLedger",
    "verificationStatus",
    "evidenceStatus",
)
ALLOWED_TOOL_NAMES = {
    "literature_analysis_get",
    "literature_analysis_write",
    "literature_paper_read",
    "literature_rebuild_analysis_base",
    "literature_retrieve",
}
PERSISTED_ANALYSIS_CONTRACTS = {
    "full-read": "references/output-contract.md",
    "passage-qa": "references/output-contract.md",
    "figure-qa": "references/figure-analysis.md",
    "literature-review": "references/output-contract.md",
    "concept-learning": "references/concept-model.md",
}
CLIENT_COMMON_FIELDS = {
    "analysisType",
    "analysisProfile",
    "secondaryProfiles",
    "title",
    "status",
    "analysisFocus",
    "primarySourceKey",
    "primarySource",
    "sourceKeys",
    "sourceCount",
    "summary",
    "skillName",
    "skillVersion",
    "tags",
}
SERVER_MANAGED_FIELDS = {
    "analysisSchemaVersion",
    "analysisId",
    "sourceFingerprint",
    "createdAt",
    "updatedAt",
}


def test_all_canonical_skills_have_minimal_frontmatter_and_one_managed_block() -> None:
    service = SkillResourceService()
    listed = service.list()

    assert tuple(SKILL_NAMES) == tuple(EXPECTED_REFERENCES)
    assert [item["name"] for item in listed] == list(SKILL_NAMES)
    assert all(item["version"] == SKILL_RESOURCE_VERSION for item in listed)
    assert all(len(item["managedHash"]) == 64 for item in listed)
    for name in SKILL_NAMES:
        text = service.read(name)
        document = parse_frontmatter(text)
        assert set(document.fields) == {"name", "description"}
        assert document.fields["name"] == name
        assert isinstance(document.fields["description"], str) and document.fields["description"].strip()
        assert text.count(MANAGED_START) == text.count(MANAGED_END) == 1
        assert "## User Customizations" in text


def test_skills_and_recursive_references_are_loaded_from_the_single_plugin_tree() -> None:
    service = SkillResourceService()
    root = resources.files("obsidian_vault_mcp.resources.agent_marketplace")
    for name in SKILL_NAMES:
        files = service.files(name)
        assert tuple(files) == ("SKILL.md", *EXPECTED_REFERENCES[name])
        for relative_path, content in files.items():
            packaged = root.joinpath("plugins/obsidian-literature/skills", name, *relative_path.split("/"))
            assert packaged.is_file()
            assert packaged.read_text(encoding="utf-8") == content


def test_skills_link_directly_to_their_references_and_use_only_the_simplified_tools() -> None:
    service = SkillResourceService()
    for name in SKILL_NAMES:
        files = service.files(name)
        skill_text = files["SKILL.md"]
        for reference in EXPECTED_REFERENCES[name]:
            assert f"]({reference})" in skill_text
        combined = "\n".join(files.values())
        assert not [term for term in FORBIDDEN_SKILL_TEXT if term in combined]
        mentioned_tools = set(re.findall(r"`(literature_[a-z_]+)`", combined))
        assert mentioned_tools <= ALLOWED_TOOL_NAMES


def test_reference_contracts_cover_the_required_analysis_boundaries() -> None:
    service = SkillResourceService()

    full_read = service.files("full-read")
    assert "analysisType: full_read" in full_read["references/output-contract.md"]
    assert "natural-language" in full_read["references/discipline-profiles.md"]

    passage = service.files("passage-qa")["references/output-contract.md"]
    assert "locatorQuality" in passage
    assert "cannot support" in passage

    figure = service.files("figure-qa")["references/figure-analysis.md"]
    assert "imageExists" in figure
    assert "caption_context" in figure

    comparison = service.files("compare-papers")["references/comparison-dimensions.md"]
    assert "not_comparable" in comparison

    review = service.files("literature-review")
    assert "reviewMode" in review["references/output-contract.md"]
    assert "systematic" in review["references/output-contract.md"]

    concept = service.files("concept-learning")["references/concept-model.md"]
    assert "Boundary conditions and counterexamples" in concept


def test_persisted_skill_examples_are_complete_runtime_valid_write_payloads(
    tmp_path: Path,
) -> None:
    for key in ("ABCD1234", "EFGH5678"):
        source = tmp_path / "Literature" / f"{key}.md"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_text(
            compose_frontmatter(
                {
                    "title": f"Paper {key}",
                    "abstract": f"Abstract {key}",
                    "year": 2026,
                    "doi": f"10.1000/{key.lower()}",
                    "zoteroKey": key,
                },
                "# Source\n",
            ),
            encoding="utf-8",
        )
    image = tmp_path / "Literature/attachment/MinerU/image/ABCD1234/ABCD1234-fig02.jpg"
    image.parent.mkdir(parents=True)
    image.write_bytes(b"real-image")

    resources_service = SkillResourceService()
    analysis_service = AnalysisService(
        tmp_path,
        now=lambda: "2026-07-30T00:00:00+00:00",
    )
    examples: dict[str, dict[str, object]] = {}
    pattern = re.compile(
        r"<!-- ovm:analysis-fields-example:start -->\s*"
        r"```yaml\n(?P<yaml>.*?)\n```\s*"
        r"<!-- ovm:analysis-fields-example:end -->",
        re.DOTALL,
    )

    for skill_name, reference_path in PERSISTED_ANALYSIS_CONTRACTS.items():
        contract = resources_service.files(skill_name)[reference_path]
        match = pattern.search(contract)
        assert match is not None, skill_name
        fields = yaml.safe_load(match.group("yaml"))
        assert isinstance(fields, dict)
        assert CLIENT_COMMON_FIELDS <= set(fields)
        assert not SERVER_MANAGED_FIELDS.intersection(fields)
        assert fields["skillVersion"] == SKILL_RESOURCE_VERSION
        assert "Do not include managed-block markers" in contract
        if fields["analysisType"] in {"full_read", "passage_qa", "figure_qa"}:
            assert "literature_paper_read.metadata.notePath" in contract

        result = analysis_service.write(
            fields,
            "# Runtime-valid managed content\n",
            dry_run=True,
            transaction_id=f"skill-contract-{skill_name}",
        )
        assert result["status"] == "dry-run"
        assert result["analysisType"] == fields["analysisType"]
        examples[skill_name] = fields

    compare_skill = resources_service.read("compare-papers")
    assert "](../literature-review/references/output-contract.md)" in compare_skill
    comparison_fields = dict(examples["literature-review"])
    comparison_fields["skillName"] = "compare-papers"
    comparison = analysis_service.write(
        comparison_fields,
        "# Runtime-valid comparative review\n",
        dry_run=True,
        transaction_id="skill-contract-compare-papers",
    )
    assert comparison["status"] == "dry-run"
    assert comparison["analysisType"] == "literature_review"


def test_managed_upgrade_preserves_text_before_and_after_the_block() -> None:
    existing = (
        "---\nname: local\nversion: 0.9.0\n---\n\nLocal preface\n"
        f"{MANAGED_START}\nold official\n{MANAGED_END}\n\n"
        "## User Customizations\n\nKeep this exactly.\n"
    )
    official = SkillResourceService().read("full-read")
    current_hash = extract_managed_block(existing).sha256

    result = upgrade_managed_skill(existing, official, expected_existing_hash=current_hash)

    assert result["ok"] is True
    assert result["changed"] is True
    assert result["version"] == SKILL_RESOURCE_VERSION
    assert result["content"].startswith("---\nname: local")
    assert result["content"].endswith("## User Customizations\n\nKeep this exactly.\n")
    assert "old official" not in result["content"]


def test_managed_upgrade_detects_user_edits_and_legacy_markers() -> None:
    official = SkillResourceService().read("compare-papers")
    changed = upgrade_managed_skill(official.replace("Compare papers", "User-edited block"), official, expected_existing_hash="0" * 64)
    assert changed["ok"] is False
    assert changed["warnings"][0]["code"] == "managed-block-modified"

    legacy = upgrade_managed_skill("# old skill\n", official)
    assert legacy["ok"] is False
    assert legacy["content"] == "# old skill\n"
    assert legacy["warnings"][0]["code"] == "legacy-skill-format"


def test_managed_markers_must_be_unique_and_ordered() -> None:
    for text in (
        "missing",
        f"{MANAGED_END}\n{MANAGED_START}",
        f"{MANAGED_START}{MANAGED_START}{MANAGED_END}",
    ):
        try:
            extract_managed_block(text)
        except ValueError:
            pass
        else:  # pragma: no cover - assertion form keeps compatibility with unittest-free tests
            raise AssertionError("invalid markers were accepted")


@pytest.mark.skipif(os.name != "nt", reason="Windows extended paths are platform-specific")
def test_recursive_skill_resources_support_deep_windows_tool_installs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    regular_root = tmp_path.joinpath(
        "deep-resource-root-" + ("x" * 80),
        "nested-" + ("y" * 80),
    )
    skill_root = skill_service_module._extended_length_path(
        regular_root
        / "plugins"
        / "obsidian-literature"
        / "skills"
        / "literature-review"
    )
    references = skill_root / "references"
    references.mkdir(parents=True)
    (skill_root / "SKILL.md").write_text("skill\n", encoding="utf-8")
    (references / "output-contract.md").write_text("reference\n", encoding="utf-8")
    assert len(str(regular_root / "plugins" / "obsidian-literature" / "skills" / "literature-review" / "references")) > 260

    monkeypatch.setattr(
        skill_service_module.resources,
        "files",
        lambda _package: regular_root,
    )

    assert SkillResourceService().files("literature-review") == {
        "SKILL.md": "skill\n",
        "references/output-contract.md": "reference\n",
    }
