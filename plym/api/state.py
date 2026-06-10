from fastapi import Request

from plym.build.asset_downloader import SiteAssets
from plym.config.site import SiteConfig


def site_config(request: Request) -> SiteConfig:
    return request.app.state.site


def site_assets(request: Request) -> SiteAssets:
    return request.app.state.assets


def bundled_css(request: Request) -> str:
    return request.app.state.css


def prism_js(request: Request) -> str:
    return request.app.state.prism_js
