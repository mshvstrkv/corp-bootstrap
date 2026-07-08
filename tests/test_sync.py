from __future__ import annotations

import logging
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import bootstrap
from config import AppConfig, Mode
from git_client import GitClient, GitError
from plugin_base import MigrationContext
from standard_loader import load_standards
from sync import run_sync


class FakeSyncGit:
    def __init__(self, branches: list[str], existing: dict[str, str] | None = None, fail: set[str] | None = None) -> None:
        self.branches = branches
        self.existing = existing or {}
        self.fail = fail or set()
        self.fetched: list[str] = []
        self.remotes: list[tuple[str, str]] = []
        self.pushed: list[tuple[str, str, str]] = []
        self.created_branches: list[str] = []
        self.commits: list[str] = []

    def clone(self, url: str, destination: Path) -> None:
        destination.mkdir(parents=True)

    def fetch(self, repo: Path, remote: str = "origin") -> None:
        self.fetched.append(remote)

    def remote_head_branches(self, repo: Path, remote: str = "origin") -> list[str]:
        return self.branches

    def add_or_set_remote(self, repo: Path, name: str, url: str) -> None:
        self.remotes.append((name, url))

    def remote_heads(self, repo: Path, remote: str) -> dict[str, str]:
        return self.existing

    def push_remote_branch(self, repo: Path, remote: str, source_remote: str, branch: str) -> None:
        if branch in self.fail:
            raise GitError("push rejected")
        self.pushed.append((remote, source_remote, branch))

    def create_branch(self, repo: Path, branch: str) -> None:
        self.created_branches.append(branch)

    def commit(self, repo: Path, message: str) -> bool:
        self.commits.append(message)
        return True


class RecordingGitClient(GitClient):
    def __init__(self) -> None:
        super().__init__(logging.getLogger("test"))
        self.commands: list[list[str]] = []

    def _run(self, args: list[str], cwd: Path | None = None) -> str:
        self.commands.append(args)
        if args[:2] == ["ls-remote", "--heads"]:
            return "\n".join(
                [
                    "1111111111111111111111111111111111111111\trefs/heads/main",
                    "2222222222222222222222222222222222222222\trefs/tags/v1",
                    "3333333333333333333333333333333333333333\trefs/heads/feature/a",
                ]
            )
        return ""


class SyncModeTest(unittest.TestCase):
    def test_sync_only_pushes_gitverse_heads_to_bitbucket(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_git = FakeSyncGit(["develop", "feature/a", "release"], existing={"develop": "abc"})
            context = MigrationContext(
                config=AppConfig(
                    "https://gitverse.example/service.git",
                    "https://bitbucket.example/service.git",
                    workspace=Path(tmp),
                    mode=Mode.SYNC,
                    workspace_explicit=True,
                ),
                standards=load_standards(),
                skill_root=Path.cwd(),
                git=fake_git,
                logger=logging.getLogger("test"),
            )

            report = run_sync(context)

            self.assertEqual(report.total_branches, 3)
            self.assertEqual(report.created_branches, ["feature/a", "release"])
            self.assertEqual(report.updated_branches, ["develop"])
            self.assertEqual(report.skipped_branches, [])
            self.assertEqual(report.failed_branches, [])
            self.assertEqual(fake_git.fetched, ["origin"])
            self.assertEqual(fake_git.remotes, [("bitbucket", "https://bitbucket.example/service.git")])
            self.assertEqual(
                fake_git.pushed,
                [("bitbucket", "origin", "develop"), ("bitbucket", "origin", "feature/a"), ("bitbucket", "origin", "release")],
            )
            self.assertEqual(fake_git.created_branches, [])
            self.assertEqual(fake_git.commits, [])

    def test_sync_report_keeps_pushing_after_branch_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_git = FakeSyncGit(["develop", "release"], fail={"develop"})
            context = MigrationContext(
                config=AppConfig(
                    "https://gitverse.example/service.git",
                    "https://bitbucket.example/service.git",
                    workspace=Path(tmp),
                    mode=Mode.SYNC,
                    workspace_explicit=True,
                ),
                standards=load_standards(),
                skill_root=Path.cwd(),
                git=fake_git,
                logger=logging.getLogger("test"),
            )

            report = run_sync(context)

            self.assertFalse(report.ok)
            self.assertEqual(report.created_branches, ["release"])
            self.assertEqual(len(report.failed_branches), 1)
            self.assertIn("develop", report.failed_branches[0])

    def test_cli_sync_does_not_load_migration_plugins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_git = FakeSyncGit(["develop"], existing={})
            with (
                patch.object(bootstrap, "GitClient", return_value=fake_git),
                patch.object(bootstrap.PluginRegistry, "load_plugins", side_effect=AssertionError("plugins must not load")),
                redirect_stdout(StringIO()) as output,
            ):
                code = bootstrap.main(
                    [
                        "sync",
                        "--gitverse-url",
                        "https://gitverse.example/service.git",
                        "--bitbucket-url",
                        "https://bitbucket.example/service.git",
                        "--workspace",
                        tmp,
                    ]
                )

            self.assertEqual(code, 0)
            rendered = output.getvalue()
            self.assertIn("Sync Report", rendered)
            self.assertIn("Total branches discovered: 1", rendered)
            self.assertIn("Created branches: develop", rendered)

    def test_git_client_pushes_remote_branch_with_explicit_refs_without_force(self) -> None:
        git = RecordingGitClient()

        git.push_remote_branch(Path("/tmp/repo"), "bitbucket", "origin", "feature/a")

        self.assertEqual(git.commands[0], ["check-ref-format", "--branch", "feature/a"])
        self.assertEqual(git.commands[1], ["push", "bitbucket", "refs/remotes/origin/feature/a:refs/heads/feature/a"])
        self.assertNotIn("--force", git.commands[1])

    def test_git_client_reads_only_remote_heads(self) -> None:
        git = RecordingGitClient()

        branches = git.remote_head_branches(Path("/tmp/repo"), "origin")

        self.assertEqual(branches, ["feature/a", "main"])
        self.assertEqual(git.commands[0], ["ls-remote", "--heads", "origin"])


if __name__ == "__main__":
    unittest.main()
