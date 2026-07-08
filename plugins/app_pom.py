from __future__ import annotations

from pathlib import Path

from config import OperationResult
from maven_reference import build_values, generate_app_pom
from plugin_base import MigrationContext, MigrationPlugin, PlanItem
from utils.xml_utils import child_text, find_child, local_name, parse_xml


class AppPomPlugin(MigrationPlugin):
    name = "app-pom"

    def plan(self, context: MigrationContext) -> list[PlanItem]:
        return [PlanItem(self.name, "Generate app pom from corporate golden reference and merge business dependencies")]

    def execute(self, context: MigrationContext, dry_run: bool = False) -> OperationResult:
        changed = migrate_app_pom(
            context.layout.root,
            context.corporate_reference_dir,
            context.layout.app_module,
            context.standards.maven_template_values,
            dry_run=dry_run,
        )
        return OperationResult("App pom migrated", changed=changed, message="corporate golden app pom rendered with business dependencies")


def migrate_app_pom(project_root: Path, reference_dir: Path, app_module: str, template_values: dict, dry_run: bool = False) -> bool:
    values = build_values(project_root, app_module, template_values)
    return generate_app_pom(project_root, reference_dir, app_module, values, dry_run=dry_run)


def app_pom_needs_migration(app_pom: Path, dependencies: dict, maven_plugins: dict) -> bool:
    root = parse_xml(app_pom).root
    required = {(str(dep["group_id"]), str(dep["artifact_id"])) for dep in dependencies["dependencies"]}
    found: set[tuple[str, str]] = set()
    for dep in root.iter():
        if local_name(dep.tag) != "dependency":
            continue
        group = child_text(dep, "groupId")
        artifact = child_text(dep, "artifactId")
        if group and artifact:
            found.add((group, artifact))
    deploy_profile = False
    profile_id = str(maven_plugins["deploy_image_profile"]["id"])
    profiles = find_child(root, "profiles")
    if profiles is not None:
        for profile in profiles:
            if local_name(profile.tag) == "profile" and child_text(profile, "id") == profile_id:
                deploy_profile = True
                break
    return not required.issubset(found) or not deploy_profile


def create_plugin() -> MigrationPlugin:
    return AppPomPlugin()
