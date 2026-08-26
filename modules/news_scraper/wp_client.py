"""WordPress REST API client for the news scraper.

Provides :class:`WpClient`, a thin wrapper around the WordPress REST API
(application-password auth + nonce-based requests), and :func:`get_wp_session`,
a pre-configured ``requests.Session`` with automatic retries.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from typing import Any
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from requests.models import Response
from urllib3.util.retry import Retry

__all__ = ["WpClient", "get_wp_session"]

logger = logging.getLogger(__name__)

MAX_IMAGE_SIZE: int = 10 * 1024 * 1024  # 10 MB hard limit
DOWNLOAD_CHUNK_SIZE: int = 64 * 1024
DEFAULT_TIMEOUT: float = 30.0


def get_wp_session() -> requests.Session:
    """Return a ``requests.Session`` configured with retries and back-off."""
    session = requests.Session()
    retry = Retry(
        total=3,
        connect=3,
        read=3,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"}),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


class WpClient:
    """Client for a WordPress site's REST API (``/wp-json/wp/v2``)."""

    def __init__(self, wp_url: str, username: str, app_password: str) -> None:
        self.wp_url: str = wp_url.rstrip("/")
        self.username: str = username
        self.app_password: str = app_password
        self.session: requests.Session = get_wp_session()
        self._tag_cache: dict[str, int] = {}

    # ------------------------------------------------------------------ #
    # Authentication
    # ------------------------------------------------------------------ #

    def login(self) -> tuple[bool, str]:
        """Validate credentials against ``/users/me``. Returns ``(ok, message)``."""
        url = f"{self.wp_url}/wp-json/wp/v2/users/me"
        try:
            resp = self.session.get(
                url, auth=(self.username, self.app_password), timeout=DEFAULT_TIMEOUT
            )
        except requests.RequestException as exc:
            logger.error("Login request failed: %s", exc)
            return False, f"Connection error: {exc}"

        if resp.status_code == 200:
            logger.info("Logged in to %s as %s", self.wp_url, self.username)
            return True, "Login successful"
        msg = f"Login failed (HTTP {resp.status_code}): {resp.text[:200]}"
        logger.error(msg)
        return False, msg

    # ------------------------------------------------------------------ #
    # Generic request helper
    # ------------------------------------------------------------------ #

    def request(self, method: str, url: str, nonce: str, **kwargs: Any) -> Response:
        """Perform an authenticated REST request carrying the WP nonce header."""
        headers = kwargs.pop("headers", None) or {}
        headers.setdefault("X-WP-Nonce", nonce)
        kwargs.setdefault("timeout", DEFAULT_TIMEOUT)
        kwargs.setdefault("auth", (self.username, self.app_password))
        return self.session.request(method, url, headers=headers, **kwargs)

    # ------------------------------------------------------------------ #
    # Media
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_safe_url(url: str) -> bool:
        """SSRF guard: only public http(s) hosts are allowed.

        Resolves every address the hostname maps to and rejects private,
        loopback, link-local, reserved, multicast and unspecified targets.
        (Note: this does not fully protect against DNS-rebinding attacks.)
        """
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        try:
            addr_infos = socket.getaddrinfo(hostname, None)
        except socket.gaierror as exc:
            logger.warning("Could not resolve host %r: %s", hostname, exc)
            return False
        for info in addr_infos:
            try:
                ip = ipaddress.ip_address(info[4][0])
            except ValueError:
                return False
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_reserved
                or ip.is_multicast
                or ip.is_unspecified
            ):
                logger.warning("Blocked URL pointing at non-public address: %s", url)
                return False
        return True

    def upload_image(self, url: str, nonce: str) -> dict[str, Any] | None:
        """Download an image from ``url`` and upload it to the WP media library.

        Enforces an SSRF check and a 10 MB size limit (both via the
        ``Content-Length`` header and while streaming the body).
        Returns the created attachment dict, or ``None`` on failure.
        """
        if not self._is_safe_url(url):
            logger.warning("Refusing unsafe image URL: %s", url)
            return None

        try:
            with self.session.get(url, stream=True, timeout=DEFAULT_TIMEOUT) as resp:
                resp.raise_for_status()
                content_type = resp.headers.get("Content-Type", "image/jpeg")

                length_header = resp.headers.get("Content-Length")
                if length_header and int(length_header) > MAX_IMAGE_SIZE:
                    logger.warning("Image too large (%s bytes): %s", length_header, url)
                    return None

                chunks: list[bytes] = []
                downloaded = 0
                for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    downloaded += len(chunk)
                    if downloaded > MAX_IMAGE_SIZE:
                        logger.warning(
                            "Image exceeds %d byte limit: %s", MAX_IMAGE_SIZE, url
                        )
                        return None
                    chunks.append(chunk)
        except (requests.RequestException, ValueError) as exc:
            logger.error("Failed to download image %s: %s", url, exc)
            return None

        payload = b"".join(chunks)
        filename = os.path.basename(urlparse(url).path) or "image.jpg"
        files = {"file": (filename, payload, content_type)}

        resp = self.request(
            "POST", f"{self.wp_url}/wp-json/wp/v2/media", nonce, files=files, timeout=120
        )
        if resp.status_code in (200, 201):
            data: dict[str, Any] = resp.json()
            logger.info("Uploaded media id=%s from %s", data.get("id"), url)
            return data
        logger.error(
            "Media upload failed (HTTP %d): %s", resp.status_code, resp.text[:300]
        )
        return None

    # ------------------------------------------------------------------ #
    # Posts
    # ------------------------------------------------------------------ #

    def create_post(self, data: dict[str, Any], nonce: str) -> Response:
        """Create a new post. ``data`` follows the WP REST post schema."""
        return self.request(
            "POST", f"{self.wp_url}/wp-json/wp/v2/posts", nonce, json=data
        )

    def update_post(self, post_id: int, data: dict[str, Any], nonce: str) -> Response:
        """Update an existing post by ID."""
        return self.request(
            "POST", f"{self.wp_url}/wp-json/wp/v2/posts/{post_id}", nonce, json=data
        )

    def get_posts(self, nonce: str, params: dict[str, Any] | None = None) -> Response:
        """Fetch posts; ``params`` are passed straight through as query args."""
        return self.request(
            "GET", f"{self.wp_url}/wp-json/wp/v2/posts", nonce, params=params or {}
        )

    # ------------------------------------------------------------------ #
    # Tags
    # ------------------------------------------------------------------ #

    def get_or_create_tag(self, name: str, nonce: str) -> int | None:
        """Return the numeric ID of tag ``name``, creating it if missing.

        Results are cached per client instance. Returns ``None`` on failure.
        """
        name = name.strip()
        if not name:
            return None
        if name in self._tag_cache:
            return self._tag_cache[name]

        # 1) Search for an existing tag (case-insensitive match).
        search = self.request(
            "GET",
            f"{self.wp_url}/wp-json/wp/v2/tags",
            nonce,
            params={"search": name, "per_page": 100},
        )
        if search.ok:
            for tag in search.json():
                if str(tag.get("name", "")).lower() == name.lower():
                    tag_id = int(tag["id"])
                    self._tag_cache[name] = tag_id
                    return tag_id

        # 2) Create the tag.
        created = self.request(
            "POST", f"{self.wp_url}/wp-json/wp/v2/tags", nonce, json={"name": name}
        )
        if created.status_code in (200, 201):
            tag_id = int(created.json()["id"])
            self._tag_cache[name] = tag_id
            logger.debug("Created tag %r -> id=%d", name, tag_id)
            return tag_id

        # 3) Handle race condition: WP returns 400 term_exists if another
        #    request created the tag in the meantime.
        try:
            err = created.json()
            if err.get("code") == "term_exists":
                tag_id = int(err["data"]["term_id"])
                self._tag_cache[name] = tag_id
                return tag_id
        except (ValueError, KeyError, TypeError):
            pass

        logger.error(
            "Failed to create tag %r (HTTP %d): %s",
            name,
            created.status_code,
            created.text[:200],
        )
        return None
