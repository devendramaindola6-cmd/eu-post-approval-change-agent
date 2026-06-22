"""Core backend logic for country-specific post-approval change management."""
import argparse
import re
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from llm_utils import NO_MATCH_MESSAGE, build_vectorstore_from_excel, llm_classify_change


def classify_change(description: str, reference_df: pd.DataFrame) -> Dict[str, Any]:
    search_series = (
        reference_df["change_type"].fillna("")
        + " "
        + reference_df["change_item"].fillna("")
        + " "
        + reference_df["conditions"].fillna("")
    )
    matches = reference_df[search_series.str.contains(description, case=False, na=False, regex=False)]
    if not matches.empty:
        row = matches.iloc[0]
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
        }
    return {"error": NO_MATCH_MESSAGE}


def get_required_documents(classification: Dict[str, Any]) -> List[str]:
    docs = str(classification.get("documents", "")).strip()
    if not docs:
        return []

    if "\n" in docs:
        parts = [part.strip(" -\t") for part in docs.splitlines() if part.strip()]
    else:
        parts = [part.strip() for part in docs.split(",") if part.strip()]

    cleaned = [re.sub(r"^\d+[\.\)]\s*", "", part).strip() for part in parts]
    return [part for part in cleaned if part]


def suggest_process(classification: Dict[str, Any]) -> str:
    proc = str(classification.get("procedure_type", "")).upper()
    market = str(classification.get("market", "")).upper()

    if market == "AUSTRALIA":
        if "DO NOT REQUIRE REPORTING" in proc:
            return "Implement the change after confirming all stated conditions; no TGA variation filing is indicated for this workbook scenario."
        if "NOTIFICATION" in proc:
            return "Submit the applicable TGA notification and follow the timing stated in the matched filing guidance."
        if "CATEGORY 3" in proc:
            return "Prepare a Category 3 TGA variation package and obtain the required regulatory clearance before implementation."

    if market == "CANADA":
        if "ANNUAL NOTIFICATION" in proc:
            return "Document the change and include it in the applicable Health Canada annual notification cycle."
        if "NOTIFIABLE CHANGE" in proc:
            return "Submit the notifiable change package to Health Canada and follow the applicable review requirements before implementation."
        if "SUPPLEMENT" in proc:
            return "Prepare the applicable Health Canada supplement and wait for the required authorization before implementation."

    if "TYPE IA" in proc:
        return "Implement the change first, then notify the authority within the applicable Type IA reporting window."
    if "TYPE IB" in proc:
        return "Notify the authority before implementation and wait for the Type IB review outcome before proceeding."
    if "TYPE II" in proc:
        return "Submit the variation for full assessment and wait for approval before implementation."
    if "EXTENSION" in proc:
        return "Treat this as an extension application and plan for a full submission package before implementation."
    return "Review the filing description and guideline reference manually to confirm whether this is an extension, safety-driven change, or another special pathway."


if __name__ == "__main__":
    workbooks = {
        "australia": "Australia.xlsx",
        "canada": "Canada.xlsx",
        "eu": "EU_TypeIB_Created.xlsx",
        "switzerland": "Switzerland_TypeIB_Created.xlsx",
    }
    parser = argparse.ArgumentParser(description="Analyze a post-approval change.")
    parser.add_argument("country", choices=workbooks)
    args = parser.parse_args()

    excel_path = Path(__file__).resolve().parent / workbooks[args.country]
    vectorstore, reference_df = build_vectorstore_from_excel(str(excel_path))

    change_desc = input("Describe your post-approval change: ")
    classification = llm_classify_change(change_desc, vectorstore, reference_df)
    print("\nClassification Result:", classification)

    docs = get_required_documents(classification)
    print("\nRequired Documents:", docs)

    process = suggest_process(classification)
    print("\nRecommended Process:", process)
