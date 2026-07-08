from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from git_client import GitError
from plugin_base import MigrationContext
from plugins.git import ensure_child_path, repository_name


@dataclass
class SyncReport:
    total_branches: int = 0
    created_branches: list[str] = field(default_factory=list)
    updated_branches: list[str] = field(default_factory=list)
    skipped_branches: list[str] = field(default_factory=list)
    failed_branches: list[str] = field(default_factory=list)

    def render(self) -> str:
        return "\n".join(
            [
                "Sync Report",
                f"Total branches discovered: {self.total_branches}",
                "Created branches: " + render_branch_list(self.created_branches),
                "Updated branches: " + render_branch_list(self.updated_branches),
                "Skipped branches: " + render_branch_list(self.skipped_branches),
                "Failed branches: " + render_branch_list(self.failed_branches),
            ]
        )

    @property
    def ok(self) -> bool:
        return not self.failed_branches


def run_sync(context: MigrationContext) -> SyncReport:
    config = context.config
    config.workspace.mkdir(parents=True, exist_ok=True)
    repo = config.workspace / repository_name(config.gitverse_url)
    ensure_child_path(config.workspace, repo)
    if repo.exists() and any(repo.iterdir()):
        raise RuntimeError(f"Workspace repository already exists and is not empty: {repo}")

    context.git.clone(config.gitverse_url, repo)
    context.repo = repo
    context.git.fetch(repo, "origin")
    branches = context.git.remote_head_branches(repo, "origin")
    context.git.add_or_set_remote(repo, "bitbucket", config.bitbucket_url)
    bitbucket_heads = context.git.remote_heads(repo, "bitbucket")

    report = SyncReport(total_branches=len(branches))
    for branch in branches:
        try:
            context.git.push_remote_branch(repo, "bitbucket", "origin", branch)
        except GitError as exc:
            report.failed_branches.append(f"{branch}: {exc}")
            continue
        if branch in bitbucket_heads:
            report.updated_branches.append(branch)
        else:
            report.created_branches.append(branch)
    return report


def cleanup_sync_workspace(context: MigrationContext) -> None:
    if context.config.workspace_explicit or context.repo is None:
        return
    ensure_child_path(context.config.workspace, context.repo)
    shutil.rmtree(context.repo, ignore_errors=True)


def render_branch_list(branches: list[str]) -> str:
    return ", ".join(branches) if branches else "0"
