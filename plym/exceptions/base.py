from fastapi import HTTPException


class PlymError(HTTPException):
    code: str = "plym_error"

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(status_code=status_code, detail={"code": self.code, "message": message})
