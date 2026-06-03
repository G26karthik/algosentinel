#!/usr/bin/env python3
"""Audit the last N closed PRs in a repository."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

import algosentinel.tools.complexity  # noqa: F401
import algosentinel.tools.github  # noqa: F401
import algosentinel.tools.optimizer  # noqa: F401
import algosentinel.tools.sandbox  # noqa: F401

import click

from algosentinel.agent.core import AgentLoop
from algosentinel.observability.logger import configure_logging
from algosentinel.tools.github.pr import ListRecentPRsInput, list_recent_prs


@click.command()
@click.option("--repo", required=True, help="GitHub repository in owner/repo format")
@click.option("--last-n", default=10, show_default=True, help="Number of recent PRs to audit")
def main(repo: str, last_n: int):
    configure_logging()
    prs = list_recent_prs(ListRecentPRsInput(repo=repo, limit=last_n, state="closed"))
    pr_numbers = [pr["number"] for pr in prs]
    click.echo(f"Auditing PRs: {pr_numbers}")
    agent = AgentLoop()
    summary = agent.run(repo=repo, pr_numbers=pr_numbers)
    click.echo(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
