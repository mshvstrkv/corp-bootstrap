from __future__ import annotations

from pathlib import Path

from config import OperationResult
from plugins.distributive import migrate_distributive, render_distributive_pom
from standard_loader import load_standards


def migrate(project_root: Path, templates_dir: Path, dry_run: bool = False) -> OperationResult:
    standards = load_standards()
    from validation import detect_application_module

    changed = migrate_distributive(
        project_root,
        Path(__file__).resolve().parents[1] / "corporate-reference",
        app_module=detect_application_module(project_root),
        template_values=standards.maven_template_values,
        dry_run=dry_run,
    )
    return OperationResult("Distributive created", changed=changed, message="corporate golden distributive rendered")
