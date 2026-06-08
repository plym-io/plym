from datetime import datetime
from typing import Any

from pydantic import Field

from plym.models.common import ORMModel


class LogEntry(ORMModel):
    id: int
    event: str
    actor_id: int | None = None
    target: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    audit: bool
    created_at: datetime
