from plym.exceptions.base import PlymError


class CategoryNotFoundError(PlymError):
    code = "categories.not_found"

    def __init__(self) -> None:
        super().__init__(404, "Category not found")


class CategoryConflictError(PlymError):
    code = "categories.conflict"

    def __init__(self, name: str) -> None:
        super().__init__(409, f"Category '{name}' is already in use")


class CategoryInUseError(PlymError):
    code = "categories.in_use"

    def __init__(self, posts: int) -> None:
        super().__init__(409, f"Category is assigned to {posts} post(s)")


class InvalidCategoryNameError(PlymError):
    code = "categories.invalid_name"

    def __init__(self, name: str) -> None:
        super().__init__(400, f"Category name '{name}' has no url-safe form")


class ReservedCategoryNameError(PlymError):
    code = "categories.reserved_name"

    def __init__(self, slug: str) -> None:
        super().__init__(400, f"'{slug}' is a reserved path segment")
