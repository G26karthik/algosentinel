import structlog
from datetime import UTC, datetime

from algosentinel.config import settings
from algosentinel.models.tools import Checkpoint, Plan, ToolCallRecord

logger = structlog.get_logger()


class ContextManager:
    """
    Maintains agent coherence across long-horizon execution.

    Rules:
    1. The Plan (goal, steps, repo) is NEVER compressed. Always shown in full.
    2. Tool call history IS compressed every COMPRESS_EVERY_N calls.
    3. After compression, raw history records are discarded.
    """

    def __init__(self, plan: Plan):
        self.plan = plan
        self.COMPRESS_EVERY_N = settings.context_compress_every_n_calls
        self.tool_history: list[ToolCallRecord] = []
        self.rolling_summary: str = ""
        self.checkpoints: list[Checkpoint] = []
        self.total_calls: int = 0
        self._log = logger.bind(component="ContextManager")

    def record_tool_call(self, record: ToolCallRecord) -> None:
        self.tool_history.append(record)
        self.total_calls += 1
        self._log.info(
            "tool_call_recorded",
            call_n=self.total_calls,
            tool=record.tool_name,
            duration_ms=record.duration_ms,
        )
        if self.total_calls % self.COMPRESS_EVERY_N == 0:
            self._compress()

    def _compress(self) -> None:
        if not self.tool_history:
            return
        recent = self.tool_history[-self.COMPRESS_EVERY_N :]
        lines = []
        for r in recent:
            status = "OK" if r.success else "FAIL"
            lines.append(
                f"[call {r.call_number}] {r.namespace}.{r.tool_name} → {status}: {r.result_summary}"
            )
        block = "\n".join(lines)
        checkpoint = Checkpoint(
            call_number=self.total_calls,
            summary=block,
            timestamp=datetime.now(UTC),
        )
        self.checkpoints.append(checkpoint)
        self.rolling_summary = (
            f"{self.rolling_summary}\n--- compressed at call {self.total_calls} ---\n{block}"
        ).strip()
        self.tool_history = []
        self._log.info(
            "context_compressed",
            checkpoint_n=len(self.checkpoints),
            total_calls=self.total_calls,
        )

    def update_plan_step(self, step_id: str, status: str) -> None:
        for step in self.plan.steps:
            if step.id == step_id:
                step.status = status
                self.plan.current_step_id = step_id
                break

    def build_system_prompt(self) -> str:
        plan_text = "\n".join(
            f"  [{s.status.upper()}] {s.id}: {s.description}" for s in self.plan.steps
        )
        return f"""You are AlgoSentinel, an autonomous agent that detects algorithmic complexity regressions.

GOAL: {self.plan.goal}
REPO: {self.plan.repo}
TARGET PRs: {self.plan.pr_numbers}

EXECUTION PLAN (always keep this in mind):
{plan_text}

PROGRESS SO FAR (compressed history of tool calls):
{self.rolling_summary or "(no tool calls yet)"}

Instructions:
- Use available tools to advance the plan step by step.
- When analyzing a changed function, call spawn_function_analysis_subagent with both
  the pre-change and post-change versions of the function.
- Always act on what tools return — never assume a result.
- If a tool fails, note the error and try an alternative approach.
- When all functions are analyzed, call generate_pr_review_body and then post_pr_review.
- Finally, call summarize_audit_findings to produce the AuditSummary.
"""

    def get_stats(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "checkpoints_created": len(self.checkpoints),
            "current_step": self.plan.current_step_id,
            "steps_done": sum(1 for s in self.plan.steps if s.status == "done"),
        }
