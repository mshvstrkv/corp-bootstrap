from __future__ import annotations

from pathlib import Path

from config import ProjectLayout
from standard_loader import Standards
from utils.xml_utils import child_text, find_child, parse_xml


PROPERTY_NAMES = (
    "corporate.platform.standard.version",
    "corp.platform.standard.version",
    "platform.standard.version",
)


def detect_project_standard_version(layout: ProjectLayout, standards: Standards) -> str:
    if not layout.root_pom.exists():
        return "unknown"
    try:
        root = parse_xml(layout.root_pom).root
    except Exception:
        return "unknown"
    properties = find_child(root, "properties")
    if properties is not None:
        for name in PROPERTY_NAMES:
            value = child_text(properties, name)
            if value:
                return value
    marker = layout.root / ".corp-platform-version"
    if marker.exists():
        value = marker.read_text(encoding="utf-8").strip()
        if value:
            return value
    return standards.default_project_standard_version


def write_project_standard_version(project_root: Path, version: str, dry_run: bool = False) -> bool:
    marker = project_root / ".corp-platform-version"
    content = f"{version}\n"
    if marker.exists() and marker.read_text(encoding="utf-8") == content:
        return False
    if not dry_run:
        marker.write_text(content, encoding="utf-8")
    return True
