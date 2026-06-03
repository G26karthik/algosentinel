from algosentinel.models.tools import Plan, Step


def build_plan(repo: str, pr_numbers: list[int]) -> Plan:
    steps = [
        Step(id="s1", description=f"Fetch PR details and diffs for PRs {pr_numbers}"),
        Step(id="s2", description="Identify changed Python files and extract changed functions"),
        Step(id="s3", description="Spawn subagents to analyze each changed function pair"),
        Step(id="s4", description="Collect ComplexityReports from all subagents"),
        Step(id="s5", description="Generate optimized fixes for any regressions found"),
        Step(id="s6", description="Verify each fix restores the original complexity class"),
        Step(id="s7", description="Post PR review comments with findings"),
        Step(id="s8", description="Open fix PRs for verified fixes"),
        Step(id="s9", description="Summarize audit findings and return AuditSummary"),
    ]
    return Plan(
        goal=f"Detect algorithmic complexity regressions in {repo} PRs {pr_numbers}",
        repo=repo,
        pr_numbers=pr_numbers,
        steps=steps,
    )
