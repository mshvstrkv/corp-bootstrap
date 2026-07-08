from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from migrators import root_pom


ROOT_POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>service</artifactId>
    <version>1.0.0</version>
    <description>Service</description>
    <modules>
        <module>service-app</module>
    </modules>
</project>
"""


def root_pom_with_java(java_version: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <artifactId>service</artifactId>
    <description>Service</description>
    <properties>
        <java.version>{java_version}</java.version>
    </properties>
    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.testcontainers</groupId>
                <artifactId>testcontainers-bom</artifactId>
                <version>1.20.6</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
"""


class RootPomMigrationTest(unittest.TestCase):
    def test_migrates_packaging_and_module_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "service-app").mkdir()
            (Path(tmp) / "service-app" / "pom.xml").write_text(ROOT_POM, encoding="utf-8")
            (Path(tmp) / "service-app" / "src").mkdir()
            pom = Path(tmp) / "pom.xml"
            pom.write_text(ROOT_POM, encoding="utf-8")

            first = root_pom.migrate(pom)
            second = root_pom.migrate(pom)
            content = pom.read_text(encoding="utf-8")

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertIn("<packaging>pom</packaging>", content)
            self.assertEqual(content.count("<module>distributive</module>"), 1)

    def test_java_17_sets_compiler_and_base_image_properties(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "service-app").mkdir()
            (root / "service-app" / "pom.xml").write_text(ROOT_POM, encoding="utf-8")
            (root / "service-app" / "src").mkdir()
            pom = root / "pom.xml"
            pom.write_text(root_pom_with_java("17"), encoding="utf-8")

            root_pom.migrate(pom)
            content = pom.read_text(encoding="utf-8")

            self.assertIn("<java.version>17</java.version>", content)
            self.assertIn("<maven.compiler.source>17</maven.compiler.source>", content)
            self.assertIn("<maven.compiler.target>17</maven.compiler.target>", content)
            self.assertIn("<base.image.name>sberjdk-17-runtime</base.image.name>", content)
            self.assertIn("<base.image.version>java-17.0.18_001-sberlinux-minimal-9.7.1-se</base.image.version>", content)
            self.assertIn("<artifactId>testcontainers-bom</artifactId>", content)

    def test_java_21_sets_compiler_and_base_image_properties(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "service-app").mkdir()
            (root / "service-app" / "pom.xml").write_text(ROOT_POM, encoding="utf-8")
            (root / "service-app" / "src").mkdir()
            pom = root / "pom.xml"
            pom.write_text(root_pom_with_java("21"), encoding="utf-8")

            root_pom.migrate(pom)
            content = pom.read_text(encoding="utf-8")

            self.assertIn("<java.version>21</java.version>", content)
            self.assertIn("<maven.compiler.source>21</maven.compiler.source>", content)
            self.assertIn("<maven.compiler.target>21</maven.compiler.target>", content)
            self.assertIn("<base.image.name>sberjdk-21-runtime</base.image.name>", content)
            self.assertIn("<base.image.version>java-21.0.11_001-sberlinux-minimal-9.7.2-se</base.image.version>", content)

    def test_unsupported_java_version_has_readable_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "service-app").mkdir()
            (root / "service-app" / "pom.xml").write_text(ROOT_POM, encoding="utf-8")
            (root / "service-app" / "src").mkdir()
            pom = root / "pom.xml"
            pom.write_text(root_pom_with_java("20"), encoding="utf-8")

            with self.assertRaisesRegex(RuntimeError, "Unsupported Java version for corporate base image: 20"):
                root_pom.migrate(pom)


if __name__ == "__main__":
    unittest.main()
