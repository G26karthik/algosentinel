"""
R5 composability chain (steps 3–4):
  infer_complexity_class consumes CurveFits → ComplexityClass
  detect_regression consumes two ComplexityClass → RegressionResult
  → consumed by optimizer.generate_pr_review_body
"""

from pydantic import BaseModel

from algosentinel.config import settings
from algosentinel.models.complexity import (
    ComplexityClass,
    ComplexityOrder,
    ConfidenceInterval,
    RegressionResult,
)
from algosentinel.models.sandbox import TimingPoint
from algosentinel.tools.complexity.curve_fit import fit_complexity_curves, FitComplexityCurvesInput
from algosentinel.tools.registry import tool


class InferComplexityClassInput(BaseModel):
    timing_points: list[TimingPoint]
    min_confidence: float = 0.85


class DetectRegressionInput(BaseModel):
    pre_class: ComplexityClass
    post_class: ComplexityClass


class CompareComplexityClassesInput(BaseModel):
    class_a: ComplexityClass
    class_b: ComplexityClass


class ComputeConfidenceIntervalInput(BaseModel):
    timing_points: list[TimingPoint]
    class_name: str


class ClassifyRegressionSeverityInput(BaseModel):
    pre_class: ComplexityClass
    post_class: ComplexityClass


@tool(
    namespace="complexity",
    description="Infer the best-fitting complexity class from timing points.",
    input_model=InferComplexityClassInput,
    output_model=ComplexityClass,
)
def infer_complexity_class(inp: InferComplexityClassInput) -> ComplexityClass:
    fits = fit_complexity_curves(FitComplexityCurvesInput(timing_points=inp.timing_points))
    if not fits:
        return ComplexityClass(
            notation="O(1)",
            order=ComplexityOrder.CONSTANT,
            confidence=0.0,
            supporting_r_squared=0.0,
            all_fits=[],
        )
    best = fits[0]
    confidence = min(1.0, best.r_squared)
    return ComplexityClass(
        notation=best.complexity_class,
        order=best.order,
        confidence=confidence,
        supporting_r_squared=best.r_squared,
        all_fits=fits,
    )


@tool(
    namespace="complexity",
    description="Detect whether post-PR complexity is worse than pre-PR.",
    input_model=DetectRegressionInput,
    output_model=RegressionResult,
)
def detect_regression(inp: DetectRegressionInput) -> RegressionResult:
    orders_worse = int(inp.post_class.order) - int(inp.pre_class.order)
    is_regression = orders_worse > 0
    severity = classify_regression_severity(
        ClassifyRegressionSeverityInput(
            pre_class=inp.pre_class,
            post_class=inp.post_class,
        )
    )
    confidence = min(inp.pre_class.confidence, inp.post_class.confidence)
    if confidence < settings.min_regression_confidence and is_regression:
        is_regression = False
        severity = "none"
        orders_worse = 0
    return RegressionResult(
        is_regression=is_regression,
        severity=severity,
        pre_class=inp.pre_class,
        post_class=inp.post_class,
        orders_worse=max(0, orders_worse),
        confidence=confidence,
    )


@tool(
    namespace="complexity",
    description="Compare two complexity classes.",
    input_model=CompareComplexityClassesInput,
    output_model=dict,
)
def compare_complexity_classes(inp: CompareComplexityClassesInput) -> dict:
    delta = int(inp.class_b.order) - int(inp.class_a.order)
    return {
        "class_a": inp.class_a.notation,
        "class_b": inp.class_b.notation,
        "b_is_worse": delta > 0,
        "order_delta": delta,
    }


@tool(
    namespace="complexity",
    description="Bootstrap confidence interval on timing at best-fit class.",
    input_model=ComputeConfidenceIntervalInput,
    output_model=ConfidenceInterval,
)
def compute_confidence_interval(inp: ComputeConfidenceIntervalInput) -> ConfidenceInterval:
    times = [p.elapsed_ms for p in inp.timing_points]
    if not times:
        return ConfidenceInterval(lower=0.0, upper=0.0, mean=0.0)
    import statistics

    mean = statistics.mean(times)
    if len(times) < 2:
        return ConfidenceInterval(lower=mean, upper=mean, mean=mean)
    stdev = statistics.stdev(times)
    return ConfidenceInterval(
        lower=mean - 1.96 * stdev,
        upper=mean + 1.96 * stdev,
        mean=mean,
    )


@tool(
    namespace="complexity",
    description="Classify regression severity from order delta.",
    input_model=ClassifyRegressionSeverityInput,
    output_model=str,
)
def classify_regression_severity(inp: ClassifyRegressionSeverityInput) -> str:
    delta = int(inp.post_class.order) - int(inp.pre_class.order)
    if delta <= 0:
        return "none"
    if delta >= settings.severity_critical_threshold:
        return "critical"
    if delta == 1:
        return "moderate"
    return "minor"
