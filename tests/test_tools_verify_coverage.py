"""Tests for libmatic.tools.coverage (Phase 1.4 PoC #2)."""

from __future__ import annotations

import pytest

from libmatic.tools.coverage import (
    CoverageReport,
    CoverageStats,
    UncoveredClaim,
    build_report_md,
    claim_covered,
    compute_coverage,
    normalize_for_match,
    strip_sections,
    verify_coverage_core,
)

# --- normalize_for_match ---


def test_normalize_full_width_space() -> None:
    assert normalize_for_match("A　B") == "A B"


def test_normalize_consecutive_spaces() -> None:
    assert normalize_for_match("A     B") == "A B"


def test_normalize_newlines_and_tabs() -> None:
    assert normalize_for_match("A\n\n\tB") == "A B"


def test_normalize_empty_or_none() -> None:
    assert normalize_for_match("") == ""
    assert normalize_for_match(None) == ""


# --- strip_sections ---


SAMPLE_ARTICLE = """# 記事タイトル

## 本論

本論の内容。重要な主張が書かれている。

## 補遺：未反映論点の簡潔カバー

補遺セクション。coverage から除外したい。

## 結論

ここは残したい結論段落。
"""


def test_strip_sections_removes_matching_heading() -> None:
    out = strip_sections(SAMPLE_ARTICLE, ["補遺"])
    assert "補遺" not in out
    assert "補遺セクション" not in out


def test_strip_sections_preserves_other_sections() -> None:
    out = strip_sections(SAMPLE_ARTICLE, ["補遺"])
    assert "本論の内容" in out
    assert "残したい結論段落" in out


def test_strip_sections_no_match_keeps_all() -> None:
    out = strip_sections(SAMPLE_ARTICLE, ["存在しない見出し"])
    assert out == SAMPLE_ARTICLE


def test_strip_sections_empty_patterns_keeps_all() -> None:
    assert strip_sections(SAMPLE_ARTICLE, []) == SAMPLE_ARTICLE


def test_strip_sections_empty_text() -> None:
    assert strip_sections("", ["any"]) == ""


def test_strip_sections_stops_at_next_same_level_heading() -> None:
    # ## 補遺 を消すと、次の ## 結論 以降は残る
    out = strip_sections(SAMPLE_ARTICLE, ["補遺"])
    assert "## 結論" in out
    # 補遺 から次の見出しの前までの内容は全部消える
    assert "補遺セクション" not in out
    assert "coverage から除外したい" not in out


def test_strip_sections_matches_at_h1_level() -> None:
    text = "# 削除対象\n本文\n# 残す\n本文B\n"
    out = strip_sections(text, ["削除対象"])
    assert "削除対象" not in out
    assert "残す" in out


# --- claim_covered ---


def test_claim_covered_by_verbatim_probe() -> None:
    claim = {"verbatim": "React 19 の use API が重要な変更点", "text": ""}
    article = "React 19 の use API が重要な変更点である、と著者は主張。"
    is_cov, reason = claim_covered(claim, article)
    assert is_cov
    assert "verbatim" in reason


def test_claim_covered_by_text_fallback() -> None:
    claim = {"verbatim": "", "text": "Suspense 境界の新仕様について"}
    article = "記事本文。Suspense 境界の新仕様についての議論。"
    is_cov, reason = claim_covered(claim, article)
    assert is_cov
    assert "text" in reason


def test_claim_not_covered() -> None:
    claim = {"verbatim": "全く記事に書かれていない独自主張", "text": "別論点"}
    article = "本記事は React 19 の use API だけを扱う。"
    is_cov, _ = claim_covered(claim, article)
    assert not is_cov


def test_claim_short_probe_skipped() -> None:
    # 8 文字未満の probe は偶発一致防止で match しない
    claim = {"verbatim": "短い", "text": "短文"}
    article = "短い短文でも一致しないこと。"
    is_cov, _ = claim_covered(claim, article)
    assert not is_cov


def test_claim_whitespace_normalized_for_match() -> None:
    claim = {"verbatim": "React 19 の use API", "text": ""}
    article = "React  19  の　use   API (全角/連続空白/タブ)"
    is_cov, _ = claim_covered(claim, article)
    assert is_cov


def test_claim_verbatim_takes_priority() -> None:
    # verbatim でヒットすれば text は見に行かない (戻り値の reason で確認)
    claim = {
        "verbatim": "verbatim 優先の主張キーワード",
        "text": "text だけ独自の 8 文字以上",
    }
    article = "verbatim 優先の主張キーワードを本文に含む。"
    is_cov, reason = claim_covered(claim, article)
    assert is_cov
    assert reason.startswith("verbatim")


# --- compute_coverage ---


ARCHIVES_SAMPLE = [
    {
        "source_id": "src1",
        "claims": [
            {
                "id": "c1",
                "verbatim": "Next.js 15 の cache 戦略は段階的に変わる",
                "text": "Next.js 15 の cache API",
                "relevance_to_theme": "primary",
                "category": "design-principle",
            },
            {
                "id": "c2",
                "verbatim": "TypeScript Go コンパイラで 10 倍の高速化",
                "text": "tsgo の性能向上",
                "relevance_to_theme": "secondary",
                "category": "number",
            },
        ],
    },
    {
        "source_id": "src2",
        "claims": [
            {
                "id": "c3",
                "verbatim": "全く触れられていないはずの主張内容",
                "text": "",
                "relevance_to_theme": "tangential",
                "category": "quote",
            },
        ],
    },
]


def test_compute_coverage_partial() -> None:
    article = "Next.js 15 の cache 戦略は段階的に変わる という議論がある。"
    stats = compute_coverage(ARCHIVES_SAMPLE, article)
    assert stats.total == 3
    assert stats.covered == 1
    assert stats.rate == pytest.approx(33.33, rel=0.01)
    assert stats.by_relevance["primary"] == (1, 1)
    assert stats.by_relevance["secondary"] == (0, 1)
    assert stats.by_relevance["tangential"] == (0, 1)
    assert stats.by_source["src1"] == (1, 2)
    assert stats.by_source["src2"] == (0, 1)
    assert len(stats.uncovered) == 2


def test_compute_coverage_full_match() -> None:
    article = (
        "Next.js 15 の cache 戦略は段階的に変わる。"
        "TypeScript Go コンパイラで 10 倍の高速化。"
        "全く触れられていないはずの主張内容まで言及する包括記事。"
    )
    stats = compute_coverage(ARCHIVES_SAMPLE, article)
    assert stats.covered == 3
    assert stats.rate == 100.0
    assert stats.uncovered == []


def test_compute_coverage_empty_archives() -> None:
    stats = compute_coverage([], "記事テキスト")
    assert stats.total == 0
    assert stats.rate == 0.0
    assert stats.by_relevance == {}
    assert stats.by_source == {}


def test_compute_coverage_empty_article() -> None:
    stats = compute_coverage(ARCHIVES_SAMPLE, "")
    assert stats.covered == 0
    assert stats.rate == 0.0


def test_compute_coverage_uncovered_contains_claim_details() -> None:
    stats = compute_coverage(ARCHIVES_SAMPLE, "何も触れていない記事")
    assert stats.covered == 0
    # 全 claim が uncovered に含まれる
    assert len(stats.uncovered) == 3
    source_ids = {u.source_id for u in stats.uncovered}
    assert source_ids == {"src1", "src2"}


# --- verify_coverage_core (pure) ---


def test_verify_coverage_core_combined_pass() -> None:
    article = (
        "Next.js 15 の cache 戦略は段階的に変わる。"
        "TypeScript Go コンパイラで 10 倍の高速化。"
        "全く触れられていないはずの主張内容も網羅。"
    )
    report = verify_coverage_core(
        claims_archive=ARCHIVES_SAMPLE,
        articles=[article],
        combined_threshold=95.0,
    )
    assert report.combined.rate == 100.0
    assert report.combined_pass
    assert report.primary is None
    assert report.primary_pass  # 検証していないので常に True
    assert report.overall_pass


def test_verify_coverage_core_combined_fail() -> None:
    article = "Next.js 15 の cache 戦略は段階的に変わる。"
    report = verify_coverage_core(
        claims_archive=ARCHIVES_SAMPLE,
        articles=[article],
        combined_threshold=95.0,
    )
    assert report.combined.rate < 95.0
    assert not report.combined_pass
    assert not report.overall_pass


def test_verify_coverage_core_primary_threshold_checks_first_article() -> None:
    # primary 記事 (1 つ目) は 1/3、合計では 3/3
    primary = "Next.js 15 の cache 戦略は段階的に変わる。"
    secondary = (
        "TypeScript Go コンパイラで 10 倍の高速化。"
        "全く触れられていないはずの主張内容に言及。"
    )
    report = verify_coverage_core(
        claims_archive=ARCHIVES_SAMPLE,
        articles=[primary, secondary],
        combined_threshold=95.0,
        primary_threshold=70.0,
    )
    assert report.combined.rate == 100.0
    assert report.combined_pass
    assert report.primary is not None
    assert report.primary.rate == pytest.approx(33.33, rel=0.01)
    assert not report.primary_pass
    assert not report.overall_pass  # primary で落ちるので全体 FAIL


def test_verify_coverage_core_exclude_sections_removes_content() -> None:
    # 補遺セクションでのみカバーしているなら coverage は下がる
    article_with_appendix = (
        "# 記事\n\n"
        "## 本論\n\n記事の冒頭。\n\n"
        "## 補遺：未反映論点\n\n"
        "Next.js 15 の cache 戦略は段階的に変わる。"
        "TypeScript Go コンパイラで 10 倍の高速化。\n"
    )
    # 補遺除外しない場合: 2/3 ヒット
    report_without_exclude = verify_coverage_core(
        claims_archive=ARCHIVES_SAMPLE,
        articles=[article_with_appendix],
    )
    assert report_without_exclude.combined.covered == 2

    # 補遺を除外すると 0/3 に落ちる
    report_with_exclude = verify_coverage_core(
        claims_archive=ARCHIVES_SAMPLE,
        articles=[article_with_appendix],
        exclude_sections=["補遺"],
    )
    assert report_with_exclude.combined.covered == 0


def test_verify_coverage_core_empty_articles_raises() -> None:
    with pytest.raises(ValueError):
        verify_coverage_core(claims_archive=ARCHIVES_SAMPLE, articles=[])


def test_verify_coverage_core_report_md_contains_summary() -> None:
    article = "Next.js 15 の cache 戦略は段階的に変わる。"
    report = verify_coverage_core(
        claims_archive=ARCHIVES_SAMPLE,
        articles=[article],
        combined_threshold=95.0,
    )
    md = report.report_md
    assert "# 記事カバレッジレポート" in md
    assert "## サマリ" in md
    assert "FAIL" in md  # 33% なので FAIL
    assert "未反映 claim 一覧" in md


def test_verify_coverage_core_report_md_shows_pass_on_success() -> None:
    article = (
        "Next.js 15 の cache 戦略は段階的に変わる。"
        "TypeScript Go コンパイラで 10 倍の高速化。"
        "全く触れられていないはずの主張内容まで記述。"
    )
    report = verify_coverage_core(
        claims_archive=ARCHIVES_SAMPLE,
        articles=[article],
        combined_threshold=95.0,
    )
    assert report.combined_pass
    assert "PASS" in report.report_md
    assert "FAIL" not in report.report_md


# --- @tool wrapper ---


def test_verify_coverage_tool_invoke() -> None:
    """LangChain @tool 経由でも同じ結果が得られる。"""
    from libmatic.tools.coverage import verify_coverage

    article = "Next.js 15 の cache 戦略は段階的に変わる。"
    result = verify_coverage.invoke(
        {
            "claims_archive": ARCHIVES_SAMPLE,
            "articles": [article],
            "combined_threshold": 95.0,
        }
    )
    assert isinstance(result, dict)
    assert result["combined"]["total"] == 3
    assert result["combined"]["covered"] == 1
    assert not result["combined_pass"]
    assert "report_md" in result


def test_verify_coverage_tool_invoke_with_primary_threshold() -> None:
    from libmatic.tools.coverage import verify_coverage

    articles = [
        "primary 記事は 1/3 しかヒットしない。Next.js 15 の cache 戦略は段階的に変わる。",
        (
            "secondary が補う。TypeScript Go コンパイラで 10 倍の高速化。"
            "全く触れられていないはずの主張内容に言及。"
        ),
    ]
    result = verify_coverage.invoke(
        {
            "claims_archive": ARCHIVES_SAMPLE,
            "articles": articles,
            "combined_threshold": 95.0,
            "primary_threshold": 70.0,
        }
    )
    assert result["combined_pass"]
    assert not result["primary_pass"]  # primary で失敗
    assert not result["overall_pass"]
    assert result["primary"]["rate"] == pytest.approx(33.33, rel=0.01)


# --- models ---


def test_coverage_stats_defaults() -> None:
    s = CoverageStats()
    assert s.total == 0
    assert s.rate == 0.0
    assert s.by_relevance == {}


def test_uncovered_claim_minimal() -> None:
    u = UncoveredClaim(
        source_id="s1",
        claim_id="c1",
        relevance="primary",
        category="number",
    )
    assert u.text == ""
    assert u.verbatim == ""


def test_build_report_md_shows_exclude_sections_note() -> None:
    stats = CoverageStats(total=0, covered=0, rate=0.0)
    md = build_report_md(
        combined=stats,
        primary=None,
        combined_threshold=95.0,
        primary_threshold=None,
        combined_pass=True,  # total=0 で technically True 扱い
        primary_pass=True,
        exclude_sections=["補遺", "付録"],
    )
    assert "除外セクション: 補遺, 付録" in md


def test_coverage_report_roundtrip() -> None:
    stats = CoverageStats(total=3, covered=1, rate=33.3)
    r = CoverageReport(
        combined=stats,
        primary=None,
        combined_threshold=95.0,
        primary_threshold=None,
        combined_pass=False,
        primary_pass=True,
        overall_pass=False,
        report_md="# x",
    )
    d = r.model_dump()
    assert d["combined"]["total"] == 3
    assert d["combined_pass"] is False
    assert d["report_md"] == "# x"
