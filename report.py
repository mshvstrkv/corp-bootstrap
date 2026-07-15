from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from config import AnalysisResult, OperationResult


@dataclass
class MigrationReport:
    completed: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, result: OperationResult) -> None:
        if result.message.startswith("\n"):
            suffix = f":{result.message}"
        else:
            suffix = f": {result.message}" if result.message else ""
        self.completed.append(f"{result.name}{suffix}")
        self.warnings.extend(result.warnings)

    def add_completed(self, message: str) -> None:
        self.completed.append(message)

    def add_warning(self, message: str) -> None:
        if message not in self.warnings:
            self.warnings.append(message)

    def add_error(self, message: str) -> None:
        self.errors.append(message)

    def render(self) -> str:
        lines = ["Migration Report"]
        lines.extend(self.completed or ["No operations completed"])
        if self.warnings:
            lines.append("Warnings")
            lines.extend(f"- {warning}" for warning in self.warnings)
        if self.errors:
            lines.append("Errors")
            lines.extend(f"- {error}" for error in self.errors)
        return "\n".join(lines)


def render_analysis(analysis: AnalysisResult) -> str:
    def mark(ok: bool) -> str:
        return "OK" if ok else "Needs migration"

    lines = [
        "Platform Analysis",
        f"Project Structure: {'OK' if analysis.validation_ok else 'Missing or invalid'}",
        f"Detected application module: {analysis.detected_application_module or 'Missing'}",
        f"Primary development branch: {analysis.primary_development_branch or 'Not selected'}",
        f"Corporate branch: {analysis.corporate_branch or 'Not selected'}",
        f"Root pom: {mark(not analysis.root_pom_needs_migration)}",
        f"Corporate dependencies: {'Missing ' + ', '.join(analysis.corporate_dependencies_missing) if analysis.corporate_dependencies_missing else 'OK'}",
        f"App pom: {mark(not analysis.app_pom_needs_migration)}",
        f"Corporate logger: {'Missing' if analysis.corporate_logger_missing else 'Configured'}",
        f"Distributive: {'Missing' if analysis.distributive_missing else 'OK'}",
    ]
    if analysis.cleanup_items:
        lines.append("Cleanup: " + ", ".join(analysis.cleanup_items) + " present")
    else:
        lines.append("Cleanup: OK")
    lines.extend(
        [
            f"Platform Standard: {analysis.project_standard_version}",
            f"Latest: {analysis.latest_standard_version}",
            f"Migration complexity: {analysis.migration_complexity}",
            f"Platform version: {analysis.project_standard_version}",
            "Migration readiness: Ready" if analysis.ready else "Migration readiness: Blocked",
        ]
    )
    if analysis.migration_blocked_reason:
        lines.append("Migration blocked")
        lines.append("Reason")
        lines.append(analysis.migration_blocked_reason)
    if analysis.warnings:
        lines.append("Warnings")
        lines.extend(f"- {warning}" for warning in analysis.warnings)
    return "\n".join(lines)


def render_plan(operations: Iterable[str]) -> str:
    lines = ["Migration Plan"]
    lines.extend(f"OK {operation}" for operation in operations)
    return "\n".join(lines)
