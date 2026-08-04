import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from plym.config.merge import deep_merge
from plym.render.urls import RESERVED_SEGMENTS
from plym.settings import settings

_PREFIX_PATTERN = re.compile(r"(?:/[a-z0-9]+(?:-[a-z0-9]+)*)+")


def normalize_prefix(value: str | None) -> str:
    v = (value or "").strip().rstrip("/")
    if v and not v.startswith("/"):
        v = "/" + v
    return v


def _url_path(url: str) -> str:
    rest = url.strip().partition("://")[2] or url.strip()
    _, slash, path = rest.partition("/")
    return f"{slash}{path}".rstrip("/") if slash else ""


class FontsConfig(BaseModel):
    heading: str = "Inter"
    body: str = "Merriweather"


class ColorsConfig(BaseModel):
    primary: str = "#111111"
    secondary: str = "#444444"
    accent: str = "#0066ff"
    background: str = "#ffffff"


class PrismConfig(BaseModel):
    enabled: bool = False
    languages: str = "python"
    theme: str = "tomorrow"

    @property
    def language_list(self) -> list[str]:
        return [lang.strip() for lang in self.languages.split(",") if lang.strip()]


class PaginationConfig(BaseModel):
    page_size: int = 10


class ReadingConfig(BaseModel):
    words_per_minute: int = 200


class BackupConfig(BaseModel):
    frequency: int = 7


class MediaConfig(BaseModel):
    location: str | None = None


class MdUrlsConfig(BaseModel):
    enabled: bool = False


class RobotsConfig(BaseModel):
    serve: bool = True
    disallow_paths: list[str] = Field(default_factory=lambda: ["/api/"])


class InjectConfig(BaseModel):
    head: str = ""
    body: str = ""

    @field_validator("head", "body")
    @classmethod
    def _no_terminator(cls, value: str) -> str:
        lowered = value.lower()
        if "</head>" in lowered or "</body>" in lowered:
            raise ValueError(
                "inject snippet must not contain </head> or </body> — "
                "those tags are plym's injection anchors and would break asset inlining"
            )
        return value


class HttpCacheConfig(BaseModel):
    enabled: bool = True
    max_age: int = 300
    index_max_age: int = 60
    public: bool = True

    def header_for_post(self) -> str | None:
        if not self.enabled:
            return None
        scope = "public" if self.public else "private"
        return f"{scope}, max-age={self.max_age}"

    def header_for_index(self) -> str | None:
        if not self.enabled:
            return None
        scope = "public" if self.public else "private"
        return f"{scope}, max-age={self.index_max_age}"


class SiteConfig(BaseModel):
    name: str = "Plym"
    description: str | None = None
    website: str = "plym.local"
    blog_home: str = "plym.local"
    blog_prefix: str = ""
    language: str = "en"
    template: str = "default"

    @field_validator("blog_prefix")
    @classmethod
    def _normalize_blog_prefix(cls, value: str) -> str:
        v = normalize_prefix(value)
        if v and not _PREFIX_PATTERN.fullmatch(v):
            raise ValueError(
                f"blog_prefix {value!r} must be one or more lowercase path segments, "
                "for example /blog or /docs/notes"
            )
        claimed = sorted(set(v.strip("/").split("/")) & RESERVED_SEGMENTS) if v else []
        if claimed:
            raise ValueError(
                f"blog_prefix {value!r} uses {', '.join(claimed)}, which the blog already "
                "serves for its own routes. Hosting the blog there hides those routes and "
                "makes robots.txt disallow the whole site; choose another path."
            )
        return v

    @model_validator(mode="after")
    def _check_prefix_matches_home(self) -> "SiteConfig":
        home_path = _url_path(self.blog_home)
        if home_path != self.blog_prefix:
            raise ValueError(
                f"blog_home {self.blog_home!r} ends with path {home_path or '/'!r} but "
                f"blog_prefix is {self.blog_prefix or '/'!r}. They address the same URL and "
                "must agree; update config.yaml (and PLYM_BLOG_PREFIX) so they match."
            )
        return self

    @model_validator(mode="after")
    def _default_robots_to_the_served_surfaces(self) -> "SiteConfig":
        if "disallow_paths" not in self.robots.model_fields_set:
            prefix = self.blog_prefix
            paths = ["/api/", "/admin", "/plym-admin"]
            if prefix:
                paths += [f"{prefix}/api/", f"{prefix}/plym-admin"]
            self.robots.disallow_paths = paths
        return self

    fonts: FontsConfig = Field(default_factory=FontsConfig)
    colors: ColorsConfig = Field(default_factory=ColorsConfig)
    prism: PrismConfig = Field(default_factory=PrismConfig)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    reading: ReadingConfig = Field(default_factory=ReadingConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    http_cache: HttpCacheConfig = Field(default_factory=HttpCacheConfig)
    robots: RobotsConfig = Field(default_factory=RobotsConfig)
    md_urls: MdUrlsConfig = Field(default_factory=MdUrlsConfig)
    inject: InjectConfig = Field(default_factory=InjectConfig)
    logo: str | None = None
    favicon: str | None = None

    def public_blog_url(self) -> str:
        url = self.blog_home.rstrip("/")
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return url

    def public_origin(self) -> str:
        url = self.public_blog_url()
        scheme, _, rest = url.partition("://")
        return f"{scheme}://{rest.split('/', 1)[0]}"

    def absolute_url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.public_origin()}{path}"


class TemplatePrismConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    theme: str | None = None


class TemplateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fonts: FontsConfig | None = None
    colors: ColorsConfig | None = None
    prism: TemplatePrismConfig | None = None


def _load_template_overrides(template_name: str) -> dict[str, Any]:
    template_yaml = settings.templates_dir / template_name / "template.yaml"
    if not template_yaml.exists():
        return {}
    with template_yaml.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    TemplateConfig.model_validate(raw)
    return raw


@lru_cache(maxsize=1)
def load_site_config(path: Path | None = None) -> SiteConfig:
    target = path or settings.config_path
    raw_operator: dict[str, Any] = {}
    if target.exists():
        with target.open("r", encoding="utf-8") as f:
            raw_operator = yaml.safe_load(f) or {}

    template_name = raw_operator.get("template", "default")
    raw_template = _load_template_overrides(template_name)

    merged = deep_merge(raw_template, raw_operator)
    config = SiteConfig.model_validate(merged)

    served = normalize_prefix(settings.blog_prefix)
    if served and served != config.blog_prefix:
        raise ValueError(
            f"PLYM_BLOG_PREFIX is {served or '/'!r} but config.yaml blog_prefix is "
            f"{config.blog_prefix or '/'!r}. The proxy would serve one path while the app "
            "answers on another; set both to the same value (plym set url does this for you)."
        )
    return config
