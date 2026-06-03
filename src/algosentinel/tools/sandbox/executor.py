import uuid
from typing import Any

import docker
import structlog
from pydantic import BaseModel, Field

from algosentinel.config import settings
from algosentinel.models.sandbox import (
    ExecutionResult,
    InstallResult,
    SandboxStatus,
)
from algosentinel.resilience.errors import SandboxStartError, SandboxTimeoutError
from algosentinel.tools.registry import tool

logger = structlog.get_logger()

_sandboxes: dict[str, docker.models.containers.Container] = {}


def _docker_client() -> docker.DockerClient:
    return docker.from_env()


def _exec_in_container(container, code: str, timeout: int | None = None) -> tuple[str, str, int]:
    timeout = timeout or settings.sandbox_timeout_seconds
    result = container.exec_run(
        ["python", "-c", code],
        demux=True,
        workdir="/tmp",
    )
    stdout = (result.output[0] or b"").decode() if result.output else ""
    stderr = (result.output[1] or b"").decode() if result.output and len(result.output) > 1 else ""
    if result.exit_code != 0 and "timeout" in stderr.lower():
        raise SandboxTimeoutError(f"Sandbox exec timed out after {timeout}s")
    return stdout, stderr, result.exit_code


class CreateSandboxInput(BaseModel):
    language: str = "python"
    dependencies: list[str] = Field(default_factory=list)


class DestroySandboxInput(BaseModel):
    sandbox_id: str


class ExecuteFunctionInput(BaseModel):
    sandbox_id: str
    code: str
    function_name: str
    input_args: list[Any]


class ExecuteRawInput(BaseModel):
    sandbox_id: str
    code: str


class InstallDependenciesInput(BaseModel):
    sandbox_id: str
    packages: list[str]


class RunTestSuiteInput(BaseModel):
    sandbox_id: str
    test_code: str


class GetSandboxLogsInput(BaseModel):
    sandbox_id: str


class CheckSandboxHealthInput(BaseModel):
    sandbox_id: str


def _get_container(sandbox_id: str):
    if sandbox_id not in _sandboxes:
        raise SandboxStartError(f"Unknown sandbox: {sandbox_id}")
    return _sandboxes[sandbox_id]


@tool(
    namespace="sandbox",
    description="Create a Docker sandbox container for Python execution.",
    input_model=CreateSandboxInput,
    output_model=str,
)
def create_sandbox(inp: CreateSandboxInput) -> str:
    try:
        client = _docker_client()
        container = client.containers.run(
            settings.sandbox_docker_image,
            command="sleep infinity",
            detach=True,
            working_dir="/tmp",
            remove=False,
        )
        sandbox_id = str(uuid.uuid4())
        _sandboxes[sandbox_id] = container
        if inp.dependencies:
            install_dependencies(
                InstallDependenciesInput(sandbox_id=sandbox_id, packages=inp.dependencies)
            )
        return sandbox_id
    except docker.errors.DockerException as e:
        raise SandboxStartError(str(e)) from e


@tool(
    namespace="sandbox",
    description="Stop and remove a sandbox container.",
    input_model=DestroySandboxInput,
    output_model=bool,
)
def destroy_sandbox(inp: DestroySandboxInput) -> bool:
    container = _sandboxes.pop(inp.sandbox_id, None)
    if container is None:
        return False
    try:
        container.stop(timeout=5)
        container.remove()
    except docker.errors.DockerException:
        pass
    return True


@tool(
    namespace="sandbox",
    description="Execute a Python function with specific arguments in the sandbox.",
    input_model=ExecuteFunctionInput,
    output_model=ExecutionResult,
)
def execute_function(inp: ExecuteFunctionInput) -> ExecutionResult:
    import json
    import time

    container = _get_container(inp.sandbox_id)
    args_json = json.dumps(inp.input_args)
    code = f"""
import json, time
{inp.code}
args = json.loads({args_json!r})
start = time.perf_counter()
result = {inp.function_name}(*args) if isinstance(args, list) else {inp.function_name}(args)
elapsed = (time.perf_counter() - start) * 1000
print(json.dumps({{"result": result, "elapsed_ms": elapsed}}))
"""
    stdout, stderr, exit_code = _exec_in_container(container, code)
    return ExecutionResult(
        stdout=stdout,
        stderr=stderr,
        exit_code=exit_code,
        elapsed_ms=0.0,
    )


@tool(
    namespace="sandbox",
    description="Run arbitrary Python code in the sandbox.",
    input_model=ExecuteRawInput,
    output_model=dict,
)
def execute_raw(inp: ExecuteRawInput) -> dict:
    container = _get_container(inp.sandbox_id)
    stdout, stderr, exit_code = _exec_in_container(container, inp.code)
    return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code}


@tool(
    namespace="sandbox",
    description="Install pip packages inside the sandbox.",
    input_model=InstallDependenciesInput,
    output_model=InstallResult,
)
def install_dependencies(inp: InstallDependenciesInput) -> InstallResult:
    container = _get_container(inp.sandbox_id)
    if not inp.packages:
        return InstallResult(success=True, packages_installed=[])
    pkg_str = " ".join(inp.packages)
    stdout, stderr, exit_code = _exec_in_container(
        container,
        f"import subprocess; subprocess.run(['pip','install',{pkg_str!r}], check=True)",
    )
    if exit_code != 0:
        return InstallResult(
            success=False,
            packages_installed=[],
            error=stderr or stdout,
        )
    return InstallResult(success=True, packages_installed=inp.packages)


@tool(
    namespace="sandbox",
    description="Run pytest test code inside the sandbox.",
    input_model=RunTestSuiteInput,
    output_model=dict,
)
def run_test_suite(inp: RunTestSuiteInput) -> dict:
    container = _get_container(inp.sandbox_id)
    code = f"""
import subprocess, sys, tempfile, os
with tempfile.NamedTemporaryFile(mode='w', suffix='_test.py', delete=False) as f:
    f.write({inp.test_code!r})
    path = f.name
result = subprocess.run([sys.executable, '-m', 'pytest', path, '-q'], capture_output=True, text=True)
print(result.stdout)
print(result.stderr, file=sys.stderr)
sys.exit(result.returncode)
"""
    stdout, stderr, exit_code = _exec_in_container(container, code)
    return {"stdout": stdout, "stderr": stderr, "exit_code": exit_code, "passed": exit_code == 0}


@tool(
    namespace="sandbox",
    description="Return container stdout/stderr logs.",
    input_model=GetSandboxLogsInput,
    output_model=list,
)
def get_sandbox_logs(inp: GetSandboxLogsInput) -> list[str]:
    container = _get_container(inp.sandbox_id)
    logs = container.logs().decode()
    return logs.splitlines() if logs else []


@tool(
    namespace="sandbox",
    description="Check whether the sandbox container is running.",
    input_model=CheckSandboxHealthInput,
    output_model=SandboxStatus,
)
def check_sandbox_health(inp: CheckSandboxHealthInput) -> SandboxStatus:
    container = _sandboxes.get(inp.sandbox_id)
    if container is None:
        return SandboxStatus(sandbox_id=inp.sandbox_id, is_healthy=False)
    container.reload()
    healthy = container.status == "running"
    return SandboxStatus(
        sandbox_id=inp.sandbox_id,
        is_healthy=healthy,
        container_id=container.id,
    )
