# AlgoSentinel — Build Specification (Model-Friendly Rewrite)

> **What this document is:** Step-by-step instructions for building AlgoSentinel.
> Read the entire document before writing any code. Implement every section exactly
> as described. Nothing is optional unless explicitly marked.

---

## Table of Contents

1. [What You Are Building](#1-what-you-are-building)
2. [Five Requirements That Must Be Met](#2-five-requirements-that-must-be-met)
3. [Exact Folder Structure to Create](#3-exact-folder-structure-to-create)
4. [Dependencies](#4-dependencies)
5. [Environment Variables](#5-environment-variables)
6. [Data Models](#6-data-models)
7. [Tool Registry](#7-tool-registry)
8. [All 55 Tools](#8-all-55-tools)
9. [Context Manager](#9-context-manager)
10. [Subagent](#10-subagent)
11. [Main Agent Loop](#11-main-agent-loop)
12. [Resilience Layer](#12-resilience-layer)
13. [Observability](#13-observability)
14. [Eval Harness](#14-eval-harness)
15. [Tests](#15-tests)
16. [FastAPI Webhook](#16-fastapi-webhook)
17. [CLI Scripts](#17-cli-scripts)
18. [Dockerfile and Compose](#18-dockerfile-and-compose)
19. [MEMO.md](#19-memomd)
20. [Build Order and Commit Points](#20-build-order-and-commit-points)
21. [Final Checklist](#21-final-checklist)

---

## 1. What You Are Building

AlgoSentinel watches GitHub pull requests for **algorithmic complexity regressions**.
When a Python function changes from `O(n)` to `O(n²)`, unit tests still pass — but the
function will be 100× slower at n=10,000. AlgoSentinel catches this before it ships.

**Full pipeline (end to end):**

```
PR opened on GitHub
  → Webhook fires → AgentLoop starts
  → Fetch diff from GitHub API
  → Find changed Python functions
  → For each function: spawn FunctionAnalysisSubagent
      → Subagent: run function at n=10, 100, 1000, 10000 in a Docker sandbox
      → Subagent: fit timing data to complexity curves (O(n), O(n²), etc.)
      → Subagent: compare pre-PR and post-PR complexity classes
      → Subagent: return ComplexityReport to parent
  → If regression found: generate optimized fix with Gemini
  → Verify fix restores original complexity class
  → Post review comment on PR with plain-English explanation
  → Open a new fix PR with the corrected code
  → Return AuditSummary
```

No step is optional. The agent must complete the full pipeline autonomously.

---

## 2. Five Requirements That Must Be Met

These are evaluated by reading the code. Every item must be provable without running it.

### R1 — 55 tools across 4 namespaces

- Namespaces: `github` (18 tools), `sandbox` (14 tools), `complexity` (13 tools), `optimizer` (10 tools)
- The model decides which tool to call next — the code never hardcodes a sequence like `if step == 3: call_tool_X()`
- The registry dispatches by dictionary lookup, not `if/elif` chains
- Every tool's input and output is a Pydantic v2 model
- JSON schemas for the Gemini API are derived from these Pydantic models at runtime — never written by hand

### R2 — Real subagent orchestration

- `github.spawn_function_analysis_subagent` spawns a `FunctionAnalysisSubagent`
- The subagent creates its **own** `genai.Client` object (separate Python object, not the parent's)
- The subagent maintains its **own** `messages` list (separate list, never shared with parent)
- The subagent can only call tools in `sandbox` and `complexity` namespaces
- The subagent makes at least 5 real Gemini API calls internally
- The subagent returns a typed `ComplexityReport` Pydantic model to the parent

A function that the parent calls and labels "subagent" does **not** satisfy R2. It must be a
separate object making separate API calls.

### R3 — Long-horizon execution (25+ tool calls, no plan drift)

- The agent can audit 10 PRs in a single session, making 25+ tool calls without forgetting its goal
- `ContextManager` is a real class in `agent/context.py`
- Every 6 tool calls, `ContextManager._compress()` runs: it summarizes the last 6 calls into text and discards the raw records
- The **Plan** (goal, repo, PR list, step statuses) is **never compressed** — it always appears in full in every system prompt sent to Gemini

### R4 — Production scaffolding

All of the following must exist in code (not comments):

- Structured JSON logging on every tool call: namespace, tool name, duration_ms, success
- `@with_retry` decorator on all GitHub API calls and all Gemini API calls. Uses tenacity with exponential backoff + jitter. Retries `RetryableError` subtypes. Never retries `FatalError` subtypes.
- `TokenBucketRateLimiter`: caps Gemini calls at 14 per minute (configurable via env var). Thread-safe.
- Typed exception hierarchy: `AlgoSentinelError` → `RetryableError` / `FatalError` → `ToolError` → `GitHubToolError`, `SandboxError`, `ComplexityInferenceError`
- Eval harness: 5 golden test cases, measuring regression detection precision/recall and fix success rate
- Unit tests: registry coherence, curve fitting, context compression, retry logic, rate limiter
- Integration tests: sandbox execution (requires Docker), subagent isolation, 10-call pipeline

### R5 — Composable tool I/O (one tool's output is the next tool's input)

This exact chain must be documented in code comments AND implemented:

```
sandbox.profile_runtime
  → returns list[TimingPoint]
  → consumed by complexity.fit_complexity_curves
  → returns list[CurveFit]
  → consumed by complexity.infer_complexity_class
  → returns ComplexityClass
  → consumed by complexity.detect_regression
  → returns RegressionResult
  → consumed by optimizer.generate_pr_review_body
  → returns str (the PR review comment)
```

---

## 3. Exact Folder Structure to Create

Create **exactly** this layout. Do not add or remove top-level directories.

```
algosentinel/
├── MEMO.md
├── README.md
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── CLAUDE.md
├── src/
│   └── algosentinel/
│       ├── __init__.py
│       ├── config.py
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── core.py
│       │   ├── context.py
│       │   ├── planner.py
│       │   └── subagent.py
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── registry.py
│       │   ├── github/
│       │   │   ├── __init__.py
│       │   │   ├── pr.py
│       │   │   ├── files.py
│       │   │   ├── reviews.py
│       │   │   └── branches.py
│       │   ├── sandbox/
│       │   │   ├── __init__.py
│       │   │   ├── executor.py
│       │   │   ├── profiler.py
│       │   │   └── generator.py
│       │   ├── complexity/
│       │   │   ├── __init__.py
│       │   │   ├── inference.py
│       │   │   ├── curve_fit.py
│       │   │   ├── ast_scan.py
│       │   │   └── annotator.py
│       │   └── optimizer/
│       │       ├── __init__.py
│       │       ├── generator.py
│       │       ├── validator.py
│       │       └── reporter.py
│       ├── models/
│       │   ├── __init__.py
│       │   ├── github.py
│       │   ├── sandbox.py
│       │   ├── complexity.py
│       │   ├── reports.py
│       │   └── tools.py
│       ├── observability/
│       │   ├── __init__.py
│       │   ├── logger.py
│       │   └── tracer.py
│       ├── resilience/
│       │   ├── __init__.py
│       │   ├── retry.py
│       │   ├── rate_limiter.py
│       │   └── errors.py
│       └── api/
│           ├── __init__.py
│           └── webhook.py
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_registry.py
│   │   ├── test_curve_fit.py
│   │   ├── test_context_manager.py
│   │   ├── test_retry.py
│   │   └── test_rate_limiter.py
│   └── integration/
│       ├── test_sandbox_execution.py
│       ├── test_subagent_isolation.py
│       └── test_pipeline_10_calls.py
├── evals/
│   ├── harness.py
│   ├── metrics.py
│   └── golden/
│       ├── case_001_on_to_on2.json
│       ├── case_002_onlogn_to_on2.json
│       ├── case_003_no_regression.json
│       ├── case_004_on2_to_on_improvement.json
│       └── case_005_multi_function_mixed.json
└── scripts/
    ├── run_agent.py
    └── audit_repo.py
```

---

## 4. Dependencies

Create `pyproject.toml` with this content exactly:

```toml
[project]
name = "algosentinel"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "google-genai>=1.0.0",
    "pydantic>=2.7.0",
    "pydantic-settings>=2.3.0",
    "fastapi>=0.111.0",
    "uvicorn[standard]>=0.30.0",
    "PyGithub>=2.3.0",
    "httpx>=0.27.0",
    "tenacity>=8.4.0",
    "structlog>=24.2.0",
    "scipy>=1.13.0",
    "numpy>=1.26.0",
    "docker>=7.1.0",
    "rich>=13.7.0",
    "click>=8.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "pytest-mock>=3.14.0",
    "ruff>=0.4.0",
    "mypy>=1.10.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/algosentinel"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

---

## 5. Environment Variables

Create `.env.example` with this content:

```bash
# Required — get these from Google AI Studio and GitHub
GEMINI_API_KEY=your_google_ai_studio_api_key_here
GITHUB_TOKEN=your_github_personal_access_token_here
GITHUB_WEBHOOK_SECRET=your_webhook_secret_here

# Agent behavior — these have safe defaults, only change if needed
GEMINI_MODEL=gemini-2.0-flash
GEMINI_MAX_RPM=14
GEMINI_MAX_TOKENS=8192
CONTEXT_COMPRESS_EVERY_N_CALLS=6
MAX_INPUT_SIZE_BENCHMARK=10000
SANDBOX_TIMEOUT_SECONDS=30
SANDBOX_DOCKER_IMAGE=python:3.11-slim

# Complexity thresholds
MIN_REGRESSION_CONFIDENCE=0.85
SEVERITY_CRITICAL_THRESHOLD=2

# Observability
LOG_LEVEL=INFO
LOG_FORMAT=json
```

Create `src/algosentinel/config.py`:

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API keys
    gemini_api_key: str
    github_token: str
    github_webhook_secret: str = ""

    # Agent behavior
    gemini_model: str = "gemini-2.0-flash"
    gemini_max_rpm: int = 14
    gemini_max_tokens: int = 8192
    context_compress_every_n_calls: int = 6
    max_input_size_benchmark: int = 10000
    sandbox_timeout_seconds: int = 30
    sandbox_docker_image: str = "python:3.11-slim"

    # Complexity thresholds
    min_regression_confidence: float = 0.85
    severity_critical_threshold: int = 2

    # Observability
    log_level: str = "INFO"
    log_format: str = "json"

    class Config:
        env_file = ".env"

settings = Settings()
```

---

## 6. Data Models

These are the typed contracts between tools. Every tool consumes and returns these models.
Never use raw `dict` as a tool's input or output type.

### `models/sandbox.py`

```python
from pydantic import BaseModel, Field
from typing import Any, Optional

class TimingPoint(BaseModel):
    """
    One data point from profiling a function at a specific input size.
    Output of sandbox.profile_runtime.
    Input to complexity.fit_complexity_curves.
    """
    input_size: int           # n — the input size used
    elapsed_ms: float         # mean execution time in milliseconds
    std_dev_ms: float = 0.0   # standard deviation across runs
    runs: int = 5             # how many times we ran at this size

class MemoryPoint(BaseModel):
    input_size: int
    peak_bytes: int

class ExecutionResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    elapsed_ms: float

class BenchmarkPoint(BaseModel):
    input_size: int
    pre_elapsed_ms: float   # time for the old (pre-PR) version
    post_elapsed_ms: float  # time for the new (post-PR) version
    ratio: float            # post / pre — values > 1.0 mean the new version is slower

class BenchmarkPairResult(BaseModel):
    """Output of sandbox.benchmark_function_pair."""
    function_name: str
    points: list[BenchmarkPoint]

class CorrectnessResult(BaseModel):
    is_correct: bool
    failed_inputs: list[Any]
    error_message: Optional[str] = None

class SandboxStatus(BaseModel):
    sandbox_id: str
    is_healthy: bool
    container_id: Optional[str] = None

class InstallResult(BaseModel):
    success: bool
    packages_installed: list[str]
    error: Optional[str] = None

class FunctionCode(BaseModel):
    """
    A single Python function extracted from a file.
    Output of sandbox.extract_function.
    Primary input to FunctionAnalysisSubagent.
    """
    function_name: str
    source_code: str
    file_path: str
    line_start: int
    line_end: int
    dependencies: list[str] = Field(default_factory=list)
```

### `models/complexity.py`

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional
from enum import IntEnum

class ComplexityOrder(IntEnum):
    """
    Integer enum so we can compare orders: QUADRATIC > LINEAR means regression.
    Used in detect_regression: if post.order > pre.order, it's a regression.
    """
    CONSTANT    = 1   # O(1)
    LOG         = 2   # O(log n)
    LINEAR      = 3   # O(n)
    NLOGN       = 4   # O(n log n)
    QUADRATIC   = 5   # O(n^2)
    CUBIC       = 6   # O(n^3)
    EXPONENTIAL = 7   # O(2^n)

COMPLEXITY_NOTATIONS = {
    ComplexityOrder.CONSTANT:    "O(1)",
    ComplexityOrder.LOG:         "O(log n)",
    ComplexityOrder.LINEAR:      "O(n)",
    ComplexityOrder.NLOGN:       "O(n log n)",
    ComplexityOrder.QUADRATIC:   "O(n^2)",
    ComplexityOrder.CUBIC:       "O(n^3)",
    ComplexityOrder.EXPONENTIAL: "O(2^n)",
}

class CurveFit(BaseModel):
    """
    Result of fitting timing data to one specific complexity function.
    Output of complexity.fit_complexity_curves (returns a list of these).
    Input to complexity.infer_complexity_class.
    """
    complexity_class: str    # e.g. "O(n^2)"
    order: ComplexityOrder
    r_squared: float         # 0.0 to 1.0 — how well the curve fits the data
    coefficients: list[float]
    is_best_fit: bool = False  # True for the one with the highest r_squared

class ComplexityClass(BaseModel):
    """
    The inferred complexity class for a function.
    Output of complexity.infer_complexity_class.
    Input to complexity.detect_regression (called twice: once for pre, once for post).
    """
    notation: str           # e.g. "O(n^2)"
    order: ComplexityOrder
    confidence: float       # 0.0 to 1.0
    supporting_r_squared: float
    all_fits: list[CurveFit]

class RegressionResult(BaseModel):
    """
    The verdict on whether a complexity regression occurred.
    Output of complexity.detect_regression.
    Input to optimizer.generate_pr_review_body.
    """
    is_regression: bool
    severity: Literal["none", "minor", "moderate", "critical"]
    pre_class: ComplexityClass
    post_class: ComplexityClass
    orders_worse: int   # post.order - pre.order. 0 means no regression.
    confidence: float

class ASTComplexityHints(BaseModel):
    """Output of complexity.scan_ast_for_hints. Static analysis results."""
    max_loop_nesting_depth: int
    has_recursive_calls: bool
    estimated_class: Optional[str] = None
    hot_paths: list[str] = Field(default_factory=list)
    suspicious_patterns: list[str] = Field(default_factory=list)

class ConfidenceInterval(BaseModel):
    lower: float
    upper: float
    mean: float

class TheoreticalEstimate(BaseModel):
    estimated_class: str
    reasoning: str
    confidence: float
```

### `models/reports.py`

```python
from pydantic import BaseModel, Field
from typing import Optional
from .sandbox import TimingPoint, CorrectnessResult
from .complexity import RegressionResult, ASTComplexityHints, ComplexityClass

class ComplexityReport(BaseModel):
    """
    The typed result that FunctionAnalysisSubagent returns to the parent agent.
    This is the primary boundary object in the system — everything the parent
    needs to know about one function's complexity analysis.
    """
    function_name: str
    file_path: str
    pre_class: ComplexityClass
    post_class: ComplexityClass
    regression: RegressionResult
    evidence: list[TimingPoint]           # the raw timing data that supports the verdict
    ast_hints: ASTComplexityHints
    explanation: str                      # plain English for the PR review comment
    fix_generated: bool
    fix_code: Optional[str] = None
    fix_verified: bool = False
    fix_correctness: Optional[CorrectnessResult] = None
    subagent_tool_calls_used: int = 0     # how many tools the subagent called internally

class AuditSummary(BaseModel):
    """Final result returned by AgentLoop.run()."""
    repo: str
    prs_audited: int
    functions_analyzed: int
    regressions_found: int
    regressions_critical: int
    regressions_moderate: int
    fixes_generated: int
    fixes_verified: int
    fix_prs_opened: list[str]
    total_tool_calls: int
    session_duration_seconds: float
    reports: list[ComplexityReport]
```

### `models/tools.py`

```python
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Optional

class ToolCallRecord(BaseModel):
    """Log entry for one tool call. Stored in ContextManager.tool_history."""
    call_number: int
    namespace: str
    tool_name: str
    input_summary: str    # first 100 chars of the input, for compression
    result_summary: str   # first 150 chars of the result, for compression
    duration_ms: float
    success: bool
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class Step(BaseModel):
    id: str
    description: str
    status: str = "pending"   # pending | in_progress | done | failed
    tool_calls: list[str] = Field(default_factory=list)

class Plan(BaseModel):
    """
    The agent's execution plan. NEVER compressed out of context.
    Always included in full in every system prompt sent to Gemini.
    """
    goal: str
    repo: str
    pr_numbers: list[int]
    steps: list[Step]
    created_at: datetime = Field(default_factory=datetime.utcnow)
    current_step_id: Optional[str] = None

class Checkpoint(BaseModel):
    """A compressed snapshot of N tool calls, created during context compression."""
    call_number: int
    summary: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    findings_so_far: list[str] = Field(default_factory=list)
```

### `models/github.py`

```python
from pydantic import BaseModel, Field
from typing import Optional

class ChangedFile(BaseModel):
    filename: str
    status: str   # added | modified | removed | renamed
    additions: int
    deletions: int
    patch: Optional[str] = None

class PRDetails(BaseModel):
    number: int
    title: str
    body: Optional[str]
    head_sha: str    # the SHA of the PR branch head
    base_sha: str    # the SHA of the base branch
    head_branch: str
    base_branch: str
    author: str
    created_at: str

class Diff(BaseModel):
    files: list[ChangedFile]
    total_additions: int
    total_deletions: int

class ReviewComment(BaseModel):
    path: str     # file path
    line: int     # line number in the file
    body: str     # the comment text
    side: str = "RIGHT"

class ReviewResult(BaseModel):
    review_id: int
    state: str
    url: str

class Branch(BaseModel):
    name: str
    sha: str

class MergeResult(BaseModel):
    merged: bool
    message: str
    sha: Optional[str] = None
```

---

## 7. Tool Registry

Create `src/algosentinel/tools/registry.py` with the following implementation.

**Key points about the registry:**
- It is a singleton (one shared instance for the whole process)
- Tools register themselves at import time using the `@tool` decorator
- `dispatch()` works by dictionary lookup — no `if/elif`
- `get_function_declarations()` builds Gemini-compatible tool schemas from Pydantic models automatically

```python
from dataclasses import dataclass
from typing import Callable, Any, Optional
from google.genai import types as genai_types
import structlog

from algosentinel.resilience.errors import ToolError

logger = structlog.get_logger()

@dataclass
class ToolDefinition:
    namespace: str
    name: str           # always "namespace__function_name"
    func: Callable
    description: str
    input_model: type   # must be a Pydantic BaseModel subclass
    output_model: type

class ToolRegistry:
    """
    Global tool registry. Singleton.

    Usage:
        registry = ToolRegistry.get()
        registry.tool_count()         # → int
        registry.dispatch("github__get_pr_details", {"repo": "...", "pr_number": 1})
    """
    _instance: Optional["ToolRegistry"] = None
    _tools: dict[str, ToolDefinition] = {}

    @classmethod
    def get(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(
        self,
        namespace: str,
        func: Callable,
        description: str,
        input_model: type,
        output_model: type,
    ) -> None:
        full_name = f"{namespace}__{func.__name__}"
        self._tools[full_name] = ToolDefinition(
            namespace=namespace,
            name=full_name,
            func=func,
            description=description,
            input_model=input_model,
            output_model=output_model,
        )
        logger.debug("tool_registered", name=full_name)

    def get_function_declarations(
        self,
        namespaces: Optional[list[str]] = None,
    ) -> list[genai_types.FunctionDeclaration]:
        """
        Build Gemini FunctionDeclaration objects from Pydantic model JSON schemas.
        This is never hand-written — always derived from the models.
        Filter by namespace if provided (used by subagent to get scoped tool set).
        """
        declarations = []
        for tool_def in self._tools.values():
            if namespaces and tool_def.namespace not in namespaces:
                continue
            schema = tool_def.input_model.model_json_schema()
            declarations.append(
                genai_types.FunctionDeclaration(
                    name=tool_def.name,
                    description=tool_def.description,
                    parameters=schema,
                )
            )
        return declarations

    def dispatch(self, tool_name: str, raw_args: dict) -> Any:
        """
        Execute a tool by name. Validates input against Pydantic model first.
        Raises ToolError (not KeyError) for unknown tool names.
        """
        if tool_name not in self._tools:
            raise ToolError(f"Unknown tool: {tool_name}. Available: {list(self._tools.keys())}")
        tool_def = self._tools[tool_name]
        validated_input = tool_def.input_model(**raw_args)
        return tool_def.func(validated_input)

    def tool_count(self) -> int:
        return len(self._tools)

    def namespaces(self) -> list[str]:
        return list({t.namespace for t in self._tools.values()})


def tool(namespace: str, description: str, input_model: type, output_model: type):
    """
    Decorator that registers a function as a tool in the global ToolRegistry.

    Usage:
        @tool(
            namespace="github",
            description="Fetch PR details including SHA and branch info.",
            input_model=GetPRDetailsInput,
            output_model=PRDetails,
        )
        def get_pr_details(inp: GetPRDetailsInput) -> PRDetails:
            ...
    """
    def decorator(func: Callable) -> Callable:
        ToolRegistry.get().register(namespace, func, description, input_model, output_model)
        return func
    return decorator
```

---

## 8. All 55 Tools

### 8.1 GitHub Tools — `tools/github/` (18 tools)

Put these in the appropriate files (`pr.py`, `files.py`, `reviews.py`, `branches.py`).
All GitHub tools use `PyGithub`. Inject the GitHub client from `settings.github_token`.
Wrap every GitHub API call with `@with_retry()`.

**Input models** (define these at the top of the relevant file):

```python
# pr.py
class GetPRDetailsInput(BaseModel):
    repo: str        # format: "owner/repo"
    pr_number: int

class GetPRDiffInput(BaseModel):
    repo: str
    pr_number: int

class ListPRFilesInput(BaseModel):
    repo: str
    pr_number: int

class ListRecentPRsInput(BaseModel):
    repo: str
    limit: int = 10
    state: str = "closed"   # open | closed | all

class GetCommitDiffInput(BaseModel):
    repo: str
    sha: str

class SpawnFunctionAnalysisSubagentInput(BaseModel):
    """
    Input to the one tool that spawns a subagent.
    Both versions of the function are passed in here.
    """
    function_code: FunctionCode        # the function BEFORE the PR change
    function_code_after: FunctionCode  # the function AFTER the PR change
    repo: str
    pr_number: int

# files.py
class GetFileContentInput(BaseModel):
    repo: str
    path: str
    ref: str    # branch name or commit SHA

# reviews.py
class PostPRReviewInput(BaseModel):
    repo: str
    pr_number: int
    body: str
    comments: list[ReviewComment] = Field(default_factory=list)
    event: str = "COMMENT"   # COMMENT | REQUEST_CHANGES | APPROVE

class PostPRCommentInput(BaseModel):
    repo: str
    pr_number: int
    body: str

class AddLabelInput(BaseModel):
    repo: str
    pr_number: int
    labels: list[str]

class GetPRReviewCommentsInput(BaseModel):
    repo: str
    pr_number: int

class ClosePRInput(BaseModel):
    repo: str
    pr_number: int

class MergePRInput(BaseModel):
    repo: str
    pr_number: int
    merge_method: str = "squash"

# branches.py
class CreateBranchInput(BaseModel):
    repo: str
    branch_name: str
    from_ref: str

class PushFileInput(BaseModel):
    repo: str
    path: str
    content: str
    branch: str
    commit_message: str

class CreatePRInput(BaseModel):
    repo: str
    title: str
    body: str
    head: str
    base: str = "main"

class CheckBranchExistsInput(BaseModel):
    repo: str
    branch_name: str

class GetRepoInfoInput(BaseModel):
    repo: str
```

**Functions to implement** (register each with `@tool(namespace="github", ...)`):

1. `get_pr_details(GetPRDetailsInput) -> PRDetails`
   - Call `github.get_repo(repo).get_pull(pr_number)` and map to `PRDetails`

2. `get_pr_diff(GetPRDiffInput) -> Diff`
   - Get PR files, return `Diff` with all `ChangedFile` objects

3. `get_file_content(GetFileContentInput) -> str`
   - Return raw file content at the given ref

4. `get_file_content_at_ref(GetFileContentInput) -> str`
   - Same as above — separate tool so the model can explicitly ask for pre/post versions

5. `list_pr_files(ListPRFilesInput) -> list[ChangedFile]`
   - Return all files changed in the PR

6. `post_pr_review(PostPRReviewInput) -> ReviewResult`
   - Post a review with optional inline comments

7. `post_pr_comment(PostPRCommentInput) -> dict`
   - Post a simple comment on the PR (no inline line comments)

8. `create_branch(CreateBranchInput) -> Branch`
   - Create a new branch from `from_ref`

9. `push_file(PushFileInput) -> dict`
   - Push (create or update) one file on a branch

10. `create_pr(CreatePRInput) -> dict`
    - Open a new PR

11. `add_label(AddLabelInput) -> dict`
    - Add labels to a PR

12. `get_repo_info(GetRepoInfoInput) -> dict`
    - Return basic repo metadata (name, default branch, language, etc.)

13. `list_recent_prs(ListRecentPRsInput) -> list[dict]`
    - Return last N PRs with number, title, state, created_at

14. `get_commit_diff(GetCommitDiffInput) -> Diff`
    - Get the diff for a single commit SHA

15. `close_pr(ClosePRInput) -> dict`
    - Close a PR without merging

16. `get_pr_review_comments(GetPRReviewCommentsInput) -> list[ReviewComment]`
    - Fetch existing review comments on a PR

17. `check_branch_exists(CheckBranchExistsInput) -> bool`
    - Return True if the branch exists in the repo

18. `spawn_function_analysis_subagent(SpawnFunctionAnalysisSubagentInput) -> ComplexityReport`
    - This is the only tool that spawns a subagent
    - Implementation: instantiate `FunctionAnalysisSubagent` and call `.run()`
    - Return the `ComplexityReport` the subagent produces

---

### 8.2 Sandbox Tools — `tools/sandbox/` (14 tools)

Sandbox tools use the Docker Python SDK (`import docker`). Each sandbox is a Docker
container running `python:3.11-slim`. Code is injected by writing to a temp file and
calling `container.exec_run()`. Apply `SANDBOX_TIMEOUT_SECONDS` to all exec calls.

**Input models:**

```python
class CreateSandboxInput(BaseModel):
    language: str = "python"
    dependencies: list[str] = Field(default_factory=list)

class DestroySandboxInput(BaseModel):
    sandbox_id: str

class ExecuteFunctionInput(BaseModel):
    sandbox_id: str
    code: str
    function_name: str
    input_args: list[Any]

class ProfileRuntimeInput(BaseModel):
    """
    Benchmark a function at multiple input sizes.
    Returns one TimingPoint per input size.
    These TimingPoints are the input to fit_complexity_curves.
    """
    sandbox_id: str
    code: str
    function_name: str
    input_sizes: list[int] = Field(
        default=[10, 50, 100, 500, 1000, 5000, 10000]
    )
    runs_per_size: int = 5
    input_type: str = "list_int"   # list_int | list_str | dict | graph_edges

class ProfileMemoryInput(BaseModel):
    sandbox_id: str
    code: str
    function_name: str
    input_sizes: list[int]

class GenerateInputsInput(BaseModel):
    input_type: str
    sizes: list[int]
    seed: int = 42

class InstallDependenciesInput(BaseModel):
    sandbox_id: str
    packages: list[str]

class RunTestSuiteInput(BaseModel):
    sandbox_id: str
    test_code: str

class GetSandboxLogsInput(BaseModel):
    sandbox_id: str

class CheckSandboxHealthInput(BaseModel):
    sandbox_id: str

class ExecuteRawInput(BaseModel):
    sandbox_id: str
    code: str

class BenchmarkFunctionPairInput(BaseModel):
    """
    Run both pre and post versions side by side and compare timing.
    Returns BenchmarkPairResult, which goes into generate_fix_pr_body.
    """
    sandbox_id: str
    pre_code: str
    post_code: str
    function_name: str
    input_sizes: list[int] = Field(default=[10, 100, 1000, 10000])

class ValidateCorrectnessInput(BaseModel):
    sandbox_id: str
    pre_code: str
    post_code: str
    function_name: str
    test_input_sizes: list[int] = Field(default=[10, 100, 1000])

class ExtractFunctionInput(BaseModel):
    code: str
    function_name: str
```

**How to implement `profile_runtime`:**

Run this Python template inside the container for each input size. Parse the printed
JSON to get timing data.

```python
TIMING_TEMPLATE = '''
import time, statistics, json, random

{function_code}

def _generate_input(input_type, n, seed=42):
    random.seed(seed)
    if input_type == "list_int":
        return [random.randint(0, n*10) for _ in range(n)]
    elif input_type == "list_str":
        return ["".join(random.choices("abcdefghij", k=5)) for _ in range(n)]
    elif input_type == "dict":
        return {{str(i): random.randint(0, 100) for i in range(n)}}
    else:
        return [random.randint(0, n*10) for _ in range(n)]

inputs = _generate_input("{input_type}", {n}, seed=42)
times = []
for _ in range({runs}):
    start = time.perf_counter()
    {function_name}(inputs)
    times.append((time.perf_counter() - start) * 1000)

print(json.dumps({{
    "input_size": {n},
    "mean_ms": statistics.mean(times),
    "std_ms": statistics.stdev(times) if len(times) > 1 else 0.0,
    "runs": {runs}
}}))
'''
```

**Functions to implement:**

1. `create_sandbox(CreateSandboxInput) -> str` — spin up a Docker container, return its ID as the sandbox_id
2. `destroy_sandbox(DestroySandboxInput) -> bool` — stop and remove the container
3. `execute_function(ExecuteFunctionInput) -> ExecutionResult` — run a single function call with specific args
4. `profile_runtime(ProfileRuntimeInput) -> list[TimingPoint]` — run at all input sizes, return list of TimingPoints
5. `profile_memory(ProfileMemoryInput) -> list[MemoryPoint]` — use tracemalloc inside container
6. `generate_inputs(GenerateInputsInput) -> dict[str, list]` — return generated inputs for each size
7. `install_dependencies(InstallDependenciesInput) -> InstallResult` — pip install inside container
8. `run_test_suite(RunTestSuiteInput) -> dict` — run pytest code inside container
9. `get_sandbox_logs(GetSandboxLogsInput) -> list[str]` — return container stdout/stderr
10. `check_sandbox_health(CheckSandboxHealthInput) -> SandboxStatus` — ping the container
11. `execute_raw(ExecuteRawInput) -> dict` — run arbitrary Python code, return stdout/stderr
12. `benchmark_function_pair(BenchmarkFunctionPairInput) -> BenchmarkPairResult` — time pre and post versions side by side
13. `validate_correctness(ValidateCorrectnessInput) -> CorrectnessResult` — compare pre and post outputs for same inputs
14. `extract_function(ExtractFunctionInput) -> FunctionCode` — parse a Python source string and extract a named function using `ast`

---

### 8.3 Complexity Tools — `tools/complexity/` (13 tools)

These are pure Python — no Docker, no API calls. Use `scipy.optimize.curve_fit` for
regression. Use the `ast` module for static code scanning.

**How to implement `fit_complexity_curves`:**

```python
import numpy as np
from scipy.optimize import curve_fit

# Define one fitting function per complexity class.
# Each takes n (array of input sizes) and returns predicted times.
COMPLEXITY_FUNCTIONS = {
    "O(1)":       (lambda n, a: np.full_like(n, a, dtype=float),       ComplexityOrder.CONSTANT),
    "O(log n)":   (lambda n, a, b: a * np.log(n + 1) + b,             ComplexityOrder.LOG),
    "O(n)":       (lambda n, a, b: a * n + b,                          ComplexityOrder.LINEAR),
    "O(n log n)": (lambda n, a, b: a * n * np.log(n + 1) + b,         ComplexityOrder.NLOGN),
    "O(n^2)":     (lambda n, a, b: a * n**2 + b,                       ComplexityOrder.QUADRATIC),
    "O(n^3)":     (lambda n, a, b: a * n**3 + b,                       ComplexityOrder.CUBIC),
    "O(2^n)":     (lambda n, a, b: a * 2.0**np.clip(n, 0, 30) + b,    ComplexityOrder.EXPONENTIAL),
}

# For each class: call scipy curve_fit, compute R², build CurveFit object.
# Return all CurveFit objects sorted by R² descending.
# Set is_best_fit=True on the one with the highest R².
```

**Input models:**

```python
class FitComplexityCurvesInput(BaseModel):
    """
    Input: timing data from profile_runtime.
    Output: list of CurveFit objects, one per complexity class.
    This is step 2 in the R5 composability chain.
    """
    timing_points: list[TimingPoint]

class InferComplexityClassInput(BaseModel):
    """
    Input: list of CurveFit from fit_complexity_curves.
    Output: ComplexityClass (the best-fitting one, with confidence).
    This is step 3 in the R5 composability chain.
    """
    timing_points: list[TimingPoint]
    min_confidence: float = 0.85

class DetectRegressionInput(BaseModel):
    """
    Input: two ComplexityClass objects (pre and post PR).
    Output: RegressionResult.
    This is step 4 in the R5 composability chain.
    Logic: if post_class.order > pre_class.order, it's a regression.
    """
    pre_class: ComplexityClass
    post_class: ComplexityClass

class ScanASTInput(BaseModel):
    code: str
    function_name: str

class AnnotateFunctionInput(BaseModel):
    code: str
    function_name: str
    complexity_class: str

class CompareComplexityClassesInput(BaseModel):
    class_a: ComplexityClass
    class_b: ComplexityClass

class EstimateTheoreticalComplexityInput(BaseModel):
    code: str

class GetComplexityExplanationInput(BaseModel):
    class_name: str    # e.g. "O(n^2)"
    context: str       # e.g. "find_duplicates — finds duplicate elements in a list"

class ComputeConfidenceIntervalInput(BaseModel):
    timing_points: list[TimingPoint]
    class_name: str

class DetectLoopNestingDepthInput(BaseModel):
    code: str

class IdentifyHotPathInput(BaseModel):
    code: str

class ComputeRSquaredInput(BaseModel):
    timing_points: list[TimingPoint]
    complexity_class: str

class ClassifyRegressionSeverityInput(BaseModel):
    pre_class: ComplexityClass
    post_class: ComplexityClass
```

**Functions to implement:**

1. `fit_complexity_curves(FitComplexityCurvesInput) -> list[CurveFit]` — fit all 7 complexity classes, return sorted by R²
2. `infer_complexity_class(InferComplexityClassInput) -> ComplexityClass` — return the best-fitting class with confidence
3. `detect_regression(DetectRegressionInput) -> RegressionResult` — compare pre and post orders
4. `scan_ast_for_hints(ScanASTInput) -> ASTComplexityHints` — use `ast` module to count loop nesting, find recursion
5. `annotate_function(AnnotateFunctionInput) -> str` — add a docstring annotation like `# O(n^2)` to the function
6. `compare_complexity_classes(CompareComplexityClassesInput) -> dict` — return which is faster and by how much
7. `estimate_theoretical_complexity(EstimateTheoreticalComplexityInput) -> TheoreticalEstimate` — static AST-based guess
8. `get_complexity_explanation(GetComplexityExplanationInput) -> str` — return a plain-English explanation of what the class means for this function
9. `compute_confidence_interval(ComputeConfidenceIntervalInput) -> ConfidenceInterval` — bootstrap confidence interval on the fit
10. `detect_loop_nesting_depth(DetectLoopNestingDepthInput) -> int` — max nesting depth of for/while loops
11. `identify_hot_path(IdentifyHotPathInput) -> list[str]` — return code lines that are inside the deepest loop nest
12. `compute_r_squared(ComputeRSquaredInput) -> float` — R² for one specific complexity class against the data
13. `classify_regression_severity(ClassifyRegressionSeverityInput) -> str` — return "none" | "minor" | "moderate" | "critical"

---

### 8.4 Optimizer Tools — `tools/optimizer/` (10 tools)

These use a **separate** Gemini client (not the parent agent's client). Create it in
`__init__.py` of the optimizer package using `settings.gemini_api_key`.

**Input models:**

```python
class GenerateOptimizedAlternativeInput(BaseModel):
    original_code: str
    function_name: str
    current_class: str    # e.g. "O(n^2)"
    target_class: str     # e.g. "O(n log n)"
    ast_hints: ASTComplexityHints

class ValidateOptimizationInput(BaseModel):
    original_code: str
    optimized_code: str
    function_name: str
    sandbox_id: str

class VerifyComplexityImprovementInput(BaseModel):
    sandbox_id: str
    pre_timing: list[TimingPoint]
    post_timing: list[TimingPoint]

class GeneratePRReviewBodyInput(BaseModel):
    """
    Terminal step in the R5 chain.
    Input: list of ComplexityReports from all subagents.
    Output: the full PR review comment as a Markdown string.
    """
    regression_reports: list[ComplexityReport]
    repo: str
    pr_number: int

class GenerateFixPRBodyInput(BaseModel):
    function_name: str
    original_class: str
    fixed_class: str
    explanation: str
    benchmark_comparison: BenchmarkPairResult

class ExplainRegressionInput(BaseModel):
    pre_code: str
    post_code: str
    pre_class: str
    post_class: str
    ast_hints: ASTComplexityHints

class SuggestDataStructuresInput(BaseModel):
    code: str
    function_name: str
    current_class: str

class CheckCacheOpportunityInput(BaseModel):
    code: str
    function_name: str

class GenerateComplexityTestInput(BaseModel):
    function_name: str
    expected_class: str

class SummarizeAuditFindingsInput(BaseModel):
    reports: list[ComplexityReport]
    repo: str
```

**Functions to implement:**

1. `generate_optimized_alternative(GenerateOptimizedAlternativeInput) -> str` — call Gemini to rewrite the function with the target complexity
2. `validate_optimization(ValidateOptimizationInput) -> dict` — verify the optimized code is syntactically valid and produces correct output
3. `verify_complexity_improvement(VerifyComplexityImprovementInput) -> dict` — compare timing arrays to confirm improvement
4. `generate_pr_review_body(GeneratePRReviewBodyInput) -> str` — format all regression reports into a Markdown PR comment
5. `generate_fix_pr_body(GenerateFixPRBodyInput) -> str` — write the PR description for the fix PR
6. `explain_regression(ExplainRegressionInput) -> str` — plain-English explanation of why the regression happened
7. `suggest_data_structures(SuggestDataStructuresInput) -> list[str]` — suggest better data structures (e.g. "use a set instead of a list for O(1) lookup")
8. `check_cache_opportunity(CheckCacheOpportunityInput) -> dict` — detect if memoization could help
9. `generate_complexity_test(GenerateComplexityTestInput) -> str` — generate a pytest that asserts the function runs in the expected complexity class
10. `summarize_audit_findings(SummarizeAuditFindingsInput) -> AuditSummary` — aggregate all ComplexityReports into one AuditSummary

---

## 9. Context Manager

Create `src/algosentinel/agent/context.py` with this exact class.

**What it does:** Keeps the agent coherent over 25+ tool calls by periodically
summarizing history, while always keeping the Plan in full.

```python
import structlog
from datetime import datetime
from algosentinel.models.tools import Plan, Step, Checkpoint, ToolCallRecord
from algosentinel.config import settings

logger = structlog.get_logger()

class ContextManager:
    """
    Maintains agent coherence across long-horizon execution.

    Rules:
    1. The Plan (goal, steps, repo) is NEVER compressed. Always shown in full.
    2. Tool call history IS compressed every COMPRESS_EVERY_N calls.
    3. After compression, raw history records are discarded.
    4. Only the rolling_summary text and the Plan survive compression.
    5. Every system prompt = PLAN (full) + ROLLING SUMMARY (compressed history).
    """

    def __init__(self, plan: Plan):
        self.plan = plan
        self.COMPRESS_EVERY_N = settings.context_compress_every_n_calls
        self.tool_history: list[ToolCallRecord] = []
        self.rolling_summary: str = ""
        self.checkpoints: list[Checkpoint] = []
        self.total_calls: int = 0
        self._log = logger.bind(component="ContextManager")

    def record_tool_call(self, record: ToolCallRecord) -> None:
        """Call this after every tool call. Triggers compression every N calls."""
        self.tool_history.append(record)
        self.total_calls += 1
        self._log.info(
            "tool_call_recorded",
            call_n=self.total_calls,
            tool=record.tool_name,
            duration_ms=record.duration_ms,
        )
        if self.total_calls % self.COMPRESS_EVERY_N == 0:
            self._compress()

    def _compress(self) -> None:
        """
        Summarize the last COMPRESS_EVERY_N tool calls into one text block.
        Discard the raw records. Keep the Plan.
        """
        if not self.tool_history:
            return
        recent = self.tool_history[-self.COMPRESS_EVERY_N:]
        lines = []
        for r in recent:
            status = "OK" if r.success else "FAIL"
            lines.append(
                f"[call {r.call_number}] {r.namespace}.{r.tool_name} → {status}: {r.result_summary}"
            )
        block = "\n".join(lines)
        checkpoint = Checkpoint(
            call_number=self.total_calls,
            summary=block,
            timestamp=datetime.utcnow(),
        )
        self.checkpoints.append(checkpoint)
        self.rolling_summary = (
            f"{self.rolling_summary}\n--- compressed at call {self.total_calls} ---\n{block}"
        ).strip()
        # Discard raw records — this keeps context window bounded
        self.tool_history = []
        self._log.info(
            "context_compressed",
            checkpoint_n=len(self.checkpoints),
            total_calls=self.total_calls,
        )

    def update_plan_step(self, step_id: str, status: str) -> None:
        for step in self.plan.steps:
            if step.id == step_id:
                step.status = status
                self.plan.current_step_id = step_id
                break

    def build_system_prompt(self) -> str:
        """
        Build the system prompt to prepend to every Gemini call.
        Always contains: GOAL + full PLAN + ROLLING SUMMARY.
        The Plan is never absent, even after many compressions.
        """
        plan_text = "\n".join(
            f"  [{s.status.upper()}] {s.id}: {s.description}"
            for s in self.plan.steps
        )
        return f"""You are AlgoSentinel, an autonomous agent that detects algorithmic complexity regressions.

GOAL: {self.plan.goal}
REPO: {self.plan.repo}
TARGET PRs: {self.plan.pr_numbers}

EXECUTION PLAN (always keep this in mind):
{plan_text}

PROGRESS SO FAR (compressed history of tool calls):
{self.rolling_summary or "(no tool calls yet)"}

Instructions:
- Use available tools to advance the plan step by step.
- When analyzing a changed function, call spawn_function_analysis_subagent with both
  the pre-change and post-change versions of the function.
- Always act on what tools return — never assume a result.
- If a tool fails, note the error and try an alternative approach.
- When all functions are analyzed, call generate_pr_review_body and then post_pr_review.
- Finally, call summarize_audit_findings to produce the AuditSummary.
"""

    def get_stats(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "checkpoints_created": len(self.checkpoints),
            "current_step": self.plan.current_step_id,
            "steps_done": sum(1 for s in self.plan.steps if s.status == "done"),
        }
```

---

## 10. Subagent

Create `src/algosentinel/agent/subagent.py`.

**Critical rules:**
- The subagent creates its own `genai.Client(api_key=settings.gemini_api_key)` — a new Python object, not a reference to the parent's client
- The subagent has its own `self._messages: list = []` — a new list, never the parent's
- The subagent can only call tools in `sandbox` and `complexity` namespaces
- The subagent must make at least 5 tool calls before returning
- The subagent returns `ComplexityReport`, not a dict or string

```python
from google import genai
from google.genai import types as genai_types
from algosentinel.tools.registry import ToolRegistry
from algosentinel.models.reports import ComplexityReport
from algosentinel.models.sandbox import FunctionCode
from algosentinel.resilience.rate_limiter import TokenBucketRateLimiter
from algosentinel.resilience.errors import SubagentError
from algosentinel.config import settings
import structlog, json

logger = structlog.get_logger()

# The subagent can ONLY call tools in these namespaces.
# It cannot call GitHub tools (no side effects) or optimizer tools.
SUBAGENT_NAMESPACES = ["sandbox", "complexity"]

SUBAGENT_SYSTEM_PROMPT = """You are a FunctionAnalysisSubagent.
Your only job: empirically measure the complexity of two Python function versions (pre and post a code change), then return a ComplexityReport.

Follow these steps in order:
1. Call sandbox__create_sandbox to get a sandbox_id.
2. Call sandbox__profile_runtime with the PRE-change code. Use input_sizes=[10,50,100,500,1000,5000,10000].
3. Call sandbox__profile_runtime with the POST-change code. Same input_sizes.
4. Call complexity__fit_complexity_curves on the PRE timing points.
5. Call complexity__fit_complexity_curves on the POST timing points.
6. Call complexity__infer_complexity_class on the PRE timing points.
7. Call complexity__infer_complexity_class on the POST timing points.
8. Call complexity__detect_regression with the two ComplexityClass results.
9. If regression detected: call complexity__scan_ast_for_hints on the post code.
10. Call complexity__classify_regression_severity.
11. Call sandbox__destroy_sandbox to clean up.
12. Return your final answer as a raw JSON object that matches the ComplexityReport schema.
    Do NOT add any text before or after the JSON object.
    Do NOT use markdown code fences.
"""

class FunctionAnalysisSubagent:
    """
    Isolated subagent for complexity analysis.

    This is NOT a function call. It is a separate object with:
    - Its own genai.Client (separate API client, not shared)
    - Its own message history (separate list, not shared)
    - A scoped tool set (sandbox + complexity only)

    Called by: github.spawn_function_analysis_subagent tool.
    Returns: ComplexityReport (typed Pydantic model, not dict).
    """

    def __init__(
        self,
        function_code: FunctionCode,
        function_code_after: FunctionCode,
        rate_limiter: TokenBucketRateLimiter,
    ):
        self.function_code = function_code
        self.function_code_after = function_code_after
        self.rate_limiter = rate_limiter

        # OWN CLIENT — not the parent's. Satisfies R2.
        self._client = genai.Client(api_key=settings.gemini_api_key)

        # OWN HISTORY — not the parent's. Satisfies R2.
        self._messages: list = []

        self._tool_calls_made: int = 0
        self._log = logger.bind(
            component="FunctionAnalysisSubagent",
            function=function_code.function_name,
        )

    def run(self) -> ComplexityReport:
        registry = ToolRegistry.get()

        # Scoped tool set — only sandbox and complexity
        declarations = registry.get_function_declarations(namespaces=SUBAGENT_NAMESPACES)
        tool_config = genai_types.Tool(function_declarations=declarations)

        user_message = (
            f"Analyze this function for complexity regression.\n\n"
            f"FUNCTION NAME: {self.function_code.function_name}\n\n"
            f"PRE-CHANGE CODE ({self.function_code.file_path}, "
            f"lines {self.function_code.line_start}–{self.function_code.line_end}):\n"
            f"```python\n{self.function_code.source_code}\n```\n\n"
            f"POST-CHANGE CODE ({self.function_code_after.file_path}):\n"
            f"```python\n{self.function_code_after.source_code}\n```\n\n"
            f"Run the full empirical analysis and return a ComplexityReport JSON."
        )

        # Initialize OWN message history
        self._messages = [{"role": "user", "parts": [{"text": user_message}]}]

        MAX_ITERATIONS = 20
        for iteration in range(MAX_ITERATIONS):
            self.rate_limiter.acquire()

            response = self._client.models.generate_content(
                model=settings.gemini_model,
                contents=self._messages,
                config=genai_types.GenerateContentConfig(
                    system_instruction=SUBAGENT_SYSTEM_PROMPT,
                    tools=[tool_config],
                    max_output_tokens=settings.gemini_max_tokens,
                ),
            )

            has_tool_call = False
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    has_tool_call = True
                    self._tool_calls_made += 1
                    call = part.function_call

                    self._log.info(
                        "subagent_tool_call",
                        tool=call.name,
                        call_n=self._tool_calls_made,
                    )

                    result = registry.dispatch(call.name, dict(call.args))
                    result_str = (
                        result.model_dump_json()
                        if hasattr(result, "model_dump_json")
                        else json.dumps(result, default=str)
                    )

                    # Append to OWN history only
                    self._messages.append({
                        "role": "model",
                        "parts": [{"function_call": {"name": call.name, "args": dict(call.args)}}],
                    })
                    self._messages.append({
                        "role": "user",
                        "parts": [{"function_response": {
                            "name": call.name,
                            "response": {"result": result_str},
                        }}],
                    })

            # No tool call = model is giving its final JSON answer
            if not has_tool_call:
                for part in response.candidates[0].content.parts:
                    if part.text:
                        raw = part.text.strip()
                        # Strip markdown code fences if present
                        if raw.startswith("```"):
                            lines = raw.split("\n")
                            raw = "\n".join(lines[1:-1])
                        report = ComplexityReport.model_validate_json(raw)
                        report.subagent_tool_calls_used = self._tool_calls_made
                        self._log.info(
                            "subagent_complete",
                            is_regression=report.regression.is_regression,
                            tool_calls=self._tool_calls_made,
                        )
                        return report

        raise SubagentError(
            f"FunctionAnalysisSubagent for '{self.function_code.function_name}' "
            f"exceeded {MAX_ITERATIONS} iterations without returning a ComplexityReport."
        )
```

---

## 11. Main Agent Loop

Create `src/algosentinel/agent/core.py`.

```python
from google import genai
from google.genai import types as genai_types
from algosentinel.tools.registry import ToolRegistry
from algosentinel.agent.context import ContextManager
from algosentinel.agent.planner import build_plan
from algosentinel.models.tools import ToolCallRecord
from algosentinel.models.reports import AuditSummary
from algosentinel.resilience.rate_limiter import TokenBucketRateLimiter
from algosentinel.resilience.errors import FatalError
from algosentinel.config import settings
import structlog, time, json

logger = structlog.get_logger()

class AgentLoop:
    """
    The parent agent. Uses all 55 tools. Delegates function analysis to subagents.

    Run with:
        summary = AgentLoop().run(repo="owner/repo", pr_numbers=[42])
    """

    MAX_ITERATIONS = 60  # Prevents infinite loops

    def __init__(self):
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._rate_limiter = TokenBucketRateLimiter(rate_per_minute=settings.gemini_max_rpm)
        self._log = logger.bind(component="AgentLoop")

    def run(self, repo: str, pr_numbers: list[int]) -> AuditSummary:
        registry = ToolRegistry.get()

        # Fail fast if not enough tools registered
        count = registry.tool_count()
        assert count >= 55, f"Expected >=55 tools, got {count}. Check that all tool modules are imported."

        plan = build_plan(repo=repo, pr_numbers=pr_numbers)
        ctx = ContextManager(plan=plan)

        # All 55 tools available to parent agent
        tool_config = genai_types.Tool(
            function_declarations=registry.get_function_declarations()
        )

        # Initial prompt explaining what to do
        messages = [{
            "role": "user",
            "parts": [{"text": (
                f"Audit the repository {repo} for algorithmic complexity regressions "
                f"in pull request(s) {pr_numbers}.\n\n"
                f"For each PR:\n"
                f"1. Fetch the PR diff and list changed Python files.\n"
                f"2. For each changed .py file, get both the pre-change and post-change content.\n"
                f"3. Extract each changed function using sandbox__extract_function.\n"
                f"4. For each changed function, call github__spawn_function_analysis_subagent "
                f"   with both versions.\n"
                f"5. Collect all ComplexityReports.\n"
                f"6. For any regression found, call optimizer__generate_optimized_alternative "
                f"   and optimizer__validate_optimization.\n"
                f"7. Call optimizer__generate_pr_review_body with all reports.\n"
                f"8. Call github__post_pr_review to post the review.\n"
                f"9. For verified fixes, create a fix branch, push the fix, and open a fix PR.\n"
                f"10. Call optimizer__summarize_audit_findings and return the result."
            )}],
        }]

        session_start = time.time()
        call_number = 0

        for iteration in range(self.MAX_ITERATIONS):
            self._rate_limiter.acquire()

            response = self._client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    {"role": "system", "parts": [{"text": ctx.build_system_prompt()}]},
                    *messages,
                ],
                config=genai_types.GenerateContentConfig(
                    tools=[tool_config],
                    max_output_tokens=settings.gemini_max_tokens,
                ),
            )

            has_tool_call = False

            for part in response.candidates[0].content.parts:
                if part.function_call:
                    has_tool_call = True
                    call_number += 1
                    call = part.function_call
                    t0 = time.time()

                    self._log.info(
                        "agent_tool_call",
                        call_n=call_number,
                        tool=call.name,
                        iteration=iteration,
                    )

                    try:
                        result = registry.dispatch(call.name, dict(call.args))
                        success = True
                    except Exception as e:
                        self._log.error("tool_call_failed", tool=call.name, error=str(e))
                        result = {"error": str(e)}
                        success = False

                    duration_ms = (time.time() - t0) * 1000
                    result_str = (
                        result.model_dump_json()
                        if hasattr(result, "model_dump_json")
                        else json.dumps(result, default=str)
                    )

                    # Record in context manager (triggers compression every 6 calls)
                    ctx.record_tool_call(ToolCallRecord(
                        call_number=call_number,
                        namespace=call.name.split("__")[0] if "__" in call.name else "unknown",
                        tool_name=call.name,
                        input_summary=str(dict(call.args))[:100],
                        result_summary=result_str[:150],
                        duration_ms=duration_ms,
                        success=success,
                    ))

                    messages.append({
                        "role": "model",
                        "parts": [{"function_call": {"name": call.name, "args": dict(call.args)}}],
                    })
                    messages.append({
                        "role": "user",
                        "parts": [{"function_response": {
                            "name": call.name,
                            "response": {"result": result_str},
                        }}],
                    })

            if not has_tool_call:
                # Agent is done — it should have called summarize_audit_findings already
                self._log.info(
                    "agent_complete",
                    total_calls=call_number,
                    duration_s=round(time.time() - session_start, 2),
                )
                return AuditSummary(
                    repo=repo,
                    prs_audited=len(pr_numbers),
                    functions_analyzed=0,
                    regressions_found=0,
                    regressions_critical=0,
                    regressions_moderate=0,
                    fixes_generated=0,
                    fixes_verified=0,
                    fix_prs_opened=[],
                    total_tool_calls=call_number,
                    session_duration_seconds=round(time.time() - session_start, 2),
                    reports=[],
                )

        raise FatalError(f"AgentLoop exceeded MAX_ITERATIONS={self.MAX_ITERATIONS} without finishing.")
```

Create `src/algosentinel/agent/planner.py`:

```python
from algosentinel.models.tools import Plan, Step

def build_plan(repo: str, pr_numbers: list[int]) -> Plan:
    """Build the initial execution plan for an audit session."""
    steps = [
        Step(id="s1", description=f"Fetch PR details and diffs for PRs {pr_numbers}"),
        Step(id="s2", description="Identify changed Python files and extract changed functions"),
        Step(id="s3", description="Spawn subagents to analyze each changed function pair"),
        Step(id="s4", description="Collect ComplexityReports from all subagents"),
        Step(id="s5", description="Generate optimized fixes for any regressions found"),
        Step(id="s6", description="Verify each fix restores the original complexity class"),
        Step(id="s7", description="Post PR review comments with findings"),
        Step(id="s8", description="Open fix PRs for verified fixes"),
        Step(id="s9", description="Summarize audit findings and return AuditSummary"),
    ]
    return Plan(
        goal=f"Detect algorithmic complexity regressions in {repo} PRs {pr_numbers}",
        repo=repo,
        pr_numbers=pr_numbers,
        steps=steps,
    )
```

---

## 12. Resilience Layer

### `resilience/errors.py`

```python
class AlgoSentinelError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable

class RetryableError(AlgoSentinelError):
    def __init__(self, message: str):
        super().__init__(message, retryable=True)

class FatalError(AlgoSentinelError):
    def __init__(self, message: str):
        super().__init__(message, retryable=False)

# Tool errors
class ToolError(AlgoSentinelError):
    pass

class GitHubToolError(ToolError):
    pass

class GitHubRateLimitError(GitHubToolError, RetryableError):
    pass

class GitHubNotFoundError(GitHubToolError, FatalError):
    pass

# Sandbox errors
class SandboxError(ToolError):
    pass

class SandboxTimeoutError(SandboxError, RetryableError):
    pass

class SandboxStartError(SandboxError, FatalError):
    pass

# Complexity errors
class ComplexityInferenceError(ToolError):
    pass

class InsufficientDataError(ComplexityInferenceError, FatalError):
    pass

# Subagent errors
class SubagentError(AlgoSentinelError):
    pass

class SubagentTimeoutError(SubagentError, RetryableError):
    pass

# Rate limit
class RateLimitError(RetryableError):
    pass
```

### `resilience/retry.py`

```python
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential_jitter,
    retry_if_exception_type,
    before_sleep_log,
)
import logging
from algosentinel.resilience.errors import RetryableError

def with_retry(max_attempts: int = 4, min_wait: float = 1.0, max_wait: float = 60.0):
    """
    Decorator for all external calls (GitHub API, Gemini API, Docker).

    Retries: RetryableError and its subclasses
    Never retries: FatalError and its subclasses
    Backoff: exponential with jitter (1s, ~2s, ~4s, ~8s...)
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=min_wait, max=max_wait, jitter=1.0),
        retry=retry_if_exception_type(RetryableError),
        before_sleep=before_sleep_log(
            logging.getLogger("tenacity"), logging.WARNING
        ),
        reraise=True,
    )
```

### `resilience/rate_limiter.py`

```python
import time
import threading

class TokenBucketRateLimiter:
    """
    Thread-safe token bucket rate limiter.
    Caps Gemini API calls at settings.gemini_max_rpm per minute (default: 14).

    The Gemini free tier allows 15 RPM. We cap at 14 to stay safely under.

    Usage:
        limiter = TokenBucketRateLimiter(rate_per_minute=14)
        limiter.acquire()   # blocks until a token is available
        response = client.models.generate_content(...)
    """

    def __init__(self, rate_per_minute: int = 14):
        self.rate = rate_per_minute
        self.capacity = float(rate_per_minute)
        self.tokens = float(rate_per_minute)
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        """Add tokens based on time elapsed since last refill."""
        now = time.monotonic()
        elapsed = now - self.last_refill
        # Tokens refill at rate_per_minute tokens per 60 seconds
        new_tokens = elapsed * (self.rate / 60.0)
        self.tokens = min(self.capacity, self.tokens + new_tokens)
        self.last_refill = now

    def acquire(self, tokens: int = 1) -> None:
        """Block until a token is available, then consume it."""
        while True:
            with self._lock:
                self._refill()
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
            time.sleep(0.1)
```

---

## 13. Observability

### `observability/logger.py`

```python
import structlog
import logging
import sys
from algosentinel.config import settings

def configure_logging() -> None:
    """Call this once at startup (in CLI scripts and webhook)."""
    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    if settings.log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )
    logging.basicConfig(
        stream=sys.stdout,
        level=getattr(logging, settings.log_level.upper()),
    )
```

### `observability/tracer.py`

```python
import time
import structlog
from algosentinel.models.tools import ToolCallRecord

logger = structlog.get_logger()

class ToolCallTracer:
    """
    Wraps tool calls with timing and structured logging.

    Usage:
        tracer = ToolCallTracer()
        with tracer.trace("github", "get_pr_details") as record:
            result = actual_tool_call()
        # Log line is emitted automatically with duration_ms, success, etc.
    """

    def trace(self, namespace: str, tool_name: str):
        return _TraceContext(namespace, tool_name)


class _TraceContext:
    def __init__(self, namespace: str, tool_name: str):
        self.namespace = namespace
        self.tool_name = tool_name
        self.start = time.time()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start) * 1000
        success = exc_type is None
        logger.info(
            "tool_call_traced",
            namespace=self.namespace,
            tool_name=self.tool_name,
            duration_ms=round(duration_ms, 2),
            success=success,
        )
        return False  # Do not suppress exceptions
```

---

## 14. Eval Harness

### Golden case format

Each file in `evals/golden/` is a JSON file with this schema:

```json
{
  "id": "case_001",
  "description": "O(n) → O(n^2): linear scan replaced by nested lookup",
  "pre_code": "def find_duplicates(lst):\n    seen = set()\n    result = []\n    for x in lst:\n        if x in seen:\n            result.append(x)\n        seen.add(x)\n    return result",
  "post_code": "def find_duplicates(lst):\n    result = []\n    for i, x in enumerate(lst):\n        if x in lst[:i]:\n            result.append(x)\n    return result",
  "function_name": "find_duplicates",
  "expected_pre_class": "O(n)",
  "expected_post_class": "O(n^2)",
  "expected_regression": true,
  "expected_severity": "moderate",
  "fix_should_restore_to": "O(n)"
}
```

**Create these 5 golden cases:**

- `case_001_on_to_on2.json`: O(n) → O(n²) — use the `find_duplicates` example above
- `case_002_onlogn_to_on2.json`: O(n log n) → O(n²) — e.g., sorted() inside a loop replaced with manual insertion sort in a loop
- `case_003_no_regression.json`: No regression — same complexity, just refactored code (`expected_regression: false`)
- `case_004_on2_to_on_improvement.json`: O(n²) → O(n) — an improvement, NOT a regression (`expected_regression: false`)
- `case_005_multi_function_mixed.json`: Two functions — one regressed, one did not. Use a list-of-functions format.

### `evals/harness.py`

```python
"""
Eval harness: runs the complexity pipeline against each golden case and reports metrics.

Run with:
    python evals/harness.py
"""
import json
import glob
from algosentinel.tools.sandbox.executor import create_sandbox, destroy_sandbox
from algosentinel.tools.complexity.inference import infer_complexity_class
from algosentinel.tools.sandbox.profiler import profile_runtime
from algosentinel.tools.complexity.curve_fit import fit_complexity_curves
from algosentinel.tools.complexity.inference import detect_regression
from algosentinel.models.sandbox import CreateSandboxInput, ProfileRuntimeInput
from algosentinel.models.complexity import FitComplexityCurvesInput, InferComplexityClassInput, DetectRegressionInput
from evals.metrics import compute_metrics

def run_case(case: dict) -> dict:
    """Run the complexity pipeline on one golden case and return results."""
    sandbox_id = create_sandbox(CreateSandboxInput())

    pre_timing = profile_runtime(ProfileRuntimeInput(
        sandbox_id=sandbox_id,
        code=case["pre_code"],
        function_name=case["function_name"],
        input_sizes=[10, 50, 100, 500, 1000, 5000],
    ))
    post_timing = profile_runtime(ProfileRuntimeInput(
        sandbox_id=sandbox_id,
        code=case["post_code"],
        function_name=case["function_name"],
        input_sizes=[10, 50, 100, 500, 1000, 5000],
    ))

    pre_class = infer_complexity_class(InferComplexityClassInput(timing_points=pre_timing))
    post_class = infer_complexity_class(InferComplexityClassInput(timing_points=post_timing))
    regression = detect_regression(DetectRegressionInput(pre_class=pre_class, post_class=post_class))

    destroy_sandbox({"sandbox_id": sandbox_id})

    return {
        "id": case["id"],
        "expected_regression": case["expected_regression"],
        "detected_regression": regression.is_regression,
        "expected_pre_class": case["expected_pre_class"],
        "detected_pre_class": pre_class.notation,
        "expected_post_class": case["expected_post_class"],
        "detected_post_class": post_class.notation,
        "severity": regression.severity,
        "passed": regression.is_regression == case["expected_regression"],
    }

def main():
    cases = []
    for path in sorted(glob.glob("evals/golden/*.json")):
        with open(path) as f:
            data = json.load(f)
            # Handle multi-function case
            if "functions" in data:
                for fn in data["functions"]:
                    cases.append(fn)
            else:
                cases.append(data)

    results = [run_case(c) for c in cases]
    metrics = compute_metrics(results)

    print("\n=== AlgoSentinel Eval Results ===")
    for r in results:
        status = "✓ PASS" if r["passed"] else "✗ FAIL"
        print(f"{status} | {r['id']}: expected {r['expected_post_class']}, "
              f"got {r['detected_post_class']} | regression={r['detected_regression']}")
    print(f"\nPrecision: {metrics['precision']:.2f}")
    print(f"Recall:    {metrics['recall']:.2f}")
    print(f"F1:        {metrics['f1']:.2f}")
    print(f"Fix rate:  {metrics['fix_success_rate']:.2f}")

if __name__ == "__main__":
    main()
```

### `evals/metrics.py`

```python
def compute_metrics(results: list[dict]) -> dict:
    """
    Compute precision, recall, F1, and fix success rate.

    TP = regression expected and detected
    FP = regression detected but not expected
    FN = regression expected but not detected
    """
    tp = sum(1 for r in results if r["expected_regression"] and r["detected_regression"])
    fp = sum(1 for r in results if not r["expected_regression"] and r["detected_regression"])
    fn = sum(1 for r in results if r["expected_regression"] and not r["detected_regression"])

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)
                 if (precision + recall) > 0 else 0.0)

    expected_regressions = sum(1 for r in results if r["expected_regression"])
    fixes_verified = sum(1 for r in results if r.get("fix_verified", False))
    fix_success_rate = fixes_verified / max(1, expected_regressions)

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "fix_success_rate": fix_success_rate,
    }
```

---

## 15. Tests

### Unit Tests (no Docker required)

#### `tests/unit/test_registry.py`

```python
import pytest
import algosentinel.tools.github  # noqa — triggers tool registration
import algosentinel.tools.sandbox
import algosentinel.tools.complexity
import algosentinel.tools.optimizer
from algosentinel.tools.registry import ToolRegistry
from algosentinel.resilience.errors import ToolError

def test_tool_count():
    """R1: must have at least 55 tools."""
    assert ToolRegistry.get().tool_count() >= 55

def test_namespaces():
    """R1: must have exactly these 4 namespaces."""
    ns = set(ToolRegistry.get().namespaces())
    assert {"github", "sandbox", "complexity", "optimizer"}.issubset(ns)

def test_all_tools_have_descriptions():
    registry = ToolRegistry.get()
    for name, tool_def in registry._tools.items():
        assert tool_def.description, f"Tool {name} has an empty description"

def test_all_tools_have_valid_schemas():
    registry = ToolRegistry.get()
    for name, tool_def in registry._tools.items():
        schema = tool_def.input_model.model_json_schema()
        assert "properties" in schema or "type" in schema, f"Invalid schema for {name}"

def test_dispatch_unknown_raises_tool_error():
    """Must raise ToolError, not KeyError."""
    with pytest.raises(ToolError):
        ToolRegistry.get().dispatch("nonexistent__tool", {})
```

#### `tests/unit/test_curve_fit.py`

```python
import pytest
import numpy as np
from algosentinel.tools.complexity.curve_fit import fit_complexity_curves
from algosentinel.tools.complexity.inference import infer_complexity_class, detect_regression
from algosentinel.models.sandbox import TimingPoint
from algosentinel.models.complexity import FitComplexityCurvesInput, InferComplexityClassInput, DetectRegressionInput

def make_timing(sizes, times):
    return [TimingPoint(input_size=n, elapsed_ms=t) for n, t in zip(sizes, times)]

SIZES = [10, 50, 100, 500, 1000, 5000, 10000]

def test_infer_linear():
    times = [n * 0.001 + 0.1 for n in SIZES]
    points = make_timing(SIZES, times)
    result = infer_complexity_class(InferComplexityClassInput(timing_points=points))
    assert result.notation == "O(n)"

def test_infer_quadratic():
    times = [n**2 * 0.000001 + 0.1 for n in SIZES]
    points = make_timing(SIZES, times)
    result = infer_complexity_class(InferComplexityClassInput(timing_points=points))
    assert result.notation == "O(n^2)"

def test_infer_nlogn():
    times = [n * np.log(n) * 0.00005 + 0.1 for n in SIZES]
    points = make_timing(SIZES, times)
    result = infer_complexity_class(InferComplexityClassInput(timing_points=points))
    assert result.notation in ("O(n log n)", "O(n)")  # allow O(n) as close neighbor

def test_detect_regression_on_to_on2():
    linear_points = make_timing(SIZES, [n * 0.001 for n in SIZES])
    quad_points   = make_timing(SIZES, [n**2 * 0.000001 for n in SIZES])
    pre  = infer_complexity_class(InferComplexityClassInput(timing_points=linear_points))
    post = infer_complexity_class(InferComplexityClassInput(timing_points=quad_points))
    result = detect_regression(DetectRegressionInput(pre_class=pre, post_class=post))
    assert result.is_regression is True

def test_detect_no_regression():
    times_a = [n * 0.001 for n in SIZES]
    times_b = [n * 0.002 for n in SIZES]  # slower constant, same class
    pre  = infer_complexity_class(InferComplexityClassInput(timing_points=make_timing(SIZES, times_a)))
    post = infer_complexity_class(InferComplexityClassInput(timing_points=make_timing(SIZES, times_b)))
    result = detect_regression(DetectRegressionInput(pre_class=pre, post_class=post))
    assert result.is_regression is False
```

#### `tests/unit/test_context_manager.py`

```python
import pytest
from algosentinel.agent.context import ContextManager
from algosentinel.agent.planner import build_plan
from algosentinel.models.tools import ToolCallRecord
from datetime import datetime

def make_record(n: int) -> ToolCallRecord:
    return ToolCallRecord(
        call_number=n,
        namespace="github",
        tool_name="get_pr_details",
        input_summary="repo=test/repo",
        result_summary="PR #1 fetched",
        duration_ms=50.0,
        success=True,
        timestamp=datetime.utcnow(),
    )

def test_plan_always_in_system_prompt():
    plan = build_plan(repo="test/repo", pr_numbers=[1])
    ctx = ContextManager(plan=plan)
    prompt = ctx.build_system_prompt()
    assert plan.goal in prompt

def test_compression_fires_at_n():
    plan = build_plan(repo="test/repo", pr_numbers=[1])
    ctx = ContextManager(plan=plan)
    n = ctx.COMPRESS_EVERY_N
    for i in range(1, n + 1):
        ctx.record_tool_call(make_record(i))
    # After exactly N calls, compression should have fired
    assert len(ctx.tool_history) == 0
    assert ctx.rolling_summary != ""

def test_tool_history_empty_after_compression():
    plan = build_plan(repo="test/repo", pr_numbers=[1])
    ctx = ContextManager(plan=plan)
    for i in range(ctx.COMPRESS_EVERY_N):
        ctx.record_tool_call(make_record(i + 1))
    assert ctx.tool_history == []

def test_plan_in_prompt_after_multiple_compressions():
    plan = build_plan(repo="test/repo", pr_numbers=[1])
    ctx = ContextManager(plan=plan)
    # Trigger 3 compressions
    for i in range(ctx.COMPRESS_EVERY_N * 3):
        ctx.record_tool_call(make_record(i + 1))
    prompt = ctx.build_system_prompt()
    assert plan.goal in prompt
    assert plan.repo in prompt
```

#### `tests/unit/test_retry.py`

```python
import pytest
from unittest.mock import MagicMock
from algosentinel.resilience.retry import with_retry
from algosentinel.resilience.errors import RetryableError, FatalError

def test_retries_retryable_error():
    call_count = 0
    @with_retry(max_attempts=3, min_wait=0.01, max_wait=0.1)
    def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise RetryableError("temporary failure")
        return "ok"
    result = flaky()
    assert result == "ok"
    assert call_count == 3

def test_does_not_retry_fatal_error():
    call_count = 0
    @with_retry(max_attempts=4, min_wait=0.01, max_wait=0.1)
    def always_fatal():
        nonlocal call_count
        call_count += 1
        raise FatalError("permanent failure")
    with pytest.raises(FatalError):
        always_fatal()
    assert call_count == 1  # Must not retry
```

#### `tests/unit/test_rate_limiter.py`

```python
import time
import pytest
from algosentinel.resilience.rate_limiter import TokenBucketRateLimiter

def test_initial_tokens_allow_immediate_calls():
    limiter = TokenBucketRateLimiter(rate_per_minute=10)
    # Should not block
    start = time.monotonic()
    limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 0.5  # Well under 500ms

def test_exhausted_tokens_cause_blocking():
    limiter = TokenBucketRateLimiter(rate_per_minute=2)
    limiter.acquire()
    limiter.acquire()
    # Tokens are now exhausted
    start = time.monotonic()
    limiter.acquire()  # This should block
    elapsed = time.monotonic() - start
    assert elapsed >= 20  # At 2 RPM, next token arrives in ~30s
    # (This test is slow — consider mocking time for CI)
```

### Integration Tests (require Docker running)

#### `tests/integration/test_sandbox_execution.py`

```python
import pytest
from algosentinel.tools.sandbox.executor import create_sandbox, destroy_sandbox, execute_raw
from algosentinel.tools.sandbox.profiler import profile_runtime
from algosentinel.models.sandbox import CreateSandboxInput, ExecuteRawInput, ProfileRuntimeInput

@pytest.fixture
def sandbox_id():
    sid = create_sandbox(CreateSandboxInput())
    yield sid
    destroy_sandbox({"sandbox_id": sid})

def test_create_and_destroy_sandbox():
    sid = create_sandbox(CreateSandboxInput())
    assert isinstance(sid, str)
    assert len(sid) > 0
    result = destroy_sandbox({"sandbox_id": sid})
    assert result is True

def test_execute_raw_returns_output(sandbox_id):
    result = execute_raw(ExecuteRawInput(sandbox_id=sandbox_id, code="print('hello')"))
    assert "hello" in result["stdout"]

def test_profile_runtime_returns_timing_points(sandbox_id):
    code = "def linear(lst):\n    return [x*2 for x in lst]"
    points = profile_runtime(ProfileRuntimeInput(
        sandbox_id=sandbox_id,
        code=code,
        function_name="linear",
        input_sizes=[10, 100, 1000],
    ))
    assert len(points) == 3
    assert all(p.elapsed_ms >= 0 for p in points)
    assert all(p.input_size in [10, 100, 1000] for p in points)
```

#### `tests/integration/test_subagent_isolation.py`

```python
import pytest
from algosentinel.agent.subagent import FunctionAnalysisSubagent
from algosentinel.models.sandbox import FunctionCode
from algosentinel.resilience.rate_limiter import TokenBucketRateLimiter
from algosentinel.models.reports import ComplexityReport

PRE_CODE = """
def find_duplicates(lst):
    seen = set()
    result = []
    for x in lst:
        if x in seen:
            result.append(x)
        seen.add(x)
    return result
"""

POST_CODE = """
def find_duplicates(lst):
    result = []
    for i, x in enumerate(lst):
        if x in lst[:i]:
            result.append(x)
    return result
"""

@pytest.fixture
def subagent():
    return FunctionAnalysisSubagent(
        function_code=FunctionCode(
            function_name="find_duplicates",
            source_code=PRE_CODE,
            file_path="utils.py",
            line_start=1,
            line_end=8,
        ),
        function_code_after=FunctionCode(
            function_name="find_duplicates",
            source_code=POST_CODE,
            file_path="utils.py",
            line_start=1,
            line_end=6,
        ),
        rate_limiter=TokenBucketRateLimiter(rate_per_minute=14),
    )

def test_subagent_returns_typed_report(subagent):
    report = subagent.run()
    assert isinstance(report, ComplexityReport)

def test_subagent_uses_at_least_5_tools(subagent):
    report = subagent.run()
    assert report.subagent_tool_calls_used >= 5

def test_subagent_history_is_isolated(subagent):
    """Subagent's _messages should not be accessible from outside after run."""
    report = subagent.run()
    # The test verifies isolation structurally: _messages is a private attribute
    # that the parent never reads. We assert it exists but is separate.
    assert hasattr(subagent, "_messages")
    assert isinstance(subagent._messages, list)
```

#### `tests/integration/test_pipeline_10_calls.py`

```python
import pytest
from unittest.mock import patch, MagicMock
from algosentinel.agent.core import AgentLoop
from algosentinel.models.reports import AuditSummary

def test_pipeline_makes_at_least_10_calls():
    """
    Run AgentLoop with mocked GitHub API but real complexity tools and sandbox.
    Assert at least 10 tool calls are made and AuditSummary is returned.
    """
    # Use pytest-mock to mock PyGithub calls only
    with patch("algosentinel.tools.github.pr.Github") as mock_gh:
        # Set up mock PR with one changed Python file
        mock_pr = MagicMock()
        mock_pr.number = 1
        mock_pr.title = "Test PR"
        mock_pr.head.sha = "abc123"
        mock_pr.base.sha = "def456"
        # ... configure the mock fully
        mock_gh.return_value.get_repo.return_value.get_pull.return_value = mock_pr

        agent = AgentLoop()
        summary = agent.run(repo="test/test-repo", pr_numbers=[1])

    assert isinstance(summary, AuditSummary)
    assert summary.total_tool_calls >= 10

def test_context_compression_fires():
    """Assert that ContextManager._compress was called at least once."""
    with patch("algosentinel.agent.context.ContextManager._compress") as mock_compress, \
         patch("algosentinel.tools.github.pr.Github"):
        agent = AgentLoop()
        agent.run(repo="test/test-repo", pr_numbers=[1])
        # With COMPRESS_EVERY_N=6 and >=10 calls, compress must be called at least once
        assert mock_compress.call_count >= 1
```

---

## 16. FastAPI Webhook

Create `src/algosentinel/api/webhook.py`:

```python
from fastapi import FastAPI, Request, HTTPException, Header
import hmac
import hashlib
import asyncio
import structlog
from algosentinel.agent.core import AgentLoop
from algosentinel.config import settings

app = FastAPI(title="AlgoSentinel", version="0.1.0")
logger = structlog.get_logger()

@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_hub_signature_256: str = Header(None),
    x_github_event: str = Header(None),
):
    """
    Receives GitHub PR webhook events and triggers the agent asynchronously.
    Fires on: pull_request opened or synchronize (new commits pushed).
    """
    body = await request.body()

    # Verify the HMAC signature from GitHub
    if settings.github_webhook_secret:
        expected = "sha256=" + hmac.new(
            settings.github_webhook_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(expected, x_hub_signature_256 or ""):
            raise HTTPException(status_code=401, detail="Invalid HMAC signature")

    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event type is {x_github_event}"}

    payload = await request.json()
    action = payload.get("action")

    if action not in ("opened", "synchronize"):
        return {"status": "ignored", "reason": f"action is {action}"}

    repo = payload["repository"]["full_name"]
    pr_number = payload["pull_request"]["number"]

    logger.info("webhook_triggered", repo=repo, pr=pr_number, action=action)

    # Run agent in background — don't make GitHub wait for analysis to finish
    loop = asyncio.get_event_loop()
    loop.run_in_executor(
        None,
        lambda: AgentLoop().run(repo=repo, pr_numbers=[pr_number])
    )

    return {"status": "accepted", "repo": repo, "pr": pr_number}

@app.get("/health")
def health():
    """Health check endpoint. Also verifies tool registry is populated."""
    from algosentinel.tools.registry import ToolRegistry
    registry = ToolRegistry.get()
    return {
        "status": "ok",
        "tool_count": registry.tool_count(),
        "namespaces": registry.namespaces(),
        "tool_count_ok": registry.tool_count() >= 55,
    }
```

---

## 17. CLI Scripts

### `scripts/run_agent.py`

```python
#!/usr/bin/env python3
"""
Analyze one or more specific PRs.

Usage:
    python scripts/run_agent.py --repo owner/repo --pr 42
    python scripts/run_agent.py --repo owner/repo --pr 42 --pr 43
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

# Import all tool modules to trigger registration
import algosentinel.tools.github   # noqa: F401
import algosentinel.tools.sandbox  # noqa: F401
import algosentinel.tools.complexity  # noqa: F401
import algosentinel.tools.optimizer  # noqa: F401

import click
from algosentinel.agent.core import AgentLoop
from algosentinel.observability.logger import configure_logging

@click.command()
@click.option("--repo", required=True, help="GitHub repository in owner/repo format")
@click.option("--pr", required=True, type=int, multiple=True, help="PR number(s) to analyze")
@click.option("--verbose", is_flag=True, default=False, help="Use console log format")
def main(repo: str, pr: tuple, verbose: bool):
    if verbose:
        os.environ["LOG_FORMAT"] = "console"
    configure_logging()
    agent = AgentLoop()
    summary = agent.run(repo=repo, pr_numbers=list(pr))
    click.echo(summary.model_dump_json(indent=2))

if __name__ == "__main__":
    main()
```

### `scripts/audit_repo.py`

```python
#!/usr/bin/env python3
"""
Audit the last N closed PRs in a repository.

Usage:
    python scripts/audit_repo.py --repo owner/repo --last-n 10
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

import algosentinel.tools.github   # noqa: F401
import algosentinel.tools.sandbox  # noqa: F401
import algosentinel.tools.complexity  # noqa: F401
import algosentinel.tools.optimizer  # noqa: F401

import click
from algosentinel.agent.core import AgentLoop
from algosentinel.observability.logger import configure_logging
from algosentinel.tools.github.pr import list_recent_prs
from algosentinel.models.github import ListRecentPRsInput

@click.command()
@click.option("--repo", required=True, help="GitHub repository in owner/repo format")
@click.option("--last-n", default=10, show_default=True, help="Number of recent PRs to audit")
def main(repo: str, last_n: int):
    configure_logging()
    prs = list_recent_prs(ListRecentPRsInput(repo=repo, limit=last_n, state="closed"))
    pr_numbers = [pr["number"] for pr in prs]
    click.echo(f"Auditing PRs: {pr_numbers}")
    agent = AgentLoop()
    summary = agent.run(repo=repo, pr_numbers=pr_numbers)
    click.echo(summary.model_dump_json(indent=2))

if __name__ == "__main__":
    main()
```

---

## 18. Dockerfile and Compose

### `Dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached layer)
COPY pyproject.toml .
RUN pip install --no-cache-dir -e ".[dev]"

# Copy source
COPY . .

EXPOSE 8000

CMD ["uvicorn", "algosentinel.api.webhook:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info"]
```

### `docker-compose.yml`

```yaml
version: "3.9"
services:
  algosentinel:
    build: .
    ports:
      - "8000:8000"
    env_file:
      - .env
    volumes:
      # Mount Docker socket so the agent can spin up sandbox containers
      - /var/run/docker.sock:/var/run/docker.sock
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## 19. MEMO.md

Fill this in after all code is written. Be honest.

```markdown
# AlgoSentinel — MEMO

## What I Built
AlgoSentinel is an autonomous agent that detects algorithmic complexity regressions
in GitHub pull requests. When a PR changes a Python function from O(n) to O(n²),
the agent catches it before it ships — by empirically running both versions in a
Docker sandbox and fitting the timing data to complexity curves.

[Replace the above paragraph with a description of what your final implementation
actually does. Be specific: which parts work end-to-end, which were tested.]

## What I Cut
[List honestly what you didn't finish or simplified. Examples:]
- Sandbox isolation: [describe your actual approach — did you use Docker fully?]
- JavaScript support: not implemented — Python functions only
- Parallel subagent execution: subagents run serially, not concurrently
- [Add your own cuts here]

## What Additional Time Would Address
- [e.g., Parallel subagent execution for faster audits]
- [e.g., More robust input generation for graph and tree structures]
- [e.g., A web dashboard showing complexity drift over time across PRs]
- [e.g., Caching of timing results to avoid re-running unchanged functions]

## One Design Decision I Would Defend

**Empirical runtime measurement over pure static AST analysis.**

An engineer might reasonably argue: count loop nesting depth in the AST, infer O(n^d),
done — faster and simpler, no Docker required.

I defend empirical measurement because:

1. Static analysis is defeated by opaque function calls. A single `list.sort()` inside
   a loop looks like O(1) to AST analysis but is O(n log n), making the enclosing
   loop O(n² log n). The AST cannot see inside standard library calls.

2. Real complexity emerges from data structure behavior, not just syntax. A dictionary
   lookup in CPython is O(1) on average but O(n) in worst case with hash collisions.
   AST analysis would call it O(1). Empirical measurement catches the real behavior
   on realistic random inputs.

3. The PR review comment is defensible. "Your function took 2ms at n=100 and 8,000ms
   at n=1000 — the timing fits O(n²) with R²=0.99" is hard to argue with. "I counted
   two nested loops" is easier to dismiss.

The cost is Docker overhead (~2–3 seconds per sandbox). I accept this because AlgoSentinel
runs asynchronously — it doesn't block the developer's workflow.
```

---

## 20. Build Order and Commit Points

Follow this exact order. **Do not move to the next phase until all tests in the current
phase pass.**

### Phase 1 — Foundation (Day 1)
**Files to create:**
1. `pyproject.toml`, `.env.example`
2. `src/algosentinel/config.py`
3. `src/algosentinel/resilience/errors.py`
4. `src/algosentinel/resilience/retry.py`
5. `src/algosentinel/resilience/rate_limiter.py`
6. `src/algosentinel/observability/logger.py`
7. `src/algosentinel/observability/tracer.py`
8. All 5 model files in `src/algosentinel/models/`
9. `src/algosentinel/tools/registry.py`
10. `tests/unit/test_registry.py` (it will fail until tools are registered — that's fine)
11. `tests/unit/test_retry.py`
12. `tests/unit/test_rate_limiter.py`

**Tests that must pass before committing:**
```bash
pytest tests/unit/test_retry.py
pytest tests/unit/test_rate_limiter.py
```

**Commit message:**
```
feat(phase-1): scaffold models, registry, resilience, observability
```

---

### Phase 2 — Core Tools (Day 2)
**Files to create:**
1. All GitHub tool files (`tools/github/pr.py`, `files.py`, `reviews.py`, `branches.py`)
2. All sandbox tool files (`tools/sandbox/executor.py`, `profiler.py`, `generator.py`)
3. `tests/integration/test_sandbox_execution.py`

**Important:** Import all tool modules in `tools/__init__.py` so registration happens:
```python
# src/algosentinel/tools/__init__.py
from algosentinel.tools.github import pr, files, reviews, branches  # noqa
from algosentinel.tools.sandbox import executor, profiler, generator  # noqa
```

**Tests that must pass before committing:**
```bash
pytest tests/unit/test_registry.py   # should now show 32+ tools
pytest tests/integration/test_sandbox_execution.py  # requires Docker
```

**Commit message:**
```
feat(phase-2): implement github (18 tools) + sandbox (14 tools), 32/55 tools registered
```

---

### Phase 3 — Complexity + Context Manager + Subagent (Day 3)
**Files to create:**
1. All complexity tool files (`tools/complexity/inference.py`, `curve_fit.py`, `ast_scan.py`, `annotator.py`)
2. `src/algosentinel/agent/context.py`
3. `src/algosentinel/agent/subagent.py`
4. `tests/unit/test_curve_fit.py`
5. `tests/unit/test_context_manager.py`
6. `tests/integration/test_subagent_isolation.py`

**Add to `tools/__init__.py`:**
```python
from algosentinel.tools.complexity import inference, curve_fit, ast_scan, annotator  # noqa
```

**Tests that must pass before committing:**
```bash
pytest tests/unit/test_curve_fit.py
pytest tests/unit/test_context_manager.py
pytest tests/integration/test_subagent_isolation.py  # requires Docker + GEMINI_API_KEY
```

**Commit message:**
```
feat(phase-3): complexity tools (13), ContextManager, FunctionAnalysisSubagent, 45/55 tools
```

---

### Phase 4 — Optimizer + Agent Loop + API + CLI (Day 4)
**Files to create:**
1. All optimizer tool files (`tools/optimizer/generator.py`, `validator.py`, `reporter.py`)
2. `src/algosentinel/agent/planner.py`
3. `src/algosentinel/agent/core.py`
4. `src/algosentinel/api/webhook.py`
5. `scripts/run_agent.py`
6. `scripts/audit_repo.py`
7. `tests/integration/test_pipeline_10_calls.py`

**Add to `tools/__init__.py`:**
```python
from algosentinel.tools.optimizer import generator, validator, reporter  # noqa
```

**Tests that must pass before committing:**
```bash
pytest tests/unit/test_registry.py   # should now show 55 tools
pytest tests/integration/test_pipeline_10_calls.py
```

**Commit message:**
```
feat(phase-4): optimizer (10 tools), AgentLoop, webhook, CLI — 55/55 tools, full pipeline
```

---

### Phase 5 — Evals, MEMO, README (Day 5)
**Files to create:**
1. All 5 golden case JSON files in `evals/golden/`
2. `evals/harness.py`
3. `evals/metrics.py`
4. Fill in `MEMO.md`
5. Write `README.md`
6. Write `CLAUDE.md`
7. `Dockerfile` and `docker-compose.yml`

**Run evals and fix any failures:**
```bash
python evals/harness.py
```

**Final verification:**
```bash
pytest tests/unit/       # all pass, no Docker needed
pytest tests/integration/ # all pass, Docker running

python -c "
import algosentinel.tools.github
import algosentinel.tools.sandbox
import algosentinel.tools.complexity
import algosentinel.tools.optimizer
from algosentinel.tools.registry import ToolRegistry
r = ToolRegistry.get()
print(f'Tools: {r.tool_count()}')
print(f'Namespaces: {r.namespaces()}')
assert r.tool_count() >= 55
"
```

**Commit message:**
```
feat(phase-5): evals, golden cases, MEMO, README — submission ready
```

---

## 21. Final Checklist

Before submitting, verify each item by reading the code (not by running it):

- [ ] `ToolRegistry.get().tool_count()` returns >= 55 (check by counting `@tool` decorators)
- [ ] All 4 namespaces exist: `github`, `sandbox`, `complexity`, `optimizer`
- [ ] `FunctionAnalysisSubagent.__init__` creates `self._client = genai.Client(...)` — a new object
- [ ] `FunctionAnalysisSubagent.__init__` creates `self._messages: list = []` — a new list
- [ ] `ContextManager._compress()` is implemented (not just a comment)
- [ ] `ContextManager._compress()` is called inside `record_tool_call` when `total_calls % COMPRESS_EVERY_N == 0`
- [ ] The R5 chain is documented in comments: `profile_runtime → TimingPoint[] → fit_complexity_curves → CurveFit[] → infer_complexity_class → ComplexityClass → detect_regression → RegressionResult → generate_pr_review_body → str`
- [ ] `@with_retry()` is applied to all GitHub API calls
- [ ] `@with_retry()` is applied to all Gemini `generate_content` calls
- [ ] `TokenBucketRateLimiter` is instantiated in `AgentLoop.__init__` and passed to each subagent
- [ ] All 5 golden eval cases exist as JSON files
- [ ] `pytest tests/unit/` passes with no Docker required
- [ ] `pytest tests/integration/` passes with Docker running
- [ ] `MEMO.md` is filled in, honest, and contains the design decision defense
- [ ] Git history shows 5 commits, one per phase
- [ ] `README.md` contains: setup instructions, how to run with Docker Compose, how to run the CLI, how to run the evals
- [ ] `/health` endpoint returns `tool_count >= 55`

---

*End of specification.*