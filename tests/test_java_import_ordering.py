from __future__ import annotations

import unittest

from plugins.logger import migrate_source
from standard_loader import load_standards


class JavaImportOrderingTest(unittest.TestCase):
    def test_adds_slf4j_to_import_block_before_static_imports(self) -> None:
        rules = load_standards().migration_rules["logger"]
        source = """package com.example;

import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import static java.util.Collections.emptyList;

@Deprecated
public class Demo {
    private static final Logger log = LoggerFactory.getLogger(Demo.class);
}
"""

        migrated = migrate_source(source, rules)

        self.assertIn(
            "import java.util.List;\nimport lombok.extern.slf4j.Slf4j;\n\nimport static java.util.Collections.emptyList;",
            migrated,
        )
        self.assertIn("@Deprecated\n@Slf4j\npublic class Demo", migrated)


if __name__ == "__main__":
    unittest.main()
