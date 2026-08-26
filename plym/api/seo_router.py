from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session
from plym.api.state import site_config
from plym.config.site import SiteConfig
from plym.exceptions.posts import PostNotFoundError
from plym.render.cache_policy import CachePolicy
from plym.service.site_files_service import SiteFilesService

router = APIRouter(tags=["SEO"], include_in_schema=False)

_LISTING = {"Cache-Control": CachePolicy.LISTING.value}


@router.get("/sitemap.xml")
async def sitemap(
    site: SiteConfig = Depends(site_config),
    session: AsyncSession = Depends(db_session),
) -> Response:
    body = await SiteFilesService(session, site).sitemap()
    return Response(content=body, media_type="application/xml", headers=_LISTING)


@router.get("/llms.txt")
async def llms_txt(
    site: SiteConfig = Depends(site_config),
    session: AsyncSession = Depends(db_session),
) -> Response:
    body = await SiteFilesService(session, site).llms_txt()
    return Response(content=body, media_type="text/markdown", headers=_LISTING)


@router.get("/robots.txt", response_class=PlainTextResponse)
async def robots(
    site: SiteConfig = Depends(site_config),
    session: AsyncSession = Depends(db_session),
) -> PlainTextResponse:
    body = SiteFilesService(session, site).robots_txt()
    if body is None:
        raise PostNotFoundError()
    return PlainTextResponse(content=body, headers=_LISTING)
