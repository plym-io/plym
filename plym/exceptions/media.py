from fastapi import HTTPException

from plym.exceptions.base import PlymError


class UnsupportedImageError(PlymError):
    code = "media.unsupported_image"

    def __init__(self) -> None:
        super().__init__(400, "Unsupported image format")


class UploadTooLargeError(PlymError):
    code = "media.upload_too_large"

    def __init__(self, max_bytes: int) -> None:
        super().__init__(413, f"Upload exceeds {max_bytes} bytes")


class MediaNotFoundError(PlymError):
    code = "media.not_found"

    def __init__(self) -> None:
        super().__init__(404, "Media not found")


class MediaForbiddenError(PlymError):
    code = "media.forbidden"

    def __init__(self) -> None:
        super().__init__(403, "Only the uploader can delete this media")


class MediaInUseError(HTTPException):
    def __init__(self, referenced_by: list[dict]) -> None:
        super().__init__(
            status_code=409,
            detail={
                "code": "media.in_use",
                "message": "Media is referenced by one or more posts",
                "referenced_by": referenced_by,
            },
        )
