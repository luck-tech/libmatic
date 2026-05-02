# libmatic SPEC

**状態**: Phase 1.2 草案（2026-04-23）
**目的**: node / tool / state / CLI / config の詳細仕様。全体俯瞰は [ARCHITECTURE.md](ARCHITECTURE.md)、Phase 0 意思決定は [`../../docs/libmatic-oss-plan.md`](../../docs/libmatic-oss-plan.md)。

---

## 目次

1. [Workflow A: suggest-topics](#1-workflow-a-suggest-topics)
2. [Workflow B: topic-debate (9 step)](#2-workflow-b-topic-debate-9-step)
3. [State schema (topic-debate)](#3-state-schema-topic-debate)
4. [Tool 一覧](#4-tool-一覧)
5. [Node 種別の一覧](#5-node-種別の一覧)
6. [Model preset + step override](#6-model-preset--step-override)
7. [Coverage loop 制御](#7-coverage-loop-制御)
8. [Workflow C: address-pr-comments](#8-workflow-c-address-pr-comments)
9. [CLI 仕様](#9-cli-仕様)
10. [Config schema](#10-config-schema)
11. [Checkpointer と resume](#11-checkpointer-と-resume)
12. [エラー処理 / リトライ方針](#12-エラー処理--リトライ方針)

---

## 1. Workflow A: suggest-topics

**目的**: 週次で信頼発信者の RSS / YouTube / X + Web 検索を巡回し、議論価値のあるテーマを `topic/pending` issue として起票する。

### 1.1 Step

| step | 役割 | 種別 |
|---|---|---|
| A1 `load_priorities` | `config/source_priorities.yml` を読み、発信者リストを構造化 | deterministic |
| A2 `fetch_candidates` | 各 source から最新エントリを取得 (RSS / YouTube RSS → yt-dlp / fxtwitter) | fan-out (Send) |
| A3 `relevance_filter` | 候補ごとに lifespan (universal / ephemeral) 判定、ジャンル別除外、ephemeral → universal 昇華試行 | ReAct |
| A4 `dedup_against_issues` | 既存の open `topic/*` issue タイトルと類似度チェック | deterministic |
| A5 `create_issues` | 生き残った候補を `topic/pending` として起票 | deterministic |
| A6 `propose_new_sources` | 候補元ドメインで未登録 source を抽出、条件 (2 件以上で登場 & 過去 3 ヶ月投稿実績) を満たせば source_priorities.yml 追加 PR を提案 | conditional + deterministic |

### 1.2 入出力

- **入力**: `config/source_priorities.yml`、既存 open issue 一覧 (`gh issue list --label topic/*`)
- **出力**: 新規 `topic/pending` issue 群、必要に応じて `proposal/sources-YYYY-MM-DD` branch + PR

### 1.3 実行頻度

- 週次 (`scripts/launchd/com.luck.suggest-topics.weekly.plist` 相当)
- GH Actions では `.github/workflows/weekly-suggest.yml` で cron

---

## 2. Workflow B: topic-debate (9 step)

**目的**: `topic/ready` な issue を 1 本 pick し、ソース取得 → 事実抽出 → 網羅性検証 → 原本 + 拡張版 の 2 記事を生成、PR として提出。

### 2.1 Step 詳細

#### Step 1: `source_collector` (ReAct)

- **input**: `issue_title`, `issue_body`, `source_priorities.yml`
- **output**: `candidate_sources: list[Source]` (通常 15-30 件)
- **tool**: `web_search`, `read_file` (source_priorities.yml)
- **責務**: issue のテーマに関連する一次情報を、priority list から + Web 検索で収集
- **prompt 要点**: lifespan に応じた探索方針、対立視点の能動的収集、信頼度の低い source は除外

#### Step 2: `source_scorer` (deterministic)

- **input**: `candidate_sources`
- **output**: `scored_sources: list[Source]` (score 降順、上位 `max_sources_per_topic` 件)
- **tool**: なし（Python の計算のみ）
- **score 計算**: `priority_weight × recency_decay × relevance`
  - `priority_weight`: source_priorities.yml の tier (S=1.0, A=0.8, B=0.5)
  - `recency_decay`: `exp(-days_since_published / 180)` (半年で 1/e)
  - `relevance`: title/snippet と issue_title の語彙一致率（簡易 Jaccard）

#### Step 3: `source_fetcher` (deterministic, Send fan-out)

- **input**: `scored_sources` (上位 N 件)
- **output**: `fetched_sources: list[Source]` (各 `fetched_content` フィールド埋め済み)
- **tool**: `fetch_source` (URL dispatcher)
- **並列度**: `max_concurrent_fetches` (default 6)
- **失敗時**: 当該 source を skip、他 source で続行

#### Step 4: `fact_extractor` (ReAct, Send per source)

- **input**: `fetched_sources`
- **output**: `raw_facts_per_source: list[list[Fact]]`
- **tool**: `edit_file` (fact 書き出し用)、`web_fetch` (補足調査)
- **責務**: source ごとに LLM が Fact を構造化抽出
- **prompt 要点**: claim / source_urls / confidence / category を明示、憶測は除外
- **並列度**: source 数と同じ

#### Step 5: `fact_merger` (ReAct)

- **input**: `raw_facts_per_source`
- **output**: `merged_facts: list[Fact]`
- **tool**: なし (state 内の facts を LLM が整理)
- **責務**: 重複削除、衝突検出、主張の階層化 (primary / secondary / tangential)

#### Step 6: `coverage_verifier` (hybrid)

- **input**: `merged_facts`, `issue_body`
- **output**: `coverage_score: float`, `coverage_gaps: list[str]`
- **tool**: `verify_coverage` (数値計算), LLM judge (gap 言語化)
- **挙動**:
  1. `verify_coverage` で issue の論点と facts の一致率を数値で計算
  2. LLM judge が「足りないトピック」を自然言語で列挙
  3. `coverage_score < threshold` かつ `loop_count < 2` → step 3 に戻る
  4. それ以外 → step 7 に進む

#### Step 7: `article_writer` (ReAct)

- **input**: `merged_facts`, `issue_body`, `lifespan`
- **output**: `article_draft: str` (原本 Markdown)
- **tool**: `read_file` (facts 参照), `edit_file` (記事書き出し)
- **責務**: facts を引用付きで原本記事に構成、論点整理 + 対立軸 + 一次情報リンク
- **lifespan 判定での分岐**:
  - universal → `content/<category>/notes/<slug>.md` に配置
  - ephemeral → `content/digest/<year>/Q<q>/<slug>.md` に配置

#### Step 8: `expanded_writer` (ReAct)

- **input**: `article_draft`, `merged_facts`
- **output**: `article_expanded: str` (拡張版 Markdown)
- **tool**: `read_file`, `edit_file`
- **責務**: 初学者向けに再構成、背景解説 + ストーリー仕立て + 原典引用集付録

#### Step 9: `pr_opener` (deterministic)

- **input**: `article_draft`, `article_expanded`, `output_path`
- **output**: `pr_number`, `pr_url`
- **tool**: `bash` (git), `gh_pr_create`
- **挙動**:
  1. branch 作成 `topic/<slug>`
  2. 記事 2 ファイルを書き込み、commit
  3. push + `gh pr create`
  4. issue label 遷移: `topic/in-progress` → `topic/review`

### 2.2 実行頻度

- 夜次 (`scripts/launchd/com.luck.topic-debate.nightly.plist` 相当)
- 1 夜 1 本 (`MAX_ISSUES_PER_NIGHT=1`)

---

## 3. State schema (topic-debate)

```python
# libmatic/state/topic_debate.py
from pydantic import BaseModel
from typing import Annotated, Literal
from langgraph.graph.message import add_messages


class Source(BaseModel):
    url: str
    type: Literal["rss", "youtube", "x", "zenn", "qiita", "github", "rfc", "generic"]
    title: str
    published_at: str | None = None
    score: float = 0.0
    fetched_content: str | None = None


class Fact(BaseModel):
    claim: str
    source_urls: list[str]
    confidence: Literal["high", "medium", "low"]
    category: str  # "design-principle" / "case" / "number" / "quote" / ...


class TopicDebateState(BaseModel):
    # 入力
    issue_number: int
    issue_title: str
    issue_body: str
    lifespan: Literal["universal", "ephemeral"]

    # step 1-3
    candidate_sources: list[Source] = []
    scored_sources: list[Source] = []
    fetched_sources: list[Source] = []

    # step 4-5
    raw_facts_per_source: list[list[Fact]] = []
    merged_facts: list[Fact] = []

    # step 6
    coverage_score: float = 0.0
    coverage_gaps: list[str] = []
    coverage_loop_count: int = 0

    # step 7-8
    article_draft: str = ""
    article_expanded: str = ""
    output_path: str = ""  # content/... or content/digest/...

    # step 9
    pr_number: int | None = None
    pr_url: str | None = None

    # メタ
    messages: Annotated[list, add_messages] = []
    retries: dict[str, int] = {}
```

---

## 4. Tool 一覧

### 4.1 File I/O

| tool | signature | 責務 |
|---|---|---|
| `read_file` | `(path: str) -> str` | ファイル読み（UTF-8） |
| `edit_file` | `(path: str, old: str, new: str) -> bool` | 差分編集、`old` が一意に存在しない場合エラー |
| `write_file` | `(path: str, content: str) -> bool` | 新規作成（既存なら上書き） |

### 4.2 Shell

| tool | signature | 責務 |
|---|---|---|
| `bash` | `(cmd: str, timeout: int = 120) -> str` | subprocess 実行、timeout 指定可 |

### 4.3 Web

| tool | signature | 責務 |
|---|---|---|
| `web_fetch` | `(url: str) -> str` | URL → text (trafilatura) |
| `web_search` | `(query: str, max_results: int = 10) -> list[dict]` | Anthropic search or tavily |

### 4.4 Source

| tool | signature | 責務 |
|---|---|---|
| `fetch_source` | `(url: str) -> Source` | URL dispatcher: YT/X/Zenn/Qiita/GitHub/RFC/generic の型判定 + fetch |
| `fetch_x_thread` | `(url: str) -> str` | X スレッドを fxtwitter 経由で取得 |

### 4.5 Coverage

| tool | signature | 責務 |
|---|---|---|
| `verify_coverage` | `(facts: list[Fact], article: str) -> dict` | `{score: float, gaps: list[str], primary_coverage: float, ...}` |

### 4.6 GitHub

| tool | signature | 責務 |
|---|---|---|
| `gh_issue_list` | `(filter: dict) -> list[dict]` | `gh issue list` wrapper |
| `gh_issue_create` | `(title: str, body: str, labels: list[str]) -> int` | issue 作成 |
| `gh_issue_edit` | `(num: int, add_labels: list[str], remove_labels: list[str]) -> None` | label 遷移 |
| `gh_pr_create` | `(branch: str, title: str, body: str) -> dict` | PR 作成 |
| `gh_pr_comments` | `(pr: int) -> list[dict]` | レビューコメント取得 |
| `gh_pr_reply` | `(pr: int, comment_id: int, body: str) -> None` | コメント返信 |

---

## 5. Node 種別の一覧

| workflow | step | node 種別 | LLM 呼出 |
|---|---|---|---|
| suggest-topics | A1 load_priorities | deterministic | なし |
| suggest-topics | A2 fetch_candidates | deterministic (Send) | なし |
| suggest-topics | A3 relevance_filter | ReAct | あり |
| suggest-topics | A4 dedup | deterministic | なし |
| suggest-topics | A5 create_issues | deterministic | なし |
| suggest-topics | A6 propose_sources | conditional | 1 回 (判定) |
| topic-debate | 1 source_collector | ReAct | あり |
| topic-debate | 2 source_scorer | deterministic | なし |
| topic-debate | 3 source_fetcher | deterministic (Send) | なし |
| topic-debate | 4 fact_extractor | ReAct (Send) | あり (per source) |
| topic-debate | 5 fact_merger | ReAct | あり |
| topic-debate | 6 coverage_verifier | hybrid | 1 回 (judge) |
| topic-debate | 7 article_writer | ReAct | あり |
| topic-debate | 8 expanded_writer | ReAct | あり |
| topic-debate | 9 pr_opener | deterministic | なし |
| address-pr-comments | C1 collect_comments | deterministic | なし |
| address-pr-comments | C2 classify_comments | ReAct | あり |
| address-pr-comments | C3 address_each | ReAct loop | あり |
| address-pr-comments | C4 commit_push | deterministic | なし |
| address-pr-comments | C5 reply_comments | deterministic | なし |

---

## 6. Model preset + step override

### 6.1 Preset (Anthropic v0.1)

| preset | default | cheap |
|---|---|---|
| quality | claude-opus-4-7 | claude-haiku-4-5 |
| balanced (init default) | claude-sonnet-4-6 | claude-haiku-4-5 |
| economy | claude-haiku-4-5 | claude-haiku-4-5 |

### 6.2 Step の tier 割当 (コード固定)

| step | tier |
|---|---|
| suggest-topics A3 relevance_filter | default |
| suggest-topics A6 propose_sources judge | cheap |
| topic-debate 1 source_collector | default |
| topic-debate 4 fact_extractor | **cheap** |
| topic-debate 5 fact_merger | default |
| topic-debate 6 coverage_verifier | default |
| topic-debate 7 article_writer | default |
| topic-debate 8 expanded_writer | default |
| address-pr-comments C2 classify | cheap |
| address-pr-comments C3 address | default |

### 6.3 resolve ロジック

```python
def resolve_model(step_name: str, config: LibmaticConfig) -> str:
    if step_name in config.models.overrides:
        return config.models.overrides[step_name]
    tier = STEP_TIER_MAP[step_name]
    return PRESET_MODELS[config.provider][config.preset][tier]
```

---

## 7. Coverage loop 制御

```python
def coverage_gate(state: TopicDebateState) -> str:
    if state.coverage_score >= COVERAGE_THRESHOLD:   # default 0.80
        return "step7_article_writer"
    if state.coverage_loop_count >= MAX_COVERAGE_LOOPS:  # default 2
        return "step7_article_writer"  # 諦めて進む
    return "step3_source_fetcher"
```

- loop back 時に `coverage_loop_count` をインクリメント
- step 3 では `coverage_gaps` を追加の fetch target として利用 (Web 検索キーワードに gap トピックを追加)

---

## 8. Workflow C: address-pr-comments

### 8.1 Step

| step | 役割 | 種別 |
|---|---|---|
| C1 `collect_comments` | `gh api repos/{owner}/{repo}/pulls/{pr}/comments` | deterministic |
| C2 `classify_comments` | 各コメントを「対応要 / reply のみ / 無視」に分類 | ReAct (cheap tier) |
| C3 `address_each` | 対応要コメントごとに fetch → edit → stage | ReAct loop |
| C4 `commit_push` | `git commit && git push` | deterministic |
| C5 `reply_comments` | 各 comment に対応内容を reply | deterministic |

### 8.2 State schema (略式)

```python
class PRReviewState(BaseModel):
    pr_number: int
    comments: list[dict] = []
    classified: dict[int, Literal["address", "reply", "ignore"]] = {}
    actions: list[dict] = []  # 対応した edit / bash コマンドのログ
    committed: bool = False
    replied: list[int] = []
    messages: Annotated[list, add_messages] = []
```

---

## 9. CLI 仕様

```
libmatic init
    対話形式で libmatic プロジェクトを scaffold。
    生成: config/libmatic.yml, config/source_priorities.yml, .env.example,
          content/ 雛形, (optional) .claude/commands/, .github/workflows/

libmatic suggest-topics [--config FILE]
    週次の workflow A を実行。

libmatic topic-debate [ISSUE]
    夜次の workflow B (9 step) を実行。引数省略時は topic/ready の LRU から 1 本 pick。

libmatic address-pr-comments PR
    workflow C を実行。

libmatic resume THREAD_ID
    中断した workflow を checkpointer thread_id から再開。

libmatic graph <workflow>
    指定 workflow の graph を mermaid 形式で stdout に出力。
```

---

## 10. Config schema

### 10.1 `config/libmatic.yml`

```yaml
version: 1
provider: anthropic            # v0.1 は anthropic のみ
preset: balanced                # quality / balanced / economy
models:
  overrides:                    # optional
    step7_article_writer: claude-opus-4-7
    step8_expanded_writer: claude-opus-4-7

content:
  universal_dir: "content/{category}/notes"
  ephemeral_dir: "content/digest/{year}/Q{quarter}"
  categories:
    - ai-ml
    - architecture
    - case-studies
    - development
    - domains
    - fundamentals
    - infrastructure
    - practices

lifespan:
  ephemeral_pruning_years: 2

workflow:
  max_sources_per_topic: 12
  max_concurrent_fetches: 6
  max_react_iterations: 15
  coverage_threshold: 0.80
  max_coverage_loops: 2

github:
  repo: OWNER/REPO
  issue_labels:
    pending: topic/pending
    ready: topic/ready
    in_progress: topic/in-progress
    review: topic/review
    failed: topic/failed
```

### 10.2 `config/source_priorities.yml`

現行 my_library の形式 (`.claude/source_priorities.yml`) をそのまま採用。

### 10.3 `.env`

```
ANTHROPIC_API_KEY=sk-ant-...
GH_TOKEN=ghp_...
TAVILY_API_KEY=...    # web_search を tavily 経由で使う場合のみ
```

---

## 11. Checkpointer と resume

### 11.1 保存形式

- v0.1: SqliteSaver → `~/.libmatic/state.sqlite`
- thread_id 規約: `{workflow}-{primary_key}-{YYYYMMDD}`
  - 例: `topic-debate-18-20260423`
  - 例: `address-pr-comments-37-20260423`

### 11.2 resume 挙動

```
libmatic resume topic-debate-18-20260423
```

- checkpointer から state 復元
- 最後に成功した step の次から再開
- 例: step 6 で coverage 不足で step 3 にループ中に落ちた → step 3 から resume

### 11.3 GH Actions での扱い (v0.1)

- checkpoint を外部に永続化しない (ephemeral runner)
- 失敗したら GH Actions re-run で最初から
- v1.0 で artifact up/down 方式を追加

---

## 12. エラー処理 / リトライ方針

### 12.1 Tool レベル

- tool 関数内で例外 → `is_error: true` の tool_result として LLM に返す
- LLM が retry or 別の approach を判断

### 12.2 Step レベル

- step 3 (fetch) の個別 source 失敗 → skip、他 source で続行
- step 6 の coverage loop は `max_coverage_loops` (default 2) で上限
- step 9 の `gh pr create` 失敗 → state に記事残して exit、`resume` でやり直し可

### 12.3 Workflow レベル

- LLM API rate limit → workflow 内で 3 回 exponential backoff retry
- 最終失敗 → issue に失敗 comment、label を `topic/failed` に遷移 (既存 nightly batch と同じ流儀)

### 12.4 バッチレベル (scripts/nightly_topic_batch.sh)

- `PER_ISSUE_TIMEOUT` (default 90m) で強制 kill
- 処理失敗時は issue label 遷移 + 通知

---

## 13. 未決 / Phase 1 以降で決める

- **OpenAI / Gemini 実装時の tool_calls 挙動差** (v0.2 / v0.3)
- **prompt caching の cache_control 配置戦略** (v1.1)
- **GH Actions artifact checkpointer の実装方式** (v1.0)
- **observability の計測項目と dashboard** (v1.0)
- **scaffold の `.github/workflows/*.yml` の具体 yaml 内容** (Phase 1.8)
- **scaffold の `.claude/commands/*.md` の skill 本文** (Phase 1.8)

---

## 14. 参考

- [ARCHITECTURE.md](ARCHITECTURE.md) — 全体俯瞰
- [`../../docs/libmatic-oss-plan.md`](../../docs/libmatic-oss-plan.md) — Phase 0 意思決定
- 現行 my_library `.claude/commands/*.md` — skill の振る舞いの種本
- 現行 my_library `scripts/*.py` — tool 化の元ネタ
