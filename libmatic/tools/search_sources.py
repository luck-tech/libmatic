"""Search sources tool — RSS/Atom feed 巡回 + theme マッチ.

my_library の scripts/search_sources.py を LangChain tool 化した移植版。
CLI entrypoint は削除し、pure 関数 + `@tool` wrapper に再構成。

Phase 0 決定 (libmatic-oss-plan.md §3.3 d): Phase 1.4 の最初の PoC として、
LangChain tool 化の手順とプロジェクト骨格を固める足掛かり。
"""

from __future__ import annotations

import re
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

import yaml
from langchain_core.tools import tool
from pydantic import BaseModel

USER_AGENT = "Mozilla/5.0 (compatible; libmatic/0.1)"
DEFAULT_TIMEOUT = 15
DEFAULT_MAX_ITEMS_PER_FEED = 20


class FeedEntry(BaseModel):
    """Parsed entry from an RSS/Atom feed."""

    title: str
    link: str
    published: str = ""


class Candidate(BaseModel):
    """Theme-matched source candidate."""

    url: str
    title: str
    domain: str
    media: str  # youtube / x / zenn / qiita / github / rfc / web
    published_at: str = ""
    discovered_by: str = "feed"


# --- HTTP + parser (pure, network を差し替え可能) ---


def http_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> str | None:
    """HTTP GET. 失敗時は None を返す (log は呼出元の判断に任せる)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    except Exception:
        return None


def _extract_tag(body: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", body, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    text = m.group(1).strip()
    text = re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", "", text)
    return text.strip()


def parse_rss(xml: str) -> list[FeedEntry]:
    items: list[FeedEntry] = []
    for m in re.finditer(r"<item[^>]*>(.*?)</item>", xml, re.DOTALL | re.IGNORECASE):
        body = m.group(1)
        title = _extract_tag(body, "title")
        link = _extract_tag(body, "link")
        pub = _extract_tag(body, "pubDate") or _extract_tag(body, "dc:date")
        if title and link:
            items.append(FeedEntry(title=title, link=link, published=pub or ""))
    return items


def parse_atom(xml: str) -> list[FeedEntry]:
    items: list[FeedEntry] = []
    for m in re.finditer(r"<entry[^>]*>(.*?)</entry>", xml, re.DOTALL | re.IGNORECASE):
        body = m.group(1)
        title = _extract_tag(body, "title")
        lm = re.search(r'<link[^>]+href=["\']([^"\']+)["\']', body, re.IGNORECASE)
        link = lm.group(1) if lm else ""
        pub = _extract_tag(body, "published") or _extract_tag(body, "updated")
        if title and link:
            items.append(FeedEntry(title=title, link=link, published=pub or ""))
    return items


def parse_feed(xml: str) -> list[FeedEntry]:
    """RSS / Atom の自動判別 + parse."""
    if "<feed" in xml and "xmlns" in xml and "atom" in xml.lower():
        return parse_atom(xml)
    if "<rss" in xml:
        return parse_rss(xml)
    if "<entry" in xml:
        return parse_atom(xml)
    return parse_rss(xml)


def fetch_feed(feed_url: str, max_items: int = DEFAULT_MAX_ITEMS_PER_FEED) -> list[FeedEntry]:
    """feed URL を取得して parse。失敗時は空リスト。"""
    raw = http_get(feed_url)
    if raw is None:
        return []
    return parse_feed(raw)[:max_items]


# --- theme matcher / media classifier ---


def extract_keywords(theme: str) -> list[str]:
    """Theme から検索キーワードを抽出 (ASCII 英数 + 非 ASCII トークン)."""
    words = re.findall(r"[A-Za-z0-9]+|[^\x00-\x7f]+", theme)
    return [w.lower() for w in words if len(w) >= 2]


def matches_theme(text: str, keywords: list[str]) -> bool:
    """部分一致ベースの緩いマッチング (いずれかのキーワードが含まれれば hit)."""
    t = text.lower()
    return any(kw in t for kw in keywords)


def classify_media(url: str) -> str:
    """URL の host から media 種別を判定."""
    host = urlparse(url).netloc.lower()
    if "youtube.com" in host or "youtu.be" in host:
        return "youtube"
    if "x.com" in host or "twitter.com" in host:
        return "x"
    if host == "zenn.dev":
        return "zenn"
    if host == "qiita.com":
        return "qiita"
    if "github.com" in host:
        return "github"
    if host in ("www.rfc-editor.org", "datatracker.ietf.org"):
        return "rfc"
    return "web"


# --- source_priorities.yml から feed を展開 ---


def collect_feeds_from_priorities(path: str | Path) -> list[str]:
    """source_priorities.yml から blogs[].feed + zenn/qiita/youtube の RSS を展開."""
    p = Path(path)
    if not p.exists():
        return []
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    feeds: list[str] = []
    for blog in data.get("blogs") or []:
        fd = blog.get("feed")
        if fd:
            feeds.append(fd)
    for zuser in (data.get("zenn") or {}).get("users") or []:
        h = zuser.get("handle")
        if h:
            feeds.append(f"https://zenn.dev/{h}/feed")
    for quser in (data.get("qiita") or {}).get("users") or []:
        h = quser.get("handle")
        if h:
            feeds.append(f"https://qiita.com/{h}/feed.atom")
    # YouTube channels は channel_id (UC 始まり) が必要
    for ch in (data.get("youtube") or {}).get("channels") or []:
        ch_id = ch.get("id")
        if ch_id and ch_id.startswith("UC"):
            feeds.append(f"https://www.youtube.com/feeds/videos.xml?channel_id={ch_id}")
    return feeds


# --- main logic (pure function) ---


def search_feeds(
    theme: str,
    feeds: list[str],
    extra_keywords: list[str] | None = None,
    max_items_per_feed: int = DEFAULT_MAX_ITEMS_PER_FEED,
) -> list[Candidate]:
    """Theme × feeds から候補 URL を抽出 (LLM 呼出なし、決定的).

    同じ URL は dedup される。feed 自体の順序は保持するが、dict.fromkeys で
    重複 feed URL も除去。
    """
    keywords = extract_keywords(theme)
    if extra_keywords:
        keywords.extend([k.lower() for k in extra_keywords])

    seen: set[str] = set()
    candidates: list[Candidate] = []

    for feed_url in dict.fromkeys(feeds):  # feed 重複排除 (順序保持)
        entries = fetch_feed(feed_url, max_items=max_items_per_feed)
        for e in entries:
            if not matches_theme(e.title, keywords):
                continue
            if e.link in seen:
                continue
            seen.add(e.link)
            candidates.append(
                Candidate(
                    url=e.link,
                    title=e.title,
                    domain=urlparse(e.link).netloc,
                    media=classify_media(e.link),
                    published_at=e.published,
                    discovered_by="feed",
                )
            )
    return candidates


# --- LangChain @tool wrapper ---


@tool
def search_sources(
    theme: str,
    feeds: list[str] | None = None,
    priorities_path: str | None = None,
    extra_keywords: list[str] | None = None,
) -> list[dict]:
    """テーマ関連の RSS/Atom feed を巡回して候補 URL を抽出する。

    Args:
        theme: 検索テーマ (日英混在可)
        feeds: feed URL のリスト (直接指定、priorities_path と併用可)
        priorities_path: source_priorities.yml のパス (指定時は blogs/zenn/
            qiita/youtube のハンドルから feed URL を自動展開する)
        extra_keywords: theme 以外の追加キーワード (optional)

    Returns:
        候補 dict のリスト。各 dict は
        {url, title, domain, media, published_at, discovered_by} を持つ。
        feed URL が 1 つも無い場合は空リストを返す。
    """
    all_feeds: list[str] = list(feeds or [])
    if priorities_path:
        all_feeds.extend(collect_feeds_from_priorities(priorities_path))
    if not all_feeds:
        return []
    candidates = search_feeds(theme, all_feeds, extra_keywords)
    return [c.model_dump() for c in candidates]
