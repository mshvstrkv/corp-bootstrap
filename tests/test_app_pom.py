from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from migrators import app_pom


APP_POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <artifactId>service-app</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
</project>
"""


class AppPomMigrationTest(unittest.TestCase):
    def test_adds_dependencies_processors_profile_and_exclusion_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>service</artifactId>
    <version>1.0.0</version>
    <description>Service</description>
</project>
""",
                encoding="utf-8",
            )
            (root / "service-app").mkdir()
            pom = root / "service-app" / "pom.xml"
            pom.write_text(APP_POM, encoding="utf-8")
            (root / "service-app" / "src").mkdir()

            first = app_pom.migrate(pom)
            second = app_pom.migrate(pom)
            content = pom.read_text(encoding="utf-8")

            self.assertTrue(first.changed)
            self.assertFalse(second.changed)
            self.assertEqual(content.count("<artifactId>logger</artifactId>"), 1)
            self.assertEqual(content.count("<artifactId>spring-boot-starter-logging</artifactId>"), 1)
            self.assertEqual(content.count("<id>deploy-image</id>"), 1)
            self.assertEqual(content.count("<artifactId>lombok-mapstruct-binding</artifactId>"), 1)

    def test_keeps_existing_lombok_dependency_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pom.xml").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <artifactId>service</artifactId>
    <description>Service</description>
</project>
""",
                encoding="utf-8",
            )
            (root / "service-app").mkdir()
            pom = root / "service-app" / "pom.xml"
            pom.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <artifactId>service-app</artifactId>
    <dependencies>
        <dependency>
            <groupId>org.projectlombok</groupId>
            <artifactId>lombok</artifactId>
            <scope>compile</scope>
        </dependency>
    </dependencies>
</project>
""",
                encoding="utf-8",
            )
            (root / "service-app" / "src").mkdir()

            app_pom.migrate(pom)
            content = pom.read_text(encoding="utf-8")

            self.assertEqual(content.count("<artifactId>lombok</artifactId>"), 2)
            self.assertIn("<scope>compile</scope>", content)
            self.assertNotIn("<scope>provided</scope>", content)


if __name__ == "__main__":
    unittest.main()
