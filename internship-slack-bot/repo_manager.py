"""
repo_manager.py — Clone or pull the internship listings GitHub repo.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

CLONED_REPO_DIR = "internships_repo"


def _run(cmd: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )


def ensure_repo(repo_url: str, branch: str | None = None) -> Path:
    """Clone the repo if absent, otherwise pull latest. Returns the repo root Path."""
    repo_path = Path(CLONED_REPO_DIR)

    if repo_path.exists() and (repo_path / ".git").exists():
        logger.info("Pulling latest from %s", repo_url)
        result = _run(["git", "pull", "--ff-only"], cwd=str(repo_path))
        if result.returncode != 0:
            raise RuntimeError(
                f"git pull failed (exit {result.returncode}):\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )
        logger.debug("git pull output: %s", result.stdout.strip())
    else:
        logger.info("Cloning %s → %s", repo_url, repo_path)
        cmd = ["git", "clone"]
        if branch:
            cmd += ["--branch", branch, "--single-branch"]
        cmd += [repo_url, str(repo_path)]
        result = _run(cmd)
        if result.returncode != 0:
            raise RuntimeError(
                f"git clone failed (exit {result.returncode}):\n"
                f"stdout: {result.stdout}\nstderr: {result.stderr}"
            )

    return repo_path
