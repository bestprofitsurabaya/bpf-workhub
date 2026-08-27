#!/usr/bin/env python3
"""
Apply custom CSS to BPF Surabaya WordPress site.
Uses WordPress REST API to inject CSS via theme header.

Run: python3 scripts/apply_custom_css.py
"""

import json
import os
import re
import requests
import time

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'news_scraper')
WP_SITES_FILE = os.path.join(DATA_DIR, 'wp_sites.json')

def load_sites():
    with open(WP_SITES_FILE) as f:
        return json.load(f)

def get_css():
    """Read the custom CSS from inject_custom_css.py"""
    script_path = os.path.join(os.path.dirname(__file__), 'inject_custom_css.py')
    with open(script_path) as f:
        content = f.read()
    match = re.search(r'CUSTOM_CSS = """(.*?)"""', content, re.DOTALL)
    return match.group(1).strip() if match else ''

def login(site):
    wp_base = site['wp_url'].split('/wp-json')[0]
    username = site.get('username', '')
    for pw in [site.get('app_password', ''), site.get('basic_password', '')]:
        if not pw:
            continue
        r = requests.get(f"{wp_base}/wp-json/wp/v2/users/me", auth=(username, pw), timeout=15)
        if r.status_code == 200:
            return True, wp_base, (username, pw)
    return False, wp_base, None

def create_plugin_file(wp_base, auth, css_url):
    """Create a mu-plugin file that enqueues our CSS."""
    php_content = f"""<?php
/**
 * BPF Custom CSS Loader
 * Auto-generated - do not edit
 */
add_action('wp_head', function() {{
    echo '<link rel="stylesheet" href="{css_url}" />';
}}, 1);
"""
    # Try to create via WP File Manager AJAX
    # First, get the admin page to find nonce
    s = requests.Session()
    s.auth = auth
    
    # Try to upload as a must-use plugin
    # WordPress loads all .php files in wp-content/mu-plugins/
    files = {
        'file': ('bpf-custom-css.php', php_content.encode('utf-8'), 'application/x-php')
    }
    
    r = requests.post(
        f"{wp_base}/wp-json/wp/v2/media",
        files=files,
        auth=auth,
        timeout=30
    )
    
    if r.status_code in (200, 201):
        media = r.json()
        print(f"  ✅ PHP file uploaded as media (ID: {media['id']})")
        print(f"  ⚠️  Note: This file needs to be moved to wp-content/mu-plugins/")
        print(f"     by an administrator via WP File Manager or FTP")
        return True
    else:
        print(f"  ❌ Upload failed: HTTP {r.status_code}")
        return False

def main():
    sites = load_sites()
    site_name = 'BPF Surabaya'
    
    if site_name not in sites:
        print(f"Site '{site_name}' not found")
        return
    
    site = sites[site_name]
    
    print(f"🔐 Login ke {site_name}...")
    ok, wp_base, auth = login(site)
    if not ok:
        print("❌ Login gagal!")
        return
    print(f"✅ Login berhasil ke {wp_base}")
    
    css = get_css()
    if not css:
        print("❌ CSS not found!")
        return
    
    print(f"\n🎨 Custom CSS: {len(css)} chars")
    
    # Step 1: Upload CSS file
    print("\n[1/3] Uploading CSS file...")
    timestamp = int(time.time())
    files = {'file': (f'bpf-custom-{timestamp}.css', css.encode('utf-8'), 'text/css')}
    r = requests.post(f"{wp_base}/wp-json/wp/v2/media", files=files, auth=auth, timeout=30)
    
    if r.status_code not in (200, 201):
        print(f"  ❌ CSS upload failed: HTTP {r.status_code}")
        return
    
    css_url = r.json().get('source_url', '')
    print(f"  ✅ CSS uploaded: {css_url}")
    
    # Step 2: Try to create mu-plugin
    print("\n[2/3] Creating mu-plugin to enqueue CSS...")
    create_plugin_file(wp_base, auth, css_url)
    
    # Step 3: Create instruction page
    print("\n[3/3] Creating setup instruction page...")
    
    # Read the CSS content for display
    css_display = css.replace('<', '&lt;').replace('>', '&gt;')
    
    instruct_html = f'''<article style="max-width:800px;margin:40px auto;font-family:system-ui,sans-serif;color:#333;">

<h1 style="color:#1e3a5f;">🎨 Custom CSS Setup</h1>

<div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:8px;padding:16px;margin:20px 0;">
  <strong>Status:</strong> ✅ CSS file sudah di-upload<br>
  <strong>URL:</strong> <a href="{css_url}" target="_blank">{css_url}</a>
</div>

<h2 style="color:#1e3a5f;">Cara Aktifkan (Pilih Salah Satu):</h2>

<h3>Method 1: WordPress Customizer (Recommended)</h3>
<ol>
  <li>Buka <a href="{wp_base}/wp-admin/customize.php">WP Admin → Appearance → Customize</a></li>
  <li>Klik <strong>"Additional CSS"</strong></li>
  <li>Paste kode CSS di bawah ini</li>
  <li>Klik <strong>"Publish"</strong></li>
</ol>

<h3>Method 2: WP File Manager</h3>
<ol>
  <li>Buka <a href="{wp_base}/wp-admin/admin.php?page=wp-file-manager">WP Admin → WP File Manager</a></li>
  <li>Navigate ke <code>wp-content/mu-plugins/</code></li>
  <li>Create file <code>bpf-custom-css.php</code> dengan isi:</li>
</ol>
<pre style="background:#f1f5f9;padding:12px;border-radius:6px;overflow-x:auto;font-size:13px;"><code>&lt;?php
add_action('wp_head', function() {{
    echo '&lt;link rel="stylesheet" href="{css_url}" /&gt;';
}}, 1);</code></pre>

<h2 style="color:#1e3a5f;">Kode CSS</h2>
<details>
  <summary style="cursor:pointer;font-weight:600;">Klik untuk melihat kode CSS ({len(css)} chars)</summary>
  <pre style="background:#1e293b;color:#e2e8f0;padding:16px;border-radius:8px;overflow-x:auto;font-size:12px;max-height:500px;overflow-y:auto;"><code>{css_display}</code></pre>
</details>

<div style="background:#fef3c7;border:1px solid #f59e0b;border-radius:8px;padding:16px;margin:20px 0;">
  <strong>💡 Tips:</strong> Setelah CSS aktif, clear browser cache (Ctrl+Shift+R) untuk melihat perubahan.
</div>

</article>'''
    
    r_page = requests.post(
        f"{wp_base}/wp-json/wp/v2/pages",
        json={
            'title': 'Custom CSS Setup',
            'slug': 'custom-css-setup',
            'content': instruct_html,
            'status': 'publish',
        },
        auth=auth,
        timeout=30
    )
    
    if r_page.status_code in (200, 201):
        page = r_page.json()
        print(f"  ✅ Setup page created: {wp_base}/{page['slug']}/")
    else:
        print(f"  ❌ Page creation failed: HTTP {r_page.status_code}")
    
    print("\n" + "="*60)
    print("📋 RINGKASAN:")
    print("="*60)
    print(f"1. CSS file: {css_url}")
    print(f"2. Setup page: {wp_base}/custom-css-setup/")
    print(f"3. Buka setup page untuk instruksi lengkap")
    print(f"\n🎨 CSS mencakup:")
    print(f"  • Color scheme: Navy + Gold (profesional)")
    print(f"  • Modern card-based article layout")
    print(f"  • Smooth hover animations")
    print(f"  • Better typography & spacing")
    print(f"  • Improved footer design")
    print(f"  • Mobile responsive")
    print(f"  • Custom scrollbar & selection highlight")

if __name__ == '__main__':
    main()
