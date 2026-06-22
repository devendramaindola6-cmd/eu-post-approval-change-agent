"""
regulation_tools.py - Tool primitives for the regulatory agent workflow
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Dict, List, Sequence, Tuple

import pandas as pd

from llm_utils import rank_reference_rows
from main import get_required_documents, suggest_process


def workbook_search_tool(description: str, reference_df: pd.DataFrame, limit: int = 3) -> List[Tuple[pd.Series, float]]:
    return rank_reference_rows(description, reference_df, limit=limit)


def ambiguity_assessor_tool(top_matches: Sequence[Tuple[pd.Series, float]]) -> Dict[str, Any]:
    if not top_matches:
        return {"confidence": "low", "needs_clarification": True, "score_gap": 0.0}

    top_score = float(top_matches[0][1])
    second_score = float(top_matches[1][1]) if len(top_matches) > 1 else 0.0
    gap = top_score - second_score

    if top_score >= 10 and gap >= 4:
        confidence = "high"
    elif top_score >= 5 and gap >= 1.5:
        confidence = "medium"
    else:
        confidence = "low"

    return {
        "confidence": confidence,
        "needs_clarification": confidence == "low",
        "score_gap": gap,
    }


def clarification_tool(top_matches: Sequence[Tuple[pd.Series, float]]) -> List[str]:
    if len(top_matches) < 2:
        return []

    top_row, _ = top_matches[0]
    second_row, _ = top_matches[1]
    questions: List[str] = []

    if str(top_row.get("procedure_type", "")) != str(second_row.get("procedure_type", "")):
        questions.append(
            f"Which filing pathway fits better: `{top_row.get('procedure_type', 'N/A')}` or `{second_row.get('procedure_type', 'N/A')}`?"
        )

    if str(top_row.get("change_item", "")) != str(second_row.get("change_item", "")):
        questions.append(
            f"Which scenario is closer: `{top_row.get('change_item', 'N/A')}` or `{second_row.get('change_item', 'N/A')}`?"
        )

    if str(top_row.get("change_scenario", "")) != str(second_row.get("change_scenario", "")):
        questions.append("Are all mandatory conditions satisfied, or does the request involve an exception/special case?")

    return questions[:3]


def evidence_synthesis_tool(classification: Dict[str, Any], top_matches: Sequence[Tuple[pd.Series, float]]) -> Dict[str, Any]:
    top_candidates = [
        {
            "reference_id": row.get("reference_id", ""),
            "change_type": row.get("change_type", ""),
            "description": row.get("change_item", ""),
            "procedure_type": row.get("procedure_type", ""),
            "change_scenario": row.get("change_scenario", ""),
            "score": float(score),
        }
        for row, score in top_matches
    ]
    return {
        "evidence_summary": (
            f"Best workbook match: {classification.get('description', 'N/A')} | "
            f"Procedure: {classification.get('procedure_type', 'N/A')} | "
            f"Scenario: {classification.get('change_scenario', 'N/A')}"
        ),
        "top_matches": top_candidates,
    }


def risk_assessor_tool(classification: Dict[str, Any]) -> Dict[str, str]:
    procedure_type = str(classification.get("procedure_type", "")).upper()
    category = str(classification.get("category", "")).lower()

    if (
        "TYPE II" in procedure_type
        or "extension" in procedure_type.lower()
        or "CATEGORY 3" in procedure_type
        or "SUPPLEMENT" in procedure_type
    ):
        risk_level = "high"
        rationale = "This pathway usually requires a fuller regulatory assessment before implementation."
    elif "TYPE IB" in procedure_type:
        risk_level = "medium"
        rationale = "This pathway generally needs authority notification and review before implementation."
    elif "low" in category or "TYPE IA" in procedure_type:
        risk_level = "low"
        rationale = "This looks like a lower-impact variation, but the stated conditions still need validation."
    else:
        risk_level = "medium"
        rationale = "The pathway is not fully explicit, so manual regulatory review remains important."

    return {"risk_level": risk_level, "risk_rationale": rationale}


def action_plan_tool(classification: Dict[str, Any]) -> List[str]:
    documents = get_required_documents(classification)
    plan = [
        "Review the matched workbook entry and confirm that the described change truly fits the selected scenario.",
        "Check every listed condition before locking the filing pathway.",
        f"Prepare the submission as `{classification.get('procedure_type', 'manual review')}` and confirm the cited filing description.",
    ]
    if documents:
        plan.append(f"Collect the document package: {', '.join(documents[:3])}.")
    plan.append(suggest_process(classification))
    plan.append("Escalate to a regulatory expert if the wording or conditions do not align cleanly with the real change.")
    return plan


@lru_cache(maxsize=1)
def _load_pdf_pages(pdf_path: str) -> List[str]:
    from PyPDF2 import PdfReader

    reader = PdfReader(pdf_path)
    pages: List[str] = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return pages


def pdf_evidence_tool(query: str, pdf_path: str, limit: int = 2) -> List[Dict[str, Any]]:
    pages = _load_pdf_pages(pdf_path)
    query_tokens = [token for token in re.findall(r"[a-z0-9]+", query.lower()) if len(token) > 2]
    if not query_tokens:
        return []

    scored_pages: List[Tuple[int, int, str]] = []
    for page_number, page_text in enumerate(pages, start=1):
        lower_text = page_text.lower()
        score = sum(lower_text.count(token) for token in query_tokens)
        if score:
            snippet_start = min((lower_text.find(token) for token in query_tokens if token in lower_text), default=0)
            snippet = page_text[max(0, snippet_start - 140): snippet_start + 280].replace("\n", " ").strip()
            scored_pages.append((page_number, score, snippet))

    scored_pages.sort(key=lambda item: item[1], reverse=True)
    return [
        {"page": page_number, "score": score, "snippet": snippet}
        for page_number, score, snippet in scored_pages[:limit]
    ]
