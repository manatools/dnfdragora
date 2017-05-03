'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Björn Esser <besser82@fedoraproject.org>

@package dnfdragora
'''

import dnfdaemon.client, gettext, sched, sh, sys, threading, time, yui

from PIL import Image
from dnfdragora import config, misc, ui
from gettext import gettext as _
from pystray import Menu, MenuItem
from pystray import Icon as Tray


class Updater:

    def __init__(self):
        self.__main_gui  = None
        self.__notifier  = sh.Command("/usr/bin/notify-send")
        self.__running   = True
        self.__updater   = threading.Thread(target=self.__update_loop)
        self.__scheduler = sched.scheduler(time.time, time.sleep)

        self.__config         = config.AppConfig('dnfdragora')
        self.__updateInterval = 180

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

        icon_path = '/usr/share/icons/hicolor/128x128/apps/dnfdragora.png'

        try:
            self.__backend = dnfdaemon.client.Client()
        except dnfdaemon.client.DaemonError as error:
            print('Error starting dnfdaemon service: [%s]', str(error))
            sys.exit(1)

        try:
            from gi.repository import Gtk
            icon_theme = Gtk.IconTheme.get_default()
            icon_path  = icon_theme.lookup_icon("dnfdragora", 128, 0).get_filename()
        except:
            pass

        self.__icon  = Image.open(icon_path)
        self.__menu  = Menu(
            MenuItem('Update', self.__run_update),
            MenuItem('Open dnfdragora dialog', self.__run_dnfdragora),
            MenuItem('Check for updates', self.__get_updates_forced),
            MenuItem('Exit', self.__shutdown)
        )
        self.__name  = 'dnfdragora-updater'
        self.__tray  = Tray(self.__name, self.__icon, self.__name, self.__menu)


    def __shutdown(self, *kwargs):
        try:
            self.__running = False
            self.__updater.join()
            self.__main_gui.quit()
            while self.__main_gui.loop_has_finished != True:
                time.sleep(1)
            try:
                self.__backend.Unlock()
                self.__main_gui.backend.quit()
            except:
                pass
            yui.YDialog.deleteAllDialogs()
            yui.YUILoader.deleteUI()

        except:
            pass

        finally:
            if self.__scheduler.empty() != False:
                for task in self.__scheduler.queue():
                    try:
                        self.__scheduler.cancel(task)
                    except:
                        pass

            self.__tray.stop()
            self.__backend.Exit()


    def __run_dialog(self, args, *kwargs):
        if self.__tray != None:
            self.__main_gui = ui.mainGui(args)
            self.__main_gui.handleevent()


    def __run_dnfdragora(self, *kwargs):
        return self.__run_dialog({})


    def __run_update(self, *kwargs):
        return self.__run_dialog({'update_only': True})


    def __get_updates(self, *kwargs):
        return self.__get_updates_func(False)


    def __get_updates_forced(self, *kwargs):
        return self.__get_updates_func(True)


    def __get_updates_func(self, forced, *kwargs):
        if self.__backend.Lock():
            pkgs = self.__backend.GetPackages('updates')
            update_count = len(pkgs)
            self.__backend.Unlock()
            if (update_count >= 1) or forced:
                self.__notifier(
                    '-a', 'dnfdragora-updater',
                    '-i', 'dnfdragora',
                    '-u', 'normal',
                    'dnfdragora',
                    '%d updates available.' % update_count
                )
        else:
            update_count = -1


    def __update_loop(self):
        while self.__running == True:
            if self.__scheduler.empty():
                self.__scheduler.enter(self.__updateInterval * 60, 1, self.__get_updates)
            self.__scheduler.run(blocking=False)
            time.sleep(1)


    def __main_loop(self):
        self.__tray.visible = True
        self.__get_updates()
        self.__updater.start()


    def main(self):
        self.__tray.run(self.__main_loop())
