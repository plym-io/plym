from opentelemetry import trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from plym.service.token_service import TokenService


class ActorMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, jwt: TokenService) -> None:
        super().__init__(app)
        self._jwt = jwt

    async def dispatch(self, request: Request, call_next) -> Response:
        auth = request.headers.get("authorization")
        if auth and auth.lower().startswith("bearer "):
            try:
                payload = self._jwt.decode_access(auth.split(" ", 1)[1].strip())
                if payload.get("typ") == "access":
                    trace.get_current_span().set_attribute("plym.actor_id", int(payload["sub"]))
            except Exception:
                pass
        return await call_next(request)
