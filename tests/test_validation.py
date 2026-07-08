from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from config import ProjectLayout
from validation import ValidationError, validate_project


POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>service</artifactId>
    <version>1.0.0</version>
</project>
"""


class ValidationTest(unittest.TestCase):
    def test_accepts_expected_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(POM, encoding="utf-8")
            (root / "service-app").mkdir()
            (root / "service-app" / "pom.xml").write_text(POM, encoding="utf-8")
            (root / "service-app" / "src").mkdir()

            self.assertEqual(validate_project(ProjectLayout(root)), "service-app")

    def test_rejects_missing_app_src(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(POM, encoding="utf-8")
            (root / "service-app").mkdir()
            (root / "service-app" / "pom.xml").write_text(POM, encoding="utf-8")

            with self.assertRaises(ValidationError):
                validate_project(ProjectLayout(root))

    def test_accepts_existing_non_default_app_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(POM, encoding="utf-8")
            (root / "payments-app").mkdir()
            (root / "payments-app" / "pom.xml").write_text(POM, encoding="utf-8")
            (root / "payments-app" / "src").mkdir()

            self.assertEqual(validate_project(ProjectLayout(root)), "payments-app")

    def test_rejects_missing_application_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(POM, encoding="utf-8")

            with self.assertRaises(ValidationError) as raised:
                validate_project(ProjectLayout(root))

            self.assertIn("Application module was not found", str(raised.exception))

    def test_rejects_multiple_application_modules(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(POM, encoding="utf-8")
            for module in ("one-app", "two-app"):
                (root / module).mkdir()
                (root / module / "pom.xml").write_text(POM, encoding="utf-8")
                (root / module / "src").mkdir()

            with self.assertRaises(ValidationError) as raised:
                validate_project(ProjectLayout(root))

            self.assertIn("Multiple application modules", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
