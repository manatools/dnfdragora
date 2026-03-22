# vim: set fileencoding=utf-8 :
# vim: set et ts=4 sw=4:
'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Björn Esser <besser82@fedoraproject.org>

@package dnfdragora
'''

import gettext, sched, sys, threading, time, os

from PIL import Image
from dnfdragora import config, misc, dialogs, ui, dnfd_client

from pystray import Menu, MenuItem
from pystray import Icon as Tray
from queue import SimpleQueue, Empty

import logging
logger = logging.getLogger('dnfdragora.updater')


class DnfdragoraUpdaterTray(Tray):
    '''
    pystray.Icon subclass with auto-closing notifications
    '''
    notification_expire_timeout = 7  # in seconds

    def notify(self, *args, **kw):
        super().notify(*args, **kw)
        logger.debug('Scheduling notification expiration in {} seconds'.format(self.notification_expire_timeout))
        # XXX: is this thread-safe?
        threading.Timer(self.notification_expire_timeout, self.remove_notification).start()


class Updater:

    def __init__(self, options=None):
        if options is None:
            options = {}
        # Initialize critical attributes upfront so that __shutdown__ and
        # main() are safe even if construction exits early (e.g. backend error).
        self.__main_gui            = None
        self.__running             = False
        self.__updater             = None
        self.__scheduler           = None
        self.__tray                = None
        self.__backend             = None
        self.__getUpdatesRequested = False
        # Set to True while a dnfdragora dialog is open so that __update_loop
        # stands down and __get_updates skips (backend session is intentionally
        # closed during that window to free a D-Bus session slot).
        self.__dialog_open         = False

        self.__config         = config.AppConfig('dnfdragora')
        self.__updateInterval = 180
        self.__update_count = -1

        self.__log_enabled = False
        self.__log_directory = None
        self.__level_debug = False

        self.__hide_menu = True

        if self.__config.userPreferences:
            if 'settings' in self.__config.userPreferences.keys() :
                settings = self.__config.userPreferences['settings']
                if 'interval for checking updates' in settings.keys() :
                    self.__updateInterval = int(settings['interval for checking updates'])
                self.__hide_menu = settings['hide_update_menu'] if 'hide_update_menu' in settings.keys() \
                  else False

                #### Logging
                if 'log' in settings.keys():
                  log = settings['log']
                  if 'enabled' in log.keys() :
                    self.__log_enabled = log['enabled']
                  if self.__log_enabled:
                    if 'directory' in log.keys() :
                        self.__log_directory = log['directory']
                    if 'level_debug' in log.keys() :
                        self.__level_debug = log['level_debug']

        if self.__log_enabled:
          if self.__log_directory:
            log_filename = os.path.join(self.__log_directory, "dnfdragora-updater.log")
            if self.__level_debug:
              misc.logger_setup(log_filename, loglvl=logging.DEBUG)
            else:
              misc.logger_setup(log_filename)
            print("Logging into %s, debug mode is %s"%(self.__log_directory, ("enabled" if self.__level_debug else "disabled")))
            logger.info("dnfdragora-updater started")
        else:
           print("Logging disabled")

        # if missing gets the default icon from our folder (same as dnfdragora)
        # If no icon-path was explicitly supplied, rely entirely on the theme
        # search (__load_icon_image).  Only use the explicit path when the user
        # has passed --icon-path, ensuring forward-compatibility with distros
        # that install icons only through the theme.
        if 'icon-path' in options.keys():
            icon_path = options['icon-path']
            if not icon_path.endswith('/'):
                icon_path += '/'
            for ext in ('svg', 'png'):
                candidate = icon_path + 'dnfdragora.' + ext
                if os.path.exists(candidate):
                    icon_path = candidate
                    break
            logger.debug("Icon (from --icon-path): %s", icon_path)
            self.__icon = Image.Image()
            try:
                if icon_path.endswith('.svg'):
                    with open(icon_path, 'rb') as svg:
                        self.__icon = self.__svg_to_Image(svg.read())
                else:
                    self.__icon = Image.open(icon_path)
            except Exception:
                logger.warning("Cannot open icon from --icon-path: %s", icon_path, exc_info=True)
        else:
            self.__icon = self.__load_icon_image('dnfdragora')

        logger.debug("Normal icon loaded: %s", type(self.__icon))

        if 'icon-path' in options.keys():
            icon_path = options['icon-path']
            if not icon_path.endswith('/'):
                icon_path += '/'
            for ext in ('svg', 'png'):
                candidate = icon_path + 'dnfdragora-update.' + ext
                if os.path.exists(candidate):
                    icon_path = candidate
                    break
            logger.debug("Update icon (from --icon-path): %s", icon_path)
            self.__icon_update = Image.Image()
            try:
                if icon_path.endswith('.svg'):
                    with open(icon_path, 'rb') as svg:
                        self.__icon_update = self.__svg_to_Image(svg.read())
                else:
                    self.__icon_update = Image.open(icon_path)
            except Exception:
                logger.warning("Cannot open update icon from --icon-path: %s", icon_path, exc_info=True)
        else:
            self.__icon_update = self.__load_icon_image('dnfdragora-update')

        logger.debug("Update icon loaded: %s", type(self.__icon_update))


        try:
            self.__backend = dnfd_client.Client()
        except Exception as e:
            logger.error(_('Error starting dnfdaemon service: [%s]')%( str(e)))
            return

        self.__running   = True
        self.__updater   = threading.Thread(target=self.__update_loop)
        self.__updater.daemon = True  # don't prevent process exit on unexpected termination
        self.__scheduler = sched.scheduler(time.time, time.sleep)
        self.__getUpdatesRequested = False

        self.__menu  = Menu(
            MenuItem(_('Update'), self.__run_update),
            MenuItem(_('Open dnfdragora dialog'), self.__run_dnfdragora),
            MenuItem(_('Check for updates'), self.__check_updates),
            MenuItem(_('Exit'), self.__shutdown)
        )
        self.__name  = 'dnfdragora-updater'
        self.__tray  = DnfdragoraUpdaterTray(self.__name, icon=self.__icon, title=self.__name, menu=self.__menu)


    def __get_theme_icon_pathname(self, name='dnfdragora'):
      '''
        Return a filesystem path for the named icon, searching (in order):
          1. XDG icon theme via xdg.IconTheme (same lookup as Qt fromTheme)
          2. hicolor theme directories at common sizes
          3. /usr/share/pixmaps
        Returns None if nothing is found.
      '''
      # 1. XDG icon theme
      try:
          import xdg.IconTheme
          pathname = xdg.IconTheme.getIconPath(name, 256)
          if pathname and os.path.exists(pathname):
              return pathname
          logger.debug("xdg.IconTheme did not find '%s' (returned %s)", name, pathname)
      except ImportError:
          logger.warning("xdg.IconTheme is not available; falling back to manual icon search")
      except Exception:
          logger.warning("xdg.IconTheme lookup failed for '%s'", name, exc_info=True)

      # 2. hicolor theme at common sizes
      for size in ('256x256', '128x128', '64x64', '48x48', '32x32'):
          for ext in ('png', 'svg', 'xpm'):
              candidate = '/usr/share/icons/hicolor/%s/apps/%s.%s' % (size, name, ext)
              if os.path.exists(candidate):
                  logger.debug("Found icon via hicolor: %s", candidate)
                  return candidate

      # 3. /usr/share/pixmaps
      for ext in ('png', 'svg', 'xpm'):
          candidate = '/usr/share/pixmaps/%s.%s' % (name, ext)
          if os.path.exists(candidate):
              logger.debug("Found icon via pixmaps: %s", candidate)
              return candidate

      logger.warning("No icon found for '%s' in any search path", name)
      return None

    def __load_icon_image(self, name):
      '''
        Return a PIL.Image for the given icon name.
        Searches the theme (via __get_theme_icon_pathname) first, then the
        user-supplied or default icon-path, and finally falls back to an empty
        Image.Image() so that the updater always starts regardless of missing
        icon files.
      '''
      pathname = self.__get_theme_icon_pathname(name)
      if pathname:
          logger.debug("Loading icon '%s' from %s", name, pathname)
          try:
              if pathname.endswith('.svg'):
                  with open(pathname, 'rb') as svg:
                      return self.__svg_to_Image(svg.read())
              else:
                  return Image.open(pathname)
          except Exception:
              logger.warning("Failed to open theme icon '%s' at %s", name, pathname,
                             exc_info=True)

      logger.warning("Could not load icon '%s' from theme; using empty image", name)
      return Image.Image()

    def __svg_to_Image(self, svg_string):
      '''
        gets svg content and returns a PIL.Image object
      '''
      import cairosvg
      import io
      in_mem_file = io.BytesIO()
      cairosvg.svg2png(bytestring=svg_string, write_to=in_mem_file)
      return Image.open(io.BytesIO(in_mem_file.getvalue()))

    def __shutdown(self, *kwargs):
        logger.info("shutdown")
        if self.__main_gui :
          logger.warning("Cannot exit dnfdragora is not deleted %s"%("and RUNNING" if self.__main_gui.running else "but NOT RUNNING"))
          return
        try:
          self.__running = False
          if self.__updater is not None:
            self.__updater.join(timeout=5)
          try:
            if self.__backend:
              self.__backend = None
          except Exception:
            pass

        except Exception:
          pass

        finally:
            if self.__scheduler is not None and not self.__scheduler.empty():
                for task in self.__scheduler.queue:
                    try:
                        self.__scheduler.cancel(task)
                    except Exception:
                        pass

            if self.__tray is not None:
              self.__tray.stop()
            if self.__backend:
              self.__backend = None

    def __reopen_backend(self):
        '''
        Try to reopen the D-Bus backend session up to 3 times.
        Returns True on success, False if all attempts failed.
        '''
        for attempt in range(1, 4):
            try:
                self.__backend.reloadDaemon()
                if self.__backend.session_path:
                    logger.info("Backend session reopened (attempt %d): %s",
                                attempt, self.__backend.session_path)
                    return True
                else:
                    logger.warning("reloadDaemon attempt %d returned but session_path is None",
                                   attempt)
            except Exception:
                logger.warning("reloadDaemon attempt %d raised an exception", attempt,
                               exc_info=True)
            if attempt < 3:
                time.sleep(2)
        logger.error("Failed to reopen backend session after 3 attempts")
        return False

    def __reschedule_update_in(self, minutes):
      '''
      clean up scheduler and schedule update in 'minutes'
      '''
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
        logger.info("Scheduled check for updates in %d %s", minutes if minutes >= 1 else minutes*60, "minutes" if minutes >= 1 else "seconds" )
        return True

      return False

    def __run_dialog(self, args, *kwargs):
        if self.__tray != None and self.__main_gui == None and self.__tray.visible:
            if self.__hide_menu:
              self.__tray.visible = False
            time.sleep(0.5)

            # ── Step 1: pause the update loop ────────────────────────────────
            # Setting __dialog_open=True tells __update_loop to idle and tells
            # __get_updates to return early (no-op), so neither thread will
            # access self.__backend while we are manipulating its session.
            self.__dialog_open = True
            logger.debug("Dialog opening: update loop paused")

            # Give __update_loop time to finish its current 0.5-second iteration
            # before we touch the backend or the scheduler.
            time.sleep(1.0)

            # ── Step 2: cancel pending scheduler tasks ───────────────────────
            # Now that the loop is idle, no new tasks will be added concurrently.
            for task in list(self.__scheduler.queue):
                try:
                    self.__scheduler.cancel(task)
                except Exception:
                    pass
            logger.debug("Scheduler cleared before dialog open")

            # ── Step 3: close the updater D-Bus session ───────────────────────
            # dnf5daemon limits concurrent sessions per user.  We must free our
            # slot BEFORE dnfdragora opens its own session.
            if self.__backend:
                try:
                    self.__backend.unloadDaemon()
                    logger.info("Backend session closed to free slot for dnfdragora")
                except Exception:
                    logger.warning("unloadDaemon before dialog raised an exception",
                                   exc_info=True)

            # ── Step 4: launch the dnfdragora dialog ─────────────────────────
            try:
                self.__main_gui = ui.mainGui(args)
            except Exception as e:
                logger.error("Exception launching dnfdragora (args=%s): %s", args, e)
                dialogs.warningMsgBox({'title': _("Running dnfdragora failure"),
                                       "text": str(e), "richtext": True})
                self.__main_gui = None
                # Reopen backend and resume loop even on launch failure.
                self.__reopen_backend()
                self.__dialog_open = False
                logger.debug("Update loop resumed after dialog launch failure")
                self.__reschedule_update_in(0.5)
                return

            self.__main_gui.handleevent()

            logger.debug("Waiting for dnfdragora to finish")
            while self.__main_gui.loop_has_finished != True:
                time.sleep(1)
            logger.info("dnfdragora dialog closed")

            # ── Step 5a: explicitly close dnfdragora's D-Bus session ─────────
            # mainGui → DnfRootBackend → mainGui (parent) is a circular
            # reference, so CPython's reference counting cannot collect it
            # immediately when we set __main_gui = None.  The cyclic GC runs
            # non-deterministically and may leave dnfdragora's session open for
            # several seconds.  After N cycles, N leaked sessions accumulate and
            # the dnf5daemon limit is hit.
            #
            # Fix: call unloadDaemon() explicitly on the DnfRootBackend BEFORE
            # releasing the reference.  Because unloadDaemon() sets
            # session_path = None, the eventual __del__ call will be a no-op.
            try:
                root_backend = getattr(self.__main_gui, '_root_backend', None)
                if root_backend is not None and root_backend.session_path:
                    root_backend.unloadDaemon()
                    logger.info("Explicitly closed dnfdragora D-Bus session (session leaked prevention)")
                else:
                    logger.debug("dnfdragora _root_backend session already closed or not found "
                                 "(session=%s)",
                                 root_backend.session_path if root_backend else 'N/A')
            except Exception:
                logger.warning("Could not explicitly close dnfdragora backend", exc_info=True)

            self.__main_gui = None

            # Brief pause to let the daemon acknowledge the session close on
            # its side before we request a new slot.
            time.sleep(1)

            # ── Step 5b: reopen the updater session ──────────────────────────
            self.__reopen_backend()

            # ── Step 6: resume the update loop ───────────────────────────────
            self.__dialog_open = False
            logger.debug("Update loop resumed after dnfdragora closed (session=%s)",
                         self.__backend.session_path if self.__backend else 'N/A')

            done = self.__reschedule_update_in(0.5)
            logger.debug("Post-dialog update check scheduled: %s", "yes" if done else "skipped")
        else:
          if self.__main_gui:
            logger.warning("Cannot run dnfdragora because it is already running")
          else:
            logger.warning("Cannot run dnfdragora")

    def __run_dnfdragora(self, *kwargs):
        logger.debug("Menu visibility is %s", str(self.__tray.visible))
        return self.__run_dialog({})


    def __run_update(self, *kwargs):
        logger.debug("Menu visibility is %s", str(self.__tray.visible))
        return self.__run_dialog({'update_only': True})

    def __check_updates(self, *kwargs):
      '''
      Start get updates by simply locking the DB
      '''
      logger.debug("Start checking for updates, by menu command")
      if self.__hide_menu:
        self.__tray.visible = False
      if self.__dialog_open:
        logger.info("Check for updates requested while dialog is open; "
                    "will check automatically after the dialog closes")
        # Remember the user's request so we show a notification even if
        # 0 updates are found when the post-dialog check fires.
        self.__getUpdatesRequested = True
        return
      try:
        if not self.__getUpdatesRequested:
           self.__get_updates()
           self.__getUpdatesRequested = True
      except Exception as e:
        logger.error(_('Exception caught: [%s]')%(str(e)))

    def __get_updates(self, *kwargs):
      '''
      Start get updates by simply locking the DB
      '''
      # Guard: skip entirely if the dialog is open (backend session is
      # intentionally closed) or the backend session is not available.
      # This prevents __get_updates from trying to call ResetSession on a
      # closed session (which would trigger the reloadDaemon fallback and
      # consume a D-Bus session slot while dnfdragora is already using one).
      session_path = self.__backend.session_path if self.__backend else None
      if self.__dialog_open or session_path is None:
        logger.info("Skipping update check: dialog_open=%s session=%s",
                    self.__dialog_open, session_path)
        return

      logger.debug("Start getting updates (session=%s)", session_path)

      filter = "upgrades"
      options = {"package_attrs": [
        "repo_id",
        "install_size",
        "download_size",
        "summary",
        "nevra",
        "group",
        ],
        "scope": filter }
      try:
        # Reset the existing session state without tearing down the D-Bus
        # connection.  Cheaper than reloadDaemon() (close + reopen) and avoids
        # the risk of losing the connection if the daemon is slow to respond.
        try:
          self.__backend.ResetSession(sync=True)
          logger.debug("ResetSession completed")
        except Exception as reset_err:
          logger.warning("ResetSession failed (%s), falling back to reloadDaemon", reset_err)
          self.__backend.reloadDaemon()
          if not self.__backend.session_path:
            logger.error("reloadDaemon fallback did not restore the session; skipping GetPackages")
            return
        self.__backend.GetPackages(options)
        logger.debug("Getting update packages")
      except Exception as e:
        logger.error(_('Exception caught: [%s]')%(str(e)))

    def __OnRepoMetaDataProgress(self, name, frac):
      '''Repository Metadata Download progress.'''
      values = (name, frac)
      #print('on_RepoMetaDataProgress (root): %s', repr(values))
      if frac == 0.0 or frac == 1.0:
        logger.debug('OnRepoMetaDataProgress: %s', repr(values))

    def __update_loop(self):
      self.__get_updates()

      while self.__running == True:
        # While a dnfdragora dialog is open the backend session is intentionally
        # closed.  Idle here rather than attempting to use the backend or adding
        # new scheduler entries that would fire on the closed session.
        if self.__dialog_open:
          time.sleep(0.5)
          continue

        update_next = self.__updateInterval
        add_to_schedule = False
        try:
          counter = 0
          count_max = 1000

          #if dnfdragora is running we receive transaction/rpm progress/download etc events
          #let's dequeue them as quick as possible
          while counter < count_max:
            counter = counter + 1

            item = self.__backend.eventQueue.get_nowait()
            event = item['event']
            info = item['value']

            if (event == 'OnRepoMetaDataProgress'):
              #let's log metadata since slows down the Lock requests
              self.__OnRepoMetaDataProgress(info['name'], info['frac'])
            elif (event == 'GetPackages'):
              logger.debug("Got GetPackages event menu visibility is %s", str(self.__tray.visible))
              #if not self.__tray.visible :
              # ugly workaround to show icon if hidden, set empty icon and show it
              self.__tray.icon = Image.Image()
              self.__tray.visible = True
              logger.debug("Event received %s", event)
              if not info['error']:
                po_list = info['result']
                self.__update_count = len(po_list)
                logger.info("Found %d updates"%(self.__update_count))

                if (self.__update_count >= 1):
                  self.__tray.icon = self.__icon_update
                  self.__tray.visible = True
                  self.__tray.notify(title='dnfdragora-update', message=_('%d updates available.') % self.__update_count)
                elif self.__getUpdatesRequested :
                  # __update_count == 0 but get updates has been requested by user command
                  # Let's give a feed back anyway
                  logger.debug("No updates found after user request")
                  self.__tray.icon = self.__icon
                  self.__tray.notify(title='dnfdragora-update', message=_('No updates available'))
                  self.__tray.visible = not self.__hide_menu
                else:
                  self.__tray.icon = self.__icon
                  self.__tray.visible = not self.__hide_menu
                  logger.debug("No updates found")
                self.__getUpdatesRequested = False
                logger.debug("Menu visibility is %s", str(self.__tray.visible))
              else:
                # error
                logger.error("GetPackages error %s", str(info['error']))
              #force scheduling again
              add_to_schedule = True
              # Session is kept open; no unloadDaemon() here.
            #elif (event == xxx)
            else:
              logger.warning("Unmanaged event received %s - info %s", event, str(info))

        except Empty:
          pass

        if add_to_schedule:
          self.__reschedule_update_in(update_next)
        elif self.__scheduler.empty():
          # if the scheduler is empty we schedule a check according
          # to configuration file anyway
          self.__scheduler.enter(update_next * 60, 1, self.__get_updates)
          logger.info("Scheduled check for updates in %d minutes", update_next)
        self.__scheduler.run(blocking=False)
        time.sleep(0.5)

      logger.info("Update loop end")


    def __main_loop(self):
        def setup(tray) :
            # False to start without icon
            tray.visible = True

        self.__updater.start()
        time.sleep(1)
        self.__tray.run(setup=setup)
        logger.info("dnfdragora-updater termination")


    def main(self):
        if not self.__running:
            logger.error("Updater not fully initialized; cannot start.")
            return
        self.__main_loop()
