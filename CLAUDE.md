# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

```bash
conda activate hackathon
cd /gpfs/mariana/home/tayyab/Hackathon
streamlit run app/app.py --server.port 8502
```

**Critical**: always run from the project root (`Hackathon/`), not from inside `app/`. The `sys.path` fix at the top of `app/app.py` depends on the file being run from the project root so `app/` resolves as a package.

## Environment variables

Copy `.env.example` to `.env` and fill in values.

| Variable | Required | Purpose |
|---|---|---|
| `LLM_BACKEND` | No | `gemini` (default), `openai`, or `local` |
| `GOOGLE_API_KEY` | Yes when `LLM_BACKEND=gemini` | Gemini 2.5 Pro/Flash |
| `GEMINI_FAST_MODEL` | No | Tool-calling model (default: `gemini-2.5-flash`) |
| `GEMINI_DEEP_MODEL` | No | Reasoning model (default: `gemini-2.5-pro`) |
| `OPENAI_API_KEY` | Yes when `LLM_BACKEND=openai` | GPT-4o agent |
| `LOCAL_MODEL_URL` | Yes when `LLM_BACKEND=local` | OpenAI-compatible vLLM endpoint |
| `LOCAL_MODEL_NAME` | No | Model name for vLLM |
| `GITHUB_TOKEN` | No | Raises GitHub rate limit 60→5000 req/hr |
| `KAGGLE_USERNAME` + `KAGGLE_KEY` | No | Dataset search |

Google OAuth for per-user chat history is configured in `.streamlit/secrets.toml` as a `[auth]` block — see `.env.example`. Without it, the app falls back to a single `local@localhost` user.

## Architecture

The agent is a **Gemini 2.5 function-calling loop** (`app/agent.py`); OpenAI and local vLLM are supported through a backend adapter layer (`app/llm/`).

1. Streamlit UI (`app/app.py`) calls `agent.run(message, history, attachments)` → returns `{"content": str, "artifacts": list}`.
2. `agent.run()` sends messages + tool schemas through `app/llm/router.py` to the active backend.
3. The model decides which tools to call; `_call_tool()` dispatches to the tool functions.
4. Tool results are appended; the loop repeats. Calls to `find_research_gaps` / `find_similar_theses` pin the rest of the turn to `DEEP_MODEL` (Gemini Pro with thinking).
5. Artifacts from `generate_plot` / `run_analysis` are collected and surfaced in the UI's right-hand panel.

### Backend adapters (`app/llm/`)

- `router.py` — reads `LLM_BACKEND` and returns the right adapter.
- `gemini.py` — wraps `google.genai`. Converts OpenAI-shape messages to Gemini `contents`, our JSON-schema tools to `FunctionDeclaration`, and tool-call responses back to the shape `agent._call_tool` expects. Passes `thinking_config` on deep calls.
- `openai_compat.py` — OpenAI + local-vLLM path (OpenAI-compatible client).
- Returns a uniform `ChatResponse(content, tool_calls, raw_message)`.

### Tools (`app/tools/`)

| Tool function | Source | Notes |
|---|---|---|
| `search_taltech_theses` | Live scrape of `digikogu.taltech.ee` | No auth; CSS selector: `li.list-group-item` |
| `search_papers` | Semantic Scholar API | Free, ~1 RPS limit |
| `search_arxiv` | arXiv API | Fallback when Semantic Scholar returns nothing |
| `search_datasets` | Kaggle API + Zenodo REST | Kaggle needs credentials |
| `get_simulation_tools` | `app/catalog/simulation_tools.yaml` | Cached with `lru_cache` |
| `search_github_repos` | GitHub REST API | `GITHUB_TOKEN` optional |
| `search_taltech_github` | GitHub API, orgs: `TalTech-IVAR`, `taltech` | Same token |
| `get_github_readme` | GitHub API | Returns first 2000 chars |
| `generate_plot` | Plotly spec builder | Kinds: `bar`, `line`, `scatter`, `hist`, `pie` |
| `run_analysis` | Sandboxed subprocess (`-I`, PYTHONNOUSERSITE, timeout 15s) | Emits tables/figures via `emit_table` / `emit_figure` helpers |

`generate_plot` and `run_analysis` return **artifact descriptors** (`{id, kind, mime, title, payload}`) that the UI renders in a Claude-style side panel.

### Features (`app/features/`)

- `citation.py` — generates BibTeX, IEEE, APA strings from a metadata dict
- `gap_finder.py` — runs multiple `search_taltech_theses` calls and classifies coverage density
- `similar_thesis.py` — searches TalTech + Semantic Scholar using an abstract as query
- `bibtex_extractor.py` — scans agent responses for BibTeX blocks and collects them for export

### Storage (`app/storage/`)

- `chats.py` — per-user SQLite persistence (`data/chats.db`, git-ignored). Tables: `chats(id, user_email, title, created_at, updated_at)` and `messages(id, chat_id, role, content, attachments_json, artifacts_json, created_at)`. Every query is parameterised with `user_email` in the WHERE clause so users cannot read each other's history.

### UI (`app/ui/`)

- `artifacts.py` — renders the right-hand artifact panel (Plotly charts, DataFrames with CSV download, code blocks) as tabs.
- `sidebar_history.py` — renders the per-user chat list grouped by Today/Yesterday/Earlier with Rename/Delete per row and a "➕ New chat" button.
- `styles.py`, `assets.py`, `spinner.py` — CSS, logo/avatar loaders, rotating-logo thinking indicator.

### Config (`app/config.py`)

Reads `LLM_BACKEND` once at import and exposes `FAST_MODEL`, `DEEP_MODEL`, `BACKEND_LABEL`, `DATA_DIR`, `CHATS_DB_PATH`. `validate_secrets()` returns a list of human-readable problems (missing `GOOGLE_API_KEY` on `gemini`, missing `OPENAI_API_KEY` on `openai`, missing `LOCAL_MODEL_URL` on `local`). `get_secret()` reads from `st.secrets` first, then `os.environ`.

## Intent routing

There is no mode radio — the agent auto-detects intent from the prompt per rules in `SYSTEM_PROMPT`:

- abstract paste → `find_similar_theses`
- "gap" / "under-researched" → `find_research_gaps`
- "cite", "BibTeX", "APA" → `generate_citation`
- everything else → general search flow (thesis → Semantic Scholar → arXiv)
- "plot" / "analysis" / "compare" / "trend" → `generate_plot` or `run_analysis`

## UI flow

- Google sign-in gate: the main page is blocked by a `st.login("google")` button until `st.user.is_logged_in` is true (falls back to `local@localhost` if `[auth]` is not configured).
- Sidebar: logo, backend label, signed-in email, Sign out, per-user chat history, Export / BibTeX buttons.
- Main area is a 2:1 split: chat on the left, artifact panel on the right.
- A `➕` popover to the left of the chat input exposes file upload (PDF/image) and a "Generate citation" form. Pending uploads are deduplicated by sha1 digest and shown as removable chips before submission.

## LLM backend switching

Default: Gemini 2.5 (Flash for tool-calling, Pro with thinking for deep tasks). Free tier on `GOOGLE_API_KEY`.

To use OpenAI:
1. `LLM_BACKEND=openai`
2. Set `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`).

To use a local vLLM:
1. Submit `slurm/serve_local_model.slurm` on the HPC.
2. Expose the compute node port via ngrok.
3. `LLM_BACKEND=local`, `LOCAL_MODEL_URL=https://xxxx.ngrok-free.app`, optionally `LOCAL_MODEL_NAME`.

## Sandbox limitations

`run_analysis` executes code via `subprocess.run([sys.executable, "-I", "-c", ...], timeout=15, env=scrubbed, cwd=tmpdir)` with `PYTHONNOUSERSITE=1`. This is **not** a hardened sandbox — it is safe because the operator (not an untrusted third party) controls the app, and no secrets are reachable from the subprocess environment or the `/tmp` cwd.

## Streamlit Community Cloud deployment

The HPC firewall blocks inbound ports, so the app is published via Streamlit Community Cloud on a public URL.

1. Push to a public GitHub repo:
   ```bash
   cd /gpfs/mariana/home/tayyab/Hackathon
   git init
   git add .
   git commit -m "feat: initial deploy"
   git remote add origin https://github.com/<user>/taltech-research-assistant.git
   git branch -M main
   git push -u origin main
   ```
2. Go to https://share.streamlit.io → **New app**.
3. Select the repo, branch `main`, main file `app/app.py`, Python 3.11.
4. Under **Advanced settings → Secrets**, paste TOML (not `KEY=VALUE`):
   ```toml
   LLM_BACKEND = "gemini"
   GOOGLE_API_KEY = "AIza..."
   GITHUB_TOKEN = "ghp_..."
   KAGGLE_USERNAME = "..."
   KAGGLE_KEY = "..."
   STREAMLIT_CLOUD = "true"

   [auth]
   redirect_uri = "https://<app>.streamlit.app/oauth2callback"
   cookie_secret = "<32-byte random string>"
   client_id = "<google oauth client id>"
   client_secret = "<google oauth secret>"
   server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
   ```
5. Deploy. The app lives at `https://<app-name>.streamlit.app`.

Note: Streamlit Cloud resets the container on redeploy, so `data/chats.db` is ephemeral. Acceptable for the hackathon; for permanent storage mount a volume or move to Supabase/Postgres.

`app/config.py` reads from `st.secrets` first, then falls back to `os.environ`, so the same code runs locally and on Cloud.

## HuggingFace Spaces deployment (alternative)

```bash
git remote add hf https://huggingface.co/spaces/YOUR_HF_USERNAME/taltech-agent
git push hf main
```

Add secrets as Repository Secrets in the Space settings. The `Dockerfile` runs on port 7860 (HF default) as a non-root user.

## Conda environment

```bash
conda create -n hackathon python=3.11 -y
conda activate hackathon
pip install -r requirements.txt
```
