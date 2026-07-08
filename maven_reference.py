from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from utils.file_utils import read_text, write_text_if_changed
from utils.xml_utils import child_text, find_child, local_name, parse_xml


ALLOWED_PLACEHOLDERS = {
    "ROOT_ARTIFACT_ID",
    "APP_MODULE",
    "APP_ARTIFACT_ID",
    "DESCRIPTION",
}
PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")
BASE_IMAGE_BY_JAVA_VERSION = {
    "17": {
        "base.image.prefix": "docker-dev.${docker.registry}/ci04675739/ci04675739/",
        "base.image.name": "sberjdk-17-runtime",
        "base.image.version": "java-17.0.18_001-sberlinux-minimal-9.7.1-se",
    },
    "21": {
        "base.image.prefix": "docker-dev.${docker.registry}/ci04675739/ci04675739/",
        "base.image.name": "sberjdk-21-runtime",
        "base.image.version": "java-21.0.11_001-sberlinux-minimal-9.7.2-se",
    },
}


class MavenReferenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class MavenTemplateValues:
    values: dict[str, str]


def build_values(project_root: Path, app_module: str, config_values: dict) -> MavenTemplateValues:
    root_pom = project_root / "pom.xml"
    app_pom = project_root / app_module / "pom.xml"
    root_doc = parse_xml(root_pom)
    app_doc = parse_xml(app_pom)
    root_artifact = child_text(root_doc.root, "artifactId")
    app_artifact = child_text(app_doc.root, "artifactId")
    description = child_text(root_doc.root, "description") or child_text(app_doc.root, "description")
    values = {
        "ROOT_ARTIFACT_ID": root_artifact or "",
        "APP_MODULE": app_module,
        "APP_ARTIFACT_ID": app_artifact or "",
        "DESCRIPTION": description or "",
    }
    for name, value in config_values.items():
        if name not in ALLOWED_PLACEHOLDERS:
            raise MavenReferenceError(f"Unsupported Maven replacement mapping: {name}")
        values[name] = str(value)
    return MavenTemplateValues(values)


def render_reference(reference: Path, values: MavenTemplateValues) -> str:
    content = read_text(reference)
    unknown = sorted(set(PLACEHOLDER.findall(content)) - ALLOWED_PLACEHOLDERS)
    if unknown:
        raise MavenReferenceError("Unsupported Maven placeholder(s): " + ", ".join(unknown))

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        value = values.values.get(name, "")
        if value == "":
            raise MavenReferenceError(f"Unable to resolve Maven placeholder: {name}")
        return value

    rendered = PLACEHOLDER.sub(replace, content)
    unresolved = PLACEHOLDER.findall(rendered)
    if unresolved:
        raise MavenReferenceError("Unresolved Maven placeholder(s): " + ", ".join(sorted(set(unresolved))))
    return rendered


def generate_root_pom(project_root: Path, reference_dir: Path, values: MavenTemplateValues, dry_run: bool = False) -> bool:
    source_root_pom = project_root / "pom.xml"
    rendered = render_reference(reference_dir / "root-pom.xml", values)
    merged = merge_root_pom(source_root_pom, rendered)
    return write_text_if_changed(source_root_pom, merged, dry_run=dry_run)


def generate_app_pom(project_root: Path, reference_dir: Path, app_module: str, values: MavenTemplateValues, dry_run: bool = False) -> bool:
    source_app_pom = project_root / app_module / "pom.xml"
    rendered = render_reference(reference_dir / "app-pom.xml", values)
    merged = merge_business_dependencies(source_app_pom, rendered)
    return write_text_if_changed(source_app_pom, merged, dry_run=dry_run)


def generate_distributive(project_root: Path, reference_dir: Path, values: MavenTemplateValues, dry_run: bool = False) -> bool:
    validate_distributive_pom_reference(reference_dir / "distributive-pom.xml")
    changed = False
    changed |= write_text_if_changed(project_root / "distributive" / "pom.xml", render_reference(reference_dir / "distributive-pom.xml", values), dry_run=dry_run)
    changed |= write_text_if_changed(project_root / "distributive" / "assembly" / "distributive.xml", render_reference(reference_dir / "distributive.xml", values), dry_run=dry_run)
    return changed


def merge_root_pom(source_root_pom: Path, rendered_golden: str) -> str:
    source_root = ET.parse(source_root_pom).getroot()
    golden_root = ET.fromstring(rendered_golden)
    ns = namespace(golden_root.tag)

    source_parent = find_child(source_root, "parent")
    if source_parent is not None and child_text(source_parent, "artifactId") == "spring-boot-starter-parent":
        source_parent_version = child_text(source_parent, "version")
        golden_parent = ensure_child(golden_root, "parent", ns)
        if source_parent_version:
            set_child_text(golden_parent, "version", source_parent_version, ns)

    source_properties = find_child(source_root, "properties")
    source_java_version = child_text(source_properties, "java.version") if source_properties is not None else None
    if source_java_version:
        golden_properties = ensure_child(golden_root, "properties", ns)
        apply_java_version_properties(golden_properties, source_java_version, ns)

    source_dependency_management = find_child(source_root, "dependencyManagement")
    if source_dependency_management is not None:
        replace_child(golden_root, "dependencyManagement", copy_with_namespace(source_dependency_management, ns), ns)
    golden_dependency_management = ensure_child(golden_root, "dependencyManagement", ns)
    dependencies = ensure_child(golden_dependency_management, "dependencies", ns)
    ensure_dependency_absent_then_append(
        dependencies,
        "org.apache.commons",
        "commons-lang3",
        """<dependency>
    <groupId>org.apache.commons</groupId>
    <artifactId>commons-lang3</artifactId>
    <version>3.18.0</version>
</dependency>""",
        ns,
    )

    return serialize_xml(golden_root)


def apply_java_version_properties(properties: ET.Element, java_version: str, ns: str) -> None:
    base_image = BASE_IMAGE_BY_JAVA_VERSION.get(java_version)
    if base_image is None:
        raise MavenReferenceError(f"Unsupported Java version for corporate base image: {java_version}")
    set_child_text(properties, "java.version", java_version, ns)
    set_child_text(properties, "maven.compiler.source", java_version, ns)
    set_child_text(properties, "maven.compiler.target", java_version, ns)
    for property_name, value in base_image.items():
        set_child_text(properties, property_name, value, ns)


def merge_business_dependencies(source_app_pom: Path, rendered_golden: str) -> str:
    source_root = ET.parse(source_app_pom).getroot()
    golden_root = ET.fromstring(rendered_golden)
    ns = namespace(golden_root.tag)
    golden_deps = find_child(golden_root, "dependencies")
    if golden_deps is None:
        golden_deps = ET.SubElement(golden_root, qualify("dependencies", ns))
    corporate_deps = [copy_with_namespace(dep, ns) for dep in golden_deps if local_name(dep.tag) == "dependency"]
    golden_root.remove(golden_deps)
    merged_deps = ET.Element(qualify("dependencies", ns))
    existing_coordinates: set[tuple[str, str]] = set()

    source_deps = find_child(source_root, "dependencies")
    if source_deps is not None:
        for dep in source_deps:
            if local_name(dep.tag) != "dependency":
                continue
            coordinates = dependency_coordinates(dep)
            if coordinates in existing_coordinates:
                continue
            copied = copy_with_namespace(dep, ns)
            add_corporate_logging_exclusion(copied, ns)
            merged_deps.append(copied)
            existing_coordinates.add(coordinates)

    for dep in corporate_deps:
        group_id = child_text(dep, "groupId")
        artifact_id = child_text(dep, "artifactId")
        is_required_lombok = group_id == "org.projectlombok" and artifact_id == "lombok"
        if group_id != "ru.sber.sbe" and artifact_id != "grpc-api" and not is_required_lombok:
            continue
        coordinates = dependency_coordinates(dep)
        if coordinates in existing_coordinates:
            continue
        merged_deps.append(dep)
        existing_coordinates.add(coordinates)

    insert_after(golden_root, "dependencyManagement", merged_deps)
    return serialize_xml(golden_root)


def add_corporate_logging_exclusion(dep: ET.Element, ns: str) -> None:
    group_id = child_text(dep, "groupId")
    artifact_id = child_text(dep, "artifactId") or ""
    if group_id != "org.springframework.boot" or not artifact_id.startswith("spring-boot-starter") or artifact_id == "spring-boot-starter-logging":
        return
    exclusions = ensure_child(dep, "exclusions", ns)
    for exclusion in exclusions:
        if local_name(exclusion.tag) != "exclusion":
            continue
        if child_text(exclusion, "groupId") == "org.springframework.boot" and child_text(exclusion, "artifactId") == "spring-boot-starter-logging":
            return
    exclusion = ET.SubElement(exclusions, qualify("exclusion", ns))
    ET.SubElement(exclusion, qualify("groupId", ns)).text = "org.springframework.boot"
    ET.SubElement(exclusion, qualify("artifactId", ns)).text = "spring-boot-starter-logging"


def validate_distributive_pom_reference(reference: Path) -> None:
    try:
        document = parse_xml(reference)
    except Exception as exc:
        raise MavenReferenceError("Provided distributive POM reference is invalid or not a distributive module POM.") from exc
    artifact_id = child_text(document.root, "artifactId") or ""
    packaging = child_text(document.root, "packaging")
    artifact_is_distributive = artifact_id == "distributive" or artifact_id.startswith("CI11366566_")
    has_deploy = False
    has_assembly = False
    for node in document.root.iter():
        tag = local_name(node.tag)
        text = (node.text or "").strip()
        if tag == "id" and ("deploy-distributive" == text or "distributive" in text and "deploy" in text):
            has_deploy = True
        if tag == "artifactId" and text == "maven-assembly-plugin":
            has_assembly = True
    if not artifact_is_distributive or packaging != "pom" or not has_deploy or not has_assembly:
        raise MavenReferenceError("Provided distributive POM reference is invalid or not a distributive module POM.")


def dependency_coordinates(dep: ET.Element) -> tuple[str, str]:
    return (
        child_text(dep, "groupId") or "",
        child_text(dep, "artifactId") or "",
    )


def copy_child_text(source_root: ET.Element, target_root: ET.Element, parent_path: list[str], child_name: str) -> None:
    source_parent = source_root
    target_parent = target_root
    ns = namespace(target_root.tag)
    for name in parent_path:
        source_parent = find_child(source_parent, name)
        target_parent = ensure_child(target_parent, name, ns)
        if source_parent is None:
            return
    value = child_text(source_parent, child_name)
    if value:
        set_child_text(target_parent, child_name, value, ns)


def set_child_text(parent: ET.Element, child_name: str, value: str, ns: str) -> None:
    child = ensure_child(parent, child_name, ns)
    child.text = value


def ensure_child(parent: ET.Element, child_name: str, ns: str) -> ET.Element:
    child = find_child(parent, child_name)
    if child is not None:
        return child
    return ET.SubElement(parent, qualify(child_name, ns))


def replace_child(parent: ET.Element, child_name: str, replacement: ET.Element, ns: str) -> None:
    for index, child in enumerate(list(parent)):
        if local_name(child.tag) == child_name:
            parent.remove(child)
            parent.insert(index, replacement)
            return
    parent.append(replacement)


def insert_after(parent: ET.Element, previous_child_name: str, child_to_insert: ET.Element) -> None:
    children = list(parent)
    for index, child in enumerate(children):
        if local_name(child.tag) == previous_child_name:
            parent.insert(index + 1, child_to_insert)
            return
    parent.append(child_to_insert)


def ensure_dependency_absent_then_append(
    dependencies: ET.Element,
    group_id: str,
    artifact_id: str,
    dependency_xml: str,
    ns: str,
) -> None:
    for dependency in dependencies:
        if local_name(dependency.tag) != "dependency":
            continue
        if child_text(dependency, "groupId") == group_id and child_text(dependency, "artifactId") == artifact_id:
            return
    dependencies.append(copy_with_namespace(ET.fromstring(dependency_xml), ns))


def serialize_xml(root: ET.Element) -> str:
    tree = ET.ElementTree(root)
    ET.indent(tree, space="    ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def copy_with_namespace(element: ET.Element, ns: str) -> ET.Element:
    copied = ET.fromstring(ET.tostring(element, encoding="unicode"))
    apply_namespace(copied, ns)
    return copied


def apply_namespace(element: ET.Element, ns: str) -> None:
    if ns and not element.tag.startswith("{"):
        element.tag = qualify(element.tag, ns)
    for child in element:
        apply_namespace(child, ns)


def namespace(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""


def qualify(name: str, ns: str) -> str:
    return f"{{{ns}}}{name}" if ns else name
