from __future__ import annotations

from typing import Any

from ....application.analysis_base_service import AnalysisBaseService
from ....application.analysis_service import AnalysisService
from ....application.base_service import BaseService
from ....application.config_service import ConfigService
from ....application.doctor_service import DoctorService
from ....application.import_service import ImportService
from ....application.index_service import IndexService
from ....application.mineru_service import MinerUService
from ....application.paper_read_service import PaperReadService
from ....application.retrieval_service import RetrievalService
from ....application.sync_service import SyncService
from ....application.transaction_service import TransactionService
from ....application.zotero_service import ZoteroQueryService
from ...common import resolve_vault


def literature_doctor(vault_path: str = "") -> dict[str, Any]:
    """Check Vault configuration, Zotero status, MinerU availability, and the exposed tool list."""
    return DoctorService(resolve_vault(vault_path)).run(tool_names=[function.__name__ for function in TOOL_FUNCTIONS])


def literature_config_get(vault_path: str = "") -> dict[str, Any]:
    """Return the validated effective Vault configuration."""
    return ConfigService(resolve_vault(vault_path)).get()


def literature_config_validate(config_json: str = "", vault_path: str = "") -> dict[str, Any]:
    """Validate supplied JSON or the Vault's single configuration file."""
    return ConfigService(resolve_vault(vault_path)).validate(config_json or None)


def literature_config_initialize(
    vault_path: str = "",
    dry_run: bool = False,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Create the one Vault configuration through the transaction engine."""
    return ConfigService(resolve_vault(vault_path)).initialize(
        dry_run=dry_run,
        transaction_id=transaction_id or None,
        conflict_policy=conflict_policy,
    )


def zotero_ping(api_base: str = "") -> dict[str, Any]:
    """Check the Zotero Desktop local API."""
    return ZoteroQueryService(api_base).ping()


def zotero_search_items(
    query: str = "",
    item_type: str = "",
    tag: str = "",
    api_base: str = "",
) -> list[dict[str, Any]]:
    """Search all matching Zotero items using complete pagination."""
    return ZoteroQueryService(api_base).search_items(query=query, item_type=item_type, tag=tag)


def zotero_list_collections(api_base: str = "") -> list[dict[str, Any]]:
    """List every Zotero collection using complete pagination."""
    return ZoteroQueryService(api_base).list_collections()


def zotero_get_item(key: str, api_base: str = "") -> dict[str, Any]:
    """Get one normalized Zotero item."""
    return ZoteroQueryService(api_base).get_item(key)


def zotero_get_children(parent_key: str, api_base: str = "") -> dict[str, Any]:
    """Get all notes, annotations, attachments, and other child items."""
    return ZoteroQueryService(api_base).get_children(parent_key)


def zotero_get_bibtex(key: str, api_base: str = "", provider: str = "auto") -> dict[str, Any]:
    """Get BibTeX using Better BibTeX, Zotero export, then builtin fallback."""
    return ZoteroQueryService(api_base).get_bibtex(key, provider=provider)


def literature_import_item(
    zotero_key: str,
    vault_path: str = "",
    dry_run: bool = False,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Import or idempotently refresh one Zotero parent item."""
    return ImportService(resolve_vault(vault_path)).import_item(
        zotero_key, dry_run=dry_run, transaction_id=transaction_id or None, conflict_policy=conflict_policy
    )


def literature_import_collection(
    collection_key: str,
    vault_path: str = "",
    dry_run: bool = False,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Import every parent item in a fully paginated Zotero collection."""
    return ImportService(resolve_vault(vault_path)).import_collection(
        collection_key, dry_run=dry_run, transaction_id=transaction_id or None, conflict_policy=conflict_policy
    )


def literature_sync_item(
    zotero_key: str,
    vault_path: str = "",
    dry_run: bool = False,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Incrementally sync an existing literature item."""
    return SyncService(resolve_vault(vault_path)).sync_item(
        zotero_key, dry_run=dry_run, transaction_id=transaction_id or None, conflict_policy=conflict_policy
    )


def literature_sync_collection(
    collection_key: str,
    vault_path: str = "",
    dry_run: bool = False,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Incrementally sync existing items from a fully paginated collection."""
    return SyncService(resolve_vault(vault_path)).sync_collection(
        collection_key, dry_run=dry_run, transaction_id=transaction_id or None, conflict_policy=conflict_policy
    )


def literature_parse_mineru(
    zotero_key: str,
    vault_path: str = "",
    dry_run: bool = False,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Parse one Vault PDF through staged MinerU normalization."""
    return MinerUService(resolve_vault(vault_path)).parse(
        zotero_key, dry_run=dry_run, transaction_id=transaction_id or None, conflict_policy=conflict_policy
    )


def literature_parse_mineru_batch(
    zotero_keys: list[str],
    vault_path: str = "",
    dry_run: bool = False,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Parse several imported items with the configured concurrency limit."""
    return MinerUService(resolve_vault(vault_path)).parse_batch(
        zotero_keys, dry_run=dry_run, transaction_id=transaction_id or None, conflict_policy=conflict_policy
    )


def literature_remove_mineru_output(
    zotero_key: str,
    vault_path: str = "",
    dry_run: bool = False,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Remove derived MinerU assets through a backed-up transaction."""
    return MinerUService(resolve_vault(vault_path)).remove_output(
        zotero_key, dry_run=dry_run, transaction_id=transaction_id or None, conflict_policy=conflict_policy
    )


def literature_rebuild_index(
    vault_path: str = "",
    dry_run: bool = False,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Deterministically rebuild Literature/index.md."""
    return IndexService(resolve_vault(vault_path)).rebuild(
        dry_run=dry_run, transaction_id=transaction_id or None, conflict_policy=conflict_policy
    )


def literature_rebuild_base(
    vault_path: str = "",
    dry_run: bool = False,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Deterministically rebuild Literature/Literature.base."""
    return BaseService(resolve_vault(vault_path)).rebuild(
        dry_run=dry_run, transaction_id=transaction_id or None, conflict_policy=conflict_policy
    )


def literature_verify(vault_path: str = "") -> dict[str, Any]:
    """Verify identities, links, portable paths, and generated assets."""
    from ....application.verify_service import VerifyService

    return VerifyService(resolve_vault(vault_path)).verify()


def literature_paper_read(
    zotero_key: str,
    vault_path: str = "",
    mode: str = "overview",
    query: str = "",
    query_variants: list[str] | None = None,
    sections: list[str] | None = None,
    max_chars: int = 12_000,
    top_k: int = 8,
    include_images: bool = False,
) -> dict[str, Any]:
    """Read bounded, source-linked text or figures from one paper without persisting derived state."""
    return PaperReadService(resolve_vault(vault_path)).read(
        zotero_key,
        mode=mode,
        query=query,
        query_variants=query_variants or (),
        sections=sections or (),
        max_chars=max_chars,
        top_k=top_k,
        include_images=include_images,
    )


def literature_retrieve(
    query: str = "",
    vault_path: str = "",
    query_variants: list[str] | None = None,
    scope: dict[str, Any] | None = None,
    intent: str = "summarize",
    depth: str = "evidence",
    methods: list[str] | None = None,
    max_candidate_papers: int = 30,
    max_snippet_papers: int = 15,
    per_paper_top_k: int = 3,
    max_total_snippets: int = 40,
) -> dict[str, Any]:
    """Retrieve bounded paper matches and source passages with request-local coverage only."""
    return RetrievalService(resolve_vault(vault_path)).retrieve(
        query,
        query_variants=query_variants,
        scope=scope,
        intent=intent,
        depth=depth,
        methods=methods,
        max_candidate_papers=max_candidate_papers,
        max_snippet_papers=max_snippet_papers,
        per_paper_top_k=per_paper_top_k,
        max_total_snippets=max_total_snippets,
    )


def literature_analysis_get(
    vault_path: str = "",
    analysis_id: str = "",
    analysis_type: str = "",
    source_key: str = "",
    question: str = "",
) -> dict[str, Any]:
    """Get Analysis notes by stable ID, type, source key, or duplicate-question lookup."""
    return AnalysisService(resolve_vault(vault_path)).get(
        analysis_id=analysis_id or None,
        analysis_type=analysis_type or None,
        source_key=source_key or None,
        question=question or None,
    )


def literature_analysis_write(
    fields: dict[str, Any],
    managed_content: str,
    vault_path: str = "",
    dry_run: bool = False,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
    reviewed_by_user: bool = False,
) -> dict[str, Any]:
    """Validate and transactionally write one Analysis note while preserving user-owned content."""
    return AnalysisService(resolve_vault(vault_path)).write(
        fields,
        managed_content,
        dry_run=dry_run,
        transaction_id=transaction_id or None,
        conflict_policy=conflict_policy,
        reviewed_by_user=reviewed_by_user,
    )


def literature_rebuild_analysis_base(
    vault_path: str = "",
    dry_run: bool = False,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Create or upgrade the single nine-view Literature/Analysis/Analysis.base file."""
    return AnalysisBaseService(resolve_vault(vault_path)).rebuild(
        dry_run=dry_run,
        transaction_id=transaction_id or None,
        conflict_policy=conflict_policy,
    )


def literature_wiki_context(topic: str, vault_path: str = "", limit: int = 20) -> dict[str, Any]:
    """Collect traceable local literature context for an Agent-authored topic."""
    from ....application.wiki_service import WikiService

    return WikiService(resolve_vault(vault_path)).context(topic, limit=limit)


def literature_wiki_write(
    topic: str,
    content: str,
    zotero_keys: list[str],
    vault_path: str = "",
    dry_run: bool = False,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Validate sources and safely write an Agent-authored Wiki topic."""
    from ....application.wiki_service import WikiService

    return WikiService(resolve_vault(vault_path)).write(
        topic,
        content,
        zotero_keys,
        dry_run=dry_run,
        transaction_id=transaction_id or None,
        conflict_policy=conflict_policy,
    )


def literature_wiki_list(vault_path: str = "") -> dict[str, Any]:
    """List deterministic Wiki topic metadata."""
    from ....application.wiki_service import WikiService

    return {"ok": True, "topics": WikiService(resolve_vault(vault_path)).list()}


def literature_migrate_v1_to_v2(
    vault_path: str = "",
    dry_run: bool = True,
    transaction_id: str = "",
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Plan or apply the complete V1 to V2 migration."""
    from ....application.migration_service import MigrationService

    return MigrationService(resolve_vault(vault_path)).migrate(
        dry_run=dry_run,
        apply=not dry_run,
        transaction_id=transaction_id or None,
        conflict_policy=conflict_policy,
    )


def literature_preview_transaction(transaction_id: str, vault_path: str = "") -> dict[str, Any]:
    """Read the safe manifest for an existing committed transaction."""
    return TransactionService(resolve_vault(vault_path)).preview_committed(transaction_id)


def literature_rollback_transaction(
    transaction_id: str,
    vault_path: str = "",
    dry_run: bool = False,
    conflict_policy: str = "preserve-user",
) -> dict[str, Any]:
    """Preview or restore every file backed up by a transaction."""
    return TransactionService(resolve_vault(vault_path)).rollback(
        transaction_id,
        dry_run=dry_run,
        conflict_policy=conflict_policy,
    )


TOOL_FUNCTIONS = (
    literature_doctor,
    literature_config_get,
    literature_config_validate,
    literature_config_initialize,
    zotero_ping,
    zotero_search_items,
    zotero_list_collections,
    zotero_get_item,
    zotero_get_children,
    zotero_get_bibtex,
    literature_import_item,
    literature_import_collection,
    literature_sync_item,
    literature_sync_collection,
    literature_parse_mineru,
    literature_parse_mineru_batch,
    literature_remove_mineru_output,
    literature_rebuild_index,
    literature_rebuild_base,
    literature_verify,
    literature_paper_read,
    literature_retrieve,
    literature_analysis_get,
    literature_analysis_write,
    literature_rebuild_analysis_base,
    literature_wiki_context,
    literature_wiki_write,
    literature_wiki_list,
    literature_migrate_v1_to_v2,
    literature_preview_transaction,
    literature_rollback_transaction,
)

TOOL_BY_NAME = {function.__name__: function for function in TOOL_FUNCTIONS}
