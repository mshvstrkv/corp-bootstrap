from __future__ import annotations

from pathlib import Path

from config import OperationResult
from maven_reference import build_values, generate_distributive, render_reference, validate_distributive_pom_reference
from plugin_base import MigrationContext, MigrationPlugin, PlanItem


class DistributivePlugin(MigrationPlugin):
    name = "distributive"

    def plan(self, context: MigrationContext) -> list[PlanItem]:
        return [PlanItem(self.name, "Generate distributive from corporate golden references")]

    def execute(self, context: MigrationContext, dry_run: bool = False) -> OperationResult:
        changed = migrate_distributive(
            context.layout.root,
            context.corporate_reference_dir,
            app_module=context.layout.app_module,
            template_values=context.standards.maven_template_values,
            dry_run=dry_run,
        )
        return OperationResult("Distributive created", changed=changed, message="corporate golden distributive rendered")


def migrate_distributive(project_root: Path, reference_dir: Path, app_module: str, template_values: dict, dry_run: bool = False) -> bool:
    values = build_values(project_root, app_module, template_values)
    return generate_distributive(project_root, reference_dir, values, dry_run=dry_run)


def render_distributive_pom(root_pom: Path, template: Path) -> str:
    from validation import detect_application_module

    project_root = root_pom.parent
    values = build_values(project_root, detect_application_module(project_root), {})
    return render_reference(template, values)


def validate_distributive_pom_template(template: Path) -> None:
    validate_distributive_pom_reference(template)


def create_plugin() -> MigrationPlugin:
    return DistributivePlugin()
