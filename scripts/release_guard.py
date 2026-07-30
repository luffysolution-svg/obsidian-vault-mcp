from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import sys
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, BinaryIO

PYPI_API = "https://pypi.org/pypi"
MCP_REGISTRY_API = "https://registry.modelcontextprotocol.io/v0.1"
GITHUB_API = "https://api.github.com"
USER_AGENT = "obsidian-vault-mcp-release-guard"
OPTIONAL_FALSE_FIELDS = frozenset({"isRepeated", "isRequired", "isSecret"})
GITHUB_DRAFT_MARKER = "<!-- obsidian-vault-mcp-release-workflow:draft-v1 -->"
SAFE_ASSET_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


class ReleaseConflict(RuntimeError):
    """A destination already contains data that differs from this build."""


class DestinationUnavailable(RuntimeError):
    """A destination could not be inspected safely."""


class StripCrossOriginAuthorization(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        request: urllib.request.Request,
        file_pointer: BinaryIO,
        code: int,
        message: str,
        headers: Mapping[str, str],
        new_url: str,
    ) -> urllib.request.Request | None:
        redirected = super().redirect_request(request, file_pointer, code, message, headers, new_url)
        if redirected is not None:
            old_origin = urllib.parse.urlsplit(request.full_url)[:2]
            new_origin = urllib.parse.urlsplit(new_url)[:2]
            if old_origin != new_origin:
                redirected.remove_header("Authorization")
        return redirected


URL_OPENER = urllib.request.build_opener(StripCrossOriginAuthorization)


def sha256_stream(stream: BinaryIO) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        size += len(chunk)
        digest.update(chunk)
    return size, digest.hexdigest()


def sha256_file(path: Path) -> tuple[int, str]:
    with path.open("rb") as stream:
        return sha256_stream(stream)


def request_json_value(url: str, headers: Mapping[str, str] | None = None) -> Any | None:
    request_headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    request_headers.update(headers or {})
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with URL_OPENER.open(request, timeout=30) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise DestinationUnavailable(f"HTTP {exc.code} while inspecting {url}.") from exc
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        raise DestinationUnavailable(f"Cannot inspect {url}: {exc}") from exc
    return payload


def request_json(url: str, headers: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    payload = request_json_value(url, headers)
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise DestinationUnavailable(f"Expected a JSON object from {url}.")
    return payload


def request_json_list(url: str, headers: Mapping[str, str] | None = None) -> list[dict[str, Any]]:
    payload = request_json_value(url, headers)
    if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
        raise DestinationUnavailable(f"Expected a JSON object list from {url}.")
    return payload


def request_sha256(url: str, headers: Mapping[str, str] | None = None) -> tuple[int, str]:
    request_headers = {"User-Agent": USER_AGENT}
    request_headers.update(headers or {})
    request_headers["Accept"] = "application/octet-stream"
    request = urllib.request.Request(url, headers=request_headers)
    try:
        with URL_OPENER.open(request, timeout=60) as response:
            return sha256_stream(response)
    except urllib.error.HTTPError as exc:
        raise DestinationUnavailable(f"HTTP {exc.code} while downloading a release asset.") from exc
    except (OSError, TimeoutError) as exc:
        raise DestinationUnavailable(f"Cannot download a release asset: {exc}") from exc


def server_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseConflict(f"Cannot read valid server metadata from {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ReleaseConflict(f"{path} must contain one JSON object.")
    return payload


def pypi_identity(server: Mapping[str, Any]) -> tuple[str, str]:
    packages = server.get("packages")
    if not isinstance(packages, list):
        raise ReleaseConflict("server.json has no package list.")
    pypi_packages = [package for package in packages if isinstance(package, dict) and package.get("registryType") == "pypi"]
    if len(pypi_packages) != 1:
        raise ReleaseConflict("server.json must contain exactly one PyPI package.")
    project = pypi_packages[0].get("identifier")
    package_version = pypi_packages[0].get("version")
    server_version = server.get("version")
    if not isinstance(project, str) or not project:
        raise ReleaseConflict("server.json has no valid PyPI package identifier.")
    if not isinstance(package_version, str) or package_version != server_version:
        raise ReleaseConflict("server.json package and server versions must match.")
    return project, package_version


def python_artifacts(directory: Path) -> dict[str, str]:
    wheels = sorted(path for path in directory.glob("*.whl") if path.is_file())
    sdists = sorted(path for path in directory.glob("*.tar.gz") if path.is_file())
    if len(wheels) != 1 or len(sdists) != 1:
        raise ReleaseConflict(f"Expected exactly one wheel and one sdist in {directory}.")
    return {path.name: sha256_file(path)[1] for path in (*wheels, *sdists)}


def normalize_sdist(archive_path: Path, epoch: int) -> None:
    if epoch < 0:
        raise ReleaseConflict("SOURCE_DATE_EPOCH must be a non-negative integer.")
    temporary_name: str | None = None
    try:
        with tarfile.open(archive_path, "r:gz") as source:
            members = sorted(source.getmembers(), key=lambda member: member.name)
            if not members or any(not (member.isfile() or member.isdir()) for member in members):
                raise ReleaseConflict("Source distribution may contain only regular files and directories.")
            with tempfile.NamedTemporaryFile(
                mode="w+b",
                prefix=f".{archive_path.name}.",
                suffix=".tmp",
                dir=archive_path.parent,
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                with gzip.GzipFile(filename="", mode="wb", fileobj=temporary, compresslevel=9, mtime=epoch) as compressed:
                    with tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as destination:
                        for member in members:
                            member.mtime = epoch
                            member.uid = 0
                            member.gid = 0
                            member.uname = ""
                            member.gname = ""
                            member.pax_headers = {}
                            content = source.extractfile(member) if member.isfile() else None
                            destination.addfile(member, content)
                temporary.flush()
                os.fsync(temporary.fileno())
        os.replace(temporary_name, archive_path)
        temporary_name = None
    except (OSError, tarfile.TarError) as exc:
        raise ReleaseConflict(f"Cannot normalize source distribution {archive_path}: {exc}") from exc
    finally:
        if temporary_name is not None:
            try:
                Path(temporary_name).unlink()
            except OSError:
                pass


def normalize_sdist_directory(directory: Path, epoch: int) -> Path:
    sdists = sorted(path for path in directory.glob("*.tar.gz") if path.is_file())
    if len(sdists) != 1:
        raise ReleaseConflict(f"Expected exactly one sdist in {directory}.")
    normalize_sdist(sdists[0], epoch)
    return sdists[0]


def normalized_project_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def assert_pypi_release(
    payload: Mapping[str, Any],
    *,
    project: str,
    version: str,
    local_artifacts: Mapping[str, str],
) -> tuple[str, ...]:
    info = payload.get("info")
    urls = payload.get("urls")
    if not isinstance(info, dict) or not isinstance(urls, list):
        raise ReleaseConflict("PyPI returned malformed release metadata.")
    remote_name = info.get("name")
    if (
        not isinstance(remote_name, str)
        or normalized_project_name(remote_name) != normalized_project_name(project)
        or info.get("version") != version
    ):
        raise ReleaseConflict("PyPI project/version metadata conflicts with server.json.")

    remote_artifacts: dict[str, str] = {}
    for entry in urls:
        if not isinstance(entry, dict):
            raise ReleaseConflict("PyPI returned a malformed release file.")
        filename = entry.get("filename")
        digests = entry.get("digests")
        digest = digests.get("sha256") if isinstance(digests, dict) else None
        if (
            not isinstance(filename, str)
            or Path(filename).name != filename
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None
            or filename in remote_artifacts
        ):
            raise ReleaseConflict("PyPI returned an invalid or duplicate release file.")
        remote_artifacts[filename] = digest.lower()

    local = dict(local_artifacts)
    if not set(remote_artifacts).issubset(local):
        raise ReleaseConflict(
            "PyPI already contains different files or SHA256 digests for this immutable version."
        )
    for filename, digest in remote_artifacts.items():
        if local[filename] != digest:
            raise ReleaseConflict(
                "PyPI already contains different files or SHA256 digests for this immutable version."
            )
    return tuple(sorted(set(local) - set(remote_artifacts)))


def pypi_state(
    artifacts_directory: Path,
    metadata_path: Path,
    missing_artifacts_file: Path | None = None,
    fetch_json: Callable[[str, Mapping[str, str] | None], dict[str, Any] | None] = request_json,
) -> str:
    metadata = server_json(metadata_path)
    project, version = pypi_identity(metadata)
    local_artifacts = python_artifacts(artifacts_directory)
    url = f"{PYPI_API}/{urllib.parse.quote(project, safe='')}/{urllib.parse.quote(version, safe='')}/json"
    payload = fetch_json(url, None)
    if payload is None:
        state = "publish"
        missing = tuple(sorted(local_artifacts))
    else:
        missing = assert_pypi_release(
            payload,
            project=project,
            version=version,
            local_artifacts=local_artifacts,
        )
        state = "resume" if missing else "existing"
    if missing_artifacts_file is not None:
        missing_artifacts_file.write_text(
            "".join(f"{name}\n" for name in missing),
            encoding="utf-8",
            newline="\n",
        )
    return state


def normalize_registry_server(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize_registry_server(child)
            for key, child in value.items()
            if not (key in OPTIONAL_FALSE_FIELDS and child is False)
        }
    if isinstance(value, list):
        return [normalize_registry_server(child) for child in value]
    return value


def assert_mcp_release(payload: Mapping[str, Any], expected_server: Mapping[str, Any]) -> None:
    published_server = payload.get("server")
    if not isinstance(published_server, dict):
        raise ReleaseConflict("MCP Registry returned malformed server metadata.")
    if normalize_registry_server(published_server) != normalize_registry_server(dict(expected_server)):
        raise ReleaseConflict(
            "MCP Registry already contains different immutable server.json metadata for this version."
        )


def mcp_state(
    metadata_path: Path,
    fetch_json: Callable[[str, Mapping[str, str] | None], dict[str, Any] | None] = request_json,
) -> str:
    metadata = server_json(metadata_path)
    name = metadata.get("name")
    version = metadata.get("version")
    if not isinstance(name, str) or not name or not isinstance(version, str) or not version:
        raise ReleaseConflict("server.json has no valid MCP name/version.")
    url = (
        f"{MCP_REGISTRY_API}/servers/{urllib.parse.quote(name, safe='')}"
        f"/versions/{urllib.parse.quote(version, safe='')}"
    )
    payload = fetch_json(url, None)
    if payload is None:
        return "publish"
    assert_mcp_release(payload, metadata)
    return "existing"


def parse_checksum_manifest(manifest: Path) -> dict[str, str]:
    recorded: dict[str, str] = {}
    try:
        lines = manifest.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise ReleaseConflict(f"Cannot read {manifest}: {exc}") from exc
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]) is None:
            raise ReleaseConflict(f"Invalid SHA256SUMS line {line_number}.")
        filename = parts[1].lstrip("*")
        if not filename or Path(filename).name != filename or filename in recorded:
            raise ReleaseConflict(f"Invalid or duplicate SHA256SUMS filename on line {line_number}.")
        recorded[filename] = parts[0].lower()
    return recorded


def github_artifacts(directory: Path) -> dict[str, tuple[int, str]]:
    artifact_paths = sorted(
        {
            path
            for pattern in ("*.whl", "*.tar.gz", "*.zip")
            for path in directory.glob(pattern)
            if path.is_file()
        },
        key=lambda path: path.name,
    )
    manifest = directory / "SHA256SUMS"
    if not artifact_paths or not manifest.is_file():
        raise ReleaseConflict(f"Release artifacts or SHA256SUMS are missing from {directory}.")

    recorded = parse_checksum_manifest(manifest)
    local: dict[str, tuple[int, str]] = {}
    for path in artifact_paths:
        if SAFE_ASSET_NAME.fullmatch(path.name) is None:
            raise ReleaseConflict(f"Unsafe local GitHub release asset name: {path.name!r}.")
        size, digest = sha256_file(path)
        if recorded.get(path.name) != digest:
            raise ReleaseConflict(f"Local SHA256SUMS does not match {path.name}.")
        local[path.name] = (size, digest)
    if set(recorded) != set(local):
        raise ReleaseConflict("Local SHA256SUMS does not list the exact release artifact set.")
    local[manifest.name] = sha256_file(manifest)
    return local


def github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def is_owned_github_release_body(value: object) -> bool:
    return isinstance(value, str) and (
        value == GITHUB_DRAFT_MARKER or value.startswith(f"{GITHUB_DRAFT_MARKER}\n")
    )


def normalized_git_object_id(value: object, *, label: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})", value) is None:
        raise ReleaseConflict(f"{label} must be a 40- or 64-character Git object ID.")
    return value.lower()


def assert_github_tag_identity(
    *,
    repository: str,
    tag: str,
    expected_commit_sha: str,
    expected_tag_object_sha: str,
    token: str | None,
    fetch_json: Callable[
        [str, Mapping[str, str] | None],
        dict[str, Any] | None,
    ] = request_json,
) -> None:
    """Require the exact remote tag object to resolve to the build commit."""

    if not token:
        raise ReleaseConflict("Authenticated GH_TOKEN is required to inspect the release tag.")
    expected_commit = normalized_git_object_id(expected_commit_sha, label="Expected release commit")
    expected_tag_object = normalized_git_object_id(
        expected_tag_object_sha,
        label="Expected release tag object",
    )
    owner, repository_name = repository.split("/", maxsplit=1)
    repository_url = (
        f"{GITHUB_API}/repos/{urllib.parse.quote(owner, safe='')}/"
        f"{urllib.parse.quote(repository_name, safe='')}"
    )
    headers = github_headers(token)
    reference_url = f"{repository_url}/git/ref/tags/{urllib.parse.quote(tag, safe='')}"
    reference = fetch_json(reference_url, headers)
    git_object = reference.get("object") if isinstance(reference, dict) else None
    if (
        not isinstance(reference, dict)
        or reference.get("ref") != f"refs/tags/{tag}"
        or not isinstance(git_object, dict)
    ):
        raise ReleaseConflict(f"GitHub release tag ref is missing or malformed: refs/tags/{tag}.")

    object_type = git_object.get("type")
    object_sha = normalized_git_object_id(git_object.get("sha"), label="Remote release tag object")
    if object_sha != expected_tag_object:
        raise ReleaseConflict("GitHub release tag object changed after the verified build.")

    seen: set[str] = set()
    for _ in range(64):
        if object_type == "commit":
            if object_sha != expected_commit:
                raise ReleaseConflict("GitHub release tag resolves to a different commit than the verified build.")
            return
        if object_type != "tag" or object_sha in seen:
            raise ReleaseConflict("GitHub release tag does not resolve through a valid annotated tag chain.")
        seen.add(object_sha)
        annotated_tag = fetch_json(f"{repository_url}/git/tags/{object_sha}", headers)
        nested_object = annotated_tag.get("object") if isinstance(annotated_tag, dict) else None
        if not isinstance(nested_object, dict):
            raise ReleaseConflict("GitHub returned a malformed annotated release tag object.")
        object_type = nested_object.get("type")
        object_sha = normalized_git_object_id(
            nested_object.get("sha"),
            label="Annotated release tag target",
        )
    raise ReleaseConflict("GitHub annotated release tag chain exceeds the safe depth limit.")


def assert_github_release_immutability(
    *,
    repository: str,
    token: str | None,
    fetch_json: Callable[
        [str, Mapping[str, str] | None],
        dict[str, Any] | None,
    ] = request_json,
) -> None:
    """Require repository-level immutability before any external publication."""

    if not token:
        raise ReleaseConflict(
            "Authenticated IMMUTABLE_RELEASES_TOKEN with repository Administration: read is required "
            "to inspect release immutability."
        )
    owner, repository_name = repository.split("/", maxsplit=1)
    url = (
        f"{GITHUB_API}/repos/{urllib.parse.quote(owner, safe='')}/"
        f"{urllib.parse.quote(repository_name, safe='')}/immutable-releases"
    )
    payload = fetch_json(url, github_headers(token))
    if not isinstance(payload, dict) or payload.get("enabled") is not True:
        raise ReleaseConflict(
            "GitHub repository release immutability must be enabled before publication."
        )


def find_github_release(
    *,
    repository: str,
    tag: str,
    token: str | None,
    fetch_json_list: Callable[[str, Mapping[str, str] | None], list[dict[str, Any]]] = request_json_list,
) -> dict[str, Any] | None:
    owner, repository_name = repository.split("/", maxsplit=1)
    matches: list[dict[str, Any]] = []
    for page in range(1, 1001):
        url = (
            f"{GITHUB_API}/repos/{urllib.parse.quote(owner, safe='')}/"
            f"{urllib.parse.quote(repository_name, safe='')}/releases?per_page=100&page={page}"
        )
        releases = fetch_json_list(url, github_headers(token))
        matches.extend(release for release in releases if release.get("tag_name") == tag)
        if len(releases) < 100:
            break
    else:
        raise DestinationUnavailable("GitHub release pagination exceeded 1000 pages.")
    if len(matches) > 1:
        raise ReleaseConflict(f"GitHub returned duplicate releases for tag {tag}.")
    return matches[0] if matches else None


def inspect_github_release(
    payload: Mapping[str, Any],
    *,
    repository: str,
    tag: str,
    local_artifacts: Mapping[str, tuple[int, str]],
    token: str | None,
    fetch_sha256: Callable[[str, Mapping[str, str] | None], tuple[int, str]] = request_sha256,
) -> tuple[str, tuple[str, ...]]:
    draft = payload.get("draft")
    if (
        payload.get("tag_name") != tag
        or payload.get("name") != tag
        or not isinstance(draft, bool)
        or payload.get("prerelease") is not False
        or not is_owned_github_release_body(payload.get("body"))
    ):
        raise ReleaseConflict("GitHub already contains a foreign release, draft marker, prerelease, title, or tag.")
    assets = payload.get("assets")
    if not isinstance(assets, list):
        raise ReleaseConflict("GitHub returned malformed release assets.")

    remote_assets: dict[str, Mapping[str, Any]] = {}
    for asset in assets:
        if not isinstance(asset, dict):
            raise ReleaseConflict("GitHub returned a malformed release asset.")
        name = asset.get("name")
        if (
            not isinstance(name, str)
            or SAFE_ASSET_NAME.fullmatch(name) is None
            or Path(name).name != name
            or name in remote_assets
        ):
            raise ReleaseConflict("GitHub returned an invalid or duplicate release asset.")
        remote_assets[name] = asset
    if not set(remote_assets).issubset(local_artifacts):
        raise ReleaseConflict("GitHub release assets are not a subset of the local immutable artifact set.")

    owner, repository_name = repository.split("/", maxsplit=1)
    headers = github_headers(token)
    for name, asset in remote_assets.items():
        local_size, local_digest = local_artifacts[name]
        asset_id = asset.get("id")
        asset_size = asset.get("size")
        api_digest = asset.get("digest")
        if not isinstance(asset_id, int) or asset_size != local_size:
            raise ReleaseConflict(f"GitHub release asset size differs from local: {name}.")
        if api_digest is not None and api_digest != f"sha256:{local_digest}":
            raise ReleaseConflict(f"GitHub release asset digest differs from local: {name}.")
        asset_url = (
            f"{GITHUB_API}/repos/{urllib.parse.quote(owner, safe='')}/"
            f"{urllib.parse.quote(repository_name, safe='')}/releases/assets/{asset_id}"
        )
        remote_size, remote_digest = fetch_sha256(asset_url, headers)
        if remote_size != local_size or remote_digest != local_digest:
            raise ReleaseConflict(f"GitHub release asset content differs from local: {name}.")

    missing = tuple(sorted(set(local_artifacts) - set(remote_assets)))
    if draft is True:
        return ("resume" if missing else "ready"), missing
    if payload.get("immutable") is not True:
        raise ReleaseConflict("Published GitHub release is not protected by repository release immutability.")
    if missing:
        raise ReleaseConflict("Published GitHub release is missing immutable local assets.")
    return "existing", ()


def github_state(
    artifacts_directory: Path,
    *,
    repository: str,
    tag: str,
    expected_commit_sha: str,
    expected_tag_object_sha: str,
    token: str | None,
    settings_token: str | None,
    missing_assets_file: Path | None = None,
    fetch_json: Callable[
        [str, Mapping[str, str] | None],
        dict[str, Any] | None,
    ] = request_json,
    fetch_tag_json: Callable[
        [str, Mapping[str, str] | None],
        dict[str, Any] | None,
    ] = request_json,
    fetch_json_list: Callable[[str, Mapping[str, str] | None], list[dict[str, Any]]] = request_json_list,
    fetch_sha256: Callable[[str, Mapping[str, str] | None], tuple[int, str]] = request_sha256,
) -> str:
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise ReleaseConflict(f"Invalid GitHub repository identifier: {repository!r}.")
    if re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag) is None:
        raise ReleaseConflict(f"Invalid immutable release tag: {tag!r}.")
    if not token:
        raise ReleaseConflict("Authenticated GH_TOKEN is required to discover resumable draft releases.")
    assert_github_tag_identity(
        repository=repository,
        tag=tag,
        expected_commit_sha=expected_commit_sha,
        expected_tag_object_sha=expected_tag_object_sha,
        token=token,
        fetch_json=fetch_tag_json,
    )
    assert_github_release_immutability(
        repository=repository,
        token=settings_token,
        fetch_json=fetch_json,
    )
    local_artifacts = github_artifacts(artifacts_directory)
    payload = find_github_release(
        repository=repository,
        tag=tag,
        token=token,
        fetch_json_list=fetch_json_list,
    )
    if payload is None:
        state = "publish"
        missing = tuple(sorted(local_artifacts))
    else:
        state, missing = inspect_github_release(
            payload,
            repository=repository,
            tag=tag,
            local_artifacts=local_artifacts,
            token=token,
            fetch_sha256=fetch_sha256,
        )
    if missing_assets_file is not None:
        missing_assets_file.write_text(
            "".join(f"{name}\n" for name in missing),
            encoding="utf-8",
            newline="\n",
        )
    return state


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Guard immutable production release destinations.")
    subparsers = parser.add_subparsers(dest="destination", required=True)

    pypi = subparsers.add_parser("pypi")
    pypi.add_argument("--artifacts-dir", type=Path, required=True)
    pypi.add_argument("--server-json", type=Path, default=Path("server.json"))
    pypi.add_argument("--missing-artifacts-file", type=Path)

    mcp = subparsers.add_parser("mcp")
    mcp.add_argument("--server-json", type=Path, default=Path("server.json"))

    github = subparsers.add_parser("github")
    github.add_argument("--artifacts-dir", type=Path, required=True)
    github.add_argument("--repository", required=True)
    github.add_argument("--tag", required=True)
    github.add_argument("--expected-commit-sha", required=True)
    github.add_argument("--expected-tag-object-sha", required=True)
    github.add_argument("--missing-assets-file", type=Path)

    normalize = subparsers.add_parser("normalize-sdist")
    normalize.add_argument("--artifacts-dir", type=Path, required=True)
    normalize.add_argument("--epoch", type=int, required=True)
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    try:
        if arguments.destination == "pypi":
            state = pypi_state(
                arguments.artifacts_dir,
                arguments.server_json,
                arguments.missing_artifacts_file,
            )
        elif arguments.destination == "mcp":
            state = mcp_state(arguments.server_json)
        elif arguments.destination == "github":
            token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
            settings_token = os.environ.get("IMMUTABLE_RELEASES_TOKEN")
            state = github_state(
                arguments.artifacts_dir,
                repository=arguments.repository,
                tag=arguments.tag,
                expected_commit_sha=arguments.expected_commit_sha,
                expected_tag_object_sha=arguments.expected_tag_object_sha,
                token=token,
                settings_token=settings_token,
                missing_assets_file=arguments.missing_assets_file,
            )
        else:
            normalize_sdist_directory(arguments.artifacts_dir, arguments.epoch)
            state = "normalized"
    except (DestinationUnavailable, OSError, ReleaseConflict) as exc:
        print(f"release destination guard failed: {exc}", file=sys.stderr)
        return 1
    print(state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
