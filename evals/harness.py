"""
Eval harness: runs the complexity pipeline against each golden case and reports metrics.

Run with:
    python evals/harness.py
"""
import glob
import json
import os
import sys

_root = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(_root, "..", "src"))
sys.path.insert(0, os.path.join(_root, ".."))

# Import only sandbox + complexity modules (avoid loading GitHub/Gemini tool side effects)
import algosentinel.tools.sandbox.executor  # noqa: F401
import algosentinel.tools.sandbox.profiler  # noqa: F401
import algosentinel.tools.complexity.inference  # noqa: F401
import algosentinel.tools.complexity.curve_fit  # noqa: F401

from algosentinel.tools.complexity.inference import (
    DetectRegressionInput,
    InferComplexityClassInput,
    detect_regression,
    infer_complexity_class,
)
from algosentinel.tools.sandbox.executor import (
    CreateSandboxInput,
    DestroySandboxInput,
    create_sandbox,
    destroy_sandbox,
)
from algosentinel.tools.sandbox.profiler import ProfileRuntimeInput, profile_runtime
from evals.metrics import compute_metrics


def run_case(case: dict) -> dict:
    sandbox_id = create_sandbox(CreateSandboxInput())

    pre_timing = profile_runtime(
        ProfileRuntimeInput(
            sandbox_id=sandbox_id,
            code=case["pre_code"],
            function_name=case["function_name"],
            input_sizes=[10, 50, 100, 500, 1000, 5000],
        )
    )
    post_timing = profile_runtime(
        ProfileRuntimeInput(
            sandbox_id=sandbox_id,
            code=case["post_code"],
            function_name=case["function_name"],
            input_sizes=[10, 50, 100, 500, 1000, 5000],
        )
    )

    pre_class = infer_complexity_class(InferComplexityClassInput(timing_points=pre_timing))
    post_class = infer_complexity_class(InferComplexityClassInput(timing_points=post_timing))
    regression = detect_regression(
        DetectRegressionInput(pre_class=pre_class, post_class=post_class)
    )

    destroy_sandbox(DestroySandboxInput(sandbox_id=sandbox_id))

    return {
        "id": case["id"],
        "expected_regression": case["expected_regression"],
        "detected_regression": regression.is_regression,
        "expected_pre_class": case.get("expected_pre_class"),
        "detected_pre_class": pre_class.notation,
        "expected_post_class": case.get("expected_post_class"),
        "detected_post_class": post_class.notation,
        "severity": regression.severity,
        "passed": regression.is_regression == case["expected_regression"],
    }


def main():
    cases = []
    base = os.path.join(os.path.dirname(__file__), "golden")
    for path in sorted(glob.glob(os.path.join(base, "*.json"))):
        with open(path) as f:
            data = json.load(f)
            if "functions" in data:
                for fn in data["functions"]:
                    cases.append(fn)
            else:
                cases.append(data)

    results = [run_case(c) for c in cases]
    metrics = compute_metrics(results)

    print("\n=== AlgoSentinel Eval Results ===")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        print(
            f"{status} | {r['id']}: expected {r['expected_post_class']}, "
            f"got {r['detected_post_class']} | regression={r['detected_regression']}"
        )
    print(f"\nPrecision: {metrics['precision']:.2f}")
    print(f"Recall:    {metrics['recall']:.2f}")
    print(f"F1:        {metrics['f1']:.2f}")
    print(f"Fix rate:  {metrics['fix_success_rate']:.2f}")


if __name__ == "__main__":
    main()
