from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from ...application.analysis_migration_service import AnalysisMigrationService
from ...application.mineru_image_migration_service import MinerUImageMigrationService
from ..agent_install import SUPPORTED_CLIENTS, install_agent
from ..common import resolve_vault
from ..mcp.server import run_server
from ..mcp.tools import TOOL_BY_NAME

_CONFLICT_POLICIES = ("preserve-user", "overwrite-managed", "fail", "rename")


class _UsageError(ValueError):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise _UsageError(message)


def _add_vault(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--vault-path", default="")


def _add_write_options(parser: argparse.ArgumentParser) -> None:
    _add_vault(parser)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--transaction-id", default="")
    parser.add_argument("--conflict-policy", choices=_CONFLICT_POLICIES, default="preserve-user")


def _add_migration_options(parser: argparse.ArgumentParser) -> None:
    _add_vault(parser)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--transaction-id", default="")
    parser.add_argument(
        "--conflict-policy",
        choices=("preserve-user",),
        default="preserve-user",
    )


def _tool(parser: argparse.ArgumentParser, name: str) -> None:
    parser.set_defaults(_handler="tool", _tool_name=name)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="obsidian-vault-mcp", description="Zotero + MinerU + Obsidian literature pipeline")
    commands = parser.add_subparsers(dest="command", required=True)

    doctor = commands.add_parser("doctor")
    _add_vault(doctor)
    _tool(doctor, "literature_doctor")

    config = commands.add_parser("config").add_subparsers(dest="config_command", required=True)
    config_get = config.add_parser("get")
    _add_vault(config_get)
    _tool(config_get, "literature_config_get")
    config_validate = config.add_parser("validate")
    _add_vault(config_validate)
    config_validate.add_argument("--json", dest="config_json", default="")
    _tool(config_validate, "literature_config_validate")
    config_init = config.add_parser("init")
    _add_write_options(config_init)
    _tool(config_init, "literature_config_initialize")

    import_commands = commands.add_parser("import").add_subparsers(dest="import_command", required=True)
    import_item = import_commands.add_parser("item")
    import_item.add_argument("zotero_key")
    _add_write_options(import_item)
    _tool(import_item, "literature_import_item")
    import_collection = import_commands.add_parser("collection")
    import_collection.add_argument("collection_key")
    _add_write_options(import_collection)
    _tool(import_collection, "literature_import_collection")

    sync_commands = commands.add_parser("sync").add_subparsers(dest="sync_command", required=True)
    sync_item = sync_commands.add_parser("item")
    sync_item.add_argument("zotero_key")
    _add_write_options(sync_item)
    _tool(sync_item, "literature_sync_item")
    sync_collection = sync_commands.add_parser("collection")
    sync_collection.add_argument("collection_key")
    _add_write_options(sync_collection)
    _tool(sync_collection, "literature_sync_collection")

    mineru = commands.add_parser("mineru").add_subparsers(dest="mineru_command", required=True)
    mineru_parse = mineru.add_parser("parse")
    mineru_parse.add_argument("zotero_key")
    _add_write_options(mineru_parse)
    _tool(mineru_parse, "literature_parse_mineru")
    mineru_batch = mineru.add_parser("parse-batch")
    mineru_batch.add_argument("zotero_keys", nargs="+")
    _add_write_options(mineru_batch)
    _tool(mineru_batch, "literature_parse_mineru_batch")
    mineru_remove = mineru.add_parser("remove")
    mineru_remove.add_argument("zotero_key")
    _add_write_options(mineru_remove)
    _tool(mineru_remove, "literature_remove_mineru_output")

    index_rebuild = commands.add_parser("index").add_subparsers(dest="index_command", required=True).add_parser("rebuild")
    _add_write_options(index_rebuild)
    _tool(index_rebuild, "literature_rebuild_index")
    base_rebuild = commands.add_parser("base").add_subparsers(dest="base_command", required=True).add_parser("rebuild")
    _add_write_options(base_rebuild)
    _tool(base_rebuild, "literature_rebuild_base")

    verify = commands.add_parser("verify")
    _add_vault(verify)
    _tool(verify, "literature_verify")

    wiki = commands.add_parser("wiki").add_subparsers(dest="wiki_command", required=True)
    wiki_context = wiki.add_parser("context")
    wiki_context.add_argument("topic")
    wiki_context.add_argument("--limit", type=int, default=20)
    _add_vault(wiki_context)
    _tool(wiki_context, "literature_wiki_context")
    wiki_write = wiki.add_parser("write")
    wiki_write.add_argument("topic")
    wiki_write.add_argument("--content", required=True)
    wiki_write.add_argument("--zotero-key", dest="zotero_keys", action="append", required=True)
    _add_write_options(wiki_write)
    _tool(wiki_write, "literature_wiki_write")
    wiki_list = wiki.add_parser("list")
    _add_vault(wiki_list)
    _tool(wiki_list, "literature_wiki_list")

    migrate = commands.add_parser("migrate").add_subparsers(dest="migrate_command", required=True)
    migrate_v2 = migrate.add_parser("v1-to-v2")
    _add_write_options(migrate_v2)
    migrate_v2.add_mutually_exclusive_group().add_argument("--apply", action="store_true")
    _tool(migrate_v2, "literature_migrate_v1_to_v2")
    migrate_analysis = migrate.add_parser("analysis-v2-to-v3")
    _add_migration_options(migrate_analysis)
    migrate_analysis.add_mutually_exclusive_group().add_argument("--apply", action="store_true")
    migrate_analysis.set_defaults(_handler="analysis-migrate")
    migrate_mineru_images = migrate.add_parser("mineru-images-v2-to-v3")
    _add_migration_options(migrate_mineru_images)
    migrate_mineru_images.add_mutually_exclusive_group().add_argument("--apply", action="store_true")
    migrate_mineru_images.add_argument(
        "--cleanup-legacy",
        action="store_true",
        help="delete legacy flat images in the same transaction",
    )
    migrate_mineru_images.add_argument(
        "--confirm-vault-offline",
        action="store_true",
        help="confirm every process capable of writing the Vault is stopped",
    )
    migrate_mineru_images.set_defaults(_handler="mineru-images-migrate")

    preview = commands.add_parser("preview")
    preview.add_argument("transaction_id")
    _add_vault(preview)
    _tool(preview, "literature_preview_transaction")

    rollback = commands.add_parser("rollback")
    rollback.add_argument("transaction_id")
    _add_vault(rollback)
    rollback.add_argument("--dry-run", action="store_true")
    rollback.add_argument("--conflict-policy", choices=_CONFLICT_POLICIES, default="preserve-user")
    _tool(rollback, "literature_rollback_transaction")

    call = commands.add_parser("call")
    call.add_argument("tool_name", choices=tuple(TOOL_BY_NAME))
    call.add_argument("--json", dest="arguments_json", default="{}")
    call.set_defaults(_handler="call")

    serve = commands.add_parser("serve")
    serve.add_argument("--transport", choices=("stdio", "sse", "streamable-http"), default="stdio")
    serve.set_defaults(_handler="serve")

    agent = commands.add_parser("agent").add_subparsers(dest="agent_command", required=True)
    install = agent.add_parser("install")
    install.add_argument("client", choices=SUPPORTED_CLIENTS)
    install.add_argument("--project-dir", type=Path, default=None)
    install.add_argument("--dry-run", action="store_true")
    install.set_defaults(_handler="agent-install")
    return parser


def _tool_arguments(namespace: argparse.Namespace) -> dict[str, Any]:
    excluded = {
        "command",
        "config_command",
        "import_command",
        "sync_command",
        "mineru_command",
        "index_command",
        "base_command",
        "wiki_command",
        "migrate_command",
        "_handler",
        "_tool_name",
        "apply",
    }
    values = {key: value for key, value in vars(namespace).items() if key not in excluded}
    if namespace._tool_name == "literature_migrate_v1_to_v2":
        if namespace.apply and namespace.dry_run:
            raise ValueError("--apply and --dry-run cannot be used together")
        values["dry_run"] = not namespace.apply
    return values


def _parse_call_arguments(raw: str) -> dict[str, Any]:
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("--json must contain a JSON object")
    return value


def _dispatch(namespace: argparse.Namespace) -> Any:
    if namespace._handler == "serve":
        run_server(namespace.transport)
        return None
    if namespace._handler == "call":
        return TOOL_BY_NAME[namespace.tool_name](**_parse_call_arguments(namespace.arguments_json))
    if namespace._handler == "agent-install":
        return install_agent(namespace.client, namespace.project_dir, dry_run=namespace.dry_run).as_dict()
    if namespace._handler == "analysis-migrate":
        if namespace.apply and namespace.dry_run:
            raise ValueError("--apply and --dry-run cannot be used together")
        return AnalysisMigrationService(resolve_vault(namespace.vault_path)).migrate(
            dry_run=not namespace.apply,
            apply=namespace.apply,
            transaction_id=namespace.transaction_id or None,
            conflict_policy=namespace.conflict_policy,
        )
    if namespace._handler == "mineru-images-migrate":
        if namespace.apply and namespace.dry_run:
            raise ValueError("--apply and --dry-run cannot be used together")
        return MinerUImageMigrationService(resolve_vault(namespace.vault_path)).migrate(
            dry_run=not namespace.apply,
            apply=namespace.apply,
            transaction_id=namespace.transaction_id or None,
            conflict_policy=namespace.conflict_policy,
            cleanup_legacy=namespace.cleanup_legacy,
            confirm_vault_offline=namespace.confirm_vault_offline,
        )
    if namespace._handler == "tool":
        return TOOL_BY_NAME[namespace._tool_name](**_tool_arguments(namespace))
    raise RuntimeError("no command handler selected")


def _emit(value: Any, *, stream: Any = None) -> None:
    target = sys.stdout if stream is None else stream
    try:
        print(json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str), file=target, flush=True)
    except UnicodeEncodeError:
        # Windows consoles commonly use a legacy code page. JSON escapes keep
        # the output lossless and machine-readable when that page cannot
        # represent a result character.
        print(json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str), file=target, flush=True)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the V3 CLI and emit one machine-readable JSON value."""

    try:
        namespace = build_parser().parse_args(argv)
        result = _dispatch(namespace)
        if namespace._handler != "serve":
            _emit(result)
        return 0
    except (KeyboardInterrupt, SystemExit):
        raise
    except Exception as exc:
        _emit({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
