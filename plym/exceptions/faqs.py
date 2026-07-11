from plym.exceptions.base import PlymError


class FaqNotFoundError(PlymError):
    code = "faqs.not_found"

    def __init__(self) -> None:
        super().__init__(404, "FAQ not found")
