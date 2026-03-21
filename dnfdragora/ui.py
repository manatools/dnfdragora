
'''
dnfdragora is a graphical frontend based on rpmdragora implementation
that uses dnf as rpm backend, due to libyui python bindings dnfdragora
is able to comfortably behave like a native gtk or qt5 or ncurses application

License: GPLv3

Author:  Angelo Naselli <anaselli@linux.it>

@package dnfdragora
'''

import os
import sys
import platform
import datetime
import re
import manatools.aui.yui as MUI

#from manatools.aui import yui_common as YUI
import webbrowser
from html import escape
from queue import SimpleQueue, Empty
from enum import Enum
from inspect import ismethod
import libdnf5

#NOTE we need a glib.MainLoop in TUI and use threading for it
import threading
from gi.repository import GLib

import manatools.ui.helpdialog as helpdialog
import manatools.ui.common as common
import dnfdragora.basedragora
import dnfdragora.compsicons as compsicons
import dnfdragora.groupicons as groupicons
import dnfdragora.progress_ui as progress_ui
import dnfdragora.dialogs as dialogs
import dnfdragora.misc as misc
import dnfdragora.helpinfo as helpinfo

import dnfdragora.config
from dnfdragora import const

import gettext
import logging
logger = logging.getLogger('dnfdragora.ui')

class UIError(Exception):
  'Raise an Error from UI'
  def __init__(self, msg=None):
    self.msg = msg

  def __str__(self):
    if self.msg:
      return self.msg
    else:
      return ""

class DNFDragoraStatus(Enum):
    '''
    Enum
        STARTUP Starting
        LOCKING Lock requested
        CACHING_UPDATE Caching updates
        CACHING_INSTALLED Caching installed packages
        CACHING_AVAILABLE Caching available packages
        RUN_TRANSACTION Running transaction
        EXPIRE_CACHE Expire cache
        RESET_SESSION Reset session
        RELOAD_METADATA Reload metadata
        RUNNING Locked, normal running no requests
    '''
    STARTUP = 1
    LOCKING = 2
    CACHING_UPDATE = 3
    CACHING_INSTALLED = 4
    CACHING_AVAILABLE = 5
    RUN_TRANSACTION = 6
    EXPIRE_CACHE = 7
    RESET_SESSION = 8
    RELOAD_METADATA = 9
    RUNNING = 10



class PackageQueue:
    '''
    A Queue class to store selected packages/groups and the pending actions
    '''

    def __init__(self):
        self.packages = {}
        self._setup_packages()
        self.actions = {}


#QUEUE_PACKAGE_TYPES = {
#    'i': 'install',
#    'u': 'update',
#    'r': 'remove',
#    'o': 'obsolete',
#    'ri': 'reinstall',
#    'do': 'downgrade',
#    'li': 'localinstall'
#}
    def _setup_packages(self):
        for key in const.QUEUE_PACKAGE_TYPES:
            self.packages[key] = []

    def clear(self):
        del self.packages
        self.packages = {}
        self._setup_packages()
        self.actions = {}


    def get(self, action=None):
        if action is None:
            return self.packages
        else:
            return self.packages[action]

    def total(self):
        num = 0
        for key in const.QUEUE_PACKAGE_TYPES:
            num += len(self.packages[key])
        return num

    def add(self, pkg, action):
        """Add a package to queue"""
        pkg_id = pkg.pkg_id
        if pkg_id in self.actions.keys():
            old_action = self.actions[pkg_id]
            if old_action != action:
                self.packages[old_action].remove(pkg_id)
                if (pkg.installed and action != 'i' or not pkg.installed and action != 'r'):
                    self.packages[action].append(pkg_id)
                    self.actions[pkg_id] = action
                else:
                    del self.actions[pkg_id]
        else:
            self.packages[action].append(pkg_id)
            self.actions[pkg_id] = action

    def checked(self, pkg):
        '''
        returns if a package has to be checked in gui package-list
        '''
        pkg_id = pkg.pkg_id
        if pkg_id in self.actions.keys():
            return pkg.installed and self.actions[pkg_id] != 'r' or self.actions[pkg_id] != 'r'
        return pkg.installed

    def action(self, pkg):
        '''
        returns the action of the queued package or None if package is not queued
        '''
        pkg_id = pkg.pkg_id
        if pkg_id in self.actions.keys():
            return self.actions[pkg_id]
        return None

    def remove(self, pkg):
        """Remove package from queue"""
        pkg_id = pkg.pkg_id
        if pkg_id in self.actions.keys():
            action = self.actions[pkg_id]
            self.packages[action].remove(pkg_id)
            del self.actions[pkg_id]


#################
# class mainGui #
#################
class mainGui(dnfdragora.basedragora.BaseDragora):
    """
  Main UI controller for dnfdragora.

  It builds the AUI layout, handles frontend events, and bridges
  asynchronous backend (dnfdaemon) notifications to widgets.
    """

    def __init__(self, options={}):
        '''
        constructor
        '''

        self._status = DNFDragoraStatus.STARTUP
        self._beforeLockAgain = 20 # 20 x 500 ms = 10 sec
        self.running = False
        self.loop_has_finished = False
        self.options = options
        self.infobar = None
        self.packageQueue = PackageQueue()
        self.toRemove = []
        self.toInstall = []
        self.itemList = {}
        self.appname = "dnfdragora"
        self._selPkg = None
        self.md_update_interval = 48 # check any 48 hours as default
        self.md_last_refresh_date = None
        self._runtime_option_managed = False
        self._download_events = {
          'in_progress' : 0,
          'downloads' : {}
        } # obsoletes _files_to_download and _files_downloaded

        self.packageActionValue = const.Actions.NORMAL
        # TODO... _package_name, _gpg_confirm imported from old event management
        # Try to remove them when fixing progress bar
        self._package_name = None
        self._action_name = None
        self._gpg_confirm = None
        # ...TODO
        self._transaction_tries = 0
        self._transaction_noreply_warned = False
        self._trans_dialog = None  # TransactionProgressDialog, active during RUN_TRANSACTION
        self.started_transaction = _('No transaction found')
        # {
        #   name-epoch_version-release.arch : { pkg: dnf-pkg, item: YItem}
        # }
        self.groupList = {}
        # {
        #    localized_name = { "item" : item, "name" : groupName }
        # }

        self.infoshown = {
            'updateinfo' : { 'title' : _("Update information"), 'show' : False },
            'files' : { 'title' : _("File list"), 'show' : False },
            'changelog' : { 'title' : _("Changelog"), 'show' : False },
            'requirements' : { 'title' : _("Requirements"), 'show' : False },
            }
        self.checkBoxColumn = 0
        self.use_comps = False
        self.group_icon_path = None
        self.images_path = '/usr/share/dnfdragora/images/'
        self.always_yes = False
        self.fuzzy_search = False
        self.newest_only = False
        self.all_updates_filter = False
        self.log_enabled = False
        self.log_directory = None
        self.level_debug = False
        self.upgrades_as_updates = True # NOTE consider package to upgrade as update
        self.config = dnfdragora.config.AppConfig(self.appname)

        # settings from configuration file first
        self._configFileRead()

        if self.log_enabled:
          if self.log_directory:
            log_filename = os.path.join(self.log_directory, "dnfdragora.log")
            if self.level_debug:
              misc.logger_setup(log_filename, loglvl=logging.DEBUG)
            else:
              misc.logger_setup(log_filename)
            print("Logging into %s, debug mode is %s"%(self.log_directory, ("enabled" if self.level_debug else "disabled")))
            logger.info("dnfdragora started")
        else:
           print("Logging disabled")

        # overrides settings from comand line
        if 'group_icons_path' in self.options.keys() :
            self.group_icon_path = self.options['group_icons_path']
        if 'images_path' in self.options.keys() :
            self.images_path = self.options['images_path']
        self.update_only = 'update_only' in self.options.keys()

        if self.use_comps and not self.group_icon_path:
            self.group_icon_path = '/usr/share/pixmaps/comps/'

        # Adding / as last har in the path if not present
        if not self.images_path.endswith('/'):
            self.images_path += "/"
        if self.group_icon_path and not self.group_icon_path.endswith('/'):
            self.group_icon_path += "/"

        if MUI.YUI.app().isTextMode():
          self.glib_loop = GLib.MainLoop()
          self.glib_thread = threading.Thread(target=self.glib_mainloop, args=(self.glib_loop,))
          self.glib_thread.start()
#

        dnfdragora.basedragora.BaseDragora.__init__(self, self.use_comps)

        # setup UI
        self._setupUI()

        self._enableAction(False)
        self.pbar_layout.setEnabled(True)

        self.backend
        #self.dialog.pollEvent()
        #self.find_entry.setKeyboardFocus()



    def glib_mainloop(self, loop):
      '''
      thread function for glib main loop
      '''
      loop.run()

    def _configFileRead(self) :
        '''
        reads the configuration file and sets application data
        '''

        if self.config.systemSettings :
            settings = {}
            if 'settings' in self.config.systemSettings.keys() :
                settings = self.config.systemSettings['settings']

            if 'use_comps' in settings.keys() :
                self.use_comps = settings['use_comps']

            if 'always_yes' in settings.keys() :
                self.always_yes = settings['always_yes']

            if 'log_directory' in settings.keys() :
              print("Warning logging must be set in user preferences, discarded")

            if 'log_level_debug' in settings.keys() :
              print("Warning logging must be set in user preferences, discarded")

            # config['settings']['path']
            path_settings = {}
            if 'path' in settings.keys():
                path_settings = settings['path']
            if 'group_icons' in path_settings.keys():
                self.group_icon_path = path_settings['group_icons']
            if 'images' in path_settings.keys():
                self.images_path = path_settings['images']

            # config['settings']['search']
            search = {}
            if 'search' in settings.keys():
                search = settings['search']
            if 'fuzzy_search' in search.keys():
                self.fuzzy_search = search['fuzzy_search']
            if 'newest_only' in search.keys():
                self.newest_only = search['newest_only']

            # all_updates force first running without user setting configured with the view
            # all packages and to_updates filter, fedora users coming from yumex-dnf are used to
            # get this view. Mageia and OpenMandriva Groups and All instead
            if 'all_updates' in settings.keys():
              self.all_updates_filter = settings['all_updates']

        # User preferences overriding
        user_settings = {}
        if self.config.userPreferences:
            if 'settings' in self.config.userPreferences.keys() :
                if self.config.userPreferences['settings'] is None:
                    self.config.userPreferences['settings'] = {}
                user_settings = self.config.userPreferences['settings']
                #### MetaData
                if 'metadata' in user_settings.keys():
                  metadata = user_settings['metadata']
                  if 'update_interval' in metadata.keys():
                    self.md_update_interval = metadata['update_interval']
                  else:
                    self.md_update_interval = metadata['update_interval'] = 48
                  if 'last_update' in metadata.keys():
                    self.md_last_refresh_date =  metadata['last_update']
                else:
                  self.config.userPreferences['settings']['metadata'] ={
                    'update_interval': self.md_update_interval, # 48 Default
                    'last_update': ''
                  }
                if 'upgrades as updates' in user_settings.keys():
                  self.upgrades_as_updates = user_settings['upgrades as updates']

                #### Search
                if 'search' in user_settings.keys():
                    search = user_settings['search']
                    if 'newest_only' in search.keys():
                        self.newest_only = search['newest_only']
                    if 'fuzzy_search' in search.keys():
                        self.fuzzy_search = search['fuzzy_search']
                #### Logging
                if 'log' in user_settings.keys():
                  log = user_settings['log']
                  if 'enabled' in log.keys() :
                    self.log_enabled = log['enabled']
                  if self.log_enabled:
                    if 'directory' in log.keys() :
                        self.log_directory = log['directory']
                    if 'level_debug' in log.keys() :
                        self.level_debug = log['level_debug']

        # metadata settings is needed adding it to update old configuration files
        if not 'settings' in self.config.userPreferences.keys() :
          self.config.userPreferences['settings'] = {}
        if not 'metadata' in self.config.userPreferences['settings'].keys():
          self.config.userPreferences['settings']['metadata'] = {
            'update_interval': self.md_update_interval, # 48 Default
            'last_update': ''
          }

    def _setupUI(self) :
        '''
            setup main dialog
        '''
        MUI.YUI.app().setApplicationTitle(_("Software Management - dnfdragora"))

        self.icon = "dnfdragora" #self.images_path + "dnfdragora.png"
        self.logo = self.images_path + "dnfdragora-logo.png"
        MUI.YUI.app().setApplicationIcon(self.icon)

        self.factory = MUI.YUI.widgetFactory()
        
        self.AboutDialog = dialogs.AboutDialog(self)

        ### MAIN DIALOG ###
        self.dialog = self.factory.createMainDialog()

        # Enforce a comfortable minimum size so the window opens with enough
        # space for the group tree, the full package table, and the description
        # pane.  Units are PIXELS: 900×680 is comfortable on a 1080p display.
        min_size = self.factory.createMinSize(self.dialog, 900, 680)
        vbox = self.factory.createVBox(min_size)

        hbox_menubar = self.factory.createHBox(vbox)

        #Line for logo and title
        #hbox_iconbar  = self.factory.createHBox(vbox)
        #head_align_left  = self.factory.createLeft(hbox_iconbar)
        #hbox_iconbar     = self.factory.createHBox(head_align_left)
        #self.factory.createImage(hbox_iconbar, self.logo)

        #self.factory.createHeading(hbox_iconbar, _("Software Management"))

        hbox_top = self.factory.createHBox(vbox)
        #hbox_middle = self.factory.createHBox(vbox)
        hbox_bottom = self.factory.createPaned(vbox, MUI.YUIDimension.YD_VERT)
        hbox_middle = self.factory.createPaned(hbox_bottom, MUI.YUIDimension.YD_HORIZ)
        #hbox_bottom = self.factory.createHBox(vbox)
        self.pbar_layout = self.factory.createHBox(vbox)
        hbox_footbar = self.factory.createHBox(vbox)

        # Package browsing area (tree + table): 70 % of vertical space.
        # Info / description area: 30 % — more than the old 33/67 split
        # expressed differently to give text room to display 3-4 lines.
        hbox_middle.setWeight(MUI.YUIDimension.YD_VERT, 70)
        hbox_bottom.setWeight(MUI.YUIDimension.YD_VERT, 30)
        if hasattr(hbox_middle, 'setStretchable'):
          hbox_middle.setStretchable(MUI.YUIDimension.YD_VERT, True)
        if hasattr(hbox_bottom, 'setStretchable'):
          hbox_bottom.setStretchable(MUI.YUIDimension.YD_VERT, True)

        #######
        foot_align_left = self.factory.createLeft(hbox_footbar)
        foot_align_right = self.factory.createRight(hbox_footbar)
        hbox_footbar = self.factory.createHBox(foot_align_left)
        right_footbar = self.factory.createHBox(foot_align_right)
        #######

        self.menu_layout = hbox_menubar
        self.top_layout = hbox_top
        self.middle_layout = hbox_middle
        self.bottom_layout = hbox_bottom
        self.footbar_layout = hbox_footbar


        # Tree for groups
        self.tree = self.factory.createTree(hbox_middle, "")
        self.tree.setWeight(MUI.YUIDimension.YD_HORIZ, 30)
        self.tree.setWeight(MUI.YUIDimension.YD_VERT, 60)
        if hasattr(self.tree, 'setStretchable'):
          self.tree.setStretchable(MUI.YUIDimension.YD_VERT, True)
        self.tree.setNotify(True)        

        packageList_header = MUI.YTableHeader()
        columns = [ _('Name'), _('Summary'), _('Version'), _('Release'), _('Arch'), _('Size')]

        checkboxed = True
        packageList_header.addColumn("", checkboxed, alignment=MUI.YAlignmentType.YAlignCenter)
        for col in (columns):
            packageList_header.addColumn(col, not checkboxed)

        if not self.update_only:
            packageList_header.addColumn(_("Status"), not checkboxed)

        self.packageList = self.factory.createTable(hbox_middle, packageList_header)
        self.packageList.setWeight(MUI.YUIDimension.YD_HORIZ, 70)
        self.packageList.setWeight(MUI.YUIDimension.YD_VERT, 60)
        if hasattr(self.packageList, 'setStretchable'):
          self.packageList.setStretchable(MUI.YUIDimension.YD_VERT, True)
        self.packageList.setHelpText("Package list")
        #self.packageList.setImmediateMode(True)

        self.filters = {
            'all' : {'title' : _("All")},
            'installed' : {'title' : _("Installed")},
            'not_installed' : {'title' : _("Not installed")},
            'to_update' : {'title' : _("To update")}
        }
        ordered_filters = [ 'all', 'installed', 'to_update', 'not_installed' ]
        if platform.machine() == "x86_64" :
            # NOTE this should work on other architectures too, but maybe it
            #      is a nonsense, at least for i586
            self.filters['skip_other'] = {'title' : _("Show %s and noarch only") % platform.machine()}
            ordered_filters.append('skip_other')

        # TODO add backports
        self.views = {
            'all' : {'title' : _("All")},
            'groups' : {'title' : _("Groups")},
        }
        ordered_views = [ 'groups', 'all' ]

        self.view_box = self.factory.createComboBox(hbox_top,"")
        self.view_box.setHelpText(_("Grouping packages"))
        itemColl = []

        view = {}
        settings = {}
        if self.config.userPreferences:
            if 'settings' in self.config.userPreferences.keys() :
                settings = self.config.userPreferences['settings']
            if 'view' in self.config.userPreferences.keys() :
                view = self.config.userPreferences['view']
            if 'show updates at startup' in settings.keys() :
                if settings['show updates at startup'] :
                    view['filter'] = 'to_update'
            if 'do not show groups at startup' in settings.keys() :
                if settings['do not show groups at startup'] :
                    view['show'] = 'all'
            if 'always_yes' in settings.keys() :
                self.always_yes = settings['always_yes']

        show_item = 'all' if self.update_only else \
          view['show'] if 'show' in view.keys() else 'groups'

        for v in ordered_views:
            item = MUI.YItem(self.views[v]['title'])
            if show_item == v :
                item.setSelected(True)
            # adding item to views to find the item selected
            self.views[v]['item'] = item
            itemColl.append(item)

        self.view_box.addItems(itemColl)
        self.view_box.setNotify(True)
        self.view_box.setEnabled(not self.update_only)

        self.filter_box = self.factory.createComboBox(hbox_top,"")
        self.filter_box.setHelpText(_("Filtering packages"))
        itemColl.clear()

        filter_item = 'to_update' if self.all_updates_filter or self.update_only \
          else view['filter'] if 'filter' in view.keys() else 'all'

        for f in ordered_filters:
            item = MUI.YItem(self.filters[f]['title'])
            if filter_item == f:
                item.setSelected(True)
            # adding item to filters to find the item selected
            self.filters[f]['item'] = item
            itemColl.append(item)

        self.filter_box.addItems(itemColl)
        self.filter_box.setNotify(True)
        self.filter_box.setEnabled(not self.update_only)

        self.local_search_types = {
            'name'       : {'title' : _("in names")       },
            'description': {'title' : _("in descriptions")},
            'summary'    : {'title' : _("in summaries")   },
            'file'       : {'title' : _("in file names")  }
        }
        search_types = ['name', 'summary', 'description', 'file' ]

        self.search_list = self.factory.createComboBox(hbox_top,"")
        itemColl.clear()
        for s in search_types:
            item = MUI.YItem(self.local_search_types[s]['title'])
            if s == search_types[0] :
                item.setSelected(True)
            # adding item to local_search_types to find the item selected
            self.local_search_types[s]['item'] = item
            itemColl.append(item)

        self.search_list.addItems(itemColl)
        self.search_list.setNotify(True)

        self.find_entry = self.factory.createInputField(hbox_top, "")
        self.find_entry.setWeight(MUI.YUIDimension.YD_HORIZ, 50)
        self.find_entry.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
        self.find_entry.setNotify(False)

        self.use_regexp = self.factory.createCheckBox(hbox_top, _("Use regexp"))
        self.use_regexp.setNotify(True)

        self.find_button = self.factory.createIconButton(hbox_top, 'edit-find', _("&Search"))
        self.find_button.setHelpText(_("Search packages"))
        #TODO self.find_button.setDefaultButton(True)

        self.reset_search_button = self.factory.createIconButton(hbox_top, 'edit-clear', _("&Clear search"))
        self.reset_search_button.setHelpText(_("Clear search field"))

        self.info = self.factory.createRichText(hbox_bottom,"")
        # Give the description area a larger share of the bottom pane so
        # multi-line package descriptions are readable without scrolling.
        self.info.setWeight(MUI.YUIDimension.YD_VERT, 100)
        self.info.setStretchable(MUI.YUIDimension.YD_VERT, True)
        self.info.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
        
        self.infobar = progress_ui.ProgressBar(self.dialog, self.pbar_layout)        

        self.applyButton = self.factory.createPushButton(hbox_footbar, _("&Apply"))
        self.applyButton.setWeight(MUI.YUIDimension.YD_HORIZ,1)
        self.applyButton.setEnabled(False)

        self.checkAllButton = self.factory.createIconButton(hbox_footbar, 'edit-select-all', _("Sel&ect all"))
        self.checkAllButton.setWeight(MUI.YUIDimension.YD_HORIZ,1)
        self.checkAllButton.setHelpText(_("Select all the packages"))
        self.checkAllButton.setEnabled(False)
        spacing = self.factory.createHStretch(hbox_footbar)

        spacing = self.factory.createHStretch(right_footbar)
        self.quitButton = self.factory.createIconButton(right_footbar, 'application-exit', _("&Quit"))
        self.quitButton.setWeight(MUI.YUIDimension.YD_HORIZ,1)
        self.quitButton.setHelpText(_("Quit the application"))

        ### BEGIN Menus #########################
        if (hasattr(self.factory, 'createMenuBar') and ismethod(getattr(self.factory, 'createMenuBar'))):
            logger.info("System has createMenuBar, using menubar")
            self.menubar = self.factory.createMenuBar(hbox_menubar)

            # building File menu
            # def addMenu(self, label: str="", icon_name: str = "", menu: YMenuItem = None) -> YMenuItem:
            # ef addItem(self, menu: YMenuItem, label: str, icon_name: str = "", enabled: bool = True) -> YMenuItem:
            mItem = self.menubar.addMenu(label=_("&File"))
            self.fileMenu = {
                'menu_name' : mItem,
                'reset_sel' : self.menubar.addItem(mItem, _("Reset the selection")),
                'reload'    : self.menubar.addItem(mItem, _("Refresh Metadata")),
                'repos'     : self.menubar.addItem(mItem, _("Repositories")),
                'sep0'      : mItem.addSeparator(),
                'quit'      : self.menubar.addItem(mItem, _("&Quit"), "application-exit"),
            }
            #Items must be "disowned"
            #for k in self.fileMenu.keys():
            #    self.fileMenu[k].this.own(False)

            # building Actions menu
            mItem = self.menubar.addMenu(_("&Actions"))
            self.ActionMenu = {
                 'menu_name' : mItem,
                 'actions'   : self.menubar.addItem(mItem, _("&Action on packages")),
            }
            #Items must be "disowned"
            #for k in self.ActionMenu.keys():
            #    self.ActionMenu[k].this.own(False)

            # # building Information menu
            # mItem = self.menubar.addMenu(_("&Information"))
            # self.infoMenu = {
            #     'menu_name' : mItem,
            #     'history'   : MUI.YMenuItem(mItem, _("&History")),
            # }
            # #Items must be "disowned"
            # for k in self.infoMenu.keys():
            #     self.infoMenu[k].this.own(False)

            # building Options menu
            mItem = self.menubar.addMenu(_("&Options"))
            self.optionsMenu = {
                'menu_name'  : mItem,
                'user_prefs' : self.menubar.addItem(mItem, _("User preferences")),
            }
            #Items must be "disowned"
            #for k in self.optionsMenu.keys():
            #    self.optionsMenu[k].this.own(False)

            # build Help menu
            mItem = self.menubar.addMenu(_("&Help"))
            self.helpMenu = {
                'menu_name': mItem,
                'help'     : self.menubar.addItem(mItem, _("Manual")),
                'sep0'     : mItem.addSeparator(),
                'about'    : self.menubar.addItem(mItem, _("&About"), 'dnfdragora'),
            }
            #Items must be "disowned"
            #for k in self.helpMenu.keys():
            #    self.helpMenu[k].this.own(False)

            #TODO self.menubar.resolveShortcutConflicts()
            self.menubar.rebuildMenus()
        else:
            logger.info("System has not createMenuBar, using old menu buttons")
            self._createMenuButtons(self.factory.createHBox(self.factory.createLeft(hbox_menubar)))
        ### END Menus #########################

    def _createMenuButtons(self, headbar):
        ''' create obsolete menu buttons to allow using dnfdragora if manubar 
            is not implemented, in the case libyui-mga is old
        '''
        # build File menu
        self.fileMenu = {
            'widget'    : self.factory.createMenuButton(headbar, _("&File")),
            'reset_sel' : MUI.YMenuItem(_("Reset the selection")),
            'reload'    : MUI.YMenuItem(_("Refresh Metadata")),
            'repos'     : MUI.YMenuItem(_("Repositories")),
            'quit'      : MUI.YMenuItem(_("&Quit"), "application-exit"),
        }

        ordered_menu_lines = ['reset_sel', 'reload', 'repos', 'quit']
        for l in ordered_menu_lines :
            self.fileMenu['widget'].addItem(self.fileMenu[l])
        self.fileMenu['widget'].rebuildMenuTree();

        # build Options menu
        #self.infoMenu = {
        #    'widget'    : self.factory.createMenuButton(headbar, _("&Information")),
        #    'history' : MUI.YMenuItem(_("History")),
        #}

        #NOTE following the same behavior to simplfy further menu entry addtion
        #ordered_menu_lines = ['history']
        #for l in ordered_menu_lines :
        #    self.infoMenu['widget'].addItem(self.infoMenu[l])
        #self.infoMenu['widget'].rebuildMenuTree();

        # build Options menu
        self.optionsMenu = {
            'widget'    : self.factory.createMenuButton(headbar, _("&Options")),
            'user_prefs' : MUI.YMenuItem(_("User preferences")),
        }

        #NOTE following the same behavior to simplfy further menu entry addtion
        ordered_menu_lines = ['user_prefs']
        for l in ordered_menu_lines :
            self.optionsMenu['widget'].addItem(self.optionsMenu[l])
        self.optionsMenu['widget'].rebuildMenuTree();

        # build help menu
        self.helpMenu = {
            'widget': self.factory.createMenuButton(headbar, _("&Help")),
            'help'  : MUI.YMenuItem(_("Manual")),
            'about' : MUI.YMenuItem(_("&About"), 'dnfdragora'),
        }
        ordered_menu_lines = ['help', 'about']
        for l in ordered_menu_lines :
            self.helpMenu['widget'].addItem(self.helpMenu[l])

        self.helpMenu['widget'].rebuildMenuTree()

    
    def _enableAction(self, value=True):
      '''
      disable ui actions but let's allow to quit
      '''
      self.menu_layout.setEnabled(value)
      self.top_layout.setEnabled(value)
      self.middle_layout.setEnabled(value)
      self.bottom_layout.setEnabled(value)
      self.footbar_layout.setEnabled(value)

    def _setStatusToItem(self, pkg, item, emit_changed=False) :
        '''
        set the status of the given package to the item so that it is shown on package list
        '''
        if self.update_only:
            return

        cellNum = item.cellCount()
        cell= item.cell(cellNum-1)
        icon = None

        status = self.packageQueue.action(pkg)
        if status:
            icon = self.images_path + const.QUEUE_PACKAGE_TYPES[status] +".png"
        else:
            #not queued
            if pkg.is_update:
                status = _("update")
                icon = self.images_path + "update.png"
            elif pkg.installed and self.backend.protected(pkg) :
                status = _("locked")
                icon = self.images_path + "protected.png"
            elif pkg.installed :
                status = _("installed")
                icon = self.images_path + "installed.png"
            else:
                status = ""
                icon = self.images_path + "available.png"
        if icon:
          cell.setLabel(status)
          cell.setIconName(icon)
          # AUI table updates automatically; no explicit cellChanged needed

    def _selectedPackage(self) :
        '''
        gets the selected package from package list, if any, and return the
        related package as DnfPackage
        '''
        selected_pkg = None
        sel = self.packageList.selectedItem()
        if sel :
            for pkg_name in self.itemList:
                if (self.itemList[pkg_name]['item'] == sel) :
                    selected_pkg = self.itemList[pkg_name]['pkg']
                    break

        return selected_pkg

    def _createCBItem(self, checked, pkg_name, pkg_summary, pkg_version, pkg_release, pkg_arch, pkg_sizeM):
        '''
        create a YCBTableItem with given data and return it
        Note that it also disowns either cells or item itself
        '''
        # produce string-sortable version of pkg_sizeM: the sizes are in KB, assume largest
        # package size <100G ie left-pad with O's to 8 digits (not counting decimals)
        digitsNeeded = 8
        sizePadded = pkg_sizeM
        # strip trailing K
        if sizePadded.endswith('K'):
            sizePadded = sizePadded[:-1]
        else:
            logger.warning('while building sizePadded, no trailing K in %s , why? proceeding anyways', pkg_sizeM)
        (sizeInt, decMark, decimals) = sizePadded.partition('.')
        sizeIntPadded = sizeInt.rjust(digitsNeeded, '0')
        sizePadded = sizeIntPadded + decMark + decimals
        item = MUI.YTableItem()
        item.addCell(bool(checked))
        item.addCell(str(pkg_name))
        item.addCell(str(pkg_summary))
        item.addCell(str(pkg_version))
        item.addCell(str(pkg_release))
        item.addCell(str(pkg_arch))
        size_cell = MUI.YTableCell(pkg_sizeM, "", sizePadded)
        item.addCell(size_cell)
        return item

    def _fillPackageList(self, groupName=None, filter="all") :
        '''
        fill package list filtered by group if groupName is given,
        and checks installed packages.
        Special value for groupName 'All' means all packages
        Available filters are:
        all, installed, not_installed, to_update and skip_other
        '''
        sel_pkg = self._selectedPackage()
        # reset info view
        # TODO self.info.setValue("")

        MUI.YUI.app().busyCursor()

        self.itemList = {}
        # {
        #   name-epoch_version-release.arch : { pkg: dnf-pkg, item: YItem}
        # }
        group_packages = set()
        if self.use_comps and groupName and (groupName != 'All'):
            # Get packages from group once and use O(1) membership checks.
            try:
                group_packages = set(self.backend.GetGroupPackageNames(groupName, sync=True) or [])
            except Exception as error:
                logger.exception("Failed to load package names for comps group '%s': %s", groupName, error)

        machine_arch = platform.machine()

        def _is_package_in_selected_group(pkg):
            """Return True when package belongs to selected group or no group filter is active."""
            if not groupName:
                return True
            if groupName == 'All':
                return True
            if self.use_comps:
                return pkg.name in group_packages
            try:
                groups_pkg = self.backend.get_groups_from_package(pkg) or []
            except Exception as error:
                logger.exception("Cannot read groups for package '%s': %s", pkg.name, error)
                return False
            return groupName in groups_pkg

        if filter == 'all' or filter == 'to_update' or filter == 'skip_other':
            updates = self.backend.get_packages('updates')
            for pkg in updates :
                insert_items = _is_package_in_selected_group(pkg)

                if insert_items :
                    skip_insert = (filter == 'skip_other' and not (pkg.arch == 'noarch' or pkg.arch == machine_arch))
                    if not skip_insert :
                        item = self._createCBItem(self.packageQueue.checked(pkg),
                                           pkg.name,
                                           pkg.summary,
                                           pkg.version,
                                           pkg.release,
                                           pkg.arch,
                                           pkg.sizeM)
                        pkg_name = pkg.fullname
                        if sel_pkg :
                            if sel_pkg.fullname == pkg_name :
                                item.setSelected(True)
                        self.itemList[pkg_name] = {
                            'pkg' : pkg, 'item' : item
                            }
                        if not self.update_only:
                            item.addCell(" ")
                            self._setStatusToItem(pkg,item)

        if filter == 'all' or filter == 'installed' or filter == 'skip_other':
            installed = self.backend.get_packages('installed')
            for pkg in installed :
                insert_items = _is_package_in_selected_group(pkg)

                if insert_items :
                    skip_insert = (filter == 'skip_other' and not (pkg.arch == 'noarch' or pkg.arch == machine_arch))
                    if not skip_insert :
                        item = self._createCBItem(self.packageQueue.checked(pkg),
                                           pkg.name,
                                           pkg.summary,
                                           pkg.version,
                                           pkg.release,
                                           pkg.arch,
                                           pkg.sizeM)
                        pkg_name = pkg.fullname
                        if sel_pkg :
                            if sel_pkg.fullname == pkg_name :
                                item.setSelected(True)
                        self.itemList[pkg_name] = {
                            'pkg' : pkg, 'item' : item
                            }
                        if not self.update_only:
                            item.addCell(" ")
                            self._setStatusToItem(pkg,item)

        if filter == 'all' or filter == 'not_installed' or filter == 'skip_other':
            installed_pkgs = {}
            if self.packageActionValue == const.Actions.DOWNGRADE:
               installed = self.backend.get_packages('installed')
               installed_pkgs = {p.name:p for p in installed}

            available = self.backend.get_packages('available')
            for pkg in available :
                insert_items = _is_package_in_selected_group(pkg)
                # if looking for downgrade we must add only the available that are installed and not upgrades
                if self.packageActionValue == const.Actions.DOWNGRADE:
                  if pkg.name not in installed_pkgs:
                    insert_items = False
                  elif pkg.fullname >= installed_pkgs[pkg.name].fullname:
                     insert_items = False

                if insert_items :
                    skip_insert = (filter == 'skip_other' and not (pkg.arch == 'noarch' or pkg.arch == machine_arch))
                    if not skip_insert :
                        item = self._createCBItem(self.packageQueue.checked(pkg),
                                           pkg.name,
                                           pkg.summary,
                                           pkg.version,
                                           pkg.release,
                                           pkg.arch,
                                           pkg.sizeM)
                        pkg_name = pkg.fullname
                        if sel_pkg :
                            if sel_pkg.fullname == pkg_name :
                                item.setSelected(True)
                        self.itemList[pkg_name] = {
                            'pkg' : pkg, 'item' : item
                            }
                        if not self.update_only:
                            item.addCell(" ")
                            self._setStatusToItem(pkg,item)

        keylist = sorted(self.itemList.keys())
        v = []
        for key in keylist :
            item = self.itemList[key]['item']
            v.append(item)

        #NOTE workaround to get YItemCollection working in python
        itemCollection = v

        #self.packageList.startMultipleChanges()
        # cleanup old changed items since we are removing all of them
        #self.packageList.setChangedItem(None)
        self.packageList.deleteAllItems()
        self.packageList.addItems(itemCollection)
        #self.packageList.doneMultipleChanges()
        MUI.YUI.app().normalCursor()

    def _viewNameSelected(self):
        '''
        return the view_box name index from the selected view
        '''
        sel = self.view_box.selectedItem()
        view = 'groups'
        ordered_views = [ 'groups', 'all' ]
        for v in ordered_views:
            if self.views[v]['item'] == sel :
                return v

        return view

    def _filterNameSelected(self) :
        '''
        return the filter name index from the selected filter e.g.
        'all', 'installed', 'to_update', 'not_installed' or 'skip other'
        '''
        filter = 'all'
        sel = self.filter_box.selectedItem()
        if sel:
            for k in self.filters.keys():
                if self.filters[k]['item'] == sel:
                    return k

        return filter

    def _groupNameFromItem(self, group, treeItem) :
        '''
        return the group name to be used for a search by group
        '''
        # TODO check type MUI.YTreeItem?
        for g in group.keys() :
            if g == 'name' or g == 'item' :
                continue
            node = group.get(g, {})
            item = node.get('item')
            if item == treeItem :
                return node.get('name')
            elif item and item.hasChildren():
                gName = self._groupNameFromItem(node, treeItem)
                if gName :
                    return gName

        return None

    def _collect_groups_for_tree(self, view_name, filter_name):
        """Return normalized group names for the left tree according to view and filter."""
        if view_name == 'all':
            return ['All']

        if filter_name == 'to_update':
            logger.debug("Collecting groups from update packages")
            package_scope = 'updates'
        elif filter_name == 'installed':
            logger.debug("Collecting groups from installed packages")
            package_scope = 'installed'
        elif filter_name == 'not_installed':
            logger.debug("Collecting groups from available packages")
            package_scope = 'available'
        else:
            logger.debug("Collecting all groups from backend cache")
            try:
                return sorted(g for g in (self.backend.get_groups() or []) if isinstance(g, str) and g)
            except Exception as error:
                logger.exception("Cannot read group cache from backend: %s", error)
                return []

        try:
            packages = self.backend.get_packages(package_scope)
        except Exception as error:
            logger.exception("Cannot load packages for scope '%s': %s", package_scope, error)
            return []

        if self.use_comps:
            pkg_names = [pkg.name for pkg in packages if getattr(pkg, 'name', None)]
            if not pkg_names:
                return []
            try:
                groups = self.backend.GetGroupsFromPackage(pkg_names, sync=True) or []
            except Exception as error:
                logger.exception("Cannot map comps groups from %d packages: %s", len(pkg_names), error)
                return []
            return sorted(g for g in groups if isinstance(g, str) and g)

        group_set = set()
        for pkg in packages:
            try:
                package_groups = self.backend.get_groups_from_package(pkg) or []
            except Exception as error:
                logger.exception("Cannot map groups for package '%s': %s", getattr(pkg, 'name', '<unknown>'), error)
                continue
            for grp in package_groups:
                if isinstance(grp, str) and grp:
                    group_set.add(grp)

        return sorted(group_set)

    def _rebuildPackageListWithSearchGroup(self):
      '''
      Next code is used to check if the package list must be rebuilt in
      the case of an active search result
      '''
      rebuild_package_list = False
      sel = self.tree.selectedItem()
      if sel :
        group = self._groupNameFromItem(self.groupList, sel)
        if (group == "Search"):
          rebuild_package_list = not self._searchPackages()
        else:
          rebuild_package_list = True
      return rebuild_package_list

    def _fillGroupTree(self) :
        '''
        fill the group tree, look for the retrieved groups and set their icons
        from groupicons module
        '''

        self.groupList = {}
        rpm_groups = []
        MUI.YUI.app().busyCursor()
        try:
            view = self._viewNameSelected()
            filter_name = self._filterNameSelected()
            rpm_groups = self._collect_groups_for_tree(view, filter_name)

            if not rpm_groups:
                logger.info("No groups found for view='%s' filter='%s'; using Empty placeholder", view, filter_name)
                rpm_groups = ['Empty']

            groups = self.gIcons.groups

            for group_path in rpm_groups:
                # Build tree path X/Y/Z...
                currG = groups
                currT = self.groupList
                subGroups = [part for part in group_path.split("/") if part]
                parentItem = None
                fullGroupName = None

                if not subGroups:
                    logger.debug("Skipping invalid empty group path: '%s'", group_path)
                    continue

                for subgroup in subGroups:
                    fullGroupName = subgroup if fullGroupName is None else "%s/%s" % (fullGroupName, subgroup)
                    icon = self.gIcons.icon(fullGroupName)

                    if subgroup in currG:
                        currG = currG[subgroup]
                        title = currG.get("title", subgroup)
                        if title in currT:
                            currT = currT[title]
                            parentItem = currT.get("item")
                        else:
                            item = MUI.YTreeItem(parent=parentItem, label=title, icon_name=icon) if parentItem else MUI.YTreeItem(label=title, icon_name=icon)
                            currT[title] = {"item": item, "name": fullGroupName}
                            currT = currT[title]
                            parentItem = item
                    else:
                        # Group is not in our predefined metadata; keep backend-provided label.
                        if subgroup in currT:
                            currT = currT[subgroup]
                            parentItem = currT.get("item")
                        else:
                            item = MUI.YTreeItem(parent=parentItem, label=subgroup, icon_name=icon) if parentItem else MUI.YTreeItem(label=subgroup, icon_name=icon)
                            currT[subgroup] = {"item": item, "name": fullGroupName}
                            currT = currT[subgroup]
                            parentItem = item

            logger.debug("Found %d groups for tree", len(rpm_groups))

            keylist = sorted(self.groupList.keys())
            items = []
            for key in keylist:
                group_item = self.groupList[key].get('item')
                if group_item:
                    items.append(group_item)

            if items:
                items[0].setSelected(True)

            #self.tree.startMultipleChanges()
            self.tree.deleteAllItems()
            #self.tree.doneMultipleChanges()
            self.tree.addItems(items)
        finally:
            MUI.YUI.app().normalCursor()


    def _formatLink(self, description, url) :
        '''
        @param description: Description to be shown as link
        @param url: to be reach when click on $description link
        returns href string to be published
        '''
        webref = '<a href="%s">%s</a>'%(url, description)

        return webref

    def _setInfoOnWidget(self, pkg) :
        """
        writes package description into info widget
        """
        self.info.setValue("")
        if pkg :
            missing = _("Missing information")
            description = escape(pkg.description).replace("\n", "<br>") if pkg.description else ''
            s = "<h2> %s - %s </h2>%s" %(pkg.name, pkg.summary, description)
            s += "<br>"
            if pkg.is_update :
                s+= '<br><b>%s</b>'%self._formatLink(self.infoshown['updateinfo']['title'], 'updateinfo')
                s += "<br>"
                if self.infoshown['updateinfo']["show"]:
                    advisory = pkg.updateinfo
                    # chosen attributes: ['advisoryid', 'name', 'title', 'description', 'type', 'severity'. 'message']
                    if advisory and len(advisory) > 0:
                        s+= '<b>%s</b>: %s'%(advisory[0]['advisoryid'], escape(advisory[0]['title']).replace("\n", "<br>"))
                        s += "<br>"
                        s += '<b>%s</b>'%escape(advisory[0]['title']).replace("\n", "<br>")
                        s += "<br>"
                        s += escape(advisory[0]['description']).replace("\n", "<br>")
                        s += "<br>"
                        s += '%s: <b>%s</b> - %s: <b>%s</b>'%(_("Type"), advisory[0]['type'], _("Severity"), advisory[0]['severity'])
                        if len(advisory[0]['message'])>0:
                            s+= "<br>%s"%(escape(advisory[0]['message']).replace("\n", "<br>"))
                    else :
                        s+= missing
                    s += "<br>"

            if pkg.repository:
                s += "<br>"
                s += '<b> %s: %s</b>'%(_("Repository"), pkg.repository)
                s += "<br>"

            if pkg.URL:
                s += "<br>"
                s += '<b><a href="%s">%s</a></b>'%(pkg.URL, pkg.URL)
                s += "<br>"

            t = 'requirements'
            s += "<br>"
            s += '<b>%s</b>'%self._formatLink(self.infoshown[t]['title'], t)
            s += "<br>"
            if self.infoshown[t]["show"]:
                if pkg.requirements :
                    s+= "<br>".join(pkg.requirements)
                else:
                    s+= missing
                s += "<br>"

            t = 'files'
            s += "<br>"
            s += '<b>%s</b>'%self._formatLink(self.infoshown[t]['title'], t)
            s += "<br>"
            if self.infoshown[t]["show"]:
                if pkg.filelist :
                    s+= "<br>".join(pkg.filelist)
                else:
                    s+= missing
                s += "<br>"

            t = 'changelog'
            s += "<br>"
            s += '<b>%s</b>'%self._formatLink(self.infoshown[t]['title'], t)
            s += "<br>"
            if self.infoshown[t]["show"]:
                if pkg.changelog:
                    for c in pkg.changelog:
                      s1 = ("<br>%s - %s<br>%s"%(datetime.datetime.fromtimestamp(c[0]), c[1], c[2])).replace("\n", "<br>")
                      s+= s1
                else:
                    s+= missing
                s += "<br>"
            self.info.setValue(s)
        else:
          logger.warning("_setInfoOnWidget without package")

    def _showErrorAndContinue(self, title, error):
      '''
      Shows an error dialog box and continue to work, it supposes error is not critical
      (i.e. a wrong search for instance)
      '''
      dialogs.warningMsgBox({'title' : title, "text": error, "richtext":True})
      self._enableAction(True)

    def _showSearchResult(self, packages, createTreeItem=False):
      '''
      Shows search result package list on package view
      if createTreeItem is True clears the table and rebuilds item list
      '''
      sel_pkg = self._selectedPackage()

      #clean up tree
      if createTreeItem:
          self._fillGroupTree()

      filter = self._filterNameSelected()
      self.itemList = {}
      # {
      #   name-epoch_version-release.arch : { pkg: dnf-pkg, item: YItem}
      # }

      # Package API doc: http://dnf.readthedocs.org/en/latest/api_package.html
      for pkg in packages:
        if (filter == 'all' or (filter == 'to_update' and pkg.is_update ) or (filter == 'installed' and pkg.installed) or
            (filter == 'not_installed' and not pkg.installed) or
            (filter == 'skip_other' and (pkg.arch == 'noarch' or pkg.arch == platform.machine()))) :
            item = self._createCBItem(self.packageQueue.checked(pkg),
                                           pkg.name,
                                           pkg.summary,
                                           pkg.version,
                                           pkg.release,
                                           pkg.arch,
                                           pkg.sizeM)
            pkg_name = pkg.fullname
            if sel_pkg :
                if sel_pkg.fullname == pkg_name :
                    item.setSelected(True)
            self.itemList[pkg_name] = {
                'pkg' : pkg, 'item' : item
                }
            if not self.update_only:
                item.addCell(" ")
                self._setStatusToItem(pkg,item)

      keylist = sorted(self.itemList.keys())
      v = []
      for key in keylist :
          item = self.itemList[key]['item']
          v.append(item)

      itemCollection = v

      #self.packageList.startMultipleChanges()
      # cleanup old changed items since we are removing all of them
      #self.packageList.setChangedItem(None)
      self.packageList.deleteAllItems()
      self.packageList.addItems(itemCollection)
      #self.packageList.doneMultipleChanges()

      if createTreeItem:
          #self.tree.startMultipleChanges()
          icon = self.gIcons.icon("Search")
          treeItem = MUI.YTreeItem(label=self.gIcons.groups['Search']['title'], icon_name=icon, selected=False)
          treeItem.setSelected(True)
          self.groupList[self.gIcons.groups['Search']['title']] = { "item" : treeItem, "name" : "Search" }
          self.tree.addItem(treeItem)
          #self.tree.doneMultipleChanges()
          #self.tree.rebuildTree()

      self._enableAction(True)


    def _searchPackages(self) :
        '''
        retrieves the info from search input field and from the search type list
        to perform a package research and to fill the package list widget

        return False if an empty string used
        '''

        type_item = self.search_list.selectedItem()
        #fields = []
        #for field in self.local_search_types.keys():
            #if self.local_search_types[field]['item'] == type_item:
                #fields.append(field)
                #break
        fields = [ field for field in self.local_search_types.keys() if self.local_search_types[field]['item'] == type_item ]
        field = fields[0] if fields else None

        if field == 'name' or field == 'summary':
          self.use_regexp.setEnabled()
        else:
          self.use_regexp.setChecked(False)
          self.use_regexp.setEnabled(False)

        search_string = self.find_entry.value().strip()
        if not search_string :
          return False

        filters = {
            'installed'     : 'installed',
            'not_installed' : 'available',
            'to_update'     : 'upgrades',
            'all'           : 'all',
            'skip_other'    : 'all',
        }
        filter = filters[self._filterNameSelected()]
        if self.use_regexp.isEnabled() and self.use_regexp.isChecked() :
          # fixing attribute names
          if field == 'name' :
            field = 'fullname'
          self.backend.search(filter, field, search_string)
        else:
          strings = [s for s in re.split('[ ,|:;]',search_string) if s]
          if self.fuzzy_search:
             strings = [s.join(["*","*"]) for s in strings]

          options = {
            "scope": filter,
            "with_binaries": field == 'file',
            "with_filenames": field == 'file',
            "with_nevra" : field == 'name',
            #"with_provides" : False,
            #"with_src" : False,
            "patterns": strings
          }

          #['name', 'summary', 'description', 'file' ]
          ### TODO how to manage mach_all, newest_only, summary and description????
          self.backend.Search(options)

        self._enableAction(False)

        return True

    def _populate_transaction(self) :
        '''
          Populate a transaction
        '''
        if self.packageActionValue == const.Actions.NORMAL:
            for action in const.QUEUE_PACKAGE_TYPES.keys():
                pkg_ids = self.packageQueue.get(action)
                if len(pkg_ids) >0:
                    pkgs = [dnfdragora.misc.pkg_id_to_full_nevra(pkg_id) for pkg_id in pkg_ids]
                    logger.debug('adding: %s %s' %(const.QUEUE_PACKAGE_TYPES[action], pkgs))
                    if action == 'i':
                        self.backend.Install(pkgs, sync=True)
                    elif action == 'u':
                        self.backend.Update(pkgs, sync=True)
                    elif action == 'r':
                        self.backend.Remove(pkgs, sync=True)
                    else:
                        logger.error('Action %s not managed' % (action))
        elif self.packageActionValue == const.Actions.REINSTALL:
            pkg_ids = self.packageQueue.get('r')
            if len(pkg_ids) >0:
                pkgs = [dnfdragora.misc.pkg_id_to_full_nevra(pkg_id) for pkg_id in pkg_ids]
                logger.debug('Reinstalling %s' %(pkgs))
                self.backend.Reinstall(pkgs, sync=True)
        elif self.packageActionValue == const.Actions.DOWNGRADE:
            pkg_ids = self.packageQueue.get('i')
            if len(pkg_ids) >0:
                pkgs = [dnfdragora.misc.pkg_id_to_full_nevra(pkg_id) for pkg_id in pkg_ids]
                logger.debug('Downgrading %s' %(pkgs))
                self.backend.Downgrade(pkgs, sync=True)
        elif self.packageActionValue == const.Actions.DISTRO_SYNC:
            pkg_ids = self.packageQueue.get('r')
            pkgs=[]
            if len(pkg_ids) >0:
                pkgs.extend([ dnfdragora.misc.to_pkg_tuple(pkg_id)[0] for pkg_id in pkg_ids])
            pkg_ids = self.packageQueue.get('u')
            if len(pkg_ids) >0:
                pkgs.extend([dnfdragora.misc.to_pkg_tuple(pkg_id)[0] for pkg_id in pkg_ids])
            logger.debug('Distro Sync %s' %(pkgs))
            self.backend.DistroSync(pkgs, sync=True)

    def _undo_transaction(self):
        '''
        Run the undo transaction
        '''
        locked = False
        performedUndo = False
        sync = True

        try:
            rc, result = self.backend.GetTransaction(sync)
            if rc :
                transaction_result_dlg = dialogs.TransactionResult(self)
                ok = transaction_result_dlg.run(result)

                if ok:  # Ok pressed
                    self.infobar.info(_('Undo transaction'))
                    rc, result = self.backend.RunTransaction(sync)
                    # This can happen more than once (more gpg keys to be
                    # imported)
                    while rc == 1:
                        logger.debug('GPG key missing: %s' % repr(result))
                        # get info about gpgkey to be confirmed
                        values = self.backend._gpg_confirm
                        if values:  # There is a gpgkey to be verified
                            (pkg_id, userid, hexkeyid, keyurl, timestamp) = values
                            logger.debug('GPGKey : %s' % repr(values))
                            resp = dialogs.ask_for_gpg_import(values)
                            self.backend.ConfirmGPGImport(hexkeyid, resp, sync)
                            # tell the backend that the gpg key is confirmed
                            # rerun the transaction
                            # FIXME: It should not be needed to populate
                            # the transaction again
                            if resp:
                                rc, result = self.backend.GetTransaction(sync)
                                rc, result = self.backend.RunTransaction(sync)
                            else:
                                # NOTE TODO answer no is the only way to exit, since it seems not
                                # to install the key :(
                                break
                        else:  # error in signature verification
                            dialogs.infoMsgBox({'title' : _('Error checking package signatures'),
                                                'text' : '<br>'.join(result), 'richtext' : True })
                            break
                    if rc == 4:  # Download errors
                        dialogs.infoMsgBox({'title'  : ngettext('Downloading error',
                            'Downloading errors', len(result)), 'text' : '<br>'.join(result), 'richtext' : True })
                        logger.error('Download error')
                        logger.error(result)
                    elif rc != 0:  # other transaction errors
                        dialogs.infoMsgBox({'title'  : ngettext('Error in transaction',
                                    'Errors in transaction', len(result)), 'text' :  '<br>'.join(result), 'richtext' : True })
                        logger.error('RunTransaction failure')
                        logger.error(result)

                    self.release_root_backend()
                    self.backend.reload()
                    performedUndo = (rc == 0)
            else:
                logger.error('BuildTransaction failure')
                logger.error(result)
                s = "%s"%result
                dialogs.warningMsgBox({'title' : _("Build transaction failure"), "text": s, "richtext":True})
        #except dnfdaemon.client.AccessDeniedError as e:
        #    logger.error("dnfdaemon client AccessDeniedError: %s ", e)
        #    dialogs.warningMsgBox({'title' : _("Build transaction failure"), "text": _("dnfdaemon client not authorized:%(NL)s%(error)s")%{'NL': "\n",'error' : str(e)}})
        except Exception as err:
          exc, msg = misc.parse_dbus_error()
          if 'AccessDeniedError' in exc:
            logger.warning("User pressed cancel button in policykit window")
            logger.warning("dnfdaemon client AccessDeniedError: %s ", msg)
          else:
            logger.exception("Unexpected error while undoing transaction: %s", err)

        return performedUndo


    def saveUserPreference(self):
        '''
        Save user preferences on exit and view layout if needed.
        The view-state update (filter/view widgets) is guarded with try/except
        so that failures in popup-dialog context (widget not accessible) do not
        prevent the actual YAML file write.
        '''
        try:
            filter = self._filterNameSelected()
            view = self._viewNameSelected()
            self.config.userPreferences['view'] = {
                'show': view,
                'filter': filter
                }

            search = {
                'fuzzy_search': self.fuzzy_search,
                'newest_only': self.newest_only
              }

            if 'settings' in self.config.userPreferences.keys() :
                settings = self.config.userPreferences['settings']
                settings['search'] = search
                if 'show updates at startup' in settings.keys() :
                    if settings['show updates at startup'] :
                        self.config.userPreferences['view']['filter'] = 'to_update'
                if 'do not show groups at startup' in settings.keys():
                    if settings['do not show groups at startup'] :
                        self.config.userPreferences['view']['show'] = 'all'
        except Exception:
            logger.exception("saveUserPreference: could not collect view/search state; settings will still be saved")
        self.config.saveUserPreferences()

    def _load_history(self, transactions):
        '''
        Load history and populate view.
        Args:
            list of (transaction is, date-time) pairs
        '''
        hw = dialogs.HistoryView(self)
        undo = hw.run(transactions)
        hw = None
        return undo

    def _updateActionView(self, newAction):
        '''
            Prepare the dnfdragora view according to the selected new action.
            Remove any selections if the  action is changed (easy way to manage new action)
            Force to rebuild the view if action is changed (easy way to manage new action)
            Args:
                newAction: action to be peroform on selected packages
            Returns:
                if packages view needs to be rebuilt
        '''
        rebuild_package_list = False
        if newAction != self.packageActionValue:
            rebuild_package_list = True
            self.packageActionValue = newAction
            ordered_filters = None
            # reset any old selection to simplfy
            self.packageQueue.clear()
            #1. Changing Filters
            filter_item = 'installed' #default
            enable_select_all = False
            apply_button_text = _("&Apply")
            enable_apply_button = False
            if newAction == const.Actions.NORMAL:
                disable_select_all = True
                #let's get back the last saved filter for NORMAL actions
                filter_item = self.config.userPreferences['view']['filter']
                ordered_filters = [ 'all', 'installed', 'to_update', 'not_installed' ]
                if platform.machine() == "x86_64" :
                    ordered_filters.append('skip_other')
            elif newAction == const.Actions.DOWNGRADE:
                ordered_filters = [ 'not_installed' ]
                filter_item = 'not_installed'
                apply_button_text = _("&Downgrade")
            elif newAction == const.Actions.REINSTALL:
                ordered_filters = [ 'installed' ]
                apply_button_text = _("&Reinstall")
            elif newAction == const.Actions.DISTRO_SYNC:
                ordered_filters = [ 'installed', 'to_update' ]
                apply_button_text = _("&Distro Sync")
                #distro sync can ber run without any file selected (sync all)
                enable_apply_button = True
                if self.update_only:
                    filter_item = 'to_update'

            for f in self.filters:
                self.filters[f]['item'] = None

            itemColl = []
            for f in ordered_filters:
                item = MUI.YItem(self.filters[f]['title'])
                if filter_item == f:
                    item.setSelected(True)
                # adding item to filters to find the item selected
                self.filters[f]['item'] = item
                itemColl.append(item)

            #self.filter_box.startMultipleChanges()
            self.filter_box.deleteAllItems()
            self.filter_box.addItems(itemColl)
            #self.filter_box.setEnabled(not self.update_only)
            #self.filter_box.doneMultipleChanges()

            # fixing groups
            view = self._viewNameSelected()
            filter = self._filterNameSelected()
            self._fillGroupTree()

            #Change Apply Button text accordingly
            self.applyButton.setLabel(apply_button_text)
            self.applyButton.setEnabled(enable_apply_button)
            #disable "select all" to avoid mistakes
            self.checkAllButton.setEnabled(enable_select_all)


        return rebuild_package_list

    def _event_loop_timeout(self):
      """Return the polling timeout used by the main AUI event loop."""
      if self._status in (
        DNFDragoraStatus.CACHING_AVAILABLE,
        DNFDragoraStatus.CACHING_UPDATE,
        DNFDragoraStatus.CACHING_INSTALLED,
      ):
        return 20
      return 200

    def _handle_menu_event(self, event):
      """Handle AUI menu events and return (rebuild_package_list, request_exit)."""
      rebuild_package_list = False
      request_exit = False

      item = event.item()
      if item:
        if item == self.fileMenu['reset_sel']:
          self.packageQueue.clear()
          rebuild_package_list = self._rebuildPackageListWithSearchGroup()
        elif item == self.fileMenu['reload']:
          self.backend.CleanCache()
        elif item == self.fileMenu['repos']:
          rd = dialogs.RepoDialog(self)
          rd.run()
        elif item == self.fileMenu['quit']:
          request_exit = True
        elif item == self.optionsMenu['user_prefs']:
          up = dialogs.OptionDialog(self)
          up.run()
        elif item == self.ActionMenu['actions']:
          actDlg = dialogs.PackageActionDialog(self, self.packageActionValue)
          newAction = actDlg.run()
          rebuild_package_list = self._updateActionView(newAction)
        elif item == self.helpMenu['help']:
          info = helpinfo.DNFDragoraHelpInfo()
          hd = helpdialog.HelpDialog(info)
          hd.run()
        elif item == self.helpMenu['about']:
          self.AboutDialog.run()
      else:
        # AUI menu events expose id() directly on the event for rich text links.
        url = getattr(event, 'id', lambda: None)()
        if url:
          logger.debug("Url selected: %s", url)
          if url in self.infoshown.keys():
            self.infoshown[url]["show"] = not self.infoshown[url]["show"]
            logger.debug("Info to show: %s", self.infoshown)
            sel_pkg = self._selectedPackage()
            self._setInfoOnWidget(sel_pkg)
            self._selPkg = sel_pkg
          else:
            logger.debug("run browser, URL: %s", url)
            webbrowser.open(url, 2)

      return rebuild_package_list, request_exit

    def _handle_widget_event(self, event):
      """Handle AUI widget events and return (rebuild_package_list, request_exit)."""
      rebuild_package_list = False
      request_exit = False
      widget = event.widget()

      if widget == self.quitButton:
        request_exit = True
      elif widget == self.packageList:
        if event.reason() == MUI.YEventReason.ValueChanged:
          changedItem = self.packageList.changedItem()
          if changedItem:
            for it in self.itemList:
              if self.itemList[it]['item'] == changedItem:
                pkg = self.itemList[it]['pkg']
                if pkg.installed and self.backend.protected(pkg):
                  dialogs.warningMsgBox({'title': _("Protected package selected"), "text": _("Package %s cannot be removed") % pkg.name, "richtext": True})
                  rebuild_package_list = self._rebuildPackageListWithSearchGroup()
                else:
                  # Checkbox is first column (0).
                  if changedItem.cell(0).checked():
                    if not self.packageQueue.checked(pkg):
                      self.packageQueue.add(pkg, 'u' if pkg.action == 'u' else 'i')
                  elif self.packageQueue.checked(pkg):
                    self.packageQueue.add(pkg, 'r')
                  self._setStatusToItem(pkg, self.itemList[it]['item'], True)
                break
        else:
          logger.debug("Package list selected, but no items changed")
      elif widget == self.reset_search_button:
        rebuild_package_list = True
        self.find_entry.setValue("")
        self._fillGroupTree()
      elif widget == self.find_button or widget == self.search_list or widget == self.use_regexp:
        if not self._searchPackages():
          rebuild_package_list = True
          self._fillGroupTree()
      elif widget == self.checkAllButton:
        for it in self.itemList:
          pkg = self.itemList[it]['pkg']
          self.packageQueue.add(pkg, 'u' if pkg.action == 'u' else 'i')
        rebuild_package_list = self._rebuildPackageListWithSearchGroup()
      elif widget == self.applyButton:
        # Disable actions while creating and running transaction.
        self._enableAction(False)
        self.pbar_layout.setEnabled(True)
        self._populate_transaction()
        self.backend.BuildTransaction()
      elif widget == self.view_box:
        filter = self._filterNameSelected()
        self.checkAllButton.setEnabled(filter == 'to_update')
        rebuild_package_list = True
        self.find_entry.setValue("")
        self._fillGroupTree()
      elif widget == self.tree:
        rebuild_package_list = True
        self.find_entry.setValue("")
      elif widget == self.filter_box:
        filter = self._filterNameSelected()
        self._fillGroupTree()
        self.checkAllButton.setEnabled(filter == 'to_update')
        rebuild_package_list = not self._searchPackages()
      else:
        logger.warning("Unmanaged widget event received")

      return rebuild_package_list, request_exit

    def _refresh_ui_after_event(self, rebuild_package_list):
      """Refresh package list and info panel after a single event is processed."""
      if rebuild_package_list:
        filter = self._filterNameSelected()
        search_string = self.find_entry.value()
        if not search_string:
          sel = self.tree.selectedItem()
          if sel:
            group = self._groupNameFromItem(self.groupList, sel)
            self._fillPackageList(group, filter)

      # Avoid sync GetAttribute calls while transaction is running.
      # The daemon can legitimately be busy and not answer metadata requests quickly.
      if self._status == DNFDragoraStatus.RUN_TRANSACTION:
        return

      sel_pkg = self._selectedPackage()
      if sel_pkg:
        if self._selPkg != sel_pkg:
          self._setInfoOnWidget(sel_pkg)
          self._selPkg = sel_pkg
      else:
        self.info.setValue("")

    def _sync_apply_button_state(self):
      """Keep Apply button enabled state consistent with queue and action mode."""
      if self.packageActionValue != const.Actions.DISTRO_SYNC:
        if self.packageQueue.total() > 0 and not self.applyButton.isEnabled():
          self.applyButton.setEnabled()
        elif self.packageQueue.total() == 0 and self.applyButton.isEnabled():
          self.applyButton.setEnabled(False)
      elif not self.applyButton.isEnabled():
        self.applyButton.setEnabled()

    def handleevent(self):
      """Main AUI event loop coordinating frontend and backend asynchronous events."""
      self.running = True
      while self.running:
        _active_dialog = (self._trans_dialog.dialog
                          if self._trans_dialog is not None else self.dialog)
        event = _active_dialog.waitForEvent(self._event_loop_timeout())
        eventType = event.eventType()

        rebuild_package_list = False
        request_exit = False

        if eventType == MUI.YEventType.CancelEvent:
          if self._trans_dialog is not None:
            self._close_trans_dialog()
            # Clean up download and transaction data
            self.__resetDownloads()
            #restore actions to Normal
            self._updateActionView(const.Actions.NORMAL)
            # TODO change UI and manage this better afer a transaction report        
            self.backend.clear_cache(also_groups=True)
            self.packageQueue.clear()
            self._status = DNFDragoraStatus.RESET_SESSION
            self._transaction_noreply_warned = False
            self._enableAction(False)
            # NOTE: do NOT call backend.ResetSession() here.
            # OnTransactionAfterComplete arrives as a D-Bus signal BEFORE the
            # RunTransaction D-Bus method reply, so _sent is still True at this
            # point. ResetSession would be rejected with "Command in progress".
            # The RunTransaction event handler below waits for the reply (which
            # clears _sent) and then issues ResetSession safely.
            rebuild_package_list = True
          else:
            request_exit = True
        elif eventType == MUI.YEventType.MenuEvent:
          if self._trans_dialog is None:
            rebuild_package_list, request_exit = self._handle_menu_event(event)
        elif eventType == MUI.YEventType.WidgetEvent:
          if self._trans_dialog is not None:
            if self._trans_dialog.handle_event(event):
              self._close_trans_dialog()
              # Clean up download and transaction data
              self.__resetDownloads()
              #restore actions to Normal
              self._updateActionView(const.Actions.NORMAL)
              # TODO change UI and manage this better afer a transaction report        
              self.backend.clear_cache(also_groups=True)
              self.packageQueue.clear()
              self._status = DNFDragoraStatus.RESET_SESSION
              self._transaction_noreply_warned = False
              self._enableAction(False)
              # NOTE: do NOT call backend.ResetSession() here.
              # OnTransactionAfterComplete arrives as a D-Bus signal BEFORE the
              # RunTransaction D-Bus method reply, so _sent is still True at this
              # point. ResetSession would be rejected with "Command in progress".
              # The RunTransaction event handler below waits for the reply (which
              # clears _sent) and then issues ResetSession safely.
              rebuild_package_list = True
          else:
            rebuild_package_list, request_exit = self._handle_widget_event(event)
        elif eventType == MUI.YEventType.TimeoutEvent:
          rebuild_package_list = self._manageDnfDaemonEvent()
          if rebuild_package_list:
            logger.debug("Rebuilding %s", rebuild_package_list)
            self._fillGroupTree()
        else:
          logger.warning("Unmanaged event type received: %s", eventType)

        if request_exit:
          self.running = False
          break

        self._refresh_ui_after_event(rebuild_package_list)
        self._sync_apply_button_state()

      # Save user prefs on exit
      self.saveUserPreference()

      if MUI.YUI.app().isTextMode():
        self.glib_loop.quit()

      self.dialog.destroy()

      try:
          self.backend.quit()
      except Exception as err:
        logger.exception("Exception on backend quit: %s", err)
      self.loop_has_finished = True

      self.backend.waitForLastAsyncRequestTermination()

      if MUI.YUI.app().isTextMode():
        self.glib_thread.join()

      #self.backend.quit()
      #self.backend.release_root_backend()

    def _show_trans_dialog(self):
        """Create the transaction progress dialog and hide the main window."""
        self._trans_dialog = progress_ui.TransactionProgressDialog(self)
        self._trans_dialog.open()

    def _close_trans_dialog(self):
        """Destroy the transaction progress dialog and restore the main window."""
        if self._trans_dialog is not None:
            self._trans_dialog.close()
            self._trans_dialog = None
        # Reset progress bar now that the main window is visible again
        self.infobar.reset_all()
        self.pbar_layout.setEnabled(True)

    def _OnRepoMetaDataProgress(self, name, frac):
      '''Repository Metadata Download progress.'''
      values = (name, frac)
      #print('on_RepoMetaDataProgress (root): %s', repr(values))
      logger.debug('OnRepoMetaDataProgress: %s', repr(values))
      if frac == 0.0:
        self.infobar.reset_all()
        self.infobar.info_sub(name)
      elif frac == 1.0:
        self.infobar.set_progress(1.0)
      else:
        self.infobar.set_progress(frac)

    def _OnTransactionEvent(self, event, data):
      ''' Manage a transaction event'''
      values = (event, data)
      logger.debug('OnTransactionEvent: %s', repr(values))
      if event == 'OnTransactionActionStart':
        self._transaction_noreply_warned = False
      elif event == 'OnTransactionAfterComplete' or event == 'OnTransactionTimeoutEvent':
        if self._trans_dialog is not None:
          self._trans_dialog.mark_complete(event == 'OnTransactionAfterComplete')
        else:
            logger.warning("Transaction complete event received, but transaction dialog is not open")

    def exception_handler(self, e):
      """Handle frontend exceptions; keep transaction alive on transient DBus NoReply."""
      msg = str(e)
      err, errmsg = self._parse_error(msg)
      if err == 'NoReply' and self._status == DNFDragoraStatus.RUN_TRANSACTION:
        if not self._transaction_noreply_warned:
          logger.warning("Transient DBus NoReply during RUN_TRANSACTION; keeping transaction alive")
          # TODO remove later
          dialogs.warningMsgBox({
            'title': _("Backend busy"),
            'text': _("The backend is busy processing the transaction. The operation will continue and progress events will still be tracked."),
            'richtext': False
          })
          self._transaction_noreply_warned = True
        return
      super().exception_handler(e)

    def _OnRPMProgress(self, package, action, te_current, te_total, ts_current, ts_total):
      ''' _OnRPMProgress manages RPM Progress event
          Parameters
            @param package:    package name
            @param action:     constant transaction set state (which ones?)
            @param te_current: current number of bytes processed in the transaction element being processed
            @param te_total:   total number of bytes in the transaction element being processed
            @param ts_current: number of processes completed in whole transaction
            @param ts_total:   total number of processes in the transaction.
      '''
      values = (package, action, te_current, te_total, ts_current, ts_total)
      if (te_current == 0 or te_current == te_total):
        logger.debug('OnRPMProgress: %s', repr(values))

      num = ' ( %i/%i )' % (ts_current, ts_total)
      if ',' in package:  # this is a pkg_id
        name = dnfdragora.misc.pkg_id_to_full_name(package)
      else:  # this is just a pkg name (cleanup)
        name = package

      if (not self._package_name or name != self._package_name or self._action_name != action):
        #let's log once
        logger.debug('OnRPMProgress : [%s]', package)
        self._package_name = name
        self._action_name = action
        try:
          self.infobar.info_sub(const.RPM_ACTIONS[action] % name)
        except KeyError:
          logger.error('OnRPMProgress: unknown action %s', action)
          self.infobar.info_sub(_("Unknown action %(action)s on %(name)s")%({'action':action, 'name':name}))

      if te_current > 0 and te_current <= te_total:
          frac = float(te_current) / float(te_total)
          self.infobar.set_progress(frac, label=num)

    def _OnGPGImport(self, session_object_path, key_id, user_ids, key_fingerprint, key_url, timestamp):
        values = (key_id, user_ids, key_fingerprint, key_url, timestamp)
        self._gpg_confirm = values
        logger.debug('OnGPGImport(%s) - %s', session_object_path, repr(values))
        # get info about gpgkey to be comfirmed
        if values:  # There is a gpgkey to be verified
            logger.debug('GPGKey : %s' % repr(values))
            resp = dialogs.ask_for_gpg_import(values)
            self.backend.ConfirmGPGImport(key_id, resp, sync=True)

    def _OnTransactionVerifyStart(self, session_object_path, total):
      '''
        Transaction verification start.
        Args:
            @session_object_path: object path of the dnf5daemon session
            @total: total to process
      '''
      values = (session_object_path, total)
      logger.debug('OnTransactionVerifyStart: %s', repr(values))
      if session_object_path != self.backend.session_path :
        logger.warning("OnTransactionVerifyStart: Different session path received")
        return
      if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
          self._trans_dialog.on_verify_start(total)
      else:
        self.infobar.set_progress(0.0)
        self.infobar.info(_('Transaction verification'))

    def _OnTransactionVerifyProgress(self, session_object_path, processed, total):
      '''
        Transaction verification in progress.
        Args:
            @session_object_path: object path of the dnf5daemon session
            @processed: amount already processed
            @total: total to process
      '''
      if session_object_path != self.backend.session_path :
          logger.warning("_OnTransactionVerifyProgress: Different session path received")
          return
      total_frac = processed / total if total > 0 else 0
      if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
          self._trans_dialog.on_verify_progress(processed, total)
      else:
        self.infobar.set_progress(total_frac)

    def _OnTransactionVerifyStop(self, session_object_path, total):
      '''
        Transaction verification has finished
        Args:
            @session_object_path: object path of the dnf5daemon session
            @total: total to process
      '''
      values = (session_object_path, total)
      logger.debug('OnTransactionVerifyStop: %s', repr(values))
      if session_object_path != self.backend.session_path :
        logger.warning("OnTransactionVerifyStop: Different session path received")
        return
      if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
          self._trans_dialog.on_verify_stop(total)
      else:
        self.infobar.reset_all()

    def _OnTransactionActionStart(self, session_object_path, nevra, action, total):
        '''
            Processing (installation or removal) of the package has started.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @nevra: full NEVRA of the package
                @action: one of the dnfdaemon::RpmTransactionItem::Actions enum
                @total: total to process
        '''
        #TODO how to get string from action and maybe localized?
        act_str = libdnf5.base.transaction.transaction_item_action_to_string(action)
        values = (session_object_path, nevra, action, act_str, total)
        logger.debug('OnTransactionActionStart: %s', repr(values))
        if session_object_path != self.backend.session_path :
            logger.warning("OnTransactionActionStart: Different session path received")
            return
        if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
            self._trans_dialog.on_action_start(nevra, act_str)
        else:
            self.infobar.set_progress(0.0)
            self.infobar.info( _('Transaction for package <%(nevra)s> started') %{'nevra': nevra })

    def _OnTransactionActionProgress(self, session_object_path, nevra, processed, total):
        '''
            Progress in processing of the package.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @nevra: full NEVRA of the package
                @processed: amount already processed
                @total: total to process
        '''
        values = (session_object_path, nevra, processed, total)
        logger.debug('OnTransactionActionProgress: %s', repr(values))
        if session_object_path != self.backend.session_path :
            logger.warning("OnTransactionActionProgress: Different session path received")
            return
        #TODO bar with processed??? if not always 0 self.infobar.set_progress(0.0)
        if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
            self._trans_dialog.on_action_progress(nevra, processed, total)
        else:
            self.infobar.info( _('Transaction for package <%(nevra)s> in progress') %{'nevra': nevra, })

    def _OnTransactionActionStop(self, session_object_path, nevra, total):
        '''
            Processing of the item has finished.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @nevra: full NEVRA of the package
                @total: total processed
        '''
        values = (session_object_path, nevra, total)
        logger.debug('OnTransactionActionStop: %s', repr(values))
        if session_object_path != self.backend.session_path :
            logger.warning("OnTransactionActionStop: Different session path received")
            return
        if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
            self._trans_dialog.on_action_stop(nevra)
        else:
            self.infobar.reset_all()

    def _OnTransactionElemProgress(self, session_object_path, nevra, processed, total):
        """
        Overall progress in transaction item processing. Called right before an item is processed.
        Args:
            @session_object_path: object path of the dnf5daemon session
            @nevra: full NEVRA of the package
            @processed: amount already processed (starting from 0, just before it is processed)
            @total: total to process
        """
        values = (session_object_path, nevra, total)
        logger.debug('OnTransactionElemProgress: %s', repr(values))
        if session_object_path != self.backend.session_path :
            logger.warning("OnTransactionElemProgress: Different session path received")
            return
        total_frac = (processed+1) / total if total > 0 else 0
        if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
            self._trans_dialog.on_elem_progress(nevra, processed, total)
        else:
            self.infobar.set_progress(total_frac)
            self.infobar.info( _('Transaction in progress: <%(nevra)s> starts') %{'nevra': nevra, })

    def _OnTransactionTransactionStart(self, session_object_path, total):
        '''
            Preparation of transaction packages has started.
            Manages the transaction_transaction_start signal.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @total: total to process
        '''
        values = (session_object_path, total)
        logger.debug('OnTransactionTransactionStart: %s', repr(values))
        if session_object_path != self.backend.session_path :
            logger.warning("OnTransactionTransactionStart: Different session path received")
            return
        if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
            self._trans_dialog.on_transaction_start(total)
        else:
            self.infobar.set_progress(0.0)
            self.infobar.info( _('Preparation of transaction'))

    def _OnTransactionTransactionProgress(self, session_object_path, processed, total):
        '''
            Progress in preparation of transaction packages.
            Manages the transaction_transaction_progress signal.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @processed: amount already processed
                @total: total to process
        '''
        values = (session_object_path, processed, total)
        logger.debug('OnTransactionTransactionProgress: %s', repr(values))
        if session_object_path != self.backend.session_path :
            logger.warning("OnTransactionTransactionProgress: Different session path received")
            return
        total_frac = processed / total if total > 0 else 0
        if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
            self._trans_dialog.on_transaction_progress(processed, total)
        else:
            self.infobar.set_progress(total_frac)
            self.infobar.info( _('Preparation of transaction'))

    def _OnTransactionTransactionStop(self, session_object_path, total):
        '''
            Preparation of transaction packages has finished.
            Manages thetransaction_transaction_stop signal.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @total: total to process
        '''
        values = (session_object_path, total)
        logger.debug('OnTransactionTransactionStop: %s', repr(values))
        if session_object_path != self.backend.session_path :
            logger.warning("OnTransactionTransactionStop: Different session path received")
            return
        if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
            self._trans_dialog.on_transaction_stop(total)
        else:
            self.infobar.reset_all()

    def _OnTransactionScriptStart(self, session_object_path, nevra, scriptlet_type):
        '''
            The scriptlet has started.
            Manages the transaction_script_start signal.
            Args:
            @session_object_path: object path of the dnf5daemon session
            @nevra: full NEVRA of the package script belongs to
            @scriptlet_type: scriptlet type that started (pre, post,...)
        '''
        '''
        TODO scriptlet type to show in the progress bar
            class LIBDNF_API TransactionCallbacks {
            public:
                enum class ScriptType {
                    UNKNOWN,
                    PRE_INSTALL,            // "%pre"
                    POST_INSTALL,           // "%post"
                    PRE_UNINSTALL,          // "%preun"
                    POST_UNINSTALL,         // "%postun"
                    PRE_TRANSACTION,        // "%pretrans"
                    POST_TRANSACTION,       // "%posttrans"
                    TRIGGER_PRE_INSTALL,    // "%triggerprein"
                    TRIGGER_INSTALL,        // "%triggerin"
                    TRIGGER_UNINSTALL,      // "%triggerun"
                    TRIGGER_POST_UNINSTALL  // "%triggerpostun"
                };

                /// @param type  scriptlet type
                /// @return  string representation of the scriptlet type
                static const char * script_type_to_string(ScriptType type) noexcept;
        '''
        scriptletType=libdnf5.rpm.TransactionCallbacks.script_type_to_string(scriptlet_type)
        values = (session_object_path,nevra, scriptlet_type, scriptletType)
        logger.debug('OnTransactionScriptStart: %s', repr(values))
        if session_object_path != self.backend.session_path :
            logger.warning("OnTransactionScriptStart: Different session path received")
            return

        if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
            self._trans_dialog.on_script_start(nevra, scriptletType)
        else:
            self.infobar.set_progress(0.0)
            self.infobar.info( _('Scriptlet <%(nevra)s> started') %{'nevra': nevra, })

    def _OnTransactionScriptStop(self, session_object_path, nevra, scriptlet_type, return_code):
        '''
            The scriptlet has successfully finished.
            Manages the transaction_script_stop signal.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @nevra: full NEVRA of the package script belongs to
                @scriptlet_type: scriptlet type that started (pre, post,...)
                @return_code: return value of the script
        '''
        scriptletType=libdnf5.rpm.TransactionCallbacks.script_type_to_string(scriptlet_type)
        values = (session_object_path,nevra, scriptlet_type, scriptletType, return_code)
        logger.debug('OnTransactionScriptStop: %s', repr(values))
        if session_object_path != self.backend.session_path :
            logger.warning("OnTransactionScriptStop: Different session path received")
            return
        if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
            self._trans_dialog.on_script_stop(nevra, scriptletType, return_code)
        else:
            self.infobar.reset_all()

    def _OnTransactionScriptError(self, session_object_path, nevra, scriptlet_type, return_code):
        '''
            The scriptlet has finished with an error.
            Manages the transaction_script_error signal.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @nevra: full NEVRA of the package script belongs to
                @scriptlet_type: scriptlet type that started (pre, post,...)
                @return_code: return value of the script
        '''
        scriptletType=libdnf5.rpm.TransactionCallbacks.script_type_to_string(scriptlet_type)
        values = (session_object_path,nevra, scriptlet_type, scriptletType, return_code)
        logger.error('_OnTransactionScriptError: %s', repr(values))
        if session_object_path != self.backend.session_path :
            logger.warning("_OnTransactionScriptError: Different session path received")
            return
        if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
            self._trans_dialog.on_script_error(nevra, scriptletType, return_code)
        else:
            self.infobar.reset_all()

    def __addDownload(self, download_id, description, total_to_download):
      '''
          add new download events
      '''
      downloads = self._download_events['downloads']
      if download_id in downloads.keys():
        logger.warning("ID %s is already present", download_id)
        if description != downloads[download_id]['description']:
          logger.warning("Probably overriding an old value %s with %s",
                         downloads[download_id]['description'], description)
      downloads[download_id] = {
        'description'       : description,
        'downloaded'        : 0,
        'total_to_download' : total_to_download,
      }

    def __resetDownloads(self):
      '''
        reset download evennts either repos or packages
      '''
      if (self._download_events['in_progress'] != 0):
        logger.warning("Resetting download events with %d events still in progress", self._download_events['in_progress'])
        for download in self._download_events['downloads'].values():
          if download['downloaded'] != download['total_to_download']:
            logger.warning("Download of %s not completed", download['description'])
      self._download_events = {
        'in_progress' : 0,
        'downloads'    : {},
      }

    def __getDownloadInfo(self, download_id):
      '''
          get information for a given download
          Args:
            download_id: id of a downloaded object
          Returns a dictionary with the following keys:
            'description'       : the description of the downloaded object
            'downloaded'        : bytes already downloaded
            'total_to_download' : total bytes to download
      '''
      downloads = self._download_events['downloads']
      if download_id not in downloads.keys():
        logger.error("Download id %s is not present", download_id)
        # prevents to return None
        self._download_events['downloads'][download_id] = {
          'description'       : _("Unknown"),
          'downloaded'        : 0,
          'total_to_download' : 0,
        }

      return downloads[download_id]

    def _OnDownloadStart(self, session_object_path, download_id, description, total_to_download):
      '''
         Starting a new parallel download batch managing signal download_add_new
            Args:
                session_object_path: object path of the dnf5daemon session
                download_id: unique id of downloaded object (repo or package)
                description: the description of the downloaded object
                total_to_download: total bytes to download
      '''
      values =  (download_id, description, total_to_download)
      logger.debug('OnDownloadStart(%s) %s', session_object_path, repr(values))

      if session_object_path != self.backend.session_path :
        logger.warning("OnDownloadStart: Different session path received")
        return
      #if self._download_events['in_progress'] == 0:
      # self.infobar.info(_('Downloading'))

      self._download_events['in_progress'] += 1
      self.__addDownload(download_id, description, total_to_download)

      if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
          self._trans_dialog.on_download_start(download_id, description, total_to_download)
      else:
        self.infobar.set_progress(0.0)
        self.infobar.info(_('Start downloading [%(count_files)d] - file %(id)s - %(description)s ...') %
            {'count_files': len(self._download_events['downloads'].keys()), 'id': download_id, 'description':description })

    def _OnDownloadProgress(self, session_object_path, download_id, total_to_download, downloaded):
        '''
            Progress for a single element in the batch. Manage signal download_progress.
            Args:
                session_object_path: object path of the dnf5daemon session
                download_id: unique id of downloaded object (repo or package)
                total_to_download: total bytes to download
                downloaded: bytes already downloaded
        '''
        values =  (download_id, total_to_download, downloaded)
        if session_object_path != self.backend.session_path :
            logger.warning("OnDownloadProgress(%s): Different session path received. %s", session_object_path, repr(values))
            return

        download = self.__getDownloadInfo(download_id)
        if download['total_to_download'] != total_to_download:
            logger.warning("Dimension does not match for object [%s]:[%s]", download_id, download['description'])
        if total_to_download > 0:
            download['total_to_download'] = total_to_download
        download['downloaded'] = downloaded

        # When the event carries an unknown total (-1), fall back to the last
        # positive total stored in the download dict.  This prevents the
        # fraction from jumping back to 0 on alternating events where
        # dnf5daemon oscillates between a real size and -1 for the same id.
        effective_total = total_to_download if total_to_download > 0 else download['total_to_download']
        total_frac = downloaded / effective_total if effective_total > 0 else 0
        logger.debug('OnDownloadProgress: %s frac=%.3f (effective_total=%s)',
                     download_id, total_frac, effective_total)

        if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
            self._trans_dialog.on_download_progress(download_id, downloaded, effective_total)
        else:
          self.infobar.set_progress(total_frac)
          self.infobar.info(_('Downloading file %(id)s - %(description)s in progress')%
                            { 'id': download_id, 'description':download['description'] })

    def _OnDownloadEnd(self, session_object_path, download_id, status, error):
      '''
          Download of af single element ended. Manage signal download_end.
            Args:
                session_object_path: object path of the dnf5daemon session
                download_id: unique id of downloaded object (repo or package)
                status: (0 - successful, 1 - already exists, 2 - error)
                error: error message in case of failed download
      '''
      download = self.__getDownloadInfo(download_id)
      values =  (download_id, download['description'], status, error)
      logger.debug('OnDownloadEnd %s', repr(values))

      if self._trans_dialog is not None and self._status == DNFDragoraStatus.RUN_TRANSACTION:
          self._trans_dialog.on_download_end(download_id, download['description'], status, error)
      else:
        if (self._download_events['in_progress'] > 0) :
          self._download_events['in_progress'] -= 1

        # (0 - successful, 1 - already exists, 2 - error)
        if status == 0 or status == 1:  # download OK or already exists
          logger.debug('Downloaded : %s - %s', download_id, download['description'])
        else:
          logger.error('Download Error : [%s]:[%s] - %s', download_id, download['description'], error)

        self.infobar.info_sub("")
        if (self._download_events['in_progress'] == 0) :
          self.infobar.reset_all()
          self.__resetDownloads()

    def _OnErrorMessage(self, session_object_path, download_id, error, url, metadata):
      logger.error('OnErrorMessage(%s) - name: %s, err: %s url: %s, metadata: %s ', session_object_path, download_id, error, url, metadata)
      label= '( %s - %s)' % (download_id, error)
      self.infobar.set_progress(0.0, label=label)
      # TODO I don't like to add a label that is not deleted, but it is an error we show it right now...

    def _cachingRequest(self, pkg_flt):
      '''
      request for packages to be cached
      @params pkg_flt (available, installed, updates)
      “all”, “installed”, “available”, “upgrades”, “upgradable”
      '''
      logger.debug('Start caching %s', pkg_flt)
      filter = pkg_flt
      #TODO manage upgrades/upgradable correctly
      if pkg_flt == "updates":
        filter = "upgrades"
      elif pkg_flt == "updates_all":
        filter = "upgrades"

      options = {"package_attrs": [
        #"name",
        #"epoch",
        #"version",
        #"release",
        #"arch",
        "repo_id",
        #"from_repo_id",
        #"is_installed",
        "install_size",
        "download_size",
        #"sourcerpm",
        "summary",
        #"url",
        #"license",
        #"description",
        #"files",
        #"changelogs",
        #"provides",
        #"requires",
        #"requires_pre",
        #"conflicts",
        #"obsoletes",
        #"recommends",
        #"suggests",
        #"enhances",
        #"supplements",
        #"evr",
        "nevra",
        #"full_nevra",
        #"reason",
        #"vendor",
        "group",
        ],
        "scope": filter }
      if pkg_flt == 'updates' or pkg_flt == 'updates_all':
        self.infobar.info_sub(_("Caching updates"))
        self._status = DNFDragoraStatus.CACHING_UPDATE
      elif pkg_flt == 'installed':
        self.infobar.info_sub(_("Caching installed"))
        self._status = DNFDragoraStatus.CACHING_INSTALLED
        #self.backend.reloadDaemon()
      elif pkg_flt == 'available':
        self.infobar.info_sub(_("Caching available"))
        self._status = DNFDragoraStatus.CACHING_AVAILABLE
        #self.backend.reloadDaemon()
      else:
        logger.error("Wrong package filter %s", pkg_flt)
        return
      self.backend.GetPackages(options)

    def _populateCache(self, pkg_flt, po_list) :
      if pkg_flt == 'updates_all':
        pkg_flt = 'updates'
      # is this type of packages is already cached ?
      if not self.backend.cache.is_populated(pkg_flt):
        pkgs = self.backend.make_pkg_object(po_list, pkg_flt)
        self.backend.cache.populate(pkg_flt, pkgs)

    def _check_MD_cache_expired(self):
      ''' Check metadata expired if enabled or dnf makecache is disabled '''
      # check if MD cache management is disabled
      if self.md_update_interval <= 0:
        logger.debug("Metadata expired check disabled")
        return False
      # check this is the first time dnfdragora is run for this user
      if not self.md_last_refresh_date:
        logger.debug("Never downloaded Metadata before, forcing it now")
        return True

      logger.debug("Last Metadata check was %s", self.md_last_refresh_date)
      time_fmt = '%Y-%m-%d %H:%M'
      now = datetime.datetime.now()
      refresh_period = datetime.timedelta(hours=self.md_update_interval)
      last_refresh = datetime.datetime.strptime(self.md_last_refresh_date, time_fmt)
      period = now - last_refresh
      logger.debug("now: %s, elapsed: %s, download Metadata: %s", now, period, (period > refresh_period))
      return period > refresh_period

    def _set_MD_cache_refreshed(self):
      ''' set  '''
      time_fmt = '%Y-%m-%d %H:%M'
      now = datetime.datetime.now()
      now_str = now.strftime(time_fmt)
      self.config.userPreferences['settings']['metadata']['last_update'] = now_str
      self.md_last_refresh_date =  now_str

    def _start_caching_packages(self):
      ''' Start caching packages from installed
        next ones are requested after automatically.
      '''
      self.infobar.reset_all()
      self.backend.cache.reset()
      self.infobar.info(_('Creating packages cache'))
      self._cachingRequest('installed')

    def _OnBuildTransaction(self, info):
      '''
          manages BuildTransaction event from dnfdaemon "resolve" transaction action.
          Provides:
            @resolve: array of resolve information
            @result: problems detected during transaction resolving. Possible values are
              0 - no problem,
              1 - no problem, but some info / warnings are present
              2 - resolving failed.
      '''

      self.infobar.reset_all()
      if not info['error']:
        result, resolve = info['result']
        if result == 1: #Transaction WARNING
          errors = self.backend.TransactionProblems(sync=True)
          err =  "".join(errors) if isinstance(errors, list) else errors if type(errors) is str else repr(errors);
          dialogs.warningMsgBox({'title'  : _('Transaction with warnings',), 'text' : err.replace("\n", "<br>"), 'richtext' : True })
          logger.warning("Transaction with warnings: %s", repr(errors))

        ok = result == 0 # Avoid to die "or result == 1" TODO manage Warning
        if ok:
          self.started_transaction = {
            'Install': {},
            'Remove':{},
            'Upgrade': {},
            'Reinstall':{},
            'Downgrade':{},
          }
          for typ, action, who, unk, pkg in resolve:
            '''
              [
                ['Package',
                'Install',
                'User',
                {},
                {'arch': 'x86_64', 'download_size': 2415775, 'epoch': '0', 'evr': '0.9.8083-18.mga9', 'from_repo_id': '', 'id': 5516, 'install_size': 6494742, 'name': 'btanks', 'reason': 'None', 'release': '18.mga9', 'repo_id': 'mageia-x86_64', 'version': '0.9.8083'}
                ],
                ['Package', 'Install', 'Dependency', {}, {'arch': 'noarch', 'download_size': 26482294, 'epoch': '0', 'evr': '0.9.8083-18.mga9', 'from_repo_id': '', 'id': 5517, 'install_size': 30026310, 'name': 'btanks-data', 'reason': 'None', 'release': '18.mga9', 'repo_id': 'mageia-x86_64', 'version': '0.9.8083'}],
                ['Package', 'Install', 'Dependency', {}, {'arch': 'x86_64', 'download_size': 36137, 'epoch': '0', 'evr': '1.2.12-16.mga9', 'from_repo_id': '', 'id': 11240, 'install_size': 65688, 'name': 'lib64SDL_image1.2_0', 'reason': 'None', 'release': '16.mga9', 'repo_id': 'mageia-x86_64', 'version': '1.2.12'}],
                ['Package', 'Upgrade', 'External User', {'replaces': [4176]}, {'arch': 'x86_64', 'download_size': 72815326, 'epoch': '0', 'evr': '115.6.0-1.mga9', 'from_repo_id': '', 'id': 37188, 'install_size': 255879886, 'name': 'thunderbird', 'reason': 'External User', 'release': '1.mga9', 'repo_id': 'updates-x86_64', 'version': '115.6.0'}],
                ['Package', 'Upgrade', 'External User', {'replaces': [2061]}, {'arch': 'x86_64', 'download_size': 1274450, 'epoch': '2', 'evr': '2:3.96.1-1.mga9', 'from_repo_id': '', 'id': 36235, 'install_size': 3366838, 'name': 'lib64nss3', 'reason': 'External User', 'release': '1.mga9', 'repo_id': 'updates-x86_64', 'version': '3.96.1'}],
                ['Package', 'Upgrade', 'External User', {'replaces': [4178]}, {'arch': 'noarch', 'download_size': 582809, 'epoch': '0', 'evr': '115.6.0-1.mga9', 'from_repo_id': '', 'id': 37398, 'install_size': 644849, 'name': 'thunderbird-it', 'reason': 'External User', 'release': '1.mga9', 'repo_id': 'updates-x86_64', 'version': '115.6.0'}],
                ['Package', 'Remove', 'User', {}, {'arch': 'x86_64', 'download_size': 0, 'epoch': '0', 'evr': '7.2-1.mga9', 'from_repo_id': '<unknown>', 'id': 3376, 'install_size': 3112536, 'name': 'nano', 'reason': 'External User', 'release': '1.mga9', 'repo_id': '@System', 'version': '7.2'}],

                ['Package', 'Replaced', 'External User', {}, {'arch': 'x86_64', 'download_size': 0, 'epoch': '2', 'evr': '2:3.95.0-1.mga9', 'from_repo_id': '<unknown>', 'id': 2061, 'install_size': 3366878, 'name': 'lib64nss3', 'reason': 'External User', 'release': '1.mga9', 'repo_id': '@System', 'version': '3.95.0'}],
                ['Package', 'Replaced', 'External User', {}, {'arch': 'x86_64', 'download_size': 0, 'epoch': '0', 'evr': '115.5.1-1.mga9', 'from_repo_id': '<unknown>', 'id': 4176, 'install_size': 258383164, 'name': 'thunderbird', 'reason': 'External User', 'release': '1.mga9', 'repo_id': '@System', 'version': '115.5.1'}],
                ['Package', 'Replaced', 'External User', {}, {'arch': 'noarch', 'download_size': 0, 'epoch': '0', 'evr': '115.5.1-1.mga9', 'from_repo_id': '<unknown>', 'id': 4178, 'install_size': 645040, 'name': 'thunderbird-it', 'reason': 'External User', 'release': '1.mga9', 'repo_id': '@System', 'version': '115.5.1'}]
              ]
            '''
            if action != 'Replaced':
              self.started_transaction[action][pkg['name']] = [
                misc.pkg_id_to_full_nevra(misc.to_pkg_id(pkg['name'], pkg["epoch"], pkg["version"], pkg["release"], pkg["arch"], pkg["repo_id"])),
                pkg['install_size'],
              ]
            elif pkg['name'] in self.started_transaction['Upgrade'].keys():
              self.started_transaction['Upgrade'][pkg['name']].append(
                misc.pkg_id_to_full_nevra(misc.to_pkg_id(pkg['name'], pkg["epoch"], pkg["version"], pkg["release"], pkg["arch"], pkg["repo_id"])))
        else:
          errors = self.backend.TransactionProblems(sync=True)
          err =  "".join(errors) if isinstance(errors, list) else errors if type(errors) is str else repr(errors);
          dialogs.infoMsgBox({'title'  : _('Build Transaction error',), 'text' : err.replace("\n", "<br>"), 'richtext' : True })
          logger.warning("Transaction Cancelled: %s", repr(errors))

          # TODO Transaction has errors we should clean it up reload all by now
          self.backend.reloadDaemon()
          self.backend.clear_cache(also_groups=True)
          self.packageQueue.clear()
          self._status = DNFDragoraStatus.STARTUP
          self._enableAction(False)
          return
        # If status is RUN_TRANSACTION we have already confirmed our transaction into BuildTransaction
        # and we are here most probably for a GPG key confirmed during last transaction
        #TODO dialog to confirm transaction, NOTE that there is no clean transaction if user say no
        if ok and not self.always_yes and self._status != DNFDragoraStatus.RUN_TRANSACTION:
            if len(resolve) >0:
                transaction_result_dlg = dialogs.TransactionResult(self)
                ok = transaction_result_dlg.run(self.started_transaction)
                if not ok:
                    self._enableAction(True)
                    return
        elif ok !=0:
          logger.error("Build transaction error %d", ok) #TODO read errors from dnf daemon

        #TODO
        TODO=True
        if not TODO:
          self.started_transaction = ''
          try:
              installed_packages = []
              removed_packages = []
              for action_list in resolve:
                  if action_list and action_list[0] == 'install':
                      if len(action_list) > 1:
                          for program in action_list[1]:
                              program_info = program[0].split(',')
                              installed_packages.append(f'{program_info[0]}-{program_info[2]}-{program_info[3]}.{program_info[4]}')
                  if action_list and action_list[0] == 'remove':
                      if len(action_list) > 1:
                          for program in action_list[1]:
                              program_info = program[0].split(',')
                              removed_packages.append(f'{program_info[0]}-{program_info[2]}-{program_info[3]}.{program_info[4]}')
              if installed_packages:
                  installed_packages = '\n' + "\n".join(installed_packages) + '\n\n'
                  self.started_transaction += _('Packages installed:') + f' {installed_packages}'
              if removed_packages:
                  removed_packages = '\n' + "\n".join(removed_packages)
                  self.started_transaction += _('Packages removed:') + f' {removed_packages}'
          except Exception as e:
              self.started_transaction += _('Error occured:') + f' {e}' + '\n' + f'result = {result}'

        if ok:
          self.infobar.info(_('Applying changes to the system'))
          self._show_trans_dialog()
          self.backend.RunTransaction()
          self._status = DNFDragoraStatus.RUN_TRANSACTION
        else:
          err =  "".join(resolve) if isinstance(resolve, list) else resolve if type(resolve) is str else repr(resolve);
          dialogs.infoMsgBox({'title'  : _('Build Transaction error',), 'text' : err.replace("\n", "<br>"), 'richtext' : True })
          logger.warning("Transaction Cancelled: %s", repr(resolve))
          self._enableAction(True)

    def _manageDnfDaemonEvent(self):
      '''
      get events from dnfd client queue
      '''
      rebuild_package_list = False
      try:
        counter = 0
        # On RUNNING we manage UI events, on other status dnfdaeomon let's try to increase
        # dequeuing when we're not in RUNNING then
        count_max = 1000 if self._status != DNFDragoraStatus.RUNNING else 1

        while counter < count_max:
          counter = counter + 1
          item = self.backend.eventQueue.get_nowait()
          event = item['event']
          info = item['value']

          if self._status != DNFDragoraStatus.RUN_TRANSACTION:
            logger.debug("Event received %s - status %s", event, self._status)

          is_dict = isinstance(info, dict)
          if is_dict:
            if 'error' in info.keys() and 'result' in info.keys():
              if info['error']:
                #got an Exception into trhead loop
                logger.error("Event received %s, %s - status %s", event, info['error'], self._status)
                title = _("Error in status %(status)s on %(event)s")%({'status':self._status, 'event':(event if event else "---")})
                dialogs.warningMsgBox({'title' : title, "text": str(info['error']), "richtext":True})
                # Force return on STARTUP on error
                try:
                  self.backend.reloadDaemon()
                except Exception as reload_err:
                  logger.error("reloadDaemon failed during error recovery: %s", reload_err)
                self.backend.clear_cache(also_groups=True)
                self.packageQueue.clear()
                self._status = DNFDragoraStatus.STARTUP
                self._enableAction(False)
                # force return on error
                return False
              elif info['result']:
                is_list = isinstance(info['result'], list)
                logger.debug("Event received %s, %s - status %s", event, len(info['result']) if is_list else info, self._status)

          if (event == 'Lock') :
            self.backend_locked = info['result']
            logger.info("Event %s received (%s)", event, info['result'])
            if self.backend_locked :
              self._status = DNFDragoraStatus.RUNNING
              self.backend.SetWatchdogState(False, sync=True)
              # Only if expired
              if self._check_MD_cache_expired():
                self.backend.CleanCache()
              else:
                self._start_caching_packages()
            else:
              self._enableAction(self.backend_locked)
              if self._status == DNFDragoraStatus.LOCKING:
                if not info['error']:
                  self._status = DNFDragoraStatus.STARTUP
          elif (event == 'Unlock') :
            logger.info("Event %s received (%s)", event, info['result'])
            self.backend_locked = False
          elif (event == 'ResetSession'):
            logger.info("Event %s received (%s)", event, info['result'])
            # ResetSession has been invoked let's refresh data
            self.backend.clear_cache(also_groups=True)
            self._status = DNFDragoraStatus.STARTUP
            self._enableAction(False)
          elif (event == 'ReloadMetadata'):
            if not info['result']:
              logger.warning("Event %s received (%s)", event, info['result'])
            # ExpireCache has been invoked let's refresh data
            self.backend.clear_cache(also_groups=True)
            self._status = DNFDragoraStatus.RESET_SESSION
            self._enableAction(False)
            self.backend.ResetSession()
          elif (event == 'CleanCache'):
            if not info['result']:
              logger.warning("Event %s received (%s)", event, info['result'])
            self.backend.clear_cache(also_groups=True)
            self._status = DNFDragoraStatus.RELOAD_METADATA
            self._enableAction(False)
            # CleanCache has been invoked let's refresh data => ReloadMetadata
            self.backend.ReloadMetadata()            
          elif (event == 'GetPackages'):
            if not info['error']:
              if self._status == DNFDragoraStatus.CACHING_INSTALLED:
                po_list = info['result']
                # we requested installed for caching
                self._populateCache('installed', po_list)
                self.infobar.set_progress(0.33)
                cache_update = 'updates_all' if self.upgrades_as_updates else 'updates'
                self._cachingRequest(cache_update)
              elif self._status == DNFDragoraStatus.CACHING_UPDATE:
                po_list = info['result']
                # we requested updates for caching
                self._populateCache('updates', po_list)
                self.infobar.set_progress(0.66)
                self._cachingRequest('available')
              elif self._status == DNFDragoraStatus.CACHING_AVAILABLE:
                po_list = info['result']
                rpm_groups = None
                if self.use_comps :
                  # let's show the dialog with a poll event
                  rpm_groups = self.backend.GetGroups(sync=True)
                self.gIcons = compsicons.CompsIcons(rpm_groups, self.group_icon_path) if self.use_comps else  groupicons.GroupIcons(self.group_icon_path)

                # we requested available for caching
                self.infobar.set_progress(1.0)
                self._populateCache('available', po_list)
                self._status = DNFDragoraStatus.RUNNING

                #TODO check --install option how it works using dnf5daemon and fix eventually
                if not self._runtime_option_managed and 'install' in self.options.keys() :
                  pkgs = " ".join(i.replace(" ", "\\ ") for i in self.options['install'])
                  self.backend.Install(pkgs, sync=True)
                  self.backend.BuildTransaction()
                  self._runtime_option_managed = True
                  return

                self._enableAction(True)
                filter = self._filterNameSelected()
                self.checkAllButton.setEnabled(filter == 'to_update')

                sel = self.tree.selectedItem()
                if sel :
                  rebuild_package_list = self._rebuildPackageListWithSearchGroup()
                else:
                  rebuild_package_list = True
                self.infobar.reset_all()
            else:
              logger.error("GetPackages error: %s", info['error'])
              raise UIError(str(info['error']))

          elif (event == 'RESearch'):
            if not info['error']:
              pkgs = None
              packages = None
              if self.newest_only:
                pkgs = sorted(info['result'], key=lambda p: p.full_nevra, reverse=True)
                name = None
                packages = []
                for p in pkgs:
                  if p.name != name:
                    packages.append(p)
                    name = p.name
              else:
                 packages = info['result']
              self._showSearchResult(packages, createTreeItem=True)
            else:
              self._showErrorAndContinue(_("Search error using regular expression"), info['error'])
              logger.error("Search error: %s", info['error'])

          elif (event == 'Search'):
            if not info['error']:
              pkgs = None
              packages = None
              if self.newest_only:
                pkgs = sorted(self.backend.make_pkg_object_with_attr(info['result']), key=lambda p: p.full_nevra, reverse=True)
                name = None
                packages = []
                for p in pkgs:
                  if p.name != name:
                    packages.append(p)
                    name = p.name
              else:
                packages = self.backend.make_pkg_object_with_attr(info['result'])
              self._showSearchResult(packages, createTreeItem=True)
            else:
              logger.error("Search error: %s", info['error'])
              raise UIError(str(info['error']))

          elif (event == 'OnRepoMetaDataProgress'):
            self._OnRepoMetaDataProgress(info['name'], info['frac'])
          elif (event == 'BuildTransaction'):
            self._OnBuildTransaction(info)
          elif (event == 'OnTransactionVerifyStart'):
            self._OnTransactionVerifyStart(info['session_object_path'], info['total'])
          elif (event == 'OnTransactionVerifyProgress'):
            self._OnTransactionVerifyProgress(info['session_object_path'], info['processed'], info['total'])
          elif (event == 'OnTransactionVerifyStop'):
            self._OnTransactionVerifyStop(info['session_object_path'], info['total'])
          elif (event == 'OnTransactionActionStart'):
              self._OnTransactionActionStart(info['session_object_path'], info['nevra'], info['action'], info['total'])
          elif (event == 'OnTransactionActionProgress'):
              self._OnTransactionActionProgress(info['session_object_path'], info['nevra'], info['processed'], info['total'])
          elif (event == 'OnTransactionActionStop'):
              self._OnTransactionActionStop(info['session_object_path'], info['nevra'], info['total'])
          elif (event == 'OnTransactionElemProgress'):
              self._OnTransactionElemProgress(info['session_object_path'], info['nevra'], info['processed'], info['total'])
          elif (event == 'OnTransactionTransactionStart'):
              self._OnTransactionTransactionStart(info['session_object_path'], info['total'])
          elif (event == 'OnTransactionTransactionProgress'):
              self._OnTransactionTransactionProgress(info['session_object_path'], info['processed'], info['total'])
          elif (event == 'OnTransactionTransactionStop'):
              self._OnTransactionTransactionStop(info['session_object_path'], info['total'])
          elif (event == 'OnTransactionScriptStart'):
              self._OnTransactionScriptStart(info['session_object_path'], info['nevra'], info['scriptlet_type'])
          elif (event == 'OnTransactionScriptStop'):
              self._OnTransactionScriptStop(info['session_object_path'], info['nevra'], info['scriptlet_type'], info['return_code'])
          elif (event == 'OnTransactionScriptError'):
              self._OnTransactionScriptError(info['session_object_path'], info['nevra'], info['scriptlet_type'], info['return_code'])
          elif  (event == 'OnTransactionAfterComplete')  or \
               (event == 'OnTransactionTimeoutEvent')   or \
               (event == 'OnTransactionUnpackError'):
            self._OnTransactionEvent(event, info)
          elif (event == 'OnRPMProgress'):
            self._OnRPMProgress(info['package'], info['action'], info['te_current'],
                                info['te_total'], info['ts_current'], info['ts_total'])
          elif (event == 'OnGPGImport'):
            self._OnGPGImport(info['session_object_path'], info['key_id'],
                              info['user_ids'], info['key_fingerprint'],
                              info['key_url'], info['timestamp'])
          elif (event == 'OnDownloadStart'):
            logger.debug(info)
            self._OnDownloadStart(info['session_object_path'], info['download_id'], info['description'], info['total_to_download'])
          elif (event == 'OnDownloadProgress'):
            self._OnDownloadProgress(info['session_object_path'], info['download_id'], info['total_to_download'], info['downloaded'])
          elif (event == 'OnDownloadEnd'):
            logger.debug(info)
            self._OnDownloadEnd(info['session_object_path'], info['download_id'], info['status'], info['error'])
          elif (event == 'OnErrorMessage'):
            logger.warning(info)
            self._OnErrorMessage(info['session_object_path'], info['download_id'], info['error'], info['url'], info['metadata'])
          elif (event == 'GetHistoryByDays'):
            if not info['error']:
              transaction_list = info['result']
              self._load_history(transaction_list)
              #### TODO fix history undo transaction
              # TODO if performedUNDO:
              # TODO   sel = self.tree.selectedItem()
              # TODO   if sel :
              # TODO       group = self._groupNameFromItem(self.groupList, sel)
              # TODO       filter = self._filterNameSelected()
              # TODO       if (group == "Search"):
              # TODO           # force tree rebuilding to show new package status
              # TODO           if not self._searchPackages(filter, True) :
              # TODO               rebuild_package_list = True
              # TODO       else:
              # TODO           if filter == "to_update":
              # TODO               self._fillGroupTree()
              # TODO           rebuild_package_list = True
          elif (event == 'HistoryUndo'):
            self._undo_transaction()
          elif (event == 'SetEnabledRepos') or (event == 'SetDisabledRepos'):
            logger.debug("%s - %s", event, info['result'])
            self.backend.clear_cache(also_groups=True)
            self._status = DNFDragoraStatus.STARTUP
            self._enableAction(False)
            # Enabled repositories are changes we need to force caching again
            self.backend.ResetSession()
          else:
            logger.warning("Unmanaged event received %s - info %s", event, str(info))

      except Empty:
          if self._status == DNFDragoraStatus.STARTUP:
            self._status = DNFDragoraStatus.RUNNING
            self._start_caching_packages()
          elif self._status == DNFDragoraStatus.RESET_SESSION:
            # RunTransaction (do_transaction) is fire-and-forget: its D-Bus ack
            # clears _sent without queuing any event, and it arrives AFTER the
            # OnTransactionAfterComplete signal. Poll on each timer tick until
            # _sent is cleared before issuing ResetSession.
            if not self.backend._sent:
              logger.debug("RESET_SESSION: _sent cleared, issuing ResetSession")
              self.backend.ResetSession()


      return rebuild_package_list

    def quit(self):
        self.running = False
