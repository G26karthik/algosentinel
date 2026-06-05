import numpy as np
import pytest

from algosentinel.models.sandbox import TimingPoint
from algosentinel.tools.complexity.inference import (
    DetectRegressionInput,
    InferComplexityClassInput,
    detect_regression,
    infer_complexity_class,
)


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
    assert result.notation in ("O(n log n)", "O(n)")


def test_detect_regression_on_to_on2():
    linear_points = make_timing(SIZES, [n * 0.001 for n in SIZES])
    quad_points = make_timing(SIZES, [n**2 * 0.000001 for n in SIZES])
    pre = infer_complexity_class(InferComplexityClassInput(timing_points=linear_points))
    post = infer_complexity_class(InferComplexityClassInput(timing_points=quad_points))
    result = detect_regression(DetectRegressionInput(pre_class=pre, post_class=post))
    assert result.is_regression is True


def test_detect_no_regression():
    times_a = [n * 0.001 for n in SIZES]
    times_b = [n * 0.002 for n in SIZES]
    pre = infer_complexity_class(
        InferComplexityClassInput(timing_points=make_timing(SIZES, times_a))
    )
    post = infer_complexity_class(
        InferComplexityClassInput(timing_points=make_timing(SIZES, times_b))
    )
    result = detect_regression(DetectRegressionInput(pre_class=pre, post_class=post))
    assert result.is_regression is False
