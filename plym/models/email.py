import re
from typing import Annotated

from pydantic import AfterValidator

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate(value: str) -> str:
    cleaned = (value or "").strip().lower()
    if not _EMAIL_PATTERN.match(cleaned):
        raise ValueError("Invalid email address format")
    return cleaned


PlymEmail = Annotated[str, AfterValidator(_validate)]
