import pytest

from algosentinel.tools.sandbox.executor import (
    CreateSandboxInput,
    DestroySandboxInput,
    ExecuteRawInput,
    create_sandbox,
    destroy_sandbox,
    execute_raw,
)
from algosentinel.tools.sandbox.profiler import ProfileRuntimeInput, profile_runtime


@pytest.fixture
def sandbox_id():
    sid = create_sandbox(CreateSandboxInput())
    yield sid
    destroy_sandbox(DestroySandboxInput(sandbox_id=sid))


def test_create_and_destroy_sandbox():
    sid = create_sandbox(CreateSandboxInput())
    assert isinstance(sid, str)
    assert len(sid) > 0
    result = destroy_sandbox(DestroySandboxInput(sandbox_id=sid))
    assert result is True


@pytest.mark.integration
def test_execute_raw_returns_output(sandbox_id):
    result = execute_raw(ExecuteRawInput(sandbox_id=sandbox_id, code="print('hello')"))
    assert "hello" in result["stdout"]


@pytest.mark.integration
def test_profile_runtime_returns_timing_points(sandbox_id):
    code = "def linear(lst):\n    return [x*2 for x in lst]"
    points = profile_runtime(
        ProfileRuntimeInput(
            sandbox_id=sandbox_id,
            code=code,
            function_name="linear",
            input_sizes=[10, 100, 1000],
        )
    )
    assert len(points) == 3
    assert all(p.elapsed_ms >= 0 for p in points)
    assert all(p.input_size in [10, 100, 1000] for p in points)
