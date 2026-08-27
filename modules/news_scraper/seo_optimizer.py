"""
modules/news_scraper/seo_optimizer.py

All SEO / backlink / schema / content-uniqueness / internal-linking /
analytics / caching logic for the BPFWorkHub news scraper pipeline.

Sections:
    1. Constants          - authority sites, keyword mapping, anchor variations
    2. Backlinks          - apply_backlinks(), get_anchor_text()
    3. Article HTML       - build_article_html(), build_bpf_cta_widget()
    4. Schema             - build_advanced_schema()  (JSON-LD)
    5. Sitemap & Timing   - ping_sitemap(), get_optimal_publish_time(),
                            should_publish_today()
    6. Content Uniqueness - rewrite_content(), normalize_title()
    7. Internal Linking   - auto_internal_links()
    8. Analytics          - track_performance(), get_analytics()
    9. Caching            - JsonCache (file-based, TTL 30s)
   10. SEO Analysis       - seo_analyze()

All data-file paths are sourced from ``modules/news_scraper/__init__.py``
constants (with safe fallbacks for standalone execution).
"""

import hashlib
import json
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta
from html import escape as _esc
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import quote as _url_quote

import requests

# -------------------------------------------------------------------
# Data-file paths from package __init__.py (with standalone fallbacks)
# -------------------------------------------------------------------
try:
    from . import (  # type: ignore
        CACHE_DIR,
        CACHE_TTL_SECONDS,
        SEO_ANALYTICS_FILE,
    )
except ImportError:  # pragma: no cover - standalone execution fallback
    _MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
    _DATA_DIR = os.path.join(_MODULE_DIR, 'data')
    CACHE_DIR = os.path.join(_DATA_DIR, 'cache')
    CACHE_TTL_SECONDS = 30
    SEO_ANALYTICS_FILE = os.path.join(_DATA_DIR, 'seo_analytics.json')

__all__ = [
    'DEFAULT_AUTHORITY_SITES',
    'DEFAULT_KEYWORD_MAPPING',
    'ANCHOR_TEXT_VARIATIONS',
    'apply_backlinks',
    'get_anchor_text',
    'build_article_html',
    'build_bpf_cta_widget',
    'seo_analyze',
    'build_advanced_schema',
    'ping_sitemap',
    'get_optimal_publish_time',
    'should_publish_today',
    'rewrite_content',
    'normalize_title',
    'auto_internal_links',
    'track_performance',
    'get_analytics',
    'JsonCache',
]

# ===================================================================
# 1. CONSTANTS
# ===================================================================

#: Authority sites available for backlinking (BPF internal + external trust sites).
DEFAULT_AUTHORITY_SITES: Dict[str, str] = {
    # --- BPF internal properties ---
    'PT BESTPROFIT FUTURES': 'https://bestprofit-futures.co.id/',
    'BESTPROFIT Trading': 'https://bestprofit-futures.co.id/trading',
    'BESTPROFIT E-Trade': 'https://etrade.bestprofit-futures.com/',
    'BESTPROFIT Demo': 'https://demo.bestprofit-futures.com/',
    'BESTPROFIT Platform': 'https://bestprofit-futures.co.id/platform',
    # --- External financial authority sites ---
    'Bank Indonesia': 'https://www.bi.go.id/',
    'Bappebti': 'https://bappebti.go.id/',
    'OJK': 'https://ojk.go.id/',
    'Reuters': 'https://www.reuters.com/',
    'Bloomberg': 'https://www.bloomberg.com/',
    'CNBC Indonesia': 'https://www.cnbcindonesia.com/',
    'Investing.com': 'https://www.investing.com/',
    'Trading Economics': 'https://tradingeconomics.com/',
}

#: Keyword -> authority-site-name mapping used to detect backlink opportunities.
DEFAULT_KEYWORD_MAPPING: Dict[str, str] = {
    # --- BPF internal ---
    'bestprofit futures': 'PT BESTPROFIT FUTURES',
    'pt bestprofit futures': 'PT BESTPROFIT FUTURES',
    'broker berjangka': 'BESTPROFIT Trading',
    'trading komoditas': 'BESTPROFIT Trading',
    'platform trading': 'BESTPROFIT Platform',
    'platform terpercaya': 'BESTPROFIT Platform',
    'akun demo': 'BESTPROFIT Demo',
    'demo gratis': 'BESTPROFIT Demo',
    'coba demo': 'BESTPROFIT Demo',
    'e-trade': 'BESTPROFIT E-Trade',
    'online trading': 'BESTPROFIT E-Trade',
    'trading online': 'BESTPROFIT E-Trade',
    # --- External authorities ---
    'bank indonesia': 'Bank Indonesia',
    'bi rate': 'Bank Indonesia',
    'bank sentral': 'Bank Indonesia',
    'bappebti': 'Bappebti',
    'badan pengawas perdagangan berjangka': 'Bappebti',
    'ojk': 'OJK',
    'otoritas jasa keuangan': 'OJK',
    'reuters': 'Reuters',
    'bloomberg': 'Bloomberg',
    'cnbc indonesia': 'CNBC Indonesia',
    'investing.com': 'Investing.com',
    'trading economics': 'Trading Economics',
}

#: Anchor-text variations to keep backlink profiles natural.
ANCHOR_TEXT_VARIATIONS: Dict[str, List[str]] = {
    'bestprofit futures': [
        'PT Bestprofit Futures',
        'Bestprofit Futures',
        'broker Bestprofit Futures',
        'Bestprofit Futures Bappebti',
    ],
    'broker berjangka': [
        'broker berjangka resmi',
        'broker futures terpercaya',
        'perusahaan berjangka',
    ],
    'platform trading': [
        'platform trading',
        'aplikasi trading',
        'platform transaksi',
    ],
    'akun demo': [
        'akun demo gratis',
        'akun latihan trading',
        'demo account',
    ],
    'e-trade': [
        'E-Trade',
        'trading online',
        'platform e-trading',
    ],
    'bank indonesia': [
        'Bank Indonesia',
        'BI',
        'bank sentral RI',
    ],
    'bappebti': [
        'Bappebti',
        'Badan Pengawas Perdagangan Berjangka Komoditi',
    ],
    'ojk': [
        'OJK',
        'Otoritas Jasa Keuangan',
    ],
    'reuters': [
        'Reuters',
        'kantor berita Reuters',
    ],
    'bloomberg': [
        'Bloomberg',
        'Bloomberg Finance',
    ],
    'cnbc indonesia': [
        'CNBC Indonesia',
        'CNBC',
    ],
    'investing.com': [
        'Investing.com',
        'Investing',
    ],
    'trading economics': [
        'Trading Economics',
        'data Trading Economics',
    ],
}

#: Publishing policy constants.
MAX_POSTS_PER_DAY = 3                 # daily publishing cap
MIN_PUBLISH_GAP_MINUTES = 90          # minimum gap between posts (minutes)
OPTIMAL_SLOTS_WIB = [(8, 30), (12, 30), (19, 0)]  # pre-open / lunch / evening

_LOCK = threading.Lock()


# ===================================================================
# SHARED JSON FILE HELPERS
# ===================================================================

def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _load_json(path: str, default: Any) -> Any:
    try:
        with open(path, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        return default


def _save_json(path: str, data: Any) -> bool:
    """Atomic JSON write (tmp file + os.replace)."""
    _ensure_parent_dir(path)
    tmp_path = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp_path, 'w', encoding='utf-8') as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp_path, path)
        return True
    except OSError:
        return False


# ===================================================================
# 2. BACKLINKS
# ===================================================================
def seo_analyze(html_content: str, title: str = '') -> Dict[str, Any]:
    """Analyse HTML content for basic SEO signals and return a score.

    Scoring breakdown (0–100):
        - Title presence & length          15 pts
        - Heading tags (h1, h2, h3)        15 pts
        - Paragraph count                  10 pts
        - Content length (word count)      20 pts
        - Image presence                    5 pts
        - Meta keywords (inline)            5 pts
        - Link presence (backlinks)         5 pts
        - Structured data (schema)         10 pts
        - Title-in-content keyword match   10 pts
        - Readability (avg sentence len)     5 pts

    Returns:
        dict with keys: seo_score (int 0-100), details (dict), suggestions (list)
    """
    details: Dict[str, Any] = {}
    suggestions: List[str] = []
    score = 0
    text_only = re.sub(r'<[^>]+>', ' ', html_content or '')
    text_only = re.sub(r'\s+', ' ', text_only).strip()
    words = text_only.split()

    # 1. Title presence & length (15 pts)
    title_len = len(title or '')
    if title_len > 0:
        score += 5
        if 30 <= title_len <= 70:
            score += 10
            details['title'] = 'optimal'
        elif title_len < 30:
            score += 3
            details['title'] = 'too_short'
            suggestions.append('Judul terlalu pendek (ideal: 30-70 karakter)')
        else:
            score += 5
            details['title'] = 'too_long'
            suggestions.append('Judul terlalu panjang (ideal: 30-70 karakter)')
    else:
        suggestions.append('Judul kosong — wajib diisi untuk SEO')

    # 2. Heading tags (15 pts)
    h1_count = len(re.findall(r'<h1[\s>]', html_content, re.I))
    h2_count = len(re.findall(r'<h2[\s>]', html_content, re.I))
    h3_count = len(re.findall(r'<h3[\s>]', html_content, re.I))
    details['headings'] = {'h1': h1_count, 'h2': h2_count, 'h3': h3_count}
    if h1_count >= 1:
        score += 5
    if h2_count >= 1:
        score += 5
    if h3_count >= 1:
        score += 5
    if h1_count == 0:
        suggestions.append('Tambahkan tag <h1> untuk judul utama')

    # 3. Paragraph count (10 pts)
    para_count = len(re.findall(r'<p[\s>]', html_content, re.I))
    details['paragraphs'] = para_count
    if para_count >= 5:
        score += 10
    elif para_count >= 3:
        score += 6
    elif para_count >= 1:
        score += 3
    else:
        suggestions.append('Tambahkan lebih banyak paragraf (minimal 5)')

    # 4. Content length (20 pts)
    word_count = len(words)
    details['word_count'] = word_count
    if word_count >= 600:
        score += 20
    elif word_count >= 300:
        score += 15
    elif word_count >= 150:
        score += 10
    elif word_count >= 50:
        score += 5
    else:
        suggestions.append('Konten terlalu pendek (ideal: 600+ kata)')

    # 5. Image presence (5 pts)
    img_count = len(re.findall(r'<img[\s>]', html_content, re.I))
    details['images'] = img_count
    if img_count >= 1:
        score += 5
    else:
        suggestions.append('Tambahkan minimal 1 gambar untuk engagement lebih baik')

    # 6. Inline meta keywords (5 pts)
    has_meta_kw = bool(re.search(r'keywords', html_content, re.I)) or bool(
        re.search(r'\b(seo|keyword|tag)\b', html_content, re.I)
    )
    if has_meta_kw:
        score += 5

    # 7. Link presence (5 pts)
    link_count = len(re.findall(r'<a[\s>]', html_content, re.I))
    details['links'] = link_count
    if link_count >= 1:
        score += 5

    # 8. Structured data / schema (10 pts)
    schema_count = html_content.count('application/ld+json')
    details['schemas'] = schema_count
    if schema_count >= 1:
        score += 10
    else:
        suggestions.append('Tambahkan JSON-LD structured data untuk rich snippets')

    # 9. Title keyword in content (10 pts)
    if title and words:
        title_words = set(w.lower() for w in re.findall(r'[a-z]{4,}', title.lower()))
        content_words_lower = ' '.join(words[:500]).lower()
        matched = sum(1 for tw in title_words if tw in content_words_lower)
        ratio = matched / max(len(title_words), 1)
        details['keyword_density'] = round(ratio, 2)
        if ratio >= 0.5:
            score += 10
        elif ratio >= 0.3:
            score += 6
        elif ratio >= 0.1:
            score += 3
        else:
            suggestions.append('Kata kunci judul kurang muncul di konten')

    # 10. Readability — avg sentence length (5 pts)
    sentences = re.split(r'[.!?]+', text_only)
    sentences = [s.strip() for s in sentences if s.strip()]
    if sentences:
        avg_len = sum(len(s.split()) for s in sentences) / len(sentences)
        details['avg_sentence_words'] = round(avg_len, 1)
        if avg_len <= 25:
            score += 5
        elif avg_len <= 35:
            score += 3
        else:
            suggestions.append('Kalimat terlalu panjang — pecah untuk readability')

    score = min(score, 100)
    return {'seo_score': score, 'details': details, 'suggestions': suggestions}


def get_anchor_text(keyword: str) -> str:
    """Pick a natural-sounding anchor variation for a matched keyword."""
    kw = keyword.lower()
    for base, variations in ANCHOR_TEXT_VARIATIONS.items():
        if base in kw:
            return random.choice(variations)
    return keyword


def apply_backlinks(
    content: str,
    title: str,
    authority_sites: Dict[str, str],
    keyword_mapping: Dict[str, str],
    max_backlinks: int = 3,
) -> Tuple[str, List[str]]:
    """Add financial authority backlinks + BPF CTA to content.

    Split budget: ~2/3 internal BPF links, remainder external authority
    links (default max_backlinks=3 -> 2 internal + 1 external).

    Returns:
        (updated_html_content, list_of_"anchor → site" descriptions)
    """
    used: List[str] = []
    combined = (title + " " + content).lower()

    # Split: BPF internal keywords vs external authority keywords
    bpf_sites = {'PT BESTPROFIT FUTURES', 'BESTPROFIT Trading', 'BESTPROFIT E-Trade',
                 'BESTPROFIT Demo', 'BESTPROFIT Platform'}
    matched_bpf: List[Tuple[str, str]] = []
    matched_ext: List[Tuple[str, str]] = []
    for kw, site_name in keyword_mapping.items():
        if kw.lower() in combined:
            if site_name in bpf_sites:
                matched_bpf.append((kw, site_name))
            else:
                matched_ext.append((kw, site_name))

    internal_budget = max(1, min(2, max_backlinks))
    external_budget = max(0, max_backlinks - internal_budget)

    # Insert internal BPF backlinks
    random.shuffle(matched_bpf)
    for kw, site_name in matched_bpf[:internal_budget]:
        if site_name in authority_sites:
            url = authority_sites[site_name]
            anchor = get_anchor_text(kw)
            pattern = r'\b' + re.escape(kw) + r'\b(?![^<]*>)'
            content = re.sub(
                pattern,
                f'<a href="{url}" target="_blank" rel="nofollow sponsored">{anchor}</a>',
                content, count=1, flags=re.IGNORECASE,
            )
            used.append(f"{anchor} → {site_name}")

    # Insert external authority backlinks
    random.shuffle(matched_ext)
    for kw, site_name in matched_ext[:external_budget]:
        if site_name in authority_sites:
            url = authority_sites[site_name]
            anchor = get_anchor_text(kw)
            pattern = r'\b' + re.escape(kw) + r'\b(?![^<]*>)'
            content = re.sub(
                pattern,
                f'<a href="{url}" target="_blank" rel="nofollow">{anchor}</a>',
                content, count=1, flags=re.IGNORECASE,
            )
            used.append(f"{anchor} → {site_name}")

    # Add BPF CTA sidebar widget at bottom of article
    cta_html = build_bpf_cta_widget()
    content = content + cta_html

    # Inject internal links to linkable pages (kalkulator & glossarium)
    content = _inject_linkable_page_links(content)

    return content, used


def _inject_linkable_page_links(content: str) -> str:
    """Add contextual internal links to linkable pages at end of article.

    These pages are designed to attract backlinks (kalkulator emas, glossarium).
    Linking from every article boosts their authority and helps them rank.
    """
    wp_base = 'https://best-profit-futures-surabaya.com'
    links = []

    # Link to kalkulator emas if article mentions emas/gold
    if any(w in content.lower() for w in ['emas', 'gold', 'harga emas', 'antam', 'logam mulia']):
        links.append(
            f'<a href="{wp_base}/kalkulator-emas/" target="_blank">'
            f'Kalkulator Emas</a>'
        )

    # Link to glossarium if article mentions trading terms
    if any(w in content.lower() for w in ['trading', 'forex', 'saham', 'komoditas', 'investasi']):
        links.append(
            f'<a href="{wp_base}/glossarium-trading/" target="_blank">'
            f'Glossarium Trading</a>'
        )

    if links:
        links_html = ' &bull; '.join(links)
        content += (
            f'<div style="margin-top:20px;padding:12px;background:#f8fafc;'
            f'border:1px solid #e2e8f0;border-radius:8px;font-size:13px;'
            f'color:#475569;">'
            f'📖 Baca juga: {links_html}</div>\n'
        )
    return content


# ===================================================================
# 3. ARTICLE HTML
# ===================================================================

def build_article_html(title: str, content: str, article: Dict[str, Any],
                       publish_date: str, publish_time: str) -> str:
    """Build professional article HTML with proper structure.

    Escapes user-controlled content to prevent HTML injection / stored XSS.
    """
    # Split content into paragraphs
    paragraphs = content.split('\n') if content else []
    paragraphs = [p.strip() for p in paragraphs if p.strip()]
    if not paragraphs:
        paragraphs = [content] if content else []

    # Build article body with proper paragraph tags
    body_paragraphs = ''
    for i, para in enumerate(paragraphs):
        # Add subheading every 3 paragraphs
        if i > 0 and i % 3 == 0 and len(para) > 50:
            words = para.split()[:6]
            subheading = ' '.join(words)
            if len(subheading) > 10:
                body_paragraphs += f'<h2>{_esc(subheading)}</h2>'
        body_paragraphs += f'<p>{_esc(para)}</p>'

    # Category badge
    category = article.get('category', '')
    category_badge = ''
    if category:
        category_badge = (
            f'<span style="display:inline-block;padding:4px 12px;background:#e0e7ff;'
            f'color:#3730a3;border-radius:20px;font-size:12px;font-weight:600;'
            f'margin-bottom:12px;">{_esc(category)}</span>'
        )

    # Date & source info
    raw_source = article.get('source', 'newsmaker')
    source_map = {
        'newsmaker': 'Newsmaker.id',
        'detik': 'Detik Finance',
        'detik_finance': 'Detik Finance',
        'detik_tag': 'Detik Finance',
    }
    source_name = source_map.get(raw_source, raw_source.title())
    source_url = article.get('link', '')
    # Escape URL for href attribute safety
    safe_url = _esc(source_url, quote=True) if source_url else ''
    source_link = (
        f'<a href="{safe_url}" target="_blank" rel="nofollow noopener" '
        f'style="color:#6b7280;">{_esc(source_name)}</a>'
        if source_url else _esc(source_name)
    )

    # Calculate reading time
    word_count = len(content.split())
    reading_time = max(1, round(word_count / 200))  # 200 wpm avg

    # Generate Table of Contents from H2 tags in body
    import re as _re
    toc_items = []
    for m in _re.finditer(r'<h2[^>]*>(.*?)</h2>', body_paragraphs):
        heading_text = _re.sub(r'<[^>]+>', '', m.group(1)).strip()
        if heading_text and len(heading_text) > 3:
            toc_id = _re.sub(r'[^a-z0-9]+', '-', heading_text.lower()).strip('-')
            toc_items.append((toc_id, heading_text))
            body_paragraphs = body_paragraphs.replace(
                m.group(0),
                m.group(0).replace('<h2>', f'<h2 id="{toc_id}">').replace('<h2 ', f'<h2 id="{toc_id}" '),
                1
            )

    toc_html = ''
    if len(toc_items) > 2:
        toc_li = '\n'.join(
            f'<li style="margin:4px 0;"><a href="#{{}}" style="color:#475569;text-decoration:none;font-size:13px;">{{}}</a></li>'.format(tid, ttext)
            for tid, ttext in toc_items
        )
        toc_html = f'''
<div class="bpf-toc" style="margin-bottom:24px;padding:16px 20px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;">
  <div onclick="this.parentElement.classList.toggle('bpf-toc-collapsed')" style="cursor:pointer;display:flex;align-items:center;justify-content:space-between;">
    <strong style="font-size:14px;color:#1e3a5f;">📑 Daftar Isi</strong>
    <span style="font-size:12px;color:#94a3b8;">▼</span>
  </div>
  <ul style="margin:12px 0 0;padding-left:20px;list-style:disc;">
    {toc_li}
  </ul>
</div>'''

    # Social share URL encoding
    import urllib.parse as _url
    page_url = article.get('link', '')
    encoded_url = _url.quote(page_url) if page_url else ''
    encoded_title = _url.quote(title) if title else ''

    html = f'''
<!-- Reading Progress Bar -->
<div id="bpf-progress" style="position:fixed;top:0;left:0;height:3px;background:linear-gradient(90deg,#1e3a5f,#c8a951);z-index:9999;width:0%;transition:width .1s;"></div>

<article style="font-family:Georgia,serif;line-height:1.8;color:#1f2937;">
  <!-- Breadcrumb -->
  <nav style="margin-bottom:16px;font-size:13px;color:#94a3b8;">
    <a href="/" style="color:#1e3a5f;text-decoration:none;">🏠 Beranda</a>
    <span style="margin:0 6px;">›</span>
    <span style="color:#1e3a5f;">Berita</span>
    <span style="margin:0 6px;">›</span>
    <span>{_esc(title[:40])}{'…' if len(title) > 40 else ''}</span>
  </nav>

  <!-- Category Badge -->
  <div style="margin-bottom:12px;">{category_badge}</div>

  <!-- Title -->
  <h1 style="font-size:28px;font-weight:700;line-height:1.3;margin:0 0 12px;color:#111827;">{_esc(title)}</h1>

  <!-- Meta Info -->
  <div style="display:flex;align-items:center;gap:16px;padding:12px 0;border-top:1px solid #e5e7eb;border-bottom:1px solid #e5e7eb;margin-bottom:24px;font-size:13px;color:#6b7280;flex-wrap:wrap;">
    <span>📅 {_esc(publish_date)}</span>
    <span>🕐 {_esc(publish_time)}</span>
    <span>⏱️ {reading_time} menit baca</span>
    <span>📰 Sumber: {source_link}</span>
    <span style="margin-left:auto;display:flex;gap:8px;">
      <a href="https://api.whatsapp.com/send?text={encoded_title}%20{encoded_url}" target="_blank" rel="noopener" title="Share ke WhatsApp" style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;background:#25d366;color:#fff;border-radius:6px;font-size:11px;text-decoration:none;">💬 WA</a>
      <a href="https://www.facebook.com/sharer/sharer.php?u={encoded_url}" target="_blank" rel="noopener" title="Share ke Facebook" style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;background:#1877f2;color:#fff;border-radius:6px;font-size:11px;text-decoration:none;">📘 FB</a>
      <a href="https://twitter.com/intent/tweet?text={encoded_title}&url={encoded_url}" target="_blank" rel="noopener" title="Share ke Twitter" style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;background:#1da1f2;color:#fff;border-radius:6px;font-size:11px;text-decoration:none;">🐦 X</a>
      <button onclick="navigator.clipboard.writeText(window.location.href);this.innerHTML='✅';setTimeout(()=>this.innerHTML='🔗',1500)" title="Salin link" style="display:inline-flex;align-items:center;gap:4px;padding:4px 10px;background:#6b7280;color:#fff;border-radius:6px;font-size:11px;border:none;cursor:pointer;">🔗</button>
    </span>
  </div>

  <!-- Table of Contents -->
  {toc_html}

  <!-- Article Body -->
  <div style="font-size:16px;">
    {body_paragraphs}
  </div>

  <!-- Disclaimer -->
  <div style="margin-top:24px;padding:16px;background:#f9fafb;border-left:4px solid #d1d5db;font-size:13px;color:#6b7280;font-style:italic;">
    <strong>Disclaimer:</strong> Artikel ini dikutip dari sumber berita untuk tujuan informasi. Segala keputusan investasi harus berdasarkan pertimbangan matang dan berkonsultasi dengan penasihat keuangan yang kompeten.
  </div>
</article>

<!-- Back to Top Button -->
<button id="bpf-backtotop" onclick="window.scrollTo({{top:0,behavior:'smooth'}})" style="position:fixed;bottom:24px;right:24px;width:44px;height:44px;border-radius:50%;background:#1e3a5f;color:#fff;border:none;font-size:20px;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,.2);display:none;z-index:9998;transition:all .3s;" onmouseover="this.style.background='#c8a951'" onmouseout="this.style.background='#1e3a5f'">↑</button>

<!-- UX JavaScript -->
<script>
(function(){{
  // Reading progress bar
  var bar = document.getElementById('bpf-progress');
  var btn = document.getElementById('bpf-backtotop');
  if(bar){{
    window.addEventListener('scroll', function(){{
      var h = document.documentElement.scrollHeight - window.innerHeight;
      var p = (window.scrollY / h) * 100;
      bar.style.width = p + '%';
      // Show/hide back-to-top
      if(btn) btn.style.display = window.scrollY > 400 ? 'block' : 'none';
    }});
  }}
  // Smooth scroll for TOC links
  document.querySelectorAll('.bpf-toc a').forEach(function(a){{
    a.addEventListener('click', function(e){{
      var id = this.getAttribute('href').slice(1);
      var target = document.getElementById(id);
      if(target){{
        e.preventDefault();
        target.scrollIntoView({{behavior:'smooth', block:'start'}});
      }}
    }});
  }});
}})();
</script>

<style>
.bpf-toc-collapsed ul {{ display: none !important; }}
.bpf-toc-collapsed span {{ transform: rotate(-90deg); display: inline-block; }}
</style>
'''
    return html.strip()


def build_bpf_cta_widget() -> str:
    """Build a CTA widget with links to BPF sites + source attribution."""
    return '''
<!-- BPF CTA Widget -->
<div style="margin:30px 0;padding:24px;background:linear-gradient(135deg,#1a365d 0%,#2563eb 100%);border-radius:12px;color:#fff;font-family:sans-serif;">
  <h3 style="margin:0 0 12px;color:#fff;font-size:18px;">📈 Mulai Trading Sekarang</h3>
  <p style="margin:0 0 16px;font-size:14px;opacity:0.9;">Bergabung dengan PT Bestprofit Futures — broker resmi Bappebti untuk perdagangan berjangka komoditi.</p>
  <div style="display:flex;gap:10px;flex-wrap:wrap;">
    <a href="https://bestprofit-futures.co.id/" target="_blank" rel="nofollow sponsored" style="display:inline-block;padding:10px 20px;background:#fff;color:#1a365d;border-radius:8px;text-decoration:none;font-weight:bold;font-size:14px;">Buka Akun Trading</a>
    <a href="https://etrade.bestprofit-futures.com/" target="_blank" rel="nofollow sponsored" style="display:inline-block;padding:10px 20px;background:rgba(255,255,255,0.2);color:#fff;border-radius:8px;text-decoration:none;font-size:14px;">E-Trade Online</a>
    <a href="https://demo.bestprofit-futures.com/" target="_blank" rel="nofollow sponsored" style="display:inline-block;padding:10px 20px;background:rgba(255,255,255,0.2);color:#fff;border-radius:8px;text-decoration:none;font-size:14px;">Coba Demo Gratis</a>
  </div>
</div>
<div style="margin-top:16px;padding:12px;background:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;font-size:12px;color:#166534;text-align:center;">
  📰 Artikel bersumber dari sumber berita terpercaya • Diterbitkan oleh <a href="https://bestprofit-futures.co.id/" target="_blank" rel="nofollow sponsored" style="color:#16a34a;font-weight:600;">PT Bestprofit Futures</a>
</div>'''


# ===================================================================
# 4. STRUCTURED DATA (JSON-LD SCHEMA)
# ===================================================================

def build_advanced_schema(title: str, content: str, publish_date: str,
                          publish_time: str, image_url: str = '') -> List[Dict[str, Any]]:
    """Build advanced JSON-LD structured data.

    Produces a list of schema.org graphs ready to be serialized into
    ``<script type="application/ld+json">`` blocks:
        1. NewsArticle  (headline, dates, author, publisher, image)
        2. BreadcrumbList
        3. WebSite (+ SearchAction)

    Args:
        title:        Article headline.
        content:      Article body (HTML or plain text).
        publish_date: 'YYYY-MM-DD'.
        publish_time: 'HH:MM' (WIB assumed, +07:00 offset).
        image_url:    Optional featured-image URL.

    Returns:
        List of dicts (one per schema graph).
    """
    plain_text = re.sub(r'<[^>]+>', ' ', content or '')
    plain_text = re.sub(r'\s+', ' ', plain_text).strip()
    words = plain_text.split()
    description = ' '.join(words[:45]) + ('…' if len(words) > 45 else '')

    now_iso = datetime.now().astimezone().isoformat(timespec='seconds')

    # Compose ISO-8601 datePublished (WIB / +07:00)
    date_published = now_iso
    if publish_date:
        try:
            t_parts = (publish_time or '08:00').strip().split(':')
            hh, mm = t_parts[0], t_parts[1]
            date_published = f"{str(publish_date).strip()}T{hh}:{mm}:00+07:00"
        except (IndexError, AttributeError, ValueError):
            pass

    bpf_home = DEFAULT_AUTHORITY_SITES['PT BESTPROFIT FUTURES']
    schemas: List[Dict[str, Any]] = []

    # --- 1. NewsArticle ---
    news_article: Dict[str, Any] = {
        '@context': 'https://schema.org',
        '@type': 'NewsArticle',
        '@id': f"newsarticle-{int(time.time())}",
        'headline': (title or '')[:110],  # Google recommends ≤ 110 chars
        'description': description,
        'inLanguage': 'id-ID',
        'datePublished': date_published,
        'dateModified': now_iso,
        'author': {
            '@type': 'Organization',
            'name': 'PT Bestprofit Futures',
            'url': bpf_home,
        },
        'publisher': {
            '@type': 'Organization',
            'name': 'PT Bestprofit Futures',
            'logo': {
                '@type': 'ImageObject',
                'url': bpf_home.rstrip('/') + '/logo.png',
            },
        },
    }
    if image_url:
        news_article['image'] = [image_url]
    schemas.append(news_article)

    # --- 2. BreadcrumbList ---
    schemas.append({
        '@context': 'https://schema.org',
        '@type': 'BreadcrumbList',
        'itemListElement': [
            {'@type': 'ListItem', 'position': 1, 'name': 'Beranda', 'item': bpf_home},
            {'@type': 'ListItem', 'position': 2, 'name': 'Berita',
             'item': bpf_home.rstrip('/') + '/berita'},
            {'@type': 'ListItem', 'position': 3, 'name': (title or '')[:80]},
        ],
    })

    # --- 3. WebSite + SearchAction ---
    schemas.append({
        '@context': 'https://schema.org',
        '@type': 'WebSite',
        'name': 'BPFWorkHub News',
        'url': bpf_home,
        'potentialAction': {
            '@type': 'SearchAction',
            'target': bpf_home.rstrip('/') + '/?s={search_term_string}',
            'query-input': 'required name=search_term_string',
        },
    })

    return schemas


# ===================================================================
# 5. SITEMAP PINGING & PUBLISH TIMING
# ===================================================================

def ping_sitemap(site_url: str) -> List[str]:
    """Notify search engines that the sitemap has been updated.

    Args:
        site_url: Base site URL (sitemap assumed at ``/sitemap.xml``).

    Returns:
        Human-readable status string per search engine, e.g.
        ``["Google: OK", "Bing: HTTP 400"]``.
    """
    results: List[str] = []
    if not site_url:
        return ['ERROR: site_url kosong']

    sitemap_url = site_url.rstrip('/') + '/sitemap.xml'
    encoded = _url_quote(sitemap_url, safe='')
    endpoints = [
        ('Google', f'https://www.google.com/ping?sitemap={encoded}'),
        ('Bing', f'https://www.bing.com/ping?sitemap={encoded}'),
    ]

    for name, url in endpoints:
        try:
            resp = requests.get(
                url,
                timeout=10,
                headers={'User-Agent': 'BPFWorkHub-Scraper/2.0'},
            )
            status = 'OK' if resp.status_code == 200 else f'HTTP {resp.status_code}'
            results.append(f'{name}: {status}')
        except Exception as exc:
            results.append(f'{name}: GAGAL ({exc})')
    return results


def get_optimal_publish_time() -> datetime:
    """Return the next optimal publish datetime.

    Slots tuned for Indonesian finance readership (WIB):
        08:30  pre-market open
        12:30  lunch-break browsing peak
        19:00  evening leisure browsing peak

    A small random jitter (±10 min) keeps the schedule human-like.
    Always returns a future datetime (rolls over to tomorrow 08:30).
    """
    now = datetime.now()
    for hour, minute in OPTIMAL_SLOTS_WIB:
        candidate = now.replace(
            hour=hour, minute=minute,
            second=random.randint(0, 59), microsecond=0,
        ) + timedelta(minutes=random.randint(-10, 10))
        if candidate > now:
            return candidate

    # All slots passed today -> tomorrow's first slot
    tomorrow = now + timedelta(days=1)
    hour, minute = OPTIMAL_SLOTS_WIB[0]
    return tomorrow.replace(hour=hour, minute=minute, second=0, microsecond=0)


def should_publish_today(published_today: Any) -> bool:
    """Decide whether another article may be published today.

    Args:
        published_today: Either
            * ``int``  — number of articles already published today, or
            * iterable — timestamps (datetime objects or ISO strings)
              of today's publications.

    Returns:
        True if under the daily cap AND the minimum inter-post gap is met.
    """
    if isinstance(published_today, (list, tuple, set)):
        entries = list(published_today)
        count = len(entries)
        now = datetime.now()
        for entry in entries:
            ts: Optional[datetime] = entry if isinstance(entry, datetime) else None
            if ts is None:
                try:
                    ts = datetime.fromisoformat(str(entry))
                except (ValueError, TypeError):
                    continue
            if (now - ts).total_seconds() < MIN_PUBLISH_GAP_MINUTES * 60:
                return False  # too soon after last post
    else:
        try:
            count = int(published_today or 0)
        except (TypeError, ValueError):
            count = 0

    return count < MAX_POSTS_PER_DAY


# ===================================================================
# 6. CONTENT UNIQUENESS — Parafrase untuk hindari duplicate
# ===================================================================

#: Synonym mappings untuk content spinning.
_SYNONYMS: Dict[str, List[str]] = {
    'menurut': ['menurut', 'berdasarkan', 'ujar', 'kata'],
    'mengatakan': ['mengatakan', 'menyatakan', 'menuturkan', 'mengungkapkan'],
    'menambahkan': ['menambahkan', 'lalu', 'selanjutnya', 'kemudian'],
    'saat ini': ['saat ini', 'kini', 'sekarang', 'di tengah'],
    'menunjukkan': ['menunjukkan', 'menjelaskan', 'memaparkan', 'menyiratkan'],
    'diperkirakan': ['diperkirakan', 'ditaksir', 'diestimasi', 'kemungkinan'],
    'sebelumnya': ['sebelumnya', 'sejak awal', 'di awal', 'sejak lama'],
    'menjadi': ['menjadi', 'berubah jadi', 'merupakan', 'jatuh ke'],
    'tercatat': ['tercatat', 'terekam', 'menempuh', 'mencapai'],
    'menguat': ['menguat', 'naik', 'melonjak', 'mengalami kenaikan'],
    'melemah': ['melemah', 'turun', 'merosot', 'mengalami penurunan'],
    'fluktuatif': ['fluktuatif', 'bergerak volatil', 'tidak stabil', 'bergerak naik-turun'],
    'optimistis': ['optimistis', 'yakin', 'positif', 'antusias'],
    'pesimistis': ['pesimistis', 'ragu', 'was-was', 'khawatir'],
    'global': ['global', 'internasional', 'dunia', 'mancanegara'],
    'aset': ['aset', 'instrumen', 'komoditas', 'komoditi'],
    'pasar': ['pasar', 'bursa', 'market', 'peringkat'],
    'analisis': ['analisis', 'analisa', 'ulasan', 'tinjauan'],
    'pergerakan': ['pergerakan', 'koreksi', 'gerakan', 'ayunan'],
    'seiring': ['seiring', 'sejalan', 'bersamaan', 'iring-iringan'],
    'terhadap': ['terhadap', 'kepada', 'bagi', 'bagi'],
    'sentimen': ['sentimen', 'suasana pasar', 'psikologi pasar', 'kondisi pasar'],
}


def normalize_title(title: str) -> str:
    """Normalize title for fuzzy duplicate matching."""
    t = (title or '').lower().strip()
    t = re.sub(r'[^a-z0-9\s]', '', t)   # Remove punctuation
    t = re.sub(r'\s+', ' ', t)          # Normalize whitespace
    return t.strip()


def rewrite_content(content: str, title: str = '') -> str:
    """Parafrase konten untuk hindari duplicate content.

    Strategy:
        * Replace one occurrence of each synonym-base per paragraph with a
          random variant (preserving capitalization).
        * Words appearing in the title are PROTECTED (never replaced) so the
          headline/body keyword alignment stays intact for SEO.
        * Short lines (< 30 chars) and short bodies (< 100 chars) untouched.

    Note:
        Operates on plain text — run BEFORE build_article_html().
    """
    if not content or len(content) < 100:
        return content

    # Protect title keywords from being spun away
    protected = set()
    if title:
        for w in re.findall(r'[A-Za-z0-9.$%]+', title):
            if len(w) >= 3:
                protected.add(w.lower())

    paragraphs = content.split('\n')
    rewritten: List[str] = []
    for para in paragraphs:
        para = para.strip()
        if not para or len(para) < 30:
            rewritten.append(para)
            continue

        new_para = para
        for base, variants in _SYNONYMS.items():
            if base in protected:
                continue  # keep title-aligned wording consistent

            pattern = r'\b' + re.escape(base) + r'\b'
            if not re.search(pattern, new_para, flags=re.IGNORECASE):
                continue

            options = [v for v in variants if v.lower() != base.lower()]
            if not options:
                continue
            replacement = random.choice(options)

            def _smart_sub(match: "re.Match[str]", rep: str = replacement) -> str:
                original = match.group(0)
                if original.isupper() and len(original) > 2:
                    return rep.upper()
                if original[0].isupper():
                    return rep[0].upper() + rep[1:]
                return rep

            new_para = re.sub(pattern, _smart_sub, new_para,
                              count=1, flags=re.IGNORECASE)

        rewritten.append(new_para)

    return '\n\n'.join(rewritten)


# ===================================================================
# 7. INTERNAL LINKING
# ===================================================================

#: Indonesian stopwords excluded from internal-link keyword scoring.
_INTERNAL_LINK_STOPWORDS = {
    'dengan', 'adalah', 'untuk', 'dari', 'yang', 'pada', 'akan', 'tidak',
    'dalam', 'juga', 'oleh', 'sebagai', 'tersebut', 'karena', 'agar',
    'masih', 'telah', 'bahkan', 'namun', 'hingga', 'sampai', 'antara',
}


def auto_internal_links(html_content: str,
                        all_articles: List[Dict[str, Any]],
                        current_title: str = '',
                        max_links: int = 3) -> Tuple[str, List[Dict[str, str]]]:
    """Automatically insert contextual internal links to related articles.

    Scoring: word-overlap (≥5-char, non-stopword) between each candidate
    article title and the visible text of ``html_content``. Anchors are
    matched as contiguous phrases from the candidate title found in the
    body, never inside existing HTML tags.

    Args:
        html_content:  Rendered article HTML.
        all_articles:  List of dicts with at least ``title`` and ``link``/``url``.
        current_title: Title of the current article (skipped as candidate).
        max_links:     Maximum number of internal links to insert.

    Returns:
        (updated_html, list_of_inserted_link_dicts)
    """
    inserted: List[Dict[str, str]] = []
    if not html_content or not all_articles:
        return html_content, inserted

    current_norm = normalize_title(current_title) if current_title else ''
    text_only = re.sub(r'<[^>]+>', ' ', html_content).lower()

    # --- Score candidate articles by keyword overlap -----------------
    scored: List[Tuple[int, str, str]] = []  # (overlap, title, link)
    for art in all_articles:
        art_title = (art.get('title') or '').strip()
        if not art_title:
            continue
        if current_norm and normalize_title(art_title) == current_norm:
            continue  # never self-link
        link = art.get('link') or art.get('url') or ''
        if not link:
            continue

        title_words = set(
            w for w in re.findall(r'[a-z]{5,}', normalize_title(art_title))
            if w not in _INTERNAL_LINK_STOPWORDS
        )
        overlap = sum(1 for w in title_words if w in text_only)
        if overlap >= 1:
            scored.append((overlap, art_title, link))

    scored.sort(key=lambda x: (-x[0], x[1]))

    # --- Insert links ------------------------------------------------
    used_anchors: set = set()
    links_added = 0
    for _overlap, art_title, link in scored:
        if links_added >= max_links:
            break

        words = [w for w in art_title.split() if len(w) >= 4]
        target_phrase = ''
        # Prefer longer (more specific) phrases; fall back to shorter ones
        for n in range(min(len(words), 6), 2, -1):
            for i in range(len(words) - n + 1):
                phrase = ' '.join(words[i:i + n])
                key = phrase.lower()
                if key in used_anchors:
                    continue
                if key in text_only:
                    target_phrase = phrase
                    break
            if target_phrase:
                break

        if not target_phrase:
            continue

        safe_link = _esc(link, quote=True)
        pattern = r'\b' + re.escape(target_phrase) + r'\b(?![^<]*>)'
        new_html, n_subs = re.subn(
            pattern,
            f'<a href="{safe_link}">{_esc(target_phrase)}</a>',
            html_content, count=1, flags=re.IGNORECASE,
        )
        if n_subs:
            html_content = new_html
            used_anchors.add(target_phrase.lower())
            inserted.append({
                'anchor': target_phrase,
                'url': link,
                'title': art_title,
            })
            links_added += 1

    return html_content, inserted


# ===================================================================
# 8. PERFORMANCE ANALYTICS
# ===================================================================

_MAX_ANALYTICS_RECORDS = 5000


def track_performance(post_id: Any, site_name: str, title: str,
                      **extra_metrics: Any) -> None:
    """Record a published post for performance analytics.

    Appends a timestamped record to ``SEO_ANALYTICS_FILE`` (path from
    package ``__init__.py``). Thread-safe; file capped at
    ``_MAX_ANALYTICS_RECORDS`` entries.

    Args:
        post_id:       WordPress post ID (or local ID).
        site_name:     Target site identifier.
        title:         Published article title.
        **extra_metrics: Optional extras (seo_score, word_count, ...).
    """
    record: Dict[str, Any] = {
        'post_id': post_id,
        'site_name': site_name,
        'title': title,
        'timestamp': datetime.now().isoformat(timespec='seconds'),
    }
    record.update(extra_metrics)

    with _LOCK:
        records = _load_json(SEO_ANALYTICS_FILE, [])
        if not isinstance(records, list):
            records = []
        records.append(record)
        if len(records) > _MAX_ANALYTICS_RECORDS:
            records = records[-_MAX_ANALYTICS_RECORDS:]
        _save_json(SEO_ANALYTICS_FILE, records)


def get_analytics(date_from: Any = None, date_to: Any = None) -> Dict[str, Any]:
    """Aggregate publishing analytics, optionally filtered by date range.

    Args:
        date_from: ``datetime`` or ISO string (inclusive lower bound).
        date_to:   ``datetime`` or ISO string (inclusive upper bound).

    Returns:
        Dict with totals, per-site breakdown, per-day breakdown, period,
        and the latest raw records.
    """

    def _parse(value: Any) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if value is None:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except (ValueError, TypeError):
            return None

    df = _parse(date_from)
    dt_to = _parse(date_to)

    records = _load_json(SEO_ANALYTICS_FILE, [])
    if not isinstance(records, list):
        records = []

    filtered: List[Dict[str, Any]] = []
    for rec in records:
        if not isinstance(rec, dict):
            continue
        ts = _parse(rec.get('timestamp'))
        if ts is None:
            continue
        if df and ts < df:
            continue
        if dt_to and ts > dt_to:
            continue
        filtered.append(rec)

    total = len(filtered)
    by_site: Dict[str, int] = {}
    by_day: Dict[str, int] = {}
    for rec in filtered:
        site = rec.get('site_name') or 'unknown'
        by_site[site] = by_site.get(site, 0) + 1
        day = str(rec.get('timestamp', ''))[:10]
        by_day[day] = by_day.get(day, 0) + 1

    return {
        'total_posts': total,
        'total_articles': total,
        'posts_by_site': by_site,
        'by_site': by_site,
        'posts_by_day': dict(sorted(by_day.items())),
        'by_date': dict(sorted(by_day.items())),
        'period': {
            'from': df.isoformat() if df else None,
            'to': dt_to.isoformat() if dt_to else None,
        },
        'latest': filtered[-20:],
    }


# ===================================================================
# 9. JSON CACHE (file-based, TTL 30s)
# ===================================================================

class JsonCache:
    """Simple file-based JSON cache with TTL (default 30 seconds).

    Each key maps to one JSON file inside ``cache_dir`` (filename is an
    MD5 digest of the key). Writes are atomic (tmp + ``os.replace``);
    expired entries are removed lazily on read or via :meth:`prune_expired`.

    Usage::

        cache = JsonCache()                     # CACHE_DIR, 30s TTL
        rates = cache.get('fx-rates')
        if rates is None:
            rates = fetch_rates()
            cache.set('fx-rates', rates)

        # Or one-liner:
        rates = cache.get_or_set('fx-rates', fetch_rates)
    """

    def __init__(self, cache_dir: Optional[str] = None,
                 ttl_seconds: Optional[int] = None) -> None:
        self.cache_dir = cache_dir or CACHE_DIR
        ttl = ttl_seconds if ttl_seconds is not None else CACHE_TTL_SECONDS
        self.ttl_seconds = max(int(ttl), 1)
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
        except OSError:
            pass

    # -- internals ----------------------------------------------------

    def _path_for(self, key: str) -> str:
        digest = hashlib.md5(str(key).encode('utf-8')).hexdigest()
        return os.path.join(self.cache_dir, f"{digest}.json")

    @staticmethod
    def _now() -> float:
        return time.time()

    # -- public API ---------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """Return cached value if fresh, else ``default`` (lazy-expire)."""
        path = self._path_for(key)
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                payload = json.load(fh)
            stored_at = float(payload.get('_ts', 0))
            if self._now() - stored_at <= self.ttl_seconds:
                return payload.get('value', default)
            # Expired -> remove lazily
            try:
                os.remove(path)
            except OSError:
                pass
        except (FileNotFoundError, json.JSONDecodeError, ValueError, OSError):
            pass
        return default

    def set(self, key: str, value: Any) -> bool:
        """Store ``value`` under ``key`` with a fresh timestamp."""
        path = self._path_for(key)
        payload = {'_ts': self._now(), 'key': str(key), 'value': value}
        tmp_path = f"{path}.tmp"
        try:
            with open(tmp_path, 'w', encoding='utf-8') as fh:
                json.dump(payload, fh, ensure_ascii=False)
            os.replace(tmp_path, path)
            return True
        except (OSError, TypeError, ValueError):
            return False

    def get_or_set(self, key: str, factory: Callable[[], Any],
                   default: Any = None) -> Any:
        """Return cached value, or compute via ``factory()`` and cache it."""
        cached = self.get(key)
        if cached is not None:
            return cached
        try:
            value = factory()
        except Exception:
            return default
        self.set(key, value)
        return value

    def delete(self, key: str) -> bool:
        """Remove a single cache entry."""
        try:
            os.remove(self._path_for(key))
            return True
        except OSError:
            return False

    def clear(self) -> int:
        """Remove ALL cache files. Returns number removed."""
        removed = 0
        try:
            names = os.listdir(self.cache_dir)
        except OSError:
            return 0
        for name in names:
            if name.endswith('.json'):
                try:
                    os.remove(os.path.join(self.cache_dir, name))
                    removed += 1
                except OSError:
                    pass
        return removed

    def prune_expired(self) -> int:
        """Delete only expired entries. Returns number pruned."""
        pruned = 0
        try:
            names = os.listdir(self.cache_dir)
        except OSError:
            return 0
        for name in names:
            if not name.endswith('.json'):
                continue
            path = os.path.join(self.cache_dir, name)
            try:
                with open(path, 'r', encoding='utf-8') as fh:
                    stored_at = float(json.load(fh).get('_ts', 0))
                if self._now() - stored_at > self.ttl_seconds:
                    os.remove(path)
                    pruned += 1
            except (OSError, ValueError, json.JSONDecodeError):
                pass
        return pruned


#: Shared default cache instance (30s TTL, CACHE_DIR from __init__.py).
default_cache = JsonCache()
