"""
Integration tests for the dnfdragora plugin system.

Tests verify that plugins are correctly discovered, loaded, and
their dialogs and updater functions can be called.
"""

import pytest
import tempfile
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

from dnfdragora.plugin_loader import PluginLoader, Plugin


class TestPluginIntegration:
    """Integration tests for the plugin system."""

    def test_plugin_discovery_and_loading(self):
        """Test discovering and loading a real plugin."""
        loader = PluginLoader()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a test plugin directory
            plugin_dir = Path(tmpdir) / "test_plugin"
            plugin_dir.mkdir()

            # Add to sys.path so the module can be imported
            sys.path.insert(0, tmpdir)

            try:
                # Create the plugin module
                (plugin_dir / "__init__.py").write_text("")
                (plugin_dir / "dialog.py").write_text("""
class TestDialog:
    def run(self):
        return True
""")
                (plugin_dir / "updater.py").write_text("""
def get_update_count():
    return 42
""")

                # Create plugin config
                config_path = Path(tmpdir) / "test.plugin"
                config_path.write_text("""[plugin]
name = Test Plugin
module = test_plugin.dialog
dialog_class = TestDialog
updater_module = test_plugin.updater
""")

                # Discover the plugin
                with patch.object(
                    PluginLoader, 'PLUGIN_DIRS', [Path(tmpdir)]
                ):
                    plugins = loader.discover_plugins()
                    assert len(plugins) == 1
                    plugin = plugins[0]

                    # Test loading the dialog class
                    dialog_class = loader.get_plugin_dialog_class(plugin)
                    assert dialog_class is not None
                    dialog = dialog_class()
                    assert hasattr(dialog, 'run')
                    assert dialog.run() == True

                    # Test loading the updater function
                    updater_func = loader.get_updater_function(plugin)
                    assert updater_func is not None
                    update_count = updater_func()
                    assert update_count == 42

            finally:
                sys.path.remove(tmpdir)

    def test_multiple_plugins_integration(self):
        """Test discovering and working with multiple plugins."""
        loader = PluginLoader()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Add to sys.path
            sys.path.insert(0, tmpdir)

            try:
                # Create two test plugins
                for i in [1, 2]:
                    plugin_dir = Path(tmpdir) / f"plugin{i}"
                    plugin_dir.mkdir()
                    (plugin_dir / "__init__.py").write_text("")
                    (plugin_dir / "dialog.py").write_text(f"""
class Plugin{i}Dialog:
    def run(self):
        return "plugin{i}"
""")
                    (plugin_dir / "updater.py").write_text(f"""
def get_update_count():
    return {i * 10}
""")

                    config_path = Path(tmpdir) / f"plugin{i}.plugin"
                    config_path.write_text(f"""[plugin]
name = Plugin {i}
module = plugin{i}.dialog
dialog_class = Plugin{i}Dialog
updater_module = plugin{i}.updater
""")

                # Discover plugins
                with patch.object(
                    PluginLoader, 'PLUGIN_DIRS', [Path(tmpdir)]
                ):
                    plugins = loader.discover_plugins()
                    assert len(plugins) == 2

                    # Test getting all update counts
                    updates = loader.get_total_plugin_updates()
                    assert len(updates) == 2
                    assert updates["Plugin 1"] == 10
                    assert updates["Plugin 2"] == 20
                    assert sum(updates.values()) == 30

                    # Test filtering for updater plugins
                    updater_plugins = loader.get_plugins_for_updater()
                    assert len(updater_plugins) == 2

            finally:
                sys.path.remove(tmpdir)

    def test_plugin_error_handling(self):
        """Test that broken plugins are filtered out during discovery."""
        loader = PluginLoader()

        with tempfile.TemporaryDirectory() as tmpdir:
            sys.path.insert(0, tmpdir)

            try:
                # Create a broken plugin (missing dialog class)
                plugin_dir = Path(tmpdir) / "broken_plugin"
                plugin_dir.mkdir()
                (plugin_dir / "__init__.py").write_text("")
                (plugin_dir / "dialog.py").write_text("")  # Missing dialog class

                config_path = Path(tmpdir) / "broken.plugin"
                config_path.write_text("""[plugin]
name = Broken Plugin
module = broken_plugin.dialog
dialog_class = NonexistentDialog
updater_module = broken_plugin.updater
""")

                # Discovery should skip invalid plugins
                with patch.object(
                    PluginLoader, 'PLUGIN_DIRS', [Path(tmpdir)]
                ):
                    plugins = loader.discover_plugins()
                    assert plugins == []

            finally:
                sys.path.remove(tmpdir)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
