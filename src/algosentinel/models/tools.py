from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ToolCallRecord(BaseModel):
    call_number: int
    namespace: str
    tool_name: str
    input_summary: str
    result_summary: str
    duration_ms: float
    success: bool
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Step(BaseModel):
    id: str
    description: str
    status: str = "pending"
    tool_calls: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    goal: str
    repo: str
    pr_numbers: list[int]
    steps: list[Step]
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    current_step_id: Optional[str] = None


class Checkpoint(BaseModel):
    call_number: int
    summary: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    findings_so_far: list[str] = Field(default_factory=list)
