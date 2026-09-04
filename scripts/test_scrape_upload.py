#!/usr/bin/env python3
"""
Standalone test: scrape articles → upload to WP → report results.
Bypasses Flask session/auth so we can test the scraper engine directly.
"""
import os, sys, json, time

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Suppress Flask warnings
os.environ.setdefault('FLASK_ENV', 'development')

from modules.news_scraper.scraper_engine import scrape_newsmaker, fetch_article_content
from modules.news_scraper.wp_client import WpClient
from modules.news_scraper.seo_optimizer import (
    rewrite_content, build_article_html, build_advanced_schema,
    seo_analyze, apply_backlinks, normalize_title
)
from modules.news_scraper import WP_SITES_FILE, BACKLINKS_FILE, DEFAULT_AUTHORITY_SITES, DEFAULT_KEYWORD_MAPPING

def load_json(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return default

def main():
    # ── STEP 1: Scrape ──
    print("=" * 60)
    print("STEP 1: Scraping articles from Newsmaker.id...")
    print("=" * 60)
    
    articles = scrape_newsmaker(pages=1)
    print(f"  Found {len(articles)} articles from newsmaker.id")
    
    # ── STEP 2: Fetch content ──
    print("\nSTEP 2: Fetching article content...")
    with_content = 0
    without_content = 0
    for i, art in enumerate(articles):
        fetch_article_content(art)
        if art.get('content') and art['content'] != 'Content not found':
            with_content += 1
        else:
            without_content += 1
            print(f"  ⚠️  No content: {art['title'][:60]}...")
        # Update progress
        if (i + 1) % 10 == 0:
            print(f"  Progress: {i+1}/{len(articles)} fetched")
    
    print(f"  Content: {with_content} OK, {without_content} failed")
    
    # Filter articles with content
    ready = [a for a in articles if a.get('content') and a['content'] != 'Content not found']
    print(f"  {len(ready)} articles ready for upload")
    
    if not ready:
        print("\n❌ No articles with content — nothing to upload")
        return
    
    # ── STEP 3: Upload to BPF Surabaya ──
    print("\n" + "=" * 60)
    print("STEP 3: Uploading to BPF Surabaya...")
    print("=" * 60)
    
    sites = load_json(WP_SITES_FILE, {})
    site_name = "BPF Surabaya"
    if site_name not in sites:
        print(f"❌ Site '{site_name}' not found in config")
        return
    
    site = sites[site_name]
    print(f"  WP URL: {site['wp_url']}")
    print(f"  Username: {site['username']}")
    
    # Build client (with fallback basic auth)
    fallback = None
    bu = site.get('basic_username', '').strip()
    bp = site.get('basic_password', '').strip()
    if bu and bp:
        fallback = (bu, bp)
    
    client = WpClient(site['wp_url'], site['username'], site['app_password'],
                      fallback_auth=fallback)
    
    print("\n  Logging in...")
    ok, msg = client.login()
    if not ok:
        print(f"  ❌ Login failed: {msg}")
        return
    print(f"  ✅ Login OK: {msg}")
    
    # Get existing posts for duplicate detection
    existing_titles = set()
    existing_posts = {}
    print("  Fetching existing posts for duplicate check...")
    for page in range(1, 6):
        try:
            r = client.get_posts(client.active_auth[1] if hasattr(client, 'active_auth') else '',
                                 params={"per_page": 100, "page": page, "orderby": "date", "order": "desc"})
            if r.status_code != 200 or not r.json():
                break
            for post in r.json():
                t = post.get('title', {}).get('rendered', '')
                existing_titles.add(t)
                existing_posts[t] = post.get('id')
            if len(r.json()) < 100:
                break
            time.sleep(0.2)
        except Exception as e:
            print(f"  ⚠️  Error fetching existing posts page {page}: {e}")
            break
    print(f"  Found {len(existing_titles)} existing posts")
    
    # Load backlinks config
    bl_config = load_json(BACKLINKS_FILE, {})
    authority_sites = bl_config.get('authority_sites', DEFAULT_AUTHORITY_SITES)
    keyword_mapping = bl_config.get('keyword_mapping', DEFAULT_KEYWORD_MAPPING)
    
    # ── STEP 4: Process each article ──
    print(f"\n  Processing {len(ready)} articles...")
    new_count = 0
    update_count = 0
    skip_count = 0
    errors = []
    
    for idx, article in enumerate(ready):
        title = article.get('title', '')
        content = article.get('content', '')
        
        if not content or content == "Content not found":
            skip_count += 1
            continue
        
        print(f"\n  [{idx+1}/{len(ready)}] {title[:60]}...")
        
        # Rewrite content for uniqueness
        content = rewrite_content(content, title)
        
        # Build HTML
        publish_date = article.get('publish_date', time.strftime('%Y-%m-%d'))
        publish_time = article.get('publish_time', '08:00')
        if not publish_time:
            publish_time = '08:00'
        
        html_content = build_article_html(title, content, article, publish_date, publish_time)
        
        # SEO analysis
        analysis = seo_analyze(html_content, title)
        seo_score = analysis['seo_score']
        print(f"    SEO Score: {seo_score}/100")
        
        # Apply backlinks
        html_content, backlinks_used = apply_backlinks(html_content, title, authority_sites, keyword_mapping, 3)
        
        # Add schema
        schemas = build_advanced_schema(title, content, publish_date, publish_time, article.get('image_url', ''))
        schema_tags = ''.join(f'<script type="application/ld+json">{json.dumps(s, ensure_ascii=False)}</script>' for s in schemas)
        html_content = schema_tags + html_content
        
        # Tags
        static_tags = 'newsmaker.id, Market, Geopolitics, Financial News'
        tag_input = [t.strip().capitalize() for t in static_tags.split(',') if t.strip()]
        title_words = [w.capitalize() for w in title.lower().split()
                       if w not in {'dan', 'di', 'ke', 'dari', 'yang', 'untuk', 'dengan', 'ini', 'itu'} and len(w) > 3]
        all_tags = list(set(tag_input + title_words[:5]))
        
        tag_ids = []
        for tag_name in all_tags:
            try:
                tag_id = client.get_or_create_tag(tag_name, client.active_auth[1])
                if tag_id is not None:
                    tag_ids.append(tag_id)
            except Exception as e:
                print(f"    ⚠️  Tag '{tag_name}' failed: {e}")
        
        # Check for duplicate
        is_duplicate = False
        matched_post_id = None
        norm_title = normalize_title(title)
        for et in existing_titles:
            if title == et or norm_title == normalize_title(et):
                is_duplicate = True
                matched_post_id = existing_posts.get(et)
                break
        
        # Upload/Update
        try:
            post_data = {
                'title': title,
                'content': html_content,
                'status': 'publish',
                'date': f"{publish_date}T{publish_time}:00",
                'tags': tag_ids,
                'featured_media': 0,
            }
            
            # Content size safety check
            content_bytes = len(html_content.encode('utf-8'))
            if content_bytes > 120 * 1024:
                print(f"    ⚠️  Content too large ({content_bytes} bytes) — truncating")
                schema_end = html_content.rfind('<!-- BPF CTA Widget -->')
                if schema_end > 0:
                    html_content = html_content[:schema_end]
                html_content = html_content[:120*1024].rsplit('\n', 1)[0] + '\n</article>'
                post_data['content'] = html_content
            
            if is_duplicate and matched_post_id:
                # Update existing post (using PUT)
                r = client.update_post(matched_post_id, {'content': post_data['content'], 'tags': tag_ids}, client.active_auth[1])
                if r.status_code == 200:
                    update_count += 1
                    print(f"    ✅ Updated (post #{matched_post_id})")
                else:
                    error_body = r.text[:200] if hasattr(r, 'text') else ''
                    errors.append(f"{title}: HTTP {r.status_code} — {error_body}")
                    print(f"    ❌ Update failed: HTTP {r.status_code} — {error_body}")
            elif is_duplicate:
                # Search and update
                r = client.search_posts(title, client.active_auth[1], timeout=15)
                if r.status_code == 200:
                    found = False
                    for post in r.json():
                        if normalize_title(post.get('title', {}).get('rendered', '')) == norm_title:
                            r2 = client.update_post(post['id'], {'content': post_data['content'], 'tags': tag_ids}, client.active_auth[1])
                            if r2.status_code == 200:
                                update_count += 1
                                print(f"    ✅ Updated (post #{post['id']})")
                            else:
                                error_body = r2.text[:200] if hasattr(r2, 'text') else ''
                                errors.append(f"{title}: HTTP {r2.status_code} — {error_body}")
                                print(f"    ❌ Update failed: HTTP {r2.status_code} — {error_body}")
                            found = True
                            break
                    if not found:
                        print(f"    ⚠️  Duplicate title matched but post not found in search")
                else:
                    print(f"    ⚠️  Search failed: HTTP {r.status_code}")
            else:
                # Create new post
                r = client.create_post(post_data, client.active_auth[1])
                if r.status_code == 201:
                    new_count += 1
                    print(f"    ✅ Created (post #{r.json().get('id')})")
                else:
                    error_body = r.text[:200] if hasattr(r, 'text') else ''
                    errors.append(f"{title}: HTTP {r.status_code} — {error_body}")
                    print(f"    ❌ Create failed: HTTP {r.status_code} — {error_body}")
        
        except Exception as e:
            errors.append(f"{title}: {str(e)}")
            print(f"    ❌ Exception: {e}")
    
    # ── SUMMARY ──
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"  New posts:     {new_count}")
    print(f"  Updated posts: {update_count}")
    print(f"  Errors:        {len(errors)}")
    if errors:
        for e in errors:
            print(f"    - {e[:100]}")
    print(f"  Skipped (no content): {skip_count}")

if __name__ == '__main__':
    main()
