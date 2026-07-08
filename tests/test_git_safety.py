from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from plugins.git import ensure_child_path, repository_name


class GitSafetyTest(unittest.TestCase):
    def test_repository_name_is_sanitized(self) -> None:
        self.assertEqual(repository_name("https://gitverse.example/team/service.git"), "service")
        self.assertEqual(repository_name("../danger.git"), "danger")
        self.assertEqual(repository_name("ssh://gitverse.example/team/service name.git"), "service-name")

    def test_rejects_paths_outside_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            child = workspace / "repo"
            workspace.mkdir()

            ensure_child_path(workspace, child)
            with self.assertRaises(RuntimeError):
                ensure_child_path(workspace, Path(tmp) / "other")


if __name__ == "__main__":
    unittest.main()
