from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from config import ProjectLayout
from report import render_analysis
from standard_loader import load_standards
from validation import analyze_project


POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>service</artifactId>
    <version>1.0.0</version>
</project>
"""


class AnalysisReportTest(unittest.TestCase):
    def test_reports_platform_version_and_complexity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(POM, encoding="utf-8")
            (root / "service-app").mkdir()
            (root / "service-app" / "pom.xml").write_text(POM, encoding="utf-8")
            (root / "service-app" / "src").mkdir()
            (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")

            analysis = analyze_project(ProjectLayout(root), load_standards())
            rendered = render_analysis(analysis)

            self.assertIn("Platform Analysis", rendered)
            self.assertIn("Detected application module: service-app", rendered)
            self.assertIn("Platform Standard: 2025.11", rendered)
            self.assertIn("Latest: 2026.06", rendered)
            self.assertIn("Migration complexity:", rendered)
            self.assertIn("Dockerfile present", rendered)

    def test_reports_blocked_when_application_module_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(POM, encoding="utf-8")

            analysis = analyze_project(ProjectLayout(root), load_standards())
            rendered = render_analysis(analysis)

            self.assertIn("Migration blocked", rendered)
            self.assertIn("Reason", rendered)
            self.assertIn("Application module missing", rendered)


if __name__ == "__main__":
    unittest.main()
