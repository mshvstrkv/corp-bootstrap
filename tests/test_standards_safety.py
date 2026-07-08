from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from plugin_registry import PluginRegistry, PluginRegistryError
from standard_loader import StandardsError, load_standards


class StandardsSafetyTest(unittest.TestCase):
    def test_missing_required_key_has_readable_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in [
                "plugins.yaml",
                "dependencies.yaml",
                "annotation-processors.yaml",
                "maven-plugins.yaml",
                "maven-reference-mapping.yaml",
                "cleanup.yaml",
                "migration-rules.yaml",
            ]:
                (root / name).write_text("{}", encoding="utf-8")
            (root / "platform.yaml").write_text(json.dumps({"standard_name": "Corporate Platform Standard"}), encoding="utf-8")

            with self.assertRaises(StandardsError) as raised:
                load_standards(root)

            self.assertIn("platform.yaml is missing required key", str(raised.exception))

    def test_plugin_modules_must_be_local_plugins(self) -> None:
        standards = load_standards()
        standards.plugins["plugins"] = [{"name": "bad", "module": "os", "enabled": True}]

        with self.assertRaises(PluginRegistryError):
            PluginRegistry(standards).load_plugins()


if __name__ == "__main__":
    unittest.main()
