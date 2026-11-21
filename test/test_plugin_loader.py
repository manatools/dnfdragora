"""
Unit tests for the dnfdragora plugin loader.

Tests cover plugin discovery, validation, loading, and update count retrieval.
Uses mocking to avoid actual file I/O and module imports.

License: GPLv3
Author: Copilot
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import logging

from dnfdragora.plugin_loader import PluginLoader, Plugin


class TestPluginParsing:
    """Test plugin configuration file parsing."""

    def test_parse_valid_plugin_config(self):
        """Test parsing a valid plugin configuration."""
        loader = PluginLoader()

        config_content = """[plugin]
name = TestPlugin
module = test_module.plugin
dialog_class = TestDialog
updater_module = test_module.updater
"""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.plugin', delete=False, encoding='utf-8'
        ) as f:
            f.write(config_content)
            config_path = Path(f.name)

        try:
            plugin = loader._parse_plugin_config(config_path)
            assert plugin is not None
            assert plugin.name == "TestPlugin"
            assert plugin.module_name == "test_module.plugin"
            assert plugin.dialog_class_name == "TestDialog"
            assert plugin.updater_module_name == "test_module.updater"
            assert plugin.config_path == config_path
        finally:
            os.unlink(config_path)

    def test_parse_plugin_without_updater_module(self):
        """Test parsing plugin config without optional updater_module."""
        loader = PluginLoader()

        config_content = """[plugin]
name = SimplePlugin
module = simple.plugin
dialog_class = SimpleDialog
"""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.plugin', delete=False, encoding='utf-8'
        ) as f:
            f.write(config_content)
            config_path = Path(f.name)

        try:
            plugin = loader._parse_plugin_config(config_path)
            assert plugin is not None
            assert plugin.updater_module_name is None
        finally:
            os.unlink(config_path)

    def test_parse_config_missing_required_field(self):
        """Test that configs with missing required fields return None."""
        loader = PluginLoader()

        config_content = """[plugin]
name = IncompletePlugin
module = incomplete.plugin
"""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.plugin', delete=False, encoding='utf-8'
        ) as f:
            f.write(config_content)
            config_path = Path(f.name)

        try:
            plugin = loader._parse_plugin_config(config_path)
            assert plugin is None
        finally:
            os.unlink(config_path)

    def test_parse_config_missing_plugin_section(self):
        """Test that configs without [plugin] section return None."""
        loader = PluginLoader()

        config_content = """[other_section]
key = value
"""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.plugin', delete=False, encoding='utf-8'
        ) as f:
            f.write(config_content)
            config_path = Path(f.name)

        try:
            plugin = loader._parse_plugin_config(config_path)
            assert plugin is None
        finally:
            os.unlink(config_path)

    def test_parse_config_whitespace_trimming(self):
        """Test that configuration values have whitespace trimmed."""
        loader = PluginLoader()

        config_content = """[plugin]
name =  SpacedPlugin  
module =  spaced.plugin  
dialog_class =  SpacedDialog  
updater_module =  spaced.updater  
"""
        with tempfile.NamedTemporaryFile(
            mode='w', suffix='.plugin', delete=False, encoding='utf-8'
        ) as f:
            f.write(config_content)
            config_path = Path(f.name)

        try:
            plugin = loader._parse_plugin_config(config_path)
            assert plugin is not None
            assert plugin.name == "SpacedPlugin"
            assert plugin.module_name == "spaced.plugin"
            assert plugin.dialog_class_name == "SpacedDialog"
            assert plugin.updater_module_name == "spaced.updater"
        finally:
            os.unlink(config_path)


class TestPluginDiscovery:
    """Test plugin discovery from directories."""

    def test_discover_plugins_empty_directory(self):
        """Test discovery when no plugins exist."""
        loader = PluginLoader()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(
                PluginLoader, 'PLUGIN_DIRS', [Path(tmpdir)]
            ):
                plugins = loader.discover_plugins()
                assert plugins == []

    def test_discover_plugins_ignores_invalid_extensions(self):
        """Test that files with invalid extensions are ignored."""
        loader = PluginLoader()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create files with invalid extensions
            Path(tmpdir, "plugin.txt").write_text("[plugin]\nname=Test\n")
            Path(tmpdir, "plugin.conf").write_text("[plugin]\nname=Test\n")

            with patch.object(
                PluginLoader, 'PLUGIN_DIRS', [Path(tmpdir)]
            ):
                plugins = loader.discover_plugins()
                assert plugins == []

    def test_discover_plugins_finds_valid_configs(self):
        """Test that valid plugin configs are discovered."""
        loader = PluginLoader()

        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "test.plugin"
            config_path.write_text(
                "[plugin]\nname=TestPlugin\nmodule=test.plugin\n"
                "dialog_class=TestDialog\n"
            )

            with patch.object(
                PluginLoader, 'PLUGIN_DIRS', [Path(tmpdir)]
            ):
                plugins = loader.discover_plugins()
                assert len(plugins) == 1
                assert plugins[0].name == "TestPlugin"

    def test_discover_plugins_nonexistent_directory(self):
        """Test that nonexistent directories are handled gracefully."""
        loader = PluginLoader()

        with patch.object(
            PluginLoader, 'PLUGIN_DIRS',
            [Path("/nonexistent/plugin/directory")]
        ):
            # Should not raise exception
            plugins = loader.discover_plugins()
            assert plugins == []

    def test_discover_plugins_multiple_directories(self):
        """Test discovery from multiple plugin directories."""
        loader = PluginLoader()

        with tempfile.TemporaryDirectory() as tmpdir1:
            with tempfile.TemporaryDirectory() as tmpdir2:
                config1 = Path(tmpdir1) / "plugin1.plugin"
                config1.write_text(
                    "[plugin]\nname=Plugin1\nmodule=plugin1\n"
                    "dialog_class=Dialog1\n"
                )

                config2 = Path(tmpdir2) / "plugin2.plugin"
                config2.write_text(
                    "[plugin]\nname=Plugin2\nmodule=plugin2\n"
                    "dialog_class=Dialog2\n"
                )

                with patch.object(
                    PluginLoader, 'PLUGIN_DIRS',
                    [Path(tmpdir1), Path(tmpdir2)]
                ):
                    plugins = loader.discover_plugins()
                    assert len(plugins) == 2
                    names = {p.name for p in plugins}
                    assert names == {"Plugin1", "Plugin2"}


class TestPluginLoading:
    """Test dynamic plugin module loading."""

    def test_load_plugin_module_success(self):
        """Test successful module loading."""
        loader = PluginLoader()

        with patch('dnfdragora.plugin_loader.importlib.import_module') as mock_import:
            mock_module = MagicMock()
            mock_import.return_value = mock_module

            plugin = Plugin(
                name="Test",
                module_name="test.module",
                dialog_class_name="TestDialog",
                updater_module_name=None,
                config_path=Path("/fake/path")
            )

            result = loader.load_plugin_module(plugin)
            assert result is True
            assert plugin.module == mock_module
            mock_import.assert_called_once_with("test.module")

    def test_load_plugin_module_import_error(self):
        """Test handling of ImportError during module loading."""
        loader = PluginLoader()

        with patch('dnfdragora.plugin_loader.importlib.import_module') as mock_import:
            mock_import.side_effect = ImportError("Module not found")

            plugin = Plugin(
                name="Test",
                module_name="nonexistent.module",
                dialog_class_name="TestDialog",
                updater_module_name=None,
                config_path=Path("/fake/path")
            )

            result = loader.load_plugin_module(plugin)
            assert result is False
            assert plugin.module is None

    def test_load_plugin_module_caching(self):
        """Test that loaded modules are cached."""
        loader = PluginLoader()

        with patch('dnfdragora.plugin_loader.importlib.import_module') as mock_import:
            mock_module = MagicMock()
            mock_import.return_value = mock_module

            plugin = Plugin(
                name="Test",
                module_name="test.module",
                dialog_class_name="TestDialog",
                updater_module_name=None,
                config_path=Path("/fake/path")
            )

            # Load twice
            loader.load_plugin_module(plugin)
            loader.load_plugin_module(plugin)

            # Import should only be called once (cached)
            assert mock_import.call_count == 1

    def test_get_plugin_dialog_class_success(self):
        """Test successful retrieval of dialog class."""
        loader = PluginLoader()

        mock_module = MagicMock()
        mock_dialog_class = MagicMock()
        mock_module.TestDialog = mock_dialog_class

        with patch('dnfdragora.plugin_loader.importlib.import_module') as mock_import:
            mock_import.return_value = mock_module

            plugin = Plugin(
                name="Test",
                module_name="test.module",
                dialog_class_name="TestDialog",
                updater_module_name=None,
                config_path=Path("/fake/path")
            )

            result = loader.get_plugin_dialog_class(plugin)
            assert result == mock_dialog_class
            assert plugin.dialog_class == mock_dialog_class

    def test_get_plugin_dialog_class_not_found(self):
        """Test handling of missing dialog class."""
        loader = PluginLoader()

        mock_module = MagicMock(spec=[])  # Empty spec, no attributes

        with patch('dnfdragora.plugin_loader.importlib.import_module') as mock_import:
            mock_import.return_value = mock_module

            plugin = Plugin(
                name="Test",
                module_name="test.module",
                dialog_class_name="NonexistentDialog",
                updater_module_name=None,
                config_path=Path("/fake/path")
            )

            result = loader.get_plugin_dialog_class(plugin)
            assert result is None


class TestUpdaterIntegration:
    """Test plugin update count retrieval."""

    def test_get_plugins_for_dnfdragora_all_plugins(self):
        """Test that get_plugins_for_dnfdragora returns all discovered plugins."""
        loader = PluginLoader()

        p1 = Plugin(
            name="Plugin1",
            module_name="plugin1",
            dialog_class_name="Dialog1",
            updater_module_name="updater1",
            config_path=Path("/fake/1")
        )
        p2 = Plugin(
            name="Plugin2",
            module_name="plugin2",
            dialog_class_name="Dialog2",
            updater_module_name=None,
            config_path=Path("/fake/2")
        )
        loader._plugins = [p1, p2]

        result = loader.get_plugins_for_dnfdragora()
        assert len(result) == 2
        assert p1 in result
        assert p2 in result

    def test_get_plugins_for_updater_only_with_updater_module(self):
        """Test that get_plugins_for_updater only returns plugins with updater_module."""
        loader = PluginLoader()

        p1 = Plugin(
            name="Plugin1",
            module_name="plugin1",
            dialog_class_name="Dialog1",
            updater_module_name="updater1",
            config_path=Path("/fake/1")
        )
        p2 = Plugin(
            name="Plugin2",
            module_name="plugin2",
            dialog_class_name="Dialog2",
            updater_module_name=None,
            config_path=Path("/fake/2")
        )
        loader._plugins = [p1, p2]

        result = loader.get_plugins_for_updater()
        assert len(result) == 1
        assert result[0] == p1

    def test_get_updater_function_success(self):
        """Test successful retrieval of get_update_count function."""
        loader = PluginLoader()

        mock_updater_module = MagicMock()
        mock_updater_module.get_update_count = MagicMock(return_value=5)

        with patch('dnfdragora.plugin_loader.importlib.import_module') as mock_import:
            mock_import.return_value = mock_updater_module

            plugin = Plugin(
                name="Test",
                module_name="test.module",
                dialog_class_name="TestDialog",
                updater_module_name="test.updater",
                config_path=Path("/fake/path")
            )

            func = loader.get_updater_function(plugin)
            assert func is not None
            count = func()
            assert count == 5

    def test_get_updater_function_timeout(self):
        """Test that get_update_count calls timeout correctly."""
        loader = PluginLoader()

        def slow_update_count():
            import time
            time.sleep(2)
            return 10

        mock_updater_module = MagicMock()
        mock_updater_module.get_update_count = slow_update_count

        with patch('dnfdragora.plugin_loader.importlib.import_module') as mock_import:
            mock_import.return_value = mock_updater_module

            plugin = Plugin(
                name="Test",
                module_name="test.module",
                dialog_class_name="TestDialog",
                updater_module_name="test.updater",
                config_path=Path("/fake/path")
            )

            func = loader.get_updater_function(plugin, timeout_sec=0.5)
            assert func is not None
            count = func()
            # Should timeout and return 0
            assert count == 0

    def test_get_updater_function_missing_function(self):
        """Test that missing get_update_count function returns None."""
        loader = PluginLoader()

        mock_updater_module = MagicMock(spec=[])  # No attributes

        with patch('dnfdragora.plugin_loader.importlib.import_module') as mock_import:
            mock_import.return_value = mock_updater_module

            plugin = Plugin(
                name="Test",
                module_name="test.module",
                dialog_class_name="TestDialog",
                updater_module_name="test.updater",
                config_path=Path("/fake/path")
            )

            func = loader.get_updater_function(plugin)
            assert func is None

    def test_get_total_plugin_updates(self):
        """Test aggregation of update counts from multiple plugins."""
        loader = PluginLoader()

        p1 = Plugin(
            name="Plugin1",
            module_name="plugin1",
            dialog_class_name="Dialog1",
            updater_module_name="updater1",
            config_path=Path("/fake/1")
        )
        p2 = Plugin(
            name="Plugin2",
            module_name="plugin2",
            dialog_class_name="Dialog2",
            updater_module_name="updater2",
            config_path=Path("/fake/2")
        )

        loader._plugins = [p1, p2]

        def mock_import_side_effect(module_name):
            mock_module = MagicMock()
            if module_name == "updater1":
                mock_module.get_update_count = MagicMock(return_value=3)
            elif module_name == "updater2":
                mock_module.get_update_count = MagicMock(return_value=7)
            return mock_module

        with patch('dnfdragora.plugin_loader.importlib.import_module') as mock_import:
            mock_import.side_effect = mock_import_side_effect

            updates = loader.get_total_plugin_updates()
            assert updates == {"Plugin1": 3, "Plugin2": 7}


class TestPluginReset:
    """Test plugin loader reset functionality."""

    def test_reset_clears_plugins_and_cache(self):
        """Test that reset clears all plugins and cached modules."""
        loader = PluginLoader()

        p1 = Plugin(
            name="Plugin1",
            module_name="plugin1",
            dialog_class_name="Dialog1",
            updater_module_name=None,
            config_path=Path("/fake/1")
        )
        loader._plugins = [p1]
        loader._loaded_modules = {"plugin1": MagicMock()}

        loader.reset()

        assert loader._plugins == []
        assert loader._loaded_modules == {}


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
