from pydantic import BaseModel


class RefreshReport(BaseModel):
    published: int
    stale: int
    rendered: int
    failed: int
    removed: int
