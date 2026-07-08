from __future__ import annotations

from pathlib import Path


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text_if_changed(path: Path, content: str, dry_run: bool = False) -> bool:
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == content:
        return False
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return True


def copy_text_if_changed(source: Path, destination: Path, dry_run: bool = False) -> bool:
    return write_text_if_changed(destination, read_text(source), dry_run=dry_run)
