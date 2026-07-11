from pathlib import Path

from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    TemplateNotFound,
    select_autoescape,
)

from plym.config.site import SiteConfig
from plym.exceptions.posts import TemplateNotFoundError
from plym.settings import settings

_CHROME_DIR = Path(__file__).parent / "chrome"


class TemplateRenderer:
    def __init__(self, site: SiteConfig) -> None:
        self._site = site
        template_root = settings.templates_dir / site.template
        self._user_env = Environment(
            loader=FileSystemLoader(str(template_root)),
            autoescape=select_autoescape(["html", "xml"]),
            enable_async=False,
        )
        self._chrome_env = Environment(
            loader=FileSystemLoader(str(_CHROME_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
            undefined=StrictUndefined,
            enable_async=False,
        )

    def render_post(self, context: dict) -> str:
        merged = self._with_globals(context)
        body = self._render_user("post.html", merged)
        return self._chrome_env.get_template("post.html").render({**merged, "body": body})

    def render_index(self, context: dict) -> str:
        merged = self._with_globals(context)
        body = self._render_user("index.html", merged)
        return self._chrome_env.get_template("index.html").render({**merged, "body": body})

    def _with_globals(self, context: dict) -> dict:
        return {
            **context,
            "site": self._site,
            "debug": settings.debug,
        }

    def _render_user(self, name: str, context: dict) -> str:
        try:
            template = self._user_env.get_template(name)
        except TemplateNotFound as e:
            raise TemplateNotFoundError(self._site.template) from e
        return template.render(**context)
