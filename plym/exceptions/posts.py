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
