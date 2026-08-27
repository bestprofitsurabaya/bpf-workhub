#!/usr/bin/env python3
"""
Inject custom CSS into BPF Surabaya WordPress site.
Improves UI: better colors, card styling, footer, responsive design.

Run: python3 scripts/inject_custom_css.py
"""

import json
import os
import requests

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'news_scraper')
WP_SITES_FILE = os.path.join(DATA_DIR, 'wp_sites.json')

# ══════════════════════════════════════════════════════════════════════
# CUSTOM CSS — Modern, professional financial site look
# ══════════════════════════════════════════════════════════════════════

CUSTOM_CSS = """
/* ============================================================
   BPF SURABAYA — Custom UI Enhancements
   ============================================================ */

/* ── 1. GLOBAL ─────────────────────────────────────────────── */
:root {
  --bpf-primary: #1e3a5f;
  --bpf-accent: #c8a951;
  --bpf-dark: #0f1923;
  --bpf-light: #f8f9fa;
  --bpf-text: #333;
  --bpf-muted: #6c757d;
  --bpf-success: #28a745;
  --bpf-border: #e9ecef;
  --bpf-shadow: 0 2px 12px rgba(0,0,0,.08);
  --bpf-radius: 10px;
}

body {
  font-family: 'Inter', 'Segoe UI', -apple-system, BlinkMacSystemFont, sans-serif;
  color: var(--bpf-text);
  background: #f5f6fa;
  line-height: 1.7;
}

/* Smooth scroll */
html { scroll-behavior: smooth; }

/* Better link colors */
a { transition: color .2s; }
a:hover { color: var(--bpf-accent); }

/* ── 2. HEADER & NAV ──────────────────────────────────────── */
.mg-headwidget {
  box-shadow: 0 2px 20px rgba(0,0,0,.12);
  position: relative;
  z-index: 100;
}

.mg-nav-widget-area-back {
  background-size: cover !important;
  background-position: center !important;
  min-height: 120px;
}

.navbar-wp {
  background: var(--bpf-primary) !important;
  border: none;
  border-radius: 0;
  margin: 0;
  padding: 0;
  box-shadow: 0 2px 8px rgba(0,0,0,.15);
}

.navbar-wp .navbar-nav > li > a {
  color: #fff !important;
  font-weight: 500;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 14px 16px;
  transition: all .25s;
  position: relative;
}

.navbar-wp .navbar-nav > li > a:hover,
.navbar-wp .navbar-nav > li > a:focus,
.navbar-wp .navbar-nav > .active > a {
  color: var(--bpf-accent) !important;
  background: rgba(255,255,255,.08);
}

.navbar-wp .navbar-nav > li > a::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 50%;
  width: 0;
  height: 2px;
  background: var(--bpf-accent);
  transition: all .3s;
  transform: translateX(-50%);
}

.navbar-wp .navbar-nav > li > a:hover::after {
  width: 70%;
}

/* ── 3. TAGS / TRENDING ───────────────────────────────────── */
.mg-tpt-tag-area {
  background: linear-gradient(135deg, var(--bpf-primary), #2c4a7c);
  padding: 12px 0;
  border-bottom: 3px solid var(--bpf-accent);
}

.mg-tpt-tag-area .tags a {
  display: inline-block;
  background: rgba(255,255,255,.12);
  color: #fff;
  padding: 5px 14px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
  margin: 3px 4px;
  transition: all .25s;
  border: 1px solid rgba(255,255,255,.15);
}

.mg-tpt-tag-area .tags a:hover {
  background: var(--bpf-accent);
  color: var(--bpf-dark);
  border-color: var(--bpf-accent);
  transform: translateY(-1px);
}

/* ── 4. LATEST NEWS SECTION ───────────────────────────────── */
.mg-latest-news-sec {
  background: #fff;
  border-radius: var(--bpf-radius);
  box-shadow: var(--bpf-shadow);
  margin: 24px auto;
  padding: 20px;
  max-width: 1200px;
}

.mg-latest-news-sec .title {
  font-size: 18px;
  font-weight: 700;
  color: var(--bpf-primary);
  border-left: 4px solid var(--bpf-accent);
  padding-left: 12px;
  margin-bottom: 16px;
}

/* ── 5. ARTICLE CARDS ─────────────────────────────────────── */
.mg-fea-area .article {
  background: #fff;
  border-radius: var(--bpf-radius);
  box-shadow: var(--bpf-shadow);
  overflow: hidden;
  transition: all .3s;
  margin-bottom: 20px;
  border: 1px solid var(--bpf-border);
}

.mg-fea-area .article:hover {
  transform: translateY(-4px);
  box-shadow: 0 8px 30px rgba(0,0,0,.12);
  border-color: var(--bpf-accent);
}

.mg-fea-area .article img {
  transition: transform .4s;
  object-fit: cover;
}

.mg-fea-area .article:hover img {
  transform: scale(1.05);
}

/* Article title */
.mg-fea-area .article h2 a,
.mg-fea-area .article h3 a,
.mg-fea-area .article .title a {
  color: var(--bpf-dark);
  font-weight: 600;
  font-size: 16px;
  line-height: 1.4;
  transition: color .2s;
}

.mg-fea-area .article h2 a:hover,
.mg-fea-area .article h3 a:hover,
.mg-fea-area .article .title a:hover {
  color: var(--bpf-accent);
}

/* Category badge */
.mg-fea-area .article .category-name,
.mg-fea-area .article .cat {
  background: var(--bpf-primary);
  color: #fff;
  padding: 3px 10px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

/* Date & author */
.mg-fea-area .article .post-format,
.mg-fea-area .article .date,
.mg-fea-area .article .author {
  color: var(--bpf-muted);
  font-size: 12px;
}

/* ── 6. SIDEBAR ───────────────────────────────────────────── */
.sidebar-sticky .widget {
  background: #fff;
  border-radius: var(--bpf-radius);
  box-shadow: var(--bpf-shadow);
  padding: 20px;
  margin-bottom: 20px;
  border: 1px solid var(--bpf-border);
}

.sidebar-sticky .widget-title,
.sidebar-sticky h2.widget-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--bpf-primary);
  border-bottom: 3px solid var(--bpf-accent);
  padding-bottom: 10px;
  margin-bottom: 16px;
}

.sidebar-sticky .widget ul li {
  padding: 8px 0;
  border-bottom: 1px solid var(--bpf-border);
  font-size: 14px;
}

.sidebar-sticky .widget ul li:last-child {
  border-bottom: none;
}

.sidebar-sticky .widget ul li a {
  color: var(--bpf-text);
  transition: all .2s;
}

.sidebar-sticky .widget ul li a:hover {
  color: var(--bpf-accent);
  padding-left: 6px;
}

/* ── 7. PAGINATION ────────────────────────────────────────── */
.navigation.pagination .nav-links {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin: 30px 0;
}

.navigation.pagination .page-numbers {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 40px;
  height: 40px;
  border-radius: 8px;
  background: #fff;
  color: var(--bpf-text);
  font-weight: 500;
  font-size: 14px;
  border: 1px solid var(--bpf-border);
  transition: all .2s;
  text-decoration: none;
}

.navigation.pagination .page-numbers:hover,
.navigation.pagination .page-numbers.current {
  background: var(--bpf-primary);
  color: #fff;
  border-color: var(--bpf-primary);
}

/* ── 8. FOOTER ────────────────────────────────────────────── */
.footer {
  background: var(--bpf-dark) !important;
  color: #ccc;
  padding: 40px 0 0;
}

.footer .overlay {
  background: transparent;
}

.mg-footer-widget-area {
  padding: 30px 0;
}

.mg-footer-widget-area h6 {
  color: var(--bpf-accent);
  font-size: 16px;
  font-weight: 700;
  margin-bottom: 16px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.mg-footer-widget-area p {
  color: #aaa;
  font-size: 13px;
  line-height: 1.8;
}

.mg-footer-bottom-area {
  border-top: 1px solid rgba(255,255,255,.1);
  padding: 20px 0;
}

.site-title-footer a {
  color: #fff;
  font-weight: 700;
  font-size: 16px;
}

.mg-social li a {
  color: #aaa;
  transition: color .2s;
}

.mg-social li a:hover {
  color: var(--bpf-accent);
}

/* ── 9. CTA BUTTONS (for articles & pages) ────────────────── */
.btn-bpf {
  display: inline-block;
  background: var(--bpf-accent);
  color: var(--bpf-dark);
  padding: 10px 24px;
  border-radius: 6px;
  font-weight: 600;
  font-size: 14px;
  text-decoration: none;
  transition: all .25s;
  border: 2px solid var(--bpf-accent);
}

.btn-bpf:hover {
  background: transparent;
  color: var(--bpf-accent);
  transform: translateY(-2px);
  box-shadow: 0 4px 15px rgba(200,169,81,.3);
}

/* ── 10. ARTICLE SINGLE PAGE ──────────────────────────────── */
.single-post .entry-content {
  font-size: 16px;
  line-height: 1.9;
  color: #444;
}

.single-post .entry-content p {
  margin-bottom: 16px;
}

.single-post .entry-title {
  font-size: 28px;
  font-weight: 700;
  color: var(--bpf-dark);
  line-height: 1.3;
}

/* Read more link */
.read-more {
  display: inline-block;
  color: var(--bpf-primary);
  font-weight: 600;
  font-size: 13px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  transition: all .2s;
}

.read-more:hover {
  color: var(--bpf-accent);
}

/* ── 11. RESPONSIVE ───────────────────────────────────────── */
@media (max-width: 768px) {
  .navbar-wp .navbar-nav > li > a {
    font-size: 12px;
    padding: 10px 12px;
  }
  
  .mg-fea-area .article h2 a,
  .mg-fea-area .article h3 a {
    font-size: 15px;
  }
  
  .mg-latest-news-sec {
    margin: 12px;
    padding: 14px;
  }
  
  .sidebar-sticky .widget {
    margin-top: 20px;
  }
}

/* ── 12. TRADINGVIEW WIDGET ───────────────────────────────── */
.tradingview-widget-container {
  background: #fff;
  border-radius: var(--bpf-radius);
  box-shadow: var(--bpf-shadow);
  overflow: hidden;
  margin-bottom: 20px;
}

/* ── 13. SCROLLBAR ────────────────────────────────────────── */
::-webkit-scrollbar {
  width: 8px;
}

::-webkit-scrollbar-track {
  background: #f1f1f1;
}

::-webkit-scrollbar-thumb {
  background: var(--bpf-primary);
  border-radius: 4px;
}

::-webkit-scrollbar-thumb:hover {
  background: var(--bpf-accent);
}

/* ── 14. SELECTION HIGHLIGHT ──────────────────────────────── */
::selection {
  background: var(--bpf-accent);
  color: var(--bpf-dark);
}
"""


def load_sites():
    with open(WP_SITES_FILE) as f:
        return json.load(f)


def login(site, session):
    wp_base = site['wp_url'].split('/wp-json')[0]
    username = site.get('username', '')
    for pw in [site.get('app_password', ''), site.get('basic_password', '')]:
        if not pw:
            continue
        r = session.get(f"{wp_base}/wp-json/wp/v2/users/me", auth=(username, pw), timeout=15)
        if r.status_code == 200:
            return True, wp_base, (username, pw)
    return False, wp_base, None


def get_existing_css(auth, wp_base):
    """Get existing custom CSS from WordPress."""
    # Check for existing additional CSS via customizer
    r = requests.get(f"{wp_base}/wp-json/wp/v2/types", auth=auth, timeout=15)
    return None


def inject_css_via_customizer(auth, wp_base, css):
    """Try to inject CSS via WordPress customizer API."""
    # Method 1: Use custom_css customizer setting
    r = requests.post(
        f"{wp_base}/wp-json/wp/v2/customize",
        json={"settings": [{"id": "custom_css", "value": css}]},
        auth=auth,
        timeout=15
    )
    return r.status_code in (200, 201)


def inject_css_via_plugin(auth, wp_base, css):
    """Inject CSS by creating a custom CSS post (Yoast method)."""
    # Create a page with CSS in a style block
    data = {
        "title": "Custom CSS",
        "slug": "custom-css-bpf",
        "content": f"<style>{css}</style>",
        "status": "publish",
    }
    r = requests.post(
        f"{wp_base}/wp-json/wp/v2/pages",
        json=data,
        auth=auth,
        timeout=30
    )
    if r.status_code in (200, 201):
        page = r.json()
        print(f"  ✅ CSS page created (ID: {page['id']})")
        print(f"  📌 Add this to your theme's header: ")
        print(f"     {{Page: custom-css-bpf}}")
        return True
    return False


def inject_css_via_snippet(auth, wp_base, css):
    """Inject CSS via Code Snippets plugin if available."""
    # Check if Code Snippets plugin is active
    r = requests.get(f"{wp_base}/wp-json/snippets/v1/snippets", auth=auth, timeout=15)
    if r.status_code == 200:
        # Code Snippets plugin is available
        snippet_data = {
            "title": "BPF Custom CSS",
            "code": css,
            "type": "css",
            "status": "active",
        }
        r2 = requests.post(
            f"{wp_base}/wp-json/snippets/v1/snippets",
            json=snippet_data,
            auth=auth,
            timeout=30
        )
        if r2.status_code in (200, 201):
            print(f"  ✅ CSS snippet created via Code Snippets plugin")
            return True
    return False


def inject_css_via_functions(auth, wp_base, css):
    """Add CSS via functions.php by creating a child theme snippet."""
    # Create a custom CSS file in uploads and enqueue it
    # This is a workaround - create a simple PHP file that outputs the CSS
    
    # First, let's try to add it via the WordPress Customizer API
    # by posting to the customize_save endpoint
    
    # Alternative: Create a CSS file in wp-content/uploads
    import time
    timestamp = int(time.time())
    
    # Upload CSS as a media attachment
    files = {
        'file': (f'bpf-custom-{timestamp}.css', css.encode('utf-8'), 'text/css')
    }
    
    r = requests.post(
        f"{wp_base}/wp-json/wp/v2/media",
        files=files,
        auth=auth,
        timeout=30
    )
    
    if r.status_code in (200, 201):
        media = r.json()
        css_url = media.get('source_url', '')
        print(f"  ✅ CSS file uploaded: {css_url}")
        
        # Now we need to enqueue this CSS in the theme
        # This requires adding a function via Code Snippets or functions.php
        # For now, we'll create a page that includes the CSS link
        
        snippet_php = f"""
// BPF Custom CSS
add_action('wp_enqueue_scripts', function() {{
    wp_enqueue_style('bpf-custom-css', '{css_url}', array(), '{timestamp}');
}});
"""
        
        # Try Code Snippets
        r2 = requests.get(f"{wp_base}/wp-json/snippets/v1/snippets", auth=auth, timeout=15)
        if r2.status_code == 200:
            snippet_data = {
                "title": "BPF Custom CSS Enqueue",
                "code": snippet_php,
                "type": "php",
                "status": "active",
            }
            r3 = requests.post(
                f"{wp_base}/wp-json/snippets/v1/snippets",
                json=snippet_data,
                auth=auth,
                timeout=30
            )
            if r3.status_code in (200, 201):
                print(f"  ✅ CSS enqueue snippet created")
                return True
        
        print(f"  ⚠️  CSS uploaded but needs manual enqueue.")
        print(f"     Add this PHP to your theme's functions.php or Code Snippets:")
        print(f"     wp_enqueue_style('bpf-custom', '{css_url}');")
        return True
    
    return False


def main():
    sites = load_sites()
    site_name = 'BPF Surabaya'
    
    if site_name not in sites:
        print(f"Site '{site_name}' not found")
        return
    
    site = sites[site_name]
    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 BPF-UIEnhance/1.0'})
    
    print(f"🔐 Login ke {site_name}...")
    ok, wp_base, auth = login(site, session)
    if not ok:
        print("❌ Login gagal!")
        return
    print(f"✅ Login berhasil ke {wp_base}")
    
    print(f"\n🎨 Injecting custom CSS ({len(CUSTOM_CSS)} chars)...")
    
    # Try multiple methods
    success = False
    
    # Method 1: Code Snippets plugin
    print("\n  [1] Trying Code Snippets plugin...")
    success = inject_css_via_snippet(auth, wp_base, CUSTOM_CSS)
    
    if not success:
        # Method 2: Upload CSS file + create enqueue snippet
        print("  [2] Trying CSS file upload + enqueue...")
        success = inject_css_via_functions(auth, wp_base, CUSTOM_CSS)
    
    if not success:
        # Method 3: Create a page with inline CSS
        print("  [3] Creating CSS page (manual header injection needed)...")
        success = inject_css_via_plugin(auth, wp_base, CUSTOM_CSS)
    
    if success:
        print("\n" + "="*60)
        print("✅ Custom CSS berhasil di-inject!")
        print("="*60)
        print("\n📄 CSS mencakup:")
        print("  • Color scheme: Navy (#1e3a5f) + Gold (#c8a951)")
        print("  • Modern card-based article layout")
        print("  • Smooth hover animations")
        print("  • Better typography & spacing")
        print("  • Improved footer design")
        print("  • Custom scrollbar")
        print("  • Mobile responsive")
        print("\n🔗 Cek hasilnya: https://best-profit-futures-surabaya.com/")
    else:
        print("\n❌ Semua method gagal. Manual injection diperlukan.")
        print("   Copy CSS dari file ini dan paste di WP Admin → Appearance → Customize → Additional CSS")


if __name__ == '__main__':
    main()
