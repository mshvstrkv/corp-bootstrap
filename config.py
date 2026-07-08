from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence


class Mode(str, Enum):
    ANALYZE = "analyze"
    DRY_RUN = "dry-run"
    MIGRATE = "migrate"
    SYNC = "sync"
    APPLY = "apply"
    UPDATE = "update"


@dataclass(frozen=True)
class AppConfig:
    gitverse_url: str
    bitbucket_url: str
    branch: str | None = None
    corporate_branch_name: str | None = None
    corporate_suffix: str = "-corp"
    workspace: Path = Path.cwd()
    mode: Mode = Mode.MIGRATE
    workspace_explicit: bool = False

    @property
    def corporate_branch(self) -> str:
        if self.corporate_branch_name:
            return self.corporate_branch_name
        if not self.branch:
            raise ValueError("Corporate branch requires a selected source branch")
        return f"{self.branch}{self.corporate_suffix}"


@dataclass(frozen=True)
class ProjectLayout:
    root: Path
    app_module: str = "service-app"

    @property
    def root_pom(self) -> Path:
        return self.root / "pom.xml"

    @property
    def app_dir(self) -> Path:
        return self.root / self.app_module

    @property
    def app_pom(self) -> Path:
        return self.app_dir / "pom.xml"

    @property
    def app_src(self) -> Path:
        return self.app_dir / "src"

    @property
    def distributive_dir(self) -> Path:
        return self.root / "distributive"


@dataclass
class OperationResult:
    name: str
    changed: bool = False
    message: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    validation_ok: bool
    root_pom_needs_migration: bool
    app_pom_needs_migration: bool
    corporate_logger_missing: bool
    distributive_missing: bool
    cleanup_items: Sequence[str]
    project_standard_version: str = "unknown"
    latest_standard_version: str = "unknown"
    migration_complexity: str = "Unknown"
    corporate_dependencies_missing: Sequence[str] = field(default_factory=list)
    detected_application_module: str | None = None
    primary_development_branch: str | None = None
    corporate_branch: str | None = None
    migration_blocked_reason: str | None = None
    warnings: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.validation_ok
