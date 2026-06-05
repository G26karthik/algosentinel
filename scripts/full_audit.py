#!/usr/bin/env python3
"""
Full PR audit without Gemini orchestration — runs the intended tool pipeline directly.

Usage:
    python scripts/full_audit.py --repo G26karthik/algosentinel --pr 1
"""
import ast
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

import algosentinel.tools.complexity  # noqa: F401
import algosentinel.tools.github  # noqa: F401
import algosentinel.tools.optimizer  # noqa: F401
import algosentinel.tools.sandbox  # noqa: F401

import click

from algosentinel.models.reports import ComplexityReport
from algosentinel.models.sandbox import FunctionCode
from algosentinel.tools.complexity.ast_scan import ScanASTInput, scan_ast_for_hints
from algosentinel.tools.complexity.inference import (
    DetectRegressionInput,
    InferComplexityClassInput,
    detect_regression,
    infer_complexity_class,
)
from algosentinel.tools.github.files import GetFileContentInput, get_file_content
from algosentinel.tools.github.pr import GetPRDetailsInput, GetPRDiffInput, get_pr_details, get_pr_diff
from algosentinel.tools.github.reviews import PostPRReviewInput, post_pr_review
from algosentinel.tools.optimizer.reporter import (
    GeneratePRReviewBodyInput,
    SummarizeAuditFindingsInput,
    generate_pr_review_body,
    summarize_audit_findings,
)
from algosentinel.tools.registry import ToolRegistry
from algosentinel.tools.sandbox.executor import CreateSandboxInput, DestroySandboxInput, create_sandbox, destroy_sandbox
from algosentinel.tools.sandbox.generator import ExtractFunctionInput, extract_function
from algosentinel.tools.sandbox.profiler import ProfileRuntimeInput, profile_runtime


def _changed_functions(pre_code: str, post_code: str, path: str) -> list[str]:
    pre_tree = ast.parse(pre_code)
    post_tree = ast.parse(post_code)
    pre_names = {n.name for n in ast.walk(pre_tree) if isinstance(n, ast.FunctionDef)}
    post_names = {n.name for n in ast.walk(post_tree) if isinstance(n, ast.FunctionDef)}
    changed = []
    for name in pre_names & post_names:
        pre_fn = ast.get_source_segment(pre_code, next(n for n in ast.walk(pre_tree) if isinstance(n, ast.FunctionDef) and n.name == name))
        post_fn = ast.get_source_segment(post_code, next(n for n in ast.walk(post_tree) if isinstance(n, ast.FunctionDef) and n.name == name))
        if pre_fn != post_fn:
            changed.append(name)
    for name in post_names - pre_names:
        changed.append(name)
    return changed


def analyze_function(
    sandbox_id: str,
    name: str,
    pre_code: str,
    post_code: str,
    path: str,
) -> ComplexityReport:
    pre_fn = extract_function(ExtractFunctionInput(code=pre_code, function_name=name))
    post_fn = extract_function(ExtractFunctionInput(code=post_code, function_name=name))
    pre_fn.file_path = path
    post_fn.file_path = path
    sizes = [10, 50, 100, 500, 1000, 5000]

    pre_timing = profile_runtime(
        ProfileRuntimeInput(
            sandbox_id=sandbox_id,
            code=pre_fn.source_code,
            function_name=name,
            input_sizes=sizes,
        )
    )
    post_timing = profile_runtime(
        ProfileRuntimeInput(
            sandbox_id=sandbox_id,
            code=post_fn.source_code,
            function_name=name,
            input_sizes=sizes,
        )
    )
    pre_class = infer_complexity_class(InferComplexityClassInput(timing_points=pre_timing))
    post_class = infer_complexity_class(InferComplexityClassInput(timing_points=post_timing))
    regression = detect_regression(
        DetectRegressionInput(pre_class=pre_class, post_class=post_class)
    )
    hints = scan_ast_for_hints(ScanASTInput(code=post_fn.source_code, function_name=name))
    explanation = (
        f"`{name}` changed from {pre_class.notation} to {post_class.notation}. "
        f"Empirical sandbox profiling detected a complexity regression."
        if regression.is_regression
        else f"`{name}` remains {post_class.notation}; no order regression detected."
    )
    return ComplexityReport(
        function_name=name,
        file_path=path,
        pre_class=pre_class,
        post_class=post_class,
        regression=regression,
        evidence=post_timing,
        ast_hints=hints,
        explanation=explanation,
        subagent_tool_calls_used=8,
    )


@click.command()
@click.option("--repo", required=True)
@click.option("--pr", "pr_number", required=True, type=int)
@click.option("--post-review/--no-post-review", default=True)
def main(repo: str, pr_number: int, post_review: bool):
    start = time.time()
    registry = ToolRegistry.get()
    assert registry.tool_count() >= 55

    print(f"=== Full audit: {repo} PR #{pr_number} ===")
    details = get_pr_details(GetPRDetailsInput(repo=repo, pr_number=pr_number))
    diff = get_pr_diff(GetPRDiffInput(repo=repo, pr_number=pr_number))
    print(f"PR: {details.title.encode('ascii', 'replace').decode()}")
    print(f"Files changed: {len(diff.files)}")

    reports: list[ComplexityReport] = []
    sandbox_id = create_sandbox(CreateSandboxInput())
    tool_calls = 4

    try:
        for f in diff.files:
            if not f.filename.endswith(".py"):
                continue
            pre_code = get_file_content(
                GetFileContentInput(repo=repo, path=f.filename, ref=details.base_sha)
            )
            post_code = get_file_content(
                GetFileContentInput(repo=repo, path=f.filename, ref=details.head_sha)
            )
            tool_calls += 2
            for fn_name in _changed_functions(pre_code, post_code, f.filename):
                print(f"Analyzing {f.filename}::{fn_name} ...")
                report = analyze_function(sandbox_id, fn_name, pre_code, post_code, f.filename)
                tool_calls += 8
                reports.append(report)
                print(
                    f"  {report.pre_class.notation} -> {report.post_class.notation} "
                    f"| regression={report.regression.is_regression} ({report.regression.severity})"
                )
    finally:
        destroy_sandbox(DestroySandboxInput(sandbox_id=sandbox_id))
        tool_calls += 1

    review_body = generate_pr_review_body(
        GeneratePRReviewBodyInput(
            regression_reports=reports,
            repo=repo,
            pr_number=pr_number,
        )
    )
    tool_calls += 1

    if post_review:
        result = post_pr_review(
            PostPRReviewInput(
                repo=repo,
                pr_number=pr_number,
                body=review_body,
                event="COMMENT",
            )
        )
        tool_calls += 1
        print(f"Posted review: {result.url}")

    summary = summarize_audit_findings(
        SummarizeAuditFindingsInput(reports=reports, repo=repo)
    )
    summary.prs_audited = 1
    summary.total_tool_calls = tool_calls
    summary.session_duration_seconds = round(time.time() - start, 2)
    tool_calls += 1

    print("\n--- AuditSummary ---")
    print(summary.model_dump_json(indent=2))
    return summary


if __name__ == "__main__":
    main()
