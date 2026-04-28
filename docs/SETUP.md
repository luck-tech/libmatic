# libmatic SETUP

新しい repo に libmatic を導入してパイプラインを動かすまでの手順。

## 0. 前提

- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (パッケージ管理)
- [GitHub CLI](https://cli.github.com/) (`gh`)
- Anthropic API キー (v0.1 は anthropic only、v0.2 で OpenAI、v0.3 で Gemini 対応予定)
- (optional) Mac で launchd 定期実行を使う場合: `brew install coreutils`

## 1. プロジェクト初期化

新しい repo を作って、その中で libmatic を install + scaffold する。

```bash
mkdir my-knowledge-base && cd my-knowledge-base
git init

# uv project 化
uv init --package
uv add 'libmatic @ git+https://github.com/luck-tech/libmatic.git'

# scaffold
uv run libmatic init --repo <owner>/<repo>
```

`libmatic init` は対話で preset (quality/balanced/economy) を聞いてくる。`--yes` を付けると balanced で進む。

CI 用の非対話実行:

```bash
uv run libmatic init --target-dir . --repo acme/foo --preset balanced --yes
```

scaffold で生成されるファイル:

```
config/libmatic.yml              # provider / preset / categories / threshold
config/source_priorities.yml     # 信頼発信者リスト (空、自分で埋める)
.env.example                     # ← .env にコピーして key 設定
.gitignore
.github/workflows/{weekly-suggest,nightly-debate}.yml
.github/ISSUE_TEMPLATE/topic.yml
.claude/commands/*.md            # Claude Code 利用時の slash command
content/<category>/notes/.gitkeep × 8 + content/digest/.gitkeep
```

## 2. secrets を設定

### dev (.env)

```bash
cp .env.example .env
# .env を編集
ANTHROPIC_API_KEY=sk-ant-xxx
GH_TOKEN=ghp_xxx   # repo + workflow scope
```

### 本番 (GitHub Actions)

repo の Settings → Secrets and variables → Actions に登録:

- `ANTHROPIC_API_KEY`
- `GITHUB_TOKEN` は GH Actions が自動で渡す (workflow yml の `permissions` で issues:write, pr:write が必要)

## 3. source_priorities.yml を埋める

`config/source_priorities.yml` に巡回したい RSS / Zenn / Qiita / YouTube などを追加:

```yaml
blogs:
  - name: Overreacted
    url: https://overreacted.io/
    feed: https://overreacted.io/rss.xml

zenn:
  users:
    - handle: mizchi

youtube:
  channels:
    - name: Example
      id: UCabcdefghijklmnopqrstuv
```

YouTube は **channel_id (`UC` 始まり)** が必要 (handle ではない)。

## 4. 初回テスト実行

```bash
# 週次 (テーマ起票)
uv run libmatic suggest-topics

# 起票された issue を確認
gh issue list --label topic/pending

# よさそうな issue を topic/ready に昇格
gh issue edit <num> --add-label topic/ready --remove-label topic/pending

# 夜次 (記事生成)
uv run libmatic topic-debate <num>

# 生成された PR を確認
gh pr list
```

## 5. 定期実行

### 5a. GitHub Actions (推奨、cross-platform)

`.github/workflows/{weekly-suggest,nightly-debate}.yml` が既に scaffold されている。

```bash
git add . && git commit -m "init libmatic" && git push
```

`workflow_dispatch` で手動 run、`cron` で定期 run される。

GH Actions の min 制限に注意 (詳細は [`COST.md`](COST.md) 参照)。

### 5b. macOS launchd (local 実行、無料)

`scaffold init --launchd` を付けて scaffold すると `scripts/launchd/` に plist テンプレが生成される:

```bash
# .example を外して自分用にコピー
cp scripts/launchd/com.libmatic.topic-debate.nightly.plist.example \
   ~/Library/LaunchAgents/com.libmatic.topic-debate.nightly.plist

# プロジェクトパスを書き換え (MY_PROJECT 部分)
vim ~/Library/LaunchAgents/com.libmatic.topic-debate.nightly.plist

# load
launchctl load ~/Library/LaunchAgents/com.libmatic.topic-debate.nightly.plist
```

Mac の TCC (Full Disk Access) 制約に注意: `~/Desktop` や `~/Documents` 配下からは launchd 経由で読めない。`~/projects/` 等 TCC 対象外に置くこと。

## 6. checkpoint resume

途中で止まった workflow は thread_id で再開可能:

```bash
uv run libmatic resume topic-debate-18-20260424
```

thread_id 規約: `{workflow}-{primary_key}-{YYYYMMDD}`

local sqlite (`~/.libmatic/state.sqlite`) に保存されているので、同じマシン内で再開する用。GH Actions の ephemeral runner 越しの resume は v0.1 では非対応 (v1.0 で artifact 方式追加予定)。

## 7. Claude Code から呼ぶ

scaffold で `--claude-code` 付き (default) なら `.claude/commands/*.md` が生成される:

```
/suggest-topics
/topic-debate 18
/address-pr-comments 37
```

中身は `!libmatic ...` を叩く薄い wrapper。普段の slash command と同じ感覚で使える。

## 関連

- [CONCEPTS.md](CONCEPTS.md) — lifespan, 9 step, luck-ism の説明
- [COST.md](COST.md) — preset 別 token コスト試算
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — よくあるハマり所
- [ARCHITECTURE.md](ARCHITECTURE.md) — 全体俯瞰
- [SPEC.md](SPEC.md) — node / tool / state の詳細仕様
