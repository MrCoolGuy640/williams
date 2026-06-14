# from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

import httpx

from williams.apis.youtube.exceptions import YouTubeError, AuthenticationError


CookieInput = Union[str, Path, dict[str, str]]


@dataclass
class YoutubeSession:
    """
    Authenticated YouTube session backed by browser cookies.

    Parameters
    ----------
    cookies : dict[str, str]
        Cookie name → value mapping (at minimum ``SAPISID`` or
        ``__Secure-3PAPISID`` for write operations).
    delegated_session_id : str | None
        The DELEGATED_SESSION_ID scraped from the YouTube homepage ytcfg.
        Required for accounts that use a brand/secondary channel.
        Sent as X-Goog-PageId on authenticated mutation requests.
    """

    cookies: dict[str, str] = field(default_factory=dict)
    delegated_session_id: Optional[str] = field(default=None)

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_cookies(cls, source: CookieInput) -> "YoutubeSession":
        """
        Build a session from a Netscape cookies.txt path, JSON file/dict,
        or a raw cookie header string.

        Automatically scrapes the YouTube homepage to obtain the
        DELEGATED_SESSION_ID needed for brand/secondary channel accounts.
        """
        if isinstance(source, dict):
            session = cls(cookies=dict(source))
            session._scrape_delegated_session_id()
            return session

        path = Path(source)
        if path.is_file():
            text = path.read_text(encoding="utf-8", errors="replace").strip()
            if text.startswith("{"):
                session = cls.from_json(text)
            else:
                session = cls.from_cookie_file(path)
            session._scrape_delegated_session_id()
            return session

        if isinstance(source, str) and "=" in source:
            session = cls.from_cookie_header(source)
            session._scrape_delegated_session_id()
            return session

        raise AuthenticationError(f"Cannot load cookies from {source!r}")

    @classmethod
    def from_cookie_file(cls, path: Union[str, Path]) -> "YoutubeSession":
        """Parse a Netscape-format cookies.txt file."""
        cookies: dict[str, str] = {}
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
                continue
            if "=" in line:
                name, _, value = line.partition("=")
                cookies[name.strip()] = value.strip()
        return cls(cookies=cookies)

    @classmethod
    def from_json(cls, text_or_path: Union[str, Path]) -> "YoutubeSession":
        path = Path(text_or_path)
        raw = path.read_text(encoding="utf-8") if path.is_file() else text_or_path
        data = json.loads(raw)
        if isinstance(data, list):
            cookies = {c["name"]: c["value"] for c in data if "name" in c and "value" in c}
        elif isinstance(data, dict):
            cookies = data
        else:
            raise AuthenticationError("JSON cookies must be a dict or list of cookie objects")
        return cls(cookies=cookies)

    @classmethod
    def from_cookie_header(cls, header: str) -> "YoutubeSession":
        cookies: dict[str, str] = {}
        for part in header.split(";"):
            part = part.strip()
            if "=" in part:
                name, _, value = part.partition("=")
                cookies[name.strip()] = value.strip()
        return cls(cookies=cookies)

    # ------------------------------------------------------------------
    # Delegated session ID scraping
    # ------------------------------------------------------------------

    def _scrape_delegated_session_id(self) -> None:
        """
        Fetch the YouTube homepage with our cookies and extract
        DELEGATED_SESSION_ID from ytcfg.  This is required for accounts
        where the active YouTube channel is a brand/secondary channel
        (i.e. not the primary Google account channel).

        Stored as self.delegated_session_id; sent as X-Goog-PageId.
        Silently ignored if the fetch fails — primary accounts don't need it.
        """
        if not self.is_authenticated:
            return
        try:
            r = httpx.get(
                "https://www.youtube.com/",
                headers={
                    "Cookie": self.cookie_header(),
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/124.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=15,
                allow_redirects=True,
            )
            m = re.search(r'"DELEGATED_SESSION_ID"\s*:\s*"([^"]+)"', r.text)
            if m:
                self.delegated_session_id = m.group(1)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Auth helpers
    # ------------------------------------------------------------------

    @property
    def is_authenticated(self) -> bool:
        return bool(self._sapisid_value())

    def _sapisid_value(self) -> str:
        for key in ("SAPISID", "__Secure-3PAPISID", "__Secure-1PAPISID"):
            if val := self.cookies.get(key):
                return val
        return ""

    def authorization_header(self, origin: str = "https://www.youtube.com") -> str:
        """
        Build the Authorization header value.
        Sends SAPISIDHASH, SAPISID1PHASH, and SAPISID3PHASH tokens space-separated.
        """
        ts = str(round(time.time()))

        def _make_hash(scheme: str, sid: str) -> str:
            sidhash = hashlib.sha1(f"{ts} {sid} {origin}".encode()).hexdigest()
            return f"{scheme} {ts}_{sidhash}"

        parts = []
        sapisid    = self.cookies.get("SAPISID")
        sapisid_1p = self.cookies.get("__Secure-1PAPISID")
        sapisid_3p = self.cookies.get("__Secure-3PAPISID")

        primary = sapisid or sapisid_3p
        if primary:
            parts.append(_make_hash("SAPISIDHASH", primary))
        if sapisid_1p:
            parts.append(_make_hash("SAPISID1PHASH", sapisid_1p))
        if sapisid_3p:
            parts.append(_make_hash("SAPISID3PHASH", sapisid_3p))

        if not parts:
            raise AuthenticationError(
                "No SAPISID cookie found. Export cookies while logged into YouTube."
            )
        return " ".join(parts)

    def cookie_header(self) -> str:
        return "; ".join(f"{k}={v}" for k, v in self.cookies.items())

    def require_auth(self) -> None:
        if not self.is_authenticated:
            raise AuthenticationError(
                "This operation requires a logged-in YouTube account. "
                "Pass cookies via YoutubeSession.from_cookies('cookies.txt')."
            )