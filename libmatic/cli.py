"""libmatic CLI entrypoint (Phase 1.1 stub)."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="libmatic",
    help="個人の知識ベースを自動運用するためのパイプラインテンプレート。",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def init() -> None:
    """対話形式で libmatic プロジェクトを scaffold する (Phase 1.9 で実装)."""
    typer.echo("[stub] libmatic init — Phase 1.9 で実装予定")


@app.command("suggest-topics")
def suggest_topics(
    config: str = typer.Option("config/libmatic.yml", "--config", help="設定ファイルのパス"),
) -> None:
    """週次のテーマ候補収集 workflow を実行 (Phase 1.3 以降で実装)."""
    typer.echo(f"[stub] suggest-topics --config {config}")


@app.command("topic-debate")
def topic_debate(
    issue: int | None = typer.Argument(
        None, help="処理する issue 番号 (省略時は topic/ready から LRU pick)"
    ),
) -> None:
    """夜次の議論記事生成 workflow (9 step) を実行 (Phase 1.3 以降で実装)."""
    target = str(issue) if issue is not None else "LRU"
    typer.echo(f"[stub] topic-debate {target}")


@app.command("address-pr-comments")
def address_pr_comments(
    pr: int = typer.Argument(..., help="対象の PR 番号"),
) -> None:
    """PR レビューコメントへの自動対応 workflow を実行 (Phase 1.3 以降で実装)."""
    typer.echo(f"[stub] address-pr-comments {pr}")


@app.command()
def resume(
    thread_id: str = typer.Argument(..., help="再開する checkpointer thread_id"),
) -> None:
    """中断した workflow を thread_id から再開 (Phase 1.3 以降で実装)."""
    typer.echo(f"[stub] resume {thread_id}")


@app.command()
def graph(
    workflow: str = typer.Argument(
        ..., help="workflow 名 (suggest-topics / topic-debate / address-pr-comments)"
    ),
) -> None:
    """指定 workflow の graph を mermaid 形式で stdout に出力 (Phase 1.3 以降で実装)."""
    typer.echo(f"[stub] graph {workflow}")


if __name__ == "__main__":
    app()
