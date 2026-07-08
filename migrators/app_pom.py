from __future__ import annotations

from pathlib import Path

from config import OperationResult
from plugins.app_pom import migrate_app_pom
from standard_loader import load_standards


def migrate(app_pom: Path, dry_run: bool = False) -> OperationResult:
    standards = load_standards()
    project_root = app_pom.parent.parent
    changed = migrate_app_pom(
        project_root,
        Path(__file__).resolve().parents[1] / "corporate-reference",
        app_module=app_pom.parent.name,
        template_values=standards.maven_template_values,
        dry_run=dry_run,
    )
    return OperationResult("App pom migrated", changed=changed, message="corporate golden app pom rendered with business dependencies")
