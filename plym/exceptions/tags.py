from plym.exceptions.base import PlymError


class TagNotFoundError(PlymError):
    code = "tags.not_found"

    def __init__(self) -> None:
        super().__init__(404, "Tag not found")
