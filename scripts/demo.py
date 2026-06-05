#!/usr/bin/env python3
"""
End-to-end demo: complexity pipeline + PR review generation (no full AgentLoop).

Usage:
    python scripts/demo.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

import algosentinel.tools.complexity.inference  # noqa: F401
import algosentinel.tools.complexity.curve_fit  # noqa: F401
import algosentinel.tools.sandbox.executor  # noqa: F401
import algosentinel.tools.sandbox.profiler  # noqa: F401
import algosentinel.tools.optimizer.reporter  # noqa: F401

from algosentinel.models.complexity import ASTComplexityHints
from algosentinel.models.reports import ComplexityReport
from algosentinel.tools.complexity.ast_scan import ScanASTInput, scan_ast_for_hints
from algosentinel.tools.complexity.inference import (
    DetectRegressionInput,
    InferComplexityClassInput,
    detect_regression,
    infer_complexity_class,
)
from algosentinel.tools.optimizer.reporter import GeneratePRReviewBodyInput, generate_pr_review_body
from algosentinel.tools.sandbox.executor import CreateSandboxInput, DestroySandboxInput, create_sandbox, destroy_sandbox
from algosentinel.tools.sandbox.profiler import ProfileRuntimeInput, profile_runtime

CASE_PATH = os.path.join(os.path.dirname(__file__), "../evals/golden/case_001_on_to_on2.json")


def main():
    with open(CASE_PATH) as f:
        case = json.load(f)

    print("=== AlgoSentinel Demo ===")
    print(f"Case: {case['description']}\n")

    sandbox_id = create_sandbox(CreateSandboxInput())
    sizes = [10, 50, 100, 500, 1000, 5000]

    print("[1/5] Profiling PRE-change code in Docker sandbox...")
    pre_timing = profile_runtime(
        ProfileRuntimeInput(
            sandbox_id=sandbox_id,
            code=case["pre_code"],
            function_name=case["function_name"],
            input_sizes=sizes,
        )
    )
    print(f"      {len(pre_timing)} timing points, n=1000 -> {next(p.elapsed_ms for p in pre_timing if p.input_size==1000):.2f}ms")

    print("[2/5] Profiling POST-change code...")
    post_timing = profile_runtime(
        ProfileRuntimeInput(
            sandbox_id=sandbox_id,
            code=case["post_code"],
            function_name=case["function_name"],
            input_sizes=sizes,
        )
    )
    print(f"      {len(post_timing)} timing points, n=1000 -> {next(p.elapsed_ms for p in post_timing if p.input_size==1000):.2f}ms")

    print("[3/5] Fitting complexity curves & detecting regression...")
    pre_class = infer_complexity_class(InferComplexityClassInput(timing_points=pre_timing))
    post_class = infer_complexity_class(InferComplexityClassInput(timing_points=post_timing))
    regression = detect_regression(
        DetectRegressionInput(pre_class=pre_class, post_class=post_class)
    )
    print(f"      PRE:  {pre_class.notation} (R²={pre_class.supporting_r_squared:.2f})")
    print(f"      POST: {post_class.notation} (R²={post_class.supporting_r_squared:.2f})")
    print(f"      Regression: {regression.is_regression} ({regression.severity})")

    print("[4/5] AST hints on post-change code...")
    hints = scan_ast_for_hints(
        ScanASTInput(code=case["post_code"], function_name=case["function_name"])
    )
    print(f"      Loop depth: {hints.max_loop_nesting_depth}, patterns: {hints.suspicious_patterns}")

    destroy_sandbox(DestroySandboxInput(sandbox_id=sandbox_id))

    report = ComplexityReport(
        function_name=case["function_name"],
        file_path="utils.py",
        pre_class=pre_class,
        post_class=post_class,
        regression=regression,
        evidence=post_timing,
        ast_hints=hints,
        explanation=(
            f"`{case['function_name']}` regressed from {pre_class.notation} to "
            f"{post_class.notation}. Nested slice lookup replaced O(n) set membership."
        ),
    )

    print("[5/5] Generating PR review comment...")
    review = generate_pr_review_body(
        GeneratePRReviewBodyInput(
            regression_reports=[report],
            repo="example/demo-repo",
            pr_number=42,
        )
    )
    print("\n--- Generated PR Review (excerpt) ---")
    print(review[:800])
    print("\n=== Demo complete: pipeline OK ===")
    return regression.is_regression


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
