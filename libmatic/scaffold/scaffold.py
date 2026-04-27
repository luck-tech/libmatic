"""libmatic init: 静的テンプレ展開 + 一部変数置換。

仕様:
- TEMPLATES_DIR (libmatic/scaffold/templates/) 配下を target にコピー
- config/libmatic.yml は {{PRESET}} / {{CATEGORIES_YAML}} / {{GITHUB_REPO}} を置換
- .env.example はそのままコピー (target は .env.example のまま、user が .env にコピー)
- Claude Code 対応 OFF の場合は .claude/ を skip
- launchd 不要なら scripts/launchd/ を skip
- GH Actions 不要なら .github/workflows/ を skip
- content/ 配下の各 category に notes/.gitkeep + content/digest/.gitkeep を作成
- .gitignore.template は target で .gitignore にリネームしてコピー (既存があれば skip)
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent / "templates"

PRESET_CHOICES = ("quality", "balanced", "economy")

DEFAULT_CATEGORIES = (
    "ai-ml",
    "architecture",
    "case-studies",
    "development",
    "domains",
    "fundamentals",
    "infrastructure",
    "practices",
)


@dataclass
class InitOptions:
    """libmatic init の対話結果。"""

    target_dir: Path
    github_repo: str
    preset: str = "balanced"
    categories: tuple[str, ...] = DEFAULT_CATEGORIES
    include_claude_code: bool = True
    include_github_actions: bool = True
    include_launchd: bool = False
    overwrite: bool = False
    written_files: list[Path] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.preset not in PRESET_CHOICES:
            raise ValueError(
                f"preset は {PRESET_CHOICES} のいずれか: got {self.preset!r}"
            )
        if not self.categories:
            raise ValueError("categories が空です")


def render_libmatic_yml(opts: InitOptions) -> str:
    """config/libmatic.yml のテンプレ置換結果を返す。"""
    raw = (TEMPLATES_DIR / "config" / "libmatic.yml").read_text(encoding="utf-8")
    cats_yaml = "\n".join(f"    - {c}" for c in opts.categories)
    return (
        raw.replace("{{PRESET}}", opts.preset)
        .replace("{{CATEGORIES_YAML}}", cats_yaml)
        .replace("{{GITHUB_REPO}}", opts.github_repo)
    )


def _write(path: Path, content: str, *, opts: InitOptions) -> bool:
    """ファイルを書き出す。既存があり overwrite=False なら skip。書いたら True。"""
    if path.exists() and not opts.overwrite:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    opts.written_files.append(path)
    return True


def _copy(src: Path, dest: Path, *, opts: InitOptions) -> bool:
    if dest.exists() and not opts.overwrite:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dest)
    opts.written_files.append(dest)
    return True


def write_scaffold(opts: InitOptions) -> InitOptions:
    """opts に基づいて target_dir に scaffold を書き出す。

    Returns:
        opts (written_files が埋まる)
    """
    target = opts.target_dir
    target.mkdir(parents=True, exist_ok=True)

    # 1. config/libmatic.yml (変数置換あり)
    _write(
        target / "config" / "libmatic.yml",
        render_libmatic_yml(opts),
        opts=opts,
    )

    # 2. config/source_priorities.yml (そのままコピー)
    _copy(
        TEMPLATES_DIR / "config" / "source_priorities.yml",
        target / "config" / "source_priorities.yml",
        opts=opts,
    )

    # 3. .env.example
    _copy(
        TEMPLATES_DIR / ".env.example",
        target / ".env.example",
        opts=opts,
    )

    # 4. .gitignore (リネーム)
    _copy(
        TEMPLATES_DIR / ".gitignore.template",
        target / ".gitignore",
        opts=opts,
    )

    # 5. .github/workflows/ (optional)
    if opts.include_github_actions:
        for name in ("weekly-suggest.yml", "nightly-debate.yml"):
            _copy(
                TEMPLATES_DIR / ".github" / "workflows" / name,
                target / ".github" / "workflows" / name,
                opts=opts,
            )
        _copy(
            TEMPLATES_DIR / ".github" / "ISSUE_TEMPLATE" / "topic.yml",
            target / ".github" / "ISSUE_TEMPLATE" / "topic.yml",
            opts=opts,
        )

    # 6. .claude/commands/ (optional)
    if opts.include_claude_code:
        for name in (
            "suggest-topics.md",
            "topic-debate.md",
            "address-pr-comments.md",
        ):
            _copy(
                TEMPLATES_DIR / ".claude" / "commands" / name,
                target / ".claude" / "commands" / name,
                opts=opts,
            )

    # 7. scripts/launchd/ (optional)
    if opts.include_launchd:
        for name in (
            "com.libmatic.suggest-topics.weekly.plist.example",
            "com.libmatic.topic-debate.nightly.plist.example",
        ):
            _copy(
                TEMPLATES_DIR / "scripts" / "launchd" / name,
                target / "scripts" / "launchd" / name,
                opts=opts,
            )

    # 8. content/<category>/notes/.gitkeep + content/digest/.gitkeep
    for cat in opts.categories:
        gk = target / "content" / cat / "notes" / ".gitkeep"
        _write(gk, "", opts=opts)
    _write(target / "content" / "digest" / ".gitkeep", "", opts=opts)

    return opts
