from github import Github
from github.GithubException import GithubException
from pydantic import BaseModel

from algosentinel.config import settings
from algosentinel.models.github import ChangedFile, Diff, PRDetails
from algosentinel.models.reports import ComplexityReport
from algosentinel.models.sandbox import FunctionCode
from algosentinel.resilience.errors import GitHubNotFoundError, GitHubRateLimitError
from algosentinel.resilience.rate_limiter import TokenBucketRateLimiter
from algosentinel.resilience.retry import with_retry
from algosentinel.tools.registry import tool


class GetPRDetailsInput(BaseModel):
    repo: str
    pr_number: int


class GetPRDiffInput(BaseModel):
    repo: str
    pr_number: int


class ListPRFilesInput(BaseModel):
    repo: str
    pr_number: int


class ListRecentPRsInput(BaseModel):
    repo: str
    limit: int = 10
    state: str = "closed"


class GetCommitDiffInput(BaseModel):
    repo: str
    sha: str


class SpawnFunctionAnalysisSubagentInput(BaseModel):
    function_code: FunctionCode
    function_code_after: FunctionCode
    repo: str
    pr_number: int


@with_retry()
def _github_client() -> Github:
    return Github(settings.github_token)


def _handle_github_error(e: GithubException) -> None:
    if e.status == 404:
        raise GitHubNotFoundError(str(e)) from e
    if e.status == 403 and "rate limit" in str(e).lower():
        raise GitHubRateLimitError(str(e)) from e
    raise


@with_retry()
def _get_repo(repo: str):
    try:
        return _github_client().get_repo(repo)
    except GithubException as e:
        _handle_github_error(e)
        raise


@tool(
    namespace="github",
    description="Fetch PR details including SHA and branch info.",
    input_model=GetPRDetailsInput,
    output_model=PRDetails,
)
def get_pr_details(inp: GetPRDetailsInput) -> PRDetails:
    gh_repo = _get_repo(inp.repo)
    try:
        pr = gh_repo.get_pull(inp.pr_number)
    except GithubException as e:
        _handle_github_error(e)
        raise
    return PRDetails(
        number=pr.number,
        title=pr.title,
        body=pr.body,
        head_sha=pr.head.sha,
        base_sha=pr.base.sha,
        head_branch=pr.head.ref,
        base_branch=pr.base.ref,
        author=pr.user.login if pr.user else "unknown",
        created_at=pr.created_at.isoformat() if pr.created_at else "",
    )


def _files_to_changed(files) -> list[ChangedFile]:
    result = []
    for f in files:
        result.append(
            ChangedFile(
                filename=f.filename,
                status=f.status,
                additions=f.additions,
                deletions=f.deletions,
                patch=f.patch,
            )
        )
    return result


@tool(
    namespace="github",
    description="Get the full diff for a pull request.",
    input_model=GetPRDiffInput,
    output_model=Diff,
)
def get_pr_diff(inp: GetPRDiffInput) -> Diff:
    gh_repo = _get_repo(inp.repo)
    pr = gh_repo.get_pull(inp.pr_number)
    files = list(pr.get_files())
    changed = _files_to_changed(files)
    return Diff(
        files=changed,
        total_additions=sum(f.additions for f in changed),
        total_deletions=sum(f.deletions for f in changed),
    )


@tool(
    namespace="github",
    description="List all files changed in a pull request.",
    input_model=ListPRFilesInput,
    output_model=list,
)
def list_pr_files(inp: ListPRFilesInput) -> list[ChangedFile]:
    gh_repo = _get_repo(inp.repo)
    pr = gh_repo.get_pull(inp.pr_number)
    return _files_to_changed(pr.get_files())


@tool(
    namespace="github",
    description="List recent pull requests in a repository.",
    input_model=ListRecentPRsInput,
    output_model=list,
)
def list_recent_prs(inp: ListRecentPRsInput) -> list[dict]:
    gh_repo = _get_repo(inp.repo)
    pulls = gh_repo.get_pulls(state=inp.state, sort="created", direction="desc")
    result = []
    for i, pr in enumerate(pulls):
        if i >= inp.limit:
            break
        result.append(
            {
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "created_at": pr.created_at.isoformat() if pr.created_at else "",
            }
        )
    return result


@tool(
    namespace="github",
    description="Get the diff for a single commit SHA.",
    input_model=GetCommitDiffInput,
    output_model=Diff,
)
def get_commit_diff(inp: GetCommitDiffInput) -> Diff:
    gh_repo = _get_repo(inp.repo)
    commit = gh_repo.get_commit(inp.sha)
    changed = []
    for f in commit.files:
        changed.append(
            ChangedFile(
                filename=f.filename,
                status=f.status,
                additions=f.additions,
                deletions=f.deletions,
                patch=f.patch,
            )
        )
    return Diff(
        files=changed,
        total_additions=sum(f.additions for f in changed),
        total_deletions=sum(f.deletions for f in changed),
    )


@tool(
    namespace="github",
    description="Spawn FunctionAnalysisSubagent to empirically measure complexity regression.",
    input_model=SpawnFunctionAnalysisSubagentInput,
    output_model=ComplexityReport,
)
def spawn_function_analysis_subagent(
    inp: SpawnFunctionAnalysisSubagentInput,
) -> ComplexityReport:
    from algosentinel.agent.subagent import FunctionAnalysisSubagent

    limiter = TokenBucketRateLimiter(rate_per_minute=settings.gemini_max_rpm)
    subagent = FunctionAnalysisSubagent(
        function_code=inp.function_code,
        function_code_after=inp.function_code_after,
        rate_limiter=limiter,
    )
    return subagent.run()
