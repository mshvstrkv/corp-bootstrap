from __future__ import annotations

import unittest

from migrators.java_logger import migrate_source


class JavaLoggerMigrationTest(unittest.TestCase):
    def test_replaces_logger_field_with_slf4j_without_touching_statements(self) -> None:
        source = """package com.example;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class Demo {
    private static final Logger log = LoggerFactory.getLogger(Demo.class);

    public void run() {
        log.info("started");
    }
}
"""
        migrated = migrate_source(source)
        migrated_again = migrate_source(migrated)

        self.assertIn("import lombok.extern.slf4j.Slf4j;", migrated)
        self.assertIn("@Slf4j\npublic class Demo", migrated)
        self.assertNotIn("LoggerFactory", migrated)
        self.assertNotIn("org.slf4j.Logger", migrated)
        self.assertIn('log.info("started");', migrated)
        self.assertEqual(migrated, migrated_again)


if __name__ == "__main__":
    unittest.main()
