import json

import structlog
from google import genai
from google.genai import types as genai_types

from algosentinel.config import settings
from algosentinel.models.reports import ComplexityReport
from algosentinel.models.sandbox import FunctionCode
from google.genai import errors as genai_errors

from algosentinel.resilience.errors import (
    QuotaExhaustedError,
    RateLimitError,
    SubagentError,
)
from algosentinel.resilience.rate_limiter import TokenBucketRateLimiter
from algosentinel.resilience.retry import with_retry
from algosentinel.tools.registry import ToolRegistry

logger = structlog.get_logger()

SUBAGENT_NAMESPACES = ["sandbox", "complexity"]

SUBAGENT_SYSTEM_PROMPT = """You are a FunctionAnalysisSubagent.
Your only job: empirically measure the complexity of two Python function versions (pre and post a code change), then return a ComplexityReport.

Follow these steps in order:
1. Call sandbox__create_sandbox to get a sandbox_id.
2. Call sandbox__profile_runtime with the PRE-change code. Use input_sizes=[10,50,100,500,1000,5000,10000].
3. Call sandbox__profile_runtime with the POST-change code. Same input_sizes.
4. Call complexity__fit_complexity_curves on the PRE timing points.
5. Call complexity__fit_complexity_curves on the POST timing points.
6. Call complexity__infer_complexity_class on the PRE timing points.
7. Call complexity__infer_complexity_class on the POST timing points.
8. Call complexity__detect_regression with the two ComplexityClass results.
9. If regression detected: call complexity__scan_ast_for_hints on the post code.
10. Call complexity__classify_regression_severity.
11. Call sandbox__destroy_sandbox to clean up.
12. Return your final answer as a raw JSON object that matches the ComplexityReport schema.
    Do NOT add any text before or after the JSON object.
    Do NOT use markdown code fences.
"""


class FunctionAnalysisSubagent:
    """Isolated subagent with own Client and message history (R2)."""

    def __init__(
        self,
        function_code: FunctionCode,
        function_code_after: FunctionCode,
        rate_limiter: TokenBucketRateLimiter,
    ):
        self.function_code = function_code
        self.function_code_after = function_code_after
        self.rate_limiter = rate_limiter
        self._client = genai.Client(api_key=settings.gemini_api_key)
        self._messages: list = []
        self._tool_calls_made: int = 0
        self._log = logger.bind(
            component="FunctionAnalysisSubagent",
            function=function_code.function_name,
        )

    @with_retry()
    def _generate(self, declarations: list, tool_config: genai_types.Tool) -> object:
        try:
            return self._client.models.generate_content(
                model=settings.gemini_model,
                contents=self._messages,
                config=genai_types.GenerateContentConfig(
                    system_instruction=SUBAGENT_SYSTEM_PROMPT,
                    tools=[tool_config],
                    max_output_tokens=settings.gemini_max_tokens,
                    thinking_config=genai_types.ThinkingConfig(
                        thinking_budget=settings.gemini_thinking_budget
                    ),
                ),
            )
        except genai_errors.ClientError as e:
            if e.code == 429:
                if "PerDay" in str(e):
                    raise QuotaExhaustedError(str(e)) from e
                raise RateLimitError(str(e)) from e
            raise

    def run(self) -> ComplexityReport:
        registry = ToolRegistry.get()
        declarations = registry.get_function_declarations(namespaces=SUBAGENT_NAMESPACES)
        tool_config = genai_types.Tool(function_declarations=declarations)

        user_message = (
            f"Analyze this function for complexity regression.\n\n"
            f"FUNCTION NAME: {self.function_code.function_name}\n\n"
            f"PRE-CHANGE CODE ({self.function_code.file_path}, "
            f"lines {self.function_code.line_start}–{self.function_code.line_end}):\n"
            f"```python\n{self.function_code.source_code}\n```\n\n"
            f"POST-CHANGE CODE ({self.function_code_after.file_path}):\n"
            f"```python\n{self.function_code_after.source_code}\n```\n\n"
            f"Run the full empirical analysis and return a ComplexityReport JSON."
        )

        self._messages = [{"role": "user", "parts": [{"text": user_message}]}]

        max_iterations = 20
        for _ in range(max_iterations):
            self.rate_limiter.acquire()
            response = self._generate(declarations, tool_config)

            if not response.candidates:
                continue

            content = response.candidates[0].content
            if content is None or not content.parts:
                self._messages.append(
                    {
                        "role": "user",
                        "parts": [
                            {
                                "text": (
                                    "Continue with the next analysis step, or return "
                                    "the final ComplexityReport JSON if all steps are done."
                                )
                            }
                        ],
                    }
                )
                continue

            has_tool_call = False
            for part in content.parts:
                if part.function_call:
                    has_tool_call = True
                    self._tool_calls_made += 1
                    call = part.function_call
                    self._log.info(
                        "subagent_tool_call",
                        tool=call.name,
                        call_n=self._tool_calls_made,
                    )
                    result = registry.dispatch(call.name, dict(call.args))
                    result_str = (
                        result.model_dump_json()
                        if hasattr(result, "model_dump_json")
                        else json.dumps(result, default=str)
                    )
                    self._messages.append(
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
                    self._messages.append(
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
                for part in content.parts:
                    if part.text:
                        raw = part.text.strip()
                        if raw.startswith("```"):
                            lines = raw.split("\n")
                            raw = "\n".join(lines[1:-1])
                        report = ComplexityReport.model_validate_json(raw)
                        report.subagent_tool_calls_used = self._tool_calls_made
                        self._log.info(
                            "subagent_complete",
                            is_regression=report.regression.is_regression,
                            tool_calls=self._tool_calls_made,
                        )
                        return report

        raise SubagentError(
            f"FunctionAnalysisSubagent for '{self.function_code.function_name}' "
            f"exceeded {max_iterations} iterations without returning a ComplexityReport."
        )
