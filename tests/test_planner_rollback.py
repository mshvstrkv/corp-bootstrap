from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

from config import AppConfig
from git_client import GitClient
from planner import MigrationExecutionError, execute_plugins
from plugin_base import MigrationContext, MigrationPlugin, PlanItem
from standard_loader import load_standards


class RecordingPlugin(MigrationPlugin):
    def __init__(self, name: str, events: list[str], fail: bool = False) -> None:
        self.name = name
        self.events = events
        self.fail = fail

    def plan(self, context: MigrationContext) -> list[PlanItem]:
        return [PlanItem(self.name, self.name)]

    def execute(self, context: MigrationContext, dry_run: bool = False):
        self.events.append(f"execute:{self.name}")
        if self.fail:
            raise RuntimeError(f"{self.name} failed")
        from config import OperationResult

        return OperationResult(self.name)

    def rollback(self, context: MigrationContext):
        self.events.append(f"rollback:{self.name}")
        from config import OperationResult

        return OperationResult(f"{self.name} rollback")


class PlannerRollbackTest(unittest.TestCase):
    def test_rolls_back_failed_and_completed_plugins_in_reverse_order(self) -> None:
        events: list[str] = []
        with tempfile.TemporaryDirectory() as tmp:
            context = MigrationContext(
                config=AppConfig("https://gitverse.example/service.git", "https://bitbucket.example/service.git"),
                standards=load_standards(),
                skill_root=Path.cwd(),
                git=GitClient(logging.getLogger("test.git")),
                logger=logging.getLogger("test"),
                repo=Path(tmp),
            )
            plugins = [
                RecordingPlugin("first", events),
                RecordingPlugin("second", events, fail=True),
            ]

            with self.assertRaises(MigrationExecutionError) as raised:
                execute_plugins(plugins, context)

            self.assertEqual(events, ["execute:first", "execute:second", "rollback:second", "rollback:first"])
            self.assertEqual(len(raised.exception.rollback_results), 2)


if __name__ == "__main__":
    unittest.main()
