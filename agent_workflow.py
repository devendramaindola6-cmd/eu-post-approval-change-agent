"""
agent_workflow.py - Agent planner/executor for post-approval change analysis
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from llm_utils import classify_reference_row, llm_classify_change
from main import get_required_documents, suggest_process
from regulation_tools import (
    action_plan_tool,
    ambiguity_assessor_tool,
    clarification_tool,
    evidence_synthesis_tool,
    pdf_evidence_tool,
    risk_assessor_tool,
    workbook_search_tool,
)
from upload_review import review_uploaded_document


@dataclass
class AgentState:
    description: str
    reference_df: pd.DataFrame
    vectorstore: Any = None
    pdf_path: Optional[str] = None
    tool_trace: List[Dict[str, Any]] = field(default_factory=list)
    workflow_steps: List[str] = field(default_factory=list)
    top_matches: Sequence[Tuple[pd.Series, float]] = field(default_factory=list)
    classification: Dict[str, Any] = field(default_factory=dict)
    confidence: str = "low"
    needs_clarification: bool = False
    clarification_questions: List[str] = field(default_factory=list)
    action_plan: List[str] = field(default_factory=list)
    risk_level: str = "unknown"
    risk_rationale: str = ""
    pdf_evidence: List[Dict[str, Any]] = field(default_factory=list)
    uploaded_document_review: Optional[Dict[str, Any]] = None
    uploaded_document: Optional[Dict[str, str]] = None
    selected_reference_id: Optional[str] = None
    user_decisions: Dict[str, str] = field(default_factory=dict)


def _log_tool(state: AgentState, tool_name: str, summary: str) -> None:
    state.tool_trace.append({"tool": tool_name, "summary": summary})


def _planner_next_step(state: AgentState) -> Optional[str]:
    if state.selected_reference_id and not state.classification:
        return "guided_classify"
    if not state.top_matches:
        return "workbook_search"
    if not state.classification:
        return "classify"
    if state.confidence == "low" and not state.clarification_questions:
        return "clarify"
    if state.risk_level == "unknown":
        return "risk_assess"
    if not state.action_plan:
        return "action_plan"
    if state.pdf_path and not state.pdf_evidence:
        return "pdf_evidence"
    if state.classification and state.uploaded_document_review is None and state.uploaded_document:
        return "upload_review"
    return None


def _execute_step(state: AgentState, step: str) -> None:
    if step == "guided_classify":
        state.classification = classify_reference_row(str(state.selected_reference_id), state.reference_df)
        if "error" in state.classification:
            _log_tool(state, "guided_classify", "The selected workbook reference could not be found.")
            state.workflow_steps.append("Guided decision tree could not resolve the selected reference.")
            return

        row = state.reference_df[
            state.reference_df["reference_id"].astype(str) == str(state.selected_reference_id)
        ].iloc[0]
        state.top_matches = [(row, 100.0)]
        evidence = evidence_synthesis_tool(state.classification, state.top_matches)
        state.classification.update(evidence)
        state.classification["required_documents_list"] = get_required_documents(state.classification)
        state.classification["recommended_process"] = suggest_process(state.classification)
        state.confidence = "high"
        state.needs_clarification = False
        state.classification["confidence"] = state.confidence
        state.classification["needs_clarification"] = state.needs_clarification
        state.classification["guided_decisions"] = dict(state.user_decisions)
        _log_tool(
            state,
            "guided_classify",
            f"User-guided decision tree selected reference `{state.selected_reference_id}`.",
        )
        state.workflow_steps.append("Guided decision tree narrowed the workbook to a selected filing scenario.")
        return

    if step == "workbook_search":
        state.top_matches = workbook_search_tool(state.description, state.reference_df, limit=3)
        _log_tool(state, "workbook_search", f"Found {len(state.top_matches)} top workbook candidates.")
        state.workflow_steps.append("Planner selected workbook retrieval as the primary decision source.")
        return

    if step == "classify":
        state.classification = llm_classify_change(state.description, state.vectorstore, state.reference_df)
        if "error" in state.classification:
            _log_tool(state, "classify", "Classification failed to find a reliable workbook match.")
            state.workflow_steps.append("Decision step could not identify a sufficiently reliable match.")
            return

        ambiguity = ambiguity_assessor_tool(state.top_matches)
        evidence = evidence_synthesis_tool(state.classification, state.top_matches)
        state.classification.update(evidence)
        state.classification["required_documents_list"] = get_required_documents(state.classification)
        state.classification["recommended_process"] = suggest_process(state.classification)
        state.confidence = ambiguity["confidence"]
        state.needs_clarification = ambiguity["needs_clarification"]
        state.classification["confidence"] = state.confidence
        state.classification["needs_clarification"] = state.needs_clarification
        _log_tool(
            state,
            "classify",
            f"Selected reference `{state.classification.get('reference_id', 'N/A')}` with {state.classification.get('match_method', 'keyword')} matching.",
        )
        state.workflow_steps.append("Decision step selected the strongest candidate and assembled workbook evidence.")
        return

    if step == "clarify":
        state.clarification_questions = clarification_tool(state.top_matches)
        state.classification["clarification_questions"] = state.clarification_questions
        _log_tool(state, "clarify", f"Prepared {len(state.clarification_questions)} clarification prompts.")
        state.workflow_steps.append("Ambiguity assessor flagged the request and requested clarifying details before final sign-off.")
        return

    if step == "risk_assess":
        risk = risk_assessor_tool(state.classification)
        state.risk_level = risk["risk_level"]
        state.risk_rationale = risk["risk_rationale"]
        state.classification.update(risk)
        _log_tool(state, "risk_assess", f"Assigned {state.risk_level} regulatory risk.")
        state.workflow_steps.append("Risk assessment estimated the regulatory review intensity for the matched pathway.")
        return

    if step == "action_plan":
        state.action_plan = action_plan_tool(state.classification)
        state.classification["action_plan"] = state.action_plan
        _log_tool(state, "action_plan", f"Built {len(state.action_plan)} action steps.")
        state.workflow_steps.append("Planning step translated the match into a practical filing and review checklist.")
        return

    if step == "pdf_evidence":
        query = " ".join(
            filter(
                None,
                [
                    state.classification.get("procedure_type", ""),
                    state.classification.get("description", ""),
                    state.description,
                ],
            )
        )
        state.pdf_evidence = pdf_evidence_tool(query, state.pdf_path, limit=2)
        state.classification["pdf_evidence"] = state.pdf_evidence
        _log_tool(state, "pdf_evidence", f"Collected {len(state.pdf_evidence)} supporting PDF snippets.")
        state.workflow_steps.append("Evidence synthesis searched the PDF guideline for supporting snippets related to the selected pathway.")
        return

    if step == "upload_review":
        upload_payload = state.uploaded_document or {}
        state.uploaded_document_review = review_uploaded_document(
            upload_payload.get("name", "uploaded file"),
            upload_payload.get("text", ""),
            state.classification,
        )
        state.classification["uploaded_document_review"] = state.uploaded_document_review
        _log_tool(state, "upload_review", "Reviewed the uploaded file against the matched scenario and required document list.")
        state.workflow_steps.append("Upload review compared the provided document contents against the matched filing scenario and expected support package.")
        return


def orchestrate_change_analysis(
    description: str,
    reference_df: pd.DataFrame,
    vectorstore=None,
    pdf_path: Optional[str] = None,
    uploaded_document: Optional[Dict[str, str]] = None,
    selected_reference_id: Optional[str] = None,
    user_decisions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    state = AgentState(
        description=description,
        reference_df=reference_df,
        vectorstore=vectorstore,
        pdf_path=pdf_path,
        uploaded_document=uploaded_document,
        selected_reference_id=selected_reference_id,
        user_decisions=user_decisions or {},
    )

    for _ in range(7):
        step = _planner_next_step(state)
        if step is None:
            break
        _execute_step(state, step)
        if "error" in state.classification:
            break

    if not state.classification or "error" in state.classification:
        return {
            "error": "No close match found. Manual review needed.",
            "workflow_steps": state.workflow_steps or [
                "Planner attempted workbook retrieval.",
                "No sufficiently reliable match was identified.",
                "Escalate for manual review.",
            ],
            "tool_trace": state.tool_trace,
        }

    result = dict(state.classification)
    result["workflow_steps"] = state.workflow_steps
    result["tool_trace"] = state.tool_trace
    result["confidence"] = state.confidence
    result["needs_clarification"] = state.needs_clarification
    result["clarification_questions"] = state.clarification_questions
    result["top_matches"] = result.get("top_matches", [])
    result["risk_level"] = state.risk_level
    result["risk_rationale"] = state.risk_rationale
    result["action_plan"] = state.action_plan
    result["pdf_evidence"] = state.pdf_evidence
    result["uploaded_document_review"] = state.uploaded_document_review
    result["agent_summary"] = (
        f"The agent selected `{result.get('description', 'N/A')}` as the best-fit scenario, "
        f"assigned `{result.get('procedure_type', 'N/A')}` as the pathway, and marked confidence as `{state.confidence}`."
    )
    return result
