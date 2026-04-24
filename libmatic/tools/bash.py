"""Bash tool."""

from __future__ import annotations

import subprocess

from langchain_core.tools import tool


@tool
def bash(cmd: str, timeout: int = 120) -> str:
    """Run a shell command with timeout. Returns 'exit=N\\n--- stdout ---\\n...\\n--- stderr ---\\n...'."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        return f"exit=timeout({timeout}s)\n--- stdout ---\n{e.stdout or ''}\n--- stderr ---\n{e.stderr or ''}"
    return (
        f"exit={result.returncode}\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
