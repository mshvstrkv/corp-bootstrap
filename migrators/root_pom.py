from __future__ import annotations

from pathlib import Path

from config import OperationResult
from plugins.root_pom import migrate_root_pom, root_pom_needs_migration
from standard_loader import load_standards


def migrate(root_pom: Path, dry_run: bool = False) -> OperationResult:
    standards = load_standards()
    from validation import detect_application_module

    changed = migrate_root_pom(
        root_pom.parent,
        Path(__file__).resolve().parents[1] / "corporate-reference",
        app_module=detect_application_module(root_pom.parent),
        template_values=standards.maven_template_values,
        dry_run=dry_run,
    )
    return OperationResult("Root pom migrated", changed=changed, message="corporate golden root pom rendered")


def needs_migration(root_pom: Path) -> bool:
    standards = load_standards()
    return root_pom_needs_migration(root_pom, standards.migration_rules["root_pom"])
