from __future__ import annotations

import logging
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from config import AppConfig, Mode
from plugin_base import MigrationContext
from plugins.git import GitPlugin
from standard_loader import load_standards


class FakeGit:
    def __init__(self, branches: list[str]) -> None:
        self.branches = branches
        self.pushed_remote_branches: list[tuple[str, str]] = []
        self.created_branches: list[str] = []
        self.pushed_local_branches: list[str] = []

    def clone(self, url: str, destination: Path) -> None:
        destination.mkdir(parents=True)

    def remote_branches(self, repo: Path) -> list[str]:
        return self.branches

    def add_or_set_remote(self, repo: Path, name: str, url: str) -> None:
        pass

    def push_remote_branch(self, repo: Path, remote: str, source_remote: str, branch: str) -> None:
        self.pushed_remote_branches.append((source_remote, branch))

    def checkout(self, repo: Path, branch: str) -> None:
        pass

    def create_branch(self, repo: Path, branch: str) -> None:
        self.created_branches.append(branch)

    def push_branch(self, repo: Path, remote: str, local_branch: str, remote_branch: str | None = None) -> None:
        self.pushed_local_branches.append(remote_branch or local_branch)


class GitWorkflowTest(unittest.TestCase):
    def test_migrate_synchronizes_all_remote_branches_before_corporate_branch(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_git = FakeGit(["develop", "release", "feature/a", "feature/b", "bugfix/x"])
            context = MigrationContext(
                config=AppConfig(
                    "https://gitverse.example/service.git",
                    "https://bitbucket.example/service.git",
                    branch="develop",
                    corporate_branch_name="develop-company",
                    workspace=Path(tmp),
                    mode=Mode.MIGRATE,
                ),
                standards=load_standards(),
                skill_root=Path.cwd(),
                git=fake_git,
                logger=logging.getLogger("test"),
            )

            with redirect_stdout(StringIO()):
                GitPlugin().validate(context)
                GitPlugin().execute(context)

            self.assertEqual(
                fake_git.pushed_remote_branches,
                [("origin", "develop"), ("origin", "release"), ("origin", "feature/a"), ("origin", "feature/b"), ("origin", "bugfix/x")],
            )
            self.assertEqual(context.selected_branch, "develop")
            self.assertEqual(context.corporate_branch, "develop-company")
            self.assertEqual(fake_git.created_branches, ["develop-company"])
            self.assertEqual(fake_git.pushed_local_branches, ["develop-company"])

    def test_prompts_for_primary_and_corporate_branch_when_not_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fake_git = FakeGit(["develop", "main"])
            context = MigrationContext(
                config=AppConfig(
                    "https://gitverse.example/service.git",
                    "https://bitbucket.example/service.git",
                    workspace=Path(tmp),
                    mode=Mode.DRY_RUN,
                ),
                standards=load_standards(),
                skill_root=Path.cwd(),
                git=fake_git,
                logger=logging.getLogger("test"),
            )

            with patch("builtins.input", side_effect=["2", "main-corp-custom"]), redirect_stdout(StringIO()):
                GitPlugin().validate(context)

            self.assertEqual(context.selected_branch, "main")
            self.assertEqual(context.corporate_branch, "main-corp-custom")


if __name__ == "__main__":
    unittest.main()
