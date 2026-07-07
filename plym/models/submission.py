from datetime import datetime
from typing import Any

from pydantic import BaseModel, IPvAnyAddress

from plym.models.common import ORMModel


class Submission(ORMModel):
    id: int
    payload: dict[str, Any]
    user_agent: str | None = None
    client_addr: IPvAnyAddress | None = None
    created_at: datetime


class SubmissionReceipt(BaseModel):
    id: int
    created_at: datetime


class SubmissionPage(BaseModel):
    items: list[Submission]
    total: int
    page: int
    page_size: int
