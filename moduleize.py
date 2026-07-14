from __future__ import annotations

import shutil
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from git_client import GitClient
from maven_reference import MavenTemplateValues, generate_root_pom, merge_business_dependencies, render_reference
from utils.xml_utils import child_text, clone_element, find_child, local_name, parse_xml, qualify, set_child_text
from utils.file_utils import write_text_if_changed
from validation import ValidationError


APP_SCOPED_ROOT_SECTIONS = {"dependencies", "build", "profiles"}
APP_SCOPED_COPIED_SECTIONS = {"name", "description", "dependencies", "build", "profiles"}


@dataclass(frozen=True)
class ModuleizeOptions:
    project: Path
    module_name: str | None = None
    commit: bool = False
    yes: bool = False


@dataclass(frozen=True)
class ModuleizePlan:
    project: Path
    module_name: str

    def render(self) -> str:
        return "\n".join(
            [
                "Moduleization Plan",
                "Project:",
                f"  {self.project}",
                "New application module:",
                f"  {self.module_name}",
                "Will move:",
                "  src/",
                f"  -> {self.module_name}/src/",
                "Will create:",
                f"  {self.module_name}/pom.xml",
                "Will update:",
                "  pom.xml",
                "Will NOT:",
                "  create distributive",
                "  migrate Maven to corporate standards",
                "  modify Java logging",
                "  run cleanup",
                "  push changes",
            ]
        )


@dataclass
class ModuleizeReport:
    changed: bool
    committed: bool = False
    rollback_actions: list[str] | None = None

    def render(self) -> str:
        if self.rollback_actions:
            lines = ["Moduleization failed. Rollback actions:"]
            lines.extend(f"- {action}" for action in self.rollback_actions)
            return "\n".join(lines)
        lines = ["Moduleization completed."]
        lines.append("Commit created: yes" if self.committed else "Commit created: no")
        lines.append("Pushed changes: no")
        lines.append("Recommended next step: run python3 bootstrap.py migrate ...")
        return "\n".join(lines)


def default_module_name(project: Path) -> str:
    try:
        root = parse_xml(project / "pom.xml").root
    except ET.ParseError as exc:
        raise ValidationError(f"Project validation failed. Invalid XML in pom.xml: {exc}") from exc
    except OSError as exc:
        raise ValidationError(f"Project validation failed. Unable to read root pom.xml: {exc}") from exc
    artifact_id = child_text(root, "artifactId")
    if not artifact_id:
        raise ValidationError("Project validation failed. Root artifactId is missing.")
    return f"{artifact_id}-app"


def prepare_moduleize_plan(options: ModuleizeOptions, git: GitClient) -> ModuleizePlan:
    project = options.project.resolve()
    _validate_project(project, git, options.module_name)
    module_name = options.module_name or default_module_name(project)
    _validate_module_name(project, module_name)
    return ModuleizePlan(project=project, module_name=module_name)


def render_moduleize_plan(options: ModuleizeOptions, git: GitClient) -> ModuleizePlan:
    return prepare_moduleize_plan(options, git)


def confirm_module_name(project: Path, module_name: str | None, assume_yes: bool) -> str:
    if module_name:
        return module_name
    suggested = default_module_name(project)
    if assume_yes:
        return suggested
    if not sys.stdin.isatty():
        raise RuntimeError("Moduleize requires --module-name or an interactive terminal. Re-run with --module-name or --yes.")
    answer = input(f"Application module name [{suggested}]\n").strip()
    return answer or suggested


def confirm_moduleize(plan: ModuleizePlan, assume_yes: bool) -> None:
    print(plan.render())
    if assume_yes:
        return
    if not sys.stdin.isatty():
        raise RuntimeError("Moduleize requires confirmation. Re-run with --yes after reviewing the plan.")
    answer = input("Proceed? [y/N]\n").strip().lower()
    if answer not in {"y", "yes"}:
        raise RuntimeError("Moduleize cancelled before repository modification")


def run_moduleize(options: ModuleizeOptions, git: GitClient) -> ModuleizeReport:
    plan = prepare_moduleize_plan(options, git)
    root_pom = plan.project / "pom.xml"
    root_src = plan.project / "src"
    app_dir = plan.project / plan.module_name
    app_pom = app_dir / "pom.xml"
    app_src = app_dir / "src"
    original_pom = root_pom.read_bytes()
    rollback_actions: list[str] = []
    try:
        root_tree, app_tree = convert_poms(root_pom, plan.module_name)
        app_dir.mkdir()
        _write_xml(app_tree, app_pom, overwrite=False)
        _write_xml(root_tree, root_pom, overwrite=True)
        shutil.move(str(root_src), str(app_src))
        committed = git.commit(plan.project, "Create application Maven module") if options.commit else False
        return ModuleizeReport(changed=True, committed=committed)
    except Exception:
        if root_pom.exists():
            root_pom.write_bytes(original_pom)
            rollback_actions.append("restored root pom.xml")
        if app_src.exists() and not root_src.exists():
            shutil.move(str(app_src), str(root_src))
            rollback_actions.append("restored src/ to repository root")
        if app_dir.exists():
            shutil.rmtree(app_dir)
            rollback_actions.append(f"removed partial {plan.module_name}/ module")
        raise ModuleizeRollbackError(rollback_actions)


class ModuleizeRollbackError(RuntimeError):
    def __init__(self, rollback_actions: list[str]) -> None:
        super().__init__("Moduleize failed and rollback was attempted.")
        self.rollback_actions = rollback_actions


def convert_poms(root_pom: Path, module_name: str) -> tuple[ET.ElementTree, ET.ElementTree]:
    doc = parse_xml(root_pom)
    root = doc.root
    ns = doc.namespace
    group_id = child_text(root, "groupId")
    artifact_id = child_text(root, "artifactId")
    version = child_text(root, "version")
    if not group_id or not artifact_id or not version:
        raise ValidationError("Project validation failed. Root groupId, artifactId, and version are required for moduleize.")

    app_root = ET.Element(root.tag, root.attrib)
    model_version = find_child(root, "modelVersion")
    if model_version is not None:
        app_root.append(clone_element(model_version))
    parent = ET.SubElement(app_root, qualify("parent", ns))
    ET.SubElement(parent, qualify("groupId", ns)).text = group_id
    ET.SubElement(parent, qualify("artifactId", ns)).text = artifact_id
    ET.SubElement(parent, qualify("version", ns)).text = version
    ET.SubElement(app_root, qualify("artifactId", ns)).text = module_name

    for child in list(root):
        name = local_name(child.tag)
        if name in APP_SCOPED_COPIED_SECTIONS:
            app_root.append(clone_element(child))

    for child in list(root):
        if local_name(child.tag) in APP_SCOPED_ROOT_SECTIONS:
            root.remove(child)
    set_child_text(root, "packaging", "pom", ns)
    modules = find_child(root, "modules")
    if modules is not None:
        root.remove(modules)
    modules = ET.SubElement(root, qualify("modules", ns))
    ET.SubElement(modules, qualify("module", ns)).text = module_name
    return ET.ElementTree(root), ET.ElementTree(app_root)


def _write_xml(tree: ET.ElementTree, path: Path, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    if hasattr(ET, "indent"):
        ET.indent(tree, space="    ")
    xml = ET.tostring(tree.getroot(), encoding="unicode")
    path.write_text('<?xml version="1.0" encoding="UTF-8"?>\n' + xml + "\n", encoding="utf-8")


def _validate_project(project: Path, git: GitClient, module_name: str | None) -> None:
    if not project.exists():
        raise ValidationError(f"Project validation failed. Project does not exist: {project}")
    if not project.is_dir():
        raise ValidationError(f"Project validation failed. Project must be a directory: {project}")
    if not git.is_git_repository(project):
        raise ValidationError("Project validation failed. Project must be a Git repository.")
    if not (project / "pom.xml").is_file():
        raise ValidationError("Project validation failed. Root pom.xml is missing.")
    if not (project / "src").is_dir():
        app_modules = _existing_app_modules(project)
        if app_modules:
            raise ValidationError("Application module already exists.\nNo moduleization required.")
        raise ValidationError("Project validation failed. Root src/ is missing.")
    app_modules = _existing_app_modules(project)
    if app_modules:
        raise ValidationError("Application module already exists.\nUse migrate instead of moduleize.")
    try:
        ET.parse(project / "pom.xml")
    except ET.ParseError as exc:
        raise ValidationError(f"Project validation failed. Invalid XML in pom.xml: {exc}") from exc
    if git.has_changes(project):
        raise ValidationError("Project validation failed. Working tree is not clean.")
    if module_name:
        _validate_module_name(project, module_name)


def _validate_module_name(project: Path, module_name: str) -> None:
    if not module_name.strip():
        raise ValidationError("Project validation failed. Module name must not be empty.")
    module_path = Path(module_name)
    if module_path.is_absolute() or len(module_path.parts) != 1 or module_name in {".", ".."}:
        raise ValidationError("Project validation failed. Module name must be a single directory name.")
    if (project / module_name).exists():
        raise ValidationError(f"Project validation failed. Module directory already exists: {module_name}")


def _existing_app_modules(project: Path) -> list[str]:
    return sorted(path.name for path in project.iterdir() if path.is_dir() and path.name.endswith("-app"))


def needs_corporate_moduleization(project: Path) -> bool:
    return (project / "pom.xml").is_file() and (project / "src").is_dir() and not _existing_app_modules(project)


def corporate_moduleize_if_needed(project: Path, reference_dir: Path, template_values: dict) -> str | None:
    if not needs_corporate_moduleization(project):
        return None
    return corporate_moduleize(project, reference_dir, template_values)


def corporate_moduleize(project: Path, reference_dir: Path, template_values: dict) -> str:
    root_pom = project / "pom.xml"
    root_src = project / "src"
    original_pom = root_pom.read_bytes()
    root = parse_xml(root_pom).root
    root_artifact = child_text(root, "artifactId")
    if not root_artifact:
        raise ValidationError("Project validation failed. Root artifactId is missing.")
    app_module = f"{root_artifact}-app"
    app_dir = project / app_module
    app_pom = app_dir / "pom.xml"
    app_src = app_dir / "src"
    if app_dir.exists():
        raise ValidationError(f"Project validation failed. Module directory already exists: {app_module}")

    values = MavenTemplateValues(
        {
            "ROOT_ARTIFACT_ID": root_artifact,
            "APP_MODULE": app_module,
            "APP_ARTIFACT_ID": app_module,
            "DESCRIPTION": child_text(root, "description") or root_artifact,
            **{name: str(value) for name, value in template_values.items()},
        }
    )
    try:
        app_dir.mkdir()
        app_rendered = render_reference(reference_dir / "app-pom.xml", values)
        write_text_if_changed(app_pom, merge_business_dependencies(root_pom, app_rendered))
        generate_root_pom(project, reference_dir, values)
        shutil.move(str(root_src), str(app_src))
        return app_module
    except Exception:
        if root_pom.exists():
            root_pom.write_bytes(original_pom)
        if app_src.exists() and not root_src.exists():
            shutil.move(str(app_src), str(root_src))
        if app_dir.exists():
            shutil.rmtree(app_dir)
        raise
