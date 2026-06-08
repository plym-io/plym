from fastapi import APIRouter, Depends

from plym.api.deps import require_admin
from plym.api.state import site_config
from plym.config.site import SiteConfig

router = APIRouter(prefix="/api/config", tags=["config"], dependencies=[Depends(require_admin)])


@router.get("", response_model=SiteConfig)
async def get_config(site: SiteConfig = Depends(site_config)) -> SiteConfig:
    return site
