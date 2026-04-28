# libmatic TROUBLESHOOTING

PoC / spike 中に踏んだ罠と対処メモ。新たな罠を踏んだら追記する方針。

## 1. install / runtime

### `gh CLI が見つかりません` (GhError)

`gh` コマンドが PATH に無い。

```bash
brew install gh           # macOS
sudo apt install gh       # Debian/Ubuntu
gh auth login             # 初回 auth
```

CI では `actions/checkout@v4` 後に `gh` が使える (GH Actions runner にプリインストール)。`GH_TOKEN` (GitHub Actions では自動の `${{ secrets.GITHUB_TOKEN }}`) を env に渡すこと。

### `ANTHROPIC_API_KEY` が無い

`.env` に書いて `uv run` で実行するか、shell 上で `export ANTHROPIC_API_KEY=...`。CI なら repo Secrets に登録 → workflow の `env:` で渡す。

### `langgraph.checkpoint.sqlite` が import できない

`langgraph-checkpoint-sqlite` が install されていない。

```bash
uv add langgraph-checkpoint-sqlite
```

(libmatic の dependencies に既に含まれているので通常は不要、独自に分けて install する場合のみ)

## 2. ネットワーク / fetch

### Cloudflare / WAF で 403

Anthropic クラウドの IP や CI 環境の IP が WAF にブロックされ、`web_fetch` / `search_sources` が 403 を返すことがある。

- **対処 1**: macOS launchd で local 実行に切替 (家庭 IP は通る)
- **対処 2**: 該当 source は `source_priorities.yml` から外す
- **対処 3**: `User-Agent` を変える (libmatic のは `Mozilla/5.0 (compatible; libmatic/0.1)`)

### YouTube RSS が 404 / 500

YouTube 側で `feeds/videos.xml?channel_id=...` が globally 死んでるケースが時々ある。`yt-dlp --flat-playlist` で channel/videos URL から動画一覧を取得する手法に切り替えたいが、v0.1 では未対応 (YouTube は addon 領分)。

### X (Twitter) スレッドが取れない

`fxtwitter` / `vxtwitter` の有志運営 proxy 経由で取得しているため、proxy が rate limit / down だと一時的に取れない。`fetch_x_core` は両 backend を順に試して両方失敗なら `fetched_content=None` で graceful skip する。

## 3. LangGraph / agent

### `RunnableConfig.configurable.libmatic_config に LibmaticConfig...` ValueError

node 側で config を渡し忘れている。invoke 時:

```python
graph.invoke(state, config={"configurable": {
    "libmatic_config": lcfg,
    "thread_id": "...",
}})
```

CLI 経由なら自動で渡るので発生しない。直接 `graph.invoke(state)` した時に出る。

### `recursion limit` 超過

ReAct agent の tool 呼出が想定以上に増えると LangGraph の `recursion_limit` (default 25) で落ちる。CLI は `lcfg.workflow.max_react_iterations * 2 + 20` を設定しているので、`config/libmatic.yml` の `workflow.max_react_iterations` を上げると緩和。

ただし上げすぎは token 浪費。15-25 が目安。

### LLM 出力が JSON にならない

`source_collector` / `fact_extractor` などの ReAct node で agent の最終 message が JSON array でないと `_parse_json_array` が空 list を返す → 空結果になる。

- prompt の出力契約を強める (「JSON のみ、コードフェンス無し」)
- temperature を下げる (将来 config 対応予定)
- log の最終 message を `LANGCHAIN_VERBOSE=1` で確認

## 4. coverage loop

### coverage_score が 0 で止まる

`fact_extractor` の出力が空 → `merged_facts` も空 → `verify_coverage_core` が score 0 を返す。原因:

- fetched_content が短すぎる / 取れていない (上記 fetch 失敗)
- LLM 出力が JSON でなく fact が parse されてない
- claim が短すぎ (8 文字未満) で probe match に乗らない

`step6_coverage_verifier` の prompt は LLM judge で gap 言語化する設計なので、score 0 でも gap が言語化されれば step 7 に進める。

### loop 上限に常に達する

`coverage_threshold` が高すぎる可能性。default 0.80 で厳しい場合は 0.60-0.70 に下げる:

```yaml
workflow:
  coverage_threshold: 0.65
```

## 5. git / gh

### `git checkout -b` で「branch 既存」エラー

夜間バッチが残した branch と衝突。

```bash
git branch -D <branch>     # local 削除
git push origin :<branch>  # remote 削除
```

### gh CLI で auth エラー

`gh auth status` で確認、`gh auth login` で再 login。CI なら `GH_TOKEN` env (workflow yml で `permissions: contents:write, issues:write, pull-requests:write` を設定)。

## 6. macOS launchd

### TCC (Full Disk Access) で読込失敗

`launchd` から `~/Desktop` / `~/Documents` 配下にアクセスすると "can't open input file" 等で失敗する。**プロジェクトを `~/projects/` 配下に置くこと** (TCC 対象外)。

System Settings → Privacy & Security → Full Disk Access に追加することでも回避可能だが、運用が複雑。

### plist load しても動かない

```bash
launchctl list | grep libmatic                      # 登録確認
log show --predicate 'process == "launchd"' --info  # 詳細ログ
tail -f /tmp/libmatic.topic-debate.err.log          # plist で指定したエラーログ
```

### `gtimeout` が無い

macOS には GNU `timeout` が無いので `gtimeout` (coreutils) を使う:

```bash
brew install coreutils
```

(libmatic CLI 自体は timeout を内部で持たないが、launchd plist 内で timeout したい場合に使う)

## 7. テスト関連 (開発者向け)

### `import libmatic.tools.X as X_mod` が attribute を返す

`libmatic.tools.__init__.py` で `from libmatic.tools.X import ...` していると、submodule 名と attribute 名の衝突で `import X.Y as Z` が attribute (関数) を返すケースがある。

test 中で monkeypatch したい場合は:

```python
import importlib
ss_mod = importlib.import_module("libmatic.tools.search_sources")
monkeypatch.setattr(ss_mod, "http_get", fake_http_get)
```

### `datetime.timezone.utc` の deprecation 警告

Python 3.11+ では `datetime.UTC` alias が推奨。ruff `UP017` で auto-fix 可能 (`from datetime import UTC, datetime`)。

### subprocess monkeypatch がきかない

`subprocess.run` 全体を monkeypatch するのは OK。逆に「該当 module で import された subprocess」を patch したい場合は `monkeypatch.setattr("libmatic.tools.github.subprocess.run", fake)` のように完全 path で指定。

## 8. その他

### `coverage_score` の単位

- `LibmaticConfig.workflow.coverage_threshold`: **fractional** (0.0-1.0、default 0.80)
- `verify_coverage_core(combined_threshold=...)`: **percent** (0-100)
- `state.coverage_score`: **fractional** (0.0-1.0)

`coverage_verifier` node 内で `× 100 / 100` の変換を行う。直接 `verify_coverage_core` を呼ぶときは percent で渡す注意。

### `Fact` schema に `relevance_to_theme` が無い

v0.1 の `Fact` には verbatim / relevance_to_theme フィールドが無い。`step5_fact_merger` の LLM 出力に `relevance_to_theme` が含まれていても drop される。`_facts_to_claims_archive` 内では `'primary'` 固定で `verify_coverage_core` に渡している。将来拡張予定。

## 関連

- [SETUP.md](SETUP.md)
- [COST.md](COST.md)
- [CONCEPTS.md](CONCEPTS.md)
