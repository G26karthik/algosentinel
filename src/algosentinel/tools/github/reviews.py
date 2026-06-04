from pydantic import BaseModel, Field

from algosentinel.models.github import ReviewComment, ReviewResult
from algosentinel.tools.github.pr import _get_repo, _handle_github_error
from algosentinel.tools.registry import tool
from github.GithubException import GithubException


class PostPRReviewInput(BaseModel):
    repo: str
    pr_number: int
    body: str
    comments: list[ReviewComment] = Field(default_factory=list)
    event: str = "COMMENT"


class PostPRCommentInput(BaseModel):
    repo: str
    pr_number: int
    body: str


class AddLabelInput(BaseModel):
    repo: str
    pr_number: int
    labels: list[str]


class GetPRReviewCommentsInput(BaseModel):
    repo: str
    pr_number: int


class ClosePRInput(BaseModel):
    repo: str
    pr_number: int


class MergePRInput(BaseModel):
    repo: str
    pr_number: int
    merge_method: str = "squash"


@tool(
    namespace="github",
    description="Post a PR review with optional inline comments.",
    input_model=PostPRReviewInput,
    output_model=ReviewResult,
)
def post_pr_review(inp: PostPRReviewInput) -> ReviewResult:
    gh_repo = _get_repo(inp.repo)
    pr = gh_repo.get_pull(inp.pr_number)
    comments = [
        {"path": c.path, "line": c.line, "body": c.body, "side": c.side}
        for c in inp.comments
    ]
    try:
        review = pr.create_review(body=inp.body, event=inp.event, comments=comments or None)
    except GithubException as e:
        _handle_github_error(e)
        raise
    return ReviewResult(
        review_id=review.id,
        state=review.state,
        url=review.html_url or "",
    )


@tool(
    namespace="github",
    description="Post a simple comment on the PR.",
    input_model=PostPRCommentInput,
    output_model=dict,
)
def post_pr_comment(inp: PostPRCommentInput) -> dict:
    gh_repo = _get_repo(inp.repo)
    pr = gh_repo.get_pull(inp.pr_number)
    comment = pr.create_issue_comment(inp.body)
    return {"id": comment.id, "url": comment.html_url}


@tool(
    namespace="github",
    description="Add labels to a pull request.",
    input_model=AddLabelInput,
    output_model=dict,
)
def add_label(inp: AddLabelInput) -> dict:
    gh_repo = _get_repo(inp.repo)
    issue = gh_repo.get_issue(inp.pr_number)
    issue.add_to_labels(*inp.labels)
    return {"labels": inp.labels}


@tool(
    namespace="github",
    description="Fetch existing review comments on a PR.",
    input_model=GetPRReviewCommentsInput,
    output_model=list,
)
def get_pr_review_comments(inp: GetPRReviewCommentsInput) -> list[ReviewComment]:
    gh_repo = _get_repo(inp.repo)
    pr = gh_repo.get_pull(inp.pr_number)
    comments = []
    for c in pr.get_review_comments():
        comments.append(
            ReviewComment(
                path=c.path,
                line=c.line or 0,
                body=c.body,
                side=getattr(c, "side", "RIGHT") or "RIGHT",
            )
        )
    return comments


@tool(
    namespace="github",
    description="Close a pull request without merging.",
    input_model=ClosePRInput,
    output_model=dict,
)
def close_pr(inp: ClosePRInput) -> dict:
    gh_repo = _get_repo(inp.repo)
    pr = gh_repo.get_pull(inp.pr_number)
    pr.edit(state="closed")
    return {"closed": True, "number": inp.pr_number}
