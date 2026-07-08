from __future__ import annotations

import re
from pathlib import Path

from config import OperationResult
from plugin_base import MigrationContext, MigrationPlugin, PlanItem


class LoggerPlugin(MigrationPlugin):
    name = "logger"

    def plan(self, context: MigrationContext) -> list[PlanItem]:
        return [PlanItem(self.name, "Java logger migration")]

    def execute(self, context: MigrationContext, dry_run: bool = False) -> OperationResult:
        return migrate_loggers(context.layout.app_src, context.standards.migration_rules["logger"], dry_run=dry_run)


def migrate_loggers(root: Path, rules: dict, dry_run: bool = False) -> OperationResult:
    changed_files: list[str] = []
    for path in root.rglob("*.java"):
        original = path.read_text(encoding="utf-8")
        migrated = migrate_source(original, rules)
        if migrated == original:
            continue
        changed_files.append(str(path.relative_to(root)))
        if not dry_run:
            path.write_text(migrated, encoding="utf-8")
    message = "No logger fields found" if not changed_files else "Migrated: " + ", ".join(changed_files)
    return OperationResult("Java logger migrated", changed=bool(changed_files), message=message)


def migrate_source(source: str, rules: dict) -> str:
    field_name = str(rules["field_name"])
    logger_type = str(rules["logger_type"])
    factory_method = str(rules["logger_factory_method"])
    annotation = str(rules["annotation"])
    annotation_import = str(rules["annotation_import"])
    if f"{factory_method}(" not in source or f"private static final {logger_type} {field_name}" not in source:
        return source

    updated = source
    for import_name in rules["logger_imports"]:
        updated = re.sub(rf"(?m)^[ \t]*import\s+{re.escape(str(import_name))};\s*\n", "", updated)
    field_pattern = re.compile(
        rf"(?m)^[ \t]*private\s+static\s+final\s+{re.escape(logger_type)}\s+{re.escape(field_name)}\s*=\s*{re.escape(factory_method)}\([^;]+;\s*\n?"
    )
    updated, count = field_pattern.subn("", updated)
    if count == 0:
        return source
    updated = _ensure_import(updated, annotation_import)
    updated = _ensure_annotation(updated, annotation)
    return updated


def _ensure_import(source: str, import_name: str) -> str:
    import_line = f"import {import_name};"
    if import_line in source:
        return source
    lines = source.splitlines(keepends=True)
    import_indexes = [index for index, line in enumerate(lines) if line.startswith("import ")]
    if import_indexes:
        first = import_indexes[0]
        last = import_indexes[-1]
        import_lines = [line.rstrip("\n") for line in lines[first : last + 1] if line.startswith("import ")]
        normal_imports = sorted({line for line in import_lines if not line.startswith("import static ")} | {import_line})
        static_imports = sorted({line for line in import_lines if line.startswith("import static ")})
        replacement = [line + "\n" for line in normal_imports]
        if static_imports:
            replacement.append("\n")
            replacement.extend(line + "\n" for line in static_imports)
        lines[first : last + 1] = replacement
        return "".join(lines)

    package_match = re.search(r"(?m)^package\s+[\w.]+;\s*$", source)
    if package_match:
        insert_at = package_match.end()
        return source[:insert_at] + "\n\n" + import_line + "\n" + source[insert_at:]
    return import_line + "\n\n" + source


def _ensure_annotation(source: str, annotation: str) -> str:
    if re.search(rf"(?m)^[ \t]*@{re.escape(annotation)}\b", source):
        return source
    pattern = re.compile(r"(?m)^((?:@[A-Za-z0-9_.$]+(?:\([^)]*\))?\s*\n)*)\s*(public\s+|final\s+|abstract\s+|class\s+|interface\s+|enum\s+)")
    match = pattern.search(source)
    if not match:
        return source
    insert_at = match.start(2)
    return source[:insert_at] + f"@{annotation}\n" + source[insert_at:]


def create_plugin() -> MigrationPlugin:
    return LoggerPlugin()
