from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from cleanup import cleanup_project


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


if __name__ == "__main__":
    unittest.main()
