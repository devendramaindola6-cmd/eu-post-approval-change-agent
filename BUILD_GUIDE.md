# Build Guide

This guide explains how a new developer can set up, run, test, and deploy the EU Post-Approval Change Management AI project.

## 1. Project Overview

The project is a Streamlit application that helps classify EU post-approval medicine changes and suggests the required regulatory documents and process.

Main files:

- `app.py`: Streamlit web application.
- `main.py`: command-line/backend workflow helpers.
- `agent_workflow.py`: agent workflow orchestration.
- `llm_utils.py`: Excel loading, normalization, and retrieval helpers.
- `regulation_tools.py`: regulatory lookup and decision tools.
- `guided_decision.py`: guided narrowing of matching change conditions.
- `upload_review.py`: uploaded support document extraction and review.
- `EU_Post_Approval_Changes_Copy.xlsx`: structured reference data.
- `EU Post approval Guidelines.pdf`: supporting guideline document.
- `requirements.txt`: Python dependencies.
- `runtime.txt`: Python version for Streamlit Cloud.

## 2. Prerequisites

Install these before starting:

- Python 3.11
- Git
- A terminal or command prompt
- An OpenAI API key, if you want hybrid/semantic retrieval

The app can still run in keyword-guided mode if the OpenAI key or vector dependencies are unavailable.

## 3. Get the Project

Clone the repository:

```sh
git clone <repository-url>
cd <repository-folder>
```

If you received the project as a zip file, extract it and open a terminal inside the extracted project folder.

## 4. Verify Required Data Files

Make sure these two files are present in the project root:

```text
EU_Post_Approval_Changes_Copy.xlsx
EU Post approval Guidelines.pdf
```

The application expects these exact file names. If either file is missing or renamed, the app may fail to load the reference data.

## 5. Create a Virtual Environment

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On Windows Command Prompt:

```bat
python -m venv .venv
.venv\Scripts\activate.bat
```

On macOS or Linux:

```sh
python3.11 -m venv .venv
source .venv/bin/activate
```

After activation, your terminal should show `(.venv)` near the prompt.

## 6. Install Dependencies

With the virtual environment activated, run:

```sh
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 7. Configure the OpenAI API Key

Use one of the following options.

Option A: Streamlit secrets file

1. Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml`.
2. Edit `.streamlit/secrets.toml`.
3. Add your key:

```toml
OPENAI_API_KEY = "your_openai_api_key_here"
```

Option B: environment variable

On Windows PowerShell:

```powershell
$env:OPENAI_API_KEY="your_openai_api_key_here"
```

On Windows Command Prompt:

```bat
set OPENAI_API_KEY=your_openai_api_key_here
```

On macOS or Linux:

```sh
export OPENAI_API_KEY="your_openai_api_key_here"
```

Do not commit `.streamlit/secrets.toml` or `.env`. They are ignored because they can contain real secrets.

## 8. Run the App Locally

Start the Streamlit application:

```sh
streamlit run app.py
```

Streamlit will print a local URL, usually:

```text
http://localhost:8501
```

Open that URL in a browser.

## 9. Use the App

1. Enter a description of a planned post-approval change.
2. Review the suggested classification.
3. Answer any clarification prompts if the request is ambiguous.
4. Review the required documents and recommended regulatory process.
5. Optionally upload support files in TXT, PDF, CSV, or XLSX format for review.

Example change descriptions:

```text
Change the invented name of the finished product.
We are updating manufacturing details for the product.
A packaging-related change is planned, but the component impact is still unclear.
Administrative information in the dossier needs to be updated.
```

## 10. Run the Command-Line Workflow

The project also has a simple command-line entry point:

```sh
python main.py
```

Enter a change description when prompted. The script will print the classification, required documents, and recommended process.

## 11. Run Tests

Run the regression tests:

```sh
python -m unittest discover -s tests
```

Run tests before making changes and before deploying.

## 12. Troubleshooting

If `streamlit` is not recognized:

```sh
python -m streamlit run app.py
```

If packages fail to import, confirm the virtual environment is activated and reinstall dependencies:

```sh
python -m pip install -r requirements.txt
```

If the app cannot find the Excel or PDF files, confirm they are in the project root and use the exact expected file names.

If OpenAI retrieval fails, check that `OPENAI_API_KEY` is set correctly. The app should still fall back to keyword mode in many cases.

If Streamlit secrets are not found, create `.streamlit/secrets.toml` from `.streamlit/secrets.toml.example`.

## 13. Streamlit Cloud Deployment

1. Push the project to GitHub.
2. Confirm these files are included:
   - `app.py`
   - `requirements.txt`
   - `runtime.txt`
   - `EU_Post_Approval_Changes_Copy.xlsx`
   - `EU Post approval Guidelines.pdf`
3. Confirm these files are not committed:
   - `.streamlit/secrets.toml`
   - `.env`
   - `.venv`
4. In Streamlit Cloud, create a new app from the GitHub repository.
5. Set the main file path to:

```text
app.py
```

6. Add the OpenAI key in Streamlit Cloud app secrets:

```toml
OPENAI_API_KEY = "your_openai_api_key_here"
```

7. Deploy the app.

## 14. New Developer Checklist

Before starting development, confirm:

- Python 3.11 is installed.
- The virtual environment is activated.
- Dependencies are installed from `requirements.txt`.
- The Excel and PDF reference files exist in the project root.
- The OpenAI API key is configured, if semantic retrieval is needed.
- `streamlit run app.py` starts successfully.
- `python -m unittest discover -s tests` passes.
