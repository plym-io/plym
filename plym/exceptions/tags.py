from plym.exceptions.base import PlymError


class TagNotFoundError(PlymError):
    code = "tags.not_found"

    def __init__(self) -> None:
        super().__init__(404, "Tag not found")


class TagInUseError(PlymError):
    code = "tags.in_use"

    def __init__(self, posts: int) -> None:
        super().__init__(428, f"Tag is assigned to {posts} post(s)")
