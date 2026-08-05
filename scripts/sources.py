"""
Data source fetchers for the daily news digest.

Three sources, all free and no login/signature reverse-engineering needed:
  - 知乎热榜: official public API (browser UA only)
  - 知乎日报: RSSHub public instances /zhihu/daily
  - 观察者网: RSSHub public instances /guancha/all + /guancha/fengwen

Each fetcher returns a list of dicts with stable fields (see make_item).
"""

import html
import re
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import requests

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
}

# Public RSSHub instances, tried in order (the first that yields items wins).
# Individual public instances are flaky, so the fallback list keeps the
# RSSHub-backed sources (知乎日报, 观察者网) resilient.
RSSHUB_INSTANCES = [
    "https://hub.slarker.me",        # verified reachable
    "https://rsshub.rssforever.com",
    "https://rsshub.app",
]


def clean_text(value, max_chars=500):
    """Strip HTML and whitespace noise from source summaries."""
    text = html.unescape(value or "")
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:max_chars]


def normalize_url(url):
    """Normalize URLs so the same story is easier to dedupe."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"}
    ]
    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path.rstrip("/"),
        urlencode(query, doseq=True),
        "",
    ))


def normalize_title(title):
    return re.sub(r"\W+", "", (title or "").lower())


def make_item(category, title, url, summary, source, published=None, metadata=None):
    """Build one digest item with a stable schema."""
    return {
        "category": category,
        "title": clean_text(title, max_chars=220),
        "url": url or "",
        "normalized_url": normalize_url(url),
        "summary": clean_text(summary),
        "source": source,
        "published": published,
        "metadata": metadata or {},
    }


def dedupe_items(items):
    """Deduplicate by normalized URL first, then normalized title."""
    seen = {}
    url_index = {}
    title_index = {}

    for item in items:
        url_key = item.get("normalized_url")
        title_key = normalize_title(item.get("title"))
        key = url_index.get(url_key) or title_index.get(title_key)

        if not key:
            key = url_key or title_key
        if not key:
            continue

        previous = seen.get(key)
        if not previous:
            seen[key] = item
            if url_key:
                url_index[url_key] = key
            if title_key:
                title_index[title_key] = key
            continue

        if len(item.get("summary", "")) > len(previous.get("summary", "")):
            item["source"] = f"{previous['source']}, {item['source']}"
            seen[key] = item
            if url_key:
                url_index[url_key] = key
            if title_key:
                title_index[title_key] = key
        else:
            previous["source"] = f"{previous['source']}, {item['source']}"

    return list(seen.values())


def fetch_zhihu_hot(max_items=20):
    """知乎热榜 via official public API — no login, browser UA only."""
    items = []
    url = f"https://api.zhihu.com/topstory/hot-lists/total?limit={max_items}&reverse_order=0"
    for attempt in range(3):
        try:
            resp = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            for entry in data.get("data", [])[:max_items]:
                target = entry.get("target", {})
                title = target.get("title", "")
                if not title:
                    continue
                question_id = target.get("id")
                link = f"https://www.zhihu.com/question/{question_id}"
                excerpt = target.get("excerpt") or target.get("excerpt_new") or ""
                heat = entry.get("detail_text", "")
                items.append(make_item(
                    category="news",
                    title=title,
                    url=link,
                    summary=excerpt,
                    source="知乎热榜",
                    published=datetime.fromtimestamp(target.get("created", 0), tz=timezone.utc).isoformat()
                    if target.get("created") else None,
                    metadata={"heat": heat},
                ))
            break
        except Exception as e:
            if attempt < 2:
                print(f"  [知乎热榜] Attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(2 * (attempt + 1))
            else:
                print(f"  [知乎热榜] Error after 3 attempts: {e}")
    return items


def rsshub(path):
    """Candidate URLs for an rsshub route across all configured instances."""
    return [instance + path for instance in RSSHUB_INSTANCES]


def fetch_rss_feed(feed_url, source_name, max_items=10, cutoff_days=2):
    """Generic RSS fetcher with retry; returns a list of items (may be empty)."""
    items = []
    for attempt in range(3):
        try:
            resp = requests.get(feed_url, headers=BROWSER_HEADERS, timeout=20)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            cutoff = datetime.now(timezone.utc) - timedelta(days=cutoff_days)
            for entry in feed.entries:
                if len(items) >= max_items:
                    break
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                published_at = None
                if published:
                    entry_date = datetime(*published[:6], tzinfo=timezone.utc)
                    if entry_date < cutoff:
                        continue
                    published_at = entry_date.isoformat()
                items.append(make_item(
                    category="news",
                    title=entry.get("title", ""),
                    url=entry.get("link", ""),
                    summary=entry.get("summary", ""),
                    source=source_name,
                    published=published_at,
                    metadata={"feed_url": feed_url},
                ))
            break
        except Exception as e:
            if attempt < 2:
                print(f"  [{source_name}] Attempt {attempt + 1} failed: {e}, retrying...")
                time.sleep(2 * (attempt + 1))
            else:
                print(f"  [{source_name}] Error after 3 attempts: {e}")
    return items


def fetch_via_rsshub(path, source_name, max_items=10, cutoff_days=1):
    """Fetch an RSSHub route across all instances; first working one wins."""
    for instance in RSSHUB_INSTANCES:
        items = fetch_rss_feed(instance + path, source_name, max_items=max_items, cutoff_days=cutoff_days)
        if items:
            return items
    print(f"  [{source_name}] All RSSHub instances failed.")
    return []


def fetch_all():
    """Fetch from all sources, return deduplicated news items."""
    print("Fetching 知乎热榜 (official API)...")
    zhihu_hot = fetch_zhihu_hot(max_items=20)
    print(f"  Got {len(zhihu_hot)} items")

    print("Fetching 知乎日报 (RSSHub)...")
    zhihu_daily = fetch_via_rsshub("/zhihu/daily", "知乎日报", max_items=10, cutoff_days=1)
    print(f"  Got {len(zhihu_daily)} items")

    print("Fetching 观察者网 头条 (RSSHub)...")
    guancha_headline = fetch_via_rsshub("/guancha/headline", "观察者网·头条", max_items=1, cutoff_days=2)
    print(f"  Got {len(guancha_headline)} items")

    print("Fetching 观察者网 要闻 (RSSHub)...")
    guancha_story = fetch_via_rsshub("/guancha/story", "观察者网·要闻", max_items=8, cutoff_days=1)
    print(f"  Got {len(guancha_story)} items")

    raw = zhihu_hot + zhihu_daily + guancha_headline + guancha_story
    items = dedupe_items(raw)
    print(f"Deduped {len(raw)} raw items to {len(items)} unique items")
    return items
