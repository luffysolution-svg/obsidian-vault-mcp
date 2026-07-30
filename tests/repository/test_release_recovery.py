from __future__ import annotations

import copy
import gzip
import hashlib
import io
import json
import tarfile
from collections.abc import Mapping
from pathlib import Path

import pytest

from scripts import release_guard

ROOT = Path(__file__).resolve().parents[2]
COMMIT_SHA = "1" * 40
TAG_OBJECT_SHA = "2" * 40


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _fetch_annotated_tag(
    url: str,
    headers: Mapping[str, str] | None,
) -> dict[str, object]:
    assert headers is not None and headers["Authorization"] in {
        "Bearer test-token",
        "Bearer workflow-token",
    }
    if url.endswith("/git/ref/tags/v3.0.0"):
        return {
            "ref": "refs/tags/v3.0.0",
            "object": {"type": "tag", "sha": TAG_OBJECT_SHA},
        }
    if url.endswith(f"/git/tags/{TAG_OBJECT_SHA}"):
        return {"object": {"type": "commit", "sha": COMMIT_SHA}}
    raise AssertionError(url)


def _release_directory(tmp_path: Path) -> dict[str, bytes]:
    files = {
        "zotero_obsidian_mcp-3.0.0-py3-none-any.whl": b"wheel",
        "zotero_obsidian_mcp-3.0.0.tar.gz": b"sdist",
        "obsidian-vault-mcp-3.0.0-plugins.zip": b"plugins",
    }
    for name, content in files.items():
        (tmp_path / name).write_bytes(content)
    manifest = "".join(f"{_digest(content)}  {name}\n" for name, content in sorted(files.items()))
    (tmp_path / "SHA256SUMS").write_text(manifest, encoding="utf-8")
    return files


def _write_sdist(path: Path, *, tar_mtime: int, gzip_mtime: int) -> None:
    with path.open("wb") as stream:
        with gzip.GzipFile(filename="", fileobj=stream, mode="wb", mtime=gzip_mtime) as compressed:
            with tarfile.open(fileobj=compressed, mode="w") as archive:
                root = tarfile.TarInfo("package-3.0.0")
                root.type = tarfile.DIRTYPE
                root.mtime = tar_mtime
                archive.addfile(root)
                content = b"metadata"
                metadata = tarfile.TarInfo("package-3.0.0/PKG-INFO")
                metadata.size = len(content)
                metadata.mtime = tar_mtime
                archive.addfile(metadata, fileobj=io.BytesIO(content))


def test_sdist_normalization_makes_rebuilds_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "first.tar.gz"
    second = tmp_path / "second.tar.gz"
    _write_sdist(first, tar_mtime=100, gzip_mtime=200)
    _write_sdist(second, tar_mtime=300, gzip_mtime=400)

    release_guard.normalize_sdist(first, 42)
    release_guard.normalize_sdist(second, 42)

    assert first.read_bytes() == second.read_bytes()
    with tarfile.open(first, "r:gz") as archive:
        assert {member.mtime for member in archive.getmembers()} == {42}


def test_pypi_guard_requires_exact_remote_filenames_and_sha256(tmp_path: Path) -> None:
    wheel = b"wheel"
    sdist = b"sdist"
    local = {
        "zotero_obsidian_mcp-3.0.0-py3-none-any.whl": _digest(wheel),
        "zotero_obsidian_mcp-3.0.0.tar.gz": _digest(sdist),
    }
    payload = {
        "info": {"name": "zotero-obsidian-mcp", "version": "3.0.0"},
        "urls": [
            {"filename": filename, "digests": {"sha256": digest}}
            for filename, digest in local.items()
        ],
    }

    assert release_guard.assert_pypi_release(
        payload,
        project="zotero-obsidian-mcp",
        version="3.0.0",
        local_artifacts=local,
    ) == ()

    partial = copy.deepcopy(payload)
    partial["urls"] = partial["urls"][:1]
    assert release_guard.assert_pypi_release(
        partial,
        project="zotero-obsidian-mcp",
        version="3.0.0",
        local_artifacts=local,
    ) == (next(filename for filename in local if filename not in {partial["urls"][0]["filename"]}),)

    conflicting = copy.deepcopy(payload)
    conflicting["urls"][0]["digests"]["sha256"] = "0" * 64
    with pytest.raises(release_guard.ReleaseConflict, match="different files or SHA256"):
        release_guard.assert_pypi_release(
            conflicting,
            project="zotero-obsidian-mcp",
            version="3.0.0",
            local_artifacts=local,
        )

    extra = copy.deepcopy(payload)
    extra["urls"].append({"filename": "unexpected.whl", "digests": {"sha256": "1" * 64}})
    with pytest.raises(release_guard.ReleaseConflict, match="different files or SHA256"):
        release_guard.assert_pypi_release(
            extra,
            project="zotero-obsidian-mcp",
            version="3.0.0",
            local_artifacts=local,
        )


@pytest.mark.parametrize("published_suffix", [".whl", ".tar.gz"])
def test_pypi_guard_resumes_only_the_exact_missing_artifact(
    tmp_path: Path,
    published_suffix: str,
) -> None:
    files = _release_directory(tmp_path)
    wheel_name = next(name for name in files if name.endswith(".whl"))
    sdist_name = next(name for name in files if name.endswith(".tar.gz"))
    published_name = wheel_name if published_suffix == ".whl" else sdist_name
    missing_name = sdist_name if published_suffix == ".whl" else wheel_name
    server_version = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))["version"]
    payload = {
        "info": {"name": "zotero-obsidian-mcp", "version": server_version},
        "urls": [
            {
                "filename": published_name,
                "digests": {"sha256": _digest(files[published_name])},
            }
        ],
    }
    missing_file = tmp_path / "pypi-missing.txt"

    state = release_guard.pypi_state(
        tmp_path,
        ROOT / "server.json",
        missing_file,
        fetch_json=lambda _url, _headers: payload,
    )

    assert state == "resume"
    assert missing_file.read_text(encoding="utf-8").splitlines() == [missing_name]


def test_mcp_guard_only_normalizes_registry_omitted_false_defaults() -> None:
    expected = json.loads((ROOT / "server.json").read_text(encoding="utf-8"))
    published = copy.deepcopy(expected)
    del published["packages"][0]["environmentVariables"][0]["isSecret"]

    release_guard.assert_mcp_release({"server": published, "_meta": {"registry": "generated"}}, expected)

    published["packages"][0]["version"] = "2.1.0"
    with pytest.raises(release_guard.ReleaseConflict, match="different immutable server.json"):
        release_guard.assert_mcp_release({"server": published}, expected)

    published = copy.deepcopy(expected)
    published["unexpected"] = "remote mutation"
    with pytest.raises(release_guard.ReleaseConflict, match="different immutable server.json"):
        release_guard.assert_mcp_release({"server": published}, expected)


def test_github_guard_resumes_only_owned_exact_draft_subsets(tmp_path: Path) -> None:
    files = _release_directory(tmp_path)
    local = release_guard.github_artifacts(tmp_path)
    remote_content = {**files, "SHA256SUMS": (tmp_path / "SHA256SUMS").read_bytes()}
    asset_names_by_id = {index: name for index, name in enumerate(sorted(remote_content), start=1)}

    def fetch_sha256(url: str, _headers: object) -> tuple[int, str]:
        asset_id = int(url.rsplit("/", maxsplit=1)[1])
        content = remote_content[asset_names_by_id[asset_id]]
        return len(content), _digest(content)

    def payload(*, draft: bool, names: set[str], marker: str = release_guard.GITHUB_DRAFT_MARKER) -> dict[str, object]:
        return {
            "tag_name": "v3.0.0",
            "name": "v3.0.0",
            "body": marker,
            "draft": draft,
            "prerelease": False,
            "immutable": not draft,
            "assets": [
                {
                    "id": asset_id,
                    "name": name,
                    "size": len(remote_content[name]),
                    "digest": f"sha256:{_digest(remote_content[name])}",
                }
                for asset_id, name in asset_names_by_id.items()
                if name in names
            ],
        }

    all_names = set(remote_content)
    subset = {next(iter(sorted(all_names)))}
    state, missing = release_guard.inspect_github_release(
        payload(draft=True, names=subset),
        repository="luffysolution-svg/obsidian-vault-mcp",
        tag="v3.0.0",
        local_artifacts=local,
        token="test-token",
        fetch_sha256=fetch_sha256,
    )
    assert state == "resume"
    assert set(missing) == all_names - subset

    assert release_guard.inspect_github_release(
        payload(draft=True, names=all_names),
        repository="luffysolution-svg/obsidian-vault-mcp",
        tag="v3.0.0",
        local_artifacts=local,
        token=None,
        fetch_sha256=fetch_sha256,
    ) == ("ready", ())
    assert release_guard.inspect_github_release(
        payload(
            draft=True,
            names=all_names,
            marker=f"{release_guard.GITHUB_DRAFT_MARKER}\n\n## Obsidian Vault MCP V3\n\nRelease notes.",
        ),
        repository="luffysolution-svg/obsidian-vault-mcp",
        tag="v3.0.0",
        local_artifacts=local,
        token=None,
        fetch_sha256=fetch_sha256,
    ) == ("ready", ())
    assert release_guard.inspect_github_release(
        payload(draft=False, names=all_names),
        repository="luffysolution-svg/obsidian-vault-mcp",
        tag="v3.0.0",
        local_artifacts=local,
        token=None,
        fetch_sha256=fetch_sha256,
    ) == ("existing", ())

    with pytest.raises(release_guard.ReleaseConflict, match="foreign release"):
        release_guard.inspect_github_release(
            payload(draft=True, names=subset, marker="foreign draft"),
            repository="luffysolution-svg/obsidian-vault-mcp",
            tag="v3.0.0",
            local_artifacts=local,
            token=None,
            fetch_sha256=fetch_sha256,
        )
    with pytest.raises(release_guard.ReleaseConflict, match="foreign release"):
        release_guard.inspect_github_release(
            payload(
                draft=True,
                names=subset,
                marker=f"Release notes\n{release_guard.GITHUB_DRAFT_MARKER}",
            ),
            repository="luffysolution-svg/obsidian-vault-mcp",
            tag="v3.0.0",
            local_artifacts=local,
            token=None,
            fetch_sha256=fetch_sha256,
        )
    with pytest.raises(release_guard.ReleaseConflict, match="missing immutable"):
        release_guard.inspect_github_release(
            payload(draft=False, names=subset),
            repository="luffysolution-svg/obsidian-vault-mcp",
            tag="v3.0.0",
            local_artifacts=local,
            token=None,
            fetch_sha256=fetch_sha256,
        )

    nonimmutable = payload(draft=False, names=all_names)
    nonimmutable["immutable"] = False
    with pytest.raises(release_guard.ReleaseConflict, match="not protected"):
        release_guard.inspect_github_release(
            nonimmutable,
            repository="luffysolution-svg/obsidian-vault-mcp",
            tag="v3.0.0",
            local_artifacts=local,
            token=None,
            fetch_sha256=fetch_sha256,
        )

    extra = payload(draft=True, names=subset)
    extra["assets"].append(
        {
            "id": 999,
            "name": "foreign.zip",
            "size": 1,
            "digest": f"sha256:{'0' * 64}",
        }
    )
    with pytest.raises(release_guard.ReleaseConflict, match="not a subset"):
        release_guard.inspect_github_release(
            extra,
            repository="luffysolution-svg/obsidian-vault-mcp",
            tag="v3.0.0",
            local_artifacts=local,
            token=None,
            fetch_sha256=fetch_sha256,
        )

    conflicting = payload(draft=True, names=all_names)
    conflicting["assets"][0]["size"] += 1
    with pytest.raises(release_guard.ReleaseConflict, match="size differs"):
        release_guard.inspect_github_release(
            conflicting,
            repository="luffysolution-svg/obsidian-vault-mcp",
            tag="v3.0.0",
            local_artifacts=local,
            token=None,
            fetch_sha256=fetch_sha256,
        )

    conflicting = payload(draft=True, names=all_names)
    conflicting["assets"][0]["digest"] = f"sha256:{'0' * 64}"
    with pytest.raises(release_guard.ReleaseConflict, match="digest differs"):
        release_guard.inspect_github_release(
            conflicting,
            repository="luffysolution-svg/obsidian-vault-mcp",
            tag="v3.0.0",
            local_artifacts=local,
            token=None,
            fetch_sha256=fetch_sha256,
        )


def test_github_guard_reports_publish_and_writes_the_exact_missing_list(tmp_path: Path) -> None:
    _release_directory(tmp_path)
    missing_file = tmp_path / "missing.txt"

    def fetch_settings(_url: str, headers: Mapping[str, str] | None) -> dict[str, object]:
        assert headers is not None and headers["Authorization"] == "Bearer admin-token"
        return {"enabled": True, "enforced_by_owner": False}

    def fetch_releases(_url: str, headers: Mapping[str, str] | None) -> list[dict[str, object]]:
        assert headers is not None and headers["Authorization"] == "Bearer test-token"
        return []

    state = release_guard.github_state(
        tmp_path,
        repository="luffysolution-svg/obsidian-vault-mcp",
        tag="v3.0.0",
        expected_commit_sha=COMMIT_SHA,
        expected_tag_object_sha=TAG_OBJECT_SHA,
        token="test-token",
        settings_token="admin-token",
        missing_assets_file=missing_file,
        fetch_json=fetch_settings,
        fetch_tag_json=_fetch_annotated_tag,
        fetch_json_list=fetch_releases,
    )

    assert state == "publish"
    assert missing_file.read_text(encoding="utf-8").splitlines() == sorted(release_guard.github_artifacts(tmp_path))


def test_github_guard_writes_only_missing_assets_for_an_owned_draft(tmp_path: Path) -> None:
    files = _release_directory(tmp_path)
    remote_content = {**files, "SHA256SUMS": (tmp_path / "SHA256SUMS").read_bytes()}
    uploaded_name = sorted(remote_content)[0]
    uploaded = remote_content[uploaded_name]
    payload = {
        "tag_name": "v3.0.0",
        "name": "v3.0.0",
        "body": release_guard.GITHUB_DRAFT_MARKER,
        "draft": True,
        "prerelease": False,
        "immutable": False,
        "assets": [
            {
                "id": 1,
                "name": uploaded_name,
                "size": len(uploaded),
                "digest": f"sha256:{_digest(uploaded)}",
            }
        ],
    }
    missing_file = tmp_path / "missing.txt"

    state = release_guard.github_state(
        tmp_path,
        repository="luffysolution-svg/obsidian-vault-mcp",
        tag="v3.0.0",
        expected_commit_sha=COMMIT_SHA,
        expected_tag_object_sha=TAG_OBJECT_SHA,
        token="test-token",
        settings_token="admin-token",
        missing_assets_file=missing_file,
        fetch_json=lambda _url, _headers: {
            "enabled": True,
            "enforced_by_owner": False,
        },
        fetch_tag_json=_fetch_annotated_tag,
        fetch_json_list=lambda _url, _headers: [payload],
        fetch_sha256=lambda _url, _headers: (len(uploaded), _digest(uploaded)),
    )

    assert state == "resume"
    assert missing_file.read_text(encoding="utf-8").splitlines() == sorted(set(remote_content) - {uploaded_name})


def test_github_guard_discovers_drafts_through_the_authenticated_release_list() -> None:
    draft = {"tag_name": "v3.0.0", "draft": True}
    requested_urls: list[str] = []

    def fetch_json_list(url: str, headers: Mapping[str, str] | None) -> list[dict[str, object]]:
        requested_urls.append(url)
        assert headers is not None and "Authorization" in headers
        return [draft]

    assert release_guard.find_github_release(
        repository="luffysolution-svg/obsidian-vault-mcp",
        tag="v3.0.0",
        token="test-token",
        fetch_json_list=fetch_json_list,
    ) == draft
    assert requested_urls == [
        "https://api.github.com/repos/luffysolution-svg/obsidian-vault-mcp/releases?per_page=100&page=1"
    ]


def test_github_tag_guard_binds_annotated_tag_object_to_build_commit() -> None:
    release_guard.assert_github_tag_identity(
        repository="luffysolution-svg/obsidian-vault-mcp",
        tag="v3.0.0",
        expected_commit_sha=COMMIT_SHA,
        expected_tag_object_sha=TAG_OBJECT_SHA,
        token="test-token",
        fetch_json=_fetch_annotated_tag,
    )

    with pytest.raises(release_guard.ReleaseConflict, match="tag object changed"):
        release_guard.assert_github_tag_identity(
            repository="luffysolution-svg/obsidian-vault-mcp",
            tag="v3.0.0",
            expected_commit_sha=COMMIT_SHA,
            expected_tag_object_sha="3" * 40,
            token="test-token",
            fetch_json=_fetch_annotated_tag,
        )

    def moved_target(url: str, headers: Mapping[str, str] | None) -> dict[str, object]:
        payload = _fetch_annotated_tag(url, headers)
        if url.endswith(f"/git/tags/{TAG_OBJECT_SHA}"):
            return {"object": {"type": "commit", "sha": "4" * 40}}
        return payload

    with pytest.raises(release_guard.ReleaseConflict, match="different commit"):
        release_guard.assert_github_tag_identity(
            repository="luffysolution-svg/obsidian-vault-mcp",
            tag="v3.0.0",
            expected_commit_sha=COMMIT_SHA,
            expected_tag_object_sha=TAG_OBJECT_SHA,
            token="test-token",
            fetch_json=moved_target,
        )


def test_github_guard_requires_repository_release_immutability(
    tmp_path: Path,
) -> None:
    _release_directory(tmp_path)

    with pytest.raises(release_guard.ReleaseConflict, match="must be enabled"):
        release_guard.github_state(
            tmp_path,
            repository="luffysolution-svg/obsidian-vault-mcp",
            tag="v3.0.0",
            expected_commit_sha=COMMIT_SHA,
            expected_tag_object_sha=TAG_OBJECT_SHA,
            token="test-token",
            settings_token="admin-token",
            fetch_json=lambda _url, _headers: {
                "enabled": False,
                "enforced_by_owner": False,
            },
            fetch_tag_json=_fetch_annotated_tag,
            fetch_json_list=lambda _url, _headers: [],
        )

    with pytest.raises(release_guard.ReleaseConflict, match="IMMUTABLE_RELEASES_TOKEN"):
        release_guard.github_state(
            tmp_path,
            repository="luffysolution-svg/obsidian-vault-mcp",
            tag="v3.0.0",
            expected_commit_sha=COMMIT_SHA,
            expected_tag_object_sha=TAG_OBJECT_SHA,
            token="workflow-token",
            settings_token=None,
            fetch_tag_json=_fetch_annotated_tag,
            fetch_json_list=lambda _url, _headers: [],
        )


def test_release_workflow_preflights_each_destination_and_creates_github_release_last() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

    pypi_guard = workflow.index("Preflight immutable PyPI destination")
    pypi_publish = workflow.index("Publish only missing Python artifacts to PyPI")
    pypi_wait = workflow.index("Wait for exact immutable PyPI artifacts")
    mcp_guard = workflow.index("Preflight immutable MCP Registry destination")
    mcp_validate = workflow.index("Install and validate verified MCP Registry publisher")
    mcp_recheck = workflow.index("Recheck MCP destination immediately before publication")
    mcp_publish = workflow.index("Publish metadata to the MCP Registry")
    mcp_wait = workflow.index("Wait for exact immutable MCP Registry metadata")
    github_guard = workflow.index("Preflight immutable GitHub Release destination")
    github_create = workflow.index("Create owned empty GitHub Release draft")
    github_upload = workflow.index("Upload only missing draft assets")
    github_ready = workflow.index("Verify owned GitHub Release draft is ready")
    github_publish = workflow.index("Publish verified GitHub Release draft")
    github_final = workflow.index("Verify final immutable GitHub Release")

    assert (
        github_guard
        < pypi_guard
        < mcp_guard
        < mcp_validate
        < pypi_publish
        < pypi_wait
        < mcp_recheck
        < mcp_publish
        < mcp_wait
        < github_create
        < github_upload
        < github_ready
        < github_publish
        < github_final
    )
    assert "if: steps.pypi.outputs.publish == 'true'" in workflow
    assert "if: steps.mcp_registry.outputs.publish == 'true'" in workflow
    assert "publish|resume|ready|existing" in workflow
    assert "publish|resume)" in workflow
    assert workflow.count("python scripts/release_guard.py pypi") == 2
    assert workflow.count("python scripts/release_guard.py mcp") == 3
    assert workflow.count("python scripts/release_guard.py github") == 7
    assert release_guard.GITHUB_DRAFT_MARKER in workflow
    assert "IMMUTABLE_RELEASES_TOKEN: ${{ secrets.IMMUTABLE_RELEASES_TOKEN }}" in workflow
    assert 'gh release create "$RELEASE_TAG"' in workflow
    assert "--draft" in workflow
    assert "--notes \"$RELEASE_NOTES\"" in workflow
    assert "Five Analysis types" in workflow
    assert "31 MCP tools" in workflow
    assert "Transactional Vault writes with dry-run, backups, conflict protection, and rollback" in workflow
    assert "Seven packaged Agent Skills for literature research workflows" in workflow
    assert "Dual CLI entry points" in workflow
    assert '--missing-assets-file "$missing_assets"' in workflow
    assert '--missing-artifacts-file "$missing_artifacts"' in workflow
    assert "packages-dir: pypi-upload/" in workflow
    assert 'gh release upload "$RELEASE_TAG" "dist/$asset"' in workflow
    assert 'gh release edit "$RELEASE_TAG" --draft=false --verify-tag' in workflow
    assert "skip-existing" not in workflow
    assert "--clobber" not in workflow
    assert "SOURCE_DATE_EPOCH=$(git show -s --format=%ct HEAD)" in workflow
    assert "uv sync --locked --all-extras" in workflow
    assert "uv run python -m build --wheel --sdist --outdir dist" in workflow
    assert "--no-isolation" not in workflow
    assert "release_guard.py normalize-sdist --artifacts-dir dist --epoch" in workflow
    pristine_before = workflow.index("Require pristine verified sources before build")
    build_candidate = workflow.index("Build wheel and source distribution")
    pristine_after = workflow.index("Require build left verified sources pristine")
    upload_candidate = workflow.index("Upload verified release candidate")
    assert pristine_before < build_candidate < pristine_after < upload_candidate
    assert workflow.count("git diff --exit-code") == 2
    assert workflow.count("git diff --cached --exit-code") == 2
    assert workflow.count("git ls-files --others --exclude-standard") == 2
    assert "github.event_name == 'workflow_dispatch' && inputs.tag || github.ref_name" in workflow
    assert "ref: ${{ steps.tag.outputs.ref }}" in workflow
    assert "ref: ${{ needs.build.outputs.commit_sha }}" in workflow
    assert "git ls-remote --exit-code --refs origin \"$RELEASE_REF\"" in workflow
    assert "ref: ${{ steps.tag.outputs.tag }}" not in workflow
    assert "commit_sha: ${{ steps.tag_identity.outputs.commit_sha }}" in workflow
    assert "tag_object_sha: ${{ steps.tag_identity.outputs.tag_object_sha }}" in workflow
    assert workflow.count('--expected-commit-sha "$EXPECTED_COMMIT_SHA"') == 7
    assert workflow.count('--expected-tag-object-sha "$EXPECTED_TAG_OBJECT_SHA"') == 7
    assert workflow.count("persist-credentials: false") == 2
    assert workflow.index("./mcp-publisher login github-oidc") < pypi_publish
    create_guard = workflow.index(
        'state="$(python scripts/release_guard.py github \\',
        github_create,
    )
    create_mutation = workflow.index('gh release create "$RELEASE_TAG"', github_create)
    upload_guard = workflow.index(
        'state="$(python scripts/release_guard.py github \\',
        github_upload,
    )
    upload_mutation = workflow.index('gh release upload "$RELEASE_TAG" "dist/$asset"')
    ready_guard = workflow.index(
        'state="$(python scripts/release_guard.py github \\',
        github_ready,
    )
    publish_guard = workflow.index(
        'state="$(python scripts/release_guard.py github \\',
        github_publish,
    )
    publish_edit = workflow.index('gh release edit "$RELEASE_TAG" --draft=false --verify-tag')
    assert github_create < create_guard < create_mutation
    assert github_upload < upload_guard < upload_mutation < github_ready < ready_guard
    assert github_publish < publish_guard < publish_edit
    assert workflow.rfind(
        "IMMUTABLE_RELEASES_TOKEN: ${{ secrets.IMMUTABLE_RELEASES_TOKEN }}",
        github_publish,
        publish_edit,
    ) != -1
    assert workflow.count("id-token: write") == 1
    assert workflow.index("permissions:\n      contents: read") < workflow.index("Install project and release tooling")
    assert workflow.index("permissions:\n      contents: write\n      id-token: write") < github_guard


def test_release_workflow_keeps_build_unprivileged_and_scopes_the_serial_publish_job() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    build_section, publish_section = workflow.split("\n  publish:\n", maxsplit=1)
    privileged_permissions = "permissions:\n      contents: write\n      id-token: write"

    assert "contents: write" not in build_section
    assert "id-token: write" not in build_section
    assert privileged_permissions in publish_section
    assert workflow.count(privileged_permissions) == 1
    assert "needs: build" in publish_section
    assert publish_section.count("persist-credentials: false") == 1


def test_developer_guides_document_strict_draft_resume_without_overwrite() -> None:
    chinese = (ROOT / "DEVELOPMENT.md").read_text(encoding="utf-8")
    english = (ROOT / "DEVELOPMENT.en.md").read_text(encoding="utf-8")

    for guide in (chinese, english):
        assert "workflow marker" in guide
        assert "draft" in guide
        assert "SHA256" in guide
        assert "PyPI" in guide
        assert "MCP Registry" in guide
        assert "immutable" in guide
    assert "禁止删除或覆盖" in chinese
    assert "without deletion or overwrite" in english
