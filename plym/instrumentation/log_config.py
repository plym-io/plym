import logging

from plym.settings import settings

_CONFIGURED = False


def configure_logging() -> None:
    """Route plym's own logs to the console so `docker compose logs api` and `plym --verbose`
    can consume them. Uvicorn keeps managing its own access/error loggers (propagate=False); this
    only governs the root and `plym.*` loggers. INFO by default, DEBUG when PLYM_DEBUG is set.
    Idempotent — safe to call on every import/reload.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return
    level = logging.DEBUG if settings.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
    )
    logging.getLogger("plym").setLevel(level)
    _CONFIGURED = True
