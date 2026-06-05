# AlgoSentinel

An autonomous agent that reviews GitHub pull requests for **algorithmic complexity regressions** — the class of bug where a function quietly changes from `O(n)` to `O(n²)`, keeps passing its unit tests, and only falls over at scale in production.

Instead of guessing from static analysis, AlgoSentinel profiles both versions of a changed function inside a Docker sandbox across growing input sizes, fits the timings to candidate complexity curves, and posts a PR review backed by an actual growth curve.

---

## How it works

A Gemini-driven parent agent plans the audit and selects tools; the heavy analysis is delegated to an isolated subagent.

```
PR opened ──> AgentLoop (parent, 55 tools)
                 │  get_pr_details → get_pr_diff → list_pr_files → get_file_content
                 │  for each changed function:
                 └──> FunctionAnalysisSubagent      (isolated context, scoped to sandbox + complexity)
                          create_sandbox → profile_runtime (pre) → profile_runtime (post)
                          → fit_complexity_curves → infer_complexity_class
                          → detect_regression → classify_severity
                          ⇒ returns a typed ComplexityReport
                 │  generate_pr_review_body  ⇐ reports
                 └──> post_pr_review
```

- **55 tools across 4 namespaces** — `github` (18), `sandbox` (14), `complexity` (13), `optimizer` (10). Each tool registers with a Pydantic input model; the Gemini function schema is derived from it and dispatched by name from a dictionary, so the registry stays flat as it grows rather than collapsing into conditional routing.
- **Subagent orchestration** — `FunctionAnalysisSubagent` runs its own model client and message history with a tool set scoped to `sandbox` + `complexity` only, and returns a structured `ComplexityReport` to the parent.
- **Long-horizon execution** — a single audit comfortably exceeds 20 tool calls. `ContextManager` pins the plan in every system prompt and compresses older tool history so the agent keeps coherence across a long session.
- **Composable tools** — the profiler's structured output feeds the complexity chain, which feeds the review-body generator; tools chain rather than dead-end.
- **Production scaffolding** — structlog JSON logging, tenacity retries with exponential backoff + jitter, a shared token-bucket rate limiter, a typed error hierarchy (retryable vs. fatal), an eval harness, and unit + integration tests.

## Project layout

```
src/algosentinel/
  agent/         AgentLoop (parent), FunctionAnalysisSubagent, ContextManager, planner
  tools/         github · sandbox · complexity · optimizer  (+ registry)
  resilience/    typed errors, retry, rate limiter
  observability/ structlog config
  api/           FastAPI webhook
  models/        Pydantic models (tools, reports, sandbox)
scripts/         run_agent.py · audit_repo.py · full_audit.py · demo.py
evals/           harness.py · golden cases
tests/           unit/ · integration/
```

## Requirements

- Python 3.11+
- Docker (sandbox profiling and integration tests)
- A [Google AI Studio](https://aistudio.google.com/) API key (`GEMINI_API_KEY`)
- A GitHub personal access token (`GITHUB_TOKEN`)

## Setup

```bash
cp .env.example .env        # add your keys
pip install -e ".[dev]"
```

## Run

With Docker Compose (serves the webhook):

```bash
docker compose up --build
# health: http://localhost:8000/health   (asserts tool_count >= 55)
# webhook: POST /webhook/github  for pull_request events (opened, synchronize)
```

From the CLI — the full Gemini-driven agent, where the model selects every tool:

```bash
python scripts/run_agent.py --repo owner/repo --pr 42 --verbose
```

The same audit, run deterministically with no model calls (handy for CI or when
the Gemini quota is spent) — it profiles in Docker and posts the review:

```bash
python scripts/full_audit.py --repo owner/repo --pr 42
```

Eval harness and tests:

```bash
python evals/harness.py
pytest tests/unit/
pytest tests/integration/   # Docker required; live subagent tests need GEMINI_API_KEY
```

## Models and free-tier limits

The default is `gemini-2.5-flash` (`GEMINI_MODEL`). Heads-up: `gemini-2.0-flash`
was **shut down on 2026-06-01** — if you ever see a `429` with `limit: 0`, that's a
retired model, not throttling. Any current Flash model works (`gemini-2.5-flash`,
`gemini-2.5-flash-lite`, `gemini-3.5-flash`).

The agent makes one model round-trip per tool call, so a full audit is ~25–35
requests. A brand-new free-tier key is currently capped at ~20 requests/day/model,
which isn't enough for one unattended live run — enable billing, or use
`scripts/full_audit.py`. The rate limiter is shared across the parent and every
subagent (one bucket per API key), and per-day quota errors fail fast rather than
retrying into the same cap.

## Design notes

See [`MEMO.md`](MEMO.md) for what was built, what was cut, and the one design
decision (empirical profiling over static AST analysis) worth defending.
