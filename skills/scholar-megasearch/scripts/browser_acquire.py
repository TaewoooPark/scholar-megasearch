#!/usr/bin/env python3
"""Acquire entitled PDFs through a temporary, skill-owned browser profile.

The browser uses the machine's current network path, so IP-based campus or VPN
entitlements apply automatically. It never attaches to the user's normal browser
profile, copies cookies, solves CAPTCHAs, or bypasses authentication controls.

Playwright is imported lazily so candidate extraction and the OA-only acquisition
path remain usable when the optional browser runtime is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
from urllib.parse import quote, urldefrag, urljoin, urlparse


PDF_MAGIC = b"%PDF-"
MAX_CANDIDATES = 12

_PDF_META_NAMES = {
    "citation_pdf_url",
    "eprints.document_url",
    "fulltext_pdf",
    "pdf_url",
    "wkhealth_pdf_url",
}
_PDF_PATH_MARKERS = (
    "/article-pdf/",
    "/download/pdf",
    "/doi/epdf/",
    "/doi/pdf/",
    "/epdf/",
    "/pdf/",
    "/pdfdirect/",
)
_CAPTCHA_MARKERS = (
    "captcha",
    "challenge-platform",
    "checking your browser",
    "security verification",
    "verify you are human",
)
_AUTH_MARKERS = (
    "authentication required",
    "institutional login",
    "log in to access",
    "login to access",
    "sign in to access",
)
_AUTH_URL_MARKERS = ("/login", "/saml", "openathens", "shibboleth")
_NOT_ENTITLED_MARKERS = (
    "buy this article",
    "check access",
    "get full access",
    "purchase access",
    "purchase pdf",
    "rent or buy",
    "subscribe to access",
    "you do not have access",
)


def normalize_doi(value: Any) -> str:
    """Return a bare DOI string or an empty string."""

    if not value:
        return ""
    doi = str(value).strip()
    doi = re.sub(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.I)
    return doi.strip()


def doi_url(value: Any) -> str:
    doi = normalize_doi(value)
    return f"https://doi.org/{quote(doi, safe='/')}" if doi else ""


def is_pdf_bytes(data: bytes | None) -> bool:
    """Validate a PDF by its file signature, not a server-provided MIME type."""

    return bool(data and data[:1024].lstrip().startswith(PDF_MAGIC))


def looks_like_pdf_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return False
    path = parsed.path.lower()
    query = parsed.query.lower()
    if path.endswith(".pdf") or any(marker in path for marker in _PDF_PATH_MARKERS):
        return True
    return any(
        marker in query
        for marker in (
            "download=1",
            "download=true",
            "format=pdf",
            "type=pdf",
        )
    )


class _CandidateParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.raw: list[tuple[int, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {str(key).lower(): value for key, value in attrs if value}
        tag = tag.lower()

        if tag == "meta":
            name = str(values.get("name") or values.get("property") or "").lower()
            content = values.get("content")
            if content and (name in _PDF_META_NAMES or name.endswith("pdf_url")):
                self.raw.append((0, content))

        if tag == "link":
            href = values.get("href")
            mime = str(values.get("type") or "").lower()
            if href and ("application/pdf" in mime or looks_like_pdf_url(href)):
                self.raw.append((10, href))

        for attr in ("data-pdf-url", "data-download-url", "data-href"):
            value = values.get(attr)
            if value and looks_like_pdf_url(value):
                self.raw.append((20, value))

        if tag == "a":
            href = values.get("href")
            if href and looks_like_pdf_url(href):
                self.raw.append((30, href))


def extract_pdf_candidates(html: str, base_url: str) -> list[str]:
    """Extract and rank absolute HTTP(S) PDF candidates from publisher HTML."""

    parser = _CandidateParser()
    try:
        parser.feed(html or "")
    except Exception:  # malformed publisher HTML should not abort a batch
        pass

    found: list[str] = []
    seen: set[str] = set()
    for _, raw in sorted(enumerate(parser.raw), key=lambda item: (item[1][0], item[0])):
        value = raw[1].strip()
        try:
            absolute, _ = urldefrag(urljoin(base_url, value))
            parsed = urlparse(absolute)
        except ValueError:
            continue
        if parsed.scheme not in ("http", "https") or absolute in seen:
            continue
        seen.add(absolute)
        found.append(absolute)
    return found


def classify_failure(
    text: str,
    final_url: str,
    candidate_statuses: list[int],
    *,
    saw_invalid_pdf: bool = False,
) -> str:
    """Map observable publisher state to a stable manifest status."""

    haystack = f"{final_url}\n{text}".lower()
    if any(marker in haystack for marker in _CAPTCHA_MARKERS):
        return "captcha"
    if 429 in candidate_statuses or "too many requests" in haystack:
        return "rate_limited"
    if 401 in candidate_statuses or any(
        marker in final_url.lower() for marker in _AUTH_URL_MARKERS
    ):
        return "auth_required"
    if 403 in candidate_statuses or any(marker in haystack for marker in _NOT_ENTITLED_MARKERS):
        return "not_entitled"
    if any(marker in haystack for marker in _AUTH_MARKERS):
        return "auth_required"
    if saw_invalid_pdf:
        return "invalid_pdf"
    return "failed"


def _brief_error(exc: BaseException) -> str:
    return " ".join(str(exc).split())[:500] or exc.__class__.__name__


def _auto_headless(mode: str) -> bool:
    if mode == "headless":
        return True
    if mode == "headed":
        return False
    if sys.platform in ("darwin", "win32"):
        return False
    return not bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


@dataclass
class BrowserResult:
    status: str
    data: bytes | None = None
    route: str = "institutional_browser"
    candidate_url: str | None = None
    landing_url: str | None = None
    backend: str | None = None
    headed: bool | None = None
    http_status: int | None = None
    candidate_count: int = 0
    detail: str | None = None

    def manifest_fields(self) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "status": self.status,
            "route": self.route,
            "browser_backend": self.backend,
            "browser_headed": self.headed,
            "candidate_count": self.candidate_count,
        }
        for key in ("candidate_url", "landing_url", "http_status", "detail"):
            value = getattr(self, key)
            if value is not None:
                fields[key] = value
        return fields


class BrowserAcquirer:
    """Reuse one isolated Playwright context for an unresolved DOI batch."""

    def __init__(self, *, mode: str = "auto", timeout_seconds: float = 45) -> None:
        if mode not in ("auto", "headed", "headless"):
            raise ValueError("mode must be auto, headed, or headless")
        self.mode = mode
        self.timeout_ms = max(1_000, int(timeout_seconds * 1_000))
        self.headless = _auto_headless(mode)
        self.backend: str | None = None
        self._playwright: Any = None
        self._context: Any = None
        self._profiles: tempfile.TemporaryDirectory[str] | None = None
        self._start_error: str | None = None

    def __enter__(self) -> "BrowserAcquirer":
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def start(self) -> None:
        if self._context is not None or self._start_error:
            return
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # noqa: BLE001
            self._start_error = f"Playwright import failed: {_brief_error(exc)}"
            return

        self._profiles = tempfile.TemporaryDirectory(prefix="scholar-browser-")
        errors: list[str] = []
        try:
            self._playwright = sync_playwright().start()
            backends = (
                ("chrome", {"channel": "chrome"}),
                ("msedge", {"channel": "msedge"}),
                ("chromium", {}),
            )
            for name, options in backends:
                profile = Path(self._profiles.name) / name
                try:
                    self._context = self._playwright.chromium.launch_persistent_context(
                        profile,
                        accept_downloads=True,
                        headless=self.headless,
                        timeout=self.timeout_ms,
                        **options,
                    )
                    self._context.set_default_timeout(self.timeout_ms)
                    self._context.set_default_navigation_timeout(self.timeout_ms)
                    self.backend = name
                    return
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{name}: {_brief_error(exc)}")
        except Exception as exc:  # noqa: BLE001
            errors.append(_brief_error(exc))

        self._start_error = "; ".join(errors)[:1_500] or "no supported browser could launch"
        self.close()

    def close(self) -> None:
        if self._context is not None:
            try:
                self._context.close()
            except Exception:  # noqa: BLE001
                pass
            self._context = None
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:  # noqa: BLE001
                pass
            self._playwright = None
        if self._profiles is not None:
            self._profiles.cleanup()
            self._profiles = None

    def _unavailable(self) -> BrowserResult:
        return BrowserResult(
            status="browser_unavailable",
            backend=self.backend,
            headed=not self.headless,
            detail=self._start_error or "browser did not start",
        )

    @staticmethod
    def _response_payload(response: Any) -> tuple[bytes | None, int | None, bool]:
        if response is None:
            return None, None, False
        try:
            status = int(response.status)
            headers = response.headers
            content_type = str(headers.get("content-type") or "").lower()
            url = str(response.url)
        except Exception:  # noqa: BLE001
            return None, None, False
        if status >= 400:
            return None, status, False
        if "application/pdf" not in content_type and not looks_like_pdf_url(url):
            return None, status, False
        try:
            data = response.body()
        except Exception:  # noqa: BLE001
            return None, status, "application/pdf" in content_type
        return (data if is_pdf_bytes(data) else None), status, bool(data)

    @staticmethod
    def _download_payload(downloads: list[Any]) -> tuple[bytes | None, str | None, str | None]:
        last_url: str | None = None
        last_error: str | None = None
        while downloads:
            download = downloads.pop(0)
            try:
                failure = download.failure()
                last_url = str(download.url)
                if failure:
                    last_error = str(failure)
                    continue
                path = download.path()
                data = Path(path).read_bytes()
                if is_pdf_bytes(data):
                    return data, last_url, None
                last_error = "download did not contain a PDF signature"
            except Exception as exc:  # noqa: BLE001
                last_error = _brief_error(exc)
        return None, last_url, last_error

    def acquire(self, doi: Any, *, landing_url: str | None = None) -> BrowserResult:
        """Resolve one DOI in a browser and return PDF bytes or a classified failure."""

        target = landing_url or doi_url(doi)
        if not target:
            return BrowserResult(status="no_doi", detail="record has no DOI or landing URL")
        self.start()
        if self._context is None:
            result = self._unavailable()
            result.landing_url = target
            return result

        try:
            page = self._context.new_page()
        except Exception as exc:  # noqa: BLE001
            return BrowserResult(
                status="failed",
                landing_url=target,
                backend=self.backend,
                headed=not self.headless,
                detail=_brief_error(exc),
            )
        downloads: list[Any] = []
        network_candidates: list[str] = []

        def remember_download(download: Any) -> None:
            downloads.append(download)

        page.on("download", remember_download)

        def remember_response(response: Any) -> None:
            try:
                content_type = str(response.headers.get("content-type") or "").lower()
                if "application/pdf" in content_type or looks_like_pdf_url(str(response.url)):
                    network_candidates.append(str(response.url))
            except Exception:  # noqa: BLE001
                return

        page.on("response", remember_response)
        candidate_statuses: list[int] = []
        saw_invalid_pdf = False
        detail: str | None = None
        landing_final = target
        text_parts: list[str] = []

        try:
            landing_response = page.goto(
                target, wait_until="domcontentloaded", timeout=self.timeout_ms
            )
            data, status, invalid = self._response_payload(landing_response)
            saw_invalid_pdf = saw_invalid_pdf or invalid
            if data:
                return BrowserResult(
                    status="ok",
                    data=data,
                    candidate_url=str(landing_response.url),
                    landing_url=str(landing_response.url),
                    backend=self.backend,
                    headed=not self.headless,
                    http_status=status,
                )

            page.wait_for_timeout(2_500)
            landing_final = page.url
            try:
                initial_text = page.locator("body").inner_text(timeout=2_000)[:30_000]
            except Exception:  # noqa: BLE001
                initial_text = ""
            text_parts.append(initial_text)
            try:
                title = page.title()
            except Exception:  # noqa: BLE001
                title = ""
            challenge_text = f"{title}\n{initial_text}".lower()
            if (
                any(marker in challenge_text for marker in _CAPTCHA_MARKERS)
                or "just a moment" in challenge_text
            ):
                page.wait_for_timeout(5_000)
                landing_final = page.url
                try:
                    text_parts.append(page.locator("body").inner_text(timeout=2_000)[:30_000])
                except Exception:  # noqa: BLE001
                    pass

            download_data, download_url, download_error = self._download_payload(downloads)
            if download_data:
                return BrowserResult(
                    status="ok",
                    data=download_data,
                    candidate_url=download_url,
                    landing_url=landing_final,
                    backend=self.backend,
                    headed=not self.headless,
                )
            detail = download_error or detail

            try:
                html = page.content()
            except Exception:  # noqa: BLE001
                html = ""
            candidates = network_candidates + extract_pdf_candidates(html, landing_final)
            candidates = list(dict.fromkeys(candidates))[:MAX_CANDIDATES]

            for candidate in candidates:
                # First use the browser context's cookie-aware request client. This avoids
                # brittle publisher button clicks while retaining challenge/session cookies.
                try:
                    api_response = self._context.request.get(
                        candidate,
                        headers={"Referer": landing_final},
                        fail_on_status_code=False,
                        timeout=self.timeout_ms,
                    )
                    api_url = str(api_response.url)
                    try:
                        data, status, invalid = self._response_payload(api_response)
                    finally:
                        api_response.dispose()
                    saw_invalid_pdf = saw_invalid_pdf or invalid
                    if status in (401, 403, 429):
                        candidate_statuses.append(status)
                    if data:
                        return BrowserResult(
                            status="ok",
                            data=data,
                            candidate_url=api_url,
                            landing_url=landing_final,
                            backend=self.backend,
                            headed=not self.headless,
                            http_status=status,
                            candidate_count=len(candidates),
                        )
                except Exception as exc:  # noqa: BLE001
                    detail = _brief_error(exc)

                try:
                    response = page.goto(
                        candidate,
                        referer=landing_final,
                        wait_until="domcontentloaded",
                        timeout=self.timeout_ms,
                    )
                    data, status, invalid = self._response_payload(response)
                    saw_invalid_pdf = saw_invalid_pdf or invalid
                    if status in (401, 403, 429):
                        candidate_statuses.append(status)
                    if data:
                        return BrowserResult(
                            status="ok",
                            data=data,
                            candidate_url=str(response.url),
                            landing_url=landing_final,
                            backend=self.backend,
                            headed=not self.headless,
                            http_status=status,
                            candidate_count=len(candidates),
                        )
                except Exception as exc:  # downloads commonly abort navigation
                    detail = _brief_error(exc)

                page.wait_for_timeout(500)
                download_data, download_url, download_error = self._download_payload(downloads)
                if download_data:
                    return BrowserResult(
                        status="ok",
                        data=download_data,
                        candidate_url=download_url or candidate,
                        landing_url=landing_final,
                        backend=self.backend,
                        headed=not self.headless,
                        candidate_count=len(candidates),
                    )
                detail = download_error or detail
                try:
                    text_parts.append(page.locator("body").inner_text(timeout=1_500)[:10_000])
                except Exception:  # noqa: BLE001
                    pass

            status = classify_failure(
                "\n".join(text_parts),
                page.url,
                candidate_statuses,
                saw_invalid_pdf=saw_invalid_pdf,
            )
            return BrowserResult(
                status=status,
                landing_url=landing_final,
                candidate_url=candidates[-1] if candidates else None,
                backend=self.backend,
                headed=not self.headless,
                http_status=candidate_statuses[-1] if candidate_statuses else None,
                candidate_count=len(candidates),
                detail=detail,
            )
        except Exception as exc:  # noqa: BLE001
            return BrowserResult(
                status="failed",
                landing_url=landing_final,
                backend=self.backend,
                headed=not self.headless,
                detail=_brief_error(exc),
            )
        finally:
            try:
                page.close()
            except Exception:  # noqa: BLE001
                pass
