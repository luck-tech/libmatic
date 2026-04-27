---
description: PR レビューコメントへの自動対応 workflow (C1-C5) を実行
argument-hint: "<PR number>"
---

`libmatic address-pr-comments <PR>` を実行する薄い wrapper です。
classify → address (edit_file) → commit/push → reply の流れ。

!libmatic address-pr-comments $ARGUMENTS --config config/libmatic.yml
