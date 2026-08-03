from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session, require_editor
from plym.api.state import bundled_css, prism_js, site_config
from plym.config.site import SiteConfig
from plym.models.category import Category, CategoryCreate, CategoryUpdate
from plym.service.category_service import CategoryService

router = APIRouter(prefix="/api/categories", tags=["Categories"])


def _service(
    session: AsyncSession = Depends(db_session),
    site: SiteConfig = Depends(site_config),
    css: str = Depends(bundled_css),
    prism: str = Depends(prism_js),
) -> CategoryService:
    return CategoryService(session, site, css, prism)


@router.get("", response_model=list[Category])
async def list_categories(service: CategoryService = Depends(_service)) -> list[Category]:
    return await service.list()


@router.get("/{category_id}", response_model=Category)
async def get_category(category_id: int, service: CategoryService = Depends(_service)) -> Category:
    return await service.get(category_id)


@router.post("", response_model=Category, status_code=201, dependencies=[Depends(require_editor)])
async def create_category(
    payload: CategoryCreate, service: CategoryService = Depends(_service)
) -> Category:
    return await service.create(payload)


@router.patch("/{category_id}", response_model=Category, dependencies=[Depends(require_editor)])
async def update_category(
    category_id: int,
    payload: CategoryUpdate,
    service: CategoryService = Depends(_service),
) -> Category:
    return await service.update(category_id, payload)


@router.delete("/{category_id}", status_code=204, dependencies=[Depends(require_editor)])
async def delete_category(category_id: int, service: CategoryService = Depends(_service)) -> None:
    await service.delete(category_id)
