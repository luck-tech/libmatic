"""Coverage verification tool.

my_library の scripts/verify_coverage.py を LangChain tool 化した移植版。
記事テキストが claims_archive をどれだけ反映しているかを文字列マッチで検証する。

Phase 0 決定 (libmatic-oss-plan.md §3.3 d): Phase 1.4 PoC #2。hybrid node
(verify_coverage tool で数値、LLM judge で gap 言語化) の基盤になる。
"""

from __future__ import annotations

import re

from langchain_core.tools import tool
from pydantic import BaseModel, Field

DEFAULT_COMBINED_THRESHOLD = 95.0
DEFAULT_VERBATIM_PROBE_LEN = 20
DEFAULT_TEXT_PROBE_LEN = 15
MIN_PROBE_CHARS = 8


class UncoveredClaim(BaseModel):
    """未反映 claim の情報 (report に含める)."""

    source_id: str
    claim_id: str
    relevance: str
    category: str
    text: str = ""
    verbatim: str = ""


class CoverageStats(BaseModel):
    """単一のテキストに対する coverage 統計."""

    total: int = 0
    covered: int = 0
    rate: float = 0.0
    by_relevance: dict[str, tuple[int, int]] = Field(default_factory=dict)
    by_source: dict[str, tuple[int, int]] = Field(default_factory=dict)
    uncovered: list[UncoveredClaim] = Field(default_factory=list)


class CoverageReport(BaseModel):
    """verify_coverage tool の完全な戻り値."""

    combined: CoverageStats
    primary: CoverageStats | None = None
    combined_threshold: float
    primary_threshold: float | None = None
    combined_pass: bool
    primary_pass: bool
    overall_pass: bool
    report_md: str


# --- pure helpers ---


def normalize_for_match(text: str | None) -> str:
    """全角空白・連続空白・改行を除去して matching 用に正規化。"""
    if not text:
        return ""
    t = text.replace("　", " ")
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def strip_sections(text: str, patterns: list[str]) -> str:
    """見出しパターンに部分一致する ## / # セクションを丸ごと除去する。

    次の同レベル以上の見出しが現れるまで (または EOF まで) を 1 セクションと扱う。
    """
    if not patterns or not text:
        return text

    lines = text.splitlines(keepends=True)
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        heading_match = re.match(r"^(#{1,2}) +(.+?)\s*$", line)
        if heading_match:
            heading_text = heading_match.group(2)
            if any(p in heading_text for p in patterns):
                i += 1
                while i < len(lines):
                    if re.match(r"^#{1,2} +", lines[i]):
                        break
                    i += 1
                continue
        out.append(line)
        i += 1
    return "".join(out)


def claim_covered(claim: dict, articles_text: str) -> tuple[bool, str]:
    """claim が記事テキストに含まれているか判定。

    - verbatim の先頭 20 文字 (長ければ truncate) を probe として in-check
    - text の先頭 15 文字を fallback
    - probe が 8 文字未満なら偶発一致防止で skip
    """
    normalized_articles = normalize_for_match(articles_text)

    verbatim = normalize_for_match(claim.get("verbatim") or "")
    if verbatim:
        probe = verbatim[:DEFAULT_VERBATIM_PROBE_LEN]
        if probe and len(probe) >= MIN_PROBE_CHARS and probe in normalized_articles:
            return True, f"verbatim:{probe[:30]}"

    text = normalize_for_match(claim.get("text") or "")
    if text:
        probe = text[:DEFAULT_TEXT_PROBE_LEN]
        if probe and len(probe) >= MIN_PROBE_CHARS and probe in normalized_articles:
            return True, f"text:{probe[:30]}"

    return False, ""


def compute_coverage(
    claims_archive: list[dict],
    articles_text: str,
) -> CoverageStats:
    """記事テキストに対する claim 反映率を集計する (LLM 呼出なし、決定的)."""
    total = 0
    covered = 0
    by_relevance: dict[str, list[int]] = {}
    by_source: dict[str, list[int]] = {}
    uncovered: list[UncoveredClaim] = []

    for arc in claims_archive:
        sid = arc.get("source_id", "unknown")
        by_source.setdefault(sid, [0, 0])
        for c in arc.get("claims") or []:
            total += 1
            by_source[sid][1] += 1
            rel = c.get("relevance_to_theme", "none")
            by_relevance.setdefault(rel, [0, 0])
            by_relevance[rel][1] += 1
            is_cov, _ = claim_covered(c, articles_text)
            if is_cov:
                covered += 1
                by_source[sid][0] += 1
                by_relevance[rel][0] += 1
            else:
                uncovered.append(
                    UncoveredClaim(
                        source_id=sid,
                        claim_id=str(c.get("id", "?")),
                        relevance=rel,
                        category=str(c.get("category", "?")),
                        text=(c.get("text") or "")[:120],
                        verbatim=(c.get("verbatim") or "")[:80],
                    )
                )

    rate = (covered / total * 100) if total else 0.0
    return CoverageStats(
        total=total,
        covered=covered,
        rate=rate,
        by_relevance={k: (v[0], v[1]) for k, v in by_relevance.items()},
        by_source={k: (v[0], v[1]) for k, v in by_source.items()},
        uncovered=uncovered,
    )


def build_report_md(
    combined: CoverageStats,
    primary: CoverageStats | None,
    combined_threshold: float,
    primary_threshold: float | None,
    combined_pass: bool,
    primary_pass: bool,
    article_labels: list[str] | None = None,
    exclude_sections: list[str] | None = None,
) -> str:
    """Coverage 結果を markdown 文字列に整形する。"""
    lines = ["# 記事カバレッジレポート", ""]
    if article_labels:
        lines.append(f"- 対象記事: {', '.join(article_labels)}")
    if exclude_sections:
        lines.append(f"- 除外セクション: {', '.join(exclude_sections)}")
    lines.append("")

    lines.append("## サマリ")
    lines.append("")
    lines.append(f"- **総 claims**: {combined.total}")
    lines.append(
        f"- **反映済 (合計)**: {combined.covered} ({combined.rate:.1f}%) "
        f"[閾値 {combined_threshold}%, {'PASS ✅' if combined_pass else 'FAIL ❌'}]"
    )
    if primary is not None and primary_threshold is not None:
        lines.append(
            f"- **反映済 (primary)**: {primary.covered} ({primary.rate:.1f}%) "
            f"[閾値 {primary_threshold}%, {'PASS ✅' if primary_pass else 'FAIL ❌'}]"
        )
    overall = combined_pass and primary_pass
    lines.append(f"- **総合判定**: {'PASS ✅' if overall else 'FAIL ❌'}")
    lines.append("")

    # relevance 別 (既知の順序を優先)
    if combined.by_relevance:
        lines.append("### relevance 別 (合計)")
        lines.append("")
        lines.append("| relevance | 反映 / 総数 | 反映率 |")
        lines.append("|---|---|---|")
        known_order = ("primary", "secondary", "tangential", "none")
        shown: set[str] = set()
        for rel in known_order:
            if rel not in combined.by_relevance:
                continue
            cov, tot = combined.by_relevance[rel]
            if tot == 0:
                continue
            r = (cov / tot * 100) if tot else 0.0
            lines.append(f"| {rel} | {cov} / {tot} | {r:.1f}% |")
            shown.add(rel)
        for rel, (cov, tot) in combined.by_relevance.items():
            if rel in shown or tot == 0:
                continue
            r = (cov / tot * 100) if tot else 0.0
            lines.append(f"| {rel} | {cov} / {tot} | {r:.1f}% |")
        lines.append("")

    # source 別
    if combined.by_source:
        lines.append("### source 別 (合計)")
        lines.append("")
        lines.append("| source_id | 反映 / 総数 | 反映率 |")
        lines.append("|---|---|---|")
        for sid, (c, t) in sorted(combined.by_source.items()):
            r = (c / t * 100) if t else 0.0
            marker = "✅" if r >= 90 else ("⚠️" if r >= 60 else "❌")
            lines.append(f"| {sid} | {c} / {t} | {r:.1f}% {marker} |")
        lines.append("")

    # primary のみで未反映 (補助記事のおかげで合計 PASS しているケースのあぶり出し)
    if primary is not None and primary.uncovered:
        combined_uncovered_keys = {(u.source_id, u.claim_id) for u in combined.uncovered}
        primary_only_gaps = [
            u for u in primary.uncovered if (u.source_id, u.claim_id) not in combined_uncovered_keys
        ]
        if primary_only_gaps:
            lines.append(f"## primary 記事のみで未反映 ({len(primary_only_gaps)} 件)")
            lines.append("")
            lines.append("合計では反映済みだが primary 記事に言及がない。補遺行きで済ませず、")
            lines.append("primary の本文に織り込むべき論点の候補。")
            lines.append("")
            rel_order = {"primary": 0, "secondary": 1, "tangential": 2, "none": 3}
            primary_only_gaps.sort(
                key=lambda u: (rel_order.get(u.relevance, 9), u.source_id, u.claim_id)
            )
            for u in primary_only_gaps:
                lines.append(
                    f"- **{u.source_id}#{u.claim_id}** ({u.relevance}/{u.category}): {u.text}"
                )
                if u.verbatim:
                    lines.append(f"  - 原文: {u.verbatim}")
            lines.append("")

    if combined.uncovered:
        lines.append(f"## 未反映 claim 一覧 ({len(combined.uncovered)} 件)")
        lines.append("")
        rel_order = {"primary": 0, "secondary": 1, "tangential": 2, "none": 3}
        sorted_uncov = sorted(
            combined.uncovered,
            key=lambda u: (rel_order.get(u.relevance, 9), u.source_id, u.claim_id),
        )
        for u in sorted_uncov:
            lines.append(
                f"- **{u.source_id}#{u.claim_id}** ({u.relevance}/{u.category}): {u.text}"
            )
            if u.verbatim:
                lines.append(f"  - 原文: {u.verbatim}")
        lines.append("")

    return "\n".join(lines) + "\n"


def verify_coverage_core(
    claims_archive: list[dict],
    articles: list[str],
    combined_threshold: float = DEFAULT_COMBINED_THRESHOLD,
    primary_threshold: float | None = None,
    exclude_sections: list[str] | None = None,
    article_labels: list[str] | None = None,
) -> CoverageReport:
    """verify_coverage の pure 関数実装 (LangChain tool ラッパー抜きで test 可能)."""
    if not articles:
        raise ValueError("articles must not be empty")

    exclude = exclude_sections or []
    processed = [strip_sections(a, exclude) for a in articles]

    combined_text = "\n\n".join(processed)
    combined = compute_coverage(claims_archive, combined_text)

    primary: CoverageStats | None = None
    primary_pass = True
    if primary_threshold is not None:
        primary = compute_coverage(claims_archive, processed[0])
        primary_pass = primary.rate >= primary_threshold

    combined_pass = combined.rate >= combined_threshold
    overall_pass = combined_pass and primary_pass

    report_md = build_report_md(
        combined=combined,
        primary=primary,
        combined_threshold=combined_threshold,
        primary_threshold=primary_threshold,
        combined_pass=combined_pass,
        primary_pass=primary_pass,
        article_labels=article_labels,
        exclude_sections=exclude if exclude else None,
    )

    return CoverageReport(
        combined=combined,
        primary=primary,
        combined_threshold=combined_threshold,
        primary_threshold=primary_threshold,
        combined_pass=combined_pass,
        primary_pass=primary_pass,
        overall_pass=overall_pass,
        report_md=report_md,
    )


# --- LangChain @tool wrapper ---


@tool
def verify_coverage(
    claims_archive: list[dict],
    articles: list[str],
    combined_threshold: float = DEFAULT_COMBINED_THRESHOLD,
    primary_threshold: float | None = None,
    exclude_sections: list[str] | None = None,
) -> dict:
    """記事テキストが claims_archive をどれだけ反映しているかを文字列マッチで検証する。

    Args:
        claims_archive: [{source_id, claims: [{id, text, verbatim,
            relevance_to_theme, category}, ...]}, ...]
        articles: 記事テキスト (articles[0] が primary、以降が補助記事)
        combined_threshold: 合計反映率の合格閾値 (%)、default 95
        primary_threshold: primary 記事単独の最低反映率 (%)。None なら
            primary 検証をスキップ
        exclude_sections: マッチング前に除外する ## 見出しの部分一致パターン
            (例: ["補遺"] で補遺セクションを coverage 外す)

    Returns:
        CoverageReport dict:
            {combined, primary, combined_threshold, primary_threshold,
             combined_pass, primary_pass, overall_pass, report_md}
    """
    report = verify_coverage_core(
        claims_archive=claims_archive,
        articles=articles,
        combined_threshold=combined_threshold,
        primary_threshold=primary_threshold,
        exclude_sections=exclude_sections,
    )
    return report.model_dump()
