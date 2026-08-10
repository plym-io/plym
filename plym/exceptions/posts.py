from plym.exceptions.base import PlymError


class PostNotFoundError(PlymError):
    code = "posts.not_found"

    def __init__(self) -> None:
        super().__init__(404, "Post not found")


class SlugConflictError(PlymError):
    code = "posts.slug_conflict"

    def __init__(self, slug: str) -> None:
        super().__init__(409, f"Slug '{slug}' is already in use")


class ReservedSlugError(PlymError):
    code = "posts.reserved_slug"

    def __init__(self, slug: str) -> None:
        super().__init__(400, f"'{slug}' is a reserved path segment")


class TemplateNotFoundError(PlymError):
    code = "posts.template_not_found"

    def __init__(self, template: str) -> None:
        super().__init__(400, f"Template '{template}' not found or invalid")


class TooManyTabsError(PlymError):
    code = "posts.too_many_tabs"

    def __init__(self, count: int, maximum: int) -> None:
        super().__init__(
            400,
            f"A tab set has {count} tabs; the maximum is {maximum}",
        )


class UnclosedBlockError(PlymError):
    code = "posts.unclosed_block"

    def __init__(self, name: str) -> None:
        super().__init__(400, f"Block ':::{name}' is never closed by a ':::' line")


class MisplacedTabError(PlymError):
    code = "posts.misplaced_tab"

    def __init__(self) -> None:
        super().__init__(400, "':::tab' is only valid inside a ':::tabs' block")


class TabSetContentError(PlymError):
    code = "posts.tab_set_content"

    def __init__(self) -> None:
        super().__init__(400, "A ':::tabs' block may only contain ':::tab <name>' blocks")


class EmptyTabSetError(PlymError):
    code = "posts.empty_tab_set"

    def __init__(self) -> None:
        super().__init__(400, "A ':::tabs' block contains no tabs")
