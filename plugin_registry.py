from __future__ import annotations

import importlib
from dataclasses import dataclass

from plugin_base import MigrationPlugin
from standard_loader import Standards


class PluginRegistryError(RuntimeError):
    pass


@dataclass(frozen=True)
class PluginRegistry:
    standards: Standards

    def load_plugins(self) -> list[MigrationPlugin]:
        plugins: list[MigrationPlugin] = []
        for entry in self.standards.plugins.get("plugins", []):
            if not entry.get("enabled", True):
                continue
            module_name = entry.get("module")
            if not module_name:
                raise PluginRegistryError("Plugin entry is missing module")
            if not str(module_name).startswith("plugins."):
                raise PluginRegistryError(f"Plugin module must be under plugins/: {module_name}")
            module = importlib.import_module(str(module_name))
            factory = getattr(module, "create_plugin", None)
            if factory is None:
                raise PluginRegistryError(f"Plugin module {module_name} must expose create_plugin()")
            plugin = factory()
            if not isinstance(plugin, MigrationPlugin):
                raise PluginRegistryError(f"Plugin module {module_name} did not create a MigrationPlugin")
            plugins.append(plugin)
        return plugins
