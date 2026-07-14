from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

from apply import parse_tasks, run_apply_tasks
from config import ProjectLayout
from git_client import GitError
from moduleize import corporate_moduleize_if_needed
from standard_loader import Standards
from validation import ValidationError, validate_project


DEFAULT_UPDATE_TASKS = ["logger"]


@dataclass
class UpdateOptions:
    project: Path
    source_branch: str | None
    target_branch: str | None
    tasks: list[str] = field(default_factory=lambda: DEFAULT_UPDATE_TASKS.copy())
    commit: bool = False
    push: bool = False
    yes: bool = False


@dataclass(frozen=True)
class CandidateBranch:
    name: str
    commits_ahead: int


@dataclass
class UpdatePlan:
    project: Path
    source_remote: str
    target_remote: str
    source_branch: str
    target_branch: str
    tasks: list[str]
    commit: bool
    push: bool

    @property
    def source_ref(self) -> str:
        return f"{self.source_remote}/{self.source_branch}"

    @property
    def target_ref(self) -> str:
        return f"{self.target_remote}/{self.target_branch}"

    def render(self) -> str:
        actions = [
            f"fetch {self.source_remote}",
            f"fetch {self.target_remote}",
            f"checkout {self.target_branch}",
            f"merge {self.source_ref}",
        ]
        actions.extend(f"apply {task}" for task in self.tasks)
        if self.commit:
            actions.append("commit")
        if self.push:
            actions.append("push")
        will_not = [
            "sync all branches",
            "create corporate branch",
            "run full migration",
            "run Maven unless requested",
            "run cleanup unless requested",
            "force-push",
        ]
        return "\n".join(
            [
                "Update Plan",
                "",
                "Project:",
                f"  {self.project}",
                "",
                "Source branch:",
                f"  {self.source_ref}",
                "",
                "Target branch:",
                f"  {self.target_ref}",
                "",
                "Tasks after merge:",
                "  " + ", ".join(self.tasks),
                "",
                "Will perform:",
                *[f"  {action}" for action in actions],
                "",
                "Will NOT:",
                *[f"  {item}" for item in will_not],
            ]
        )


@dataclass
class UpdateReport:
    source_branch: str
    target_branch: str
    tasks: list[str]
    merge: str
    changed_files: list[str] = field(default_factory=list)
    commit: str = "not created"
    push: str = "not performed"

    def render(self) -> str:
        lines = [
            "Update completed",
            "",
            "Source:",
            f"  {self.source_branch}",
            "",
            "Target:",
            f"  {self.target_branch}",
            "",
            "Merge:",
            f"  {self.merge}",
            "",
            "Tasks:",
            "  " + ", ".join(self.tasks),
            "",
            "Changed files:",
        ]
        lines.extend(f"  {path}" for path in self.changed_files) if self.changed_files else lines.append("  none")
        lines.extend(["", "Commit:", f"  {self.commit}", "", "Push:", f"  {self.push}"])
        return "\n".join(lines)


@dataclass
class ConflictReport:
    source_ref: str
    target_branch: str
    conflicted_files: list[str]
    root_src_files: list[str]
    project: Path
    tasks: list[str]
    message: str = ""

    def render(self) -> str:
        lines = [
            "Merge conflicts detected.",
            "",
            "Source:",
            f"  {self.source_ref}",
            "",
            "Target:",
            f"  {self.target_branch}",
            "",
            "Conflicted files:",
        ]
        lines.extend(f"  {path}" for path in self.conflicted_files)
        if self.root_src_files:
            lines.extend(
                [
                    "",
                    "Files added in old root src/ that may need to be moved into app module:",
                    *[f"  {path}" for path in self.root_src_files],
                    "",
                    "Detected files added under root src/ during merge.",
                    "They probably need to be moved into <app-module>/src/.",
                ]
            )
        lines.extend(
            [
                "",
                "Resolve conflicts manually, then run:",
                "",
                "  git status",
                "  git add .",
                "  git commit",
                "",
                "After that, run:",
                "",
                f"  python3 bootstrap.py apply --project {self.project} --branch {self.target_branch} --tasks {','.join(self.tasks)} --commit --push",
            ]
        )
        return "\n".join(lines)


def parse_update_tasks(raw: str | None) -> list[str]:
    if raw is None or not raw.strip():
        return DEFAULT_UPDATE_TASKS.copy()
    return parse_tasks(raw)


def prepare_update_plan(options: UpdateOptions, git, standards: Standards) -> UpdatePlan:
    project = validate_update_project(options.project, git)
    if options.yes and (not options.source_branch or not options.target_branch):
        raise ValueError("--source-branch and --target-branch are required with update --yes")

    remotes = git.remotes(project)
    source_remote = choose_remote(remotes, "origin", "GitVerse", options.yes)
    target_remote = choose_remote(remotes, "bitbucket", "Bitbucket", options.yes)
    git.fetch(project, source_remote)
    git.fetch(project, target_remote)

    available_targets = available_target_branches(git, project, target_remote)
    target_branch = options.target_branch or ask_target_branch(available_targets)
    if target_branch not in available_targets:
        raise GitError(f"Target branch must already exist locally or on {target_remote}: {target_branch}")

    source_branches = git.remote_tracking_branches(project, source_remote)
    if not source_branches:
        raise GitError(f"No GitVerse branches were found on remote {source_remote}")
    source_branch = options.source_branch
    if source_branch is None:
        candidates = candidate_source_branches(git, project, source_remote, target_ref_for_counts(git, project, target_remote, target_branch), source_branches)
        source_branch = ask_source_branch(candidates, target_branch)
    if source_branch not in source_branches:
        raise GitError(f"Source branch does not exist on {source_remote}: {source_branch}")

    return UpdatePlan(
        project=project,
        source_remote=source_remote,
        target_remote=target_remote,
        source_branch=source_branch,
        target_branch=target_branch,
        tasks=options.tasks,
        commit=options.commit,
        push=options.push,
    )


def run_update(plan: UpdatePlan, git, standards: Standards, skill_root: Path) -> UpdateReport | ConflictReport:
    git.checkout_target_branch(plan.project, plan.target_branch, plan.target_remote)
    corporate_moduleize_if_needed(plan.project, skill_root / "corporate-reference", standards.maven_template_values)
    merge_result = git.merge(
        plan.project,
        plan.source_ref,
        f"Merge {plan.source_branch} from GitVerse into {plan.target_branch}",
    )
    if not merge_result.ok:
        return ConflictReport(
            source_ref=plan.source_ref,
            target_branch=plan.target_branch,
            conflicted_files=merge_result.conflicts,
            root_src_files=git.added_root_src_files(plan.project),
            project=plan.project,
            tasks=plan.tasks,
            message=merge_result.message,
        )

    layout = ProjectLayout(plan.project, app_module=validate_project(ProjectLayout(plan.project, app_module=standards.app_module)))
    run_apply_tasks(layout, plan.tasks, standards, skill_root)

    changed_files = git.changed_files(plan.project)
    if plan.push and not plan.commit and changed_files:
        raise GitError("Cannot push with uncommitted update changes. Re-run with --commit or commit changes manually.")

    report = UpdateReport(
        source_branch=plan.source_ref,
        target_branch=plan.target_branch,
        tasks=plan.tasks,
        merge="completed",
        changed_files=changed_files,
    )
    if plan.commit and git.has_changes(plan.project):
        git.commit(plan.project, "Apply corporate tasks after update: " + ",".join(plan.tasks))
        report.commit = "created"
        report.changed_files = git.changed_files(plan.project)
    if plan.push:
        git.push_current_branch(plan.project, plan.target_remote, plan.target_branch)
        report.push = f"pushed to {plan.target_remote}/{plan.target_branch}"
    return report


def validate_update_project(project: Path, git) -> Path:
    resolved = project.resolve()
    if not resolved.exists():
        raise ValidationError(f"Update project does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValidationError(f"Update project must be a directory: {resolved}")
    if not git.is_git_repository(resolved):
        raise ValidationError(f"Update project is not a Git repository: {resolved}")
    return resolved


def available_target_branches(git, project: Path, remote: str) -> list[str]:
    return sorted(set(git.local_branches(project)) | set(git.remote_tracking_branches(project, remote)))


def target_ref_for_counts(git, project: Path, remote: str, branch: str) -> str:
    if git.remote_tracking_branch_exists(project, remote, branch):
        return f"{remote}/{branch}"
    return branch


def candidate_source_branches(git, project: Path, remote: str, target_ref: str, source_branches: list[str]) -> list[CandidateBranch]:
    candidates = [
        CandidateBranch(name=branch, commits_ahead=git.commits_ahead(project, f"{remote}/{branch}", target_ref))
        for branch in source_branches
    ]
    with_changes = [candidate for candidate in candidates if candidate.commits_ahead > 0]
    return sorted(with_changes or candidates, key=lambda item: (item.commits_ahead == 0, item.name))


def choose_remote(remotes: list[str], preferred: str, label: str, assume_yes: bool) -> str:
    if preferred in remotes:
        return preferred
    if assume_yes:
        raise GitError(f"{label} remote '{preferred}' is not configured. Configure remotes or run update interactively.")
    if not sys.stdin.isatty():
        raise GitError(f"{label} remote '{preferred}' is not configured and cannot be selected non-interactively.")
    if not remotes:
        raise GitError(f"No Git remotes are configured for {label}")
    print(f"Select {label} remote:")
    for index, remote in enumerate(remotes, start=1):
        print(f"{index}. {remote}")
    return select_numbered(remotes, f"Which remote should be used for {label}?\n")


def ask_target_branch(branches: list[str]) -> str:
    if not branches:
        raise GitError("No existing corporate branches were found locally or on Bitbucket.")
    print("Available corporate branches:")
    for index, branch in enumerate(branches, start=1):
        print(f"{index}. {branch}")
    return select_numbered(branches, "Which corporate branch should be updated?\n")


def ask_source_branch(candidates: list[CandidateBranch], target_branch: str) -> str:
    if not candidates:
        raise GitError("No GitVerse branches are available to merge.")
    print(f"GitVerse branches with commits not in {target_branch}:")
    for index, candidate in enumerate(candidates, start=1):
        print(f"{index}. {candidate.name} (+{candidate.commits_ahead} commits)")
    return select_numbered([candidate.name for candidate in candidates], f"Из какой GitVerse ветки мержить изменения в {target_branch}?\n")


def select_numbered(values: list[str], prompt: str) -> str:
    if not sys.stdin.isatty():
        raise RuntimeError("Update requires an interactive selection. Re-run with explicit branch arguments and --yes.")
    answer = input(prompt).strip()
    try:
        index = int(answer)
    except ValueError as exc:
        raise ValueError("Selection must be a number") from exc
    if index < 1 or index > len(values):
        raise ValueError("Selection is outside the available range")
    return values[index - 1]


def confirm_update(plan: UpdatePlan, assume_yes: bool) -> None:
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise RuntimeError("Update requires confirmation. Re-run with --yes after reviewing the plan.")
    answer = input("Proceed? [y/N]\n").strip().lower()
    if answer not in {"y", "yes"}:
        raise RuntimeError("Update cancelled before repository modification")
