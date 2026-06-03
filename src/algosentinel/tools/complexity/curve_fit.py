"""
R5 composability chain (step 2):
  complexity.fit_complexity_curves consumes list[TimingPoint] from profile_runtime
  → returns list[CurveFit] for infer_complexity_class
"""

import numpy as np
from pydantic import BaseModel
from scipy.optimize import curve_fit

from algosentinel.models.complexity import ComplexityOrder, CurveFit
from algosentinel.models.sandbox import TimingPoint
from algosentinel.tools.registry import tool

COMPLEXITY_FUNCTIONS = {
    "O(1)": (lambda n, a: np.full_like(n, a, dtype=float), ComplexityOrder.CONSTANT),
    "O(log n)": (lambda n, a, b: a * np.log(n + 1) + b, ComplexityOrder.LOG),
    "O(n)": (lambda n, a, b: a * n + b, ComplexityOrder.LINEAR),
    "O(n log n)": (lambda n, a, b: a * n * np.log(n + 1) + b, ComplexityOrder.NLOGN),
    "O(n^2)": (lambda n, a, b: a * n**2 + b, ComplexityOrder.QUADRATIC),
    "O(n^3)": (lambda n, a, b: a * n**3 + b, ComplexityOrder.CUBIC),
    "O(2^n)": (lambda n, a, b: a * 2.0 ** np.clip(n, 0, 30) + b, ComplexityOrder.EXPONENTIAL),
}


class FitComplexityCurvesInput(BaseModel):
    timing_points: list[TimingPoint]


class ComputeRSquaredInput(BaseModel):
    timing_points: list[TimingPoint]
    complexity_class: str


def _r_squared(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    ss_res = np.sum((y_true - y_pred) ** 2)
    ss_tot = np.sum((y_true - np.mean(y_true)) ** 2)
    if ss_tot == 0:
        return 1.0 if ss_res == 0 else 0.0
    return float(max(0.0, 1.0 - ss_res / ss_tot))


@tool(
    namespace="complexity",
    description="Fit timing data to all complexity curve models; returns CurveFits sorted by R².",
    input_model=FitComplexityCurvesInput,
    output_model=list,
)
def fit_complexity_curves(inp: FitComplexityCurvesInput) -> list[CurveFit]:
    if len(inp.timing_points) < 2:
        return []
    sizes = np.array([p.input_size for p in inp.timing_points], dtype=float)
    times = np.array([p.elapsed_ms for p in inp.timing_points], dtype=float)
    fits: list[CurveFit] = []
    for name, (func, order) in COMPLEXITY_FUNCTIONS.items():
        try:
            popt, _ = curve_fit(func, sizes, times, maxfev=10000)
            predicted = func(sizes, *popt)
            r2 = _r_squared(times, predicted)
            fits.append(
                CurveFit(
                    complexity_class=name,
                    order=order,
                    r_squared=r2,
                    coefficients=[float(x) for x in popt],
                    is_best_fit=False,
                )
            )
        except (RuntimeError, ValueError):
            continue
    fits.sort(key=lambda f: f.r_squared, reverse=True)
    if fits:
        best = fits[0].model_copy(update={"is_best_fit": True})
        fits[0] = best
    return fits


@tool(
    namespace="complexity",
    description="Compute R² for one complexity class against timing data.",
    input_model=ComputeRSquaredInput,
    output_model=float,
)
def compute_r_squared(inp: ComputeRSquaredInput) -> float:
    fits = fit_complexity_curves(FitComplexityCurvesInput(timing_points=inp.timing_points))
    for f in fits:
        if f.complexity_class == inp.complexity_class:
            return f.r_squared
    return 0.0
