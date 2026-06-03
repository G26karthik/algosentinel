from typing import Any, Optional

from pydantic import BaseModel, Field


class TimingPoint(BaseModel):
    """Output of sandbox.profile_runtime; input to complexity.fit_complexity_curves."""

    input_size: int
    elapsed_ms: float
    std_dev_ms: float = 0.0
    runs: int = 5


class MemoryPoint(BaseModel):
    input_size: int
    peak_bytes: int


class ExecutionResult(BaseModel):
    stdout: str
    stderr: str
    exit_code: int
    elapsed_ms: float


class BenchmarkPoint(BaseModel):
    input_size: int
    pre_elapsed_ms: float
    post_elapsed_ms: float
    ratio: float


class BenchmarkPairResult(BaseModel):
    function_name: str
    points: list[BenchmarkPoint]


class CorrectnessResult(BaseModel):
    is_correct: bool
    failed_inputs: list[Any]
    error_message: Optional[str] = None


class SandboxStatus(BaseModel):
    sandbox_id: str
    is_healthy: bool
    container_id: Optional[str] = None


class InstallResult(BaseModel):
    success: bool
    packages_installed: list[str]
    error: Optional[str] = None


class FunctionCode(BaseModel):
    function_name: str
    source_code: str
    file_path: str
    line_start: int
    line_end: int
    dependencies: list[str] = Field(default_factory=list)
