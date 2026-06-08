from plym.exceptions.base import PlymError


class InvalidCredentialsError(PlymError):
    code = "auth.invalid_credentials"

    def __init__(self) -> None:
        super().__init__(401, "Invalid email or password")


class InactiveUserError(PlymError):
    code = "auth.inactive_user"

    def __init__(self) -> None:
        super().__init__(403, "User account is inactive")


class TokenInvalidError(PlymError):
    code = "auth.token_invalid"

    def __init__(self) -> None:
        super().__init__(401, "Token is invalid or expired")


class InsufficientRoleError(PlymError):
    code = "auth.insufficient_role"

    def __init__(self) -> None:
        super().__init__(403, "Insufficient role for this action")


class WeakPasswordError(PlymError):
    code = "auth.weak_password"

    def __init__(self) -> None:
        super().__init__(400, "Password must be at least 8 characters")
