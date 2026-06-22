# Code Explanation

This document explains the project folders, files, and code flow for a newcomer.

## Folder Structure

```text
.
├── .git/
├── .streamlit/
├── .venv/
├── tests/
├── __pycache__/
├── app.py
├── main.py
├── agent_workflow.py
├── llm_utils.py
├── regulation_tools.py
├── guided_decision.py
├── upload_review.py
├── EU_Post_Approval_Changes_Copy.xlsx
├── EU Post approval Guidelines.pdf
├── requirements.txt
├── runtime.txt
├── README.md
└── BUILD_GUIDE.md
```

## Folders

### `.git/`

This is the Git repository metadata folder. It tracks file history, branches, commits, and changes. Developers normally do not edit files inside this folder manually.

### `.streamlit/`

This folder stores Streamlit configuration and secrets.

- `secrets.toml.example`: example file showing how to store `OPENAI_API_KEY`.
- `secrets.toml`: local real secrets file. This should not be committed to Git.

The app reads the OpenAI key from this folder when it runs locally or on Streamlit Cloud.

### `.venv/`

This is the local Python virtual environment. It contains installed packages such as Streamlit, pandas, LangChain, FAISS, and PyPDF2.

This folder is machine-specific and should not be committed.

### `tests/`

This folder contains automated tests.

- `test_classification.py`: checks classification, guided decision behavior, document extraction, upload review, and agent workflow output.

Run tests with:

```sh
python -m unittest discover -s tests
```

### `__pycache__/`

Python creates this folder automatically to store compiled bytecode cache files. Developers do not need to edit it.

## Main Application Flow

At a high level, the app works like this:

```text
User opens Streamlit app
        ↓
app.py loads Excel and PDF resources
        ↓
User enters change description
        ↓
Guided decision tree narrows workbook rows
        ↓
agent_workflow.py runs the planner/executor flow
        ↓
llm_utils.py and regulation_tools.py find the best reference match
        ↓
main.py formats documents and process guidance
        ↓
app.py displays classification, evidence, risk, actions, and tool trace
```

## File-by-File Explanation

### `app.py`

This is the Streamlit user interface and the main file used when running:

```sh
streamlit run app.py
```

Important responsibilities:

- Shows the page title and input form.
- Reads the OpenAI API key from environment variables or `.streamlit/secrets.toml`.
- Loads the Excel workbook and PDF guideline.
- Builds a semantic vectorstore when OpenAI embeddings are available.
- Falls back to keyword mode if embeddings are unavailable.
- Shows a guided decision tree with dropdowns and condition questions.
- Accepts optional uploaded support documents.
- Calls `orchestrate_change_analysis()` from `agent_workflow.py`.
- Displays the final classification, required documents, process, risk, evidence, uploaded document review, and tool trace.

Important functions:

- `configure_openai_api_key()`: checks whether `OPENAI_API_KEY` exists, then tries to read it from Streamlit secrets.
- `load_resources()`: loads the Excel workbook and tries to build the vectorstore. It is cached with `st.cache_resource`.
- `_ranked_options()`: ranks dropdown options based on the user's change description.
- `_extract_uploaded_document()`: converts an uploaded file into text.
- `_render_analysis()`: displays the final result returned by the agent workflow.

### `main.py`

This file contains simple backend helper functions and a command-line entry point.

Important functions:

- `classify_change(description, reference_df)`: performs a simple exact text search across workbook fields.
- `get_required_documents(classification)`: converts the workbook document text into a clean Python list.
- `suggest_process(classification)`: returns process guidance based on the procedure type, such as Type IA, Type IB, Type II, or Extension.

It can also be run directly:

```sh
python main.py
```

When run directly, it asks the user for a change description, classifies it, prints required documents, and prints the recommended process.

### `agent_workflow.py`

This file coordinates the agent-style workflow. It acts like the decision engine.

Important parts:

- `AgentState`: a dataclass that stores the current workflow state, including user description, workbook data, top matches, classification, confidence, risk, evidence, and uploaded document review.
- `_planner_next_step(state)`: decides which step should happen next.
- `_execute_step(state, step)`: performs the selected step.
- `orchestrate_change_analysis(...)`: public function used by `app.py` and tests.

Workflow steps:

- `guided_classify`: use a reference row selected by the guided decision tree.
- `workbook_search`: find top workbook candidates.
- `classify`: choose the best classification.
- `clarify`: create clarification questions if confidence is low.
- `risk_assess`: estimate regulatory risk.
- `action_plan`: create next action steps.
- `pdf_evidence`: search PDF guideline snippets.
- `upload_review`: compare uploaded support documents against required documents.

The final return value is a dictionary containing the full result shown in the UI.

### `llm_utils.py`

This file handles workbook loading, normalization, keyword scoring, semantic matching, and classification.

Important constants:

- `EXCEL_HEADER_ROW = 1`: tells pandas to read the second row as the Excel header.
- `SOURCE_TO_NORMALIZED_COLUMNS`: maps long Excel column names to simpler internal names.
- `REQUIRED_NORMALIZED_COLUMNS`: columns that must exist after normalization.
- `SEARCH_FIELDS`: fields used to build searchable text.
- `STOPWORDS`: common words ignored during keyword scoring.

Important functions:

- `load_reference_table(path)`: reads the Excel file, normalizes columns, removes empty rows, adds `reference_id`, and builds `search_text`.
- `_build_search_text(row)`: combines useful row fields into one searchable text block.
- `_build_classification_payload(row)`: converts a workbook row into the classification dictionary used by the app.
- `classify_reference_row(reference_id, df)`: returns the classification for a selected workbook row.
- `build_vectorstore_from_excel(path)`: creates a FAISS vectorstore using OpenAI embeddings.
- `rank_reference_rows(description, df, semantic_candidates=None, limit=5)`: ranks workbook rows using keyword score and optional semantic score.
- `keyword_classify_change(description, df)`: classifies using keyword scoring only.
- `llm_classify_change(description, vectorstore, df)`: classifies using hybrid semantic plus keyword matching when possible.

Despite the name `llm_classify_change`, the current code does not ask a chat model to produce free-form classification. It uses embeddings and deterministic scoring against workbook rows.

### `regulation_tools.py`

This file contains small tool functions used by the agent workflow.

Important functions:

- `workbook_search_tool(...)`: retrieves top workbook matches.
- `ambiguity_assessor_tool(...)`: checks score strength and score gap to decide confidence.
- `clarification_tool(...)`: creates questions when top matches are too close or unclear.
- `evidence_synthesis_tool(...)`: builds a summary and top candidate list.
- `risk_assessor_tool(...)`: assigns low, medium, or high risk from the procedure type.
- `action_plan_tool(...)`: creates practical next steps for the user.
- `pdf_evidence_tool(...)`: extracts relevant snippets from the guideline PDF.

The PDF pages are cached by `_load_pdf_pages()` so the file is not re-read repeatedly.

### `guided_decision.py`

This file supports the guided decision tree shown in the Streamlit UI.

Important functions:

- `parse_conditions(conditions_text)`: converts condition text into a list of individual conditions.
- `unique_conditions_for_rows(df)`: collects unique condition questions from selected workbook rows.
- `filter_rows_by_condition_answers(df, answers)`: narrows workbook rows based on Yes/No answers.

This helps users move from a broad change description to a specific workbook reference row.

### `upload_review.py`

This file handles optional document uploads.

Supported upload types:

- `.txt`
- `.pdf`
- `.csv`
- `.xlsx`

Important functions:

- `extract_uploaded_text(file_name, file_bytes)`: extracts readable text from the uploaded file.
- `review_uploaded_document(upload_name, upload_text, classification)`: compares extracted text against required documents from the selected classification.

The review is a simple keyword-based check. It reports matched requirements, missing or unclear requirements, extracted signals, and an upload excerpt.

### `tests/test_classification.py`

This test file verifies that important behavior keeps working.

It tests:

- Specific queries map to expected filing types.
- Required documents are extracted correctly.
- Type IB guidance says review happens before implementation.
- The orchestrator returns workflow fields, risk, action plan, and tool trace.
- Guided reference selection works.
- Condition parsing and filtering work.
- Ambiguous requests trigger clarification questions.
- CSV upload extraction and document review work.
- Uploaded document review appears in the orchestrator result.

## Data Files

### `EU_Post_Approval_Changes_Copy.xlsx`

This is the main structured regulatory reference workbook. The app reads this file into a pandas DataFrame.

Important behavior:

- The second row is used as the header.
- Long column names are renamed to simpler names.
- Each row receives a `reference_id`.
- Searchable text is built from fields like change type, change item, conditions, procedure type, filing description, and documents.

### `EU Post approval Guidelines.pdf`

This PDF is used as supporting guidance evidence. The app searches the text of the PDF and returns relevant snippets with page numbers.

## Configuration Files

### `requirements.txt`

Lists Python packages required by the project:

- `streamlit`: web app UI.
- `pandas`: Excel/CSV data handling.
- `openpyxl`: Excel reading support.
- `PyPDF2`: PDF text extraction.
- `langchain-community`: FAISS vectorstore integration.
- `langchain-openai`: OpenAI embeddings.
- `faiss-cpu`: local vector search.

### `runtime.txt`

Used by Streamlit Cloud to select the Python runtime:

```text
python-3.11
```

### `.env.example`

Example environment file showing:

```text
OPENAI_API_KEY=your_openai_api_key_here
```

The code currently reads the key from environment variables or Streamlit secrets.

### `.gitignore`

Prevents local-only or sensitive files from being committed:

- `.env`
- `.streamlit/secrets.toml`
- `.venv/`
- `__pycache__/`
- `*.pyc`

## End-to-End Example

If a user enters:

```text
We need to update the ATC code after a WHO change.
```

The flow is:

1. `app.py` receives the text.
2. `rank_reference_rows()` in `llm_utils.py` scores matching workbook rows.
3. `agent_workflow.py` selects the classification step.
4. `regulation_tools.py` assesses ambiguity, evidence, risk, PDF snippets, and action plan.
5. `main.py` extracts required documents and suggests the process.
6. `app.py` displays the final result.

Expected result from tests:

- Procedure type: `Type IA`
- Required document includes: `ATC Code list`
- Risk level: `low`

## What a New Developer Should Understand First

Start with these files in this order:

1. `app.py`: understand what the user sees.
2. `llm_utils.py`: understand how workbook rows are loaded and matched.
3. `agent_workflow.py`: understand how steps are planned and executed.
4. `regulation_tools.py`: understand risk, evidence, clarification, and action plan helpers.
5. `guided_decision.py`: understand the guided UI filters.
6. `upload_review.py`: understand upload extraction and simple requirement matching.
7. `tests/test_classification.py`: understand the expected behavior.
