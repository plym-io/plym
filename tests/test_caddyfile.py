import re
from pathlib import Path

CADDYFILE = Path("docker/Caddyfile")

_NAMED_MATCHER = re.compile(r"^\s*(@[\w.-]+)\s*\{", re.MULTILINE)
_HANDLE = re.compile(r"^\s*handle[a-z_]*\s+(@[\w.-]+|[^\n{]*?)\s*\{", re.MULTILINE)


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


def _named_matchers(source: str) -> dict[str, str]:
    return {
        match.group(1): _block_at(source, match.end() - 1)
        for match in _NAMED_MATCHER.finditer(source)
    }


def _handlers(source: str) -> list[tuple[str, str]]:
    return [
        (match.group(1).strip(), _block_at(source, match.end() - 1))
        for match in _HANDLE.finditer(source)
    ]


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
