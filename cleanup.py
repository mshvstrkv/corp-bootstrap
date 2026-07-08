from __future__ import annotations

from pathlib import Path

from config import OperationResult
from plugins.cleanup import cleanup_project as cleanup_with_targets
from standard_loader import load_standards


def cleanup_project(root: Path, dry_run: bool = False) -> OperationResult:
    standards = load_standards()
    return cleanup_with_targets(root, standards.cleanup["targets"], dry_run=dry_run)
