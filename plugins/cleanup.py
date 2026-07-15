from __future__ import annotations

import shutil
from pathlib import Path

from config import OperationResult
from plugin_base import MigrationContext, MigrationPlugin, PlanItem


CERTIFICATE_DIRS = {"certs", "cert", "certificates", "ssl", "tls", "keys"}
CERTIFICATE_EXTENSIONS = {".jks", ".p12", ".pfx", ".pem", ".crt", ".cer", ".key", ".keystore", ".truststore"}
SAFE_CONTEXT_DIRS = {"docs", "examples", "sample"}
TEMPLATE_HINTS = {"template", "sample", "example"}
README_NAMES = {"readme", "readme.md", "readme.txt"}


class CleanupPlugin(MigrationPlugin):
    name = "cleanup"

    def plan(self, context: MigrationContext) -> list[PlanItem]:
        return [PlanItem(self.name, "Cleanup legacy build, deployment files, and local certificates")]

    def execute(self, context: MigrationContext, dry_run: bool = False) -> OperationResult:
        return cleanup_project(context.layout.root, context.standards.cleanup["targets"], dry_run=dry_run)


def cleanup_project(root: Path, targets: list[str], dry_run: bool = False) -> OperationResult:
    removed: list[str] = []
    for target in targets:
        path = root / str(target)
        if not path.exists():
            continue
        removed.append(str(target))
        if dry_run:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    removed_certificates = remove_local_certificates(root, dry_run=dry_run)
    changed = bool((removed or removed_certificates) and not dry_run)
    return OperationResult("Cleanup", changed=changed, message=render_cleanup_message(removed, removed_certificates, dry_run=dry_run))


def remove_local_certificates(root: Path, dry_run: bool = False) -> list[str]:
    candidates = certificate_cleanup_candidates(root)
    removed: list[str] = []
    for path in candidates:
        if not path.exists():
            continue
        removed.append(_relative_display(root, path))
        if dry_run:
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    return removed


def certificate_cleanup_candidates(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in sorted(root.rglob("*"), key=lambda item: (len(item.relative_to(root).parts), str(item.relative_to(root)))):
        if path == root or _is_in_safe_context(root, path):
            continue
        if any(parent in candidates for parent in path.parents):
            continue
        if path.is_dir() and path.name.lower() in CERTIFICATE_DIRS:
            candidates.append(path)
            continue
        if path.is_file() and _is_certificate_file(path):
            candidates.append(path)
    return candidates


def render_cleanup_message(removed_targets: list[str], removed_certificates: list[str], dry_run: bool = False) -> str:
    lines: list[str] = []
    if removed_targets:
        action = "would remove" if dry_run else "removed"
        lines.append(f"  {action}: {', '.join(removed_targets)}")
    else:
        lines.append("  legacy targets: none")
    if removed_certificates:
        label = "would remove certificates" if dry_run else "removed certificates"
        lines.append(f"  {label}:")
        lines.extend(f"    {path}" for path in removed_certificates)
    else:
        lines.append("  certificates: none")
    return "\n" + "\n".join(lines)


def _is_certificate_file(path: Path) -> bool:
    name = path.name.lower()
    if name in README_NAMES:
        return False
    stem = path.stem.lower()
    if any(hint in stem for hint in TEMPLATE_HINTS):
        return False
    return path.suffix.lower() in CERTIFICATE_EXTENSIONS or any(name.endswith(extension) for extension in CERTIFICATE_EXTENSIONS)


def _is_in_safe_context(root: Path, path: Path) -> bool:
    parts = {part.lower() for part in path.relative_to(root).parts[:-1]}
    return bool(parts & SAFE_CONTEXT_DIRS)


def _relative_display(root: Path, path: Path) -> str:
    relative = path.relative_to(root).as_posix()
    return f"{relative}/" if path.is_dir() else relative


def create_plugin() -> MigrationPlugin:
    return CleanupPlugin()
