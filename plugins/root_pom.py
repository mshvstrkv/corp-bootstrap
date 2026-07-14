from __future__ import annotations

from config import OperationResult
from moduleize import corporate_moduleize_if_needed, needs_corporate_moduleization
from maven_reference import build_values, generate_root_pom
from plugin_base import MigrationContext, MigrationPlugin, PlanItem
from utils.xml_utils import child_text, parse_xml
from validation import validate_project


class RootPomPlugin(MigrationPlugin):
    name = "root-pom"

    def validate(self, context: MigrationContext) -> list[str]:
        if needs_corporate_moduleization(context.layout.root):
            artifact_id = child_text(parse_xml(context.layout.root_pom).root, "artifactId")
            if not artifact_id:
                validate_project(context.layout)
            app_module = f"{artifact_id}-app"
            context.state["app_module"] = app_module
            context.state["moduleization.pending"] = True
            return [
                "Single-module Maven project detected",
                f"Application module will be created: {app_module}",
            ]
        app_module = validate_project(context.layout)
        context.state["app_module"] = app_module
        return ["Project structure validated", f"Application module detected: {app_module}"]

    def plan(self, context: MigrationContext) -> list[PlanItem]:
        items: list[PlanItem] = []
        if context.state.get("moduleization.pending"):
            app_module = context.state.get("app_module", "<artifactId>-app")
            items.append(PlanItem(self.name, f"Create application module {app_module} from root src/"))
        items.append(PlanItem(self.name, "Generate root pom from corporate golden reference"))
        return items

    def execute(self, context: MigrationContext, dry_run: bool = False) -> OperationResult:
        moduleized = None
        if not dry_run:
            moduleized = corporate_moduleize_if_needed(
                context.layout.root,
                context.corporate_reference_dir,
                context.standards.maven_template_values,
            )
            if moduleized:
                context.state["app_module"] = moduleized
                context.state["moduleization.completed"] = True
        app_module = validate_project(context.layout)
        context.state["app_module"] = app_module
        changed = migrate_root_pom(
            context.layout.root,
            context.corporate_reference_dir,
            context.layout.app_module,
            context.standards.maven_template_values,
            dry_run=dry_run,
        )
        message = "corporate golden root pom rendered"
        if moduleized:
            message = f"application module {moduleized} created; {message}"
        return OperationResult("Root pom migrated", changed=changed or bool(moduleized), message=message)


def migrate_root_pom(project_root, reference_dir, app_module: str, template_values: dict, dry_run: bool = False) -> bool:
    values = build_values(project_root, app_module, template_values)
    return generate_root_pom(project_root, reference_dir, values, dry_run=dry_run)


def root_pom_needs_migration(root_pom, rules: dict, app_module: str = "service-app") -> bool:
    return True


def create_plugin() -> MigrationPlugin:
    return RootPomPlugin()
