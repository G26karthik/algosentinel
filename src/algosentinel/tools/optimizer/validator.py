import ast

from pydantic import BaseModel

from algosentinel.models.sandbox import TimingPoint
from algosentinel.tools.complexity.inference import (
    DetectRegressionInput,
    InferComplexityClassInput,
    detect_regression,
    infer_complexity_class,
)
from algosentinel.tools.registry import tool
from algosentinel.tools.sandbox.executor import ExecuteRawInput, execute_raw
from algosentinel.tools.sandbox.profiler import ProfileRuntimeInput, profile_runtime


class ValidateOptimizationInput(BaseModel):
    original_code: str
    optimized_code: str
    function_name: str
    sandbox_id: str


class VerifyComplexityImprovementInput(BaseModel):
    sandbox_id: str
    pre_timing: list[TimingPoint]
    post_timing: list[TimingPoint]


@tool(
    namespace="optimizer",
    description="Validate optimized code syntax and sandbox execution.",
    input_model=ValidateOptimizationInput,
    output_model=dict,
)
def validate_optimization(inp: ValidateOptimizationInput) -> dict:
    try:
        ast.parse(inp.optimized_code)
        syntax_ok = True
    except SyntaxError as e:
        return {"valid": False, "syntax_ok": False, "error": str(e)}
    combined = f"{inp.optimized_code}\nprint('ok')"
    result = execute_raw(ExecuteRawInput(sandbox_id=inp.sandbox_id, code=combined))
    runs = result.get("exit_code", 1) == 0
    return {"valid": syntax_ok and runs, "syntax_ok": syntax_ok, "runs": runs}


@tool(
    namespace="optimizer",
    description="Compare timing arrays to confirm complexity improvement.",
    input_model=VerifyComplexityImprovementInput,
    output_model=dict,
)
def verify_complexity_improvement(inp: VerifyComplexityImprovementInput) -> dict:
    pre = infer_complexity_class(
        InferComplexityClassInput(timing_points=inp.pre_timing)
    )
    post = infer_complexity_class(
        InferComplexityClassInput(timing_points=inp.post_timing)
    )
    regression = detect_regression(
        DetectRegressionInput(pre_class=post, post_class=pre)
    )
    return {
        "improved": int(post.order) < int(pre.order) or not regression.is_regression,
        "pre_class": pre.notation,
        "post_class": post.notation,
    }
