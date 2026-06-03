# AlgoSentinel

AlgoSentinel watches GitHub pull requests for **algorithmic complexity regressions**. When a Python function changes from O(n) to O(n²), unit tests still pass — but runtime can explode at scale. This agent profiles both versions in Docker, fits timing curves, and posts actionable PR reviews.

## Requirements

- Python 3.11+
- Docker (for sandbox profiling and integration tests)
- [Google AI Studio](https://aistudio.google.com/) API key (`GEMINI_API_KEY`)
- GitHub personal access token (`GITHUB_TOKEN`)

## Setup

```bash
cp .env.example .env
# Edit .env with your API keys

pip install -e ".[dev]"
```

## Run with Docker Compose

```bash
docker compose up --build
```

Health check: http://localhost:8000/health (expects `tool_count >= 55`).

Configure a GitHub webhook pointing to `POST /webhook/github` for `pull_request` events (`opened`, `synchronize`).

## CLI

Analyze specific PRs:

```bash
python scripts/run_agent.py --repo owner/repo --pr 42
```

Audit recent closed PRs:

```bash
python scripts/audit_repo.py --repo owner/repo --last-n 10
```

## Evals

Golden-case regression detection (requires Docker):

```bash
python evals/harness.py
```

## Tests

```bash
pytest tests/unit/
pytest tests/integration/   # Docker required; subagent tests need GEMINI_API_KEY
```

## Architecture

- **55 tools** in four namespaces: `github`, `sandbox`, `complexity`, `optimizer`
- **FunctionAnalysisSubagent**: isolated Gemini client and message history; sandbox + complexity tools only
- **ContextManager**: compresses tool history every 6 calls; plan never compressed
- **R5 pipeline**: `profile_runtime` → `fit_complexity_curves` → `infer_complexity_class` → `detect_regression` → `generate_pr_review_body`

See `MEMO.md` for design notes and `Prd.md` for the full specification.
