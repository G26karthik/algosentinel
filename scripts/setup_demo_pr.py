#!/usr/bin/env python3
"""Create a demo PR with O(n) -> O(n^2) regression on G26karthik/algosentinel."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../src"))

from github import Auth, Github

from algosentinel.config import settings

REPO = "G26karthik/algosentinel"
BRANCH = "demo/complexity-regression"
FILE_PATH = "examples/demo_utils.py"

POST_CODE = '''"""Demo module — intentional O(n^2) regression for agent audit."""

def find_duplicates(lst):
    result = []
    for i, x in enumerate(lst):
        if x in lst[:i]:
            result.append(x)
    return result
'''


def main():
    g = Github(auth=Auth.Token(settings.github_token))
    repo = g.get_repo(REPO)
    main_ref = repo.get_git_ref("heads/main")
    base_sha = main_ref.object.sha

    try:
        repo.get_git_ref(f"heads/{BRANCH}").delete()
        print(f"Deleted existing branch {BRANCH}")
    except Exception:
        pass

    repo.create_git_ref(ref=f"refs/heads/{BRANCH}", sha=base_sha)
    print(f"Created branch {BRANCH} from main ({base_sha[:8]})")

    contents = repo.get_contents(FILE_PATH, ref=BRANCH)
    repo.update_file(
        FILE_PATH,
        "demo: introduce O(n^2) find_duplicates regression",
        POST_CODE,
        contents.sha,
        branch=BRANCH,
    )
    print(f"Updated {FILE_PATH} on {BRANCH}")

    pr = repo.create_pull(
        title="demo: complexity regression in find_duplicates (O(n) → O(n²))",
        body=(
            "Intentional demo PR for AlgoSentinel audit.\n\n"
            "Replaces O(n) set-based duplicate detection with O(n²) slice scanning."
        ),
        head=BRANCH,
        base="main",
    )
    print(f"Opened PR #{pr.number}: {pr.html_url}")
    return pr.number


if __name__ == "__main__":
    main()
