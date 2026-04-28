# libmatic COST

libmatic の運用コスト見積り。Anthropic API 料金 (2026-04 時点目安) と GH Actions の min 制限を踏まえた試算。

**重要**: 数値は概算で、実際は記事の長さ / 引用 source 数 / coverage loop 回数で変動する。±50% は普通にブレる。

## 1. preset 別の token コスト

`libmatic init` で選ぶ preset がコストの主軸。default / cheap の 2 tier に展開される (詳細は [`SPEC.md §6`](SPEC.md#6-model-preset--step-override))。

### Anthropic 料金 (per MTok 目安、2026-04)

| model | input | output |
|---|---|---|
| claude-opus-4-7 | $15 | $75 |
| claude-sonnet-4-6 | $3 | $15 |
| claude-haiku-4-5 | $1 | $5 |

### preset

| preset | default | cheap |
|---|---|---|
| **quality** | claude-opus-4-7 | claude-haiku-4-5 |
| **balanced** (init default) | claude-sonnet-4-6 | claude-haiku-4-5 |
| **economy** | claude-haiku-4-5 | claude-haiku-4-5 |

## 2. ワークフロー別の token 試算

### topic-debate (1 記事生成、9 step)

仮定:
- source 12 本、各 3000 token (合計 input ~36k token)
- step 4 fact_extractor: per source 入力 3k + 出力 800 → 12 並列で input 36k / output 9.6k (cheap)
- step 5 fact_merger: input 10k / output 5k (default)
- step 6 coverage_verifier: input 8k / output 1k (default)
- step 7 article_writer: input 50k / output 8k (default)
- step 8 expanded_writer: input 60k / output 12k (default)
- step 1 source_collector: input 20k / output 3k (default)

**preset 別合計コスト (1 記事あたり)**:

| preset | default 入出 | cheap 入出 | 概算合計 |
|---|---|---|---|
| **quality** | input 148k × $15/M = $2.22 + output 29k × $75/M = $2.18 → **$4.4** | input 36k × $1/M = $0.04 + output 9.6k × $5/M = $0.05 → **$0.09** | **~$4.5** |
| **balanced** | input 148k × $3/M = $0.44 + output 29k × $15/M = $0.44 → **$0.88** | $0.09 (同上) | **~$1.0** |
| **economy** | input 148k × $1/M = $0.15 + output 29k × $5/M = $0.15 → **$0.30** | $0.09 | **~$0.4** |

### suggest-topics (週次、1 回実行)

ほぼ A3 relevance_filter のみ LLM 使用 (cheap tier 想定だと安価):

- input ~30k (raw_candidates 100 件) / output ~5k
- balanced default の場合 input × $3/M + output × $15/M ≒ **$0.16 / 回**

週 1 回なので **月 ~$0.7**。

### address-pr-comments (PR レビュー対応、1 PR あたり)

C2 (cheap、small) + C3 (default、コード読み書きで多め):

- input ~30k (PR 全 file + comments) / output ~10k
- balanced default → **~$0.25 / PR**

### 月間試算 (典型運用)

| 項目 | 頻度 | quality | balanced | economy |
|---|---|---|---|---|
| topic-debate | 30 記事/月 | $135 | $30 | $12 |
| suggest-topics | 4 週/月 | $4 | $0.7 | $0.3 |
| address-pr-comments | 5 PR/月 | $5 | $1.3 | $0.5 |
| **合計** | | **~$145** | **~$32** | **~$13** |

実際は coverage loop で +10-20%、prompt caching (v1.1) で -30-50% の調整あり。

## 3. preset の選び方

| 想定 | おすすめ |
|---|---|
| 個人趣味で記事品質最優先 | **quality** (月 $100+) |
| OSS 利用者の default、コスパ良 | **balanced** (月 $30) ← `init` default |
| とりあえず動かしてみたい / 学習 | **economy** (月 $10) — 記事品質は落ちる |

step 7/8 だけ Opus に上げて他は Sonnet、というハイブリッド運用も `models.overrides` で可能 (config 例は `SETUP.md` 参照)。

## 4. GitHub Actions の min 制限

| repo 種別 | ubuntu-latest 月間制限 |
|---|---|
| **public** | **無制限・無料** |
| private Free | 2,000 min/月 |
| private Pro | 3,000 min/月 |
| private Team | 50,000 min/月 |

libmatic の想定消費:
- weekly suggest (~30 min) × 4 = 120 min
- nightly debate (~60 min) × 30 = 1,800 min
- (PR 対応) 想定変動

**月 ~2,000 min が目安**。private Pro でほぼ上限、private Team なら余裕。

### コスト圧縮策

1. **public repo にする** (private にする実利が無いケースが多い)
2. **macOS launchd で local 実行** (Claude Max なら無料、ただし Mac 起動必須)
3. **nightly 頻度を下げる** (隔日にすれば 900 min/月)
4. private なら Team tier に upgrade

## 5. token 使用量の観測 (v1.0 予定)

v0.1 では token 計測の観測ポイントなし。v1.0 で:

- step 別の token 消費を log 出力
- 月別 / preset 別の累積コストを集計

を追加予定。

## 関連

- [SETUP.md](SETUP.md) — 導入手順
- [SPEC.md §6](SPEC.md#6-model-preset--step-override) — preset / override の詳細
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
