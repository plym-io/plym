import re

from pydantic import AfterValidator
from typing_extensions import Annotated

_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate(value: str) -> str:
    cleaned = (value or "").strip().lower()
    if not _EMAIL_PATTERN.match(cleaned):
        raise ValueError("Invalid email address format")
    return cleaned


PlymEmail = Annotated[str, AfterValidator(_validate)]
