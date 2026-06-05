import ast

from pydantic import BaseModel

from algosentinel.tools.registry import tool


class AnnotateFunctionInput(BaseModel):
    code: str
    function_name: str
    complexity_class: str


class GetComplexityExplanationInput(BaseModel):
    class_name: str
    context: str


@tool(
    namespace="complexity",
    description="Add a complexity annotation comment to a function.",
    input_model=AnnotateFunctionInput,
    output_model=str,
)
def annotate_function(inp: AnnotateFunctionInput) -> str:
    lines = inp.code.splitlines()
    tree = ast.parse(inp.code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == inp.function_name:
            idx = node.lineno - 1
            indent = len(lines[idx]) - len(lines[idx].lstrip()) if idx < len(lines) else 0
            annotation = " " * indent + f"# Complexity: {inp.complexity_class}"
            if idx > 0 and "Complexity:" in lines[idx - 1]:
                lines[idx - 1] = annotation
            else:
                lines.insert(idx, annotation)
            return "\n".join(lines)
    return f"# Complexity: {inp.complexity_class}\n{inp.code}"


@tool(
    namespace="complexity",
    description="Plain-English explanation of a complexity class in context.",
    input_model=GetComplexityExplanationInput,
    output_model=str,
)
def get_complexity_explanation(inp: GetComplexityExplanationInput) -> str:
    explanations = {
        "O(1)": "constant time regardless of input size",
        "O(log n)": "time grows logarithmically with input size",
        "O(n)": "time grows linearly with input size",
        "O(n log n)": "time grows as n log n (typical for efficient sorts)",
        "O(n^2)": "time grows quadratically — often from nested loops",
        "O(n^3)": "time grows cubically — triple nested loops",
        "O(2^n)": "exponential time — often from brute-force recursion",
    }
    base = explanations.get(inp.class_name, f"complexity class {inp.class_name}")
    return (
        f"For `{inp.context}`, the measured complexity is **{inp.class_name}** ({base}). "
        f"At large n this dominates runtime and memory pressure."
    )
