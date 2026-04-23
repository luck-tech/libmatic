# libmatic

**個人の知識ベースを自動運用するためのパイプラインテンプレート**

週次で信頼発信者の RSS / YouTube / X と Web 検索を自動巡回し、議論価値のあるテーマを GitHub issue として起票。人が `topic/ready` に昇格した issue を夜次で 1 本ずつ pick し、ソース取得 → 事実抽出 → 網羅性検証 → 原本 + 初学者向け拡張版の 2 本立てで記事化、PR として提出する。人間は PR レビューと merge にだけ介入すれば、自分の関心に沿った議論記事が毎日 1 本ずつ知識ベースに蓄積される。

## 状態

**Phase 1 (spike 開発中)** — 上位 repo [`luck-tech/my_library`](https://github.com/luck-tech/my_library) 内の `libmatic/` サブディレクトリで開発中。Phase 1.11 で `git subtree split` により独立 repo `luck-tech/libmatic` に切り出す予定。

Phase 0 の設計書: [`../docs/libmatic-oss-plan.md`](../docs/libmatic-oss-plan.md)

## クイックスタート (開発用)

```bash
# editable install
uv pip install -e .

# CLI 動作確認
libmatic --help
```

## 主要コンセプト

- **LangGraph hybrid**: 9 step 全体 = Workflow (StateGraph)、各 step 内部 = ReAct Agent
- **Multi-provider 前提の設計**: v0.1 は Anthropic only、v0.2 で OpenAI、v0.3 で Gemini
- **Model 選択**: preset (`quality` / `balanced` / `economy`) + step 別 override の 2 軸
- **lifespan 管理**: universal / ephemeral を自動判定し、ephemeral は `content/digest/<year>/Q<q>/` に隔離
- **Claude Code 対応**: scaffold で `.claude/commands/` に thin skill を生成 (optional)

## ドキュメント

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — LangGraph hybrid の graph 構造
- [docs/SPEC.md](docs/SPEC.md) — State schema, node 種別, tool 一覧, coverage loop

## ライセンス

MIT
