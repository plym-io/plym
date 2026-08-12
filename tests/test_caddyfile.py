import re
from pathlib import Path

from plym.render.cache_policy import CachePolicy

CADDYFILE = Path("docker/Caddyfile")

# Caddy serves every artifact, so it is the emitter for those resources. It cannot read
# config.yaml, so the values cannot be derived at runtime — they are pinned here instead,
# against the one table the app reads, so the two cannot drift silently.
CADDY_POLICIES = {
    "@page": CachePolicy.PAGE,
    "@md": CachePolicy.MARKDOWN,
    "{$PLYM_BLOG_PREFIX}/webfonts/*": CachePolicy.ASSET,
    "{$PLYM_BLOG_PREFIX}/static/*": CachePolicy.ASSET,
    "/webfonts/*": CachePolicy.ASSET,
    "/static/*": CachePolicy.ASSET,
    "@found": CachePolicy.MEDIA,
    "@sitemap": CachePolicy.LISTING,
    "@llms": CachePolicy.LISTING,
    "@robots": CachePolicy.LISTING,
    "@searchindex": CachePolicy.LISTING,
    "@index": CachePolicy.LISTING,
    "@indexmd": CachePolicy.MARKDOWN,
    "@pagedindex": CachePolicy.LISTING,
}

_NAMED_MATCHER = re.compile(r"^\s*(@[\w.-]+)\s+\{\s*$", re.MULTILINE)
_HANDLE = re.compile(r"^\s*handle[a-z_]*\s*(.*?)\s*\{\s*$", re.MULTILINE)


def _block_at(source: str, brace: int) -> str:
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[brace + 1 : index]
    raise AssertionError(f"unbalanced braces in {CADDYFILE} at offset {brace}")


def _open_brace(source: str, match: re.Match[str]) -> int:
    return match.start() + match.group().rindex("{")


def _named_matchers(source: str) -> dict[str, str]:
    return {
        match.group(1): _block_at(source, _open_brace(source, match))
        for match in _NAMED_MATCHER.finditer(source)
    }


def _handlers(source: str) -> list[tuple[str, str]]:
    return [
        (match.group(1).strip(), _block_at(source, _open_brace(source, match)))
        for match in _HANDLE.finditer(source)
    ]


def _leaf_handlers(source: str) -> list[tuple[str, str]]:
    return [(matcher, body) for matcher, body in _handlers(source) if not _HANDLE.search(body)]


def test_the_file_server_never_answers_an_explicit_md_url() -> None:
    source = CADDYFILE.read_text(encoding="utf-8")
    matchers = _named_matchers(source)

    offenders = [
        matcher
        for matcher, body in _handlers(source)
        if "file_server" in body and re.search(r"path\s+\*\.md\b", matchers.get(matcher, matcher))
    ]
    assert not offenders, (
        "md_urls.enabled is decided in config.yaml, which Caddy cannot read. A file_server "
        "that answers *.md serves the artifact before the app's gate runs, so the documented "
        f"toggle does nothing in the only deployment plym ships. Offending handler(s): {offenders}"
    )


def _declared_cache_controls(body: str) -> list[str]:
    return re.findall(r'header\s+Cache-Control\s+"([^"]*)"', body)


def test_every_caddy_cache_header_comes_from_the_policy_table() -> None:
    source = CADDYFILE.read_text(encoding="utf-8")
    known = {policy.value for policy in CachePolicy}

    declared = {
        matcher: value
        for matcher, body in _leaf_handlers(source)
        for value in _declared_cache_controls(body)
    }
    unknown = {m: v for m, v in declared.items() if v not in known}
    assert not unknown, (
        "these Cache-Control values are not in plym.render.cache_policy, so a resource is "
        f"governed by a constant nobody can find from the app: {unknown}"
    )

    wrong = {
        matcher: (declared.get(matcher), expected.value)
        for matcher, expected in CADDY_POLICIES.items()
        if declared.get(matcher) != expected.value
    }
    assert not wrong, f"Caddy disagrees with the policy table (got, expected): {wrong}"


def test_the_policy_table_covers_every_resource_caddy_serves() -> None:
    source = CADDYFILE.read_text(encoding="utf-8")
    serving = {
        matcher
        for matcher, body in _leaf_handlers(source)
        if "file_server" in body and "Cache-Control" in body
    }
    uncovered = serving - set(CADDY_POLICIES)
    assert not uncovered, (
        "Caddy serves these off disk with a cache header the policy table does not pin, so "
        f"they can drift from the app's answer for the same resource: {uncovered}"
    )


# The sanitizer keeps remote images in post bodies (ALLOWED_TAGS has img, ALLOWED_URL_SCHEMES
# has https) and the default post template renders author.avatar_url verbatim. A policy that
# forbids loading them would have plym render content it then guarantees the browser drops.
# Everything that actually governs authored HTML stays exactly as strict.
CSP_DIRECTIVES = {
    "default-src": "'self'",
    "script-src": "'self' 'unsafe-inline'",
    "style-src": "'self' 'unsafe-inline'",
    "img-src": "'self' data: https:",
    "font-src": "'self'",
    "object-src": "'none'",
    "base-uri": "'self'",
    "frame-ancestors": "'none'",
    "form-action": "'self'",
}


def _blog_csp() -> dict[str, str]:
    source = CADDYFILE.read_text(encoding="utf-8")
    match = re.search(r'header @notdocs Content-Security-Policy "([^"]*)"', source)
    assert match, "the blog Content-Security-Policy is no longer set where this test looks"
    return {
        directive.split(" ", 1)[0]: directive.split(" ", 1)[1]
        for directive in (part.strip() for part in match.group(1).split(";"))
        if directive
    }


def test_the_blog_content_security_policy_is_pinned() -> None:
    assert _blog_csp() == CSP_DIRECTIVES


def test_remote_images_survive_the_sanitizer_the_policy_has_to_allow() -> None:
    from plym.render.sanitizer import ALLOWED_ATTRIBUTES, ALLOWED_TAGS, ALLOWED_URL_SCHEMES

    assert "img" in ALLOWED_TAGS
    assert "src" in ALLOWED_ATTRIBUTES["img"]
    assert "https" in ALLOWED_URL_SCHEMES
    assert "https:" in _blog_csp()["img-src"]
