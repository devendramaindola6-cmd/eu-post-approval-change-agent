"""
Streamlit UI for EU Post-Approval Change Management Agentic AI
"""
import os

import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError

from agent_workflow import orchestrate_change_analysis
from guided_decision import filter_rows_by_condition_answers, parse_conditions, unique_conditions_for_rows
from llm_utils import build_vectorstore_from_excel, rank_reference_rows
from upload_review import SUPPORTED_UPLOAD_TYPES, extract_uploaded_text

AMBIGUOUS_CHANGE_EXAMPLES = [
    "Change the invented name of the finished product.",
    "We are updating manufacturing details for the product.",
    "A packaging-related change is planned, but the component impact is still unclear.",
    "There is a site-related update for the finished product and batch release activities.",
    "Administrative information in the dossier needs to be updated.",
]

st.title("EU Post-Approval Change Management AI")

st.markdown("""
Enter a description of your post-approval change. The agent will classify the change, list required documents, and recommend the regulatory process.
""")


def configure_openai_api_key() -> None:
    if os.environ.get("OPENAI_API_KEY"):
        return

    try:
        secret_key = st.secrets.get("OPENAI_API_KEY")
    except StreamlitSecretNotFoundError:
        secret_key = None

    if secret_key:
        os.environ["OPENAI_API_KEY"] = secret_key


def ensure_openai_api_key() -> None:
    return


configure_openai_api_key()
ensure_openai_api_key()

# Load reference data and build vectorstore (cache for performance)
@st.cache_resource
def load_resources():
    excel_path = "EU_Post_Approval_Changes_Copy.xlsx"
    pdf_path = "EU Post approval Guidelines.pdf"
    try:
        vectorstore, reference_df = build_vectorstore_from_excel(excel_path)
        return vectorstore, reference_df, retrieval_mode_from_vectorstore(vectorstore), None, pdf_path
    except Exception as exc:
        from llm_utils import load_reference_table

        reference_df = load_reference_table(excel_path)
        return None, reference_df, "keyword", str(exc), pdf_path


def retrieval_mode_from_vectorstore(vectorstore) -> str:
    return "hybrid" if vectorstore is not None else "keyword"


def _clean_options(values):
    return sorted({str(value).strip() for value in values if str(value).strip() and str(value) != "nan"})


def _filter_by_selection(df, column, selected_value):
    if not selected_value or selected_value == "All":
        return df
    return df[df[column].fillna("").astype(str) == selected_value]


def _ranked_options(description, df, column):
    if not description.strip():
        return _clean_options(df[column].dropna().unique())

    scored = {}
    for row, score in rank_reference_rows(description, df, limit=len(df)):
        value = str(row.get(column, "")).strip()
        if value and value != "nan":
            scored[value] = max(scored.get(value, 0.0), float(score))
    return [value for value, _ in sorted(scored.items(), key=lambda item: (-item[1], item[0]))]


def _format_reference_option(row):
    parts = [
        f"Ref {row.get('reference_id', 'N/A')}",
        str(row.get("procedure_type", "N/A")),
        str(row.get("change_category", "N/A")),
        str(row.get("change_item", "N/A")),
    ]
    return " | ".join(part for part in parts if part and part != "nan")


def _extract_uploaded_document(uploaded_file):
    if uploaded_file is None:
        return None

    uploaded_text = extract_uploaded_text(uploaded_file.name, uploaded_file.getvalue())
    return {
        "name": uploaded_file.name,
        "text": uploaded_text,
    }


def _render_analysis(analysis):
    if "error" in analysis:
        st.error(analysis["error"])
        return

    st.subheader("Agent Decision")

    st.write(f"**Reference ID:** {analysis.get('reference_id', 'N/A')}")
    st.write(f"**Change Type:** {analysis.get('change_type', 'N/A')}")
    st.write(f"**Change Item:** {analysis.get('description', 'N/A')}")
    st.write(f"**Classification:** {analysis.get('category', 'N/A')}")
    st.write(f"**Procedure Type:** {analysis.get('procedure_type', 'N/A')}")
    st.write(f"**Filing Required:** {analysis.get('filing_required', 'N/A')}")
    st.write(f"**Market:** {analysis.get('market', 'N/A')}")
    st.write(f"**Match Method:** {analysis.get('match_method', retrieval_mode)}")
    st.write(f"**Confidence:** {analysis.get('confidence', 'N/A').title()}")
    st.write(f"**Risk Level:** {analysis.get('risk_level', 'N/A').title()}")

    if analysis.get("guided_decisions"):
        st.subheader("Selected Path")
        st.write(analysis["guided_decisions"])

    st.subheader("Workflow")
    st.write(analysis.get("workflow_steps", []))

    st.subheader("Agent Summary")
    st.write(analysis.get("agent_summary", "N/A"))

    st.subheader("Evidence Summary")
    st.write(analysis.get("evidence_summary", "N/A"))

    if analysis.get("needs_clarification"):
        st.warning("This request looks ambiguous. Review the clarification questions before treating the recommendation as final.")
        st.write(analysis.get("clarification_questions", []))

    if analysis.get("conditions"):
        st.subheader("Conditions")
        st.write(analysis["conditions"])

    if analysis.get("filing_description"):
        st.subheader("Filing Guidance")
        st.write(analysis["filing_description"])

    st.subheader("Required Documents")
    docs = analysis.get("required_documents_list", [])
    if docs:
        st.write(docs)
    else:
        st.write("No documents listed in the workbook for this entry.")

    st.subheader("Recommended Process")
    st.write(analysis.get("recommended_process", "N/A"))

    st.subheader("Next Actions")
    st.write(analysis.get("action_plan", []))

    st.subheader("Top Candidate Matches")
    st.write(analysis.get("top_matches", []))

    if analysis.get("pdf_evidence"):
        st.subheader("PDF Evidence")
        st.write(analysis.get("pdf_evidence", []))

    if analysis.get("uploaded_document_review"):
        st.subheader("Uploaded Document Review")
        st.write(analysis.get("uploaded_document_review", {}))

    st.subheader("Tool Trace")
    st.write(analysis.get("tool_trace", []))


vectorstore, reference_df, retrieval_mode, load_warning, pdf_path = load_resources()

with st.sidebar:
    st.subheader("Agent Status")
    st.write(f"**Workbook rows:** {len(reference_df)}")
    st.write(f"**Retrieval mode:** {retrieval_mode}")
    st.write(f"**PDF guidance:** {'available' if os.path.exists(pdf_path) else 'missing'}")
    st.write(f"**OpenAI key configured:** {'yes' if bool(os.environ.get('OPENAI_API_KEY')) else 'no'}")
    if load_warning:
        st.caption(f"Fallback reason: {load_warning}")

if retrieval_mode == "hybrid":
    st.caption("Retrieval mode: hybrid semantic + keyword matching")
else:
    st.warning("Running in keyword-only fallback mode because OpenAI embeddings are unavailable.")
    if load_warning:
        st.caption(f"Fallback reason: {load_warning}")

with st.expander("Ambiguous change examples"):
    st.write("Use these to test clarification behavior:")
    st.code("\n\n".join(AMBIGUOUS_CHANGE_EXAMPLES))

change_desc = st.text_area("Describe your post-approval change:")
uploaded_file = st.file_uploader(
    "Optional supporting document upload",
    type=[suffix.lstrip(".") for suffix in SUPPORTED_UPLOAD_TYPES],
    help="Upload a TXT, PDF, CSV, or XLSX file for document review against the matched filing scenario.",
)

if change_desc.strip():
    st.subheader("Guided Decision Tree")

    filtered_df = reference_df.copy()
    user_decisions = {}

    material_options = ["All"] + _ranked_options(change_desc, filtered_df, "material_type")
    selected_material = st.selectbox("Material type", material_options)
    filtered_df = _filter_by_selection(filtered_df, "material_type", selected_material)
    user_decisions["material_type"] = selected_material

    change_type_options = _ranked_options(change_desc, filtered_df, "change_type")
    selected_change_type = st.selectbox("Change type", change_type_options)
    filtered_df = _filter_by_selection(filtered_df, "change_type", selected_change_type)
    user_decisions["change_type"] = selected_change_type

    change_item_options = _ranked_options(change_desc, filtered_df, "change_item")
    selected_change_item = st.selectbox("Specific change item", change_item_options)
    filtered_df = _filter_by_selection(filtered_df, "change_item", selected_change_item)
    user_decisions["change_item"] = selected_change_item

    condition_questions = unique_conditions_for_rows(filtered_df)
    if condition_questions:
        st.subheader("Condition Check")
        condition_answers = {}
        for index, condition in enumerate(condition_questions, start=1):
            answer = st.radio(
                condition,
                ["Yes", "No", "Not sure"],
                horizontal=True,
                key=f"condition_{index}_{abs(hash(condition))}",
            )
            condition_answers[condition] = answer
        user_decisions["condition_answers"] = condition_answers

        if "Not sure" in condition_answers.values():
            st.warning("Some conditions are marked as not sure. The matching entries remain available for manual selection.")
        else:
            filtered_df = filter_rows_by_condition_answers(filtered_df, condition_answers)

    if len(filtered_df) > 1:
        scenario_options = _clean_options(filtered_df["change_scenario"].dropna().unique())
        if len(scenario_options) > 1:
            selected_scenario = st.selectbox("Change scenario", scenario_options)
            filtered_df = _filter_by_selection(filtered_df, "change_scenario", selected_scenario)
            user_decisions["change_scenario"] = selected_scenario

    if len(filtered_df) > 1:
        procedure_options = _clean_options(filtered_df["procedure_type"].dropna().unique())
        if len(procedure_options) > 1:
            selected_procedure = st.selectbox("Filing pathway", procedure_options)
            filtered_df = _filter_by_selection(filtered_df, "procedure_type", selected_procedure)
            user_decisions["procedure_type"] = selected_procedure

    if len(filtered_df) > 1:
        category_options = _clean_options(filtered_df["change_category"].dropna().unique())
        if len(category_options) > 1:
            selected_category = st.selectbox("Impact classification", category_options)
            filtered_df = _filter_by_selection(filtered_df, "change_category", selected_category)
            user_decisions["change_category"] = selected_category

    reference_options = {
        _format_reference_option(row): str(row.get("reference_id", ""))
        for _, row in filtered_df.iterrows()
    }
    selected_reference_label = st.selectbox("Final matching workbook entry", list(reference_options.keys()))
    selected_reference_id = reference_options[selected_reference_label]
    selected_row = filtered_df[filtered_df["reference_id"].astype(str) == selected_reference_id].iloc[0]
    user_decisions["reference_id"] = selected_reference_id

    with st.expander("Selected entry details", expanded=True):
        selected_conditions = parse_conditions(selected_row.get("conditions", ""))
        if selected_conditions:
            st.write("**Conditions:**")
            st.write(selected_conditions)
        else:
            st.write("**Conditions:** No Conditions")
        st.write(f"**Filing description:** {selected_row.get('filing_description', 'N/A')}")
        st.write(f"**Documents:** {selected_row.get('documents', 'N/A')}")

    if st.button("Analyze Selected Path"):
        with st.spinner("Analyzing selected path..."):
            try:
                uploaded_document = _extract_uploaded_document(uploaded_file)
            except Exception as exc:
                st.error(f"Unable to read uploaded file: {exc}")
                st.stop()

            analysis = orchestrate_change_analysis(
                change_desc.strip(),
                reference_df,
                vectorstore=vectorstore,
                pdf_path=pdf_path,
                uploaded_document=uploaded_document,
                selected_reference_id=selected_reference_id,
                user_decisions=user_decisions,
            )
            _render_analysis(analysis)
else:
    st.info("Enter a change description to start the guided decision tree.")
