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

Copy `.env.example` to `.env` and fill in values. Required for most tools:

| Variable | Required | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | Yes (default backend) | GPT-4o agent |
| `GITHUB_TOKEN` | No | Raises GitHub rate limit 60→5000 req/hr |
| `KAGGLE_USERNAME` + `KAGGLE_KEY` | No | Dataset search |
| `LOCAL_MODEL_URL` | No | Switch to local vLLM (see below) |
| `LOCAL_MODEL_NAME` | No | Model name for vLLM (default: `google/gemma-2-27b-it`) |

## Architecture

The agent is a **GPT-4o function-calling loop** (`app/agent.py`):
1. Streamlit UI (`app/app.py`) calls `agent.run(message, history)`
2. `agent.run()` sends messages + 9 tool schemas to the OpenAI API
3. GPT-4o decides which tools to call; `_call_tool()` dispatches to the tool functions
4. Tool results are appended as `role: tool` messages; the loop repeats until no more tool calls
5. Final text response is returned to the UI

### Tools (`app/tools/`)

| Tool function | Source | Notes |
|---|---|---|
| `search_taltech_theses` | Live scrape of `digikogu.taltech.ee` | No auth; CSS selector: `li.list-group-item` |
| `search_papers` | Semantic Scholar API | Free, ~1 RPS limit |
| `search_datasets` | Kaggle API + Zenodo REST | Kaggle needs credentials |
| `get_simulation_tools` | `app/catalog/simulation_tools.yaml` | Cached with `lru_cache` |
| `search_github_repos` | GitHub REST API | `GITHUB_TOKEN` optional |
| `search_taltech_github` | GitHub API, orgs: `TalTech-IVAR`, `taltech` | Same token |
| `get_github_readme` | GitHub API | Returns first 2000 chars |

### Features (`app/features/`)

- `citation.py` — generates BibTeX, IEEE, APA strings from a metadata dict
- `gap_finder.py` — runs multiple `search_taltech_theses` calls and classifies coverage density
- `similar_thesis.py` — searches TalTech + Semantic Scholar using an abstract as query

### Config (`app/config.py`)

Sets `client`, `MODEL`, `BACKEND_LABEL` once at import. If `LOCAL_MODEL_URL` is set, uses that as an OpenAI-compatible base URL (vLLM); otherwise uses `OPENAI_API_KEY` with `gpt-4o`. Missing `OPENAI_API_KEY` emits a `warnings.warn` (not an exception) so modules can import cleanly during testing.

## LLM backend switching

To use a local vLLM instead of the OpenAI API:
1. Submit `slurm/serve_local_model.slurm` on the HPC
2. Expose the compute node port via ngrok
3. Set `LOCAL_MODEL_URL=https://xxxx.ngrok-free.app` in `.env` (or HF Space secrets)
4. Optionally set `LOCAL_MODEL_NAME` — defaults to `google/gemma-2-27b-it`

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
   OPENAI_API_KEY = "sk-..."
   GITHUB_TOKEN = "ghp_..."
   KAGGLE_USERNAME = "..."
   KAGGLE_KEY = "..."
   STREAMLIT_CLOUD = "true"
   ```
5. Deploy. The app lives at `https://<app-name>.streamlit.app`.

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
