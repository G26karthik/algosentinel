import os

import pytest

from algosentinel.agent.subagent import FunctionAnalysisSubagent
from algosentinel.models.reports import ComplexityReport
from algosentinel.models.sandbox import FunctionCode
from algosentinel.resilience.rate_limiter import TokenBucketRateLimiter

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


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY required for subagent integration test",
)
def test_subagent_returns_typed_report(subagent):
    report = subagent.run()
    assert isinstance(report, ComplexityReport)


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY required",
)
def test_subagent_uses_at_least_5_tools(subagent):
    report = subagent.run()
    assert report.subagent_tool_calls_used >= 5


@pytest.mark.integration
@pytest.mark.skipif(
    not os.environ.get("GEMINI_API_KEY"),
    reason="GEMINI_API_KEY required",
)
def test_subagent_history_is_isolated(subagent):
    subagent.run()
    assert hasattr(subagent, "_messages")
    assert isinstance(subagent._messages, list)
