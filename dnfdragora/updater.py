# vim: set fileencoding=utf-8 :
# vim: set et ts=4 sw=4:
'''
dnfdragora system tray updater — PySide6 / QSystemTrayIcon implementation.

License: GPLv3

Author:  Angelo Naselli <anaselli@linux.it>

Former author:  Björn Esser <besser82@fedoraproject.org>

@package dnfdragora
'''

import gettext, sched, signal, sys, threading, time, os
from dataclasses import dataclass
from typing import Optional

from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon, QMessageBox
from PySide6.QtGui     import QIcon
from PySide6.QtCore    import QCoreApplication, QEventLoop, QTimer

from dnfdragora import config, misc, ui, dnfd_client, plugin_loader

from queue import Queue, Empty

import logging
logger = logging.getLogger('dnfdragora.updater')


@dataclass
class UpdateProviderState:
    provider_id: str
    display_name: str
    include_in_extra_menu: bool
    icon_name: Optional[str] = None
    plugin: Optional[object] = None


class Updater:
    '''Updater class for managing system tray updates in dnfdragora.'''
    DNF_PROVIDER_ID = "__dnf_internal__"

    '''Reschedule interval in seconds, 
       after a conclusion of an operation, such as running dindfdragora or dnfddragora update.'''
    RESCHEDULE_INTERVAL_SEC = 5 # 5 seconds

    def __init__(self, options=None):
        if options is None:
            options = {}

        # ── Backend probe: must run before QApplication creation ─────────────
        # Determines whether MUI_BACKEND needs to be overridden to 'qt'.
        # Must come first so QApplication's own GLib/D-Bus integration does
        # not influence the probe's sys.modules check.
        Updater._probe_backend_for_process()

        # ── QApplication must be the very first Qt object ─────────────────────
        # setQuitOnLastWindowClosed(False) prevents QApplication from quitting
        # automatically when the dnfdragora dialog is closed (it is the last
        # window at that point); the updater must keep running.
        self._app = QApplication.instance() or QApplication(sys.argv)
        self._app.setQuitOnLastWindowClosed(False)

        # ── Initialize critical attributes upfront ────────────────────────────
        self.__main_gui            = None
        self.__running             = False
        self.__updater             = None
        self.__scheduler           = None
        self._tray                 = None
        self.__backend             = None
        self.__getUpdatesRequested = False
        self.__shutdown_requested  = False
        self.__repo_md_active_ids  = set()
        self.__repo_md_seen_ids    = set()
        self.__repo_md_followup_scheduled = False
        self.__suppress_context_menu_once = False
        # Set to True while a dnfdragora dialog is open so that __update_loop
        # stands down and __get_updates skips (backend session intentionally
        # closed during that window to free a D-Bus session slot).
        self.__dialog_open         = False
        # True from the moment updates are first confirmed until a check
        # confirms zero updates.  Used to keep the update icon stable.
        self.__has_updates         = False
        # Monotonically-increasing counter bumped by every __get_updates call.
        # The counter value is stamped on every ('no_updates', gen) message so
        # that __on_no_updates can detect and discard stale results (a stale
        # result has gen < self.__check_gen at the time the main thread
        # processes the message).
        self.__check_gen           = 0

        # ── Configuration ─────────────────────────────────────────────────────
        self.__config         = config.AppConfig('dnfdragora')
        self.__updateInterval = 180
        self.__update_count   = -1
        self.__log_enabled    = False
        self.__log_directory  = None
        self.__level_debug    = False
        self.__hide_menu      = True
        self.__plugin_loader  = plugin_loader.PluginLoader()
        self.__plugin_updates = {}  # Cache for plugin update counts
        self.__plugin_updates_lock = threading.Lock()
        self.__update_provider_states = {}
        self.__update_provider_counts = {}
        self.__update_provider_lock = threading.Lock()
        self.__dnf_provider_enabled = options.get('enable-dnf-provider', True)

        if self.__config.userPreferences:
            if 'settings' in self.__config.userPreferences.keys():
                settings = self.__config.userPreferences['settings']
                if 'interval for checking updates' in settings.keys():
                    self.__updateInterval = int(settings['interval for checking updates'])
                self.__hide_menu = settings.get('hide_update_menu', False)
                if 'log' in settings.keys():
                    log = settings['log']
                    if 'enabled' in log.keys():
                        self.__log_enabled = log['enabled']
                    if self.__log_enabled:
                        self.__log_directory = log.get('directory',    None)
                        self.__level_debug   = log.get('level_debug', False)

        if self.__log_enabled and self.__log_directory:
            log_filename = os.path.join(self.__log_directory, "dnfdragora-updater.log")
            if self.__level_debug:
                misc.logger_setup(log_filename, loglvl=logging.DEBUG)
            else:
                misc.logger_setup(log_filename)
            print("Logging into %s, debug mode is %s" % (
                self.__log_directory,
                "enabled" if self.__level_debug else "disabled"))
            logger.info("dnfdragora-updater started")
        else:
            print("Logging disabled")

        # ── Icons ─────────────────────────────────────────────────────────────
        icon_dir = options.get('icon-path')
        self._icon        = self.__load_qicon('dnfdragora',               icon_dir)

        # ── System tray ───────────────────────────────────────────────────────
        self._tray = QSystemTrayIcon(self._icon, self._app)
        self._tray.setToolTip('dnfdragora-updater')

        self._tray_menu = QMenu()
        self._tray_update_action = None
        self._tray_open_action = None
        if self.__dnf_provider_enabled:
            self._tray_update_action = self._tray_menu.addAction(_('Update'), self.__run_update)
            self._tray_open_action = self._tray_menu.addAction(
                _('Open dnfdragora dialog'), self.__run_dnfdragora
            )
            self.__refresh_dnf_action_presentation()
        self._tray_menu.addAction(_('Check for updates'),      self.__check_updates)
        
        # Plugin menu (Extra) - populated dynamically before Exit.
        self._plugin_menu = None
        self._plugin_menu_actions = {}
        self._plugin_menu_top_separator = None
        self._plugin_menu_bottom_separator = None
        self._tray_exit_action = self._tray_menu.addAction(_('Exit'), self.__shutdown)
        
        self._tray_menu.aboutToShow.connect(self.__on_tray_menu_about_to_show)
        self._tray.setContextMenu(self._tray_menu)
        self._tray.activated.connect(self.__on_tray_activated)

        # ── Cross-thread GUI queue ────────────────────────────────────────────
        # The background update-loop thread puts commands here; a QTimer on the
        # main thread drains them.  This avoids any direct Qt GUI calls from a
        # non-main thread (which is undefined behaviour in Qt).
        #
        # Commands: ('updates_found', n) | ('no_updates',) | ('check_failed', msg)
        self._gui_queue = Queue()
        self._poll_timer = QTimer()
        self._poll_timer.setInterval(100)          # drain every 100 ms
        self._poll_timer.timeout.connect(self.__process_gui_queue)
        self._poll_timer.start()

        # ── D-Bus backend ─────────────────────────────────────────────────────
        if self.__dnf_provider_enabled:
            try:
                self.__backend = dnfd_client.Client()
            except Exception as e:
                logger.error('Error connecting to dnfdaemon service: [%s]' % str(e))
                msg = QMessageBox()
                msg.setIcon(QMessageBox.Icon.Critical)
                msg.setText(_("Error connecting to dnfdaemon service.\nPlease check that dnfdaemon is installed and running and try again."))
                msg.setInformativeText(str(e))
                msg.setWindowTitle(_("dnfdragora-updater failure"))
                msg.exec()
                return
        else:
            self.__backend = None
            logger.info("DNF update provider disabled; updater will use external providers only")

        # ── Update-loop thread ────────────────────────────────────────────────
        self.__running   = True
        self.__updater   = threading.Thread(target=self.__update_loop, daemon=True)
        self.__scheduler = sched.scheduler(time.time, time.sleep)
        self.__getUpdatesRequested = False

    # ── Icon loading ─────────────────────────────────────────────────────────

    @staticmethod
    def _probe_backend_for_process():
        '''
        Determine the safe manatools.aui backend for dialogs opened inside
        this process and set MUI_BACKEND accordingly — without importing GTK.

        IMPORTANT: this method must never call _detect_backend() or import
        anything from gi.repository.  Those probes execute
        "from gi.repository import Gtk" which registers all GLib/GObject
        boxed types into the process.  When QApplication is subsequently
        created, Qt's own GLib integration tries to register the same types
        a second time, producing:
          • g_boxed_type_register_static: assertion '…' failed
          • cannot register existing type 'GtkWidget'
          • QColor::fromRgbF: Alpha parameter out of range   (platform theme)
          • etc.
        The probe therefore uses only environment variables and
        importlib.util.find_spec (which locates packages without executing
        their code).

        Decision tree
        -------------
        1. MUI_BACKEND already set by the user/environment → no-op.
        2. No desktop session (XDG_CURRENT_DESKTOP unset) → NCurses would be
           the natural choice; no GTK conflict possible → no-op.
        3. Qt-preferred desktop (KDE, LXQt, …) → Qt is already natural → no-op.
        4. GTK-preferred desktop (GNOME, XFCE, LXDE, …):
           a. PySide6 already in sys.modules → loading GTK4 later would clash;
              override to MUI_BACKEND=qt.
           b. PySide6 not yet loaded AND gi/python-gobject not installed →
              GTK4 is unavailable anyway; override to MUI_BACKEND=qt.
           c. PySide6 not yet loaded AND gi is present → GTK4 is safe to use;
              leave MUI_BACKEND unset.
        '''
        import importlib.util

        if os.environ.get('MUI_BACKEND'):
            logger.debug("MUI_BACKEND already set to '%s' — probe skipped",
                         os.environ['MUI_BACKEND'])
            return

        xdg = os.environ.get('XDG_CURRENT_DESKTOP', '')
        if not xdg:
            # No desktop session → NCurses path; no Qt/GTK conflict.
            logger.debug("Backend probe: no XDG_CURRENT_DESKTOP — no override")
            return

        _GTK_DESKTOPS = {
            'GNOME', 'XFCE', 'MATE', 'LXDE', 'CINNAMON',
            'PANTHEON', 'UNITY', 'ENLIGHTENMENT', 'SUGAR',
        }
        desktops = {d.strip().upper() for d in xdg.split(':')}

        if not (desktops & _GTK_DESKTOPS):
            # Qt-preferred desktop → Qt is already the natural choice.
            logger.debug("Backend probe: Qt-preferred desktop (%s) — no override",
                         ', '.join(sorted(desktops)))
            return

        # GTK-preferred desktop ─────────────────────────────────────────────
        matched = ', '.join(sorted(desktops & _GTK_DESKTOPS))

        if any(k.startswith('PySide6') for k in sys.modules):
            # PySide6 is already imported (always the case in this process
            # because updater.py imports PySide6 at module level).  Loading
            # GTK4 after Qt's GLib initialisation would cause type conflicts.
            logger.warning(
                "Backend probe: GTK desktop (%s) detected but PySide6 is "
                "already imported — overriding MUI_BACKEND=qt to avoid "
                "GLib type-registration conflicts", matched
            )
            os.environ['MUI_BACKEND'] = 'qt'
            return

        # PySide6 not yet loaded: check gi availability without importing it.
        # Check sys.modules first (already loaded → definitely available);
        # fall back to find_spec for the not-yet-loaded case.
        # find_spec can raise ValueError if a stale mock is in sys.modules, so
        # guard with try/except.
        try:
            gi_available = ('gi' in sys.modules) or (
                importlib.util.find_spec('gi') is not None
            )
        except (ValueError, AttributeError):
            gi_available = 'gi' in sys.modules

        if not gi_available:
            logger.warning(
                "Backend probe: GTK desktop (%s) but python-gobject (gi) "
                "is not installed — overriding MUI_BACKEND=qt", matched
            )
            os.environ['MUI_BACKEND'] = 'qt'
            return

        # gi is available and PySide6 is not active → GTK4 is safe.
        logger.debug(
            "Backend probe: GTK desktop (%s), gi available, PySide6 not "
            "active — MUI_BACKEND left unset (GTK)", matched
        )

    def __load_qicon(self, name, icon_dir=None):
        '''
        Return a QIcon for *name*.  Search order:
          1. File from --icon-path directory (svg/png)
          2. Qt icon theme (QIcon.fromTheme — covers XDG/hicolor automatically)
          3. hicolor theme directories (manual fallback)
          4. /usr/share/pixmaps
          5. Empty QIcon (updater still starts; icon will be invisible)
        '''
        # 1. Explicit --icon-path directory
        if icon_dir:
            d = icon_dir if icon_dir.endswith('/') else icon_dir + '/'
            for ext in ('svg', 'png'):
                candidate = d + name + '.' + ext
                if os.path.exists(candidate):
                    icon = QIcon(candidate)
                    if not icon.isNull():
                        logger.debug("Icon '%s' loaded from --icon-path: %s", name, candidate)
                        return icon

        # 2. Qt icon theme
        icon = QIcon.fromTheme(name)
        if not icon.isNull():
            logger.debug("Icon '%s' loaded from Qt theme", name)
            return icon

        # 3. hicolor (manual)
        for size in ('256x256', '128x128', '64x64', '48x48', '32x32'):
            for ext in ('png', 'svg', 'xpm'):
                candidate = '/usr/share/icons/hicolor/%s/apps/%s.%s' % (size, name, ext)
                if os.path.exists(candidate):
                    icon = QIcon(candidate)
                    if not icon.isNull():
                        logger.debug("Icon '%s' loaded from hicolor: %s", name, candidate)
                        return icon

        # 4. pixmaps
        for ext in ('png', 'svg', 'xpm'):
            candidate = '/usr/share/pixmaps/%s.%s' % (name, ext)
            if os.path.exists(candidate):
                icon = QIcon(candidate)
                if not icon.isNull():
                    logger.debug("Icon '%s' loaded from pixmaps: %s", name, candidate)
                    return icon

        logger.warning("No icon found for '%s' in any search path; "
                       "tray icon may be invisible", name)
        return QIcon()

    # ── Tray state helpers (main-thread only) ────────────────────────────────

    def __set_tray_icon(self, icon_name, reason=''):
        '''Set the tray icon and log every change.'''
        logger.info("Tray icon → %s%s", icon_name, ' [%s]' % reason if reason else '')
        self._tray.setIcon(self.__load_qicon(icon_name))

    def __set_tray_visible(self, visible, reason=''):
        '''Show or hide the tray icon.  Log every change; skip no-op calls.'''
        current = self._tray.isVisible()
        if current == visible:
            logger.debug("Tray already %s — skipped%s",
                         'visible' if visible else 'hidden',
                         ' [%s]' % reason if reason else '')
            return
        logger.info("Tray %s%s",
                    'shown' if visible else 'hidden',
                    ' [%s]' % reason if reason else '')
        if visible:
            self._tray.show()
        else:
            self._tray.hide()

    # ── Cross-thread GUI queue processing (main thread, every 100 ms) ────────

    def __process_gui_queue(self):
        '''Drain the cross-thread GUI command queue in the main thread.'''
        try:
            while True:
                try:
                    cmd, *args = self._gui_queue.get_nowait()
                except Empty:
                    break
                if cmd == 'updates_found':
                    # args = (count, gen)
                    self.__on_updates_found(args[0], args[1] if len(args) > 1 else None)
                elif cmd == 'no_updates':
                    # args = (gen,)
                    self.__on_no_updates(args[0] if args else None)
                elif cmd == 'check_failed':
                    self.__on_check_failed(args[0])
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt received while processing GUI queue")
            self.__request_shutdown('keyboard interrupt')

    def __request_shutdown(self, reason=''):
        '''Request shutdown once, from any callback/signal path.'''
        if self.__shutdown_requested:
            return
        self.__shutdown_requested = True
        logger.info("Shutdown requested%s",
                    ' [%s]' % reason if reason else '')
        self.__running = False
        if self._poll_timer is not None:
            try:
                self._poll_timer.stop()
            except Exception:
                pass
        # Execute actual shutdown work in the Qt event loop thread.
        QTimer.singleShot(0, self.__shutdown)

    def __on_signal(self, signum, _frame):
        try:
            sig_name = signal.Signals(signum).name
        except Exception:
            sig_name = str(signum)
        logger.info("Received signal %s", sig_name)
        self.__request_shutdown('signal %s' % sig_name)

    def __refresh_update_providers(self, dnf_count=None):
        """
        Refresh all update providers (internal + external) in background phase.

        DNF is represented as a special internal provider. External plugins
        are represented as regular providers that can appear in the "Extra"
        menu. The menu consumes only cached provider state.
        """
        provider_states = {}
        provider_counts = {}
        plugin_updates = {}

        if self.__dnf_provider_enabled and dnf_count is not None:
            try:
                normalized_dnf_count = max(0, int(dnf_count))
            except (TypeError, ValueError):
                normalized_dnf_count = 0
            provider_states[self.DNF_PROVIDER_ID] = UpdateProviderState(
                provider_id=self.DNF_PROVIDER_ID,
                display_name='dnf',
                include_in_extra_menu=False,
                icon_name='dnfdragora',
            )
            provider_counts[self.DNF_PROVIDER_ID] = normalized_dnf_count

        try:
            self.__plugin_loader.discover_plugins()
            updater_plugins = self.__plugin_loader.get_plugins_for_updater()
            plugin_updates = self.__plugin_loader.get_total_plugin_updates(
                timeout_sec=5.0
            )
            for plugin in updater_plugins:
                provider_id = f"plugin::{plugin.name}"
                provider_states[provider_id] = UpdateProviderState(
                    provider_id=provider_id,
                    display_name=plugin.name,
                    include_in_extra_menu=True,
                    icon_name=plugin.icon_name,
                    plugin=plugin,
                )
                plugin_count = plugin_updates.get(plugin.name, 0)
                provider_counts[provider_id] = max(0, int(plugin_count))
            logger.debug("Update provider cache refreshed: %s", provider_counts)
        except Exception as e:
            logger.error(f"Error refreshing update providers: {e}", exc_info=True)

        with self.__plugin_updates_lock:
            self.__plugin_updates = dict(plugin_updates)
        with self.__update_provider_lock:
            self.__update_provider_states = provider_states
            self.__update_provider_counts = provider_counts

    def __get_update_providers_snapshot(self):
        with self.__update_provider_lock:
            return dict(self.__update_provider_states), dict(self.__update_provider_counts)

    def __get_plugin_updates_snapshot(self):
        with self.__plugin_updates_lock:
            return dict(self.__plugin_updates)

    @staticmethod
    def __format_provider_count_label(provider_name, count):
        return f"{provider_name} ({count})"

    def __refresh_dnf_action_presentation(self):
        if not self.__dnf_provider_enabled or self._tray_update_action is None:
            return

        provider_states, provider_counts = self.__get_update_providers_snapshot()
        dnf_state = provider_states.get(self.DNF_PROVIDER_ID)
        dnf_count = provider_counts.get(self.DNF_PROVIDER_ID, 0)
        if dnf_count > 0 and dnf_state is not None:
            label = self.__format_provider_count_label(_('Update'), dnf_count)
        else:
            label = _('Update')
        self._tray_update_action.setText(label)

        icon = self.__load_qicon('dnfdragora')
        self._tray_update_action.setIcon(icon)
        if self._tray_open_action is not None:
            self._tray_open_action.setIcon(icon)

    def __get_total_update_count(self):
        """
        Calculate total update count: DNF updates + plugin updates.

        Returns:
            Tuple of (total_count, dnf_count, plugin_counts_dict)
        """
        provider_states, provider_counts = self.__get_update_providers_snapshot()
        dnf_count = provider_counts.get(self.DNF_PROVIDER_ID, 0)
        plugin_counts = {}
        for provider_id, state in provider_states.items():
            if state.include_in_extra_menu:
                plugin_counts[state.display_name] = provider_counts.get(provider_id, 0)
        total_count = sum(provider_counts.values())
        return total_count, dnf_count, plugin_counts

    def __handle_check_result(self, dnf_update_count, gen=None):
        """
        Handle the result of an update check: DNF + plugin updates.

        This method is called after each update check (regardless of whether
        DNF has updates or not) to aggregate updates from both DNF and all
        plugin sources.

        Args:
            dnf_update_count: Number of DNF package updates available
            gen: Generation number for stale result detection

        Behavior:
        - Uses provider cache refreshed by background update-check phase
        - If DNF updates OR plugin updates exist: shows "updates found"
        - If neither exist: shows "no updates"
        """
        # Keep the DNF count tied to the callback payload that triggered this
        # GUI update. Relying on shared mutable state can race with newer
        # background checks and lead to inconsistent tray notifications.
        try:
            self.__update_count = max(0, int(dnf_update_count))
        except (TypeError, ValueError):
            logger.warning("Invalid dnf_update_count=%r, forcing to 0",
                           dnf_update_count)
            self.__update_count = 0
        if self.__dnf_provider_enabled:
            with self.__update_provider_lock:
                if self.DNF_PROVIDER_ID not in self.__update_provider_states:
                    self.__update_provider_states[self.DNF_PROVIDER_ID] = UpdateProviderState(
                        provider_id=self.DNF_PROVIDER_ID,
                        display_name='dnf',
                        include_in_extra_menu=False,
                        icon_name='dnfdragora',
                    )
                self.__update_provider_counts[self.DNF_PROVIDER_ID] = self.__update_count

        total_count, dnf_count, plugin_counts = self.__get_total_update_count()
        plugin_total = sum(plugin_counts.values())
        self.__refresh_dnf_action_presentation()

        logger.info("check_result: %d DNF update(s), %d plugin update(s), "
                    "total: %d [gen=%s current_gen=%d]",
                    dnf_count, plugin_total, total_count,
                    gen, self.__check_gen)

        # Determine if we have any updates (DNF or plugin)
        has_any_updates = total_count > 0

        if has_any_updates:
            self.__has_updates = True
            # Build detailed update message
            message_parts = []
            if dnf_count > 0:
                message_parts.append(self.__format_provider_count_label('dnf', dnf_count))
            for plugin_name, count in plugin_counts.items():
                if count > 0:
                    message_parts.append(self.__format_provider_count_label(plugin_name, count))

            if message_parts:
                message = ', '.join(message_parts)
            else:
                message = _('%d updates available') % total_count

            self.__set_tray_icon('system-software-update', 'updates found')
            self.__set_tray_visible(True, 'updates found')
            if QSystemTrayIcon.supportsMessages():
                # Some tray implementations can drop notifications when they are
                # emitted before the tray icon is visible. Ensure visibility first.
                self._tray.showMessage(
                    'dnfdragora-update',
                    message,
                    QSystemTrayIcon.MessageIcon.Information,
                    7000,
                )
            self._tray.setToolTip(_('%s - %d updates available.') % (
                'dnfdragora-updater', total_count
            ))
        else:
            # No updates from any source (DNF or plugins)
            self.__has_updates = False
            self.__set_tray_icon('dnfdragora', 'no updates')
            if self.__getUpdatesRequested and QSystemTrayIcon.supportsMessages():
                self._tray.showMessage(
                    'dnfdragora-update',
                    _('No updates available'),
                    QSystemTrayIcon.MessageIcon.Information,
                    7000,
                )
            self._tray.setToolTip('dnfdragora-updater')
            # Apply hide_menu setting only when there are NO updates
            if self.__hide_menu:
                self.__set_tray_visible(False, 'no updates, hide_menu')
            else:
                self.__set_tray_visible(True, 'no updates, always-visible')

        self.__getUpdatesRequested = False

    def __on_updates_found(self, n, gen=None):
        """
        Backend callback: DNF package updates found.

        Delegates to unified handler which also checks plugin updates.
        """
        logger.debug("Backend event: updates_found (n=%d, gen=%s)", n, gen)
        self.__handle_check_result(n, gen)

    def __on_no_updates(self, gen=None):
        """
        Backend callback: No DNF package updates found.

        CRITICAL FIX: Discard stale results, then check plugin updates anyway!
        Even if DNF has no updates, plugins might have updates.

        Args:
            gen: Generation number for stale result detection
        """
        # Discard stale results: if a newer check has already been initiated
        # (check_gen advanced), this result is from a previous cycle and must
        # not reset the update icon.
        if gen is not None and gen != self.__check_gen:
            logger.warning("Ignoring stale no_updates result "
                           "[gen=%d, current_gen=%d]", gen, self.__check_gen)
            return
        logger.debug("Backend event: no_updates (gen=%s, current_gen=%d)", gen, self.__check_gen)
        # Delegates to unified handler which checks plugin updates AND handles hide_menu
        self.__handle_check_result(0, gen)

    def __on_check_failed(self, error):
        logger.error("GetPackages error: %s", error)

    def __on_tray_menu_about_to_show(self):
        '''Update plugin menu before showing the tray context menu.
        
        Suppress one delayed context-menu popup after a left-click launch.
        Some tray implementations can deliver a late context-menu popup even
        when the action was initiated via left-click (Trigger). When that
        happens while opening the update dialog, hide this menu once.
        '''
        self.__populate_plugin_menu()
        self.__refresh_dnf_action_presentation()
        
        if not self.__suppress_context_menu_once:
            return
        self.__suppress_context_menu_once = False
        logger.debug("Suppressing delayed tray context menu after left-click")
        if self._tray_menu is not None:
            QTimer.singleShot(0, self._tray_menu.hide)

    def __on_tray_activated(self, reason):
        '''Handle tray icon activation in the Qt main thread.

        A single left-click starts the update flow only when updates are
        currently available. Right-click/context-menu behavior is unchanged.
        '''
        if reason != QSystemTrayIcon.ActivationReason.Trigger:
            return

        if not self.__dnf_provider_enabled:
            logger.debug("Tray left-click ignored: DNF provider is disabled")
            return

        if not self.__has_updates:
            logger.debug("Tray left-click ignored: no updates available")
            return

        logger.info("Tray left-click: updates available, opening update dialog")
        # Guard against a delayed context-menu popup generated by tray hosts.
        self.__suppress_context_menu_once = True
        QTimer.singleShot(0, self.__run_update)

    def __populate_plugin_menu(self):
        """
        Populate the Extra menu with available plugins that have updater modules.
        
        The menu is positioned BEFORE the Exit action with a separator.
        Menu structure:
            Update
            Open dnfdragora dialog
            Check for updates
            ───────────────── (separator)
            [Extra plugins submenu]  (only if plugins exist)
            ───────────────── (separator)
            Exit
        """
        # Remove old plugin menu and separators if they exist
        if self._plugin_menu is not None:
            self._tray_menu.removeAction(self._plugin_menu.menuAction())
            self._plugin_menu = None

        if self._plugin_menu_top_separator is not None:
            self._tray_menu.removeAction(self._plugin_menu_top_separator)
            self._plugin_menu_top_separator = None

        if self._plugin_menu_bottom_separator is not None:
            self._tray_menu.removeAction(self._plugin_menu_bottom_separator)
            self._plugin_menu_bottom_separator = None

        self._plugin_menu_actions.clear()
        
        try:
            provider_states, provider_counts = self.__get_update_providers_snapshot()
            extra_providers = [
                (provider_id, state)
                for provider_id, state in provider_states.items()
                if state.include_in_extra_menu and state.plugin is not None
            ]
            
            # Only create menu if we have plugins
            if extra_providers:
                # Create submenu with icon support
                self._plugin_menu = QMenu(_('Extra plugins'), self._tray_menu)
                
                # Add plugins to submenu with icons if available
                for provider_id, state in extra_providers:
                    plugin = state.plugin
                    # Try to load plugin icon from theme
                    icon = None
                    if state.icon_name:
                        icon = self.__load_plugin_icon(state.icon_name)
                    
                    # Create action with optional icon
                    if icon:
                        action = self._plugin_menu.addAction(icon, state.display_name)
                    else:
                        action = self._plugin_menu.addAction(state.display_name)
                    
                    self._plugin_menu_actions[action] = plugin
                    action.triggered.connect(lambda checked=False, p=plugin: self.__run_plugin_dialog(p))
                    
                    # Add update count info if available
                    update_count = provider_counts.get(provider_id, 0)
                    if update_count > 0:
                        action.setText(self.__format_provider_count_label(state.display_name, update_count))
                
                if self._tray_exit_action is not None:
                    # Keep plugin group visually isolated and always before Exit:
                    # [... Check updates] [sep] [Extra plugins] [sep] [Exit]
                    self._plugin_menu_top_separator = self._tray_menu.insertSeparator(self._tray_exit_action)
                    self._tray_menu.insertMenu(self._tray_exit_action, self._plugin_menu)
                    self._plugin_menu_bottom_separator = self._tray_menu.insertSeparator(self._tray_exit_action)
                else:
                    # Fallback should never happen, but keep behavior safe.
                    self._tray_menu.addSeparator()
                    self._tray_menu.addMenu(self._plugin_menu)
                    self._tray_menu.addSeparator()
                    self._tray_exit_action = self._tray_menu.addAction(_('Exit'), self.__shutdown)
                    
        except Exception as e:
            logger.error(f"Error populating plugin menu: {e}", exc_info=True)

    def __load_plugin_icon(self, icon_name: str) -> Optional[QIcon]:
        """
        Attempt to load a plugin icon from the system theme.
        
        Args:
            icon_name: Icon name (e.g., 'manapak')
            
        Returns:
            QIcon if found in theme, None otherwise
        """
        try:
            from PySide6.QtGui import QIcon
            if QIcon.hasThemeIcon(icon_name):
                icon = QIcon.fromTheme(icon_name)
                if not icon.isNull():
                    logger.debug(f"Loaded plugin icon from theme: {icon_name}")
                    return icon
            logger.debug(f"Plugin icon not found in theme: {icon_name}")
            return None
        except Exception as e:
            logger.debug(f"Failed to load plugin icon {icon_name}: {e}")
            return None

    def __run_plugin_dialog(self, plugin):
        """Launch a plugin dialog from the updater tray menu."""
        try:
            logger.info(f"Running plugin dialog: {plugin.name}")
            # Import the dialog class and instantiate it
            dialog_class = self.__plugin_loader.get_plugin_dialog_class(plugin)
            if dialog_class is None:
                logger.error(f"Could not load dialog class for plugin {plugin.name}")
                return
            
            # Instantiate and run the dialog
            dialog = dialog_class()
            dialog.run()
            
            # Refresh updates after plugin runs (might have made changes)
            QTimer.singleShot(1000, lambda: self.__get_updates())
        except Exception as e:
            logger.error(f"Error running plugin dialog {plugin.name}: {e}", exc_info=True)
            if QSystemTrayIcon.supportsMessages():
                self._tray.showMessage(
                    'dnfdragora-update',
                    _('Error running plugin: %s') % plugin.name,
                    QSystemTrayIcon.MessageIcon.Warning,
                    7000,
                )

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def __shutdown(self):
        logger.info("shutdown")
        if self.__main_gui:
            logger.warning("Cannot exit: dnfdragora is still %s",
                           "RUNNING" if self.__main_gui.running else "open (not running)")
            return
        self.__running = False
        if self.__updater is not None:
            self.__updater.join(timeout=5)
        if self.__scheduler is not None and not self.__scheduler.empty():
            for task in self.__scheduler.queue:
                try:
                    self.__scheduler.cancel(task)
                except Exception:
                    pass
        if self.__backend:
            self.__backend = None
        self._poll_timer.stop()
        if self._tray is not None:
            self.__set_tray_visible(False, 'shutdown')
        self._app.quit()

    # ── Backend helpers ───────────────────────────────────────────────────────

    def __reopen_backend(self):
        '''Try to reopen the D-Bus backend session up to 3 times.'''
        if not self.__backend:
            logger.debug("Backend reopen skipped: no backend client available")
            return not self.__dnf_provider_enabled
        for attempt in range(1, 4):
            try:
                self.__backend.reloadDaemon()
                if self.__backend.session_path:
                    logger.info("Backend session reopened (attempt %d): %s",
                                attempt, self.__backend.session_path)
                    return True
                else:
                    logger.warning("reloadDaemon attempt %d: session_path is None", attempt)
            except Exception:
                logger.warning("reloadDaemon attempt %d raised an exception",
                               attempt, exc_info=True)
            if attempt < 3:
                time.sleep(2)
        logger.error("Failed to reopen backend session after 3 attempts")
        return False

    def __reschedule_update_in(self, minutes=0, seconds=0):
        logger.debug("rescheduling")
        if not self.__scheduler.empty():
            logger.debug("Reset scheduler")
            for task in self.__scheduler.queue:
                try:
                    self.__scheduler.cancel(task)
                except Exception:
                    pass
        if self.__scheduler.empty():
            if minutes < 0 : minutes = 0
            if seconds < 0 : seconds = 0
            if minutes == 0 and seconds == 0:
                seconds = 1
            self.__scheduler.enter(minutes * 60 + seconds, 1, self.__get_updates)
            logger.info("Scheduled check for updates in %d minutes and %d seconds",
                        minutes,
                        seconds)
            return True
        return False

    # ── Dialog helpers ────────────────────────────────────────────────────────

    @staticmethod
    def __processEvents(seconds):
        '''
        Process Qt events for up to *seconds* seconds, yielding to the event
        loop in 50 ms slices.  This keeps the tray icon responsive during the
        short synchronisation waits inside __run_dialog.
        '''
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            QCoreApplication.processEvents(
                QEventLoop.ProcessEventsFlag.AllEvents, 50)
            remaining = deadline - time.monotonic()
            if remaining > 0.05:
                time.sleep(0.05)

    # ── Menu actions (main thread) ────────────────────────────────────────────

    def __run_dnfdragora(self):
        self.__run_dialog({})

    def __run_update(self):
        self.__run_dialog({'update_only': True})

    def __run_dialog(self, args):
        '''
        Open the dnfdragora dialog.

        This method runs entirely in the main Qt thread (it is invoked as a
        menu-action slot).  Qt widget creation and the handleevent() nested
        event loop are therefore on the correct thread.

        The background update loop is held back via __dialog_open so it does
        not try to use the D-Bus session while dnfdragora owns it.
        '''
        if not self.__dnf_provider_enabled:
            logger.info("Skipping dnfdragora dialog launch: DNF provider is disabled")
            return

        if self._tray is None or self.__main_gui is not None:
            if self.__main_gui:
                logger.warning("Cannot run dnfdragora: already running")
            else:
                logger.warning("Cannot run dnfdragora: tray not initialised")
            return

        if not self._tray.isVisible():
            logger.warning("Cannot run dnfdragora: tray icon is not visible")
            return

        # ── Step 1: pause the update loop ─────────────────────────────────────
        # Give the update loop up to 1 s to finish its current iteration and
        # notice __dialog_open = True.  processEvents keeps the tray responsive.
        self.__dialog_open = True
        # Discard any pending GUI commands that arrived before we paused the
        # update loop.  Without this flush, a stale ('no_updates', gen) sitting
        # in the queue could be drained by the poll timer during the 1-second
        # processEvents window and wrongly reset the update icon.
        flushed = 0
        while True:
            try:
                self._gui_queue.get_nowait()
                flushed += 1
            except Empty:
                break
        logger.debug("Dialog opening: update loop paused, "
                     "gui_queue flushed (%d item(s))", flushed)
        self.__processEvents(1.0)

        # ── Step 2: cancel pending scheduler tasks ────────────────────────────
        for task in list(self.__scheduler.queue):
            try:
                self.__scheduler.cancel(task)
            except Exception:
                pass
        logger.debug("Scheduler cleared before dialog open")

        # ── Step 3: close the updater D-Bus session ───────────────────────────
        # dnf5daemon limits concurrent sessions per user.  We must free our
        # slot BEFORE dnfdragora opens its own session.
        if self.__backend:
            try:
                self.__backend.unloadDaemon()
                logger.info("Updater backend session closed to free slot for dnfdragora")
            except Exception:
                logger.warning("unloadDaemon before dialog raised an exception",
                               exc_info=True)

        # ── Step 4: launch the dnfdragora dialog ──────────────────────────────
        try:
            self.__main_gui = ui.mainGui(args)
        except Exception as e:
            logger.error("Exception launching dnfdragora (args=%s): %s", args, e)
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Critical)
            msg.setText(_("Error launching dnfdragora dialog"))
            msg.setInformativeText(str(e))
            msg.setWindowTitle(_("Running dnfdragora failure"))
            msg.exec()

            self.__main_gui = None
            self.__reopen_backend()
            self.__dialog_open = False
            logger.debug("Update loop resumed after dialog launch failure")
            self.__set_tray_visible(not self.__hide_menu, 'dialog launch failure')
            self.__reschedule_update_in(seconds=Updater.RESCHEDULE_INTERVAL_SEC)
            return

        try:
            # handleevent() runs a nested Qt event loop (QApplication.processEvents
            # in a loop) and returns when the dialog is closed.
            self.__main_gui.handleevent()

            # Safety net: poll until loop_has_finished is set.
            logger.debug("Waiting for dnfdragora to finish")
            self.__processEvents(0.5)
            logger.info("dnfdragora dialog closed")

            # ── Step 5a: explicitly close dnfdragora's D-Bus session ──────────────
            # mainGui → DnfRootBackend → mainGui is a circular reference.  CPython's
            # ref-counting cannot collect it immediately on __main_gui = None.  Call
            # unloadDaemon() now so the eventual __del__ is a no-op.
            try:
                root_backend = getattr(self.__main_gui, '_root_backend', None)
                if root_backend is not None and root_backend.session_path:
                    root_backend.unloadDaemon()
                    logger.info("Explicitly closed dnfdragora D-Bus session")
                else:
                    logger.debug("dnfdragora _root_backend session already closed "
                                "(session=%s)",
                                root_backend.session_path if root_backend else 'N/A')
            except Exception:
                logger.warning("Could not explicitly close dnfdragora backend",
                            exc_info=True)

        except Exception as e:
            logger.error("Exception in dnfdragora dialog: %s", e, exc_info=True)
        finally:
            self.__main_gui = None

        # Reset the manatools YUI singleton so the next dialog open gets a
        # fresh widget-factory instance.  The dialog's Qt widgets are already
        # destroyed at this point; keeping a stale _instance would cause the
        # next mainGui() call to reuse a factory whose internal state may
        # reference closed/deleted objects.
        try:
            import manatools.aui.yui as _yui_mod
            _yui_mod.YUI._instance = None
            _yui_mod.YUI._backend  = None
            logger.debug("YUI singleton reset after dialog close")
        except Exception:
            logger.debug("YUI singleton reset skipped (module not loaded)")

        # ── Step 5b: brief pause, then reopen the updater session ─────────────
        self.__processEvents(1.0)
        self.__reopen_backend()

        # ── Step 6: resume the update loop ────────────────────────────────────
        self.__dialog_open = False
        logger.debug("Update loop resumed (session=%s)",
                     self.__backend.session_path if self.__backend else 'N/A')
        self.__set_tray_visible(not self.__hide_menu, 'dialog closed')
        done = self.__reschedule_update_in(seconds=Updater.RESCHEDULE_INTERVAL_SEC)
        logger.debug("Post-dialog update check scheduled: %s",
                     "yes" if done else "skipped")

    def __check_updates(self):
        logger.debug("Start checking for updates, by menu command")
        # Do not hide tray here.  On some desktop environments hiding the tray
        # icon from within the tray-menu action callback can terminate the app.
        # hide_update_menu is applied only when a check result confirms no
        # updates (see __handle_check_result / __on_no_updates flow).
        if self.__dialog_open:
            logger.info("Check for updates requested while dialog is open; "
                        "will check automatically after the dialog closes")
            self.__getUpdatesRequested = True
            return
        try:
            if not self.__getUpdatesRequested:
                self.__get_updates()
                self.__getUpdatesRequested = True
        except Exception as e:
            logger.error(_('Exception caught: [%s]') % str(e))

    # ── Update logic (background thread) ─────────────────────────────────────

    def __reset_repo_metadata_tracking(self):
        self.__repo_md_active_ids.clear()
        self.__repo_md_seen_ids.clear()
        self.__repo_md_followup_scheduled = False

    @staticmethod
    def __is_repo_metadata_download(info):
        download_id = str(info.get('download_id') or '')
        return download_id.startswith('repo:')

    def __handle_repo_metadata_download(self, event, info):
        if not self.__is_repo_metadata_download(info):
            return False

        session_path = self.__backend.session_path if self.__backend else None
        event_session = info.get('session_object_path')
        if session_path and event_session and event_session != session_path:
            logger.debug(
                "Ignoring repo metadata event from stale session %s (current=%s)",
                event_session, session_path,
            )
            return True

        download_id = str(info.get('download_id') or '')
        if event == 'OnDownloadStart':
            is_new = download_id not in self.__repo_md_seen_ids
            self.__repo_md_active_ids.add(download_id)
            self.__repo_md_seen_ids.add(download_id)
            if is_new and len(self.__repo_md_seen_ids) == 1:
                logger.info("Repository metadata refresh detected during update check")
            return True

        if event == 'OnDownloadProgress':
            return True

        if event == 'OnDownloadEnd':
            self.__repo_md_active_ids.discard(download_id)
            if (
                self.__repo_md_seen_ids
                and not self.__repo_md_active_ids
                and not self.__repo_md_followup_scheduled
                and self.__running
                and not self.__dialog_open
            ):
                self.__repo_md_followup_scheduled = True
                logger.info(
                    "Repository metadata refresh completed for %d repo(s); scheduling update recheck in %d seconds",
                    len(self.__repo_md_seen_ids),
                    Updater.RESCHEDULE_INTERVAL_SEC,
                )
                self.__reschedule_update_in(seconds=Updater.RESCHEDULE_INTERVAL_SEC)
            return True

        return False

    def __get_updates(self, *kwargs):
        if self.__dialog_open:
            logger.info("Skipping update check: dialog_open=%s session=%s",
                        self.__dialog_open,
                        self.__backend.session_path if self.__backend else None)
            return

        self.__reset_repo_metadata_tracking()

        # Each call gets a new generation number.  This number is stamped on
        # ('no_updates', gen) messages so the main thread can detect and
        # discard results that belong to an older check cycle.
        self.__check_gen += 1
        gen = self.__check_gen
        if not self.__dnf_provider_enabled:
            logger.debug("Starting provider-only update check (gen=%d)", gen)
            self.__refresh_update_providers(dnf_count=None)
            total_count, _, _ = self.__get_total_update_count()
            if total_count > 0:
                self._gui_queue.put(('updates_found', total_count, gen))
            else:
                self._gui_queue.put(('no_updates', gen))
            return

        session_path = self.__backend.session_path if self.__backend else None
        if session_path is None:
            logger.warning("Skipping DNF update fetch: backend session is unavailable")
            self.__refresh_update_providers(dnf_count=0)
            total_count, _, _ = self.__get_total_update_count()
            if total_count > 0:
                self._gui_queue.put(('updates_found', total_count, gen))
            else:
                self._gui_queue.put(('no_updates', gen))
            return

        logger.debug("Starting update check (gen=%d session=%s)",
                     gen, session_path)

        # Discard any stale events left over from a previous (possibly
        # cancelled) check.  Without this flush, the loop might read an old
        # empty GetPackages result and wrongly clear the update icon.
        stale = 0
        while True:
            try:
                self.__backend.eventQueue.get_nowait()
                stale += 1
            except Empty:
                break
        if stale:
            logger.debug("Discarded %d stale backend event(s) before fetching updates",
                         stale)

        logger.debug("Start getting updates (session=%s)", session_path)
        options = {
            "package_attrs": [
                "repo_id", "install_size", "download_size",
                "summary", "nevra", "group",
            ],
            "scope": "upgrades",
        }
        try:
            try:
                self.__backend.ResetSession(sync=True)
                logger.debug("ResetSession completed")
            except Exception as reset_err:
                logger.warning("ResetSession failed (%s), falling back to reloadDaemon",
                               reset_err)
                self.__backend.reloadDaemon()
                if not self.__backend.session_path:
                    logger.error("reloadDaemon did not restore session; "
                                 "skipping GetPackages")
                    return
            self.__backend.GetPackages(options, piped=False)
            logger.debug("Getting update packages")
        except Exception as e:
            logger.error(_('Exception caught: [%s]') % str(e))

    def __OnRepoMetaDataProgress(self, name, frac):
        if frac == 0.0 or frac == 1.0:
            logger.debug('OnRepoMetaDataProgress: %s', repr((name, frac)))

    def __update_loop(self):
        self.__get_updates()

        while self.__running:
            # While a dnfdragora dialog is open the backend session is
            # intentionally closed.  Stand down rather than using the backend.
            if self.__dialog_open:
                time.sleep(0.5)
                continue

            update_next     = self.__updateInterval
            add_to_schedule = False

            # Provider-only mode (DNF provider disabled) or temporarily
            # unavailable backend: no DNF event queue to drain here.
            if (not self.__dnf_provider_enabled) or self.__backend is None:
                if self.__scheduler.empty():
                    self.__scheduler.enter(update_next * 60, 1, self.__get_updates)
                    logger.info("Scheduled check for updates in %d minutes",
                                update_next)
                self.__scheduler.run(blocking=False)
                time.sleep(0.5)
                continue

            try:
                counter   = 0
                count_max = 1000
                while counter < count_max:
                    counter += 1
                    item  = self.__backend.eventQueue.get_nowait()
                    event = item['event']
                    info  = item['value']

                    if event == 'OnRepoMetaDataProgress':
                        self.__OnRepoMetaDataProgress(info['name'], info['frac'])

                    elif event in ('OnDownloadStart', 'OnDownloadProgress', 'OnDownloadEnd'):
                        if self.__handle_repo_metadata_download(event, info):
                            continue
                        logger.debug("Ignoring non-repo download event %s: %s", event, info)

                    elif event == 'GetPackages_fd' or event == 'GetPackages':
                        # Capture the generation number at read-time (update
                        # thread).  If __get_updates fires again and increments
                        # __check_gen before the main thread drains the queue,
                        # the main thread will see gen < __check_gen and
                        # correctly discard the no_updates result as stale.
                        gen = self.__check_gen
                        logger.debug("Got GetPackages event [gen=%d]", gen)
                        if not info['error']:
                            po_list = info['result']
                            self.__update_count = len(po_list)
                            self.__refresh_update_providers(self.__update_count)
                            if self.__update_count >= 1:
                                # Post to main thread via GUI queue
                                self._gui_queue.put(('updates_found',
                                                     self.__update_count, gen))
                            else:
                                self._gui_queue.put(('no_updates', gen))
                        else:
                            self.__refresh_update_providers(0)
                            self._gui_queue.put(('check_failed',
                                                 str(info['error'])))
                        add_to_schedule = True

                    else:
                        logger.warning("Unmanaged event %s: %s", event, info)

            except Empty:
                pass

            if add_to_schedule:
                self.__reschedule_update_in(minutes=update_next)
            elif self.__scheduler.empty():
                self.__scheduler.enter(update_next * 60, 1, self.__get_updates)
                logger.info("Scheduled check for updates in %d minutes",
                            update_next)

            self.__scheduler.run(blocking=False)
            time.sleep(0.5)

        logger.info("Update loop end")

    # ── Entry point ───────────────────────────────────────────────────────────

    def main(self):
        if not self.__running:
            logger.error("Updater not fully initialized; cannot start.")
            return

        if not QSystemTrayIcon.isSystemTrayAvailable():
            logger.warning("System tray is not available on this desktop")

        # Show the tray icon immediately if __hide_menu is False; otherwise
        # it will be shown by __on_updates_found when updates are found.
        if not self.__hide_menu:
            self.__set_tray_visible(True, 'startup')

        self.__updater.start()

        # Ensure Ctrl-C from console triggers a graceful shutdown path.
        # SIGTERM is also trapped for service managers.
        signal.signal(signal.SIGINT, self.__on_signal)
        signal.signal(signal.SIGTERM, self.__on_signal)

        rc = 0
        while True:
            try:
                rc = self._app.exec()
            except KeyboardInterrupt:
                logger.info("KeyboardInterrupt in Qt main loop")
                self.__request_shutdown('keyboard interrupt in main loop')
                rc = 130

            # Normal shutdown path:
            # - __shutdown() sets __running=False
            # - __request_shutdown() sets __shutdown_requested=True
            if self.__shutdown_requested or not self.__running:
                break

            # Some desktop tray implementations can terminate the Qt event
            # loop when the tray icon is hidden and no windows are visible.
            # Keep updater alive and continue background scheduling.
            tray_visible = self._tray.isVisible() if self._tray is not None else False
            logger.warning(
                "Qt main loop exited unexpectedly (rc=%s, hide_menu=%s, tray_visible=%s); restarting",
                rc, self.__hide_menu, tray_visible
            )
            time.sleep(0.2)
        sys.exit(rc)

