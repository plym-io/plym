from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from plym.api.deps import db_session, require_editor
from plym.models.faq import Faq, FaqItem
from plym.service.faq_service import FaqService

router = APIRouter(prefix="/api/faqs", tags=["FAQs"])


@router.get("", response_model=list[Faq])
async def list_faqs(session: AsyncSession = Depends(db_session)) -> list[Faq]:
    return await FaqService(session).list()


@router.get("/{faq_id}", response_model=Faq)
async def get_faq(faq_id: int, session: AsyncSession = Depends(db_session)) -> Faq:
    return await FaqService(session).get(faq_id)


@router.post("", response_model=Faq, status_code=201, dependencies=[Depends(require_editor)])
async def create_faq(
    payload: FaqItem, session: AsyncSession = Depends(db_session)
) -> Faq:
    return await FaqService(session).create(payload)


@router.put("/{faq_id}", response_model=Faq, dependencies=[Depends(require_editor)])
async def update_faq(
    faq_id: int, payload: FaqItem, session: AsyncSession = Depends(db_session)
) -> Faq:
    return await FaqService(session).update(faq_id, payload)


@router.delete("/{faq_id}", status_code=204, dependencies=[Depends(require_editor)])
async def delete_faq(faq_id: int, session: AsyncSession = Depends(db_session)) -> None:
    await FaqService(session).delete(faq_id)
