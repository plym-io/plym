from typing import cast

from fastapi import Request

from plym.config.site import SiteConfig


def site_config(request: Request) -> SiteConfig:
    return cast(SiteConfig, request.app.state.site)


def bundled_css(request: Request) -> str:
    return cast(str, request.app.state.css)


def prism_js(request: Request) -> str:
    return cast(str, request.app.state.prism_js)
