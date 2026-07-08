from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class StandardsError(RuntimeError):
    pass


@dataclass(frozen=True)
class Standards:
    root: Path
    platform: dict[str, Any]
    plugins: dict[str, Any]
    dependencies: dict[str, Any]
    annotation_processors: dict[str, Any]
    maven_plugins: dict[str, Any]
    maven_template_values: dict[str, Any]
    cleanup: dict[str, Any]
    migration_rules: dict[str, Any]

    @property
    def app_module(self) -> str:
        return str(self.platform["app_module"])

    @property
    def latest_standard_version(self) -> str:
        return str(self.platform["latest_standard_version"])

    @property
    def default_project_standard_version(self) -> str:
        return str(self.platform["default_project_standard_version"])

    @property
    def corporate_branch_suffix(self) -> str:
        return str(self.platform["corporate_branch_suffix"])

    @property
    def commit_message(self) -> str:
        return str(self.platform["commit_message"])


def load_standards(root: Path | None = None) -> Standards:
    base = root or Path(__file__).resolve().parent / "standards"
    standards = Standards(
        root=base,
        platform=_load(base / "platform.yaml"),
        plugins=_load(base / "plugins.yaml"),
        dependencies=_load(base / "dependencies.yaml"),
        annotation_processors=_load(base / "annotation-processors.yaml"),
        maven_plugins=_load(base / "maven-plugins.yaml"),
        maven_template_values=_load(base / "maven-reference-mapping.yaml"),
        cleanup=_load(base / "cleanup.yaml"),
        migration_rules=_load(base / "migration-rules.yaml"),
    )
    _validate_standards(standards)
    return standards


def _load(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise StandardsError(f"Missing standards file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise StandardsError(f"Invalid standards file {path.name}: {exc}") from exc
    if not isinstance(data, dict):
        raise StandardsError(f"Standards file must contain an object: {path.name}")
    return data


def _validate_standards(standards: Standards) -> None:
    _require(standards.platform, "platform.yaml", ["standard_name", "latest_standard_version", "default_project_standard_version", "app_module", "corporate_branch_suffix", "commit_message"])
    _require(standards.plugins, "plugins.yaml", ["plugins"])
    _require(standards.dependencies, "dependencies.yaml", ["dependencies", "exclusions"])
    _require(standards.annotation_processors, "annotation-processors.yaml", ["annotation_processors"])
    _require(standards.maven_plugins, "maven-plugins.yaml", ["compiler_plugin", "deploy_image_profile"])
    _require(standards.cleanup, "cleanup.yaml", ["targets"])
    _require(standards.migration_rules, "migration-rules.yaml", ["root_pom", "distributive", "logger", "out_of_scope"])
    _require(standards.migration_rules["root_pom"], "migration-rules.yaml:root_pom", ["packaging", "required_modules"])
    _require(standards.migration_rules["distributive"], "migration-rules.yaml:distributive", ["module_dir", "pom_template", "assembly_template", "assembly_path", "ci_artifact_prefix", "nexus_url_property"])
    _require(standards.migration_rules["logger"], "migration-rules.yaml:logger", ["field_name", "logger_type", "logger_factory_method", "logger_imports", "annotation_import", "annotation"])


def _require(data: dict[str, Any], source: str, keys: list[str]) -> None:
    missing = [key for key in keys if key not in data]
    if missing:
        raise StandardsError(f"{source} is missing required key(s): {', '.join(missing)}")
