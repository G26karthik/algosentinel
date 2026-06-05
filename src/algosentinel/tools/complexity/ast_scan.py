import ast

from pydantic import BaseModel

from algosentinel.models.complexity import ASTComplexityHints, TheoreticalEstimate
from algosentinel.tools.registry import tool


class ScanASTInput(BaseModel):
    code: str
    function_name: str


class DetectLoopNestingDepthInput(BaseModel):
    code: str


class IdentifyHotPathInput(BaseModel):
    code: str


class EstimateTheoreticalComplexityInput(BaseModel):
    code: str


def _max_loop_depth(node: ast.AST, depth: int = 0) -> int:
    max_d = depth
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.For, ast.While)):
            max_d = max(max_d, _max_loop_depth(child, depth + 1))
        else:
            max_d = max(max_d, _max_loop_depth(child, depth))
    return max_d


def _has_recursion(tree: ast.AST, func_name: str) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == func_name:
                return True
    return False


@tool(
    namespace="complexity",
    description="Static AST scan for loop nesting, recursion, and suspicious patterns.",
    input_model=ScanASTInput,
    output_model=ASTComplexityHints,
)
def scan_ast_for_hints(inp: ScanASTInput) -> ASTComplexityHints:
    tree = ast.parse(inp.code)
    depth = 0
    suspicious: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.For, ast.While)):
            depth = max(depth, _max_loop_depth(node))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in ("sort", "sorted"):
                suspicious.append("sort call may add O(n log n)")
    recursive = _has_recursion(tree, inp.function_name)
    estimated = None
    if depth >= 2:
        estimated = "O(n^2)"
    elif depth == 1:
        estimated = "O(n)"
    return ASTComplexityHints(
        max_loop_nesting_depth=depth,
        has_recursive_calls=recursive,
        estimated_class=estimated,
        hot_paths=[],
        suspicious_patterns=suspicious,
    )


@tool(
    namespace="complexity",
    description="Return maximum loop nesting depth.",
    input_model=DetectLoopNestingDepthInput,
    output_model=int,
)
def detect_loop_nesting_depth(inp: DetectLoopNestingDepthInput) -> int:
    tree = ast.parse(inp.code)
    return _max_loop_depth(tree)


@tool(
    namespace="complexity",
    description="Identify lines inside the deepest loop nest.",
    input_model=IdentifyHotPathInput,
    output_model=list,
)
def identify_hot_path(inp: IdentifyHotPathInput) -> list[str]:
    lines = inp.code.splitlines()
    tree = ast.parse(inp.code)
    hot: list[str] = []
    best_depth = 0

    def visit(node, depth):
        nonlocal best_depth
        if isinstance(node, (ast.For, ast.While)):
            depth += 1
            if depth >= best_depth and hasattr(node, "lineno"):
                best_depth = depth
                if node.lineno - 1 < len(lines):
                    hot.append(lines[node.lineno - 1].strip())
        for child in ast.iter_child_nodes(node):
            visit(child, depth)

    visit(tree, 0)
    return hot[:5]


@tool(
    namespace="complexity",
    description="Static AST-based complexity estimate.",
    input_model=EstimateTheoreticalComplexityInput,
    output_model=TheoreticalEstimate,
)
def estimate_theoretical_complexity(inp: EstimateTheoreticalComplexityInput) -> TheoreticalEstimate:
    depth = detect_loop_nesting_depth(DetectLoopNestingDepthInput(code=inp.code))
    if depth >= 2:
        return TheoreticalEstimate(
            estimated_class="O(n^2)",
            reasoning=f"Detected {depth} levels of nested loops",
            confidence=0.7,
        )
    if depth == 1:
        return TheoreticalEstimate(
            estimated_class="O(n)",
            reasoning="Single loop over input",
            confidence=0.75,
        )
    return TheoreticalEstimate(
        estimated_class="O(1)",
        reasoning="No loops detected",
        confidence=0.6,
    )
