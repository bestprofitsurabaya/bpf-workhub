"""
modules/news_scraper/scraper_engine.py

All scraping logic for the news pipeline, extracted into a standalone engine.

Contents
--------
* SSRF-safe URL validation          -> validate_url_safe()
* Commodity keyword filtering       -> CommodityKeywords / is_commodity_related()
* Multi-source scrapers             -> scrape_newsmaker(), scrape_detik_finance(),
                                       scrape_detik_article(), fetch_article_content()
* Date parsing                      -> parse_detik_date()
* RSS feed support                  -> scrape_rss_feed(), DEFAULT_RSS_FEEDS
* Rate limiting                     -> RateLimiter (5 req/min/user, in-memory)
* Progress store with TTL           -> ProgressTracker (auto-cleanup after 1 hour)

Notes on sources
----------------
MULTI-SOURCE (Newsmaker.id + Detik Finance + RSS feeds).
kontan.co.id HTML scraping removed: JS-rendered, no static HTML to scrape
(RSS feed is used instead). bisnis.com removed: 403 Forbidden, anti-bot
protection.

Politeness / rate limiting
--------------------------
Instead of a hardcoded 1s sleep between requests, an adaptive delay is used:
sleep(max(0.3, min(2.0, response_time * 0.5))) measured from the server's
actual response time.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import threading
import time
import xml.etree.ElementTree as ET
from collections import defaultdict, deque
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .scraper_logger import get_logger

logger = logging.getLogger(__name__)
_sl = get_logger()  # structured scraper logger

__all__ = [
    'validate_url_safe',
    'CommodityKeywords',
    'is_commodity_related',
    'parse_detik_date',
    'scrape_newsmaker',
    'scrape_detik_finance',
    'scrape_detik_article',
    'fetch_article_content',
    'scrape_rss_feed',
    'DEFAULT_RSS_FEEDS',
    'RateLimiter',
    'ProgressTracker',
    'rate_limiter',
    'progress_tracker',
]

# ===================================================================
# CONSTANTS
# ===================================================================

DEFAULT_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
REQUEST_TIMEOUT = 15

# Detik Finance tag URLs for commodity news
_DETIK_TAG_URLS = [
    'https://detik.com/tag/emas/',
    'https://detik.com/tag/komoditas/',
    'https://detik.com/tag/harga-emas/',
]

# Default RSS feeds (HTML scraping of these sites is blocked/unreliable)
DEFAULT_RSS_FEEDS = {
    'cnbc_indonesia': 'https://www.cnbcindonesia.com/api/rss/rssnewestcnbcindonesia',
    'kontan': 'https://kontan.co.id/feed',
}

_NEWSMAKER_BASE = 'https://www.newsmaker.id/id/news/commodity'
_NEWSMAKER_SUBCATEGORIES = ['gold', 'oil', 'silver']

_ISO_DATETIME_RE = re.compile(r'(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})')

# ===================================================================
# SSRF-SAFE URL VALIDATION
# ===================================================================

_ALLOWED_PORTS = {None, 80, 443}
_MAX_URL_LENGTH = 2048


def _ip_is_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True if the IP is globally routable (not private/loopback/etc.)."""
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def validate_url_safe(url) -> bool:
    """Return True only if ``url`` is safe to request (basic SSRF guard).

    Checks performed:
      * scheme must be http/https
      * explicit port (if any) must be 80/443
      * hostname must not be "localhost"-style
      * hostname (IP literal or DNS-resolved) must not map to loopback,
        private, link-local, reserved, multicast or unspecified addresses
        (blocks 127.0.0.1, 10.x, 192.168.x.x, 169.254.x.x cloud-metadata
        endpoints, ::1, etc.)

    Limitation: this does not defend against DNS-rebinding TOCTOU races;
    pin resolved IPs at the HTTP-client layer if that threat model applies.
    """
    if not url or not isinstance(url, str) or len(url) > _MAX_URL_LENGTH:
        return False
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme not in ('http', 'https'):
        return False

    try:
        port = parsed.port
    except ValueError:
        return False
    if port not in _ALLOWED_PORTS:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False
    if hostname.lower() in ('localhost', 'localdomain'):
        return False

    # Host is already an IP literal?
    try:
        return _ip_is_public(ipaddress.ip_address(hostname))
    except ValueError:
        pass

    # Resolve DNS: EVERY resolved address must be public.
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except OSError:
        return False
    if not addr_infos:
        return False
    for info in addr_infos:
        try:
            if not _ip_is_public(ipaddress.ip_address(info[4][0])):
                return False
        except ValueError:
            return False
    return True


# ===================================================================
# ADAPTIVE DELAY (replaces hardcoded 1s sleep)
# ===================================================================

def _adaptive_sleep(response, multiplier: float = 0.5,
                    floor: float = 0.3, ceiling: float = 2.0) -> None:
    """Sleep based on the server's measured response time.

    delay = clamp(response_time * multiplier, floor, ceiling)
    """
    try:
        response_time = response.elapsed.total_seconds()
    except Exception:
        response_time = 1.0
    time.sleep(max(floor, min(ceiling, response_time * multiplier)))


# ===================================================================
# RETRY WITH EXPONENTIAL BACKOFF
# ===================================================================

def _retry_get(url: str, sess=None, max_retries: int = 3,
               base_delay: float = 2.0, timeout: int = REQUEST_TIMEOUT) -> 'requests.Response | None':
    """GET a URL with retry + exponential backoff on failure/rate-limit.

    Retries on HTTP 429 (Too Many Requests), 5xx, and connection errors.
    Returns the successful Response, or None after all retries exhausted.
    """
    getter = (sess or requests).get
    headers = {'User-Agent': DEFAULT_UA}
    last_err = None
    for attempt in range(max_retries):
        try:
            r = getter(url, timeout=timeout, headers=headers)
            if r.status_code == 200:
                return r
            # Retry on rate-limit (429) or server errors (5xx)
            if r.status_code in (429, 500, 502, 503, 504):
                delay = base_delay * (2 ** attempt)
                # Respect Retry-After header if present
                retry_after = r.headers.get('Retry-After')
                if retry_after:
                    try: delay = max(delay, float(retry_after))
                    except ValueError: pass
                logger.warning('Retry %d/%d for %s (HTTP %d) — sleeping %.1fs',
                               attempt + 1, max_retries, url[:80], r.status_code, delay)
                time.sleep(delay)
                last_err = f'HTTP {r.status_code}'
                continue
            # Non-retryable error (400, 403, 404 etc.)
            logger.warning('Non-retryable HTTP %d for %s', r.status_code, url[:80])
            return None
        except requests.RequestException as exc:
            delay = base_delay * (2 ** attempt)
            logger.warning('Request error %d/%d for %s: %s — sleeping %.1fs',
                           attempt + 1, max_retries, url[:80], exc, delay)
            time.sleep(delay)
            last_err = str(exc)[:100]
    logger.error('All %d retries exhausted for %s: %s', max_retries, url[:80], last_err)
    return None


# ===================================================================
# COMMODITY KEYWORD FILTERING
# ===================================================================

class CommodityKeywords:
    """Keyword list used to decide whether a headline is commodity-related."""

    _COMMODITY_KEYWORDS = [
        'emas', 'gold', 'komoditas', 'komoditi', 'minyak', 'oil', 'crude',
        'silver', 'perak', 'nickel', 'nikel', 'tembaga', 'copper',
        'cpo', 'karet', 'palm oil', 'yield', 'suku bunga', 'interest rate',
        'inflasi', 'inflation', 'dollar', 'rupiah', 'forex',
    ]

    #: Public alias
    KEYWORDS = _COMMODITY_KEYWORDS

    @classmethod
    def all(cls) -> list:
        """Return a copy of the keyword list."""
        return list(cls._COMMODITY_KEYWORDS)

    @classmethod
    def is_related(cls, title: str) -> bool:
        """True if any commodity keyword appears in the title."""
        lower = (title or '').lower()
        return any(kw in lower for kw in cls._COMMODITY_KEYWORDS)

    @classmethod
    def matched(cls, title: str) -> list:
        """Return the list of keywords present in the title."""
        lower = (title or '').lower()
        return [kw for kw in cls._COMMODITY_KEYWORDS if kw in lower]


# Backwards-compatible module-level alias (used by legacy code paths)
_COMMODITY_KEYWORDS = CommodityKeywords._COMMODITY_KEYWORDS


def is_commodity_related(title: str) -> bool:
    """Check if an article title is commodity-related."""
    return CommodityKeywords.is_related(title)


# ===================================================================
# DATE PARSING
# ===================================================================

_ID_MONTHS_DETIK = {
    'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
    'mei': '05', 'jun': '06', 'jul': '07', 'agu': '08',
    'sep': '09', 'okt': '10', 'nov': '11', 'des': '12',
}


def parse_detik_date(date_text: str) -> tuple:
    """Parse Detik date format like 'Kamis, 20 Agu 2026 11:04 WIB'.

    Returns:
        (publish_date 'YYYY-MM-DD', publish_time 'HH:MM')
        Falls back to (today, '00:00') on unparsable input.
    """
    try:
        # Remove day-name prefix
        text = date_text.strip()
        if ',' in text:
            text = text.split(',', 1)[1].strip()
        # Remove timezone suffix
        for tz in [' WIB', ' WITA', ' WIT', ' GMT+7']:
            text = text.replace(tz, '')
        parts = text.strip().split()
        if len(parts) >= 3:
            day = parts[0]
            mon = _ID_MONTHS_DETIK.get(parts[1].lower(), '01')
            year = parts[2]
            time_str = parts[3].replace('.', ':') if len(parts) > 3 else '00:00'
            return f"{year}-{mon}-{day.zfill(2)}", time_str
    except Exception:
        pass
    return datetime.now().strftime('%Y-%m-%d'), '00:00'


# ===================================================================
# MULTI-SOURCE SCRAPERS
# ===================================================================

def _scrape_newsmaker_page(url: str, sess, headers: dict, seen: set) -> list:
    """Scrape articles from a single newsmaker.id page."""
    articles = []
    t0 = time.time()
    try:
        resp = _retry_get(url, sess=sess, max_retries=3, base_delay=2.0)
        elapsed_ms = int((time.time() - t0) * 1000)
        if resp is None:
            _sl.scrape_page(f'newsmaker/{url.split("/commodity")[-1][:30]}',
                            status='ERROR', items_found=0,
                            error='All retries failed', duration_ms=elapsed_ms)
            return articles
        _adaptive_sleep(resp)
        if resp.status_code != 200:
            _sl.scrape_page(f'newsmaker/{url.split("/commodity")[-1][:30]}',
                            status='ERROR', items_found=0,
                            error=f'HTTP {resp.status_code}', duration_ms=elapsed_ms)
            return articles
        soup = BeautifulSoup(resp.text, 'html.parser')
        hits = 0
        h3_tags = soup.select('h3')
        for h3 in h3_tags:
            title = h3.get_text(strip=True)[:200]
            if not title or len(title) < 10:
                continue
            card = h3.parent
            article_link = None
            for _ in range(5):
                if card is None:
                    break
                article_link = card.select_one('a[href*="/id/news/commodity/"]')
                if article_link:
                    break
                card = card.parent
            if not article_link:
                continue
            href = article_link.get('href', '')
            if not href:
                continue
            link = urljoin(_NEWSMAKER_BASE, href.strip())
            if link in seen:
                continue
            seen.add(link)
            hits += 1
            articles.append({
                'title': title,
                'link': link,
                'category': '',
                'publish_date': datetime.now().strftime('%Y-%m-%d'),
                'publish_time': '',
                'image_url': '',
                'content': None,
                'source': 'newsmaker',
            })
        _sl.scrape_page(f'newsmaker/{url.split("/commodity")[-1][:30]}',
                        status='OK', items_found=hits, duration_ms=elapsed_ms)
    except requests.RequestException as exc:
        elapsed_ms = int((time.time() - t0) * 1000)
        _sl.scrape_page(f'newsmaker/{url.split("/commodity")[-1][:30]}',
                        status='ERROR', items_found=0,
                        error=str(exc)[:200], duration_ms=elapsed_ms)
        logger.warning('newsmaker %s failed: %s', url, exc)
        time.sleep(0.5)
    return articles


def scrape_newsmaker(pages: int = 1, session=None) -> list:
    """Scrape newsmaker.id commodity pages + sub-categories.

    Crawls the main commodity page plus sub-categories (gold, oil, silver)
    to maximize article coverage.

    Args:
        pages: number of listing pages to walk per section.
        session: optional pre-configured requests.Session.

    Returns:
        List of article dicts in the standard pipeline shape.
    """
    own_session = session is None
    sess = session or requests.Session()
    headers = {'User-Agent': DEFAULT_UA}
    seen_links = set()
    all_articles = []
    _sl.scrape_start('newsmaker')

    # Build URL list: main commodity page + sub-categories
    urls = [_NEWSMAKER_BASE]
    for sub in _NEWSMAKER_SUBCATEGORIES:
        urls.append(f'{_NEWSMAKER_BASE}/{sub}')

    try:
        for url in urls:
            page_articles = _scrape_newsmaker_page(url, sess, headers, seen_links)
            all_articles.extend(page_articles)
            # Also try page 2+ if pages > 1
            for page in range(2, max(1, int(pages)) + 1):
                page_url = f'{url}?page={page}'
                extra = _scrape_newsmaker_page(page_url, sess, headers, seen_links)
                if not extra:
                    break
                all_articles.extend(extra)
    finally:
        if own_session:
            sess.close()
    _sl.scrape_done(total_articles=len(all_articles))
    return all_articles


def scrape_detik_finance(pages: int = 1) -> list:
    """Scrape Detik Finance homepage + commodity tag pages.

    Homepage headlines are keyword-filtered; tag pages are already
    commodity-specific so they are accepted as-is. Adaptive delays
    are applied between requests.

    Args:
        pages: how many pages deep to walk each tag page (?page=N).

    Returns:
        List of article dicts in the standard pipeline shape.
    """
    headers = {'User-Agent': DEFAULT_UA}
    articles = []
    seen = set()
    _sl.scrape_start('detik')

    # 1) Main finance page with keyword filter
    t0 = time.time()
    try:
        r = _retry_get('https://finance.detik.com/', max_retries=3, base_delay=2.0)
        elapsed_ms = int((time.time() - t0) * 1000)
        if r and r.status_code == 200:
            _sl.scrape_page('detik.com', status='OK', items_found=0, duration_ms=elapsed_ms)
            soup = BeautifulSoup(r.text, 'html.parser')
            for a_tag in soup.select('h2 a, h3 a'):
                title = a_tag.get_text(strip=True)[:200]
                url = a_tag.get('href', '')
                if title and url and len(title) > 10 and is_commodity_related(title):
                    if url not in seen:
                        seen.add(url)
                        articles.append({
                            'title': title, 'link': url,
                            'category': '',
                            'publish_date': datetime.now().strftime('%Y-%m-%d'),
                            'publish_time': '',
                            'image_url': '',
                            'content': None,
                            'source': 'detik_finance',
                        })
    except requests.RequestException as exc:
        elapsed_ms = int((time.time() - t0) * 1000)
        _sl.scrape_page('detik.com', status='ERROR', items_found=0,
                        error=str(exc)[:200], duration_ms=elapsed_ms)
        logger.warning('detik finance homepage failed: %s', exc)

    # 2) Tag pages for specific commodity terms (with pagination)
    total_pages = max(1, int(pages))
    for tag_url in _DETIK_TAG_URLS:
        for page in range(1, total_pages + 1):
            target = tag_url if page == 1 else f'{tag_url}?page={page}'
            try:
                r = _retry_get(target, max_retries=3, base_delay=2.0)
                if r is None or r.status_code != 200:
                    break
                soup = BeautifulSoup(r.text, 'html.parser')
                page_hits = 0
                for a_tag in soup.select('h2 a, h3 a'):
                    title = a_tag.get_text(strip=True)[:200]
                    url = a_tag.get('href', '')
                    if title and url and len(title) > 10 and url not in seen:
                        seen.add(url)
                        page_hits += 1
                        articles.append({
                            'title': title, 'link': url,
                            'category': '',
                            'publish_date': datetime.now().strftime('%Y-%m-%d'),
                            'publish_time': '',
                            'image_url': '',
                            'content': None,
                            'source': 'detik_finance',
                        })
                _sl.scrape_page(target, status='OK', items_found=page_hits, duration_ms=elapsed_ms)
                if page_hits == 0:
                    break
            except requests.RequestException as exc:
                elapsed_ms = int((time.time() - t0) * 1000)
                _sl.scrape_page(target, status='ERROR', items_found=0,
                                error=str(exc)[:200], duration_ms=elapsed_ms)
                logger.warning('detik tag %s failed: %s', target, exc)
                break
    _sl.scrape_done(total_articles=len(articles))
    return articles


def scrape_detik_article(article: dict) -> None:
    """Fetch full content for a single Detik article.

    Mutates ``article`` in place: fills ``content``, ``publish_date``,
    ``publish_time`` and ``image_url`` when missing. Always returns None.
    """
    url = article.get('link') or article.get('url') or ''
    if not url or not validate_url_safe(url):
        return
    try:
        r = requests.get(url, timeout=REQUEST_TIMEOUT,
                         headers={'User-Agent': DEFAULT_UA})
        _adaptive_sleep(r)
        if r.status_code != 200:
            return
        soup = BeautifulSoup(r.text, 'html.parser')

        # ---- body ----
        body = (
            soup.select_one('div.detail__body-text')
            or soup.select_one('div.detail_text')
            or soup.find(attrs={'itemprop': 'articleBody'})
        )
        if body:
            for junk in body.select(
                    'script, style, table, iframe, '
                    '.detail__body-tag, .paradetail'):
                junk.decompose()
            paragraphs = [p.get_text(' ', strip=True) for p in body.find_all('p')]
            text = '\n\n'.join(p for p in paragraphs if len(p) > 20)
            if len(text) >= 100 and not article.get('content'):
                article['content'] = text

        # ---- publish date/time ----
        if not article.get('publish_date') or not article.get('publish_time'):
            raw_date = ''
            date_el = soup.select_one('.detail__date') or soup.find('time')
            if date_el:
                raw_date = date_el.get('datetime') or date_el.get_text(strip=True)
            if not raw_date:
                meta = soup.find('meta', attrs={'name': 'dts:published'})
                raw_date = meta.get('content', '') if meta else ''
            if raw_date:
                iso = _ISO_DATETIME_RE.search(raw_date)
                if iso:
                    if not article.get('publish_date'):
                        article['publish_date'] = \
                            f'{iso.group(1)}-{iso.group(2)}-{iso.group(3)}'
                    if not article.get('publish_time'):
                        article['publish_time'] = f'{iso.group(4)}:{iso.group(5)}'
                else:
                    d, t = parse_detik_date(raw_date)
                    if not article.get('publish_date'):
                        article['publish_date'] = d
                    if not article.get('publish_time'):
                        article['publish_time'] = t

        # ---- hero image ----
        if not article.get('image_url'):
            og = (soup.find('meta', property='og:image')
                  or soup.find('meta', attrs={'name': 'og:image'}))
            if og and og.get('content'):
                article['image_url'] = og['content'].strip()
    except requests.RequestException as exc:
        logger.warning('scrape_detik_article failed for %s: %s', url, exc)


def fetch_article_content(article: dict, session=None) -> None:
    """Fetch & populate full article content for any supported source.

    Dispatches to the Detik-specific extractor when applicable, otherwise
    performs generic HTML extraction (article / entry-content / itemprop).
    Mutates ``article`` in place; always returns None.
    """
    source = (article.get('source') or '').lower()
    if 'detik' in source:
        scrape_detik_article(article)
        return

    url = article.get('link') or article.get('url') or ''
    if not url or not validate_url_safe(url):
        _sl.scrape_article(article.get('title', '?')[:50], url=url, error='SSRF blocked')
        return

    try:
        r = _retry_get(url, sess=session, max_retries=3, base_delay=2.0)
        if r is None:
            _sl.scrape_article(article.get('title', '?')[:50], url=url,
                               error='All retries failed')
            return
        _adaptive_sleep(r)
        if r.status_code != 200:
            _sl.scrape_article(article.get('title', '?')[:50], url=url,
                               error=f'HTTP {r.status_code}')
            return
        soup = BeautifulSoup(r.text, 'html.parser')

        # Pick the richest candidate container
        candidates = [
            soup.find('article'),
            soup.find(attrs={'itemprop': 'articleBody'}),
            soup.select_one('.detail__body-text'),
            soup.select_one('.read__content'),
            soup.select_one('.post-content'),
            soup.select_one('.entry-content'),
            soup.select_one('.prose'),
        ]
        best, best_len = None, 0
        for cand in candidates:
            if cand is None:
                continue
            length = len(cand.get_text(strip=True))
            if length > best_len:
                best, best_len = cand, length

        text = ''
        if best is not None:
            for junk in best.select('script, style, iframe, form'):
                junk.decompose()
            paragraphs = [p.get_text(' ', strip=True) for p in best.find_all('p')]
            text = '\n\n'.join(p for p in paragraphs if len(p) > 20)

        # Fallback: meta description
        if len(text) < 100:
            og_desc = (soup.find('meta', attrs={'name': 'description'})
                       or soup.find('meta', property='og:description'))
            text = og_desc.get('content', '').strip() if og_desc else ''

        if len(text) >= 100 and not article.get('content'):
            article['content'] = text
            _sl.scrape_article(article.get('title', '?')[:50], url=url,
                               word_count=len(text.split()))

        # Metadata top-ups
        if not article.get('image_url'):
            # 1) og:image meta tag
            og_img = soup.find('meta', property='og:image')
            if og_img and og_img.get('content'):
                article['image_url'] = og_img['content'].strip()

        if not article.get('image_url'):
            # 2) Fallback: find <img> with full URL whose alt matches article title
            title_lower = (article.get('title') or '').lower()
            for img in soup.select('img[src]'):
                src = img.get('src', '')
                alt = (img.get('alt') or '').lower()
                if not src or not src.startswith('http'):
                    continue
                # Skip logos, icons, avatars
                skip_words = ['logo', 'icon', 'avatar', 'favicon', 'banner', 'widget']
                if any(w in src.lower() for w in skip_words):
                    continue
                # Match by alt text or by being the first large image in article area
                if title_lower and any(w in alt for w in title_lower.split()[:3] if len(w) > 3):
                    article['image_url'] = src.strip()
                    break
            # 3) Last resort: first external <img> with class containing 'full'
            if not article.get('image_url'):
                for img in soup.select('img[src]'):
                    src = img.get('src', '')
                    cls = ' '.join(img.get('class', []))
                    if src.startswith('http') and 'full' in cls:
                        article['image_url'] = src.strip()
                        break

        if not article.get('publish_date'):
            meta_time = soup.find('meta', property='article:published_time')
            if meta_time and meta_time.get('content'):
                iso = _ISO_DATETIME_RE.search(meta_time['content'])
                if iso:
                    article['publish_date'] = \
                        f'{iso.group(1)}-{iso.group(2)}-{iso.group(3)}'
                    article['publish_time'] = f'{iso.group(4)}:{iso.group(5)}'
    except requests.RequestException as exc:
        _sl.scrape_article(article.get('title', '?')[:50], url=url,
                           error=str(exc)[:200])
        logger.warning('fetch_article_content failed for %s: %s', url, exc)


# ===================================================================
# RSS FEED SUPPORT
# ===================================================================

def _xml_local(tag) -> str:
    """Namespace-agnostic local name of an ElementTree tag."""
    if isinstance(tag, str):
        return tag.rsplit('}', 1)[-1]
    return ''


def _xml_child_text(element, name: str) -> str:
    """Text of the first direct child whose local tag name matches."""
    for child in element:
        if _xml_local(child.tag) == name:
            return (child.text or '').strip()
    return ''


def _parse_rss_pubdate(raw: str) -> tuple:
    """Normalize RFC-822 or ISO-8601 feed dates to (date, time) strings."""
    if not raw:
        return datetime.now().strftime('%Y-%m-%d'), ''
    try:
        dt = parsedate_to_datetime(raw.strip())
        return dt.strftime('%Y-%m-%d'), dt.strftime('%H:%M')
    except Exception:
        pass
    iso = _ISO_DATETIME_RE.search(raw)
    if iso:
        return (f'{iso.group(1)}-{iso.group(2)}-{iso.group(3)}',
                f'{iso.group(4)}:{iso.group(5)}')
    return datetime.now().strftime('%Y-%m-%d'), ''


def _extract_rss_image(item) -> str:
    """Pull an image URL from media:* elements or an image enclosure."""
    for child in item:
        tag = _xml_local(child.tag)
        if tag in ('content', 'thumbnail'):
            ns_uri = child.tag[1:].split('}')[0] \
                if isinstance(child.tag, str) and child.tag.startswith('{') else ''
            if 'media' in ns_uri and child.get('url'):
                return child.get('url')
        elif tag == 'enclosure':
            mime = (child.get('type') or '')
            if mime.startswith('image') and child.get('url'):
                return child.get('url')
    return ''


def scrape_rss_feed(feed_url: str, source_name: str = 'rss') -> list:
    """Scrape an RSS/Atom feed into the standard article-dict shape.

    Handles RSS 0.9x/1.0/2.0 and Atom, namespace-agnostically.
    Returns [] on any fetch/validation/parse failure.
    """
    if not feed_url or not validate_url_safe(feed_url):
        logger.warning('RSS feed rejected by SSRF guard: %s', feed_url)
        return []

    try:
        r = requests.get(feed_url, timeout=REQUEST_TIMEOUT,
                         headers={'User-Agent': DEFAULT_UA})
        _adaptive_sleep(r)
        if r.status_code != 200:
            logger.warning('RSS %s -> HTTP %s', feed_url, r.status_code)
            return []
        root = ET.fromstring(r.content)
    except (requests.RequestException, ET.ParseError) as exc:
        logger.warning('RSS fetch/parse failed for %s: %s', feed_url, exc)
        return []

    items = [el for el in root.iter()
             if _xml_local(el.tag) in ('item', 'entry')]

    articles = []
    for item in items[:50]:
        title = _xml_child_text(item, 'title')
        link = _xml_child_text(item, 'link')
        if not link:
            # Atom puts the URL in an href attribute
            for child in item:
                if _xml_local(child.tag) == 'link':
                    link = (child.get('href') or '').strip()
                    if link:
                        break
        if not title or not link:
            continue

        pub_raw = (_xml_child_text(item, 'pubDate')
                   or _xml_child_text(item, 'published')
                   or _xml_child_text(item, 'updated'))
        publish_date, publish_time = _parse_rss_pubdate(pub_raw)

        articles.append({
            'title': title[:200],
            'link': link,
            'category': '',
            'publish_date': publish_date,
            'publish_time': publish_time,
            'image_url': _extract_rss_image(item),
            'content': None,
            'source': source_name,
        })
    return articles


# ===================================================================
# RATE LIMITING (in-memory, sliding window)
# ===================================================================

class RateLimiter:
    """Sliding-window rate limiter: MAX_REQUESTS per WINDOW_SECONDS per user.

    Purely in-memory (per-process); suitable for a single-worker deployment.
    """

    MAX_REQUESTS = 5
    WINDOW_SECONDS = 60

    def __init__(self, max_requests: int = MAX_REQUESTS,
                 window_seconds: float = WINDOW_SECONDS):
        self._max = max_requests
        self._window = window_seconds
        self._hits = defaultdict(deque)  # user_id -> deque[timestamps]
        self._lock = threading.Lock()

    def check(self, user_id) -> bool:
        """Record a hit for ``user_id``; return False if over the limit."""
        now = time.monotonic()
        with self._lock:
            dq = self._hits[user_id]
            while dq and now - dq[0] > self._window:
                dq.popleft()
            if len(dq) >= self._max:
                retry_after = int(self._window - (now - dq[0])) if dq else int(self._window)
                _sl.rate_limit_hit(service=str(user_id), retry_after=retry_after)
                return False
            dq.append(now)
            return True

    def reset(self, user_id=None) -> None:
        """Clear history for one user (or everyone if user_id is None)."""
        with self._lock:
            if user_id is None:
                self._hits.clear()
            else:
                self._hits.pop(user_id, None)


#: Shared instance for the app to use
rate_limiter = RateLimiter()


# ===================================================================
# PROGRESS STORE WITH TTL (in-memory)
# ===================================================================

class ProgressTracker:
    """In-memory task-progress store with automatic TTL cleanup.

    Entries older than TTL_SECONDS (default 1 hour) are purged lazily
    on every set/get/clear call, so finished/stale tasks never leak.
    """

    TTL_SECONDS = 3600

    def __init__(self, ttl_seconds: float = TTL_SECONDS):
        self._ttl = ttl_seconds
        self._tasks = {}  # task_id -> {'_ts': epoch, **data}
        self._lock = threading.Lock()

    # -- internals ---------------------------------------------------

    def _cleanup_locked(self, now: float) -> None:
        """Drop expired tasks. Caller must hold the lock."""
        expired = [task_id for task_id, entry in self._tasks.items()
                   if now - entry.get('_ts', 0) > self._ttl]
        for task_id in expired:
            del self._tasks[task_id]

    # -- public API ----------------------------------------------------

    def set(self, task_id, data: dict = None, **fields) -> None:
        """Create/replace the progress entry for ``task_id``."""
        payload = dict(data or {})
        payload.update(fields)
        with self._lock:
            self._cleanup_locked(time.time())
            payload['_ts'] = time.time()
            self._tasks[task_id] = payload

    def get(self, task_id):
        """Return a copy of the task's data (without bookkeeping keys),
        or None if unknown/expired."""
        with self._lock:
            self._cleanup_locked(time.time())
            entry = self._tasks.get(task_id)
            if entry is None:
                return None
            snapshot = {k: v for k, v in entry.items() if k != '_ts'}
            return snapshot

    def clear(self, task_id=None) -> None:
        """Remove one task (or all tasks if task_id is None)."""
        with self._lock:
            self._cleanup_locked(time.time())
            if task_id is None:
                self._tasks.clear()
            else:
                self._tasks.pop(task_id, None)

    def active_count(self) -> int:
        """Number of live (non-expired) tracked tasks."""
        with self._lock:
            self._cleanup_locked(time.time())
            return len(self._tasks)


#: Shared instance for the app to use
progress_tracker = ProgressTracker()
