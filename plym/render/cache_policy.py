from enum import StrEnum


class CachePolicy(StrEnum):
    PAGE = "public, max-age=300, stale-while-revalidate=60"
    MARKDOWN = "public, max-age=300"
    LISTING = "public, max-age=60"
    ASSET = "public, max-age=31536000, immutable"
    MEDIA = "public, max-age=31536000"
