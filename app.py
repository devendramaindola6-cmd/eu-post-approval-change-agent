"""Streamlit UI for country-specific post-approval change assessment."""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from agent_workflow import orchestrate_change_analysis
from guided_decision import filter_rows_by_condition_answers, parse_conditions, unique_conditions_for_rows
from llm_utils import NO_MATCH_MESSAGE, build_vectorstore_from_excel, load_reference_table

PROJECT_ROOT = Path(__file__).resolve().parent

COUNTRY_CONFIG = {
    "Australia": {
        "workbook": "Australia.xlsx",
        "market": "Australia",
    },
    "Canada": {
        "workbook": "Canada.xlsx",
        "market": "Canada",
    },
    "European Union": {
        "workbook": "EU_TypeIB_Created.xlsx",
        "market": "EU",
    },
    "Switzerland": {
        "workbook": "Switzerland_TypeIB_Created.xlsx",
        "market": "Switzerland",
    },
}

st.set_page_config(page_title="Post-Approval Change Management AI", layout="wide")
st.title("Post-Approval Change Management AI")
st.caption("Choose a country, follow the suggested change path, then generate only the relevant regulatory output.")


def configure_openai_api_key() -> None:
    if os.environ.get("OPENAI_API_KEY"):
        return
    try:
        secret_key = st.secrets.get("OPENAI_API_KEY")
    except StreamlitSecretNotFoundError:
        secret_key = None
    if secret_key:
        os.environ["OPENAI_API_KEY"] = secret_key


def _pill_selector(label, options, key, help_text=None, format_func=None):
    options = list(options)
    format_func = format_func or str
    if hasattr(st, "pills"):
        return st.pills(
            label,
            options,
            key=key,
            help=help_text,
            format_func=format_func,
        )
    return st.radio(
        label,
        options,
        index=None,
        horizontal=True,
        key=key,
        help=help_text,
        format_func=format_func,
    )


def _clean_options(values):
    return sorted(
        {
            str(value).strip()
            for value in values
            if str(value).strip() and str(value).strip().lower() != "nan"
        },
        key=str.casefold,
    )


def _filter_by_selection(df, column, selected_value):
    if not selected_value:
        return df
    return df[df[column].fillna("").astype(str).str.strip() == selected_value]


def _compact_suggestion(value):
    compact = " ".join(str(value).split())
    return compact if len(compact) <= 150 else f"{compact[:147].rstrip()}..."


def _format_reference_option(row):
    parts = [
        f"Ref {row.get('reference_id', 'N/A')}",
        str(row.get("procedure_type", "N/A")),
        str(row.get("change_category", "N/A")),
        str(row.get("change_scenario", "")).strip(),
    ]
    return " | ".join(part for part in parts if part and part.lower() != "nan")


def _format_output_value(value, empty_message="Not specified"):
    if value is None:
        return empty_message
    if isinstance(value, (list, tuple, set)):
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        return "\n".join(f"{index}. {item}" for index, item in enumerate(cleaned, start=1)) or empty_message
    text = str(value).strip()
    return text if text and text.lower() != "nan" else empty_message


def _build_output_table(analysis):
    conditions = parse_conditions(analysis.get("conditions", ""))
    guided_decisions = analysis.get("guided_decisions", {})
    rows = [
        ("Country / Region", analysis.get("selected_country") or analysis.get("market")),
        ("Material Type", guided_decisions.get("material_type")),
        ("Change Type", analysis.get("change_type")),
        ("User Change Description", analysis.get("user_change_description")),
        ("Matched Regulatory Change", analysis.get("description")),
        ("Applicable Conditions", conditions or "No conditions listed"),
        ("Filing Required", analysis.get("filing_required")),
        ("Submission Type", analysis.get("procedure_type")),
        ("Impact Classification", analysis.get("category")),
        ("Filing Guidance", analysis.get("filing_description")),
        ("Required Documents", analysis.get("required_documents_list") or "No documents listed"),
        ("Recommended Process", analysis.get("recommended_process")),
        ("Next Actions", analysis.get("action_plan")),
    ]

    return pd.DataFrame(
        [
            {"Information": label, "Result": _format_output_value(value)}
            for label, value in rows
        ]
    )


def _render_analysis(analysis):
    if "error" in analysis:
        st.error(analysis["error"])
        return

    st.divider()
    st.subheader("Regulatory assessment")
    output_df = _build_output_table(analysis)
    st.dataframe(
        output_df,
        hide_index=True,
        width="stretch",
        column_config={
            "Information": st.column_config.TextColumn("Information", width="medium"),
            "Result": st.column_config.TextColumn("Result", width="large"),
        },
    )

    country_slug = str(
        analysis.get("selected_country") or analysis.get("market") or "regulatory"
    ).lower().replace(" ", "_")
    st.download_button(
        "Download assessment as CSV",
        data=output_df.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"{country_slug}_post_approval_assessment.csv",
        mime="text/csv",
        width="stretch",
    )


configure_openai_api_key()


@st.cache_resource(show_spinner=False)
def load_country_resources(country_name):
    config = COUNTRY_CONFIG[country_name]
    workbook_path = PROJECT_ROOT / config["workbook"]

    reference_df = load_reference_table(str(workbook_path))
    market_rows = reference_df[
        reference_df["market"].fillna("").astype(str).str.strip().str.casefold()
        == config["market"].casefold()
    ]
    if not market_rows.empty:
        reference_df = market_rows.reset_index(drop=True).copy()
        reference_df["reference_id"] = reference_df.index.astype(str)

    if not os.environ.get("OPENAI_API_KEY"):
        return None, reference_df

    try:
        vectorstore, semantic_df = build_vectorstore_from_excel(str(workbook_path))
        return vectorstore, semantic_df
    except Exception:
        return None, reference_df


selected_country = _pill_selector(
    "Select a country or region",
    COUNTRY_CONFIG.keys(),
    key="selected_country",
)

if not selected_country:
    st.info("Select a country to begin.")
    st.stop()

with st.spinner(f"Loading {selected_country} guidance..."):
    vectorstore, reference_df = load_country_resources(selected_country)

st.subheader("1. Choose the proposed change")

material_options = _clean_options(reference_df["material_type"].dropna().unique())
selected_material = _pill_selector(
    "Material type",
    material_options,
    key=f"material_{selected_country}",
)
if not selected_material:
    st.info("Select a material type to see relevant change suggestions.")
    st.stop()

filtered_df = _filter_by_selection(reference_df, "material_type", selected_material)
change_type_options = _clean_options(filtered_df["change_type"].dropna().unique())
selected_change_type = _pill_selector(
    "Change type",
    change_type_options,
    key=f"change_type_{selected_country}_{selected_material}",
)
if not selected_change_type:
    st.info("Select a change type to see specific suggested changes.")
    st.stop()

filtered_df = _filter_by_selection(filtered_df, "change_type", selected_change_type)
change_item_options = _clean_options(filtered_df["change_item"].dropna().unique())
selected_change_item = _pill_selector(
    "Suggested change",
    change_item_options,
    key=f"change_item_{selected_country}_{selected_material}_{selected_change_type}",
    help_text="Choose the closest suggestion. You can edit its wording in the next field.",
    format_func=_compact_suggestion,
)
if not selected_change_item:
    st.info("Select the closest suggested change.")
    st.stop()

draft_key = f"change_description_{selected_country}"
source_key = f"change_description_source_{selected_country}"
if st.session_state.get(source_key) != selected_change_item:
    st.session_state[draft_key] = selected_change_item
    st.session_state[source_key] = selected_change_item

change_desc = st.text_area(
    "Edit or add details",
    key=draft_key,
    help="Keep the suggested wording or add product-specific context before analysis.",
)

filtered_df = _filter_by_selection(filtered_df, "change_item", selected_change_item)
user_decisions = {
    "country": selected_country,
    "material_type": selected_material,
    "change_type": selected_change_type,
    "change_item": selected_change_item,
}

st.subheader("2. Confirm the applicable scenario")

condition_questions = unique_conditions_for_rows(filtered_df)
if condition_questions:
    condition_answers = {}
    for index, condition in enumerate(condition_questions, start=1):
        answer = _pill_selector(
            condition,
            ["Yes", "No", "Not sure"],
            key=f"condition_{selected_country}_{index}_{abs(hash(condition))}",
        )
        if answer is None:
            st.info("Answer each condition to continue.")
            st.stop()
        condition_answers[condition] = answer
    user_decisions["condition_answers"] = condition_answers

    if "Not sure" in condition_answers.values():
        st.warning("One or more conditions are uncertain. Review the final workbook scenario carefully.")
    else:
        filtered_df = filter_rows_by_condition_answers(filtered_df, condition_answers)

for column, label in (
    ("change_scenario", "Change scenario"),
    ("procedure_type", "Filing pathway"),
    ("change_category", "Impact classification"),
):
    if len(filtered_df) <= 1:
        break
    if column not in filtered_df.columns:
        continue
    options = _clean_options(filtered_df[column].dropna().unique())
    if len(options) > 1:
        selection = _pill_selector(
            label,
            options,
            key=f"{column}_{selected_country}_{selected_material}_{selected_change_type}_{selected_change_item}",
        )
        if not selection:
            st.info(f"Select the {label.lower()} to continue.")
            st.stop()
        filtered_df = _filter_by_selection(filtered_df, column, selection)
        user_decisions[column] = selection

if filtered_df.empty:
    st.error(NO_MATCH_MESSAGE)
    st.stop()

if len(filtered_df) == 1:
    selected_row = filtered_df.iloc[0]
else:
    reference_options = {
        _format_reference_option(row): str(row.get("reference_id", ""))
        for _, row in filtered_df.iterrows()
    }
    selected_reference_label = st.selectbox(
        "Final matching workbook entry",
        list(reference_options.keys()),
    )
    selected_reference_id = reference_options[selected_reference_label]
    selected_row = filtered_df[
        filtered_df["reference_id"].astype(str) == selected_reference_id
    ].iloc[0]

selected_reference_id = str(selected_row["reference_id"])
user_decisions["reference_id"] = selected_reference_id

st.subheader("3. Generate the relevant output")
analysis_signature = (
    selected_country,
    selected_reference_id,
    change_desc.strip(),
)
if st.button("Analyze selected path", type="primary", width="stretch"):
    if not change_desc.strip():
        st.error("Add a change description before analysis.")
        st.stop()

    with st.spinner("Analyzing the selected regulatory path..."):
        analysis = orchestrate_change_analysis(
            change_desc.strip(),
            reference_df,
            vectorstore=vectorstore,
            pdf_path=None,
            selected_reference_id=selected_reference_id,
            user_decisions=user_decisions,
        )
        analysis["selected_country"] = selected_country
        analysis["user_change_description"] = change_desc.strip()
        st.session_state["latest_analysis"] = analysis
        st.session_state["latest_analysis_signature"] = analysis_signature

if (
    st.session_state.get("latest_analysis")
    and st.session_state.get("latest_analysis_signature") == analysis_signature
):
    _render_analysis(st.session_state["latest_analysis"])
