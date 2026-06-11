from fastapi import Request

from plym.config.site import SiteConfig


def site_config(request: Request) -> SiteConfig:
    return request.app.state.site


def bundled_css(request: Request) -> str:
    return request.app.state.css


def prism_js(request: Request) -> str:
    return request.app.state.prism_js
