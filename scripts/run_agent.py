#!/usr/bin/env python3
"""Analyze one or more specific PRs."""
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


@click.command()
@click.option("--repo", required=True, help="GitHub repository in owner/repo format")
@click.option("--pr", required=True, type=int, multiple=True, help="PR number(s) to analyze")
@click.option("--verbose", is_flag=True, default=False, help="Use console log format")
def main(repo: str, pr: tuple, verbose: bool):
    if verbose:
        os.environ["LOG_FORMAT"] = "console"
    configure_logging()
    agent = AgentLoop()
    summary = agent.run(repo=repo, pr_numbers=list(pr))
    click.echo(summary.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
