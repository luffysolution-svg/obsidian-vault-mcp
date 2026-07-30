"""Deterministic Obsidian Bases renderer for all V3 Analysis notes."""

from __future__ import annotations

from typing import Any

import yaml

ANALYSIS_BASE_TEMPLATE_VERSION = 1

_COMMON_COLUMNS = [
    "title",
    "analysisType",
    "analysisProfile",
    "status",
    "primarySource",
    "sourceCount",
    "summary",
    "updatedAt",
    "tags",
]


def analysis_base_document(
    analysis_folder: str = "Literature/Analysis",
) -> dict[str, Any]:
    """Return the single recursive Base contract for the Analysis tree."""

    folder = analysis_folder.replace("\\", "/").strip("/")
    if not folder or folder.startswith(".") or "/../" in f"/{folder}/":
        raise ValueError("analysis_folder must be a safe Vault-relative folder")

    properties = {
        "title": {"displayName": "Title"},
        "analysisType": {"displayName": "Type"},
        "analysisProfile": {"displayName": "Profile"},
        "status": {"displayName": "Status"},
        "primarySource": {"displayName": "Primary Source"},
        "sourceCount": {"displayName": "Source Count"},
        "summary": {"displayName": "Summary"},
        "updatedAt": {"displayName": "Updated"},
        "tags": {"displayName": "Tags"},
        "paperTitle": {"displayName": "Paper"},
        "year": {"displayName": "Year"},
        "journal": {"displayName": "Journal"},
        "paperKind": {"displayName": "Paper Kind"},
        "researchQuestion": {"displayName": "Research Question"},
        "coreContribution": {"displayName": "Contribution"},
        "methodSummary": {"displayName": "Method"},
        "mainFinding": {"displayName": "Main Finding"},
        "limitationSummary": {"displayName": "Limitation"},
        "reviewMode": {"displayName": "Review Mode"},
        "reviewQuestion": {"displayName": "Review Question"},
        "scopeSummary": {"displayName": "Scope"},
        "timeRange": {"displayName": "Time Range"},
        "taxonomySummary": {"displayName": "Taxonomy"},
        "consensusSummary": {"displayName": "Consensus"},
        "controversySummary": {"displayName": "Controversy"},
        "gapSummary": {"displayName": "Gap"},
        "conclusionSummary": {"displayName": "Conclusion"},
        "question": {"displayName": "Question"},
        "sourceSection": {"displayName": "Section"},
        "sourceSubsection": {"displayName": "Subsection"},
        "sourceParagraph": {"displayName": "Paragraph"},
        "answerSummary": {"displayName": "Answer"},
        "locatorQuality": {"displayName": "Locator Quality"},
        "targetType": {"displayName": "Target Type"},
        "targetLabel": {"displayName": "Target Label"},
        "targetPanel": {"displayName": "Panel"},
        "page": {"displayName": "Page"},
        "imageExists": {"displayName": "Image Exists"},
        "visualMode": {"displayName": "Visual Mode"},
        "conceptName": {"displayName": "Concept"},
        "conceptKind": {"displayName": "Kind"},
        "definitionSummary": {"displayName": "Definition"},
        "relationSummary": {"displayName": "Relations"},
        "useSummary": {"displayName": "Use"},
    }
    return {
        "filters": {
            "and": [
                f'file.inFolder("{folder}")',
                "analysisId != null",
            ]
        },
        "properties": properties,
        "views": [
            {
                "type": "table",
                "name": "Dashboard",
                "filters": {"and": ['status != "archived"']},
                "order": list(_COMMON_COLUMNS),
            },
            {
                "type": "table",
                "name": "Full Reads",
                "filters": {"and": ['analysisType == "full_read"']},
                "order": [
                    "paperTitle",
                    "year",
                    "journal",
                    "paperKind",
                    "analysisProfile",
                    "researchQuestion",
                    "coreContribution",
                    "methodSummary",
                    "mainFinding",
                    "limitationSummary",
                    "status",
                    "updatedAt",
                ],
            },
            {
                "type": "table",
                "name": "Reviews",
                "filters": {"and": ['analysisType == "literature_review"']},
                "order": [
                    "title",
                    "reviewMode",
                    "analysisProfile",
                    "reviewQuestion",
                    "scopeSummary",
                    "timeRange",
                    "sourceCount",
                    "taxonomySummary",
                    "consensusSummary",
                    "controversySummary",
                    "gapSummary",
                    "conclusionSummary",
                    "status",
                    "updatedAt",
                ],
            },
            {
                "type": "table",
                "name": "Passage Q&A",
                "filters": {"and": ['analysisType == "passage_qa"']},
                "order": [
                    "question",
                    "primarySource",
                    "sourceSection",
                    "sourceSubsection",
                    "sourceParagraph",
                    "answerSummary",
                    "locatorQuality",
                    "status",
                    "updatedAt",
                ],
            },
            {
                "type": "table",
                "name": "Figure Q&A",
                "filters": {"and": ['analysisType == "figure_qa"']},
                "order": [
                    "question",
                    "primarySource",
                    "targetType",
                    "targetLabel",
                    "targetPanel",
                    "page",
                    "imageExists",
                    "visualMode",
                    "answerSummary",
                    "status",
                    "updatedAt",
                ],
            },
            {
                "type": "table",
                "name": "Concepts",
                "filters": {"and": ['analysisType == "concept"']},
                "order": [
                    "conceptName",
                    "conceptKind",
                    "analysisProfile",
                    "definitionSummary",
                    "relationSummary",
                    "useSummary",
                    "sourceCount",
                    "status",
                    "updatedAt",
                ],
            },
            {
                "type": "table",
                "name": "Needs Attention",
                "filters": {
                    "or": [
                        'status == "draft"',
                        'status == "ready"',
                        'status == "needs_update"',
                    ]
                },
                "order": [
                    "title",
                    "analysisType",
                    "analysisProfile",
                    "status",
                    "primarySource",
                    "summary",
                    "updatedAt",
                ],
            },
            {
                "type": "table",
                "name": "By Discipline",
                "groupBy": {"property": "analysisProfile", "direction": "ASC"},
                "order": list(_COMMON_COLUMNS),
            },
            {
                "type": "table",
                "name": "Recently Updated",
                "sort": [{"property": "updatedAt", "direction": "DESC"}],
                "order": list(_COMMON_COLUMNS),
            },
        ],
    }


def render_analysis_base(
    analysis_folder: str = "Literature/Analysis",
) -> str:
    """Render the complete Analysis Base as deterministic YAML."""

    return yaml.safe_dump(
        analysis_base_document(analysis_folder),
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=1000,
    )
