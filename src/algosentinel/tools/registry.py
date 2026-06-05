import copy
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import structlog
from google.genai import types as genai_types

from algosentinel.resilience.errors import ToolError

logger = structlog.get_logger()


def _inline_json_schema(schema: dict) -> dict:
    """Resolve $ref / $defs for Gemini FunctionDeclaration compatibility."""
    defs = schema.get("$defs", {})

    def resolve(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                ref_name = node["$ref"].split("/")[-1]
                return resolve(copy.deepcopy(defs[ref_name]))
            return {k: resolve(v) for k, v in node.items() if k != "$defs"}
        if isinstance(node, list):
            return [resolve(item) for item in node]
        return node

    result = resolve(copy.deepcopy(schema))
    if isinstance(result, dict):
        result.pop("$defs", None)
    return _sanitize_schema_for_gemini(result)


def _sanitize_schema_for_gemini(node: Any) -> Any:
    """Gemini FunctionDeclaration requires string enum values, not integers."""
    if isinstance(node, dict):
        out = {}
        for key, value in node.items():
            out[key] = _sanitize_schema_for_gemini(value)
        if "enum" in out and out["enum"] and all(isinstance(x, int) for x in out["enum"]):
            out["enum"] = [str(x) for x in out["enum"]]
            out["type"] = "string"
        return out
    if isinstance(node, list):
        return [_sanitize_schema_for_gemini(item) for item in node]
    return node


@dataclass
class ToolDefinition:
    namespace: str
    name: str
    func: Callable
    description: str
    input_model: type
    output_model: type


class ToolRegistry:
    _instance: Optional["ToolRegistry"] = None
    _tools: dict[str, ToolDefinition] = {}

    @classmethod
    def get(cls) -> "ToolRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register(
        self,
        namespace: str,
        func: Callable,
        description: str,
        input_model: type,
        output_model: type,
    ) -> None:
        full_name = f"{namespace}__{func.__name__}"
        self._tools[full_name] = ToolDefinition(
            namespace=namespace,
            name=full_name,
            func=func,
            description=description,
            input_model=input_model,
            output_model=output_model,
        )
        logger.debug("tool_registered", name=full_name)

    def get_function_declarations(
        self,
        namespaces: Optional[list[str]] = None,
    ) -> list[genai_types.FunctionDeclaration]:
        declarations = []
        for tool_def in self._tools.values():
            if namespaces and tool_def.namespace not in namespaces:
                continue
            schema = _inline_json_schema(tool_def.input_model.model_json_schema())
            declarations.append(
                genai_types.FunctionDeclaration(
                    name=tool_def.name,
                    description=tool_def.description,
                    parameters=schema,
                )
            )
        return declarations

    def dispatch(self, tool_name: str, raw_args: dict) -> Any:
        if tool_name not in self._tools:
            raise ToolError(
                f"Unknown tool: {tool_name}. Available: {list(self._tools.keys())}"
            )
        tool_def = self._tools[tool_name]
        validated_input = tool_def.input_model(**raw_args)
        t0 = time.time()
        success = False
        try:
            result = tool_def.func(validated_input)
            success = True
            return result
        except Exception:
            raise
        finally:
            logger.info(
                "tool_call",
                namespace=tool_def.namespace,
                tool_name=tool_name,
                duration_ms=round((time.time() - t0) * 1000, 2),
                success=success,
            )

    def tool_count(self) -> int:
        return len(self._tools)

    def namespaces(self) -> list[str]:
        return list({t.namespace for t in self._tools.values()})


def tool(namespace: str, description: str, input_model: type, output_model: type):
    def decorator(func: Callable) -> Callable:
        ToolRegistry.get().register(namespace, func, description, input_model, output_model)
        return func

    return decorator
