"""X (Twitter) fetch via fxtwitter / vxtwitter proxy.

my_library の scripts/fetch_x.py の移植。CLI を削除して Source を返す pure 関数に再構成。
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import UTC, datetime
from urllib.parse import urlparse

from libmatic.state.topic_debate import Source

BACKENDS = ["api.fxtwitter.com", "api.vxtwitter.com"]
USER_AGENT = "Mozilla/5.0 (compatible; libmatic/0.1)"
DEFAULT_TIMEOUT = 15


def parse_x_url(url: str) -> tuple[str, str]:
    """X URL から (username, tweet_id) を抽出。"""
    p = urlparse(url)
    parts = [s for s in p.path.split("/") if s]
    if len(parts) < 3 or parts[1] != "status":
        raise ValueError(f"解釈できない X URL: {url}")
    return parts[0], parts[2]


def http_get_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> dict | None:
    """JSON GET。失敗時は None。"""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None
    except Exception:
        return None


def try_backends(username: str, tweet_id: str, thread: bool) -> dict | None:
    """各 backend を順に試す。成功したら data を返す。"""
    suffix = "/thread" if thread else ""
    for backend in BACKENDS:
        endpoint = f"https://{backend}/{username}/status/{tweet_id}{suffix}"
        data = http_get_json(endpoint)
        if data is None:
            continue
        if data.get("code") == 200 or "tweet" in data or "tweets" in data:
            return data
    return None


def format_timestamp(ts: int | None) -> str:
    if not ts:
        return ""
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _author_full(author: dict) -> str:
    """'山田太郎 (@taro)' のような文字列を組み立てる。"""
    handle = author.get("screen_name") or author.get("handle") or ""
    name = author.get("name") or ""
    if handle and name and name != handle:
        return f"{name} (@{handle})"
    if handle:
        return f"@{handle}"
    return name


def tweet_to_md(tweet: dict, *, level: int = 0) -> list[str]:
    """1 ツイート → md 行のリスト。引用ツイートは入れ子 quote として再帰。"""
    indent = "> " * level if level > 0 else ""
    lines: list[str] = []

    author = tweet.get("author", {})
    author_name = author.get("name", "")
    author_handle = author.get("screen_name") or author.get("handle") or ""
    ts = tweet.get("created_timestamp")
    ts_s = format_timestamp(ts)
    url = tweet.get("url", "")

    header = f"{indent}**@{author_handle}** ({author_name})"
    if ts_s:
        header += f" — {ts_s}"
    lines.append(header)
    lines.append(indent.rstrip())

    text = tweet.get("text") or ""
    for t_line in text.splitlines():
        lines.append(f"{indent}{t_line}")
    lines.append(indent.rstrip())

    media = tweet.get("media", {})
    photos = media.get("photos") or []
    videos = media.get("videos") or []
    if photos:
        lines.append(f"{indent}**添付画像**:")
        for p in photos:
            lines.append(f"{indent}- {p.get('url', '')}")
        lines.append(indent.rstrip())
    if videos:
        lines.append(f"{indent}**添付動画**:")
        for v in videos:
            lines.append(f"{indent}- {v.get('url', '')}")
        lines.append(indent.rstrip())

    if url:
        lines.append(f"{indent}元URL: {url}")
        lines.append(indent.rstrip())

    quote = tweet.get("quote")
    if quote:
        lines.append(f"{indent}**引用元**:")
        lines.append(indent.rstrip())
        lines.extend(tweet_to_md(quote, level=level + 1))

    return lines


_EXCLUDED_URL_HOSTS = (
    "x.com/",
    "twitter.com/",
    "mobile.twitter.com/",
    "t.co/",
    "pbs.twimg.com",
    "video.twimg.com",
    "abs.twimg.com",
)


def extract_quoted_urls(tweet: dict) -> list[str]:
    """ツイートから引用されている外部 URL を抽出。

    entities.urls の expanded_url を優先し、本文正規表現で fallback。
    X 内部 URL / t.co / 画像・動画 URL は除外。
    """
    urls: list[str] = []
    entities = tweet.get("entities") or {}
    for u in entities.get("urls") or []:
        expanded = u.get("expanded_url") or u.get("url")
        if expanded:
            urls.append(expanded)
    text = tweet.get("text") or ""
    for m in re.finditer(r"https?://[^\s　]+", text):
        urls.append(m.group(0).rstrip(".,)】）"))
    filtered: list[str] = []
    for u in urls:
        if any(ex in u for ex in _EXCLUDED_URL_HOSTS):
            continue
        if u not in filtered:
            filtered.append(u)
    return filtered


def collect_thread_urls(tweets: list[dict]) -> list[str]:
    seen: list[str] = []
    for tw in tweets:
        for u in extract_quoted_urls(tw):
            if u not in seen:
                seen.append(u)
    return seen


def _append_quoted_urls_section(lines: list[str], urls: list[str]) -> None:
    if not urls:
        return
    lines.append("")
    lines.append("## 引用リンク")
    lines.append("")
    lines.append("このポスト/スレッドで言及・引用されている外部リンク。")
    lines.append("")
    for u in urls:
        lines.append(f"- {u}")


def render_single(data: dict, url: str) -> str:
    tweet = data.get("tweet", data)
    author = tweet.get("author", {})
    published = format_timestamp(tweet.get("created_timestamp"))
    lines = [f"# X ポスト: @{author.get('screen_name', '')}", ""]
    lines.append(f"**出典**: {url}")
    if author:
        lines.append(f"**著者**: {_author_full(author)}")
    if published:
        lines.append(f"**公開日**: {published}")
    lines.append(f"**取得日時**: {datetime.now(UTC).isoformat()}")
    lines.append("")
    lines.extend(tweet_to_md(tweet))
    _append_quoted_urls_section(lines, extract_quoted_urls(tweet))
    return "\n".join(lines) + "\n"


def render_thread(data: dict, url: str) -> str:
    tweets = data.get("tweets") or []
    if not tweets and "tweet" in data:
        return render_single(data, url)
    first = tweets[0] if tweets else {}
    first_author = first.get("author", {})
    first_published = format_timestamp(first.get("created_timestamp"))
    lines = [f"# X スレッド: @{first_author.get('screen_name', '')}", ""]
    lines.append(f"**出典**: {url}")
    if first_author:
        lines.append(f"**著者**: {_author_full(first_author)}")
    if first_published:
        lines.append(f"**公開日**: {first_published}")
    lines.append(f"**ツイート数**: {len(tweets)}")
    lines.append(f"**取得日時**: {datetime.now(UTC).isoformat()}")
    lines.append("")
    for i, tw in enumerate(tweets, 1):
        lines.append(f"## ({i}/{len(tweets)})")
        lines.append("")
        lines.extend(tweet_to_md(tw))
        lines.append("")
    _append_quoted_urls_section(lines, collect_thread_urls(tweets))
    return "\n".join(lines) + "\n"


def fetch_x_core(url: str, thread: bool = True) -> Source:
    """X URL を取得して Source を返す。

    全 backend 失敗時は fetched_content=None の Source を返す (呼出側で skip 判定)。
    """
    username, tweet_id = parse_x_url(url)
    data = try_backends(username, tweet_id, thread=thread)
    if data is None:
        return Source(
            url=url,
            type="x",
            title=f"@{username}/status/{tweet_id}",
            fetched_content=None,
        )

    md = render_thread(data, url) if thread else render_single(data, url)

    if thread and data.get("tweets"):
        first = data["tweets"][0]
    else:
        first = data.get("tweet", data)
    author = first.get("author", {})
    handle = author.get("screen_name", username)
    text_preview = (first.get("text") or "").replace("\n", " ")[:80]
    title = f"@{handle}: {text_preview}" if text_preview else f"@{handle}"
    published = format_timestamp(first.get("created_timestamp")) or None

    return Source(
        url=url,
        type="x",
        title=title,
        published_at=published,
        fetched_content=md,
    )
