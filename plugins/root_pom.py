from __future__ import annotations

from config import OperationResult
from maven_reference import build_values, generate_root_pom
from plugin_base import MigrationContext, MigrationPlugin, PlanItem
from validation import validate_project


class RootPomPlugin(MigrationPlugin):
    name = "root-pom"

    def validate(self, context: MigrationContext) -> list[str]:
        app_module = validate_project(context.layout)
        context.state["app_module"] = app_module
        return ["Project structure validated", f"Application module detected: {app_module}"]

    def plan(self, context: MigrationContext) -> list[PlanItem]:
        return [PlanItem(self.name, "Generate root pom from corporate golden reference")]

    def execute(self, context: MigrationContext, dry_run: bool = False) -> OperationResult:
        changed = migrate_root_pom(
            context.layout.root,
            context.corporate_reference_dir,
            context.layout.app_module,
            context.standards.maven_template_values,
            dry_run=dry_run,
        )
        return OperationResult("Root pom migrated", changed=changed, message="corporate golden root pom rendered")


def migrate_root_pom(project_root, reference_dir, app_module: str, template_values: dict, dry_run: bool = False) -> bool:
    values = build_values(project_root, app_module, template_values)
    return generate_root_pom(project_root, reference_dir, values, dry_run=dry_run)


def root_pom_needs_migration(root_pom, rules: dict, app_module: str = "service-app") -> bool:
    return True


def create_plugin() -> MigrationPlugin:
    return RootPomPlugin()
