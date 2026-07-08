from __future__ import annotations

from config import OperationResult
from platform_version import write_project_standard_version
from plugin_base import MigrationContext, MigrationPlugin, PlanItem


class FinalizePlugin(MigrationPlugin):
    name = "finalize"

    def plan(self, context: MigrationContext) -> list[PlanItem]:
        branch = context.corporate_branch or "<branch>-corp"
        return [
            PlanItem(self.name, "Create Corporate migration commit"),
            PlanItem(self.name, f"Push completed migration to {branch}"),
        ]

    def execute(self, context: MigrationContext, dry_run: bool = False) -> OperationResult:
        if context.repo is None or context.corporate_branch is None:
            raise RuntimeError("Finalize plugin requires a prepared repository and corporate branch")
        if dry_run:
            return OperationResult("Finalize planned", changed=False, message=f"Would commit and push {context.corporate_branch}")
        write_project_standard_version(context.repo, context.standards.latest_standard_version)
        committed = context.git.commit(context.repo, context.standards.commit_message)
        context.git.push_branch(context.repo, "bitbucket", context.corporate_branch)
        if committed:
            return OperationResult("Push completed", changed=True, message="Commit created and corporate branch pushed")
        return OperationResult("Push completed", changed=False, message="Commit skipped: no changes; corporate branch pushed")


def create_plugin() -> MigrationPlugin:
    return FinalizePlugin()
