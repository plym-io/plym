from pydantic import BaseModel, Field

from plym.models.common import ORMModel


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    weight: int | None = None


class CategoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    weight: int | None = None


class Category(ORMModel):
    id: int
    name: str
    slug: str
    weight: int | None = None
