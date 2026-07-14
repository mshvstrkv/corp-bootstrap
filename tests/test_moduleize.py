from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import ProjectLayout
from moduleize import ModuleizeOptions, ModuleizeRollbackError, corporate_moduleize_if_needed, default_module_name, prepare_moduleize_plan, run_moduleize
from standard_loader import load_standards
from utils.xml_utils import child_text, find_child, parse_xml
from validation import ValidationError, validate_project


POM = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example.payments</groupId>
    <artifactId>ai-payments-service</artifactId>
    <version>1.0.0</version>
    <name>AI Payments</name>
    <description>Payment service</description>
    <properties>
        <java.version>21</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
    <profiles>
        <profile>
            <id>local</id>
        </profile>
    </profiles>
</project>
"""


class FakeGit:
    def __init__(self, repository: bool = True, dirty: bool = False) -> None:
        self.repository = repository
        self.dirty = dirty
        self.commits: list[tuple[Path, str]] = []

    def is_git_repository(self, repo: Path) -> bool:
        return self.repository

    def has_changes(self, repo: Path) -> bool:
        return self.dirty

    def commit(self, repo: Path, message: str) -> bool:
        self.commits.append((repo, message))
        return True


class ModuleizeTest(unittest.TestCase):
    def test_validates_single_module_project_and_default_module_name(self) -> None:
        with project_fixture() as root:
            plan = prepare_moduleize_plan(ModuleizeOptions(project=root), FakeGit())

            self.assertEqual(plan.module_name, "ai-payments-service-app")
            self.assertEqual(default_module_name(root), "ai-payments-service-app")

    def test_custom_module_name_is_used(self) -> None:
        with project_fixture() as root:
            report = run_moduleize(ModuleizeOptions(project=root, module_name="payments-api"), FakeGit())

            self.assertTrue(report.changed)
            self.assertTrue((root / "payments-api" / "pom.xml").is_file())

    def test_moves_root_src_into_app_module(self) -> None:
        with project_fixture() as root:
            run_moduleize(ModuleizeOptions(project=root), FakeGit())

            self.assertFalse((root / "src").exists())
            self.assertTrue((root / "ai-payments-service-app" / "src" / "main" / "java" / "Example.java").is_file())
            self.assertTrue((root / "ai-payments-service-app" / "src" / "test" / "resources" / ".keep").is_file())

    def test_root_pom_converted_to_aggregator_preserving_parent_version_and_java_version(self) -> None:
        with project_fixture() as root:
            run_moduleize(ModuleizeOptions(project=root), FakeGit())

            pom = parse_xml(root / "pom.xml").root
            parent = find_child(pom, "parent")
            modules = find_child(pom, "modules")
            properties = find_child(pom, "properties")
            self.assertEqual(child_text(pom, "groupId"), "com.example.payments")
            self.assertEqual(child_text(pom, "artifactId"), "ai-payments-service")
            self.assertEqual(child_text(pom, "version"), "1.0.0")
            self.assertEqual(child_text(pom, "packaging"), "pom")
            self.assertEqual(child_text(parent, "artifactId"), "spring-boot-starter-parent")
            self.assertEqual(child_text(parent, "version"), "3.2.5")
            self.assertEqual(child_text(properties, "java.version"), "21")
            self.assertEqual(child_text(modules, "module"), "ai-payments-service-app")

    def test_app_pom_created_with_correct_parent_and_dependencies(self) -> None:
        with project_fixture() as root:
            run_moduleize(ModuleizeOptions(project=root), FakeGit())

            pom = parse_xml(root / "ai-payments-service-app" / "pom.xml").root
            parent = find_child(pom, "parent")
            dependencies = find_child(pom, "dependencies")
            self.assertEqual(child_text(parent, "groupId"), "com.example.payments")
            self.assertEqual(child_text(parent, "artifactId"), "ai-payments-service")
            self.assertEqual(child_text(parent, "version"), "1.0.0")
            self.assertEqual(child_text(pom, "artifactId"), "ai-payments-service-app")
            self.assertEqual(child_text(dependencies[0], "artifactId"), "spring-boot-starter-web")

    def test_no_distributive_logger_migration_or_cleanup_are_performed(self) -> None:
        with project_fixture() as root:
            original_java = (root / "src" / "main" / "java" / "Example.java").read_text(encoding="utf-8")
            run_moduleize(ModuleizeOptions(project=root), FakeGit())

            moved_java = root / "ai-payments-service-app" / "src" / "main" / "java" / "Example.java"
            self.assertFalse((root / "distributive").exists())
            self.assertTrue((root / "Jenkinsfile").is_file())
            self.assertEqual(moved_java.read_text(encoding="utf-8"), original_java)
            self.assertNotIn("Slf4j", moved_java.read_text(encoding="utf-8"))

    def test_dirty_working_tree_is_rejected(self) -> None:
        with project_fixture() as root:
            with self.assertRaises(ValidationError) as raised:
                prepare_moduleize_plan(ModuleizeOptions(project=root), FakeGit(dirty=True))

            self.assertIn("Working tree is not clean", str(raised.exception))

    def test_existing_app_module_is_rejected(self) -> None:
        with project_fixture() as root:
            (root / "legacy-app").mkdir()

            with self.assertRaises(ValidationError) as raised:
                prepare_moduleize_plan(ModuleizeOptions(project=root), FakeGit())

            self.assertEqual(str(raised.exception), "Application module already exists.\nUse migrate instead of moduleize.")

    def test_repeated_moduleize_is_idempotent(self) -> None:
        with project_fixture() as root:
            run_moduleize(ModuleizeOptions(project=root), FakeGit())

            with self.assertRaises(ValidationError) as raised:
                prepare_moduleize_plan(ModuleizeOptions(project=root), FakeGit())

            self.assertEqual(str(raised.exception), "Application module already exists.\nNo moduleization required.")

    def test_module_directory_must_not_already_exist(self) -> None:
        with project_fixture() as root:
            (root / "existing-module").mkdir()

            with self.assertRaises(ValidationError) as raised:
                prepare_moduleize_plan(ModuleizeOptions(project=root, module_name="existing-module"), FakeGit())

            self.assertIn("Module directory already exists", str(raised.exception))

    def test_module_name_must_be_single_directory_name(self) -> None:
        with project_fixture() as root:
            with self.assertRaises(ValidationError) as raised:
                prepare_moduleize_plan(ModuleizeOptions(project=root, module_name="../outside"), FakeGit())

            self.assertIn("single directory name", str(raised.exception))

    def test_rollback_restores_original_files(self) -> None:
        with project_fixture() as root:
            original_pom = (root / "pom.xml").read_text(encoding="utf-8")

            with patch("moduleize.shutil.move", side_effect=RuntimeError("move failed")):
                with self.assertRaises(ModuleizeRollbackError) as raised:
                    run_moduleize(ModuleizeOptions(project=root), FakeGit())

            self.assertIn("restored root pom.xml", raised.exception.rollback_actions)
            self.assertEqual((root / "pom.xml").read_text(encoding="utf-8"), original_pom)
            self.assertTrue((root / "src").is_dir())
            self.assertFalse((root / "ai-payments-service-app").exists())

    def test_commit_created_only_with_commit_flag(self) -> None:
        with project_fixture() as root:
            git = FakeGit()
            run_moduleize(ModuleizeOptions(project=root), git)
            self.assertEqual(git.commits, [])

        with project_fixture() as root:
            git = FakeGit()
            run_moduleize(ModuleizeOptions(project=root, commit=True), git)
            self.assertEqual(git.commits, [(root.resolve(), "Create application Maven module")])

    def test_corporate_moduleize_uses_reference_poms_and_moves_src(self) -> None:
        with project_fixture() as root:
            standards = load_standards()

            app_module = corporate_moduleize_if_needed(root, skill_root() / "corporate-reference", standards.maven_template_values)

            self.assertEqual(app_module, "ai-payments-service-app")
            self.assertEqual(validate_project(ProjectLayout(root)), "ai-payments-service-app")
            self.assertFalse((root / "src").exists())
            self.assertTrue((root / "ai-payments-service-app" / "src" / "main" / "java" / "Example.java").is_file())
            self.assertIn("<module>distributive</module>", (root / "pom.xml").read_text(encoding="utf-8"))
            app_pom = (root / "ai-payments-service-app" / "pom.xml").read_text(encoding="utf-8")
            self.assertIn("<artifactId>ai-payments-service-app</artifactId>", app_pom)
            self.assertIn("<artifactId>spring-boot-starter-web</artifactId>", app_pom)
            self.assertIn("<artifactId>logger</artifactId>", app_pom)


class project_fixture:
    def __enter__(self) -> Path:
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / "pom.xml").write_text(POM, encoding="utf-8")
        (root / "src" / "main" / "java").mkdir(parents=True)
        (root / "src" / "main" / "resources").mkdir(parents=True)
        (root / "src" / "test" / "resources").mkdir(parents=True)
        (root / "src" / "main" / "java" / "Example.java").write_text(
            "import org.apache.commons.logging.LogFactory;\nclass Example {}\n",
            encoding="utf-8",
        )
        (root / "src" / "test" / "resources" / ".keep").write_text("", encoding="utf-8")
        (root / "Jenkinsfile").write_text("pipeline {}\n", encoding="utf-8")
        return root

    def __exit__(self, *args) -> None:
        self.tmp.cleanup()


def skill_root() -> Path:
    return Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    unittest.main()
