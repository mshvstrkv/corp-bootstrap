from __future__ import annotations

import argparse
import logging
import shutil
import sys
import tempfile
from pathlib import Path

from apply import ApplyOptions, parse_tasks, render_apply_plan, run_apply, validate_apply
from config import AppConfig, Mode
from git_client import GitClient, GitError
from moduleize import ModuleizeOptions, ModuleizeReport, ModuleizeRollbackError, confirm_module_name, confirm_moduleize, prepare_moduleize_plan, run_moduleize
from planner import MigrationExecutionError, build_plan, execute_plugins
from plugin_base import MigrationContext
from plugin_registry import PluginRegistry, PluginRegistryError
from report import MigrationReport, render_analysis
from standard_loader import StandardsError, load_standards
from sync import run_sync
from update import ConflictReport, UpdateOptions, confirm_update, parse_update_tasks, prepare_update_plan, run_update
from validation import ValidationError, analyze_project


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.verbose)
    try:
        standards = load_standards()
        mode = Mode(args.mode)
        if mode == Mode.ANALYZE:
            project = Path(args.project or Path.cwd()).resolve()
            from config import ProjectLayout

            analysis = analyze_project(ProjectLayout(project, app_module=standards.app_module), standards)
            analysis.primary_development_branch = args.branch
            analysis.corporate_branch = args.corporate_branch
            print(render_analysis(analysis))
            return 0

        if mode == Mode.APPLY:
            options = ApplyOptions(
                project=Path(args.project).resolve() if args.project else Path(),
                branch=args.branch,
                tasks=parse_tasks(args.tasks),
                commit=args.commit,
                push=args.push,
                yes=args.yes,
            )
            if args.project is None:
                raise ValueError("--project is required for apply mode")
            git = GitClient(logging.getLogger("corp-bootstrap.git"))
            layout = validate_apply(options, git, standards)
            branch = options.branch or git.current_branch(layout.root)
            plan = render_apply_plan(options, branch)
            print(plan)
            confirm_apply(args.yes)
            report = run_apply(options, git, standards, Path(__file__).resolve().parent)
            print(report.render())
            return 0

        if mode == Mode.UPDATE:
            if args.project is None:
                raise ValueError("--project is required for update mode")
            options = UpdateOptions(
                project=Path(args.project).resolve(),
                source_branch=args.source_branch,
                target_branch=args.target_branch,
                tasks=parse_update_tasks(args.tasks),
                commit=args.commit,
                push=args.push,
                yes=args.yes,
            )
            git = GitClient(logging.getLogger("corp-bootstrap.git"))
            plan = prepare_update_plan(options, git, standards)
            print(plan.render())
            confirm_update(plan, args.yes)
            report = run_update(plan, git, standards, Path(__file__).resolve().parent)
            print(report.render())
            return 1 if isinstance(report, ConflictReport) else 0

        if mode == Mode.MODULEIZE:
            if args.project is None:
                raise ValueError("--project is required for moduleize mode")
            git = GitClient(logging.getLogger("corp-bootstrap.git"))
            module_name = confirm_module_name(Path(args.project).resolve(), args.module_name, args.yes)
            options = ModuleizeOptions(
                project=Path(args.project).resolve(),
                module_name=module_name,
                commit=args.commit,
                yes=args.yes,
            )
            plan = prepare_moduleize_plan(options, git)
            confirm_moduleize(plan, args.yes)
            try:
                report = run_moduleize(options, git)
            except ModuleizeRollbackError as exc:
                print(ModuleizeReport(changed=False, rollback_actions=exc.rollback_actions).render())
                return 1
            print(report.render())
            return 0

        config = collect_config(args, mode, standards.corporate_branch_suffix)
        context = build_context(config, standards)
        if mode == Mode.SYNC:
            try:
                sync_report = run_sync(context)
            finally:
                cleanup_temporary_workspace(context)
            print(sync_report.render())
            return 0 if sync_report.ok else 1

        plugins = PluginRegistry(standards).load_plugins()
        validate_plugins(plugins, context)
        plan = build_plan(plugins, context)
        print(plan.render("Migration Plan" if mode == Mode.MIGRATE else "Dry Run Plan"))

        if mode == Mode.DRY_RUN:
            print()
            print(render_analysis(analyze_project(context.layout, standards)))
            cleanup_temporary_workspace(context)
            return 0

        try:
            confirm_migration(context, args.yes)
        except RuntimeError:
            cleanup_temporary_workspace(context)
            raise
        print("Running migration...")
        report = MigrationReport()
        try:
            results = execute_plugins(plugins, context, dry_run=False)
        except MigrationExecutionError as exc:
            for rollback_result in exc.rollback_results:
                report.add(rollback_result)
            report.add_error(f"Migration failed: {exc}")
            print(report.render())
            return 1
        for result in results:
            report.add(result)
        report.add_completed("Recommended next steps: review the Bitbucket diff, run service tests, and open the team migration pull request.")
        print(report.render())
        return 0
    except (GitError, ValidationError, RuntimeError, ValueError, StandardsError, PluginRegistryError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Migration cancelled by developer.", file=sys.stderr)
        return 130


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Migrate GitVerse Spring Boot services to corporate Bitbucket.")
    parser.add_argument("mode", choices=[mode.value for mode in Mode], nargs="?", default=Mode.MIGRATE.value)
    parser.add_argument("--gitverse-url", help="Source GitVerse repository URL")
    parser.add_argument("--bitbucket-url", help="Target corporate Bitbucket repository URL")
    parser.add_argument("--branch", help="GitVerse branch to migrate")
    parser.add_argument("--source-branch", help="GitVerse branch to merge from in update mode")
    parser.add_argument("--target-branch", help="Existing corporate branch to merge into in update mode")
    parser.add_argument("--corporate-branch", help="Corporate branch name to create from the primary development branch")
    parser.add_argument("--workspace", type=Path, help="Workspace used for clone operations")
    parser.add_argument("--project", type=Path, help="Existing project directory for analyze mode")
    parser.add_argument("--module-name", help="Application module name for moduleize mode")
    parser.add_argument("--tasks", help="Comma-separated apply tasks: logger, cleanup, maven")
    parser.add_argument("--commit", action="store_true", help="Create an apply commit when changes exist")
    parser.add_argument("--push", action="store_true", help="Push the current apply branch after commit")
    parser.add_argument("--yes", action="store_true", help="Confirm the generated migration plan non-interactively")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser


def setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(levelname)s %(message)s")


def collect_config(args: argparse.Namespace, mode: Mode, corporate_suffix: str) -> AppConfig:
    gitverse_url = args.gitverse_url or input("Please provide the GitVerse repository URL.\n").strip()
    bitbucket_url = args.bitbucket_url or input("Please provide the Bitbucket repository URL.\n").strip()
    if not gitverse_url or not bitbucket_url:
        raise ValueError("Both GitVerse and Bitbucket repository URLs are required")
    workspace_explicit = args.workspace is not None
    workspace = (args.workspace.resolve() if args.workspace else Path(tempfile.mkdtemp(prefix="corp-bootstrap-")).resolve())
    return AppConfig(
        gitverse_url=gitverse_url,
        bitbucket_url=bitbucket_url,
        branch=args.branch,
        corporate_branch_name=args.corporate_branch,
        corporate_suffix=corporate_suffix,
        workspace=workspace,
        mode=mode,
        workspace_explicit=workspace_explicit,
    )


def build_context(config: AppConfig, standards) -> MigrationContext:
    logger = logging.getLogger("corp-bootstrap")
    return MigrationContext(
        config=config,
        standards=standards,
        skill_root=Path(__file__).resolve().parent,
        git=GitClient(logging.getLogger("corp-bootstrap.git")),
        logger=logger,
    )


def validate_plugins(plugins, context: MigrationContext) -> None:
    for plugin in plugins:
        for message in plugin.validate(context):
            context.logger.info(message)


def confirm_migration(context: MigrationContext, assume_yes: bool) -> None:
    print()
    print("Migration Summary")
    print(f"Source: {context.config.gitverse_url}")
    print(f"Target: {context.config.bitbucket_url}")
    print(f"Source branch: {context.selected_branch}")
    print(f"Corporate branch: {context.corporate_branch}")
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise RuntimeError("Migration requires confirmation. Re-run with --yes after reviewing the plan.")
    answer = input("Proceed with migration? [y/N]\n").strip().lower()
    if answer not in {"y", "yes"}:
        raise RuntimeError("Migration cancelled before repository modification")


def confirm_apply(assume_yes: bool) -> None:
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise RuntimeError("Apply requires confirmation. Re-run with --yes after reviewing the plan.")
    answer = input("Proceed? [y/N]\n").strip().lower()
    if answer not in {"y", "yes"}:
        raise RuntimeError("Apply cancelled before repository modification")


def cleanup_temporary_workspace(context: MigrationContext) -> None:
    if context.config.workspace_explicit:
        return
    workspace = context.config.workspace.resolve()
    temp_root = Path(tempfile.gettempdir()).resolve()
    if workspace == temp_root or temp_root not in workspace.parents or not workspace.name.startswith("corp-bootstrap-"):
        return
    shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
