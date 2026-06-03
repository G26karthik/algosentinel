from typing import Optional

from pydantic import BaseModel, Field


class ChangedFile(BaseModel):
    filename: str
    status: str
    additions: int
    deletions: int
    patch: Optional[str] = None


class PRDetails(BaseModel):
    number: int
    title: str
    body: Optional[str]
    head_sha: str
    base_sha: str
    head_branch: str
    base_branch: str
    author: str
    created_at: str


class Diff(BaseModel):
    files: list[ChangedFile]
    total_additions: int
    total_deletions: int


class ReviewComment(BaseModel):
    path: str
    line: int
    body: str
    side: str = "RIGHT"


class ReviewResult(BaseModel):
    review_id: int
    state: str
    url: str


class Branch(BaseModel):
    name: str
    sha: str


class MergeResult(BaseModel):
    merged: bool
    message: str
    sha: Optional[str] = None
