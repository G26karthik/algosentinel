# AlgoSentinel — MEMO

## What I Built

AlgoSentinel is an autonomous agent that detects algorithmic complexity regressions in GitHub pull requests. The implementation includes:

- **55 registered tools** across `github` (18), `sandbox` (14), `complexity` (13), and `optimizer` (10), with dictionary-based dispatch and Pydantic-derived Gemini schemas
- **FunctionAnalysisSubagent** with its own `genai.Client` and `_messages` list, scoped to sandbox/complexity tools
- **AgentLoop** parent orchestrator with **ContextManager** compression every 6 tool calls and full plan retention in every system prompt
- **Docker sandbox** profiling at multiple input sizes, **scipy** curve fitting, and regression detection via `ComplexityOrder` comparison
- **FastAPI webhook**, CLI scripts, eval harness with 5 golden cases, unit and integration tests
- Production scaffolding: structlog JSON logging, tenacity `@with_retry`, `TokenBucketRateLimiter`, typed exception hierarchy

Unit tests for registry, curve fit, context compression, retry, and rate limiter run without Docker. Sandbox and pipeline integration tests require Docker; subagent tests require `GEMINI_API_KEY`.

## What I Cut

- **Full autonomous fix-PR loop in CI**: optimizer tools and GitHub branch/PR tools exist, but end-to-end fix verification depends on live Gemini + GitHub credentials in production runs
- **JavaScript support**: Python functions only
- **Parallel subagent execution**: subagents run serially when the parent spawns them
- **merge_pr** GitHub tool: input model defined in spec for reviews module context but not exposed as a separate registered tool (18 github tools per spec list)
- **Memory profiling (tracemalloc)**: implemented but not on the critical path for the subagent prompt

## What Additional Time Would Address

- Parallel subagent execution for multi-function PRs
- Caching timing results per function SHA to skip re-profiling unchanged code
- Richer input generators for graphs/trees and property-based correctness checks
- Dashboard for complexity drift across PR history
- Hardening `validate_correctness` for functions with side effects

## One Design Decision I Would Defend

**Empirical runtime measurement over pure static AST analysis.**

Static loop nesting misses library calls (e.g. `sorted()` inside a loop), mis-estimates average-case dict behavior, and produces weaker review comments. Measuring at n ∈ {10, …, 10000} and reporting fitted class with R² gives evidence engineers can act on. The cost is Docker startup per sandbox; the webhook runs analysis asynchronously so developers are not blocked.
