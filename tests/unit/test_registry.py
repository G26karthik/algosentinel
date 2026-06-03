import pytest

import algosentinel.tools.complexity  # noqa: F401
import algosentinel.tools.github  # noqa: F401
import algosentinel.tools.optimizer  # noqa: F401
import algosentinel.tools.sandbox  # noqa: F401
from algosentinel.resilience.errors import ToolError
from algosentinel.tools.registry import ToolRegistry


def test_tool_count():
    assert ToolRegistry.get().tool_count() >= 55


def test_namespaces():
    ns = set(ToolRegistry.get().namespaces())
    assert {"github", "sandbox", "complexity", "optimizer"}.issubset(ns)


def test_all_tools_have_descriptions():
    registry = ToolRegistry.get()
    for name, tool_def in registry._tools.items():
        assert tool_def.description, f"Tool {name} has an empty description"


def test_all_tools_have_valid_schemas():
    registry = ToolRegistry.get()
    for name, tool_def in registry._tools.items():
        schema = tool_def.input_model.model_json_schema()
        assert "properties" in schema or "type" in schema, f"Invalid schema for {name}"


def test_dispatch_unknown_raises_tool_error():
    with pytest.raises(ToolError):
        ToolRegistry.get().dispatch("nonexistent__tool", {})
