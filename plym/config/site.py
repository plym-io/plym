import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from plym.config.merge import deep_merge
from plym.render.urls import RESERVED_SEGMENTS
from plym.settings import settings

log = logging.getLogger("plym.config")

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


# Google Fonts family names use only letters, digits and spaces. The names also
# reach a :root{} declaration and the css2 URL verbatim, so nothing else may pass.
_FAMILY_PATTERN = re.compile(r"[A-Za-z0-9 ]+")

# Role names are labels, not weights: a template picks the number each one means,
# so `bold: 600` reads as "this template's bold is 600". The vocabulary is closed,
# which also caps a slot at five weights.
WeightRole = Literal["light", "regular", "medium", "bold", "black"]

CssWeight = Annotated[int, Field(ge=1, le=1000)]

DEFAULT_FAMILIES = {"heading": "Inter", "body": "Merriweather"}

DEFAULT_WEIGHTS: dict[str, dict[WeightRole, int]] = {
    "heading": {"bold": 600},
    "body": {"regular": 400},
}


def normalize_font_slots(raw: dict[str, Any]) -> dict[str, Any]:
    fonts = raw.get("fonts")
    if not isinstance(fonts, dict):
        return raw
    slots = {
        key: {"family": value} if key in DEFAULT_WEIGHTS and isinstance(value, str) else value
        for key, value in fonts.items()
    }
    return {**raw, "fonts": slots}


# COMPAT: every template written before weights were configurable hardcodes 600
# and 900 and reads none of the variables, so the one-weight-per-slot default
# would restyle all of them. A slot that declares no weights keeps the pair plym
# has always shipped; a slot that declares any gets exactly those. Drop this at
# the next major version, once those templates declare their own weights.
_UNDECLARED_SLOT_WEIGHTS: dict[str, dict[str, int]] = {
    "heading": {"bold": 600, "black": 900},
    "body": {"regular": 400},
}


def _keep_weights_of_undeclared_slots(raw: dict[str, Any]) -> dict[str, Any]:
    fonts = raw.get("fonts", {})
    if not isinstance(fonts, dict):
        return raw
    slots = dict(fonts)
    for slot_name, weights in _UNDECLARED_SLOT_WEIGHTS.items():
        slot = slots.get(slot_name, {"family": DEFAULT_FAMILIES[slot_name]})
        if isinstance(slot, dict) and not slot.get("weights"):
            slots[slot_name] = {**slot, "weights": dict(weights)}
    return {**raw, "fonts": slots}


class FontSlotConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    family: str
    weights: dict[WeightRole, CssWeight] = Field(default_factory=dict)

    @field_validator("family")
    @classmethod
    def _family_is_a_google_fonts_name(cls, value: str) -> str:
        # Google's embed URLs spell spaces as +, so operators paste that form.
        value = " ".join(value.replace("+", " ").split())
        if not _FAMILY_PATTERN.fullmatch(value):
            raise ValueError(f"font family {value!r} must match {_FAMILY_PATTERN.pattern}")
        return value


class FontsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heading: FontSlotConfig = Field(
        default_factory=lambda: FontSlotConfig(family=DEFAULT_FAMILIES["heading"])
    )
    body: FontSlotConfig = Field(
        default_factory=lambda: FontSlotConfig(family=DEFAULT_FAMILIES["body"])
    )

    def slots(self) -> tuple[tuple[str, FontSlotConfig], ...]:
        return (("heading", self.heading), ("body", self.body))

    @model_validator(mode="before")
    @classmethod
    def _accept_the_bare_family_string(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return normalize_font_slots({"fonts": data})["fonts"]
        return data

    @model_validator(mode="after")
    def _fill_default_weights(self) -> "FontsConfig":
        for slot_name, slot in self.slots():
            if not slot.weights:
                slot.weights = dict(DEFAULT_WEIGHTS[slot_name])
        return self


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

    def media_url(self, filename: str) -> str:
        base = (
            self.media.location.rstrip("/") if self.media.location else f"{self.blog_prefix}/media"
        )
        return f"{base}/{filename}"


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


REMOVED_KEYS = {
    "http_cache": (
        "cache lifetimes are now one policy per resource, decided where the bytes are served: "
        "docker/Caddyfile for artifacts, plym.render.cache_policy for the app's own routes. "
        "The values match the old defaults, so deleting the block changes nothing"
    ),
}


def _warn_about_unknown_keys(raw: dict[str, Any], source: Path) -> None:
    for key in raw:
        if key in SiteConfig.model_fields:
            continue
        removed = REMOVED_KEYS.get(key)
        if removed:
            log.warning("%s: %r is no longer used — %s.", source, key, removed)
        else:
            log.warning("%s: %r is not a plym setting and is ignored.", source, key)


@lru_cache(maxsize=1)
def load_site_config(path: Path | None = None) -> SiteConfig:
    target = path or settings.config_path
    raw_operator: dict[str, Any] = {}
    if target.exists():
        with target.open("r", encoding="utf-8") as f:
            raw_operator = yaml.safe_load(f) or {}
    _warn_about_unknown_keys(raw_operator, target)

    template_name = raw_operator.get("template", "default")
    raw_template = _load_template_overrides(template_name)

    # A bare-string slot must become {"family": ...} before the merge, or an
    # operator writing `heading: Roboto` would wipe the template's weight roles.
    merged = deep_merge(normalize_font_slots(raw_template), normalize_font_slots(raw_operator))
    config = SiteConfig.model_validate(_keep_weights_of_undeclared_slots(merged))

    served = normalize_prefix(settings.blog_prefix)
    if served and served != config.blog_prefix:
        raise ValueError(
            f"PLYM_BLOG_PREFIX is {served or '/'!r} but config.yaml blog_prefix is "
            f"{config.blog_prefix or '/'!r}. The proxy would serve one path while the app "
            "answers on another; set both to the same value (plym set url does this for you)."
        )
    return config
