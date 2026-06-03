from enum import IntEnum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ComplexityOrder(IntEnum):
    CONSTANT = 1
    LOG = 2
    LINEAR = 3
    NLOGN = 4
    QUADRATIC = 5
    CUBIC = 6
    EXPONENTIAL = 7


COMPLEXITY_NOTATIONS = {
    ComplexityOrder.CONSTANT: "O(1)",
    ComplexityOrder.LOG: "O(log n)",
    ComplexityOrder.LINEAR: "O(n)",
    ComplexityOrder.NLOGN: "O(n log n)",
    ComplexityOrder.QUADRATIC: "O(n^2)",
    ComplexityOrder.CUBIC: "O(n^3)",
    ComplexityOrder.EXPONENTIAL: "O(2^n)",
}


class CurveFit(BaseModel):
    complexity_class: str
    order: ComplexityOrder
    r_squared: float
    coefficients: list[float]
    is_best_fit: bool = False


class ComplexityClass(BaseModel):
    notation: str
    order: ComplexityOrder
    confidence: float
    supporting_r_squared: float
    all_fits: list[CurveFit]


class RegressionResult(BaseModel):
    is_regression: bool
    severity: Literal["none", "minor", "moderate", "critical"]
    pre_class: ComplexityClass
    post_class: ComplexityClass
    orders_worse: int
    confidence: float


class ASTComplexityHints(BaseModel):
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
