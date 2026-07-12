from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from plym.config.merge import deep_merge
from plym.settings import settings


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
    blog_home: str = "plym.local/blog"
    blog_prefix: str = "/blog"
    language: str = "en"
    template: str = "default"

    @field_validator("blog_prefix")
    @classmethod
    def _normalize_blog_prefix(cls, value: str) -> str:
        v = (value or "").strip().rstrip("/")
        if v and not v.startswith("/"):
            v = "/" + v
        return v
    fonts: FontsConfig = Field(default_factory=FontsConfig)
    colors: ColorsConfig = Field(default_factory=ColorsConfig)
    prism: PrismConfig = Field(default_factory=PrismConfig)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    reading: ReadingConfig = Field(default_factory=ReadingConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    media: MediaConfig = Field(default_factory=MediaConfig)
    http_cache: HttpCacheConfig = Field(default_factory=HttpCacheConfig)
    robots: RobotsConfig = Field(default_factory=RobotsConfig)
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
    """Subset of SiteConfig fields a template can declare as defaults.

    Operator-only fields (site identity, behaviour, injection, etc.) are
    rejected at load time via ``extra="forbid"``.
    """

    model_config = ConfigDict(extra="forbid")
    fonts: FontsConfig | None = None
    colors: ColorsConfig | None = None
    prism: TemplatePrismConfig | None = None


def _load_template_overrides(template_name: str) -> dict:
    """Return the raw dict from ``plym/templates/<name>/template.yaml`` if it exists.

    Validates against ``TemplateConfig`` to reject fields a template is not
    allowed to declare. Returns the raw YAML dict (only fields explicitly set)
    so the deep merge contributes nothing for undeclared fields.
    """
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
    raw_operator: dict = {}
    if target.exists():
        with target.open("r", encoding="utf-8") as f:
            raw_operator = yaml.safe_load(f) or {}

    template_name = raw_operator.get("template", "default")
    raw_template = _load_template_overrides(template_name)

    merged = deep_merge(raw_template, raw_operator)
    return SiteConfig.model_validate(merged)
