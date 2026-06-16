from fastapi import APIRouter, Depends

from plym.api.deps import current_user
from plym.api.state import site_config
from plym.config.site import SiteConfig

router = APIRouter(prefix="/api/config", tags=["Config"], dependencies=[Depends(current_user)])


@router.get("", response_model=SiteConfig)
async def get_config(site: SiteConfig = Depends(site_config)) -> SiteConfig:
    return site
