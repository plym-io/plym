from pydantic import BaseModel, Field

from plym.models.common import ORMModel


class FaqItem(BaseModel):
    question: str = Field(min_length=1, max_length=512)
    answer: str = Field(min_length=1, max_length=4096)


class Faq(ORMModel):
    id: int
    question: str
    answer: str
