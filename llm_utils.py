"""
llm_utils.py - Excel normalization and semantic matching helpers
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

EXCEL_HEADER_ROW = 1

SOURCE_TO_NORMALIZED_COLUMNS = {
    "Product Type": "product_type",
    "Material Type": "material_type",
    "Change Type": "change_type",
    "Change Item": "change_item",
    "Pharmaceutical Dosage Form (No Abbreviations, Full Form Only)": "dosage_form",
    "Drug Release Mechanism": "drug_release_mechanism",
    "Market": "market",
    "Change Scenario": "change_scenario",
    "Health Authority Change Conditions (Write conditions only. If there are more than one, create a List like this: 1. <condition text> 2. <condition text>": "conditions",
    "Data Source - Filing Requirements": "filing_data_source",
    "Filing Required?": "filing_required",
    "Health Authority Submission Type (Filing Type)": "procedure_type",
    "Filing Description (Write the ppplicable section No. of respective guideline - e.g. Q.1.a.1 from EU Guideline, add other Info if required.) ": "filing_description",
    "Change Classification": "change_category",
    "Additional Details - Filing Requirements (Subjective/ Free Text Remark)": "filing_notes",
    "Data Source - Documentation Requirements+O2:R2": "documentation_data_source",
    "Are there any documents need to be submitted to Health Authority for filing this Post Approval Change?": "documents_required_flag",
    "List the documents that need to be submitted for filing this Post Approval Change": "documents",
    "Additional Details - Documentation Requirements": "documentation_notes",
}

REQUIRED_NORMALIZED_COLUMNS = {
    "change_type",
    "change_item",
    "conditions",
    "procedure_type",
    "documents",
    "filing_description",
    "change_category",
}

SEARCH_FIELDS = (
    "product_type",
    "material_type",
    "change_type",
    "change_item",
    "conditions",
    "procedure_type",
    "filing_description",
    "documents",
)

STOPWORDS = {
    "a",
    "an",
    "and",
    "after",
    "all",
    "any",
    "are",
    "authorised",
    "be",
    "by",
    "for",
    "in",
    "is",
    "it",
    "its",
    "need",
    "of",
    "or",
    "the",
    "to",
    "we",
    "while",
    "with",
}


def load_reference_table(path: str) -> pd.DataFrame:
    df = pd.read_excel(path, header=EXCEL_HEADER_ROW)
    df = df.dropna(axis=1, how="all")
    df = df.rename(columns=SOURCE_TO_NORMALIZED_COLUMNS)

    missing = sorted(REQUIRED_NORMALIZED_COLUMNS.difference(df.columns))
    if missing:
        missing_str = ", ".join(missing)
        raise ValueError(f"Workbook is missing required normalized columns: {missing_str}")

    df = df.dropna(subset=["change_item"]).copy()
    df = df.reset_index(drop=True)
    df["reference_id"] = df.index.astype(str)
    df["search_text"] = df.apply(_build_search_text, axis=1)
    return df


def _build_search_text(row: pd.Series) -> str:
    parts: List[str] = []
    for key in SEARCH_FIELDS:
        value = row.get(key, "")
        if pd.notna(value) and str(value).strip():
            parts.append(str(value).strip())
    return "\n".join(parts)


def _build_classification_payload(row: pd.Series) -> Dict[str, str]:
    return {
        "reference_id": row.get("reference_id", ""),
        "category": row.get("change_category", ""),
        "change_type": row.get("change_type", ""),
        "description": row.get("change_item", ""),
        "conditions": row.get("conditions", ""),
        "documents": row.get("documents", ""),
        "procedure_type": row.get("procedure_type", ""),
        "filing_required": row.get("filing_required", ""),
        "filing_description": row.get("filing_description", ""),
        "market": row.get("market", ""),
        "change_scenario": row.get("change_scenario", ""),
    }


def classify_reference_row(reference_id: str, df: pd.DataFrame) -> Dict[str, str]:
    matches = df[df["reference_id"].astype(str) == str(reference_id)]
    if matches.empty:
        return {"error": "Selected workbook reference was not found. Manual review needed."}

    result = _build_classification_payload(matches.iloc[0])
    result["match_score"] = 100.0
    result["match_method"] = "guided_decision_tree"
    return result


def build_vectorstore_from_excel(path: str):
    df = load_reference_table(path)
    texts = df["search_text"].fillna("").tolist()
    metadatas = [{"reference_id": ref_id} for ref_id in df["reference_id"]]
    embeddings = OpenAIEmbeddings()
    vectorstore = FAISS.from_texts(texts, embeddings, metadatas=metadatas)
    return vectorstore, df


def _tokenize(text: str) -> List[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text.lower()) if token not in STOPWORDS]


def extract_preference_hints(text: str) -> Dict[str, str]:
    lowered = text.lower()
    hints: Dict[str, str] = {}

    procedure_match = re.search(r"type\s+(ia|ib|ii)\b", lowered)
    if procedure_match:
        hints["procedure_type"] = f"TYPE {procedure_match.group(1).upper()}"

    if "centrally authorised" in lowered:
        hints["authorization_scope"] = "centrally authorised"
    elif "nationally authorised" in lowered:
        hints["authorization_scope"] = "nationally authorised"

    return hints


def _keyword_score(description: str, row: pd.Series) -> float:
    desc_tokens = set(_tokenize(description))
    if not desc_tokens:
        return 0.0

    field_weights = {
        "change_item": 4.0,
        "change_type": 3.0,
        "conditions": 2.0,
        "procedure_type": 1.5,
        "documents": 1.0,
        "filing_description": 1.0,
        "product_type": 0.5,
        "material_type": 0.5,
    }

    score = 0.0
    for field, weight in field_weights.items():
        field_text = str(row.get(field, ""))
        field_tokens = set(_tokenize(field_text))
        if not field_tokens:
            continue
        overlap = desc_tokens.intersection(field_tokens)
        if overlap:
            coverage = len(overlap) / len(desc_tokens)
            specificity = len(overlap) / len(field_tokens)
            score += weight * coverage
            score += (weight / 2.0) * specificity

            normalized_field = " ".join(_tokenize(field_text))
            normalized_query = " ".join(_tokenize(description))
            if normalized_query and normalized_query in normalized_field:
                score += weight * 1.5

            if " ".join(sorted(overlap)) == " ".join(sorted(desc_tokens)) and desc_tokens:
                score += weight

    normalized_search_text = " ".join(_tokenize(str(row.get("search_text", ""))))
    normalized_query = " ".join(_tokenize(description))
    if normalized_query and normalized_query in normalized_search_text:
        score += 5.0

    phrase_bonuses = ("atc code", "nationally authorised", "centrally authorised", "packaging component")
    lower_search_text = str(row.get("search_text", "")).lower()
    lower_description = description.lower()
    for phrase in phrase_bonuses:
        if phrase in lower_description and phrase in lower_search_text:
            score += 4.0

    hints = extract_preference_hints(description)
    row_procedure = str(row.get("procedure_type", "")).upper()
    if hints.get("procedure_type"):
        if hints["procedure_type"] in row_procedure:
            score += 8.0
        else:
            score -= 4.0

    row_description = str(row.get("change_item", "")).lower()
    if hints.get("authorization_scope"):
        if hints["authorization_scope"] in row_description:
            score += 5.0
        else:
            score -= 2.0
    return score


def rank_reference_rows(
    description: str,
    df: pd.DataFrame,
    semantic_candidates: Optional[Sequence[Tuple[str, float]]] = None,
    limit: int = 5,
) -> List[Tuple[pd.Series, float]]:
    candidate_scores = {str(ref_id): 0.0 for ref_id in df["reference_id"]}

    if semantic_candidates:
        for ref_id, semantic_score in semantic_candidates:
            candidate_scores[str(ref_id)] = candidate_scores.get(str(ref_id), 0.0) + semantic_score

    ranked_rows: List[Tuple[pd.Series, float]] = []
    for _, row in df.iterrows():
        ref_id = str(row["reference_id"])
        score = candidate_scores.get(ref_id, 0.0)
        score += _keyword_score(description, row)
        ranked_rows.append((row, score))

    ranked_rows.sort(key=lambda item: item[1], reverse=True)
    return ranked_rows[:limit]


def keyword_classify_change(description: str, df: pd.DataFrame) -> Dict[str, str]:
    ranked_rows = rank_reference_rows(description, df, semantic_candidates=None, limit=1)
    if not ranked_rows or ranked_rows[0][1] <= 0:
        return {"error": "No close match found. Manual review needed."}

    row, score = ranked_rows[0]
    result = _build_classification_payload(row)
    result["match_score"] = float(score)
    result["match_method"] = "keyword"
    return result


def _semantic_candidates_from_vectorstore(description: str, vectorstore, top_k: int = 5) -> List[Tuple[str, float]]:
    docs_and_scores = vectorstore.similarity_search_with_score(description, k=top_k)
    candidates: List[Tuple[str, float]] = []
    for doc, distance in docs_and_scores:
        reference_id = doc.metadata.get("reference_id")
        if reference_id is None:
            continue
        semantic_score = 1.0 / (1.0 + float(distance))
        candidates.append((str(reference_id), semantic_score))
    return candidates


def llm_classify_change(description: str, vectorstore, df: pd.DataFrame):
    semantic_candidates: Optional[Iterable[Tuple[str, float]]] = None

    if vectorstore is not None:
        try:
            semantic_candidates = _semantic_candidates_from_vectorstore(description, vectorstore)
        except Exception:
            semantic_candidates = None

    ranked_rows = rank_reference_rows(description, df, semantic_candidates=semantic_candidates, limit=1)
    if not ranked_rows or ranked_rows[0][1] <= 0:
        return {"error": "No close match found. Manual review needed."}

    row, score = ranked_rows[0]
    result = _build_classification_payload(row)
    result["match_score"] = float(score)
    result["match_method"] = "hybrid" if semantic_candidates else "keyword"
    return result
