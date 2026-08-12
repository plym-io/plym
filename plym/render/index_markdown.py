from typing import Any

_ESCAPES = str.maketrans({"\\": "\\\\", "[": "\\[", "]": "\\]", "(": "\\(", ")": "\\)"})


def _collapse(value: str) -> str:
    return " ".join(value.split())


def _text(value: str) -> str:
    return _collapse(value).translate(_ESCAPES)


def _entry(base: str, post: dict[str, Any]) -> str:
    entry = f"- [{_text(post['title'])}]({base}/{post['path']})"
    if post.get("excerpt"):
        entry = f"{entry}: {_text(post['excerpt'])}"
    return entry


def render_index_markdown(
    *,
    name: str,
    description: str | None,
    base: str,
    posts: list[dict[str, Any]],
    page: int,
    pages: int,
    prev_url: str | None,
    next_url: str | None,
) -> str:
    sections = [f"# {name}" if page == 1 else f"# {name} — page {page} of {pages}"]
    if description:
        sections.append(f"> {_collapse(description)}")
    if posts:
        sections.append("\n".join(_entry(base, post) for post in posts))
    else:
        sections.append("No posts yet.")
    navigation = [
        f"[{label}]({url})" for label, url in (("Previous", prev_url), ("Next", next_url)) if url
    ]
    if navigation:
        sections.append(" · ".join(navigation))
    return "\n\n".join(sections) + "\n"
