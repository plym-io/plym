from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Role(StrEnum):
    READER = "reader"
    EDITOR = "editor"
    ADMINISTRATOR = "administrator"


class PostStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class Timestamped(ORMModel):
    created_at: datetime
    updated_at: datetime
