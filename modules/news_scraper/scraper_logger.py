import json
import os
import sys
import threading
import time
from datetime import datetime, timezone


class ScraperLogger:
    """
    Thread-safe structured JSON logger for scraping/upload pipelines.
    - Writes JSON lines to a log file
    - Prints colored output to stdout
    - Buffers entries (30s auto-flush, max 2000 buffered entries)
    - Singleton access via get_logger()
    """

    _instance = None
    _instance_lock = threading.Lock()

    MAX_BUFFER = 2000
    FLUSH_INTERVAL = 30  # seconds

    LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

    # ANSI colors per level
    COLORS = {
        "DEBUG": "\033[36m",     # cyan
        "INFO": "\033[32m",      # green
        "WARNING": "\033[33m",   # yellow
        "ERROR": "\033[31m",     # red
        "CRITICAL": "\033[35m",  # magenta
    }
    RESET = "\033[0m"
    DIM = "\033[2m"

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self, filepath="scraper.log", min_level="DEBUG", use_color=True):
        if getattr(self, "_initialized", False):
            return
        self._initialized = True

        self.filepath = filepath
        self.min_level = self.LEVELS.get(min_level.upper(), 10)
        self.use_color = use_color and sys.stdout.isatty()

        self._buffer = []
        self._lock = threading.RLock()
        self._last_flush = time.time()

        # Ensure file exists
        try:
            open(self.filepath, "a").close()
        except OSError:
            pass

    # ------------------------------------------------------------------ core

    def log(self, level, category, msg, **extra):
        """Log a structured entry. Buffered; flushed every 30s or when full."""
        level = level.upper()
        if self.LEVELS.get(level, 20) < self.min_level:
            return

        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "category": category,
            "msg": msg,
        }
        if extra:
            entry["extra"] = extra

        with self._lock:
            self._print_colored(entry)
            self._buffer.append(entry)

            now = time.time()
            if len(self._buffer) >= self.MAX_BUFFER or (now - self._last_flush) >= self.FLUSH_INTERVAL:
                self.flush()

    def flush(self):
        """Write buffered entries to the log file."""
        with self._lock:
            if not self._buffer:
                return
            try:
                with open(self.filepath, "a", encoding="utf-8") as f:
                    for entry in self._buffer:
                        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError as e:
                sys.stderr.write(f"[ScraperLogger] flush failed: {e}\n")
            finally:
                self._buffer.clear()
                self._last_flush = time.time()

    def close(self):
        self.flush()

    def _print_colored(self, entry):
        color = self.COLORS.get(entry["level"], "") if self.use_color else ""
        reset = self.RESET if color else ""
        dim = self.DIM if self.use_color else ""
        line = (
            f"{color}[{entry['level']:<8}]{reset} "
            f"{dim}{entry['ts'][11:19]}{reset} "
            f"{color}[{entry['category']}]{reset} {entry['msg']}"
        )
        if entry.get("extra"):
            extra_str = " ".join(f"{k}={v}" for k, v in entry["extra"].items())
            line += f" {dim}| {extra_str}{reset}"
        print(line)

    # ------------------------------------------------------- pipeline events

    def scrape_start(self, source, url=None, **extra):
        self.log("INFO", "scrape", f"Scrape started: {source}", source=source, url=url, **extra)

    def scrape_page(self, url, status=None, items_found=0, **extra):
        self.log("DEBUG", "scrape.page", f"Fetched page: {url}",
                 url=url, status=status, items_found=items_found, **extra)

    def scrape_article(self, title, url=None, word_count=None, **extra):
        self.log("INFO", "scrape.article", f"Scraped article: {title}",
                 title=title, url=url, word_count=word_count, **extra)

    def scrape_done(self, total_articles=0, duration_s=None, **extra):
        self.log("INFO", "scrape", f"Scrape finished: {total_articles} articles",
                 total_articles=total_articles, duration_s=duration_s, **extra)

    def upload_start(self, target=None, batch_size=None, **extra):
        self.log("INFO", "upload", f"Upload started: {target}",
                 target=target, batch_size=batch_size, **extra)

    def upload_article(self, post_id=None, title=None, status="published", **extra):
        self.log("INFO", "upload.article", f"Uploaded article: {title or post_id}",
                 post_id=post_id, title=title, status=status, **extra)

    def upload_done(self, uploaded=0, failed=0, duration_s=None, **extra):
        self.log("INFO", "upload", f"Upload finished: {uploaded} ok, {failed} failed",
                 uploaded=uploaded, failed=failed, duration_s=duration_s, **extra)

    def wp_login(self, site, success=True, user=None, **extra):
        level = "INFO" if success else "ERROR"
        self.log(level, "wp.auth", f"WP login {'ok' if success else 'failed'}: {site}",
                 site=site, success=success, user=user, **extra)

    def image_upload(self, filename, media_id=None, size_bytes=None, success=True, **extra):
        level = "INFO" if success else "WARNING"
        self.log(level, "wp.media", f"Image upload {'ok' if success else 'failed'}: {filename}",
                 filename=filename, media_id=media_id, size_bytes=size_bytes, success=success, **extra)

    def tag_create(self, tag, tag_id=None, created=True, **extra):
        action = "created" if created else "reused"
        self.log("DEBUG", "wp.tag", f"Tag {action}: {tag}",
                 tag=tag, tag_id=tag_id, created=created, **extra)

    def backlink_insert(self, post_id=None, anchor=None, target_url=None, **extra):
        self.log("DEBUG", "wp.backlink", f"Backlink inserted in post {post_id}",
                 post_id=post_id, anchor=anchor, target_url=target_url, **extra)

    def rate_limit_hit(self, service=None, retry_after=None, **extra):
        self.log("WARNING", "ratelimit", f"Rate limit hit: {service or 'unknown'}",
                 service=service, retry_after=retry_after, **extra)

    def sitemap_ping(self, search_engine, url=None, success=True, **extra):
        level = "INFO" if success else "WARNING"
        self.log(level, "seo.sitemap", f"Sitemap ping to {search_engine}: {'ok' if success else 'failed'}",
                 engine=search_engine, url=url, success=success, **extra)

    def error(self, msg, exc=None, category="error", **extra):
        if exc is not None:
            extra.setdefault("exception", f"{type(exc).__name__}: {exc}")
        self.log("ERROR", category, msg, **extra)


def get_logger(filepath="scraper.log", min_level=None, use_color=True) -> ScraperLogger:
    """Singleton accessor.

    Level default: env SCRAPER_LOG_LEVEL (default INFO — DEBUG membanjiri log
    dengan baris per-tag saat upload puluhan artikel). Set SCRAPER_LOG_LEVEL=DEBUG
    hanya untuk troubleshooting.
    """
    if min_level is None:
        min_level = os.environ.get('SCRAPER_LOG_LEVEL', 'INFO')
    return ScraperLogger(filepath=filepath, min_level=min_level, use_color=use_color)


if __name__ == "__main__":
    logger = get_logger("demo.log")

    logger.scrape_start("example.com", url="https://example.com/sitemap.xml")
    logger.scrape_page("https://example.com/page/1", status=200, items_found=12)
    logger.scrape_article("Sample Article", url="https://example.com/a/1", word_count=850)
    logger.rate_limit_hit("example.com", retry_after=60)
    logger.error("Something broke", exc=ValueError("bad value"), page="/page/3")
    logger.scrape_done(total_articles=12, duration_s=42.5)

    logger.wp_login("https://mysite.com", success=True, user="admin")
    logger.upload_start("https://mysite.com", batch_size=12)
    logger.image_upload("cover.jpg", media_id=101, size_bytes=204800)
    logger.tag_create("python", tag_id=7)
    logger.backlink_insert(post_id=55, anchor="read more", target_url="https://example.com/a/1")
    logger.upload_article(post_id=55, title="Sample Article")
    logger.upload_done(uploaded=11, failed=1, duration_s=120.3)
    logger.sitemap_ping("google", url="https://mysite.com/sitemap.xml")

    logger.close()
