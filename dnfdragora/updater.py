# vim: set fileencoding=utf-8 :
# vim: set et ts=4 sw=4:
'''
dnfdragora system tray updater — PySide6 / QSystemTrayIcon implementation.

License: GPLv3

Author:  Angelo Naselli <anaselli@linux.it>

Former author:  Björn Esser <besser82@fedoraproject.org>

@package dnfdragora
'''

import gettext, sched, sys, threading, time, os

from dnfdragora import config, misc, dialogs, ui, dnfd_client

from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon
from PySide6.QtGui     import QIcon
from PySide6.QtCore    import QCoreApplication, QEventLoop, QTimer

from queue import Queue, Empty

import logging
logger = logging.getLogger('dnfdragora.updater')


class Updater:

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
        # Prefer the standard FreeDesktop theme icon; fall back to the
        # application-specific one if the theme does not provide it.
        self._icon_update = self.__load_qicon('software-update-available', icon_dir)
        if self._icon_update.isNull():
            logger.debug("Falling back to application-specific update icon")
            self._icon_update = self.__load_qicon('dnfdragora-update', icon_dir)

        # ── System tray ───────────────────────────────────────────────────────
        self._tray = QSystemTrayIcon(self._icon, self._app)
        self._tray.setToolTip('dnfdragora-updater')

        menu = QMenu()
        menu.addAction(_('Update'),                 self.__run_update)
        menu.addAction(_('Open dnfdragora dialog'), self.__run_dnfdragora)
        menu.addAction(_('Check for updates'),      self.__check_updates)
        menu.addSeparator()
        menu.addAction(_('Exit'),                   self.__shutdown)
        self._tray.setContextMenu(menu)

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
        try:
            self.__backend = dnfd_client.Client()
        except Exception as e:
            logger.error(_('Error starting dnfdaemon service: [%s]') % str(e))
            return

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

    def __set_tray_icon(self, icon, reason=''):
        '''Set the tray icon and log every change.'''
        name = 'update' if icon is self._icon_update else 'normal'
        logger.info("Tray icon → %s%s", name, ' [%s]' % reason if reason else '')
        self._tray.setIcon(icon)

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

    def __on_updates_found(self, n, gen=None):
        logger.info("updates_found: %d update(s) [gen=%s current_gen=%d]",
                    n, gen, self.__check_gen)
        self.__has_updates = True
        self.__set_tray_icon(self._icon_update, 'updates found')
        self.__set_tray_visible(True, 'updates found')
        if QSystemTrayIcon.supportsMessages():
            self._tray.showMessage(
                'dnfdragora-update',
                _('%d updates available.') % n,
                QSystemTrayIcon.MessageIcon.Information,
                7000,
            )
        self.__getUpdatesRequested = False

    def __on_no_updates(self, gen=None):
        # Discard stale results: if a newer check has already been initiated
        # (check_gen advanced), this result is from a previous cycle and must
        # not reset the update icon.
        if gen is not None and gen != self.__check_gen:
            logger.warning("Ignoring stale no_updates result "
                           "[gen=%d, current_gen=%d]", gen, self.__check_gen)
            return
        logger.info("no_updates [gen=%s current_gen=%d "
                    "was_updates=%s requested=%s]",
                    gen, self.__check_gen,
                    self.__has_updates, self.__getUpdatesRequested)
        self.__has_updates = False
        self.__set_tray_icon(self._icon, 'no updates')
        if self.__getUpdatesRequested and QSystemTrayIcon.supportsMessages():
            self._tray.showMessage(
                'dnfdragora-update',
                _('No updates available'),
                QSystemTrayIcon.MessageIcon.Information,
                7000,
            )
        self.__getUpdatesRequested = False
        if self.__hide_menu:
            self.__set_tray_visible(False, 'no updates, hide_menu')
        else:
            self.__set_tray_visible(True, 'no updates, always-visible')

    def __on_check_failed(self, error):
        logger.error("GetPackages error: %s", error)

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

    def __reschedule_update_in(self, minutes):
        logger.debug("rescheduling")
        if not self.__scheduler.empty():
            logger.debug("Reset scheduler")
            for task in self.__scheduler.queue:
                try:
                    self.__scheduler.cancel(task)
                except Exception:
                    pass
        if self.__scheduler.empty():
            self.__scheduler.enter(minutes * 60, 1, self.__get_updates)
            logger.info("Scheduled check for updates in %d %s",
                        minutes if minutes >= 1 else minutes * 60,
                        "minutes" if minutes >= 1 else "seconds")
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
        if self._tray is None or self.__main_gui is not None:
            if self.__main_gui:
                logger.warning("Cannot run dnfdragora: already running")
            else:
                logger.warning("Cannot run dnfdragora: tray not initialised")
            return

        if not self._tray.isVisible():
            logger.warning("Cannot run dnfdragora: tray icon is not visible")
            return

        if self.__hide_menu:
            self.__set_tray_visible(False, 'dialog opening, hide_menu')

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
            dialogs.warningMsgBox({'title': _("Running dnfdragora failure"),
                                   "text": str(e), "richtext": True})
            self.__main_gui = None
            self.__reopen_backend()
            self.__dialog_open = False
            logger.debug("Update loop resumed after dialog launch failure")
            self.__set_tray_visible(not self.__hide_menu, 'dialog launch failure')
            self.__reschedule_update_in(0.5)
            return

        # handleevent() runs a nested Qt event loop (QApplication.processEvents
        # in a loop) and returns when the dialog is closed.
        self.__main_gui.handleevent()

        # Safety net: poll until loop_has_finished is set.
        logger.debug("Waiting for dnfdragora to finish")
        while not self.__main_gui.loop_has_finished:
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
        done = self.__reschedule_update_in(0.5)
        logger.debug("Post-dialog update check scheduled: %s",
                     "yes" if done else "skipped")

    def __check_updates(self):
        logger.debug("Start checking for updates, by menu command")
        if self.__hide_menu:
            self.__set_tray_visible(False, 'check_updates, hide_menu')
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

    def __get_updates(self, *kwargs):
        session_path = self.__backend.session_path if self.__backend else None
        if self.__dialog_open or session_path is None:
            logger.info("Skipping update check: dialog_open=%s session=%s",
                        self.__dialog_open, session_path)
            return

        # Each call gets a new generation number.  This number is stamped on
        # ('no_updates', gen) messages so the main thread can detect and
        # discard results that belong to an older check cycle.
        self.__check_gen += 1
        logger.debug("Starting update check (gen=%d session=%s)",
                     self.__check_gen, session_path)

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
            self.__backend.GetPackages(options)
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

                    elif event == 'GetPackages':
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
                            if self.__update_count >= 1:
                                # Post to main thread via GUI queue
                                self._gui_queue.put(('updates_found',
                                                     self.__update_count, gen))
                            else:
                                self._gui_queue.put(('no_updates', gen))
                        else:
                            self._gui_queue.put(('check_failed',
                                                 str(info['error'])))
                        add_to_schedule = True

                    else:
                        logger.warning("Unmanaged event %s: %s", event, info)

            except Empty:
                pass

            if add_to_schedule:
                self.__reschedule_update_in(update_next)
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
        sys.exit(self._app.exec())

