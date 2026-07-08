from __future__ import annotations

from dataclasses import dataclass, field

from config import OperationResult
from plugin_base import MigrationContext, MigrationPlugin, PlanItem


class MigrationExecutionError(RuntimeError):
    def __init__(self, message: str, rollback_results: list[OperationResult]) -> None:
        super().__init__(message)
        self.rollback_results = rollback_results


@dataclass
class ExecutionPlan:
    items: list[PlanItem] = field(default_factory=list)

    def render(self, title: str = "Migration Plan") -> str:
        lines = [title]
        lines.extend(f"OK {item.description}" for item in self.items)
        return "\n".join(lines)


def build_plan(plugins: list[MigrationPlugin], context: MigrationContext) -> ExecutionPlan:
    items: list[PlanItem] = []
    for plugin in plugins:
        items.extend(plugin.plan(context))
    return ExecutionPlan(items)


def execute_plugins(plugins: list[MigrationPlugin], context: MigrationContext, dry_run: bool = False) -> list[OperationResult]:
    executed: list[MigrationPlugin] = []
    results: list[OperationResult] = []
    try:
        for plugin in plugins:
            executed.append(plugin)
            result = plugin.execute(context, dry_run=dry_run)
            results.append(result)
        return results
    except Exception as exc:
        rollback_results: list[OperationResult] = []
        for plugin in reversed(executed):
            try:
                rollback_results.append(plugin.rollback(context))
            except Exception as rollback_error:
                rollback_results.append(OperationResult(f"{plugin.name} rollback", changed=False, message=f"Rollback failed: {rollback_error}"))
        raise MigrationExecutionError(str(exc), rollback_results) from exc
