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

Analyze specific PRs with the full Gemini-driven agent (the model selects every tool):

```bash
python scripts/run_agent.py --repo owner/repo --pr 42 --verbose
```

Audit recent closed PRs:

```bash
python scripts/audit_repo.py --repo owner/repo --last-n 10
```

Run the same end-to-end audit deterministically (no LLM calls — useful for CI or
when you are out of Gemini quota). It fetches the PR, profiles both versions in
Docker, classifies the regression, and posts a review:

```bash
python scripts/full_audit.py --repo owner/repo --pr 42
```

## Models and free-tier limits

The default model is `gemini-2.5-flash` (set via `GEMINI_MODEL`). Note that
`gemini-2.0-flash` was **shut down on 2026-06-01** — if you see a `429` with
`limit: 0`, that is a retired model, not a quota problem. Any current Flash model
works: `gemini-2.5-flash`, `gemini-2.5-flash-lite`, or `gemini-3.5-flash`.

The agent makes one model round-trip per tool call, so a full audit (parent loop
+ subagent) is ~25–35 requests. On a brand-new free-tier key Google currently
caps usage at **20 requests/day/model**, which is not enough for one unattended
run — enable billing or use `scripts/full_audit.py`, which needs no model calls.
The shared rate limiter (`GEMINI_MAX_RPM`) keeps the parent and every subagent
under the per-minute cap from a single token bucket; daily-quota `429`s fail fast
(`QuotaExhaustedError`) instead of burning the remaining allowance on retries.

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

## Verification

Latest local run on this machine:

- `pytest tests/` — **23 passed, 3 skipped** (the 3 skips are live-Gemini subagent
  tests, which skip without `GEMINI_API_KEY` in the environment)
- `python evals/harness.py` — **Precision 1.00, Recall 1.00, F1 1.00** across 6
  evaluations over 5 golden cases
- `python scripts/run_agent.py` — live Gemini run where the parent autonomously
  called `get_pr_details → get_pr_diff → list_pr_files → get_file_content → extract_function
  → spawn_function_analysis_subagent`, and the subagent ran its own scoped chain
  (`create_sandbox → profile_runtime ×2 → fit_complexity_curves ×2 → infer_complexity_class`)
  in an isolated context
- `python scripts/full_audit.py` — deterministic end-to-end audit that posts a real
  PR review (no model quota required)

## Architecture

- **55 tools** in four namespaces: `github`, `sandbox`, `complexity`, `optimizer`
- **FunctionAnalysisSubagent**: isolated Gemini client and message history; sandbox + complexity tools only
- **ContextManager**: compresses tool history every 6 calls; plan never compressed
- **R5 pipeline**: `profile_runtime` → `fit_complexity_curves` → `infer_complexity_class` → `detect_regression` → `generate_pr_review_body`

See `MEMO.md` for design notes and `Prd.md` for the full specification.
