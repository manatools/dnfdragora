# vim: set fileencoding=utf-8 :
# vim: set et ts=4 sw=4:
'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Björn Esser <besser82@fedoraproject.org>

@package dnfdragora
'''

import gettext, sched, sys, threading, time, yui, os

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

    def __init__(self, options={}):
        self.__main_gui  = None

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
        icon_path = '/usr/share/dnfdragora/images/'

        if 'icon-path' in options.keys() :
            icon_path = options['icon-path']
        if icon_path.endswith('/'):
            icon_path = icon_path + 'dnfdragora.svg' if ( os.path.exists(icon_path + 'dnfdragora.svg') ) else icon_path + 'dnfdragora.png'
        else:
            icon_path = icon_path + '/dnfdragora.svg' if ( os.path.exists(icon_path + '/dnfdragora.svg') ) else icon_path + '/dnfdragora.png'

        theme_icon_pathname = icon_path if 'icon-path' in options.keys() else self.__get_theme_icon_pathname() or icon_path

        logger.debug("Icon: %s"%(theme_icon_pathname))
        #empty icon as last chance
        self.__icon = Image.Image()
        try:
          if theme_icon_pathname.endswith('.svg'):
              with open(theme_icon_pathname, 'rb') as svg:
                  self.__icon = self.__svg_to_Image(svg.read())
          else:
              self.__icon  = Image.open(theme_icon_pathname)
        except Exception as e:
          logger.error(e)
          logger.error("Cannot open theme icon using default one %s"%(icon_path))
          self.__icon  = Image.open(icon_path)

        # resetting icon_path to default value
        icon_path = '/usr/share/dnfdragora/images/'
        if 'icon-path' in options.keys() :
            icon_path = options['icon-path']
        if icon_path.endswith('/'):
            icon_path = icon_path + 'dnfdragora-update.svg' if ( os.path.exists(icon_path + 'dnfdragora-update.svg') ) else icon_path + 'dnfdragora-update.png'
        else:
            icon_path = icon_path + '/dnfdragora-update.svg' if ( os.path.exists(icon_path + '/dnfdragora-update.svg') ) else icon_path + '/dnfdragora-update.png'

        theme_icon_pathname = icon_path if 'icon-path' in options.keys() else self.__get_theme_icon_pathname(name="dnfdragora-update") or icon_path

        self.__icon_update = Image.Image()
        try:
          if theme_icon_pathname.endswith('.svg'):
              with open(theme_icon_pathname, 'rb') as svg:
                  self.__icon_update = self.__svg_to_Image(svg.read())
          else:
              self.__icon_update  = Image.open(theme_icon_pathname)
        except Exception as e:
          logger.error(e)
          logger.error("Cannot open theme icon using default one %s"%(icon_path))
          self.__icon_update  = Image.open(icon_path)

        try:
            self.__backend = dnfd_client.Client()
        except Exception as e:
            logger.error(_('Error starting dnfdaemon service: [%s]')%( str(e)))
            return

        self.__running   = True
        self.__updater   = threading.Thread(target=self.__update_loop)
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
        return theme icon pathname or None if missing
      '''
      try:
          import xdg.IconTheme
      except ImportError:
          logger.error("Error: module xdg.IconTheme is missing")
          return None
      else:
          pathname = xdg.IconTheme.getIconPath(name, 256)
          return pathname
      return None

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
          self.__updater.join()
          try:
            if self.__backend:
              self.__backend = None
          except:
            pass
          yui.YDialog.deleteAllDialogs()
          yui.YUILoader.deleteUI()

        except:
          pass

        finally:
            if not self.__scheduler.empty():
                for task in self.__scheduler.queue:
                    try:
                        self.__scheduler.cancel(task)
                    except:
                        pass

            if self.__tray != None:
              self.__tray.stop()
            if self.__backend:
              self.__backend = None

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
          except:
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
            try:
                self.__main_gui = ui.mainGui(args)
            except Exception as e:
              logger.error("Exception on running dnfdragora with args %s - %s", str(args), str(e))
              dialogs.warningMsgBox({'title' : _("Running dnfdragora failure"), "text": str(e), "richtext":True})
              yui.YDialog.deleteAllDialogs()
              time.sleep(0.5)
              self.__main_gui = None
              return
            #self.__tray.icon = None
            self.__main_gui.handleevent()

            logger.debug("Closing dnfdragora")
            while self.__main_gui.loop_has_finished != True:
                time.sleep(1)
            logger.info("Closed dnfdragora")
            yui.YDialog.deleteAllDialogs()
            time.sleep(1)
            self.__main_gui = None
            logger.debug("Look for remaining updates")
            # Let's delay a bit the check, otherwise Lock will fail
            done=self.__reschedule_update_in(0.5)
            logger.debug("Scheduled %s", "done" if done else "skipped")
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
      logger.debug("Start getting updates")

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
        self.__backend.reloadDaemon()
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
              # Let's release the daemon
              self.__backend.unloadDaemon()
            #elif (event == xxx)
            else:
              logger.warning("Unmanaged event received %s - info %s", event, str(info))

        except Empty as e:
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
        self.__main_loop()
