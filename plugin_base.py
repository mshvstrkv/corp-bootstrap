from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from config import AppConfig, OperationResult, ProjectLayout
from git_client import GitClient
from standard_loader import Standards


@dataclass(frozen=True)
class PlanItem:
    plugin: str
    description: str
    destructive: bool = False


@dataclass
class MigrationContext:
    config: AppConfig
    standards: Standards
    skill_root: Path
    git: GitClient
    logger: logging.Logger
    repo: Path | None = None
    selected_branch: str | None = None
    corporate_branch: str | None = None
    state: dict[str, Any] = field(default_factory=dict)

    @property
    def layout(self) -> ProjectLayout:
        if self.repo is None:
            raise RuntimeError("Repository is not available in migration context")
        return ProjectLayout(self.repo, app_module=str(self.state.get("app_module", self.standards.app_module)))

    @property
    def templates_dir(self) -> Path:
        return self.skill_root / "templates"

    @property
    def corporate_reference_dir(self) -> Path:
        return self.skill_root / "corporate-reference"


class MigrationPlugin(ABC):
    name: str = "plugin"

    def validate(self, context: MigrationContext) -> list[str]:
        return []

    @abstractmethod
    def plan(self, context: MigrationContext) -> list[PlanItem]:
        raise NotImplementedError

    @abstractmethod
    def execute(self, context: MigrationContext, dry_run: bool = False) -> OperationResult:
        raise NotImplementedError

    def rollback(self, context: MigrationContext) -> OperationResult:
        return OperationResult(f"{self.name} rollback", changed=False, message="No rollback action available")
