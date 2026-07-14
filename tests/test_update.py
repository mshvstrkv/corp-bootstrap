from __future__ import annotations

import tempfile
import unittest
from contextlib import contextmanager
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from git_client import MergeResult, GitError
from standard_loader import load_standards
from update import (
    UpdateOptions,
    UpdatePlan,
    parse_update_tasks,
    prepare_update_plan,
    run_update,
)


class FakeUpdateGit:
    def __init__(
        self,
        source_branches: list[str] | None = None,
        target_branches: list[str] | None = None,
        local_branches: list[str] | None = None,
        commits: dict[str, int] | None = None,
    ) -> None:
        self.source_branches = source_branches or ["develop", "module"]
        self.target_branches = target_branches or ["develop-corp"]
        self._local_branches = local_branches or []
        self.commits = commits or {"develop": 10, "module": 2}
        self.fetched: list[str] = []
        self.checked_out: list[tuple[str, str]] = []
        self.merged: list[tuple[str, str]] = []
        self.applied_tasks: list[list[str]] = []
        self.commits_created: list[str] = []
        self.pushed: list[tuple[str, str]] = []
        self.merge_result = MergeResult(ok=True, conflicts=[])
        self.changed = False
        self.root_src_files: list[str] = []
        self.app_module_exists_at_merge = False

    def is_git_repository(self, repo: Path) -> bool:
        return True

    def remotes(self, repo: Path) -> list[str]:
        return ["origin", "bitbucket"]

    def fetch(self, repo: Path, remote: str) -> None:
        self.fetched.append(remote)

    def local_branches(self, repo: Path) -> list[str]:
        return self._local_branches

    def remote_tracking_branches(self, repo: Path, remote: str) -> list[str]:
        return self.source_branches if remote == "origin" else self.target_branches

    def remote_tracking_branch_exists(self, repo: Path, remote: str, branch: str) -> bool:
        return remote == "bitbucket" and branch in self.target_branches

    def commits_ahead(self, repo: Path, source_ref: str, target_ref: str) -> int:
        return self.commits[source_ref.removeprefix("origin/")]

    def checkout_target_branch(self, repo: Path, branch: str, remote: str) -> None:
        self.checked_out.append((branch, remote))

    def merge(self, repo: Path, source_ref: str, message: str) -> MergeResult:
        self.app_module_exists_at_merge = (repo / "service-app").exists()
        self.merged.append((source_ref, message))
        return self.merge_result

    def added_root_src_files(self, repo: Path) -> list[str]:
        return self.root_src_files

    def changed_files(self, repo: Path) -> list[str]:
        return ["service-app/src/main/java/App.java"] if self.changed else []

    def has_changes(self, repo: Path) -> bool:
        return self.changed

    def commit(self, repo: Path, message: str) -> bool:
        self.commits_created.append(message)
        self.changed = False
        return True

    def push_current_branch(self, repo: Path, remote: str, branch: str) -> None:
        self.pushed.append((remote, branch))


class UpdateModeTest(unittest.TestCase):
    def test_update_asks_for_source_branch_when_omitted(self) -> None:
        with temp_project() as project:
            git = FakeUpdateGit()
            with interactive_inputs(["1"]):
                plan = prepare_update_plan(
                    UpdateOptions(project=project, source_branch=None, target_branch="develop-corp", yes=False),
                    git,
                    load_standards(),
                )

            self.assertEqual(plan.source_branch, "develop")

    def test_update_asks_for_target_branch_when_omitted(self) -> None:
        with temp_project() as project:
            git = FakeUpdateGit(target_branches=["release-corp", "develop-corp"])
            with interactive_inputs(["2"]):
                plan = prepare_update_plan(
                    UpdateOptions(project=project, source_branch="module", target_branch=None, yes=False),
                    git,
                    load_standards(),
                )

            self.assertEqual(plan.target_branch, "release-corp")

    def test_yes_requires_source_and_target(self) -> None:
        with temp_project() as project:
            with self.assertRaisesRegex(ValueError, "--source-branch and --target-branch"):
                prepare_update_plan(UpdateOptions(project=project, source_branch=None, target_branch="develop-corp", yes=True), FakeUpdateGit(), load_standards())

    def test_update_does_not_assume_develop_or_module(self) -> None:
        with temp_project() as project:
            git = FakeUpdateGit(source_branches=["develop", "module"], commits={"develop": 10, "module": 2})
            with interactive_inputs(["2"]):
                plan = prepare_update_plan(
                    UpdateOptions(project=project, source_branch=None, target_branch="develop-corp", yes=False),
                    git,
                    load_standards(),
                )

            self.assertEqual(plan.source_branch, "module")

    def test_target_branch_must_already_exist(self) -> None:
        with temp_project() as project:
            with self.assertRaisesRegex(GitError, "Target branch must already exist"):
                prepare_update_plan(
                    UpdateOptions(project=project, source_branch="develop", target_branch="missing-corp", yes=True),
                    FakeUpdateGit(target_branches=["develop-corp"]),
                    load_standards(),
                )

    def test_merge_uses_selected_source_and_target(self) -> None:
        with temp_project() as project:
            git = FakeUpdateGit()
            plan = update_plan(project, source="module", target="release-corp")
            with patched_apply(git):
                run_update(plan, git, load_standards(), project)

            self.assertEqual(git.checked_out, [("release-corp", "bitbucket")])
            self.assertEqual(git.merged[0][0], "origin/module")
            self.assertIn("Merge module from GitVerse into release-corp", git.merged[0][1])

    def test_merge_conflict_stops_before_apply_commit_and_push(self) -> None:
        with temp_project() as project:
            git = FakeUpdateGit()
            git.merge_result = MergeResult(ok=False, conflicts=["service-app/src/main/java/App.java"])
            plan = update_plan(project, commit=True, push=True)
            with patched_apply(git):
                report = run_update(plan, git, load_standards(), project)

            self.assertIn("Merge conflicts detected", report.render())
            self.assertEqual(git.applied_tasks, [])
            self.assertEqual(git.commits_created, [])
            self.assertEqual(git.pushed, [])

    def test_root_src_added_files_are_hints_only(self) -> None:
        with temp_project() as project:
            git = FakeUpdateGit()
            git.merge_result = MergeResult(ok=False, conflicts=["pom.xml"])
            git.root_src_files = ["src/main/java/NewController.java"]

            report = run_update(update_plan(project), git, load_standards(), project)

            rendered = report.render()
            self.assertIn("Detected files added under root src/ during merge.", rendered)
            self.assertIn("They probably need to be moved into <app-module>/src/.", rendered)
            self.assertEqual(git.applied_tasks, [])

    def test_successful_merge_runs_selected_apply_tasks(self) -> None:
        with temp_project() as project:
            git = FakeUpdateGit()
            with patched_apply(git):
                run_update(update_plan(project, tasks=["logger", "cleanup"]), git, load_standards(), project)

            self.assertEqual(git.applied_tasks, [["logger", "cleanup"]])

    def test_update_moduleizes_single_module_project_before_apply(self) -> None:
        with single_module_project() as project:
            git = FakeUpdateGit()

            run_update(update_plan(project, tasks=["logger"]), git, load_standards(), skill_root())

            self.assertTrue(git.app_module_exists_at_merge)
            self.assertFalse((project / "src").exists())
            source = project / "service-app" / "src" / "main" / "java" / "com" / "example" / "Service.java"
            self.assertTrue(source.is_file())
            self.assertIn("@Slf4j", source.read_text(encoding="utf-8"))
            self.assertIn("<artifactId>service-app</artifactId>", (project / "service-app" / "pom.xml").read_text(encoding="utf-8"))

    def test_tasks_logger_runs_logger_only(self) -> None:
        self.assertEqual(parse_update_tasks("logger"), ["logger"])

    def test_tasks_logger_cleanup_runs_only_logger_and_cleanup(self) -> None:
        self.assertEqual(parse_update_tasks("logger,cleanup"), ["logger", "cleanup"])

    def test_push_without_commit_fails_with_uncommitted_changes(self) -> None:
        with temp_project() as project:
            git = FakeUpdateGit()
            git.changed = True
            with patched_apply(git), self.assertRaisesRegex(GitError, "Cannot push with uncommitted update changes"):
                run_update(update_plan(project, push=True, commit=False), git, load_standards(), project)

    def test_successful_push_uses_normal_branch_push(self) -> None:
        with temp_project() as project:
            git = FakeUpdateGit()
            with patched_apply(git):
                run_update(update_plan(project, push=True, commit=True), git, load_standards(), project)

            self.assertEqual(git.pushed, [("bitbucket", "develop-corp")])


def update_plan(project: Path, source: str = "develop", target: str = "develop-corp", tasks: list[str] | None = None, commit: bool = False, push: bool = False) -> UpdatePlan:
    return UpdatePlan(
        project=project,
        source_remote="origin",
        target_remote="bitbucket",
        source_branch=source,
        target_branch=target,
        tasks=tasks or ["logger"],
        commit=commit,
        push=push,
    )


def patched_apply(git: FakeUpdateGit):
    def record(layout, tasks, standards, skill_root):
        git.applied_tasks.append(tasks)
        return []

    return patch.multiple("update", run_apply_tasks=record, validate_project=lambda layout: "service-app")


@contextmanager
def interactive_inputs(values: list[str]):
    answers = iter(values)
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("builtins.input", side_effect=lambda prompt="": next(answers)),
        patch("sys.stdout", new_callable=StringIO),
    ):
        yield


class temp_project:
    def __enter__(self) -> Path:
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        return self.project

    def __exit__(self, exc_type, exc, tb) -> None:
        self.temp.cleanup()


class single_module_project:
    def __enter__(self) -> Path:
        self.temp = tempfile.TemporaryDirectory()
        self.project = Path(self.temp.name)
        (self.project / "pom.xml").write_text(SINGLE_MODULE_POM, encoding="utf-8")
        source_dir = self.project / "src" / "main" / "java" / "com" / "example"
        source_dir.mkdir(parents=True)
        (source_dir / "Service.java").write_text(LOGGER_SOURCE, encoding="utf-8")
        return self.project

    def __exit__(self, exc_type, exc, tb) -> None:
        self.temp.cleanup()


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


SINGLE_MODULE_POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <artifactId>service</artifactId>
    <description>Service</description>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
</project>
"""


LOGGER_SOURCE = """package com.example;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class Service {
    private static final Logger log = LoggerFactory.getLogger(Service.class);

    public void run() {
        log.info("run");
    }
}
"""


if __name__ == "__main__":
    unittest.main()
