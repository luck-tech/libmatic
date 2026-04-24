# topic-debate step prompts

Phase 1.5 で各 step の system prompt を執筆する。philosophy.md を include する。

## 予定ファイル

- `step1_source_collector.md` — 探索戦略、一次情報優先、対立視点収集
- `step4_fact_extractor.md` — 構造化抽出、憶測除外、confidence 付与
- `step5_fact_merger.md` — dedup、衝突解決、階層化 (primary / secondary / tangential)
- `step6_coverage_verifier.md` — gap 抽出の LLM judge
- `step7_article_writer.md` — 原本執筆、引用付き、論点整理
- `step8_expanded_writer.md` — 初学者向け再構成、原典引用集付録

## suggest-topics と address-pr-comments の prompt

- `../suggest_topics.md` に A3 relevance_filter / A6 propose_sources judge を記述
- `../pr_review.md` に C2 classify_comments / C3 address_each を記述
