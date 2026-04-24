"""Coverage verification tool (Phase 1.3 stub).

Phase 1.4 で scripts/verify_coverage.py を移植し、step 6 の hybrid node に統合する。
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def verify_coverage(facts: list[dict], article: str) -> dict:
    """facts と article の網羅率を計算し、gap を返す。

    戻り値:
    {
        "score": float,                # 全体の網羅率 [0, 1]
        "primary_coverage": float,      # primary claim の網羅率
        "gaps": list[str],              # 記事に反映されていないトピック
        "verified_count": int,          # 反映された claim 数
        "total_count": int,             # claim 総数
    }
    """
    raise NotImplementedError(
        "Phase 1.4 で実装 (scripts/verify_coverage.py の移植、厳格化ロジック含む)"
    )
