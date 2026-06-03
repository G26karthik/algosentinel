from pydantic import BaseModel

from algosentinel.tools.github.pr import _get_repo, _handle_github_error
from algosentinel.tools.registry import tool
from github.GithubException import GithubException


class GetFileContentInput(BaseModel):
    repo: str
    path: str
    ref: str


@tool(
    namespace="github",
    description="Return raw file content at the given ref.",
    input_model=GetFileContentInput,
    output_model=str,
)
def get_file_content(inp: GetFileContentInput) -> str:
    gh_repo = _get_repo(inp.repo)
    try:
        content = gh_repo.get_contents(inp.path, ref=inp.ref)
        if isinstance(content, list):
            raise ValueError(f"Path {inp.path} is a directory")
        return content.decoded_content.decode("utf-8")
    except GithubException as e:
        _handle_github_error(e)
        raise


@tool(
    namespace="github",
    description="Return raw file content at ref (explicit pre/post version fetch).",
    input_model=GetFileContentInput,
    output_model=str,
)
def get_file_content_at_ref(inp: GetFileContentInput) -> str:
    return get_file_content(inp)
