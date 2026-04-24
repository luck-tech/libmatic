"""URL dispatcher + media-specific fetchers.

my_library の scripts/fetch_source.py の移植。LangChain @tool + Source dataclass。
YouTube は optional addon (libmatic-addon-youtube) の領分、v0.1 では placeholder。
"""

from __future__ import annotations

import hashlib
import html as html_module
import json
import re
import subprocess
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse

try:
    import trafilatura  # type: ignore[import-untyped]

    _HAS_TRAFILATURA = True
except ImportError:
    _HAS_TRAFILATURA = False

from langchain_core.tools import tool

from libmatic.state.topic_debate import Source, SourceType
from libmatic.tools.x_fetch import fetch_x_core

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}
X_HOSTS = {
    "x.com",
    "www.x.com",
    "twitter.com",
    "www.twitter.com",
    "mobile.twitter.com",
}
ZENN_HOSTS = {"zenn.dev"}
QIITA_HOSTS = {"qiita.com"}
GITHUB_HOSTS = {"github.com", "www.github.com"}
RFC_HOSTS = {"www.rfc-editor.org", "datatracker.ietf.org"}

USER_AGENT = "Mozilla/5.0 (compatible; libmatic/0.1)"
DEFAULT_TIMEOUT = 30


def classify(url: str) -> SourceType:
    """URL の host を見て media 種別 (SourceType) を判定する。"""
    host = urlparse(url).netloc.lower()
    if host in YOUTUBE_HOSTS:
        return "youtube"
    if host in X_HOSTS:
        return "x"
    if host in ZENN_HOSTS:
        return "zenn"
    if host in QIITA_HOSTS:
        return "qiita"
    if host in GITHUB_HOSTS:
        return "github"
    if host in RFC_HOSTS:
        return "rfc"
    return "generic"


def extract_youtube_id(url: str) -> str:
    """YouTube URL から video ID を抽出 (失敗時は URL の SHA1 先頭 11 文字)。"""
    p = urlparse(url)
    if p.netloc == "youtu.be":
        return p.path.lstrip("/").split("/")[0]
    qs = parse_qs(p.query)
    if "v" in qs:
        return qs["v"][0]
    return hashlib.sha1(url.encode()).hexdigest()[:11]


def http_get(
    url: str, *, accept: str | None = None, timeout: int = DEFAULT_TIMEOUT
) -> str | None:
    """HTTP GET (UTF-8 decoded)。失敗時は None。"""
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None
    except Exception:
        return None


def strip_html_to_text(html: str) -> str:
    """HTML → plain text (stdlib のみ、簡易抽出)。

    article / main があればその中身を優先、無ければ body、無ければ全体。
    script/style/nav/header/footer/aside/svg は除去。
    """
    html = re.sub(
        r"<(script|style|nav|header|footer|aside|svg)[^>]*>.*?</\1>",
        "",
        html,
        flags=re.DOTALL | re.IGNORECASE,
    )
    m = re.search(r"<(article|main)[^>]*>(.*?)</\1>", html, re.DOTALL | re.IGNORECASE)
    if m:
        body = m.group(2)
    else:
        mb = re.search(r"<body[^>]*>(.*?)</body>", html, re.DOTALL | re.IGNORECASE)
        body = mb.group(1) if mb else html
    body = re.sub(r"<br\s*/?>", "\n", body, flags=re.IGNORECASE)
    body = re.sub(r"</p\s*>", "\n\n", body, flags=re.IGNORECASE)
    body = re.sub(r"</(div|section|li|h[1-6])\s*>", "\n", body, flags=re.IGNORECASE)
    body = re.sub(r"</(tr|table)\s*>", "\n", body, flags=re.IGNORECASE)
    body = re.sub(r"<[^>]+>", "", body)
    body = html_module.unescape(body)
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n[ \t]+", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def extract_title(html: str) -> str:
    """<title> または og:title から title を抽出。"""
    m = re.search(r"<title[^>]*>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if m:
        return html_module.unescape(m.group(1).strip())
    m = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)',
        html,
        re.IGNORECASE,
    )
    if m:
        return html_module.unescape(m.group(1).strip())
    return ""


def extract_published_at(html: str) -> str | None:
    """OGP article:published_time / meta pubdate / <time datetime=...> から公開日。"""
    for pattern in (
        r'<meta[^>]+property=["\']article:published_time["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\']pubdate["\'][^>]+content=["\']([^"\']+)',
        r'<time[^>]+datetime=["\']([^"\']+)',
    ):
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _render_generic_content(html: str, url: str) -> tuple[str, str, str]:
    """HTML → (title, content_md, published_at)。trafilatura 優先、fallback stdlib。"""
    title = ""
    published = ""
    text = ""

    if _HAS_TRAFILATURA:
        try:
            data = trafilatura.bare_extraction(
                html,
                url=url,
                include_comments=False,
                include_tables=True,
                with_metadata=True,
                favor_precision=True,
            )
            if data is not None:
                get = (
                    (lambda k: getattr(data, k, None))
                    if not isinstance(data, dict)
                    else data.get
                )
                title = get("title") or ""
                published = get("date") or ""
                text = (
                    trafilatura.extract(
                        html,
                        url=url,
                        include_comments=False,
                        include_tables=True,
                        output_format="markdown",
                        favor_precision=True,
                    )
                    or ""
                )
        except Exception:
            pass

    if not text:
        title = title or extract_title(html)
        published = published or extract_published_at(html) or ""
        text = strip_html_to_text(html)

    return title or url, text, published or ""


# --- media-specific core fetchers (pure → Source) ---


def fetch_web_core(url: str, type_override: SourceType = "generic") -> Source:
    """Generic HTML → Source。失敗時は fetched_content=None。"""
    html = http_get(url)
    if html is None:
        return Source(url=url, type=type_override, title=url, fetched_content=None)
    title, content, published = _render_generic_content(html, url)
    return Source(
        url=url,
        type=type_override,
        title=title,
        published_at=published or None,
        fetched_content=content,
    )


def fetch_zenn_core(url: str) -> Source:
    return fetch_web_core(url, type_override="zenn")


def fetch_qiita_core(url: str) -> Source:
    """Qiita API v2 (認証不要) で記事を取得。"""
    p = urlparse(url)
    parts = [s for s in p.path.split("/") if s]
    if len(parts) < 3 or parts[1] != "items":
        raise ValueError(f"解釈できない Qiita URL: {url}")
    item_id = parts[2]
    api_url = f"https://qiita.com/api/v2/items/{item_id}"
    raw = http_get(api_url, accept="application/json")
    if raw is None:
        return Source(url=url, type="qiita", title=url, fetched_content=None)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return Source(url=url, type="qiita", title=url, fetched_content=None)
    title = data.get("title", "")
    body = data.get("body") or data.get("rendered_body", "")
    user = data.get("user", {})
    author = user.get("id") or user.get("name", "")
    created = data.get("created_at", "")
    md_lines = [f"# {title}", ""]
    md_lines.append(f"**出典**: {url}")
    if author:
        md_lines.append(f"**著者**: @{author}")
    if created:
        md_lines.append(f"**公開日**: {created}")
    md_lines.append("")
    md_lines.append(body)
    return Source(
        url=url,
        type="qiita",
        title=title or url,
        published_at=created or None,
        fetched_content="\n".join(md_lines) + "\n",
    )


def fetch_rfc_core(url: str) -> Source:
    """RFC/IETF docs: rfc-editor は .txt を取得、datatracker は HTML 汎用で。"""
    p = urlparse(url)
    fetch_url = url
    if p.netloc == "www.rfc-editor.org":
        m = re.search(r"/rfc/(rfc\d+)(?:\.html)?/?$", p.path)
        if m:
            fetch_url = f"https://www.rfc-editor.org/rfc/{m.group(1)}.txt"
    raw = http_get(fetch_url)
    if raw is None:
        return Source(url=url, type="rfc", title=url, fetched_content=None)
    if fetch_url.endswith(".txt"):
        title_m = re.search(r"^\s*(RFC \d+\s+.+)$", raw, re.MULTILINE)
        title = title_m.group(1).strip() if title_m else fetch_url
        md = f"# {title}\n\n**出典**: {url}\n\n```\n{raw}\n```\n"
        return Source(url=url, type="rfc", title=title, fetched_content=md)
    title, content, published = _render_generic_content(raw, url)
    return Source(
        url=url,
        type="rfc",
        title=title,
        published_at=published or None,
        fetched_content=content,
    )


def _github_is_issue_or_pr(path_parts: list[str]) -> str | None:
    """/owner/repo/issues/N or /owner/repo/pull/N を判別。該当なら kind を返す。"""
    if len(path_parts) < 4:
        return None
    if path_parts[2] == "issues":
        return "issue"
    if path_parts[2] == "pull":
        return "pr"
    return None


def fetch_github_core(url: str) -> Source:
    """GitHub issue/PR は gh api で、それ以外は汎用 HTML 取得。"""
    p = urlparse(url)
    parts = [s for s in p.path.split("/") if s]
    kind = _github_is_issue_or_pr(parts)
    if kind is None:
        return fetch_web_core(url, type_override="github")

    try:
        result = subprocess.run(
            [
                "gh",
                "issue" if kind == "issue" else "pr",
                "view",
                url,
                "--json",
                "number,title,body,author,createdAt,comments,labels,state",
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        data = json.loads(result.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError):
        return fetch_web_core(url, type_override="github")

    number = data.get("number", "?")
    title = f"[{kind.upper()}] #{number} {data.get('title', '')}"
    author = (data.get("author") or {}).get("login", "")
    created = data.get("createdAt", "")
    labels = [lb.get("name") for lb in (data.get("labels") or [])]
    state = data.get("state", "")
    lines = [f"# {title}", ""]
    lines.append(f"**出典**: {url}")
    if author:
        lines.append(f"**投稿者**: @{author}")
    if created:
        lines.append(f"**作成日**: {created}")
    if labels:
        lines.append(f"**ラベル**: {', '.join(labels)}")
    if state:
        lines.append(f"**状態**: {state}")
    lines.append("")
    lines.append("## 本文")
    lines.append("")
    lines.append(data.get("body") or "_(本文なし)_")
    comments = data.get("comments") or []
    if comments:
        lines.append("")
        lines.append(f"## コメント ({len(comments)})")
        for c in comments:
            c_author = (c.get("author") or {}).get("login", "")
            c_at = c.get("createdAt", "")
            lines.append("")
            lines.append(f"### @{c_author} — {c_at}")
            lines.append("")
            lines.append(c.get("body", ""))
    return Source(
        url=url,
        type="github",
        title=title,
        published_at=created or None,
        fetched_content="\n".join(lines) + "\n",
    )


def fetch_youtube_core(url: str) -> Source:
    """YouTube は optional addon (libmatic-addon-youtube) の領分。

    v0.1 では placeholder を返す (fetched_content=None で呼出側が skip できる)。
    """
    return Source(
        url=url,
        type="youtube",
        title="(YouTube URL — install libmatic-addon-youtube to fetch transcripts)",
        fetched_content=None,
    )


def fetch_source_core(url: str, thread: bool = False) -> Source:
    """URL を判定して対応 fetcher に dispatch、Source を返す。"""
    media = classify(url)
    if media == "youtube":
        return fetch_youtube_core(url)
    if media == "x":
        return fetch_x_core(url, thread=thread)
    if media == "zenn":
        return fetch_zenn_core(url)
    if media == "qiita":
        return fetch_qiita_core(url)
    if media == "github":
        return fetch_github_core(url)
    if media == "rfc":
        return fetch_rfc_core(url)
    return fetch_web_core(url, type_override="generic")


# --- LangChain @tool wrappers ---


@tool
def fetch_source(url: str, thread: bool = False) -> dict:
    """URL の type を判定し、type 別に fetch して Source dict を返す。

    Args:
        url: 取得対象 URL
        thread: X URL の場合、スレッド全体を取得する (他 type では無視)

    Returns:
        Source dict: {url, type, title, published_at, score, fetched_content}
        取得失敗時は fetched_content=None の Source を返す (呼出側で判定)
    """
    return fetch_source_core(url, thread=thread).model_dump()


@tool
def fetch_x_thread(url: str) -> dict:
    """X URL を強制的にスレッドとして取得する (fetch_source(url, thread=True) と等価)."""
    return fetch_source_core(url, thread=True).model_dump()
