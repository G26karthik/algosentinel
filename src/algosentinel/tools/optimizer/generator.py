from google import genai
from pydantic import BaseModel

from algosentinel.config import settings
from algosentinel.models.complexity import ASTComplexityHints
from algosentinel.resilience.retry import with_retry
from algosentinel.tools.registry import tool

_optimizer_client: genai.Client | None = None


def _get_optimizer_client() -> genai.Client:
    global _optimizer_client
    if _optimizer_client is None:
        _optimizer_client = genai.Client(api_key=settings.gemini_api_key)
    return _optimizer_client


class GenerateOptimizedAlternativeInput(BaseModel):
    original_code: str
    function_name: str
    current_class: str
    target_class: str
    ast_hints: ASTComplexityHints


class SuggestDataStructuresInput(BaseModel):
    code: str
    function_name: str
    current_class: str


class CheckCacheOpportunityInput(BaseModel):
    code: str
    function_name: str


class GenerateComplexityTestInput(BaseModel):
    function_name: str
    expected_class: str


@with_retry()
def _gemini_generate(prompt: str) -> str:
    client = _get_optimizer_client()
    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
    )
    return response.text or ""


@tool(
    namespace="optimizer",
    description="Use Gemini to rewrite a function toward a target complexity class.",
    input_model=GenerateOptimizedAlternativeInput,
    output_model=str,
)
def generate_optimized_alternative(inp: GenerateOptimizedAlternativeInput) -> str:
    prompt = (
        f"Rewrite this Python function `{inp.function_name}` from {inp.current_class} "
        f"to approximately {inp.target_class}. Return only the function code.\n\n"
        f"AST hints: nesting={inp.ast_hints.max_loop_nesting_depth}, "
        f"patterns={inp.ast_hints.suspicious_patterns}\n\n"
        f"```python\n{inp.original_code}\n```"
    )
    return _gemini_generate(prompt).strip()


@tool(
    namespace="optimizer",
    description="Suggest better data structures for the function.",
    input_model=SuggestDataStructuresInput,
    output_model=list,
)
def suggest_data_structures(inp: SuggestDataStructuresInput) -> list[str]:
    suggestions = []
    if "in lst" in inp.code or " in list" in inp.code.lower():
        suggestions.append("Use a set for O(1) membership checks instead of scanning a list")
    if "append" in inp.code and "for" in inp.code:
        suggestions.append("Consider list comprehension or deque for batch appends")
    if not suggestions:
        suggestions.append("Profile access patterns; consider dict/set for lookups")
    return suggestions


@tool(
    namespace="optimizer",
    description="Detect whether memoization could help.",
    input_model=CheckCacheOpportunityInput,
    output_model=dict,
)
def check_cache_opportunity(inp: CheckCacheOpportunityInput) -> dict:
    has_recursion = "return " in inp.code and inp.function_name in inp.code
    repeated_calls = inp.code.count(f"{inp.function_name}(") > 1
    return {
        "memoization_recommended": has_recursion or repeated_calls,
        "reason": "Recursive or repeated subcalls detected" if repeated_calls else "Low overlap",
    }


@tool(
    namespace="optimizer",
    description="Generate a pytest asserting expected complexity behavior.",
    input_model=GenerateComplexityTestInput,
    output_model=str,
)
def generate_complexity_test(inp: GenerateComplexityTestInput) -> str:
    return f'''
import time
import pytest

def test_{inp.function_name}_complexity_scaling():
    """Expect {inp.expected_class} scaling for {inp.function_name}."""
    sizes = [100, 500, 1000]
    times = []
    for n in sizes:
        data = list(range(n))
        start = time.perf_counter()
        {inp.function_name}(data)
        times.append(time.perf_counter() - start)
    ratio = times[-1] / max(times[0], 1e-9)
    assert ratio < 500, f"Scaling worse than expected for {inp.expected_class}"
'''
