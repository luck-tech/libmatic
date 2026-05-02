# libmatic

**個人の知識ベースを自動運用するためのパイプラインテンプレート**

週次で信頼発信者の RSS / YouTube / X と Web 検索を自動巡回し、議論価値のあるテーマを GitHub issue として起票。人が `topic/ready` に昇格した issue を夜次で 1 本ずつ pick し、ソース取得 → 事実抽出 → 網羅性検証 → 原本 + 初学者向け拡張版の 2 本立てで記事化、PR として提出する。人間は PR レビューと merge にだけ介入すれば、自分の関心に沿った議論記事が毎日 1 本ずつ知識ベースに蓄積される。

## 状態

**Phase 1 spike 完了** (2026-05-02) — 3 workflow + tools + scaffold + CLI 結線、Anthropic API tuning、377 tests passing。`git subtree split` で独立 repo `luck-tech/libmatic` に切り出した直後 (履歴保持)。次は実 API での E2E 確認 → `v0.1.0-alpha` タグ。

Phase 0 の設計書 (上位 repo `luck-tech/my_library` 内): [docs/libmatic-oss-plan.md](https://github.com/luck-tech/my_library/blob/main/docs/libmatic-oss-plan.md)

## クイックスタート

新規 repo に libmatic を導入する場合:

```bash
mkdir my-knowledge-base && cd my-knowledge-base
git init
uv init --package
uv add 'libmatic @ git+https://github.com/luck-tech/libmatic.git'
uv run libmatic init --repo <owner>/<repo>

# .env.example を .env にコピーして API key 設定 → 動作確認
cp .env.example .env  # 編集
uv run libmatic suggest-topics
```

詳しい手順は [docs/SETUP.md](docs/SETUP.md)。

### 開発用 (libmatic 自体を hack する場合)

```bash
git clone https://github.com/luck-tech/libmatic.git && cd libmatic
uv sync --extra dev
.venv/bin/pytest                       # 358 tests
.venv/bin/libmatic --help
```

## 主要コンセプト

- **LangGraph hybrid**: 9 step 全体 = Workflow (StateGraph)、各 step 内部 = ReAct Agent
- **Multi-provider 前提の設計**: v0.1 は Anthropic only、v0.2 で OpenAI、v0.3 で Gemini
- **Model 選択**: preset (`quality` / `balanced` / `economy`) + step 別 override の 2 軸
- **lifespan 管理**: universal / ephemeral を自動判定し、ephemeral は `content/digest/<year>/Q<q>/` に隔離
- **Claude Code 対応**: scaffold で `.claude/commands/` に thin skill を生成 (optional)

## ドキュメント

- [docs/SETUP.md](docs/SETUP.md) — 導入手順 (uv init / scaffold / secrets / 定期実行)
- [docs/CONCEPTS.md](docs/CONCEPTS.md) — lifespan / 9 step / luck-ism の説明
- [docs/COST.md](docs/COST.md) — preset 別 token コスト試算 + GH Actions min 制限
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — よくあるハマり所
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — LangGraph hybrid の graph 構造 (技術寄り)
- [docs/SPEC.md](docs/SPEC.md) — State schema, node 種別, tool 一覧, coverage loop

## ライセンス

MIT
