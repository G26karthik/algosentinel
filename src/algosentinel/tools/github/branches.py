from pydantic import BaseModel

from algosentinel.models.github import Branch
from algosentinel.tools.github.pr import _get_repo, _handle_github_error
from algosentinel.tools.registry import tool
from github.GithubException import GithubException


class CreateBranchInput(BaseModel):
    repo: str
    branch_name: str
    from_ref: str


class PushFileInput(BaseModel):
    repo: str
    path: str
    content: str
    branch: str
    commit_message: str


class CreatePRInput(BaseModel):
    repo: str
    title: str
    body: str
    head: str
    base: str = "main"


class CheckBranchExistsInput(BaseModel):
    repo: str
    branch_name: str


class GetRepoInfoInput(BaseModel):
    repo: str


@tool(
    namespace="github",
    description="Create a new branch from a ref.",
    input_model=CreateBranchInput,
    output_model=Branch,
)
def create_branch(inp: CreateBranchInput) -> Branch:
    gh_repo = _get_repo(inp.repo)
    try:
        source = gh_repo.get_git_ref(f"heads/{inp.from_ref}")
    except GithubException:
        source = gh_repo.get_git_ref(f"heads/{inp.from_ref.split('/')[-1]}")
    sha = source.object.sha
    ref = gh_repo.create_git_ref(ref=f"refs/heads/{inp.branch_name}", sha=sha)
    return Branch(name=inp.branch_name, sha=ref.object.sha)


@tool(
    namespace="github",
    description="Push or update a file on a branch.",
    input_model=PushFileInput,
    output_model=dict,
)
def push_file(inp: PushFileInput) -> dict:
    gh_repo = _get_repo(inp.repo)
    try:
        contents = gh_repo.get_contents(inp.path, ref=inp.branch)
        gh_repo.update_file(
            inp.path,
            inp.commit_message,
            inp.content,
            contents.sha,
            branch=inp.branch,
        )
        action = "updated"
    except GithubException:
        gh_repo.create_file(
            inp.path,
            inp.commit_message,
            inp.content,
            branch=inp.branch,
        )
        action = "created"
    return {"path": inp.path, "branch": inp.branch, "action": action}


@tool(
    namespace="github",
    description="Open a new pull request.",
    input_model=CreatePRInput,
    output_model=dict,
)
def create_pr(inp: CreatePRInput) -> dict:
    gh_repo = _get_repo(inp.repo)
    pr = gh_repo.create_pull(
        title=inp.title,
        body=inp.body,
        head=inp.head,
        base=inp.base,
    )
    return {"number": pr.number, "url": pr.html_url}


@tool(
    namespace="github",
    description="Check whether a branch exists.",
    input_model=CheckBranchExistsInput,
    output_model=bool,
)
def check_branch_exists(inp: CheckBranchExistsInput) -> bool:
    gh_repo = _get_repo(inp.repo)
    try:
        gh_repo.get_branch(inp.branch_name)
        return True
    except GithubException:
        return False


@tool(
    namespace="github",
    description="Return basic repository metadata.",
    input_model=GetRepoInfoInput,
    output_model=dict,
)
def get_repo_info(inp: GetRepoInfoInput) -> dict:
    gh_repo = _get_repo(inp.repo)
    return {
        "name": gh_repo.name,
        "full_name": gh_repo.full_name,
        "default_branch": gh_repo.default_branch,
        "language": gh_repo.language,
        "description": gh_repo.description,
        "stars": gh_repo.stargazers_count,
    }
