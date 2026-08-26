from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session, require_editor
from plym.api.state import site_config
from plym.config.site import SiteConfig
from plym.exceptions.search import SearchIndexNotBuiltError
from plym.models.search_index import SearchIndexBuildResult
from plym.render.cache_policy import CachePolicy
from plym.service.search_index_service import SearchIndexService

index_json_router = APIRouter(tags=["Search"], include_in_schema=False)
api_router = APIRouter(prefix="/api/index", tags=["Search"])


@index_json_router.get("/index.json")
async def serve_search_index(site: SiteConfig = Depends(site_config)) -> Response:
    content = SearchIndexService.read()
    if content is None:
        raise SearchIndexNotBuiltError()
    return Response(
        content=content,
        media_type="application/json",
        headers={"Cache-Control": CachePolicy.LISTING.value},
    )


@api_router.post("", response_model=SearchIndexBuildResult, dependencies=[Depends(require_editor)])
async def build_search_index(
    site: SiteConfig = Depends(site_config),
    session: AsyncSession = Depends(db_session),
) -> SearchIndexBuildResult:
    index = await SearchIndexService(session, site).build()
    return SearchIndexBuildResult(documents=index.count, generated_at=index.generated_at)
