from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from config import OperationResult, ProjectLayout
from git_client import GitError
from migrators import app_pom, distributive, root_pom
from plugins.cleanup import cleanup_project
from plugins.logger import migrate_loggers
from standard_loader import Standards
from validation import ValidationError, detect_application_module, validate_project


SUPPORTED_TASKS = {"logger", "cleanup", "maven"}


@dataclass
class ApplyOptions:
    project: Path
    branch: str | None
    tasks: list[str]
    commit: bool = False
    push: bool = False
    yes: bool = False


@dataclass
class ApplyReport:
    tasks: list[str]
    changed_files: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    commit: str = "not created"
    push: str = "not performed"

    def render(self) -> str:
        lines = [
            "Apply completed",
            "",
            "Tasks:",
            "  " + ", ".join(self.tasks),
            "",
            "Changed files:",
        ]
        if self.changed_files:
            lines.extend(f"  {path}" for path in self.changed_files)
        else:
            lines.append("  none")
        lines.extend(
            [
                "",
                "Skipped:",
            ]
        )
        lines.extend(f"  {item}" for item in self.skipped)
        lines.extend(
            [
                "",
                "Commit:",
                f"  {self.commit}",
                "",
                "Push:",
                f"  {self.push}",
            ]
        )
        return "\n".join(lines)


def parse_tasks(raw: str | None) -> list[str]:
    if raw is None or not raw.strip():
        raise ValueError("--tasks is required for apply mode")
    tasks = [part.strip() for part in raw.split(",") if part.strip()]
    invalid = [task for task in tasks if task not in SUPPORTED_TASKS]
    if invalid:
        raise ValueError("Unsupported apply task(s): " + ", ".join(invalid))
    ordered: list[str] = []
    for task in tasks:
        if task not in ordered:
            ordered.append(task)
    return ordered


def validate_apply(options: ApplyOptions, git, standards: Standards) -> ProjectLayout:
    project = options.project.resolve()
    if not project.exists():
        raise ValidationError(f"Apply project does not exist: {project}")
    if not project.is_dir():
        raise ValidationError(f"Apply project must be a directory: {project}")
    if not (project / ".git").exists():
        raise ValidationError(f"Apply project is not a Git repository: {project}")
    if options.branch:
        git.verify_local_branch(project, options.branch)
    app_module = validate_project(ProjectLayout(project, app_module=standards.app_module))
    return ProjectLayout(project, app_module=app_module)


def render_apply_plan(options: ApplyOptions, branch: str) -> str:
    modify = {
        "logger": "Java files matching LoggerFactory pattern",
        "cleanup": "configured cleanup targets",
        "maven": "Maven files generated from corporate references",
    }
    will_not = [
        "sync branches",
        "create corporate branch",
    ]
    if "maven" not in options.tasks:
        will_not.append("migrate Maven")
    if "cleanup" not in options.tasks:
        will_not.append("cleanup files")
    if not options.commit:
        will_not.append("commit")
    if not options.push:
        will_not.append("push")
    return "\n".join(
        [
            "Apply Plan",
            "",
            "Project:",
            f"  {options.project.resolve()}",
            "",
            "Branch:",
            f"  {branch}",
            "",
            "Tasks:",
            "  " + ", ".join(options.tasks),
            "",
            "Will modify:",
            *[f"  {modify[task]}" for task in options.tasks],
            "",
            "Will NOT:",
            *[f"  {item}" for item in will_not],
        ]
    )


def run_apply(options: ApplyOptions, git, standards: Standards, skill_root: Path) -> ApplyReport:
    layout = validate_apply(options, git, standards)
    if options.branch:
        git.checkout_existing(layout.root, options.branch)
        branch = options.branch
    else:
        branch = git.current_branch(layout.root)
    run_apply_tasks(layout, options.tasks, standards, skill_root)

    changed_files = git.changed_files(layout.root)
    if options.push and not options.commit and changed_files:
        raise GitError("Cannot push with uncommitted apply changes. Re-run with --commit or commit changes manually.")

    report = ApplyReport(tasks=options.tasks, changed_files=changed_files, skipped=skipped_tasks(options.tasks))
    if options.commit:
        if git.has_changes(layout.root):
            message = "Apply corporate tasks: " + ", ".join(options.tasks)
            committed = git.commit(layout.root, message)
            report.commit = "created" if committed else "not created"
            report.changed_files = git.changed_files(layout.root)
        else:
            report.commit = "not created"
    if options.push:
        remote = choose_push_remote(git.remotes(layout.root))
        git.push_current_branch(layout.root, remote, branch)
        report.push = f"pushed to {remote}/{branch}"
    return report


def run_apply_tasks(layout: ProjectLayout, tasks: list[str], standards: Standards, skill_root: Path) -> list[OperationResult]:
    results: list[OperationResult] = []
    for task in tasks:
        if task == "logger":
            results.append(migrate_loggers(layout.app_src, standards.migration_rules["logger"]))
        elif task == "cleanup":
            results.append(cleanup_project(layout.root, standards.cleanup["targets"]))
        elif task == "maven":
            results.extend(run_maven_apply(layout, skill_root))
    return results


def run_maven_apply(layout: ProjectLayout, skill_root: Path) -> list[OperationResult]:
    reference_dir = skill_root / "corporate-reference"
    return [
        root_pom.migrate(layout.root_pom),
        app_pom.migrate(layout.app_pom),
        distributive.migrate(layout.root, skill_root / "templates"),
    ]


def skipped_tasks(tasks: list[str]) -> list[str]:
    skipped = ["Git sync"]
    if "maven" not in tasks:
        skipped.append("Maven migration")
    if "cleanup" not in tasks:
        skipped.append("Cleanup")
    if "logger" not in tasks:
        skipped.append("Logger migration")
    return skipped


def choose_push_remote(remotes: list[str]) -> str:
    if "bitbucket" in remotes:
        return "bitbucket"
    if "origin" in remotes:
        return "origin"
    if len(remotes) == 1:
        return remotes[0]
    raise GitError("No Git remote is configured for push")
