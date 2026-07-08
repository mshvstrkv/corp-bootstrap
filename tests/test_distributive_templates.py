from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugins.distributive import migrate_distributive, validate_distributive_pom_template
from standard_loader import load_standards


ROOT_POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>payments</artifactId>
    <version>1.2.3</version>
</project>
"""


class DistributiveTemplateTest(unittest.TestCase):
    def test_generates_from_templates_with_dynamic_app_module(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(ROOT_POM, encoding="utf-8")
            (root / "payments-app").mkdir()
            (root / "payments-app" / "pom.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <artifactId>payments-app</artifactId>
</project>
""",
                encoding="utf-8",
            )
            templates = Path.cwd() / "corporate-reference"
            values = load_standards().maven_template_values

            result = migrate_distributive(root, templates, app_module="payments-app", template_values=values)

            pom = (root / "distributive" / "pom.xml").read_text(encoding="utf-8")
            assembly = (root / "distributive" / "assembly" / "distributive.xml").read_text(encoding="utf-8")
            self.assertTrue(result)
            self.assertIn("<groupId>CI11366566</groupId>", pom)
            self.assertIn("<artifactId>CI11366566_payments</artifactId>", pom)
            self.assertIn("<version>1.0.0</version>", pom)
            self.assertIn("../payments-app/target", assembly)
            self.assertIn("<id>distrib</id>", assembly)
            self.assertIn("<include>jib-image.digest</include>", assembly)
            self.assertNotIn("__APP_MODULE__", assembly)

    def test_rejects_non_distributive_pom_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            invalid = Path(tmp) / "distributive-pom.xml"
            invalid.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <artifactId>service-app</artifactId>
    <packaging>jar</packaging>
</project>
""",
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeError) as raised:
                validate_distributive_pom_template(invalid)

            self.assertEqual(
                str(raised.exception),
                "Provided distributive POM reference is invalid or not a distributive module POM.",
            )


if __name__ == "__main__":
    unittest.main()
