from typing import Optional

from pydantic import BaseModel, Field

from algosentinel.models.complexity import (
    ASTComplexityHints,
    ComplexityClass,
    RegressionResult,
)
from algosentinel.models.sandbox import CorrectnessResult, TimingPoint


class ComplexityReport(BaseModel):
    function_name: str
    file_path: str
    pre_class: ComplexityClass
    post_class: ComplexityClass
    regression: RegressionResult
    evidence: list[TimingPoint] = Field(default_factory=list)
    ast_hints: ASTComplexityHints
    explanation: str
    fix_generated: bool = False
    fix_code: Optional[str] = None
    fix_verified: bool = False
    fix_correctness: Optional[CorrectnessResult] = None
    subagent_tool_calls_used: int = 0


class AuditSummary(BaseModel):
    repo: str
    prs_audited: int
    functions_analyzed: int
    regressions_found: int
    regressions_critical: int
    regressions_moderate: int
    fixes_generated: int
    fixes_verified: int
    fix_prs_opened: list[str]
    total_tool_calls: int
    session_duration_seconds: float
    reports: list[ComplexityReport]
