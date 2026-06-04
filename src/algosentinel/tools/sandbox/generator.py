import ast
import random
from typing import Any

from pydantic import BaseModel, Field

from algosentinel.models.sandbox import FunctionCode
from algosentinel.tools.registry import tool


class GenerateInputsInput(BaseModel):
    input_type: str
    sizes: list[int]
    seed: int = 42


class ExtractFunctionInput(BaseModel):
    code: str
    function_name: str


def _generate_input_value(input_type: str, n: int, seed: int) -> Any:
    rng = random.Random(seed)
    if input_type == "list_int":
        return [rng.randint(0, n * 10) for _ in range(n)]
    if input_type == "list_str":
        return ["".join(rng.choices("abcdefghij", k=5)) for _ in range(n)]
    if input_type == "dict":
        return {str(i): rng.randint(0, 100) for i in range(n)}
    if input_type == "graph_edges":
        return [(rng.randint(0, n), rng.randint(0, n)) for _ in range(n)]
    return [rng.randint(0, n * 10) for _ in range(n)]


@tool(
    namespace="sandbox",
    description="Generate test inputs for each requested size.",
    input_model=GenerateInputsInput,
    output_model=dict,
)
def generate_inputs(inp: GenerateInputsInput) -> dict[str, list]:
    return {
        str(size): _generate_input_value(inp.input_type, size, inp.seed)
        for size in inp.sizes
    }


@tool(
    namespace="sandbox",
    description="Extract a named function from Python source using AST.",
    input_model=ExtractFunctionInput,
    output_model=FunctionCode,
)
def extract_function(inp: ExtractFunctionInput) -> FunctionCode:
    tree = ast.parse(inp.code)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == inp.function_name:
            lines = inp.code.splitlines()
            start = node.lineno - 1
            end = node.end_lineno or node.lineno
            source = "\n".join(lines[start:end])
            deps: list[str] = []
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id not in deps:
                    if child.id != inp.function_name:
                        deps.append(child.id)
            return FunctionCode(
                function_name=inp.function_name,
                source_code=source,
                file_path="",
                line_start=node.lineno,
                line_end=end,
                dependencies=deps[:20],
            )
    return FunctionCode(
        function_name=inp.function_name,
        source_code=inp.code,
        file_path="",
        line_start=1,
        line_end=len(inp.code.splitlines()),
    )
