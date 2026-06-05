# AlgoSentinel — Agent Guide

## Project

Detect algorithmic complexity regressions in GitHub PRs using empirical Docker profiling and Gemini-orchestrated tools.

## Layout

- `src/algosentinel/tools/` — 55 `@tool`-registered functions (import modules to register)
- `src/algosentinel/agent/` — `AgentLoop`, `ContextManager`, `FunctionAnalysisSubagent`
- `evals/golden/` — regression detection golden cases
- `tests/unit/` — no Docker; `tests/integration/` — Docker (+ API key for subagent)

## Conventions

- Tool names: `namespace__function_name`; dispatch via `ToolRegistry`, never if/elif sequences
- All tool I/O: Pydantic v2 models
- GitHub and Gemini external calls: `@with_retry()`; respect `TokenBucketRateLimiter`
- Plan in `ContextManager` is never compressed

## Commands

```bash
pip install -e ".[dev]"
pytest tests/unit/
python evals/harness.py
python scripts/run_agent.py --repo owner/repo --pr 1
```

## R5 chain (must preserve)

`profile_runtime` → `fit_complexity_curves` → `infer_complexity_class` → `detect_regression` → `generate_pr_review_body`
