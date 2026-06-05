"""
R5 composability chain (terminal step):
  optimizer.generate_pr_review_body consumes RegressionResult via ComplexityReport list
  → returns str (PR review Markdown)
"""

from pydantic import BaseModel

from algosentinel.models.reports import AuditSummary, ComplexityReport
from algosentinel.models.sandbox import BenchmarkPairResult
from algosentinel.models.complexity import ASTComplexityHints
from algosentinel.tools.optimizer.generator import _gemini_generate
from algosentinel.tools.registry import tool


class GeneratePRReviewBodyInput(BaseModel):
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


class SummarizeAuditFindingsInput(BaseModel):
    reports: list[ComplexityReport]
    repo: str


@tool(
    namespace="optimizer",
    description="Format regression reports into a Markdown PR review comment.",
    input_model=GeneratePRReviewBodyInput,
    output_model=str,
)
def generate_pr_review_body(inp: GeneratePRReviewBodyInput) -> str:
    lines = [
        "## AlgoSentinel — Complexity Audit",
        "",
        f"Repository: `{inp.repo}` · PR #{inp.pr_number}",
        "",
    ]
    regressions = [r for r in inp.regression_reports if r.regression.is_regression]
    if not regressions:
        lines.append("No algorithmic complexity regressions detected.")
        return "\n".join(lines)
    lines.append(f"**{len(regressions)} regression(s) detected:**")
    lines.append("")
    for r in regressions:
        lines.append(f"### `{r.function_name}` (`{r.file_path}`)")
        lines.append(
            f"- **Before:** {r.pre_class.notation} (R²={r.pre_class.supporting_r_squared:.2f})"
        )
        lines.append(
            f"- **After:** {r.post_class.notation} (R²={r.post_class.supporting_r_squared:.2f})"
        )
        lines.append(f"- **Severity:** {r.regression.severity}")
        lines.append(f"- {r.explanation}")
        if r.evidence:
            lines.append("- Timing evidence:")
            for pt in r.evidence[:4]:
                lines.append(f"  - n={pt.input_size}: {pt.elapsed_ms:.2f}ms")
        lines.append("")
    return "\n".join(lines)


@tool(
    namespace="optimizer",
    description="Write the PR description body for a fix PR.",
    input_model=GenerateFixPRBodyInput,
    output_model=str,
)
def generate_fix_pr_body(inp: GenerateFixPRBodyInput) -> str:
    ratios = [p.ratio for p in inp.benchmark_comparison.points]
    avg_ratio = sum(ratios) / len(ratios) if ratios else 1.0
    return (
        f"## Fix: restore complexity for `{inp.function_name}`\n\n"
        f"Restores **{inp.original_class}** from **{inp.fixed_class}**.\n\n"
        f"{inp.explanation}\n\n"
        f"Average post/pre timing ratio after fix: {avg_ratio:.2f}x"
    )


@tool(
    namespace="optimizer",
    description="Plain-English explanation of why a regression occurred.",
    input_model=ExplainRegressionInput,
    output_model=str,
)
def explain_regression(inp: ExplainRegressionInput) -> str:
    prompt = (
        f"Explain in 2-3 sentences why complexity regressed from {inp.pre_class} to "
        f"{inp.post_class} for this function. AST: depth={inp.ast_hints.max_loop_nesting_depth}, "
        f"patterns={inp.ast_hints.suspicious_patterns}\n\n"
        f"PRE:\n```python\n{inp.pre_code}\n```\n\n"
        f"POST:\n```python\n{inp.post_code}\n```"
    )
    try:
        return _gemini_generate(prompt).strip()
    except Exception:
        return (
            f"Complexity increased from {inp.pre_class} to {inp.post_class}. "
            f"Loop nesting depth is {inp.ast_hints.max_loop_nesting_depth}."
        )


@tool(
    namespace="optimizer",
    description="Aggregate ComplexityReports into an AuditSummary.",
    input_model=SummarizeAuditFindingsInput,
    output_model=AuditSummary,
)
def summarize_audit_findings(inp: SummarizeAuditFindingsInput) -> AuditSummary:
    regressions = [r for r in inp.reports if r.regression.is_regression]
    critical = sum(1 for r in regressions if r.regression.severity == "critical")
    moderate = sum(1 for r in regressions if r.regression.severity == "moderate")
    fixes_gen = sum(1 for r in inp.reports if r.fix_generated)
    fixes_ver = sum(1 for r in inp.reports if r.fix_verified)
    return AuditSummary(
        repo=inp.repo,
        prs_audited=0,
        functions_analyzed=len(inp.reports),
        regressions_found=len(regressions),
        regressions_critical=critical,
        regressions_moderate=moderate,
        fixes_generated=fixes_gen,
        fixes_verified=fixes_ver,
        fix_prs_opened=[],
        total_tool_calls=sum(r.subagent_tool_calls_used for r in inp.reports),
        session_duration_seconds=0.0,
        reports=inp.reports,
    )
