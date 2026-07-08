from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from apply import ApplyOptions, parse_tasks, run_apply
from config import Mode
from git_client import GitClient, GitError
from standard_loader import load_standards
from validation import ValidationError


ROOT_POM = """<?xml version="1.0" encoding="UTF-8"?>
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
</project>
"""

APP_POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <artifactId>service-app</artifactId>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>domain</artifactId>
            <version>1.0.0</version>
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


class ApplyModeTest(unittest.TestCase):
    def test_apply_logger_runs_only_logger_migration(self) -> None:
        with prepared_repo() as repo:
            maven_before = (repo / "pom.xml").read_text(encoding="utf-8")
            cleanup_file = repo / "Dockerfile"

            report = run_apply(options(repo, "logger"), git(), load_standards(), skill_root())

            source = (repo / "service-app/src/main/java/com/example/Service.java").read_text(encoding="utf-8")
            self.assertIn("@Slf4j", source)
            self.assertEqual((repo / "pom.xml").read_text(encoding="utf-8"), maven_before)
            self.assertTrue(cleanup_file.exists())
            self.assertEqual(report.commit, "not created")

    def test_apply_cleanup_runs_only_cleanup(self) -> None:
        with prepared_repo() as repo:
            source_before = (repo / "service-app/src/main/java/com/example/Service.java").read_text(encoding="utf-8")
            pom_before = (repo / "pom.xml").read_text(encoding="utf-8")

            run_apply(options(repo, "cleanup"), git(), load_standards(), skill_root())

            self.assertFalse((repo / "Dockerfile").exists())
            self.assertEqual((repo / "service-app/src/main/java/com/example/Service.java").read_text(encoding="utf-8"), source_before)
            self.assertEqual((repo / "pom.xml").read_text(encoding="utf-8"), pom_before)

    def test_apply_maven_runs_only_maven_migration(self) -> None:
        with prepared_repo() as repo:
            source_before = (repo / "service-app/src/main/java/com/example/Service.java").read_text(encoding="utf-8")

            run_apply(options(repo, "maven"), git(), load_standards(), skill_root())

            self.assertIn("<groupId>ru.sber.ai-payments</groupId>", (repo / "pom.xml").read_text(encoding="utf-8"))
            self.assertEqual((repo / "service-app/src/main/java/com/example/Service.java").read_text(encoding="utf-8"), source_before)
            self.assertTrue((repo / "Dockerfile").exists())

    def test_apply_without_commit_does_not_commit(self) -> None:
        with prepared_repo() as repo:
            before = commit_count(repo)

            run_apply(options(repo, "logger"), git(), load_standards(), skill_root())

            self.assertEqual(commit_count(repo), before)

    def test_apply_with_commit_creates_commit_only_when_changes_exist(self) -> None:
        with prepared_repo() as repo:
            before = commit_count(repo)

            run_apply(options(repo, "logger", commit=True), git(), load_standards(), skill_root())
            after_change = commit_count(repo)
            run_apply(options(repo, "logger", commit=True), git(), load_standards(), skill_root())

            self.assertEqual(after_change, before + 1)
            self.assertEqual(commit_count(repo), after_change)

    def test_apply_push_with_uncommitted_changes_requires_commit(self) -> None:
        with prepared_repo() as repo:
            add_remote(repo)

            with self.assertRaisesRegex(GitError, "Cannot push with uncommitted apply changes"):
                run_apply(options(repo, "logger", push=True), git(), load_standards(), skill_root())

    def test_invalid_task_name_fails(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported apply task"):
            parse_tasks("logger,bad")

    def test_missing_app_module_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            run_git(repo, "init")
            (repo / "pom.xml").write_text(ROOT_POM, encoding="utf-8")

            with self.assertRaises(ValidationError):
                run_apply(options(repo, "logger"), git(), load_standards(), skill_root())

    def test_repeated_apply_logger_is_idempotent(self) -> None:
        with prepared_repo() as repo:
            first = run_apply(options(repo, "logger"), git(), load_standards(), skill_root())
            run_git(repo, "add", "-A")
            run_git(repo, "commit", "-m", "logger")
            second = run_apply(options(repo, "logger"), git(), load_standards(), skill_root())

            self.assertTrue(first.changed_files)
            self.assertEqual(second.changed_files, [])


def options(repo: Path, tasks: str, commit: bool = False, push: bool = False) -> ApplyOptions:
    return ApplyOptions(project=repo, branch=None, tasks=parse_tasks(tasks), commit=commit, push=push, yes=True)


def git() -> GitClient:
    import logging

    return GitClient(logging.getLogger("test.git"))


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


def prepared_repo():
    temp = tempfile.TemporaryDirectory()
    repo = Path(temp.name)
    create_project(repo)
    return temp_repo_context(temp, repo)


class temp_repo_context:
    def __init__(self, temp: tempfile.TemporaryDirectory, repo: Path) -> None:
        self.temp = temp
        self.repo = repo

    def __enter__(self) -> Path:
        return self.repo

    def __exit__(self, exc_type, exc, tb) -> None:
        self.temp.cleanup()


def create_project(repo: Path) -> None:
    run_git(repo, "init")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test User")
    (repo / "pom.xml").write_text(ROOT_POM, encoding="utf-8")
    app = repo / "service-app"
    (app / "src/main/java/com/example").mkdir(parents=True)
    (app / "pom.xml").write_text(APP_POM, encoding="utf-8")
    (app / "src/main/java/com/example/Service.java").write_text(LOGGER_SOURCE, encoding="utf-8")
    (repo / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    run_git(repo, "add", "-A")
    run_git(repo, "commit", "-m", "initial")


def add_remote(repo: Path) -> None:
    bare = repo.parent / "remote.git"
    run_git(bare, "init", "--bare")
    run_git(repo, "remote", "add", "bitbucket", str(bare))


def commit_count(repo: Path) -> int:
    return int(run_git(repo, "rev-list", "--count", "HEAD"))


def run_git(repo: Path, *args: str) -> str:
    repo.mkdir(parents=True, exist_ok=True)
    completed = subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise AssertionError(completed.stderr or completed.stdout)
    return completed.stdout.strip()


if __name__ == "__main__":
    unittest.main()
