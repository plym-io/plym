import re
from typing import Any

_SEGMENT_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

RESERVED_SEGMENTS = frozenset(
    {
        "admin",
        "api",
        "health",
        "mcp",
        "media",
        "page",
        "plym-admin",
        "plym-docs",
        "static",
        "webfonts",
    }
)


def is_path_segment(value: str) -> bool:
    return bool(_SEGMENT_RE.match(value))


def post_path(category_slug: str | None, slug: str) -> str:
    return f"{category_slug}/{slug}" if category_slug else slug


def path_for_row(row: dict[str, Any]) -> str:
    category = row.get("category")
    category_slug = category["slug"] if category else row.get("category_slug")
    return post_path(category_slug, row["slug"])
