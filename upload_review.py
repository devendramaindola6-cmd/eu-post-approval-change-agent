"""
upload_review.py - Extraction and review helpers for uploaded regulatory documents
"""
from __future__ import annotations

from io import BytesIO
from typing import Any, Dict, List

import pandas as pd


SUPPORTED_UPLOAD_TYPES = (".txt", ".pdf", ".csv", ".xlsx")


def extract_uploaded_text(file_name: str, file_bytes: bytes) -> str:
    lower_name = file_name.lower()

    if lower_name.endswith(".txt"):
        return file_bytes.decode("utf-8", errors="ignore")

    if lower_name.endswith(".pdf"):
        from PyPDF2 import PdfReader

        reader = PdfReader(BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages)

    if lower_name.endswith(".csv"):
        df = pd.read_csv(BytesIO(file_bytes))
        return df.fillna("").astype(str).to_csv(index=False)

    if lower_name.endswith(".xlsx"):
        sheets = pd.read_excel(BytesIO(file_bytes), sheet_name=None)
        parts: List[str] = []
        for sheet_name, df in sheets.items():
            parts.append(f"Sheet: {sheet_name}")
            parts.append(df.fillna("").astype(str).to_csv(index=False))
        return "\n".join(parts)

    raise ValueError(f"Unsupported upload type for `{file_name}`. Supported types: {', '.join(SUPPORTED_UPLOAD_TYPES)}")


def review_uploaded_document(upload_name: str, upload_text: str, classification: Dict[str, Any]) -> Dict[str, Any]:
    normalized_text = upload_text.lower()
    required_documents = classification.get("required_documents_list", [])

    matched_requirements: List[str] = []
    missing_requirements: List[str] = []
    for requirement in required_documents:
        req_tokens = [token for token in requirement.lower().replace("/", " ").split() if len(token) > 3]
        if req_tokens and any(token in normalized_text for token in req_tokens[:4]):
            matched_requirements.append(requirement)
        else:
            missing_requirements.append(requirement)

    extracted_signals = []
    for key, label in (
        ("procedure_type", "Procedure type"),
        ("description", "Matched scenario"),
        ("filing_description", "Filing guidance"),
    ):
        value = str(classification.get(key, "")).strip()
        if value:
            extracted_signals.append(f"{label}: {value}")

    review_summary = (
        f"Reviewed uploaded file `{upload_name}` against the selected scenario and required document list. "
        f"Matched requirements: {len(matched_requirements)}. Missing or unclear requirements: {len(missing_requirements)}."
    )

    return {
        "upload_name": upload_name,
        "matched_requirements": matched_requirements,
        "missing_requirements": missing_requirements,
        "review_summary": review_summary,
        "extracted_signals": extracted_signals,
        "upload_excerpt": upload_text[:1200].strip(),
    }
