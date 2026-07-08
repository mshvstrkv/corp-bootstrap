from __future__ import annotations

from pathlib import Path

from config import OperationResult
from plugins.logger import migrate_loggers, migrate_source as migrate_source_with_rules
from standard_loader import load_standards


def migrate(root: Path, dry_run: bool = False) -> OperationResult:
    standards = load_standards()
    return migrate_loggers(root, standards.migration_rules["logger"], dry_run=dry_run)


def migrate_source(source: str) -> str:
    standards = load_standards()
    return migrate_source_with_rules(source, standards.migration_rules["logger"])
