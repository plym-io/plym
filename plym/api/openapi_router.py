from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Request

from plym.api.deps import current_user

router = APIRouter(prefix="/api", tags=["OpenAPI"], dependencies=[Depends(current_user)])


@router.get("/openapi.json")
async def openapi_schema(request: Request) -> dict[str, Any]:
    app: FastAPI = request.app
    return app.openapi()
