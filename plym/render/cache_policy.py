from enum import StrEnum


class CachePolicy(StrEnum):
    PAGE = "public, max-age=300, stale-while-revalidate=60"
    MARKDOWN = "public, max-age=300"
    LISTING = "public, max-age=60"
    ASSET = "public, max-age=31536000, immutable"
    MEDIA = "public, max-age=31536000"


# Not a resource: the lifetime of a canonical redirect. A 308 with no Cache-Control is
# heuristically cacheable and clients may keep a permanent redirect indefinitely, so
# changing blog_prefix later would strand everyone who saw the old shape — and no purge
# reaches a browser. Short enough to recover from, long enough to save the round trip.
REDIRECT_CACHE_CONTROL = "public, max-age=300"
