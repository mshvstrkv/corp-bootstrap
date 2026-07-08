from __future__ import annotations

import shutil
import re
from urllib.parse import urlparse

from config import OperationResult
from config import Mode
from plugin_base import MigrationContext, MigrationPlugin, PlanItem


class GitPlugin(MigrationPlugin):
    name = "git"

    def validate(self, context: MigrationContext) -> list[str]:
        config = context.config
        config.workspace.mkdir(parents=True, exist_ok=True)
        repo = config.workspace / repository_name(config.gitverse_url)
        ensure_child_path(config.workspace, repo)
        if repo.exists() and any(repo.iterdir()):
            raise RuntimeError(f"Workspace repository already exists and is not empty: {repo}")
        print("Validating repository access...")
        context.git.clone(config.gitverse_url, repo)
        context.repo = repo
        print(f"Repository cloned: {repo}")
        branches = context.git.remote_branches(repo)
        context.state["git.remote_branches"] = branches
        if config.mode == Mode.MIGRATE:
            context.git.add_or_set_remote(repo, "bitbucket", config.bitbucket_url)
            synchronized = synchronize_all_branches(context, branches)
            context.state["git.all_branches_synchronized"] = synchronized
        else:
            context.state["git.all_branches_synchronized"] = []
        selected = config.branch or choose_primary_branch(branches)
        if selected not in branches:
            raise ValueError(f"Primary development branch '{selected}' does not exist in GitVerse repository")
        context.git.checkout(repo, selected)
        context.selected_branch = selected
        context.corporate_branch = config.corporate_branch_name or choose_corporate_branch(
            default=f"{selected}{context.standards.corporate_branch_suffix}"
        )
        context.state["git.clone_created"] = True
        return [
            "Repository cloned from GitVerse",
            f"Branches discovered: {len(branches)}",
            f"Branches synchronized to Bitbucket: {len(context.state['git.all_branches_synchronized']) if config.mode == Mode.MIGRATE else 'planned'}",
            f"Primary development branch selected: {selected}",
            f"Corporate branch selected: {context.corporate_branch}",
        ]

    def plan(self, context: MigrationContext) -> list[PlanItem]:
        source = context.selected_branch or "<selected branch>"
        corporate = context.corporate_branch or f"{source}{context.standards.corporate_branch_suffix}"
        branch_count = len(context.state.get("git.remote_branches", []))
        return [
            PlanItem(self.name, f"Synchronize all GitVerse branches to Bitbucket ({branch_count} branch(es))"),
            PlanItem(self.name, f"Create corporate branch {corporate}"),
            PlanItem(self.name, f"Push corporate branch {corporate}"),
        ]

    def execute(self, context: MigrationContext, dry_run: bool = False) -> OperationResult:
        if context.repo is None or context.selected_branch is None or context.corporate_branch is None:
            raise RuntimeError("Git plugin was not validated before execution")
        if dry_run:
            return OperationResult("Git migration planned", changed=False, message=f"Would create {context.corporate_branch}")
        if not context.state.get("git.all_branches_synchronized"):
            context.git.add_or_set_remote(context.repo, "bitbucket", context.config.bitbucket_url)
            context.state["git.all_branches_synchronized"] = synchronize_all_branches(context, context.state.get("git.remote_branches", []))
        context.git.create_branch(context.repo, context.corporate_branch)
        context.state["git.local_corporate_branch_created"] = True
        context.git.push_branch(context.repo, "bitbucket", context.corporate_branch)
        context.state["git.remote_corporate_branch_created"] = True
        synchronized_count = len(context.state.get("git.all_branches_synchronized", []))
        return OperationResult(
            f"{context.corporate_branch} created",
            changed=True,
            message=f"{synchronized_count} branch(es) synchronized; corporate branch created from {context.selected_branch}",
        )

    def rollback(self, context: MigrationContext) -> OperationResult:
        warnings: list[str] = []
        changed = False
        if context.repo is not None:
            try:
                context.git.restore_worktree(context.repo)
                changed = True
            except Exception as exc:
                warnings.append(f"Unable to restore local working tree: {exc}")
            if context.corporate_branch and context.state.get("git.local_corporate_branch_created"):
                try:
                    context.git.delete_local_branch(context.repo, context.corporate_branch, fallback_branch=context.selected_branch)
                    changed = True
                except Exception as exc:
                    warnings.append(f"Unable to delete local branch {context.corporate_branch}: {exc}")
            if context.corporate_branch and context.state.get("git.remote_corporate_branch_created"):
                try:
                    context.git.delete_remote_branch(context.repo, "bitbucket", context.corporate_branch)
                    changed = True
                except Exception as exc:
                    warnings.append(f"Remote branch {context.corporate_branch} was not deleted automatically: {exc}")
            if context.state.get("git.clone_created"):
                try:
                    ensure_child_path(context.config.workspace, context.repo)
                    shutil.rmtree(context.repo)
                    changed = True
                except Exception as exc:
                    warnings.append(f"Temporary clone was not removed automatically: {exc}")
        return OperationResult("Git rollback", changed=changed, message="Best-effort rollback completed", warnings=warnings)


def synchronize_all_branches(context: MigrationContext, branches: list[str]) -> list[str]:
    synchronized: list[str] = []
    for branch in branches:
        context.git.push_remote_branch(context.repo, "bitbucket", "origin", branch)
        synchronized.append(branch)
    return synchronized


def choose_primary_branch(branches: list[str]) -> str:
    print("Reading available Git branches...")
    print("Which branch is the primary development branch?")
    for index, branch in enumerate(branches, start=1):
        print(f"{index}. {branch}")
    while True:
        answer = input().strip()
        if answer.isdigit() and 1 <= int(answer) <= len(branches):
            return branches[int(answer) - 1]
        if answer in branches:
            return answer
        print("Please enter a valid primary branch number or branch name.")


def choose_corporate_branch(default: str) -> str:
    print("Corporate branch name")
    print("Default:")
    print(default)
    answer = input("Press Enter to accept or type another name.\n").strip()
    return answer or default


def repository_name(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or url
    name = path.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    if safe in {"", ".", ".."}:
        return "repository"
    return safe[:80]


def ensure_child_path(parent, child) -> None:
    parent_resolved = parent.resolve()
    child_resolved = child.resolve()
    if child_resolved == parent_resolved or parent_resolved not in child_resolved.parents:
        raise RuntimeError(f"Refusing to operate outside workspace: {child}")


def create_plugin() -> MigrationPlugin:
    return GitPlugin()
