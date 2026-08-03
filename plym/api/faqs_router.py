from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session, require_editor
from plym.api.state import bundled_css, prism_js, site_config
from plym.config.site import SiteConfig
from plym.models.faq import Faq, FaqItem
from plym.service.faq_service import FaqService

router = APIRouter(prefix="/api/faqs", tags=["FAQs"])


def _service(
    session: AsyncSession = Depends(db_session),
    site: SiteConfig = Depends(site_config),
    css: str = Depends(bundled_css),
    prism: str = Depends(prism_js),
) -> FaqService:
    return FaqService(session, site, css, prism)


@router.get("", response_model=list[Faq])
async def list_faqs(service: FaqService = Depends(_service)) -> list[Faq]:
    return await service.list()


@router.get("/{faq_id}", response_model=Faq)
async def get_faq(faq_id: int, service: FaqService = Depends(_service)) -> Faq:
    return await service.get(faq_id)


@router.post("", response_model=Faq, status_code=201, dependencies=[Depends(require_editor)])
async def create_faq(payload: FaqItem, service: FaqService = Depends(_service)) -> Faq:
    return await service.create(payload)


@router.put("/{faq_id}", response_model=Faq, dependencies=[Depends(require_editor)])
async def update_faq(faq_id: int, payload: FaqItem, service: FaqService = Depends(_service)) -> Faq:
    return await service.update(faq_id, payload)


@router.delete("/{faq_id}", status_code=204, dependencies=[Depends(require_editor)])
async def delete_faq(faq_id: int, service: FaqService = Depends(_service)) -> None:
    await service.delete(faq_id)
