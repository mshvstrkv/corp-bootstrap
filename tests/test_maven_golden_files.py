from __future__ import annotations

import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from migrators import app_pom, distributive, root_pom


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "maven"
CORPORATE_REFERENCE = Path(__file__).resolve().parents[1] / "corporate-reference"
FORBIDDEN_REFERENCE_PLACEHOLDERS = [
    "{{CORPORATE_",
    "{{BASE_IMAGE}}",
    "{{NEXUS_",
    "{{DISTRIBUTIVE_GROUP_ID}}",
    "{{DISTRIBUTIVE_CLASSIFIER}}",
]


class MavenGoldenFileTest(unittest.TestCase):
    def test_corporate_references_do_not_use_unsupported_placeholders(self) -> None:
        for reference in CORPORATE_REFERENCE.glob("*.xml"):
            content = reference.read_text(encoding="utf-8")
            for forbidden in FORBIDDEN_REFERENCE_PLACEHOLDERS:
                self.assertNotIn(forbidden, content, f"{reference.name} contains forbidden placeholder {forbidden}")

    def test_maven_migration_matches_golden_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            app_dir = root / "payments-app"
            app_dir.mkdir()
            (app_dir / "src").mkdir()
            shutil.copy(FIXTURES / "input" / "pom.xml", root / "pom.xml")
            shutil.copy(FIXTURES / "input" / "app-pom.xml", app_dir / "pom.xml")

            root_pom.migrate(root / "pom.xml")
            app_pom.migrate(app_dir / "pom.xml")
            distributive.migrate(root, Path.cwd() / "templates")
            second_root = root_pom.migrate(root / "pom.xml")
            second_app = app_pom.migrate(app_dir / "pom.xml")
            second_dist = distributive.migrate(root, Path.cwd() / "templates")

            assert_xml_equal(self, root / "pom.xml", FIXTURES / "expected" / "pom.xml")
            assert_xml_equal(self, app_dir / "pom.xml", FIXTURES / "expected" / "app-pom.xml")
            assert_xml_equal(self, root / "distributive" / "pom.xml", FIXTURES / "expected" / "distributive" / "pom.xml")
            assert_xml_equal(
                self,
                root / "distributive" / "assembly" / "distributive.xml",
                FIXTURES / "expected" / "distributive" / "assembly" / "distributive.xml",
            )

            root_content = (root / "pom.xml").read_text(encoding="utf-8")
            app_content = (app_dir / "pom.xml").read_text(encoding="utf-8")
            dist_pom = (root / "distributive" / "pom.xml").read_text(encoding="utf-8")
            dist_xml = (root / "distributive" / "assembly" / "distributive.xml").read_text(encoding="utf-8")

            self.assertIn("<pluginRepositories>", root_content)
            self.assertIn("<pluginManagement>", root_content)
            self.assertIn("<version>3.3.5</version>", root_content)
            self.assertIn("<java.version>21</java.version>", root_content)
            self.assertIn("<maven.compiler.source>21</maven.compiler.source>", root_content)
            self.assertIn("<maven.compiler.target>21</maven.compiler.target>", root_content)
            self.assertIn("<base.image.name>sberjdk-21-runtime</base.image.name>", root_content)
            self.assertIn("<base.image.version>java-21.0.11_001-sberlinux-minimal-9.7.2-se</base.image.version>", root_content)
            self.assertNotIn("<legacy.only>true</legacy.only>", root_content)
            self.assertIn("<artifactId>business-bom</artifactId>", root_content)
            self.assertIn("<artifactId>commons-lang3</artifactId>", root_content)
            self.assertIn("<version>3.18.0</version>", root_content)
            self.assertNotIn("<artifactId>testcontainers-bom</artifactId>", root_content)
            self.assertIn("<artifactId>jib-maven-plugin</artifactId>", root_content)
            self.assertIn("<artifactId>sonar-maven-plugin</artifactId>", root_content)
            self.assertIn("<artifactId>jacoco-maven-plugin</artifactId>", root_content)
            self.assertIn("<artifactId>maven-surefire-plugin</artifactId>", root_content)
            self.assertIn("<artifactId>maven-failsafe-plugin</artifactId>", root_content)
            self.assertIn("<artifactId>maven-deploy-plugin</artifactId>", root_content)
            self.assertIn("<artifactId>business-domain</artifactId>", app_content)
            self.assertIn("<artifactId>spring-boot-starter-logging</artifactId>", app_content)
            self.assertEqual(app_content.count("<artifactId>grpc-api</artifactId>"), 1)
            self.assertIn("<version>9.9.9</version>", app_content)
            self.assertIn("<artifactId>logger</artifactId>", app_content)
            self.assertIn("<artifactId>common-utils-starter</artifactId>", app_content)
            self.assertIn("<artifactId>secman-starter</artifactId>", app_content)
            self.assertNotIn("<artifactId>spring-boot-starter-web</artifactId>", app_content)
            self.assertNotIn("<artifactId>liquibase-core</artifactId>", app_content)
            self.assertNotIn("<artifactId>postgresql</artifactId>", app_content)
            self.assertEqual(app_content.count("<artifactId>lombok</artifactId>"), 2)
            self.assertIn("<scope>provided</scope>", app_content)
            self.assertIn("<artifactId>maven-compiler-plugin</artifactId>", app_content)
            self.assertIn("<id>deploy-image</id>", app_content)
            self.assertIn("<id>deploy-distributive</id>", dist_pom)
            self.assertIn("<classifier>${distributive.classifier}</classifier>", dist_pom)
            self.assertIn("<artifactId>maven-assembly-plugin</artifactId>", dist_pom)
            self.assertNotIn("{{", root_content + app_content + dist_pom + dist_xml)
            self.assertIn("../payments-app/target", dist_xml)
            self.assertIn("<id>distrib</id>", dist_xml)
            self.assertIn("<include>jib-image.digest</include>", dist_xml)
            self.assertFalse(second_root.changed)
            self.assertFalse(second_app.changed)
            self.assertFalse(second_dist.changed)


def assert_xml_equal(test_case: unittest.TestCase, actual: Path, expected: Path) -> None:
    test_case.assertEqual(normalized_xml(actual), normalized_xml(expected))


def normalized_xml(path: Path) -> bytes:
    root = ET.parse(path).getroot()
    strip_whitespace(root)
    return ET.tostring(root, encoding="utf-8")


def strip_whitespace(node: ET.Element) -> None:
    if node.text is not None and not node.text.strip():
        node.text = None
    if node.tail is not None and not node.tail.strip():
        node.tail = None
    for child in node:
        strip_whitespace(child)


if __name__ == "__main__":
    unittest.main()
