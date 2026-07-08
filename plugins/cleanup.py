from __future__ import annotations

import shutil
from pathlib import Path

from config import OperationResult
from plugin_base import MigrationContext, MigrationPlugin, PlanItem


class CleanupPlugin(MigrationPlugin):
    name = "cleanup"

    def plan(self, context: MigrationContext) -> list[PlanItem]:
        return [PlanItem(self.name, "Cleanup legacy build and deployment files")]

    def execute(self, context: MigrationContext, dry_run: bool = False) -> OperationResult:
        return cleanup_project(context.layout.root, context.standards.cleanup["targets"], dry_run=dry_run)


def cleanup_project(root: Path, targets: list[str], dry_run: bool = False) -> OperationResult:
    removed: list[str] = []
    for target in targets:
        path = root / str(target)
        if not path.exists():
            continue
        removed.append(str(target))
        if dry_run:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    if removed:
        action = "Would remove" if dry_run else "Removed"
        return OperationResult("Cleanup completed", changed=not dry_run, message=f"{action}: {', '.join(removed)}")
    return OperationResult("Cleanup completed", changed=False, message="No cleanup targets found")


def create_plugin() -> MigrationPlugin:
    return CleanupPlugin()
