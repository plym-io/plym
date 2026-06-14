from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from plym.instrumentation.context import set_actor
from plym.service.token_service import TokenService


class ActorMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, jwt: TokenService) -> None:
        super().__init__(app)
        self._jwt = jwt

    async def dispatch(self, request: Request, call_next) -> Response:
        actor: int | None = None
        auth = request.headers.get("authorization")
        if auth and auth.lower().startswith("bearer "):
            try:
                payload = self._jwt.decode_access(auth.split(" ", 1)[1].strip())
                if payload.get("typ") == "access":
                    actor = int(payload["sub"])
            except Exception:
                actor = None
        set_actor(actor)
        if actor is not None:
            trace.get_current_span().set_attribute("plym.actor_id", actor)
        try:
            return await call_next(request)
        finally:
            set_actor(None)
