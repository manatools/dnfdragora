# dnfdragora Plugin System

## Overview

The dnfdragora plugin system allows third-party applications to integrate with dnfdragora and dnfdragora-updater. Plugins can provide custom UI dialogs in dnfdragora and expose update counts to the system updater.

## Plugin Discovery

Plugins are discovered from the following directories (in order):
- `/usr/share/dnfdragora/plugins/`
- `/usr/local/share/dnfdragora/plugins/`
- `~/.local/share/dnfdragora/plugins/`

Each plugin must be defined by a configuration file with one of these extensions:
- `.plugin`
- `.ini`
- `.cfg`

## Plugin Configuration File Format

Create a plugin configuration file in INI format with the following structure:

```ini
[plugin]
name = MyPlugin
module = mypackage.dnfdragora_plugin
dialog_class = MyPluginDialog
updater_module = mypackage.updater
updater_function=get_update_count
```

### Required Fields

- **name**: Display name shown in the dnfdragora "Extra" menu
- **module**: Fully qualified Python module name containing the dialog class
- **dialog_class**: Name of the class to instantiate as the UI dialog

### Optional Fields

- **updater_module**: Module name that exposes a `get_update_count()` function for dnfdragora-updater

## Creating a Dialog Class

The dialog class must have a `run()` method that displays the UI and returns when the user closes the dialog.

### Example: Simple Dialog

```python
# mypackage/dnfdragora_plugin.py
import manatools.aui.yui as MUI

class MyPluginDialog:
    """A simple plugin dialog for dnfdragora."""

    def __init__(self):
        """Initialize the dialog."""
        self.factory = MUI.YUI_ui().widgetFactory()
        self.dialog = None

    def run(self):
        """Display and run the dialog."""
        # Create the main dialog window
        self.dialog = self.factory.createMainDialog()

        # Create widgets
        layout = self.factory.createVBox(self.dialog)
        self.factory.createLabel(layout, "Hello from My Plugin!")
        
        button = self.factory.createPushButton(layout, "Close")

        # Show dialog
        self.dialog.show()

        # Event loop
        while True:
            event = self.dialog.waitForEvent()
            if event is None or event.widget() == button:
                break

        self.dialog.destroy()
```

## Creating an Updater Module

If your plugin provides updates, create an updater module with a `get_update_count()` function:

```python
# mypackage/updater.py
def get_update_count():
    """
    Return the number of available updates for this plugin.

    This function is called by dnfdragora-updater periodically.
    It should return quickly (< 5 seconds) or be wrapped with timeout.

    Returns:
        int: Number of available updates (0 or more)
    """
    # Example: check for updates from your package repository
    available_updates = check_your_updates()
    return len(available_updates)
```

### Guidelines for `get_update_count()`

1. **Performance**: The function should complete within 5 seconds. It runs in a background thread with a timeout, so network operations are acceptable, but avoid blocking I/O.

2. **Error Handling**: Return 0 if any error occurs (the function is wrapped with exception handling).

3. **Return Type**: Always return an integer ≥ 0.

## Testing Your Plugin

### 1. Create Test Plugin Structure
```bash
mkdir -p ~/.local/share/dnfdragora/plugins
cat > ~/.local/share/dnfdragora/plugins/test-plugin.plugin << 'EOF'
[plugin]
name = Test Plugin
module = test_plugin.dialog
dialog_class = TestDialog
updater_module = test_plugin.updater
EOF
```

### 2. Create Test Plugin Module
```bash
mkdir -p test_plugin

cat > test_plugin/__init__.py << 'EOF'
"""Test plugin module."""
EOF

cat > test_plugin/dialog.py << 'EOF'
import manatools.aui.yui as MUI
from gettext import gettext as _

class TestDialog:
    def __init__(self):
        self.factory = MUI.YUI_ui().widgetFactory()
        self.dialog = None

    def run(self):
        self.dialog = self.factory.createMainDialog()
        layout = self.factory.createVBox(self.dialog)
        self.factory.createLabel(layout, _("Test Plugin Dialog"))
        close_btn = self.factory.createPushButton(layout, _("Close"))
        
        self.dialog.show()
        while True:
            event = self.dialog.waitForEvent()
            if event is None or event.widget() == close_btn:
                break
        self.dialog.destroy()
EOF

cat > test_plugin/updater.py << 'EOF'
def get_update_count():
    """Return a test update count."""
    return 2
EOF
```

### 3. Run dnfdragora
```bash
export PYTHONPATH="$PYTHONPATH:$(pwd):$HOME/.local/share/dnfdragora"
dnfdragora
```

The "Extra" menu should now appear with your test plugin.

## Security Considerations

### Module Loading
- Plugins are loaded using Python's `importlib`, which requires the module to be on `sys.path`
- Never install plugins from untrusted sources
- Plugins have full access to your Python environment

### Update Count Calls
- Each `get_update_count()` call runs in its own thread with a 5-second timeout
- Broken plugins will not crash dnfdragora-updater

### Best Practices
1. **Sign your plugins** if distributing them
2. **Document dependencies** clearly
3. **Handle exceptions gracefully** in `get_update_count()`
4. **Test on multiple systems** before releasing
5. **Keep the AUI library version** consistent with dnfdragora's requirements

## Troubleshooting

### Plugin Not Showing in Menu
1. Check the configuration file format and location
2. Verify the `module` and `dialog_class` names
3. Check logs: enable logging and check `dnfdragora.log` and `dnfdragora-updater.log` in their related directory 
4. dnfdragora validates plugin modules and dialog classes during discovery:
   - module import must succeed
   - `dialog_class` must exist and be callable
   - class constructor must instantiate without errors
   - if `updater_module` is configured, it must be importable and export a callable `get_update_count()` with no required arguments
   Invalid plugins are skipped and logged with a warning.

### Dialog Crashes
1. Check the Python interpreter version (must match dnfdragora's)
2. Verify the Manatools.AUI library is installed and compatible
3. Test your dialog independently before integrating

### Updater Not Showing Plugin Updates
1. Ensure `updater_module` is specified in the configuration
2. Verify `get_update_count()` function exists and returns an integer
3. Check dnfdragora-updater logs for timeout warnings

### Plugin Timeout
If your `get_update_count()` takes longer than 5 seconds:
1. Use threading to perform long operations
2. Cache results to avoid repeated I/O
3. Consider moving heavy operations to background tasks

## API Reference

### PluginLoader Class
Located in `dnfdragora.plugin_loader`:

```python
class PluginLoader:
    def discover_plugins() -> List[Plugin]
        """Discover all available plugins."""

    def get_plugins_for_dnfdragora() -> List[Plugin]
        """Get plugins for the main UI menu."""

    def get_plugins_for_updater() -> List[Plugin]
        """Get plugins with updater_module defined."""

    def load_plugin_module(plugin: Plugin) -> bool
        """Load a plugin's Python module."""

    def get_plugin_dialog_class(plugin: Plugin) -> Optional[Any]
        """Get the dialog class from a plugin module."""

    def get_updater_function(plugin: Plugin) -> Optional[callable]
        """Get the update count function with timeout wrapper."""

    def get_total_plugin_updates(timeout_sec: float = 5.0) -> Dict[str, int]
        """Get update counts from all plugins."""
```

### Plugin Class
Located in `dnfdragora.plugin_loader`:

```python
@dataclass
class Plugin:
    name: str                      # Display name
    module_name: str               # Python module to import
    dialog_class_name: str         # Dialog class name
    updater_module_name: Optional[str]  # Updater module (optional)
    config_path: Path              # Path to config file
    module: Optional[Any] = None   # Loaded module (internal)
    dialog_class: Optional[Any] = None  # Loaded class (internal)
```

## Contributing Plugins

To contribute a plugin to the dnfdragora project:

1. **Create a repository** for your plugin
2. **Follow the naming convention**: `dnfdragora-plugin-<name>`
3. **Write documentation** similar to this guide
4. **Include unit tests** for `get_update_count()`
5. **Package and distribute** via your project's standard mechanism

## License

Plugins distributed with dnfdragora should comply with GPLv3 (or later) or compatible licenses.

## Support

For issues or questions about the plugin system:
- Check the dnfdragora GitHub repository: https://github.com/manatools/dnfdragora
- Open an issue with detailed information
- Include your plugin configuration and error logs
