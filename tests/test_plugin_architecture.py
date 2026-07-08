from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from config import AppConfig, Mode
from git_client import GitClient
from planner import build_plan
from plugin_base import MigrationContext
from plugin_registry import PluginRegistry
from standard_loader import load_standards


class PluginArchitectureTest(unittest.TestCase):
    def test_loads_enabled_plugins_from_standards(self) -> None:
        standards = load_standards()
        plugins = PluginRegistry(standards).load_plugins()
        names = [plugin.name for plugin in plugins]

        self.assertEqual(names, ["git", "root-pom", "app-pom", "distributive", "cleanup", "logger", "finalize"])

    def test_builds_plan_without_bootstrap_migration_logic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            standards = load_standards()
            context = MigrationContext(
                config=AppConfig(
                    gitverse_url="https://gitverse.example/service.git",
                    bitbucket_url="https://bitbucket.example/service.git",
                    branch="develop",
                    workspace=Path(tmp),
                    mode=Mode.MIGRATE,
                ),
                standards=standards,
                skill_root=Path.cwd(),
                git=GitClient(logging.getLogger("test.git")),
                logger=logging.getLogger("test"),
                repo=Path(tmp) / "service",
                selected_branch="develop",
                corporate_branch="develop-corp",
            )
            plugins = [plugin for plugin in PluginRegistry(standards).load_plugins() if plugin.name != "git"]
            plan = build_plan(plugins, context)
            rendered = plan.render()

            self.assertIn("Generate root pom from corporate golden reference", rendered)
            self.assertIn("Generate app pom from corporate golden reference", rendered)
            self.assertIn("Push completed migration to develop-corp", rendered)


if __name__ == "__main__":
    unittest.main()
