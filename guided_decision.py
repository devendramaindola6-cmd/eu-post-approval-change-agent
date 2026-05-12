"""
guided_decision.py - Helpers for condition-driven workbook narrowing.
"""
from __future__ import annotations

import re
from typing import Dict, List

import pandas as pd


def parse_conditions(conditions_text: str) -> List[str]:
    text = str(conditions_text or "").strip()
    if not text or text.lower() == "nan" or "no conditions" in text.lower():
        return []

    text = re.sub(r"^\s*all\s+conditions?\s+are\s+met\s*:?\s*", "", text, flags=re.IGNORECASE)
    parts = re.split(r"(?:^|\n)\s*\d+[\.\)]\s+", text)
    conditions = [part.strip(" \n\t.;") for part in parts if part.strip(" \n\t.;")]
    if conditions:
        return conditions
    return [text.strip(" \n\t.;")]


def unique_conditions_for_rows(df: pd.DataFrame) -> List[str]:
    conditions: List[str] = []
    seen = set()
    for value in df.get("conditions", []):
        for condition in parse_conditions(str(value)):
            normalized = re.sub(r"\s+", " ", condition.lower())
            if normalized not in seen:
                seen.add(normalized)
                conditions.append(condition)
    return conditions


def filter_rows_by_condition_answers(df: pd.DataFrame, answers: Dict[str, str]) -> pd.DataFrame:
    answered = {key: value for key, value in answers.items() if value in {"Yes", "No"}}
    if not answered:
        return df

    any_not_met = any(value == "No" for value in answered.values())
    scenario_text = df.get("change_scenario", pd.Series(dtype=str)).fillna("").astype(str).str.lower()
    conditions_text = df.get("conditions", pd.Series(dtype=str)).fillna("").astype(str).str.lower()

    if any_not_met:
        not_met_mask = scenario_text.str.contains("not met", regex=False)
        no_conditions_mask = conditions_text.str.contains("no conditions", regex=False)
        narrowed = df[not_met_mask | no_conditions_mask]
        return narrowed if not narrowed.empty else df

    all_met_mask = scenario_text.str.contains("all conditions are met", regex=False)
    possibility_met_mask = scenario_text.str.contains("possibility 1", regex=False)
    conditions_met_mask = conditions_text.str.contains("all condition", regex=False)
    narrowed = df[all_met_mask | possibility_met_mask | conditions_met_mask]
    return narrowed if not narrowed.empty else df
