"""
Plugin loader and manager for dnfdragora.

This module provides a system for discovering, loading, and managing plugins
that extend dnfdragora functionality. Plugins are defined via configuration files
and must conform to a specific interface.

License: GPLv3
Author: Angelo Naselli <anaselli@linux.it> by using Copilot
"""

import os
import sys
import logging
import importlib
import configparser
import inspect
import threading
from dataclasses import dataclass
from typing import List, Dict, Optional, Any
from pathlib import Path

logger = logging.getLogger('dnfdragora.plugin_loader')


@dataclass
class Plugin:
    """
    Represents a loaded plugin with its metadata and module reference.

    Attributes:
        name: Display name of the plugin
        module_name: Fully qualified Python module name
        dialog_class_name: Name of the dialog class to instantiate
        updater_module_name: Optional module with get_update_count() function
        icon_name: Optional icon name from theme (e.g. 'manapak')
        config_path: Path to the plugin configuration file
        module: Loaded Python module (None if not yet loaded)
        dialog_class: Loaded dialog class (None if not yet loaded)
    """
    name: str
    module_name: str
    dialog_class_name: str
    updater_module_name: Optional[str]
    icon_name: Optional[str]
    config_path: Path
    module: Optional[Any] = None
    dialog_class: Optional[Any] = None

    def __eq__(self, other):
        if not isinstance(other, Plugin):
            return False
        return self.name == other.name and self.module_name == other.module_name


class PluginLoader:
    """
    Manages plugin discovery, loading, and lifecycle.

    Plugins are discovered from standard directories and loaded on demand
    with comprehensive error handling to prevent broken plugins from crashing
    the application.

    Security Considerations:
    - Plugins are only loaded from known system and user directories
    - Module imports use importlib with strict error handling
    - No arbitrary code execution without user consent
    - Plugin calls (e.g., get_update_count) should be wrapped with timeouts
    """

    # Standard plugin directories (checked in order)
    PLUGIN_DIRS = [
        Path("/usr/share/dnfdragora/plugins"),
        Path("/usr/local/share/dnfdragora/plugins"),
        Path.home() / ".local" / "share" / "dnfdragora" / "plugins",
    ]

    # Supported configuration file extensions
    CONFIG_EXTENSIONS = (".plugin", ".ini", ".cfg")

    def __init__(self):
        """Initialize the plugin loader."""
        self._plugins: List[Plugin] = []
        self._loaded_modules: Dict[str, Any] = {}

    def discover_plugins(self) -> List[Plugin]:
        """
        Discover all available plugins in standard directories.

        Plugins are configuration files with metadata specifying the module
        and dialog class to load. Invalid or incomplete configurations are
        logged but do not raise exceptions.

        Returns:
            List of discovered Plugin objects (not yet loaded).
        """
        self._plugins = []

        for plugin_dir in self.PLUGIN_DIRS:
            if not plugin_dir.exists():
                logger.debug(f"Plugin directory does not exist: {plugin_dir}")
                continue

            if not plugin_dir.is_dir():
                logger.warning(f"Plugin path is not a directory: {plugin_dir}")
                continue

            logger.debug(f"Scanning plugin directory: {plugin_dir}")

            # Scan both top-level and subdirectory-based plugins
            # Allow *.plugin files directly in plugin_dir or in subdirectories
            for item in plugin_dir.iterdir():
                config_path = None
                
                # Case 1: Direct .plugin file in plugin_dir
                if item.is_file() and item.suffix in self.CONFIG_EXTENSIONS:
                    config_path = item
                
                # Case 2: Subdirectory with a .plugin file inside
                elif item.is_dir():
                    for sub_item in item.iterdir():
                        if sub_item.is_file() and sub_item.suffix in self.CONFIG_EXTENSIONS:
                            config_path = sub_item
                            break  # Use first .plugin file found
                
                if config_path:
                    try:
                        plugin = self._parse_plugin_config(config_path)
                        if plugin and self._validate_plugin(plugin):
                            self._plugins.append(plugin)
                            logger.info(f"Discovered plugin: {plugin.name} ({config_path})")
                    except Exception as e:
                        logger.error(
                            f"Failed to parse plugin config {config_path}: {e}",
                            exc_info=True
                        )

        logger.info(f"Total plugins discovered: {len(self._plugins)}")
        return self._plugins

    def _validate_plugin(self, plugin: Plugin) -> bool:
        """
        Validate plugin module and dialog class before exposing it in menus.

        Validation checks:
            - plugin module can be imported
            - configured dialog class exists
            - dialog class is callable
            - dialog class can be instantiated with no args
            - when updater_module is configured, it can be imported
            - updater module exports callable get_update_count() with no args

        Returns:
            True if validation succeeds, False otherwise.
        """
        plugin_parent_dir = str(plugin.config_path.parent.parent)
        if plugin_parent_dir not in sys.path:
            sys.path.insert(0, plugin_parent_dir)
            logger.debug(f"Added plugin directory to sys.path: {plugin_parent_dir}")

        try:
            module = importlib.import_module(plugin.module_name)
            dialog_class = getattr(module, plugin.dialog_class_name)
            if not callable(dialog_class):
                raise TypeError(
                    f"Configured dialog class {plugin.dialog_class_name} is not callable"
                )
            dialog_class()
        except ImportError as e:
            logger.warning(
                "Skipping plugin '%s': cannot import module '%s' (%s)",
                plugin.name, plugin.module_name, e
            )
            return False
        except AttributeError as e:
            logger.warning(
                "Skipping plugin '%s': missing dialog class '%s' in module '%s' (%s)",
                plugin.name, plugin.dialog_class_name, plugin.module_name, e
            )
            return False
        except TypeError as e:
            logger.warning(
                "Skipping plugin '%s': invalid dialog class '%s' (%s)",
                plugin.name, plugin.dialog_class_name, e
            )
            return False
        except Exception as e:
            logger.warning(
                "Skipping plugin '%s': failed to instantiate dialog class '%s' (%s)",
                plugin.name, plugin.dialog_class_name, e
            )
            return False

        plugin.module = module
        plugin.dialog_class = dialog_class
        return self._validate_updater_contract(plugin)

    def _validate_updater_contract(self, plugin: Plugin) -> bool:
        """
        Validate optional updater module contract for updater integration.

        Returns:
            True when no updater module is configured or updater contract is valid.
        """
        if not plugin.updater_module_name:
            return True

        try:
            updater_module = importlib.import_module(plugin.updater_module_name)
            updater_function = getattr(updater_module, 'get_update_count')
            if not callable(updater_function):
                raise TypeError("get_update_count is not callable")

            signature = inspect.signature(updater_function)
            for parameter in signature.parameters.values():
                if (
                    parameter.default is inspect.Parameter.empty
                    and parameter.kind in (
                        inspect.Parameter.POSITIONAL_ONLY,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    )
                ):
                    raise TypeError("get_update_count must not require arguments")
        except ImportError as e:
            logger.warning(
                "Skipping plugin '%s': cannot import updater module '%s' (%s)",
                plugin.name, plugin.updater_module_name, e
            )
            return False
        except AttributeError as e:
            logger.warning(
                "Skipping plugin '%s': updater module '%s' is missing get_update_count (%s)",
                plugin.name, plugin.updater_module_name, e
            )
            return False
        except TypeError as e:
            logger.warning(
                "Skipping plugin '%s': invalid get_update_count in updater module '%s' (%s)",
                plugin.name, plugin.updater_module_name, e
            )
            return False
        except Exception as e:
            logger.warning(
                "Skipping plugin '%s': failed to validate updater module '%s' (%s)",
                plugin.name, plugin.updater_module_name, e
            )
            return False

        return True

    def _parse_plugin_config(self, config_path: Path) -> Optional[Plugin]:
        """
        Parse a plugin configuration file.

        Configuration files must be in INI format with a [plugin] section
        containing required and optional keys.

        Required keys:
            - name: Display name
            - module: Python module to import
            - dialog_class: Class name to instantiate

        Optional keys:
            - updater_module: Module with get_update_count() function
            - icon: Icon name from the system theme

        Args:
            config_path: Path to the configuration file

        Returns:
            Plugin object if valid, None otherwise
        """
        config = configparser.ConfigParser()
        try:
            config.read(config_path, encoding='utf-8')
        except Exception as e:
            logger.error(f"Failed to read plugin config {config_path}: {e}")
            return None

        if 'plugin' not in config:
            logger.error(f"Plugin config missing [plugin] section: {config_path}")
            return None

        section = config['plugin']
        required_keys = {'name', 'module', 'dialog_class'}
        missing_keys = required_keys - set(section.keys())

        if missing_keys:
            logger.error(
                f"Plugin config missing required keys {missing_keys}: {config_path}"
            )
            return None

        try:
            plugin = Plugin(
                name=section['name'].strip(),
                module_name=section['module'].strip(),
                dialog_class_name=section['dialog_class'].strip(),
                updater_module_name=section.get('updater_module', '').strip() or None,
                icon_name=section.get('icon', '').strip() or None,
                config_path=config_path
            )
            return plugin
        except Exception as e:
            logger.error(f"Failed to create Plugin object from {config_path}: {e}")
            return None

    def get_plugins_for_dnfdragora(self) -> List[Plugin]:
        """
        Get list of plugins available for the dnfdragora main UI.

        Only returns plugins that have been successfully validated and have
        the required fields (name, module, dialog_class).

        Returns:
            List of Plugin objects ready to be used in the UI.
        """
        return self._plugins.copy()

    def get_plugins_for_updater(self) -> List[Plugin]:
        """
        Get list of plugins that provide update counts for dnfdragora-updater.

        Only returns plugins that have an updater_module specified.

        Returns:
            List of Plugin objects with updater_module defined.
        """
        return [p for p in self._plugins if p.updater_module_name]

    def load_plugin_module(self, plugin: Plugin) -> bool:
        """
        Load the Python module for a plugin.

        Uses importlib to safely import the module. If already loaded, returns
        the cached module. Comprehensive error handling prevents broken
        plugins from crashing the application.

        Args:
            plugin: The Plugin object to load

        Returns:
            True if module loaded successfully, False otherwise
        """
        if plugin.module_name in self._loaded_modules:
            plugin.module = self._loaded_modules[plugin.module_name]
            return True

        try:
            # Ensure the plugin directory is in sys.path so modules can be imported
            plugin_parent_dir = str(plugin.config_path.parent.parent)
            if plugin_parent_dir not in sys.path:
                sys.path.insert(0, plugin_parent_dir)
                logger.debug(f"Added plugin directory to sys.path: {plugin_parent_dir}")
            
            logger.debug(f"Loading plugin module: {plugin.module_name}")
            module = importlib.import_module(plugin.module_name)
            self._loaded_modules[plugin.module_name] = module
            plugin.module = module
            logger.info(f"Successfully loaded plugin module: {plugin.module_name}")
            return True
        except ImportError as e:
            logger.error(
                f"Failed to import plugin module {plugin.module_name}: {e}",
                exc_info=True
            )
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error loading plugin module {plugin.module_name}: {e}",
                exc_info=True
            )
            return False

    def get_plugin_dialog_class(self, plugin: Plugin) -> Optional[Any]:
        """
        Get the dialog class from a plugin module.

        First loads the plugin module if not already loaded, then retrieves
        the specified class. Returns None if the class cannot be found.

        Args:
            plugin: The Plugin object

        Returns:
            The dialog class if found, None otherwise
        """
        if plugin.dialog_class:
            return plugin.dialog_class

        if not plugin.module:
            if not self.load_plugin_module(plugin):
                return None

        try:
            dialog_class = getattr(plugin.module, plugin.dialog_class_name)
            plugin.dialog_class = dialog_class
            logger.info(
                f"Successfully loaded dialog class {plugin.dialog_class_name} "
                f"from {plugin.module_name}"
            )
            return dialog_class
        except AttributeError:
            logger.error(
                f"Dialog class {plugin.dialog_class_name} not found in "
                f"module {plugin.module_name}"
            )
            return None
        except Exception as e:
            logger.error(
                f"Failed to get dialog class {plugin.dialog_class_name} from "
                f"module {plugin.module_name}: {e}",
                exc_info=True
            )
            return None

    def get_updater_function(
        self, plugin: Plugin, timeout_sec: float = 5.0
    ) -> Optional[callable]:
        """
        Get the get_update_count function from a plugin's updater module.

        Returns a wrapper that calls the function with a timeout to prevent
        hanging if a plugin's update check is slow or broken.

        Args:
            plugin: The Plugin object
            timeout_sec: Maximum time (seconds) to wait for the function

        Returns:
            A callable that returns the update count, or None if not found
        """
        if not plugin.updater_module_name:
            return None

        try:
            logger.debug(
                f"Loading updater module: {plugin.updater_module_name}"
            )
            updater_module = importlib.import_module(plugin.updater_module_name)
            if not hasattr(updater_module, 'get_update_count'):
                logger.error(
                    f"Updater module {plugin.updater_module_name} missing "
                    f"get_update_count function"
                )
                return None

            func = getattr(updater_module, 'get_update_count')
            if not callable(func):
                logger.error(
                    f"Updater module {plugin.updater_module_name} has non-callable "
                    f"get_update_count"
                )
                return None
            logger.info(
                f"Successfully loaded get_update_count from "
                f"{plugin.updater_module_name}"
            )

            # Return a wrapper with timeout support
            def call_with_timeout():
                """Call the plugin's get_update_count with a timeout."""
                import threading
                result = {'count': 0, 'error': False}

                def target():
                    try:
                        count = func()
                        if isinstance(count, bool) or not isinstance(count, int):
                            logger.warning(
                                "Plugin %s returned non-int update count from %s: %r",
                                plugin.name, plugin.updater_module_name, count
                            )
                            result['error'] = True
                            return
                        result['count'] = count
                    except Exception as e:
                        logger.error(
                            f"Error calling get_update_count from "
                            f"{plugin.updater_module_name}: {e}",
                            exc_info=True
                        )
                        result['error'] = True

                thread = threading.Thread(target=target, daemon=True)
                thread.start()
                thread.join(timeout=timeout_sec)

                if thread.is_alive():
                    logger.warning(
                        f"Plugin {plugin.name} update check timed out after "
                        f"{timeout_sec}s"
                    )
                    result['count'] = 0

                return result['count'] if not result['error'] else 0

            return call_with_timeout

        except ImportError as e:
            logger.error(
                f"Failed to import updater module {plugin.updater_module_name}: {e}",
                exc_info=True
            )
            return None
        except Exception as e:
            logger.error(
                f"Unexpected error loading updater function from "
                f"{plugin.updater_module_name}: {e}",
                exc_info=True
            )
            return None

    def get_total_plugin_updates(self, timeout_sec: float = 5.0) -> Dict[str, int]:
        """
        Get update counts from all plugins with updater_module.

        Calls get_update_count() on each plugin's updater module. Each call
        is wrapped with a timeout to prevent blocking.

        Args:
            timeout_sec: Maximum time (seconds) per plugin call

        Returns:
            Dictionary mapping plugin name to update count. Only includes
            plugins that have an updater_module.
        """
        updates = {}
        updates_lock = threading.Lock()
        workers = []

        def collect_update_count(plugin: Plugin, updater_func):
            try:
                count = updater_func()
                with updates_lock:
                    updates[plugin.name] = count
                logger.debug(f"Plugin {plugin.name}: {count} updates")
            except Exception as e:
                logger.error(
                    f"Failed to get updates from plugin {plugin.name}: {e}",
                    exc_info=True
                )
                with updates_lock:
                    updates[plugin.name] = 0

        for plugin in self.get_plugins_for_updater():
            func = self.get_updater_function(plugin, timeout_sec)
            if not func:
                continue
            worker = threading.Thread(
                target=collect_update_count,
                args=(plugin, func),
                daemon=True
            )
            workers.append(worker)
            worker.start()

        for worker in workers:
            worker.join(timeout=timeout_sec + 0.5)
            if worker.is_alive():
                logger.warning(
                    "Plugin update collector worker exceeded timeout budget "
                    "(timeout=%ss)",
                    timeout_sec
                )

        return updates

    def reset(self):
        """Clear all loaded plugins and cached modules."""
        self._plugins = []
        self._loaded_modules = {}
        logger.debug("Plugin loader reset")
