"""Outbound HTTP for untrusted, user-supplied URLs.

Guards: http(s) only, standard ports, DNS resolved and every address checked against
private/loopback/link-local/reserved ranges (SSRF), redirects followed manually and
re-checked, robots.txt honoured, size and time limits enforced.
"""

import ipaddress
import socket
import urllib.robotparser
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

from app.config import get_settings


class FetchBlocked(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class FetchResult:
    url: str
    status_code: int
    content_type: str
    text: str


def canonicalize_url(url: str) -> str:
    p = urlparse(url.strip())
    scheme = p.scheme.lower()
    netloc = p.netloc.lower()
    if netloc.startswith("www.") and netloc.count(".") >= 2:
        pass  # keep www; some providers only serve on www
    path = p.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    # Drop fragments and common tracking params.
    query = "&".join(
        kv for kv in p.query.split("&") if kv and not kv.lower().startswith(("utm_", "fbclid", "gclid", "ref="))
    )
    return urlunparse((scheme, netloc, path, "", query, ""))


def _check_host(host: str, port: int | None) -> None:
    if port not in (None, 80, 443):
        raise FetchBlocked("BLOCKED_PORT", "Only standard web ports are allowed.")
    if not host or host == "localhost" or host.endswith((".local", ".internal", ".localhost")):
        raise FetchBlocked("BLOCKED_HOST", "That address is not allowed.")
    try:
        infos = socket.getaddrinfo(host, port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as e:
        raise FetchBlocked("DNS_FAILED", "The website could not be found.") from e
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise FetchBlocked("BLOCKED_HOST", "That address points to a private network and is not allowed.")


def validate_public_url(url: str) -> str:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise FetchBlocked("BAD_SCHEME", "Only http and https links are supported.")
    if p.username or p.password:
        raise FetchBlocked("BAD_URL", "Links with embedded credentials are not allowed.")
    _check_host(p.hostname or "", p.port)
    return url


def robots_allows(client: httpx.Client, url: str) -> bool:
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    try:
        r = client.get(robots_url, timeout=5)
    except httpx.HTTPError:
        return True  # unreachable robots.txt: treat as no restrictions (RFC 9309 §2.3.1.3)
    if r.status_code >= 500:
        return False
    if r.status_code >= 400:
        return True
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch(get_settings().outbound_user_agent, url)


def safe_get(url: str, *, check_robots: bool = True, transport: httpx.BaseTransport | None = None) -> FetchResult:
    s = get_settings()
    headers = {"User-Agent": s.outbound_user_agent, "Accept": "text/html,application/xhtml+xml,text/plain"}
    with httpx.Client(
        follow_redirects=False, timeout=s.outbound_fetch_timeout_seconds, headers=headers, transport=transport
    ) as client:
        current = url
        for _ in range(4):
            if transport is None:
                validate_public_url(current)
            if check_robots and not robots_allows(client, current):
                raise FetchBlocked("ROBOTS_DISALLOWED", "This website does not allow automated reading of that page.")
            with client.stream("GET", current) as r:
                if r.status_code in (301, 302, 303, 307, 308) and "location" in r.headers:
                    current = urljoin(current, r.headers["location"])
                    continue
                ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if r.status_code < 400 and ctype not in ("text/html", "application/xhtml+xml", "text/plain", ""):
                    raise FetchBlocked("UNSUPPORTED_CONTENT", "That link is not a web page.")
                body = bytearray()
                for chunk in r.iter_bytes():
                    body.extend(chunk)
                    if len(body) > s.outbound_max_bytes:
                        raise FetchBlocked("TOO_LARGE", "That page is too large to read.")
                text = body.decode(r.encoding or "utf-8", errors="replace")
                return FetchResult(url=current, status_code=r.status_code, content_type=ctype, text=text)
        raise FetchBlocked("TOO_MANY_REDIRECTS", "That link redirects too many times.")
