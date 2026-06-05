from datetime import UTC, datetime

from algosentinel.agent.context import ContextManager
from algosentinel.agent.planner import build_plan
from algosentinel.models.tools import ToolCallRecord


def make_record(n: int) -> ToolCallRecord:
    return ToolCallRecord(
        call_number=n,
        namespace="github",
        tool_name="get_pr_details",
        input_summary="repo=test/repo",
        result_summary="PR #1 fetched",
        duration_ms=50.0,
        success=True,
        timestamp=datetime.now(UTC),
    )


def test_plan_always_in_system_prompt():
    plan = build_plan(repo="test/repo", pr_numbers=[1])
    ctx = ContextManager(plan=plan)
    prompt = ctx.build_system_prompt()
    assert plan.goal in prompt


def test_compression_fires_at_n():
    plan = build_plan(repo="test/repo", pr_numbers=[1])
    ctx = ContextManager(plan=plan)
    n = ctx.COMPRESS_EVERY_N
    for i in range(1, n + 1):
        ctx.record_tool_call(make_record(i))
    assert len(ctx.tool_history) == 0
    assert ctx.rolling_summary != ""


def test_tool_history_empty_after_compression():
    plan = build_plan(repo="test/repo", pr_numbers=[1])
    ctx = ContextManager(plan=plan)
    for i in range(ctx.COMPRESS_EVERY_N):
        ctx.record_tool_call(make_record(i + 1))
    assert ctx.tool_history == []


def test_plan_in_prompt_after_multiple_compressions():
    plan = build_plan(repo="test/repo", pr_numbers=[1])
    ctx = ContextManager(plan=plan)
    for i in range(ctx.COMPRESS_EVERY_N * 3):
        ctx.record_tool_call(make_record(i + 1))
    prompt = ctx.build_system_prompt()
    assert plan.goal in prompt
    assert plan.repo in prompt
