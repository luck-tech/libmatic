# libmatic

**個人の知識ベースを自動運用するためのパイプラインテンプレート**

週次で信頼発信者の RSS / YouTube / X と Web 検索を自動巡回し、議論価値のあるテーマを GitHub issue として起票。人が `topic/ready` に昇格した issue を夜次で 1 本ずつ pick し、ソース取得 → 事実抽出 → 網羅性検証 → 原本 + 初学者向け拡張版の 2 本立てで記事化、PR として提出する。人間は PR レビューと merge にだけ介入すれば、自分の関心に沿った議論記事が毎日 1 本ずつ知識ベースに蓄積される。

## 出力例

GitHub issue 1 つ (テーマ + 雑メモ程度) を入力に、libmatic は **対立軸を含む長文の議論型解説記事** を 1 本生成する。サンプル出力:

- 📄 **[examples/wasm-component-model.md](examples/wasm-component-model.md)** — 「WebAssembly Component Model と WASI 0.3」を題材に、container との使い分け / WASIX 分派論争 / 言語サポート実情 / 懐疑論まで含めた 4400 行の解説 (step 8 expanded_writer 出力)

特徴:

- **対立軸を矮小化しない** (Wasm vs container、WASIX vs Bytecode Alliance、等の論争を両論併記)
- **複数ソースを統合**して事実関係を構築 (RSS / YouTube / X / Web 検索からの自動取得)
- **読者像と前提知識**を冒頭で明示、学習目標を箇条書き
- **判断軸 / チェックリスト**を末尾に配置 (読者が自分のケースに当てはめられる形)

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
.venv/bin/pytest                       # 377 tests
.venv/bin/libmatic --help
```

## 主要コンセプト

- **LangGraph hybrid**: 9 step 全体 = Workflow (StateGraph)、各 step 内部 = ReAct Agent
- **Multi-provider 前提の設計**: v0.1 は Anthropic only、v0.2 で OpenAI、v0.3 で Gemini
- **Model 選択**: preset (`quality` / `balanced` / `economy`) + step 別 override の 2 軸
- **lifespan 管理**: universal / ephemeral を自動判定し、ephemeral は `content/digest/<year>/Q<q>/` に隔離
- **Claude Code 対応**: scaffold で `.claude/commands/` に thin skill を生成 (optional)

## ドキュメント

- [examples/](examples/) — libmatic が生成した記事のサンプル
- [docs/SETUP.md](docs/SETUP.md) — 導入手順 (uv init / scaffold / secrets / 定期実行)
- [docs/CONCEPTS.md](docs/CONCEPTS.md) — lifespan / 9 step / luck-ism の説明
- [docs/COST.md](docs/COST.md) — preset 別 token コスト試算 + GH Actions min 制限
- [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md) — よくあるハマり所
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — LangGraph hybrid の graph 構造 (技術寄り)
- [docs/SPEC.md](docs/SPEC.md) — State schema, node 種別, tool 一覧, coverage loop

## ライセンス

MIT
