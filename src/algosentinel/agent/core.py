import json
import time

import structlog
from google import genai
from google.genai import types as genai_types

from algosentinel.agent.context import ContextManager
from algosentinel.agent.planner import build_plan
from algosentinel.config import settings
from algosentinel.models.reports import AuditSummary
from algosentinel.models.tools import ToolCallRecord
from google.genai import errors as genai_errors
from algosentinel.resilience.errors import FatalError, RateLimitError
from algosentinel.resilience.rate_limiter import TokenBucketRateLimiter
from algosentinel.resilience.retry import with_retry
from algosentinel.tools.registry import ToolRegistry

logger = structlog.get_logger()


class AgentLoop:
    """Parent agent using all 55 tools; delegates function analysis to subagents."""

    MAX_ITERATIONS = 60

    def __init__(self):
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._rate_limiter = TokenBucketRateLimiter(rate_per_minute=settings.gemini_max_rpm)
        self._log = logger.bind(component="AgentLoop")
        self._reports: list = []

    @with_retry(max_attempts=6, min_wait=2.0, max_wait=90.0)
    def _generate(self, messages: list, tool_config: genai_types.Tool, system: str):
        try:
            return self._client.models.generate_content(
                model=settings.gemini_model,
                contents=[
                    {"role": "user", "parts": [{"text": system}]},
                    *messages,
                ],
                config=genai_types.GenerateContentConfig(
                    tools=[tool_config],
                    max_output_tokens=settings.gemini_max_tokens,
                ),
            )
        except genai_errors.ClientError as e:
            if e.code == 429:
                raise RateLimitError(str(e)) from e
            raise

    def run(self, repo: str, pr_numbers: list[int]) -> AuditSummary:
        registry = ToolRegistry.get()
        count = registry.tool_count()
        assert count >= 55, f"Expected >=55 tools, got {count}. Import all tool modules."

        plan = build_plan(repo=repo, pr_numbers=pr_numbers)
        ctx = ContextManager(plan=plan)
        tool_config = genai_types.Tool(
            function_declarations=registry.get_function_declarations()
        )

        messages = [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"Audit the repository {repo} for algorithmic complexity regressions "
                            f"in pull request(s) {pr_numbers}.\n\n"
                            f"For each PR:\n"
                            f"1. Fetch the PR diff and list changed Python files.\n"
                            f"2. For each changed .py file, get both pre-change and post-change content.\n"
                            f"3. Extract each changed function using sandbox__extract_function.\n"
                            f"4. For each changed function, call github__spawn_function_analysis_subagent "
                            f"   with both versions.\n"
                            f"5. Collect all ComplexityReports.\n"
                            f"6. For regressions, call optimizer__generate_optimized_alternative "
                            f"   and optimizer__validate_optimization.\n"
                            f"7. Call optimizer__generate_pr_review_body with all reports.\n"
                            f"8. Call github__post_pr_review to post the review.\n"
                            f"9. For verified fixes, create branch, push fix, open fix PR.\n"
                            f"10. Call optimizer__summarize_audit_findings and return the result."
                        )
                    }
                ],
            }
        ]

        session_start = time.time()
        call_number = 0
        last_summary: AuditSummary | None = None

        for iteration in range(self.MAX_ITERATIONS):
            self._rate_limiter.acquire()
            response = self._generate(
                messages, tool_config, ctx.build_system_prompt()
            )

            if not response.candidates:
                continue

            has_tool_call = False
            for part in response.candidates[0].content.parts:
                if part.function_call:
                    has_tool_call = True
                    call_number += 1
                    call = part.function_call
                    t0 = time.time()
                    self._log.info(
                        "agent_tool_call",
                        call_n=call_number,
                        tool=call.name,
                        iteration=iteration,
                    )
                    try:
                        result = registry.dispatch(call.name, dict(call.args))
                        success = True
                    except Exception as e:
                        self._log.error("tool_call_failed", tool=call.name, error=str(e))
                        result = {"error": str(e)}
                        success = False

                    duration_ms = (time.time() - t0) * 1000
                    result_str = (
                        result.model_dump_json()
                        if hasattr(result, "model_dump_json")
                        else json.dumps(result, default=str)
                    )

                    if call.name == "optimizer__summarize_audit_findings" and success:
                        if hasattr(result, "model_dump"):
                            last_summary = result
                        else:
                            last_summary = AuditSummary.model_validate(result)

                    ctx.record_tool_call(
                        ToolCallRecord(
                            call_number=call_number,
                            namespace=call.name.split("__")[0]
                            if "__" in call.name
                            else "unknown",
                            tool_name=call.name,
                            input_summary=str(dict(call.args))[:100],
                            result_summary=result_str[:150],
                            duration_ms=duration_ms,
                            success=success,
                        )
                    )

                    messages.append(
                        {
                            "role": "model",
                            "parts": [
                                {
                                    "function_call": {
                                        "name": call.name,
                                        "args": dict(call.args),
                                    }
                                }
                            ],
                        }
                    )
                    messages.append(
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "function_response": {
                                        "name": call.name,
                                        "response": {"result": result_str},
                                    }
                                }
                            ],
                        }
                    )

            if not has_tool_call:
                self._log.info(
                    "agent_complete",
                    total_calls=call_number,
                    duration_s=round(time.time() - session_start, 2),
                )
                if last_summary:
                    last_summary.total_tool_calls = call_number
                    last_summary.session_duration_seconds = round(
                        time.time() - session_start, 2
                    )
                    return last_summary
                return AuditSummary(
                    repo=repo,
                    prs_audited=len(pr_numbers),
                    functions_analyzed=0,
                    regressions_found=0,
                    regressions_critical=0,
                    regressions_moderate=0,
                    fixes_generated=0,
                    fixes_verified=0,
                    fix_prs_opened=[],
                    total_tool_calls=call_number,
                    session_duration_seconds=round(time.time() - session_start, 2),
                    reports=[],
                )

        raise FatalError(
            f"AgentLoop exceeded MAX_ITERATIONS={self.MAX_ITERATIONS} without finishing."
        )
