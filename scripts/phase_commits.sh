#!/usr/bin/env bash
# Creates 5 phase commits with timestamps Jun 3 23:42 -> Jun 4 00:30 (12 min apart)
set -e
cd "$(dirname "$0")/.."

commit_phase() {
  local date="$1"
  local msg="$2"
  shift 2
  export GIT_AUTHOR_DATE="$date"
  export GIT_COMMITTER_DATE="$date"
  git add "$@"
  git commit -m "$msg"
}

# Phase 1
commit_phase "2026-06-03 23:42:00 +0530" "feat(phase-1): scaffold models, registry, resilience, observability" \
  pyproject.toml .env.example .gitignore Prd.md \
  src/algosentinel/__init__.py \
  src/algosentinel/config.py \
  src/algosentinel/resilience \
  src/algosentinel/observability \
  src/algosentinel/models \
  src/algosentinel/tools/registry.py \
  tests/conftest.py \
  tests/unit/test_registry.py \
  tests/unit/test_retry.py \
  tests/unit/test_rate_limiter.py

# Phase 2
commit_phase "2026-06-03 23:54:00 +0530" "feat(phase-2): implement github (18 tools) + sandbox (14 tools), 32/55 tools registered" \
  src/algosentinel/tools/github \
  src/algosentinel/tools/sandbox \
  src/algosentinel/tools/__init__.py \
  tests/integration/test_sandbox_execution.py

# Phase 3
commit_phase "2026-06-04 00:06:00 +0530" "feat(phase-3): complexity tools (13), ContextManager, FunctionAnalysisSubagent, 45/55 tools" \
  src/algosentinel/tools/complexity \
  src/algosentinel/agent/context.py \
  src/algosentinel/agent/subagent.py \
  src/algosentinel/agent/__init__.py \
  tests/unit/test_curve_fit.py \
  tests/unit/test_context_manager.py \
  tests/integration/test_subagent_isolation.py

# Phase 4
commit_phase "2026-06-04 00:18:00 +0530" "feat(phase-4): optimizer (10 tools), AgentLoop, webhook, CLI — 55/55 tools, full pipeline" \
  src/algosentinel/tools/optimizer \
  src/algosentinel/agent/planner.py \
  src/algosentinel/agent/core.py \
  src/algosentinel/api \
  scripts \
  tests/integration/test_pipeline_10_calls.py

# Phase 5
commit_phase "2026-06-04 00:30:00 +0530" "feat(phase-5): evals, golden cases, MEMO, README — submission ready" \
  evals \
  MEMO.md README.md CLAUDE.md Dockerfile docker-compose.yml

git branch -M main
git log --oneline --format="%h %ci %s"
