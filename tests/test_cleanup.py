from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cleanup import cleanup_project
from plugins.cleanup import remove_local_certificates
from report import MigrationReport


class CleanupTest(unittest.TestCase):
    def test_removes_expected_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".mvn").mkdir()
            (root / "k8s").mkdir()
            (root / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
            (root / "mvnw").write_text("#!/bin/sh\n", encoding="utf-8")

            result = cleanup_project(root)

            self.assertTrue(result.changed)
            self.assertFalse((root / ".mvn").exists())
            self.assertFalse((root / "k8s").exists())
            self.assertFalse((root / "Dockerfile").exists())
            self.assertFalse((root / "mvnw").exists())

    def test_removes_certificate_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "certs").mkdir()
            (root / "certs" / "client.p12").write_text("secret\n", encoding="utf-8")

            removed = remove_local_certificates(root)

            self.assertEqual(removed, ["certs/"])
            self.assertFalse((root / "certs").exists())

    def test_removes_certificate_files_by_extension(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            resources = root / "src" / "main" / "resources"
            resources.mkdir(parents=True)
            for name in ("truststore.jks", "client.p12", "ca.pem"):
                (resources / name).write_text("secret\n", encoding="utf-8")

            removed = remove_local_certificates(root)

            self.assertEqual(
                removed,
                [
                    "src/main/resources/ca.pem",
                    "src/main/resources/client.p12",
                    "src/main/resources/truststore.jks",
                ],
            )
            for name in ("truststore.jks", "client.p12", "ca.pem"):
                self.assertFalse((resources / name).exists())

    def test_preserves_docs_examples_and_sample_certificates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory in ("docs", "examples", "sample"):
                target = root / directory / "certs"
                target.mkdir(parents=True)
                (target / "example.pem").write_text("not-secret\n", encoding="utf-8")
            (root / "src" / "main" / "resources").mkdir(parents=True)
            (root / "src" / "main" / "resources" / "client-template.pem").write_text("template\n", encoding="utf-8")

            removed = remove_local_certificates(root)

            self.assertEqual(removed, [])
            self.assertTrue((root / "docs" / "certs" / "example.pem").exists())
            self.assertTrue((root / "examples" / "certs" / "example.pem").exists())
            self.assertTrue((root / "sample" / "certs" / "example.pem").exists())
            self.assertTrue((root / "src" / "main" / "resources" / "client-template.pem").exists())

    def test_certificate_cleanup_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "src" / "main" / "resources").mkdir(parents=True)
            (root / "src" / "main" / "resources" / "client.p12").write_text("secret\n", encoding="utf-8")

            first = remove_local_certificates(root)
            second = remove_local_certificates(root)

            self.assertEqual(first, ["src/main/resources/client.p12"])
            self.assertEqual(second, [])

    def test_migration_report_lists_removed_certificates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "certs").mkdir()
            (root / "src" / "main" / "resources").mkdir(parents=True)
            (root / "src" / "main" / "resources" / "truststore.jks").write_text("secret\n", encoding="utf-8")

            result = cleanup_project(root)
            report = MigrationReport()
            report.add(result)
            rendered = report.render()

            self.assertIn("Cleanup:", rendered)
            self.assertIn("  removed certificates:", rendered)
            self.assertIn("    certs/", rendered)
            self.assertIn("    src/main/resources/truststore.jks", rendered)

    def test_migration_report_shows_no_certificates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = cleanup_project(Path(tmp))
            report = MigrationReport()
            report.add(result)

            self.assertIn("  certificates: none", report.render())


if __name__ == "__main__":
    unittest.main()
