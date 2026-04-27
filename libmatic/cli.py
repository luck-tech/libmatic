"""libmatic CLI entrypoint.

Phase 1.6: stub から workflow.invoke 結線への置換。
- init は Phase 1.9 で対話 scaffold を実装する予定 (現状 stub)
- suggest-topics / topic-debate / address-pr-comments は workflow を invoke
- resume は checkpointer から thread_id 指定で再開
- graph は mermaid を stdout に出力
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import typer

from libmatic import __version__

app = typer.Typer(
    name="libmatic",
    help="個人の知識ベースを自動運用するためのパイプラインテンプレート。",
    no_args_is_help=True,
    add_completion=False,
)


def _load_config(path: str) -> Any:
    """LibmaticConfig.load の薄いラッパー (CLI のエラー出力用)."""
    from libmatic.config import LibmaticConfig

    p = Path(path)
    if not p.exists():
        typer.echo(f"設定ファイルが見つかりません: {p}", err=True)
        raise typer.Exit(code=1)
    try:
        return LibmaticConfig.load(p)
    except Exception as e:
        typer.echo(f"設定ファイルの読込失敗: {e}", err=True)
        raise typer.Exit(code=1) from e


def _runtime_config(lcfg: Any, thread_id: str) -> dict:
    """LangGraph の RunnableConfig を組み立てる。"""
    return {
        "configurable": {
            "libmatic_config": lcfg,
            "thread_id": thread_id,
        },
        "recursion_limit": lcfg.workflow.max_react_iterations * 2 + 20,
    }


@app.command()
def version() -> None:
    """libmatic のバージョンを表示。"""
    typer.echo(__version__)


@app.command()
def init() -> None:
    """対話形式で libmatic プロジェクトを scaffold する (Phase 1.9 で実装予定)."""
    typer.echo("[stub] libmatic init — Phase 1.9 で実装予定 (対話で provider/preset 選択)")


@app.command("suggest-topics")
def suggest_topics(
    config: str = typer.Option(
        "config/libmatic.yml", "--config", help="設定ファイルのパス"
    ),
) -> None:
    """週次のテーマ候補収集 workflow (A1-A6) を実行する。"""
    from libmatic.checkpointer import build_thread_id, open_checkpointer
    from libmatic.state.suggest_topics import SuggestTopicsState
    from libmatic.workflows.suggest_topics import build_suggest_topics_graph

    lcfg = _load_config(config)
    initial_state = SuggestTopicsState(
        source_priorities_path="config/source_priorities.yml",
    )
    thread_id = build_thread_id("suggest-topics", "weekly")

    typer.echo(f"==> suggest-topics 開始 (thread_id={thread_id})", err=True)
    with open_checkpointer() as saver:
        graph = build_suggest_topics_graph().compile(checkpointer=saver)
        final = graph.invoke(initial_state, config=_runtime_config(lcfg, thread_id))

    created = final.get("created_issues") or []
    new_sources = final.get("new_sources_detected") or []
    typer.echo(f"==> 起票 {len(created)} 件: {created}", err=True)
    if new_sources:
        typer.echo(f"==> 未登録 source 候補 {len(new_sources)} 件: {new_sources}", err=True)


@app.command("topic-debate")
def topic_debate(
    issue: int = typer.Argument(..., help="処理する issue 番号"),
    config: str = typer.Option(
        "config/libmatic.yml", "--config", help="設定ファイルのパス"
    ),
    title: str = typer.Option("", "--title", help="issue タイトル (省略時は gh で取得)"),
    body: str = typer.Option("", "--body", help="issue 本文 (省略時は gh で取得)"),
    lifespan: str = typer.Option("universal", "--lifespan", help="universal / ephemeral"),
) -> None:
    """夜次の議論記事生成 workflow (9 step) を 1 つの issue について実行する。"""
    from libmatic.checkpointer import build_thread_id, open_checkpointer
    from libmatic.state.topic_debate import TopicDebateState
    from libmatic.workflows.topic_debate import build_topic_debate_graph

    lcfg = _load_config(config)

    if not title or not body:
        # gh で issue 取得 (失敗時はユーザー側で --title/--body を渡してもらう)
        try:
            from libmatic.tools.github import _run_gh

            result = _run_gh(
                ["issue", "view", str(issue), "--json", "title,body"]
            )
            data = json.loads(result.stdout)
            title = title or data.get("title") or ""
            body = body or data.get("body") or ""
        except Exception as e:
            typer.echo(f"issue #{issue} の取得失敗: {e}", err=True)
            typer.echo("--title / --body を明示してください", err=True)
            raise typer.Exit(code=1) from e

    if lifespan not in ("universal", "ephemeral"):
        typer.echo(f"--lifespan は universal / ephemeral のみ: {lifespan}", err=True)
        raise typer.Exit(code=1)

    initial_state = TopicDebateState(
        issue_number=issue,
        issue_title=title,
        issue_body=body,
        lifespan=lifespan,  # type: ignore[arg-type]
    )
    thread_id = build_thread_id("topic-debate", issue)

    typer.echo(f"==> topic-debate #{issue} 開始 (thread_id={thread_id})", err=True)
    with open_checkpointer() as saver:
        graph = build_topic_debate_graph().compile(checkpointer=saver)
        final = graph.invoke(initial_state, config=_runtime_config(lcfg, thread_id))

    pr_url = final.get("pr_url")
    pr_number = final.get("pr_number")
    if pr_url:
        typer.echo(f"==> PR 作成: #{pr_number} {pr_url}", err=True)
    else:
        typer.echo("==> PR 作成に至りませんでした (途中で停止)", err=True)


@app.command("address-pr-comments")
def address_pr_comments(
    pr: int = typer.Argument(..., help="対象の PR 番号"),
    config: str = typer.Option(
        "config/libmatic.yml", "--config", help="設定ファイルのパス"
    ),
) -> None:
    """PR レビューコメント対応 workflow (C1-C5) を実行する。"""
    from libmatic.checkpointer import build_thread_id, open_checkpointer
    from libmatic.state.pr_review import PRReviewState
    from libmatic.workflows.pr_review import build_pr_review_graph

    lcfg = _load_config(config)
    initial_state = PRReviewState(pr_number=pr)
    thread_id = build_thread_id("address-pr-comments", pr)

    typer.echo(f"==> address-pr-comments PR #{pr} 開始 (thread_id={thread_id})", err=True)
    with open_checkpointer() as saver:
        graph = build_pr_review_graph().compile(checkpointer=saver)
        final = graph.invoke(initial_state, config=_runtime_config(lcfg, thread_id))

    committed = final.get("committed", False)
    replied = final.get("replied_comment_ids") or []
    typer.echo(
        f"==> 完了 (commit={'yes' if committed else 'no'}, replies={len(replied)})",
        err=True,
    )


@app.command()
def resume(
    thread_id: str = typer.Argument(..., help="再開する checkpointer thread_id"),
    config: str = typer.Option(
        "config/libmatic.yml", "--config", help="設定ファイルのパス"
    ),
) -> None:
    """checkpointer から thread_id を指定して中断 workflow を再開する。

    thread_id 規約: `{workflow}-{primary_key}-{YYYYMMDD}` (例: `topic-debate-18-20260424`)
    """
    from libmatic.checkpointer import open_checkpointer
    from libmatic.workflows.pr_review import build_pr_review_graph
    from libmatic.workflows.suggest_topics import build_suggest_topics_graph
    from libmatic.workflows.topic_debate import build_topic_debate_graph

    lcfg = _load_config(config)

    # thread_id の prefix で workflow を判別
    workflow_builders = {
        "topic-debate": build_topic_debate_graph,
        "suggest-topics": build_suggest_topics_graph,
        "address-pr-comments": build_pr_review_graph,
    }
    builder = None
    for prefix, b in workflow_builders.items():
        if thread_id.startswith(prefix + "-"):
            builder = b
            break
    if builder is None:
        typer.echo(
            f"thread_id から workflow を判別できません: {thread_id}", err=True
        )
        typer.echo(
            f"想定 prefix: {list(workflow_builders)}", err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"==> resume {thread_id}", err=True)
    with open_checkpointer() as saver:
        graph = builder().compile(checkpointer=saver)
        # 既存 state から続行 (input=None で checkpointer から復元)
        final = graph.invoke(None, config=_runtime_config(lcfg, thread_id))

    typer.echo(f"==> 完了: {list(final.keys()) if final else '(empty)'}", err=True)


@app.command()
def graph(
    workflow: str = typer.Argument(
        ..., help="workflow 名 (topic-debate / suggest-topics / address-pr-comments)"
    ),
) -> None:
    """指定 workflow の graph を mermaid 形式で stdout に出力する。"""
    from libmatic.workflows.pr_review import build_pr_review_graph
    from libmatic.workflows.suggest_topics import build_suggest_topics_graph
    from libmatic.workflows.topic_debate import build_topic_debate_graph

    builders = {
        "topic-debate": build_topic_debate_graph,
        "suggest-topics": build_suggest_topics_graph,
        "address-pr-comments": build_pr_review_graph,
    }
    if workflow not in builders:
        typer.echo(f"未知の workflow: {workflow}", err=True)
        typer.echo(f"想定値: {list(builders)}", err=True)
        raise typer.Exit(code=1)

    g = builders[workflow]().compile()
    try:
        mermaid = g.get_graph().draw_mermaid()
    except Exception as e:
        typer.echo(f"mermaid 生成失敗: {e}", err=True)
        raise typer.Exit(code=1) from e
    sys.stdout.write(mermaid)


if __name__ == "__main__":
    app()
