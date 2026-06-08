from plym.exceptions.base import PlymError


class UserNotFoundError(PlymError):
    code = "users.not_found"

    def __init__(self) -> None:
        super().__init__(404, "User not found")


class EmailAlreadyExistsError(PlymError):
    code = "users.email_exists"

    def __init__(self) -> None:
        super().__init__(409, "Email already in use")
