from pydantic import BaseModel, Field

from plym.models.common import ORMModel


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)


class TagUpdate(BaseModel):
    weight: int | None = None


class Tag(ORMModel):
    id: int
    name: str
    slug: str
    weight: int | None = None
