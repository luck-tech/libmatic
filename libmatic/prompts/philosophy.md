# libmatic philosophy (luck-ism)

この文書は libmatic の default philosophy をまとめる。各 step の system prompt に
部分的に include され、workflow の judgment に埋め込まれる。OSS 利用者は fork /
skill 改変で変更可能（libmatic-oss-plan.md §3.1 #7）。

## Lifespan 判定

- **universal**: 2 年後も読まれる可能性が高い
  - 設計原則、アーキテクチャ論、トレードオフ俯瞰、歴史追跡、原理的論点
  - 配置: `content/{category}/notes/<slug>.md` に永続
- **ephemeral**: 数ヶ月で陳腐化する
  - 特定バージョン比較、直近の事件、一時トレンド
  - 配置: `content/digest/<year>/Q<quarter>/<slug>.md`、2 年目安で pruning 候補

## Ephemeral → Universal 昇華ルール

ephemeral に見えたら、背景にある普遍的な問いに昇華できないか必ず検討する:

- 「Gemma 4 vs Llama 4」→「オープンモデル LLM 選定の永続トレードオフ（ライセンス
  × アーキ × コスト × 地政学）」
- 「Vercel 情報漏洩」→「メタフレームワーク選定における lockin と逃げ道」
- 「Next.js 15 新機能レビュー」→「メタフレームワーク設計の歴史的変遷」

## ジャンル別除外

- **LLM / API / SaaS**: ユーザー視点が版で変わりにくい。単純な版比較は記事化しない
- **フレームワーク / 言語 / 標準規格**: 版毎に出来ることが変わる。版比較も有効
- **ツール / ライブラリ**: breaking change の大きさで判断

## Source PR フロー

- 自動で `source_priorities.yml` を書き換えない
- 週次で候補が 2 件以上に登場した新ソースドメインを検出した場合のみ、
  `proposal/sources-YYYY-MM-DD` branch で PR 提案
- user が merge / close で意思表示する
