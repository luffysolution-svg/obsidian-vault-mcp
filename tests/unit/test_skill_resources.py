from __future__ import annotations

from importlib import resources

from obsidian_vault_mcp.application.skill_service import (
    MANAGED_END,
    MANAGED_START,
    SKILL_NAMES,
    SkillResourceService,
    extract_managed_block,
    upgrade_managed_skill,
)


def test_all_canonical_skills_have_one_versioned_managed_block() -> None:
    service = SkillResourceService()
    listed = service.list()
    assert [item["name"] for item in listed] == list(SKILL_NAMES)
    assert all(item["version"] == "1.0.0" for item in listed)
    assert all(len(item["managedHash"]) == 64 for item in listed)
    for name in SKILL_NAMES:
        text = service.read(name)
        assert text.count(MANAGED_START) == text.count(MANAGED_END) == 1
        assert "## User Customizations" in text


def test_skills_are_loaded_from_the_single_plugin_resource_tree() -> None:
    root = resources.files("obsidian_vault_mcp.resources.agent_marketplace")
    for name in SKILL_NAMES:
        packaged = root.joinpath("plugins/obsidian-literature/skills", name, "SKILL.md")
        assert packaged.is_file()
        assert packaged.read_text(encoding="utf-8") == SkillResourceService().read(name)


def test_reading_skills_explicitly_record_coverage() -> None:
    service = SkillResourceService()
    for name in (
        "analyze-figures",
        "compare-papers",
        "evidence-based-qa",
        "literature-review",
        "structured-paper-note",
        "verify-paper-claims",
    ):
        text = service.read(name)
        assert "record_coverage=true" in text
        assert "Coverage Ledger" in text


def test_managed_upgrade_preserves_text_before_and_after_the_block() -> None:
    existing = (
        "---\nname: local\nversion: 0.9.0\n---\n\nLocal preface\n"
        f"{MANAGED_START}\nold official\n{MANAGED_END}\n\n"
        "## User Customizations\n\nKeep this exactly.\n"
    )
    official = SkillResourceService().read("evidence-based-qa")
    current_hash = extract_managed_block(existing).sha256

    result = upgrade_managed_skill(existing, official, expected_existing_hash=current_hash)

    assert result["ok"] is True
    assert result["changed"] is True
    assert result["version"] == "1.0.0"
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
