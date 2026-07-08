from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path


ET.register_namespace("", "http://maven.apache.org/POM/4.0.0")


@dataclass
class XmlDocument:
    path: Path
    tree: ET.ElementTree
    root: ET.Element
    namespace: str

    @property
    def tag(self) -> str:
        return f"{{{self.namespace}}}" if self.namespace else ""

    def write_if_changed(self, dry_run: bool = False) -> bool:
        before = self.path.read_text(encoding="utf-8") if self.path.exists() else ""
        if hasattr(ET, "indent"):
            ET.indent(self.tree, space="    ")
        xml_bytes = ET.tostring(self.root, encoding="unicode")
        normalized = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes + "\n"
        if before == normalized:
            return False
        if not dry_run:
            self.path.write_text(normalized, encoding="utf-8")
        return True


def parse_xml(path: Path) -> XmlDocument:
    tree = ET.parse(path)
    root = tree.getroot()
    return XmlDocument(path=path, tree=tree, root=root, namespace=namespace(root.tag))


def namespace(tag: str) -> str:
    if tag.startswith("{") and "}" in tag:
        return tag[1:].split("}", 1)[0]
    return ""


def local_name(tag: str) -> str:
    return tag.split("}", 1)[1] if tag.startswith("{") and "}" in tag else tag


def child(parent: ET.Element, name: str, ns: str = "") -> ET.Element:
    found = find_child(parent, name)
    if found is not None:
        return found
    created = ET.SubElement(parent, qualify(name, ns))
    return created


def find_child(parent: ET.Element, name: str) -> ET.Element | None:
    for item in parent:
        if local_name(item.tag) == name:
            return item
    return None


def child_text(parent: ET.Element, name: str) -> str | None:
    found = find_child(parent, name)
    if found is None or found.text is None:
        return None
    return found.text.strip()


def set_child_text(parent: ET.Element, name: str, value: str, ns: str = "") -> bool:
    target = child(parent, name, ns)
    if (target.text or "").strip() == value:
        return False
    target.text = value
    return True


def qualify(name: str, ns: str = "") -> str:
    return f"{{{ns}}}{name}" if ns else name


def dependency_exists(parent: ET.Element, group_id: str, artifact_id: str) -> bool:
    for dep in parent.iter():
        if local_name(dep.tag) == "dependency" and child_text(dep, "groupId") == group_id and child_text(dep, "artifactId") == artifact_id:
            return True
    return False


def append_dependency(dependencies: ET.Element, group_id: str, artifact_id: str, ns: str, version: str | None = None, scope: str | None = None, optional: str | None = None) -> ET.Element:
    dep = ET.SubElement(dependencies, qualify("dependency", ns))
    ET.SubElement(dep, qualify("groupId", ns)).text = group_id
    ET.SubElement(dep, qualify("artifactId", ns)).text = artifact_id
    if version:
        ET.SubElement(dep, qualify("version", ns)).text = version
    if scope:
        ET.SubElement(dep, qualify("scope", ns)).text = scope
    if optional:
        ET.SubElement(dep, qualify("optional", ns)).text = optional
    return dep


def clone_element(element: ET.Element) -> ET.Element:
    return copy.deepcopy(element)
