# Agentic AI for EU Post-Approval Change Management

This project automates the classification and management of post-approval changes for medicines in the EU using a tool-driven agent workflow.

## Features
- Change classification (Type IA, IB, II, Extension)
- Compliance documentation checklist
- Regulatory process guidance
- Urgent safety workflow
- Clarification prompts for ambiguous requests
- Structured action plan and evidence summary
- Tool trace showing planner/executor decisions
- PDF evidence lookup for supporting guidance snippets
- Upload review for TXT, PDF, CSV, and XLSX support files

## Stack
- Python 3.11 for Streamlit Cloud deployment
- LangChain + OpenAI embeddings (semantic retrieval)
- pandas, openpyxl (Excel handling)
- PyPDF2 (PDF parsing)
- Streamlit (UI)

## Getting Started
1. Activate the virtual environment:
   
   ```sh
   .venv\Scripts\activate
   ```

2. Set the OpenAI API key:

   ```sh
   set OPENAI_API_KEY=your_key_here
   ```

   Or create a local `.streamlit/secrets.toml` from `.streamlit/secrets.toml.example` and put the key there.

3. Run the Streamlit app:
    
   ```sh
   streamlit run app.py
   ```

4. Run the regression tests:

   ```sh
   python -m unittest discover -s tests
   ```

## Streamlit Cloud Deployment
1. Push this project to a GitHub repository. Include `app.py`, `requirements.txt`, `runtime.txt`, the Excel workbook, and the PDF guideline.
2. Do not commit `.streamlit/secrets.toml`; it is ignored because it can contain real API keys.
3. In Streamlit Cloud, create a new app from the GitHub repository and set the main file path to `app.py`.
4. Add the API key in Streamlit Cloud app secrets:

   ```toml
   OPENAI_API_KEY = "your_openai_api_key_here"
   ```

5. Deploy the app. If the API key or vector dependencies are unavailable, the app can still run in keyword-guided mode.

## Project Structure
- `app.py`: Streamlit UI
- `main.py`: backend workflow helpers for classification, document extraction, and process guidance
- `agent_workflow.py`: planner/executor loop that coordinates tools and produces a structured recommendation
- `llm_utils.py`: workbook normalization and vectorstore construction
- `regulation_tools.py`: workbook search, ambiguity assessment, PDF lookup, risk scoring, and action-plan tools
- `guided_decision.py`: condition parsing and guided decision-tree narrowing
- `upload_review.py`: uploaded document extraction and requirement-gap review
- `EU_Post_Approval_Changes_Copy.xlsx`: primary structured reference dataset
- `EU Post approval Guidelines.pdf`: supporting guideline document

## Data Notes
- The workbook is read using the second header row (`header=1`) because the file uses grouped/merged top-level headers.
- The app normalizes workbook columns into internal fields such as `change_type`, `change_item`, `conditions`, `procedure_type`, and `documents`.
- Never hard-code API keys into `app.py`, `main.py`, or `llm_utils.py`. Use environment variables or `.streamlit/secrets.toml`, which is ignored by `.gitignore`.

## Ambiguous Changes
- The agent treats short or underspecified requests as ambiguous and surfaces clarification questions before you should trust the recommendation as final.
- Example ambiguous inputs:
  - `Change the invented name of the finished product.`
  - `We are updating manufacturing details for the product.`
  - `A packaging-related change is planned, but the component impact is still unclear.`
  - `Administrative information in the dossier needs to be updated.`

## Next Steps
- Expand the regression suite with more workbook-backed queries and expected outcomes.
- Add answer refinement after the user responds to clarification questions so the agent can re-plan instead of only surfacing prompts.
- Improve PDF evidence search quality for multilingual or noisy extracted text.
- Add OCR support for scanned PDFs and richer document package validation across multiple uploads.
