# vim: set fileencoding=utf-8 :
# vim: set et ts=4 sw=4:
'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Björn Esser <besser82@fedoraproject.org>

@package dnfdragora
'''

import dnfdaemon.client, gettext, sched, sys, threading, time, yui

from PIL import Image
from dnfdragora import config, misc, dialogs, ui
from pystray import Menu, MenuItem
from pystray import Icon as Tray
import notify2

notify2.init('dnfdragora-updater')


class Updater:

    def __init__(self, options={}):
        self.__main_gui  = None
        self.__notifier  = notify2.Notification('dnfdragora', '', 'dnfdragora')
        self.__running   = True
        self.__updater   = threading.Thread(target=self.__update_loop)
        self.__scheduler = sched.scheduler(time.time, time.sleep)

        self.__config         = config.AppConfig('dnfdragora')
        self.__updateInterval = 180
        self.__update_count = -1

        if self.__config.systemSettings :
            settings = {}
            if 'settings' in self.__config.systemSettings.keys() :
                settings = self.__config.systemSettings['settings']
                if 'update_interval' in settings.keys() :
                    self.__updateInterval = int(settings['update_interval'])

        if self.__config.userPreferences:
            if 'settings' in self.__config.userPreferences.keys() :
                settings = self.__config.userPreferences['settings']
                if 'interval for checking updates' in settings.keys() :
                    self.__updateInterval = int(settings['interval for checking updates'])

        # if missing gets the default icon from our folder (same as dnfdragora)
        icon_path = '/usr/share/dnfdragora/images/'

        if 'icon-path' in options.keys() :
            icon_path = options['icon-path']
        if icon_path.endswith('/'):
            icon_path = icon_path + 'dnfdragora.png'
        else:
            icon_path = icon_path + '/dnfdragora.png'

        theme_icon_pathname = self.__get_theme_icon_pathname() or icon_path
        print("Icon: %s"%(theme_icon_pathname))
        #empty icon as last chance
        self.__icon = Image.Image()
        try:
          if theme_icon_pathname.endswith('.svg'):
              with open(theme_icon_pathname, 'rb') as svg:
                  self.__icon = self.__svg_to_Image(svg.read())
          else:
              self.__icon  = Image.open(theme_icon_pathname)
        except Exception as e:
          print(e)
          print("Cannot open theme icon using default one %s"%(icon_path))
          self.__icon  = Image.open(icon_path)

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
          print ("Error: module xdg.IconTheme is missing")
          return None
      else:
          pathname = xdg.IconTheme.getIconPath("dnfdragora", 128)
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
        print("shutdown")
        if self.__main_gui :
            print("----> %s"%("RUN" if self.__main_gui.running else "NOT RUNNING"))
            return
        try:
            self.__running = False
            self.__updater.join()
            try:
                if self.__backend:
                    self.__backend.Unlock()
                    self.__backend.Exit()
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
        try:
            self.__backend = dnfdaemon.client.Client()
        except dnfdaemon.client.DaemonError as error:
            print(_('Error starting dnfdaemon service: [%s]')%(str(error)))
            self.__update_count = -1
            self.__tray.icon = None
            return
        except Exception as e:
            print(_('Error starting dnfdaemon service: [%s]')%( str(e)))
            self.__update_count = -1
            self.__tray.icon = None
            return

        try:
            if self.__backend.Lock():
                pkgs = self.__backend.GetPackages('updates')
                self.__update_count = len(pkgs)
                self.__backend.Unlock()
                self.__backend.Exit()
                time.sleep(0.5)
                self.__backend = None
                if (self.__update_count >= 1) or forced:
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
            else:
                print("DNF backend already locked cannot check for updates")
                self.__update_count = -1
                self.__tray.icon = None
                self.__backend = None
        except Exception as e:
            print(_('Exception caught: [%s]')%(str(e)))


    def __update_loop(self):
        self.__get_updates()
        while self.__running == True:
            if self.__scheduler.empty():
                self.__scheduler.enter(self.__updateInterval * 60, 1, self.__get_updates)
            self.__scheduler.run(blocking=False)
            time.sleep(1)


    def __main_loop(self):
        def setup(tray) :
            tray.visible = False

        self.__updater.start()
        time.sleep(1)
        self.__tray.run(setup=setup)
        print("dnfdragora-updater termination")


    def main(self):
        self.__main_loop()
