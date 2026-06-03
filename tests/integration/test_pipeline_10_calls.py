from unittest.mock import MagicMock, patch

import pytest

from algosentinel.agent.core import AgentLoop
from algosentinel.models.reports import AuditSummary


def _mock_gemini_tool_loop(mock_generate, tool_names: list[str]):
    """Simulate Gemini returning tool calls then finishing."""
    call_idx = {"n": 0}

    def side_effect(*args, **kwargs):
        n = call_idx["n"]
        call_idx["n"] += 1
        response = MagicMock()
        part = MagicMock()
        if n < len(tool_names):
            fc = MagicMock()
            fc.name = tool_names[n]
            fc.args = {"repo": "test/test-repo", "pr_number": 1}
            part.function_call = fc
            part.text = None
        else:
            part.function_call = None
            part.text = None
        response.candidates = [MagicMock()]
        response.candidates[0].content.parts = [part]
        return response

    mock_generate.side_effect = side_effect


@pytest.mark.integration
def test_pipeline_makes_at_least_10_calls():
    tool_sequence = [
        "github__get_pr_details",
        "github__get_pr_diff",
        "github__list_pr_files",
        "sandbox__extract_function",
        "github__spawn_function_analysis_subagent",
        "optimizer__generate_pr_review_body",
        "github__post_pr_review",
        "optimizer__summarize_audit_findings",
        "github__get_repo_info",
        "github__list_recent_prs",
        "github__get_file_content",
    ]

    with patch("algosentinel.agent.core.genai.Client"), patch.object(
        AgentLoop, "_generate"
    ) as mock_gen, patch("algosentinel.tools.github.pr._get_repo") as mock_repo_fn:
        mock_pr = MagicMock()
        mock_pr.number = 1
        mock_pr.title = "Test"
        mock_pr.body = ""
        mock_pr.head.sha = "abc"
        mock_pr.base.sha = "def"
        mock_pr.head.ref = "feature"
        mock_pr.base.ref = "main"
        mock_pr.user.login = "tester"
        mock_pr.created_at = None
        mock_pr.get_files.return_value = []
        mock_repo = MagicMock()
        mock_repo.get_pull.return_value = mock_pr
        mock_repo_fn.return_value = mock_repo

        from algosentinel.models.reports import ComplexityReport
        from algosentinel.models.complexity import (
            ASTComplexityHints,
            ComplexityClass,
            ComplexityOrder,
            RegressionResult,
        )

        mock_report = ComplexityReport(
            function_name="fn",
            file_path="f.py",
            pre_class=ComplexityClass(
                notation="O(n)",
                order=ComplexityOrder.LINEAR,
                confidence=0.9,
                supporting_r_squared=0.95,
                all_fits=[],
            ),
            post_class=ComplexityClass(
                notation="O(n)",
                order=ComplexityOrder.LINEAR,
                confidence=0.9,
                supporting_r_squared=0.95,
                all_fits=[],
            ),
            regression=RegressionResult(
                is_regression=False,
                severity="none",
                pre_class=ComplexityClass(
                    notation="O(n)",
                    order=ComplexityOrder.LINEAR,
                    confidence=0.9,
                    supporting_r_squared=0.95,
                    all_fits=[],
                ),
                post_class=ComplexityClass(
                    notation="O(n)",
                    order=ComplexityOrder.LINEAR,
                    confidence=0.9,
                    supporting_r_squared=0.95,
                    all_fits=[],
                ),
                orders_worse=0,
                confidence=0.9,
            ),
            ast_hints=ASTComplexityHints(
                max_loop_nesting_depth=1,
                has_recursive_calls=False,
            ),
            explanation="ok",
        )

        call_idx = {"n": 0}

        def dispatch_side_effect(tool_name, raw_args):
            if tool_name == "github__spawn_function_analysis_subagent":
                return mock_report
            if tool_name == "optimizer__summarize_audit_findings":
                from algosentinel.tools.optimizer.reporter import summarize_audit_findings
                from algosentinel.tools.optimizer.reporter import SummarizeAuditFindingsInput

                return summarize_audit_findings(
                    SummarizeAuditFindingsInput(reports=[mock_report], repo="test/test-repo")
                )
            return {"ok": True}

        def gen_side_effect(*args, **kwargs):
            n = call_idx["n"]
            call_idx["n"] += 1
            response = MagicMock()
            part = MagicMock()
            if n < len(tool_sequence):
                fc = MagicMock()
                fc.name = tool_sequence[n]
                fc.args = {
                    "repo": "test/test-repo",
                    "pr_number": 1,
                    "regression_reports": [],
                    "body": "review",
                    "reports": [],
                }
                part.function_call = fc
                part.text = None
            else:
                part.function_call = None
                part.text = None
            response.candidates = [MagicMock()]
            response.candidates[0].content.parts = [part]
            return response

        mock_gen.side_effect = gen_side_effect

        with patch(
            "algosentinel.tools.registry.ToolRegistry.dispatch",
            side_effect=dispatch_side_effect,
        ), patch(
            "algosentinel.tools.registry.ToolRegistry.get_function_declarations",
            return_value=[],
        ):
            import algosentinel.tools.github  # noqa: F401
            import algosentinel.tools.sandbox  # noqa: F401
            import algosentinel.tools.complexity  # noqa: F401
            import algosentinel.tools.optimizer  # noqa: F401

            agent = AgentLoop()
            summary = agent.run(repo="test/test-repo", pr_numbers=[1])

    assert isinstance(summary, AuditSummary)
    assert summary.total_tool_calls >= 10


def test_context_compression_fires():
    with patch("algosentinel.agent.core.genai.Client"), patch(
        "algosentinel.agent.context.ContextManager._compress"
    ) as mock_compress, patch.object(AgentLoop, "_generate") as mock_gen:
        call_idx = {"n": 0}

        def gen(*a, **k):
            n = call_idx["n"]
            call_idx["n"] += 1
            response = MagicMock()
            part = MagicMock()
            if n < 12:
                fc = MagicMock()
                fc.name = "github__get_pr_details"
                fc.args = {"repo": "test/test-repo", "pr_number": 1}
                part.function_call = fc
            else:
                part.function_call = None
            response.candidates = [MagicMock()]
            response.candidates[0].content.parts = [part]
            return response

        mock_gen.side_effect = gen

        with patch(
            "algosentinel.tools.registry.ToolRegistry.dispatch",
            return_value={"ok": True},
        ), patch(
            "algosentinel.tools.registry.ToolRegistry.get_function_declarations",
            return_value=[],
        ):
            import algosentinel.tools.github  # noqa: F401
            import algosentinel.tools.sandbox  # noqa: F401
            import algosentinel.tools.complexity  # noqa: F401
            import algosentinel.tools.optimizer  # noqa: F401
            agent = AgentLoop()
            try:
                agent.run(repo="test/test-repo", pr_numbers=[1])
            except Exception:
                pass
        assert mock_compress.call_count >= 1
