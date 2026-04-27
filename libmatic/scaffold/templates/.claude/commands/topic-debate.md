---
description: 夜次の議論記事生成 workflow (9 step) を 1 issue について実行
argument-hint: "[issue number]"
---

`libmatic topic-debate <issue>` を実行する薄い wrapper です。引数なしで呼ぶと
`topic/ready` から LRU で 1 件 pick されます (実行例は GH Actions 側を参照)。

!libmatic topic-debate $ARGUMENTS --config config/libmatic.yml
