from plym.exceptions.base import PlymError


class SearchIndexNotBuiltError(PlymError):
    code = "search.index_not_built"

    def __init__(self) -> None:
        super().__init__(404, "Search index has not been built yet")
