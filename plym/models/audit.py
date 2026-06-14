from datetime import datetime
from typing import Any

from pydantic import Field

from plym.models.common import ORMModel


class AuditEntry(ORMModel):
    id: int
    event: str
    actor_id: int | None = None
    target: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    request_id: str | None = None
    created_at: datetime
