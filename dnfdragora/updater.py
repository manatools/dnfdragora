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
import notify2
from queue import SimpleQueue, Empty

import logging
logger = logging.getLogger('dnfdragora.updater')

notify2.init('dnfdragora-updater')


class Updater:

    def __init__(self, options={}):
        self.__main_gui  = None

        self.__config         = config.AppConfig('dnfdragora')
        self.__updateInterval = 180
        self.__update_count = -1

        self.__log_enabled = False
        self.__log_directory = None
        self.__level_debug = False

        if self.__config.userPreferences:
            if 'settings' in self.__config.userPreferences.keys() :
                settings = self.__config.userPreferences['settings']
                if 'interval for checking updates' in settings.keys() :
                    self.__updateInterval = int(settings['interval for checking updates'])

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
            icon_path = icon_path + 'dnfdragora.png'
        else:
            icon_path = icon_path + '/dnfdragora.png'

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

        try:
            self.__backend = dnfd_client.Client()
        except dnfdaemon.client.DaemonError as error:
            logger.error(_('Error starting dnfdaemon service: [%s]')%(str(error)))
            return
        except Exception as e:
            logger.error(_('Error starting dnfdaemon service: [%s]')%( str(e)))
            return
        self.__notifier  = notify2.Notification('dnfdragora', '', 'dnfdragora')
        self.__running   = True
        self.__updater   = threading.Thread(target=self.__update_loop)
        self.__scheduler = sched.scheduler(time.time, time.sleep)

        self.__menu  = Menu(
            MenuItem(_('Update'), self.__run_update),
            MenuItem(_('Open dnfdragora dialog'), self.__run_dnfdragora),
            MenuItem(_('Check for updates'), self.__get_updates_forced),
            MenuItem(_('Exit'), self.__shutdown)
        )
        self.__name  = 'dnfdragora-updater'
        self.__tray  = Tray(self.__name, self.__icon, self.__name, self.__menu)


    def __get_theme_icon_pathname(self):
      '''
        return theme icon pathname or None if missing
      '''
      try:
          import xdg.IconTheme
      except ImportError:
          logger.error("Error: module xdg.IconTheme is missing")
          return None
      else:
          pathname = xdg.IconTheme.getIconPath("dnfdragora", 256)
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
            logger.debug("----> %s"%("RUN" if self.__main_gui.running else "NOT RUNNING"))
            return
        try:
            self.__running = False
            self.__updater.join()
            try:
                if self.__backend:
                    self.__backend.Unlock(sync=True)
                    self.__backend.Exit(sync=True)
            except:
                pass
            yui.YDialog.deleteAllDialogs()
            yui.YUILoader.deleteUI()

        except:
            pass

        finally:
            if self.__scheduler.empty() != False:
                for task in self.__scheduler.queue:
                    try:
                        self.__scheduler.cancel(task)
                    except:
                        pass

            if self.__tray != None:
                self.__tray.stop()
            if self.__backend:
                self.__backend.Exit()


    def __run_dialog(self, args, *kwargs):
        if self.__tray != None and self.__main_gui == None:
            time.sleep(0.5)
            try:
                self.__main_gui = ui.mainGui(args)
            except Exception as e:
                dialogs.warningMsgBox({'title' : _("Running dnfdragora failure"), "text": str(e), "richtext":True}) 
                yui.YDialog.deleteAllDialogs()
                time.sleep(0.5)
                self.__main_gui = None
                return
            self.__tray.icon = None
            self.__main_gui.handleevent()

            while self.__main_gui.loop_has_finished != True:
                time.sleep(1)
            yui.YDialog.deleteAllDialogs()
            time.sleep(1)
            self.__main_gui = None
            self.__get_updates()


    def __run_dnfdragora(self, *kwargs):
        return self.__run_dialog({})


    def __run_update(self, *kwargs):
        return self.__run_dialog({'update_only': True})


    def __get_updates(self, *kwargs):
        return self.__get_updates_func(False)


    def __get_updates_forced(self, *kwargs):
        return self.__get_updates_func(True)


    def __get_updates_func(self, forced, *kwargs):
        #TODO REMOVE try:
        #TODO REMOVE     self.__backend = dnfd_client.Client()
        #TODO REMOVE except dnfdaemon.client.DaemonError as error:
        #TODO REMOVE     logger.error(_('Error starting dnfdaemon service: [%s]')%(str(error)))
        #TODO REMOVE     self.__update_count = -1
        #TODO REMOVE     self.__tray.icon = None
        #TODO REMOVE     return
        #TODO REMOVE except Exception as e:
        #TODO REMOVE     logger.error(_('Error starting dnfdaemon service: [%s]')%( str(e)))
        #TODO REMOVE     self.__update_count = -1
        #TODO REMOVE     self.__tray.icon = None
        #TODO REMOVE     return

        try:
            sync=True
            self.__backend.Lock()
            # TODO MOVE if locked:
            # TODO MOVE     pkgs = self.__backend.GetPackages('updates', sync)
            # TODO MOVE     self.__update_count = len(pkgs)
            # TODO MOVE     logger.debug("Found %d updates"%(self.__update_count))
            # TODO MOVE     self.__backend.Unlock(sync)
            # TODO MOVE     self.__backend.Exit(sync)
            # TODO MOVE     time.sleep(0.5)
            # TODO MOVE     self.__backend = None
            # TODO MOVE     if (self.__update_count >= 1) or forced:
            # TODO MOVE         self.__notifier.update(
            # TODO MOVE             'dnfdragora',
            # TODO MOVE             _('%d updates available.') % self.__update_count,
            # TODO MOVE             'dnfdragora'
            # TODO MOVE         )
            # TODO MOVE         self.__notifier.show()
            # TODO MOVE         self.__tray.icon = self.__icon
            # TODO MOVE         self.__tray.visible = True
            # TODO MOVE     else:
            # TODO MOVE         self.__notifier.close()
            # TODO MOVE else:
            # TODO MOVE     logger.error("DNF backend already locked cannot check for updates")
            # TODO MOVE     self.__update_count = -1
            # TODO MOVE     self.__tray.icon = None
            # TODO MOVE     self.__backend = None
        except Exception as e:
            logger.error(_('Exception caught: [%s]')%(str(e)))


    def __update_loop(self):
      self.__get_updates()

      while self.__running == True:
        update_next = 1 # self.__updateInterval
        add_to_schedule = False
        try:
          item = self.__backend.eventQueue.get_nowait()
          event = item['event']
          info = item['value']
          logger.debug("Event received %s - info %s", event, str(info))
          if (event == 'Lock') :
            backend_locked = info['result']
            if backend_locked:
              self.__backend.GetPackages('updates_all')
            else:
              # no locked try again in a minute
              update_next = 1
              add_to_schedule = True

          elif (event == 'GetPackages'):
            if not info['error']:
              po_list = info['result']
              self.__update_count = len(po_list)
              logger.info("Found %d updates"%(self.__update_count))

              if (self.__update_count >= 1):
                self.__notifier.update(
                    'dnfdragora',
                    _('%d updates available.') % self.__update_count,
                    'dnfdragora'
                )
                self.__notifier.show()
                self.__tray.icon = self.__icon
                self.__tray.visible = True
              else:
                  self.__notifier.close()

              add_to_schedule = True
            # Let's release the db
            self.__backend.Unlock(sync=True)

        except Empty as e:
          pass

        if (add_to_schedule and self.__scheduler.empty()):
          self.__scheduler.enter(update_next * 60, 1, self.__get_updates)
        self.__scheduler.run(blocking=False)
        time.sleep(1)



    def __main_loop(self):
        def setup(tray) :
            tray.visible = False

        self.__updater.start()
        time.sleep(1)
        self.__tray.run(setup=setup)
        logger.info("dnfdragora-updater termination")


    def main(self):
        self.__main_loop()
