import asyncio
import ipaddress
import mimetypes
import socket
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx
from markdownify import markdownify

from plym.mcp.settings import mcp_settings

MAX_REDIRECTS = 5
MAX_FETCH_BYTES = 16 * 1024 * 1024

_ALLOWED_SCHEMES = frozenset({"http", "https"})
# RFC 6598 shared address space: ipaddress does not classify it as private, but a
# CGNAT peer is as unreachable-by-design as an RFC 1918 one, so deny it explicitly.
_SHARED_ADDRESS_SPACE = ipaddress.ip_network("100.64.0.0/10")

type IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class FetchError(Exception):
    pass


class UnsafeUrlError(FetchError):
    pass


class FetchTooLargeError(FetchError):
    pass


@dataclass(frozen=True)
class Fetched:
    url: str
    content: bytes
    content_type: str | None
    encoding: str | None


def _filename_for(url: str, content_type: str | None) -> str:
    name = Path(urlparse(url).path).name
    if Path(name).suffix:
        return name
    extension = mimetypes.guess_extension((content_type or "").split(";")[0].strip()) or ""
    return f"{name or 'upload'}{extension}"


def _is_forbidden(address: IPAddress) -> bool:
    # An IPv4-mapped IPv6 literal (::ffff:169.254.169.254) carries none of the IPv4
    # properties, so unwrap it before judging or the metadata service slips through.
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
        or (address.version == 4 and address in _SHARED_ADDRESS_SPACE)
    )


def _resolve(host: str, port: int) -> list[IPAddress]:
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"Cannot resolve host {host!r}: {exc}") from exc
    # getaddrinfo hands back scoped literals such as fe80::1%eth0, which ip_address rejects.
    return [ipaddress.ip_address(str(info[4][0]).split("%")[0]) for info in infos]


async def _assert_public(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(
            f"Only http and https URLs can be fetched, {url!r} uses {parsed.scheme or 'no'} scheme."
        )
    host = parsed.hostname
    if not host:
        raise UnsafeUrlError(f"URL {url!r} has no host.")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise UnsafeUrlError(f"URL {url!r} has an invalid port.") from exc
    # Every address behind the name must be public: one public A record does not
    # excuse a second record pointing at the compose network.
    for address in await asyncio.to_thread(_resolve, host, port):
        if _is_forbidden(address):
            raise UnsafeUrlError(
                f"Refusing to fetch {url!r}: {host} resolves to the non-public address {address}."
            )


async def _read_capped(response: httpx.Response) -> bytes:
    declared = response.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_FETCH_BYTES:
        raise FetchTooLargeError(
            f"{response.request.url} declares {declared} bytes, over the {MAX_FETCH_BYTES} cap."
        )
    body = bytearray()
    async for chunk in response.aiter_bytes():
        body += chunk
        if len(body) > MAX_FETCH_BYTES:
            raise FetchTooLargeError(
                f"{response.request.url} exceeds the {MAX_FETCH_BYTES} byte cap."
            )
    return bytes(body)


async def _fetch(url: str) -> Fetched:
    # Redirects are followed by hand so that every hop is re-validated: with
    # follow_redirects=True a public URL can bounce to 169.254.169.254 unchecked.
    async with httpx.AsyncClient(
        timeout=mcp_settings.request_timeout, follow_redirects=False
    ) as http:
        target = url
        for _ in range(MAX_REDIRECTS + 1):
            await _assert_public(target)
            response = await http.send(http.build_request("GET", target), stream=True)
            try:
                location = response.headers.get("location")
                if response.is_redirect and location:
                    target = str(response.url.join(location))
                    continue
                response.raise_for_status()
                return Fetched(
                    url=str(response.url),
                    content=await _read_capped(response),
                    content_type=response.headers.get("content-type"),
                    encoding=response.charset_encoding,
                )
            finally:
                await response.aclose()
        raise UnsafeUrlError(f"More than {MAX_REDIRECTS} redirects while fetching {url!r}.")


async def fetch_bytes(url: str) -> tuple[bytes, str]:
    fetched = await _fetch(url)
    return fetched.content, _filename_for(fetched.url, fetched.content_type)


def html_to_markdown(html: str) -> str:
    rendered: str = markdownify(html)
    return rendered.strip()


async def fetch_html(url: str) -> str:
    fetched = await _fetch(url)
    return fetched.content.decode(fetched.encoding or "utf-8", errors="replace")
