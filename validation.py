from __future__ import annotations

import xml.etree.ElementTree as ET

from config import AnalysisResult, ProjectLayout
from platform_version import detect_project_standard_version
from standard_loader import Standards, load_standards
from utils.xml_utils import child_text, find_child, local_name, parse_xml


class ValidationError(RuntimeError):
    pass


def validate_project(layout: ProjectLayout) -> str:
    if not layout.root_pom.exists():
        raise ValidationError("Project validation failed. Expected root pom.xml is missing.")
    if not layout.root_pom.is_file():
        raise ValidationError("Project validation failed. Root pom.xml must be a file.")
    try:
        ET.parse(layout.root_pom)
    except ET.ParseError as exc:
        raise ValidationError(f"Project validation failed. Invalid XML in pom.xml: {exc}") from exc

    app_module = detect_application_module(layout.root)
    app_layout = ProjectLayout(layout.root, app_module=app_module)
    missing: list[str] = []
    for path in (app_layout.app_pom, app_layout.app_src):
        if not path.exists():
            missing.append(str(path.relative_to(app_layout.root)))
    if missing:
        raise ValidationError(
            "Project validation failed. Expected Spring Boot layout is missing: "
            + ", ".join(missing)
        )
    if not app_layout.app_pom.is_file() or not app_layout.app_src.is_dir():
        raise ValidationError(f"Project validation failed. {app_module}/pom.xml and {app_module}/src must have correct types.")
    for pom in (app_layout.app_pom,):
        try:
            ET.parse(pom)
        except ET.ParseError as exc:
            raise ValidationError(f"Project validation failed. Invalid XML in {pom.name}: {exc}") from exc
    return app_module


def detect_application_module(project_root) -> str:
    candidates = sorted(
        path.name
        for path in project_root.iterdir()
        if path.is_dir()
        and path.name.endswith("-app")
    )
    if not candidates:
        raise ValidationError(
            "Application module was not found.\n"
            "The repository must already be converted to the modular project structure.\n"
            "Migration aborted.\n"
            "Please create the application module before running this Skill."
        )
    if len(candidates) > 1:
        raise ValidationError(
            "Multiple application modules were found: "
            + ", ".join(candidates)
            + ".\nMigration aborted.\nPlease keep exactly one *-app module before running this Skill."
        )
    return candidates[0]


def analyze_project(layout: ProjectLayout, standards: Standards | None = None) -> AnalysisResult:
    standards = standards or load_standards()
    warnings: list[str] = []
    validation_ok = True
    detected_module: str | None = None
    effective_layout = layout
    blocked_reason: str | None = None
    try:
        detected_module = validate_project(layout)
        effective_layout = ProjectLayout(layout.root, app_module=detected_module)
    except ValidationError as exc:
        validation_ok = False
        message = str(exc)
        warnings.append(message)
        if "Application module was not found" in message:
            blocked_reason = "Application module missing"
        elif "Multiple application modules" in message:
            blocked_reason = "Multiple application modules found"
        else:
            blocked_reason = "Project validation failed"

    root_needs = True
    app_needs = True
    logger_missing = True
    missing_dependencies: list[str] = []
    if effective_layout.root_pom.exists():
        try:
            root = parse_xml(effective_layout.root_pom).root
            root_rules = standards.migration_rules["root_pom"]
            root_needs = child_text(root, "packaging") != str(root_rules["packaging"]) or any(
                not _module_exists(root, str(module)) for module in root_rules["required_modules"]
            )
        except (ET.ParseError, OSError) as exc:
            warnings.append(f"Unable to analyze root pom: {exc}")
    if effective_layout.app_pom.exists():
        try:
            root = parse_xml(effective_layout.app_pom).root
            app_needs, missing_dependencies = _app_pom_needs_migration(root, standards)
        except (ET.ParseError, OSError) as exc:
            warnings.append(f"Unable to analyze app pom: {exc}")

    if effective_layout.app_src.exists():
        annotation_import = str(standards.migration_rules["logger"]["annotation_import"])
        seen_java = False
        logger_missing = True
        for path in effective_layout.app_src.rglob("*.java"):
            seen_java = True
            if annotation_import in path.read_text(encoding="utf-8"):
                logger_missing = False
                break
        if not seen_java:
            logger_missing = True

    cleanup_items = [str(item) for item in standards.cleanup["targets"] if (effective_layout.root / str(item)).exists()]
    distributive_dir = effective_layout.root / str(standards.migration_rules["distributive"]["module_dir"])
    issues = sum(
        [
            root_needs,
            app_needs,
            logger_missing,
            not distributive_dir.exists(),
            bool(cleanup_items),
            bool(missing_dependencies),
        ]
    )
    return AnalysisResult(
        validation_ok=validation_ok,
        root_pom_needs_migration=root_needs,
        app_pom_needs_migration=app_needs,
        corporate_logger_missing=logger_missing,
        distributive_missing=not distributive_dir.exists(),
        cleanup_items=cleanup_items,
        project_standard_version=detect_project_standard_version(effective_layout, standards),
        latest_standard_version=standards.latest_standard_version,
        migration_complexity=_complexity(issues),
        corporate_dependencies_missing=missing_dependencies,
        detected_application_module=detected_module,
        migration_blocked_reason=blocked_reason,
        warnings=warnings,
    )


def _module_exists(root: ET.Element, value: str) -> bool:
    modules = find_child(root, "modules")
    if modules is None:
        return False
    return any(local_name(child.tag) == "module" and (child.text or "").strip() == value for child in modules)


def _app_pom_needs_migration(root: ET.Element, standards: Standards) -> tuple[bool, list[str]]:
    required = {
        (str(dep["group_id"]), str(dep["artifact_id"]))
        for dep in standards.dependencies["dependencies"]
    }
    found: set[tuple[str, str]] = set()
    for dep in root.iter():
        if local_name(dep.tag) != "dependency":
            continue
        group = child_text(dep, "groupId")
        artifact = child_text(dep, "artifactId")
        if group and artifact:
            found.add((group, artifact))
    missing = sorted(f"{group}:{artifact}" for group, artifact in required - found)
    deploy_profile = False
    profile_id = str(standards.maven_plugins["deploy_image_profile"]["id"])
    profiles = find_child(root, "profiles")
    if profiles is not None:
        for profile in profiles:
            if local_name(profile.tag) == "profile" and child_text(profile, "id") == profile_id:
                deploy_profile = True
                break
    return bool(missing) or not deploy_profile, missing


def _complexity(issue_count: int) -> str:
    if issue_count <= 2:
        return "Low"
    if issue_count <= 4:
        return "Medium"
    return "High"
