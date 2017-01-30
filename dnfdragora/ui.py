
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
import yui

import dnfdragora.basedragora
import dnfdragora.compsicons as compsicons
import dnfdragora.groupicons as groupicons
import dnfdragora.progress_ui as progress_ui
import dnfdragora.dialogs as dialogs
import dnfdragora.misc as misc

import dnfdragora.config
from dnfdragora import const

import gettext
from gettext import gettext as _, ngettext
import logging
logger = logging.getLogger('dnfdragora.ui')

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
        returns if a package has to be checked in gui pacakge-list
        '''
        pkg_id = pkg.pkg_id
        if pkg_id in self.actions.keys():
            return pkg.installed and self.actions[pkg_id] != 'r' or self.actions[pkg_id] != 'r'
        return pkg.installed

    def action(self, pkg):
        '''
        returns the action of the queued package or None if pacakge is not queued
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
    Main class
    """

    def __init__(self, options={}):

        self.options = options
        self._progressBar = None
        self.packageQueue = PackageQueue()
        self.toRemove = []
        self.toInstall = []
        self.itemList = {}
        self.appname = "dnfdragora"


        # {
        #   name-epoch_version-release.arch : { pkg: dnf-pkg, item: YItem}
        # }
        self.groupList = {}
        # {
        #    localized_name = { "item" : item, "name" : groupName }
        # }
        # TODO : perhaps fix with a relative path
        DIR="/usr/share/locale"
        gettext.bindtextdomain(self.appname, DIR)
        gettext.textdomain(self.appname)

        self.use_comps = False
        self.group_icon_path = None
        self.images_path = '/usr/share/dnfdragora/images/'
        self.always_yes = False
        self.log_filename = None
        self.level_debug = False
        self.config = dnfdragora.config.AppConfig(self.appname)

        # settings from configuration file first
        self._configFileRead()

        if self.log_filename:
            if self.level_debug:
                misc.logger_setup(self.log_filename, loglvl=logging.DEBUG)
            else:
                misc.logger_setup(self.log_filename)
            logger.info("dnfdragora started")

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

        dnfdragora.basedragora.BaseDragora.__init__(self, self.use_comps)
        rpm_groups = self.backend.GetGroups() if self.use_comps else None
        self.gIcons = compsicons.CompsIcons(rpm_groups, self.group_icon_path) if self.use_comps else  groupicons.GroupIcons(self.group_icon_path)

        # setup UI
        self._setupUI()

    def _configFileRead(self) :
        '''
            reads the configuration file and sets application data
        '''
        try:
            self.config.load()
        except Exception as e:
            print ("Exception: %s" % str(e))
            exc = "Configuration file <%s> problem" % self.config.fileName
            raise (Exception(exc))

        if self.config.content :
            settings = {}
            if 'settings' in self.config.content.keys() :
                settings = self.config.content['settings']

            if 'use_comps' in settings.keys() :
                self.use_comps = settings['use_comps']

            if 'always_yes' in settings.keys() :
                self.always_yes = settings['always_yes']

            if 'log_filename' in settings.keys() :
                self.log_filename = settings['log_filename']

            if 'log_level_debug' in settings.keys() :
                self.level_debug = settings['log_level_debug']

            # config['settings']['path']
            path_settings = {}
            if 'path' in settings.keys():
                path_settings = settings['path']
            if 'group_icons' in path_settings.keys():
                self.group_icon_path = path_settings['group_icons']
            if 'images' in path_settings.keys():
                self.images_path = path_settings['images']

    def _setupUI(self) :
        '''
            setup main dialog
        '''
        yui.YUI.app().setApplicationTitle(_("Software Management - dnfdragora"))

        #TODO fix icons
        self.icon = self.images_path + "dnfdragora.png"
        yui.YUI.app().setApplicationIcon(self.icon)

        MGAPlugin = "mga"

        self.factory = yui.YUI.widgetFactory()
        mgaFact = yui.YExternalWidgets.externalWidgetFactory(MGAPlugin)
        self.mgaFactory = yui.YMGAWidgetFactory.getYMGAWidgetFactory(mgaFact)
        self.optFactory = yui.YUI.optionalWidgetFactory()

        self.AboutDialog = dialogs.AboutDialog(self)

        ### MAIN DIALOG ###
        self.dialog = self.factory.createMainDialog()

        vbox = self.factory.createVBox(self.dialog)

        hbox_headbar = self.factory.createHBox(vbox)
        head_align_left = self.factory.createLeft(hbox_headbar)
        head_align_right = self.factory.createRight(hbox_headbar)
        headbar = self.factory.createHBox(head_align_left)
        headRight = self.factory.createHBox(head_align_right)

        #Line for logo and title
        hbox_iconbar  = self.factory.createHBox(vbox)
        head_align_left  = self.factory.createLeft(hbox_iconbar)
        hbox_iconbar     = self.factory.createHBox(head_align_left)
        self.factory.createImage(hbox_iconbar, self.icon)

        self.factory.createHeading(hbox_iconbar, _("Software Management"))

        hbox_top = self.factory.createHBox(vbox)
        hbox_middle = self.factory.createHBox(vbox)
        hbox_bottom = self.factory.createHBox(vbox)
        pbar_layout = self.factory.createHBox(vbox)
        hbox_footbar = self.factory.createHBox(vbox)

        hbox_headbar.setWeight(1,10)
        hbox_top.setWeight(1,10)
        hbox_middle.setWeight(1,50)
        hbox_bottom.setWeight(1,30)
        hbox_footbar.setWeight(1,10)

        # Tree for groups
        self.tree = self.factory.createTree(hbox_middle, "")
        self.tree.setWeight(0,20)
        self.tree.setNotify(True)

        packageList_header = yui.YTableHeader()
        columns = [ _('Name'), _('Summary'), _('Version'), _('Release'), _('Arch')]

        packageList_header.addColumn("")
        for col in (columns):
            packageList_header.addColumn(col)

        if not self.update_only :
            packageList_header.addColumn(_("Status"))

        self.packageList = self.mgaFactory.createCBTable(hbox_middle,packageList_header,yui.YCBTableCheckBoxOnFirstColumn)
        self.packageList.setWeight(0,50)
        self.packageList.setImmediateMode(True)

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
        itemColl = yui.YItemCollection()

        for v in ordered_views:
            item = yui.YItem(self.views[v]['title'], False)
            #TODO restore saved settings selection
            if self.update_only and v == "all":
                item.setSelected(True)
                
            # adding item to views to find the item selected
            self.views[v]['item'] = item
            itemColl.push_back(item)
            item.this.own(False)

        self.view_box.addItems(itemColl)
        self.view_box.setNotify(True)
        self.view_box.setEnabled(not self.update_only)

        self.filter_box = self.factory.createComboBox(hbox_top,"")
        itemColl.clear()

        for f in ordered_filters:
            item = yui.YItem(self.filters[f]['title'], False)
            #TODO restore saved settings selection
            if self.update_only and f == "to_update":
                item.setSelected(True)

            # adding item to filters to find the item selected
            self.filters[f]['item'] = item
            itemColl.push_back(item)
            item.this.own(False)

        self.filter_box.addItems(itemColl)
        self.filter_box.setNotify(True)
        self.filter_box.setEnabled(not self.update_only)

        self.local_search_types = {
            'name'       : {'title' : _("in names")       },
            'description': {'title' : _("in descriptions")},
            'summary'    : {'title' : _("in summaries")   },
            'file'       : {'title' : _("in file names")  }
        }
        search_types = ['name', 'description', 'summary', 'file' ]

        self.search_list = self.factory.createComboBox(hbox_top,"")
        itemColl.clear()
        for s in search_types:
            item = yui.YItem(self.local_search_types[s]['title'], False)
            if s == search_types[0] :
                item.setSelected(True)
            # adding item to local_search_types to find the item selected
            self.local_search_types[s]['item'] = item
            itemColl.push_back(item)
            item.this.own(False)

        self.search_list.addItems(itemColl)
        self.search_list.setNotify(True)

        self.find_entry = self.factory.createInputField(hbox_top, "")

        icon_file = self.images_path + "find.png"
        self.find_button = self.factory.createIconButton(hbox_top, icon_file, _("&Search"))
        self.find_button.setWeight(0,6)
        self.dialog.setDefaultButton(self.find_button)
        self.find_entry.setKeyboardFocus()

        icon_file = self.images_path + "clear_22x22.png"
        self.reset_search_button = self.factory.createIconButton(hbox_top, icon_file, _("&Clear search"))
        self.reset_search_button.setWeight(0,7)
        self.find_entry.setWeight(0,10)

        self.info = self.factory.createRichText(hbox_bottom,"")
        self.info.setWeight(0,40)
        self.info.setWeight(1,40);

        self.infobar = progress_ui.ProgressBar(self.dialog, pbar_layout)

        self.applyButton = self.factory.createIconButton(hbox_footbar,"",_("&Apply"))
        self.applyButton.setWeight(0,3)
        self.applyButton.setEnabled(False)

        self.checkAllButton = self.factory.createIconButton(hbox_footbar,"",_("Ch&eck all"))
        self.checkAllButton.setWeight(0,3)
        self.checkAllButton.setEnabled(False)

        self.quitButton = self.factory.createIconButton(hbox_footbar,"",_("&Quit"))
        self.quitButton.setWeight(0,6)

        # build File menu
        self.fileMenu = {
            'widget'    : self.factory.createMenuButton(headbar, _("&File")),
            'reset_sel' : yui.YMenuItem(_("Reset the selection")),
            'reload'    : yui.YMenuItem(_("Refresh Metadata")),
            'quit'      : yui.YMenuItem(_("&Quit")),
        }

        ordered_menu_lines = ['reset_sel', 'reload', 'quit']
        for l in ordered_menu_lines :
            self.fileMenu['widget'].addItem(self.fileMenu[l])
        self.fileMenu['widget'].rebuildMenuTree();

        # build help menu
        self.helpMenu = {
            'widget': self.factory.createMenuButton(headRight, _("&Help")),
            'help'  : yui.YMenuItem(_("Manual")),
            'about' : yui.YMenuItem(_("&About")),
        }
        ordered_menu_lines = ['help', 'about']
        for l in ordered_menu_lines :
            self.helpMenu['widget'].addItem(self.helpMenu[l])

        self.helpMenu['widget'].rebuildMenuTree()

        self.dialog.pollEvent()
        self._fillGroupTree()
        sel = self.tree.selectedItem()
        group = None
        if sel :
            group = self._groupNameFromItem(self.groupList, sel)

        filter = self._filterNameSelected()
        self.checkAllButton.setEnabled(filter == 'to_update')
        self._fillPackageList(group, filter)
        sel = self.packageList.toCBYTableItem(self.packageList.selectedItem())
        if sel :
            pkg_name = sel.cell(0).label()
            self.setInfoOnWidget(pkg_name)

    def _pkg_name(self, name, epoch, version, release, arch) :
        '''
            return a package name in the form name-epoch_version-release.arch
        '''
        return ("{0}-{1}_{2}-{3}.{4}".format(name, epoch, version, release, arch))

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
            if emit_changed:
                self.packageList.cellChanged(cell)



    def _fillPackageList(self, groupName=None, filter="all") :
        '''
        fill package list filtered by group if groupName is given,
        and checks installed packages.
        Special value for groupName 'All' means all packages
        Available filters are:
        all, installed, not_installed, to_update and skip_other
        '''

        yui.YUI.app().busyCursor()

        self.itemList = {}
        # {
        #   name-epoch_version-release.arch : { pkg: dnf-pkg, item: YItem}
        # }
        if filter == 'all' or filter == 'to_update' or filter == 'skip_other':
            updates = self.backend.get_packages('updates')
            for pkg in updates:
                groups_pkg = self.backend.get_groups_from_package(pkg)
                if groupName and (groupName in groups_pkg or groupName == 'All') :
                    skip_insert = (filter == 'skip_other' and not (pkg.arch == 'noarch' or pkg.arch == platform.machine()))
                    if not skip_insert :
                        item = yui.YCBTableItem(pkg.name , pkg.summary , pkg.version, pkg.release, pkg.arch)
                        item.check(self.packageQueue.checked(pkg))
                        self.itemList[self._pkg_name(pkg.name , pkg.epoch , pkg.version, pkg.release, pkg.arch)] = {
                            'pkg' : pkg, 'item' : item
                            }
                        if not self.update_only:
                            item.addCell("")
                            self._setStatusToItem(pkg,item)
                        item.this.own(False)

        if filter == 'all' or filter == 'installed' or filter == 'skip_other':
            installed = self.backend.get_packages('installed')
            for pkg in installed :
                groups_pkg = self.backend.get_groups_from_package(pkg)
                if groupName and (groupName in groups_pkg or groupName == 'All') :
                    skip_insert = (filter == 'skip_other' and not (pkg.arch == 'noarch' or pkg.arch == platform.machine()))
                    if not skip_insert :
                        item = yui.YCBTableItem(pkg.name , pkg.summary , pkg.version, pkg.release, pkg.arch)
                        item.check(self.packageQueue.checked(pkg))
                        self.itemList[self._pkg_name(pkg.name , pkg.epoch , pkg.version, pkg.release, pkg.arch)] = {
                            'pkg' : pkg, 'item' : item
                            }
                        if not self.update_only:
                            item.addCell("")
                            self._setStatusToItem(pkg,item)
                        item.this.own(False)

        if filter == 'all' or filter == 'not_installed' or filter == 'skip_other':
            available = self.backend.get_packages('available')
            for pkg in available:
                groups_pkg = self.backend.get_groups_from_package(pkg)
                if groupName and (groupName in groups_pkg or groupName == 'All') :
                    skip_insert = (filter == 'skip_other' and not (pkg.arch == 'noarch' or pkg.arch == platform.machine()))
                    if not skip_insert :
                        item = yui.YCBTableItem(pkg.name , pkg.summary , pkg.version, pkg.release, pkg.arch)
                        item.check(self.packageQueue.checked(pkg))
                        self.itemList[self._pkg_name(pkg.name , pkg.epoch , pkg.version, pkg.release, pkg.arch)] = {
                            'pkg' : pkg, 'item' : item
                            }
                        if not self.update_only:
                            item.addCell("")
                            self._setStatusToItem(pkg,item)
                        item.this.own(False)

        keylist = sorted(self.itemList.keys())
        v = []
        for key in keylist :
            item = self.itemList[key]['item']
            v.append(item)

        #NOTE workaround to get YItemCollection working in python
        itemCollection = yui.YItemCollection(v)

        self.packageList.startMultipleChanges()
        # cleanup old changed items since we are removing all of them
        self.packageList.setChangedItem(None)
        self.packageList.deleteAllItems()
        self.packageList.addItems(itemCollection)
        self.packageList.doneMultipleChanges()

        yui.YUI.app().normalCursor()

    def _viewNameSelectet(self):
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
        # TODO check type yui.YTreeItem?
        for g in group.keys() :
            if g == 'name' or g == 'item' :
                continue
            if group[g]['item'] == treeItem :
                return group[g]['name']
            elif group[g]['item'].hasChildren():
                gName =  self._groupNameFromItem(group[g], treeItem)
                if gName :
                    return gName

        return None


    def _fillGroupTree(self) :
        '''
        fill the group tree, look for the retrieved groups and set their icons
        from groupicons module
        '''

        self.groupList = {}
        rpm_groups = []
        yui.YUI.app().busyCursor()

        view = self._viewNameSelectet()
        filter = self._filterNameSelected()

        if view != 'all' :
            print ("Start looking for groups")

            #filters = [ 'all', 'installed', 'to_update', 'not_installed' ]
            if (filter == 'to_update'):
                logger.debug("get groups for update packages only")
                pkgs = self.backend.get_packages('updates')
                for pkg in pkgs:
                    groups = self.backend.get_groups_from_package(pkg)
                    rpm_groups = list(set().union(rpm_groups, groups))
            elif (filter == 'installed'):
                logger.debug("get groups for installed packages only")
                pkgs = self.backend.get_packages('installed')
                for pkg in pkgs:
                    groups = self.backend.get_groups_from_package(pkg)
                    rpm_groups = list(set().union(rpm_groups, groups))
            elif (filter == 'not_installed'):
                logger.debug("get groups for available packages only")
                pkgs = self.backend.get_packages('available')
                for pkg in pkgs:
                    groups = self.backend.get_groups_from_package(pkg)
                    rpm_groups = list(set().union(rpm_groups, groups))
            else:
                # all pr arch
                logger.debug("get all groups")
                rpm_groups = self.backend.get_groups()
            rpm_groups = sorted(rpm_groups)
        else:
            rpm_groups = ['All']

        if not rpm_groups:
            rpm_groups = ['Empty']

        groups = self.gIcons.groups

        for g in rpm_groups:
            #X/Y/Z/...
            currG = groups
            currT = self.groupList
            subGroups = g.split("/")
            currItem = None
            parentItem = None
            groupName = None

            for sg in subGroups:
                if groupName:
                    groupName += "/%s"%(sg)
                else:
                    groupName = sg
                icon = self.gIcons.icon(groupName)

                if sg in currG:
                    currG = currG[sg]
                    if currG["title"] in currT :
                        currT = currT[currG["title"]]
                        parentItem = currT["item"]
                    else :
                        # create the item
                        item = None
                        if parentItem:
                            item = yui.YTreeItem(parentItem, currG["title"], icon)
                        else :
                            item = yui.YTreeItem(currG["title"], icon)
                        item.this.own(False)
                        currT[currG["title"]] = { "item" : item, "name" : groupName }
                        currT = currT[currG["title"]]
                        parentItem = item
                else:
                    # group is not in our group definition, but it's into the repository
                    # we just use it
                    if sg in currT :
                        currT = currT[sg]
                        parentItem = currT["item"]
                    else :
                        item = None
                        if parentItem:
                            item = yui.YTreeItem(parentItem, sg, icon)
                        else :
                            item = yui.YTreeItem(sg, icon)
                        item.this.own(False)
                        currT[sg] = { "item" : item, "name": groupName }
                        currT = currT[sg]
                        parentItem = item

        print ("End found %d groups" %len(rpm_groups))

        keylist = sorted(self.groupList.keys())
        v = []
        for key in keylist :
            item = self.groupList[key]['item']
            v.append(item)

        itemCollection = yui.YItemCollection(v)
        self.tree.startMultipleChanges()
        self.tree.deleteAllItems()
        self.tree.addItems(itemCollection)
        self.tree.doneMultipleChanges()
        yui.YUI.app().normalCursor()


    def setInfoOnWidget(self, pkg_name) :
        """
        write package description into info widget,
        this method performs a new query based on package name,
        future implementation could save package info into a temporary
        object structure linked to the selected item
        """
        packages = self.backend.get_packages_by_name(pkg_name, True)
        self.info.setValue("")
        if (len(packages)) :
            # NOTE first item of the list should be enough, different
            # arch should have same description for the package
            pkg = packages[0]
            if pkg :
                s = "<h2> %s - %s </h2>%s" %(pkg.name, pkg.summary, pkg.description)
                self.info.setValue(s)

    def _searchPackages(self, filter='all', createTreeItem=False) :
        '''
        retrieves the info from search input field and from the search type list
        to perform a paclage research and to fill the package list widget

        return False if an empty string used
        '''
        #clean up tree
        if createTreeItem:
            self._fillGroupTree()

        search_string = self.find_entry.value()
        if search_string :
            fields = []
            type_item = self.search_list.selectedItem()
            for field in self.local_search_types.keys():
                if self.local_search_types[field]['item'] == type_item:
                    fields.append(field)
                    break

            yui.YUI.app().busyCursor()
            strings = search_string.split(" ,|:;")
            ### TODO manage match_all, newest_only, tags
            match_all = False
            newest_only = False
            tags =""
            packages = self.backend.search(fields, strings, match_all, newest_only, tags )


            self.itemList = {}
            # {
            #   name-epoch_version-release.arch : { pkg: dnf-pkg, item: YItem}
            # }

            # Package API doc: http://dnf.readthedocs.org/en/latest/api_package.html
            for pkg in packages:
                if (filter == 'all' or (filter == 'to_update' and pkg.is_update ) or (filter == 'installed' and pkg.installed) or
                    (filter == 'not_installed' and not pkg.installed) or
                    (filter == 'skip_other' and (pkg.arch == 'noarch' or pkg.arch == platform.machine()))) :
                    item = yui.YCBTableItem(pkg.name , pkg.summary , pkg.version, pkg.release, pkg.arch)
                    item.check(self.packageQueue.checked(pkg))
                    self.itemList[self._pkg_name(pkg.name , pkg.epoch , pkg.version, pkg.release, pkg.arch)] = {
                        'pkg' : pkg, 'item' : item
                        }
                    if not self.update_only:
                        item.addCell("")
                        self._setStatusToItem(pkg,item)
                    item.this.own(False)

            keylist = sorted(self.itemList.keys())
            v = []
            for key in keylist :
                item = self.itemList[key]['item']
                v.append(item)

            itemCollection = yui.YItemCollection(v)

            self.packageList.startMultipleChanges()
            # cleanup old changed items since we are removing all of them
            self.packageList.setChangedItem(None)
            self.packageList.deleteAllItems()
            self.packageList.addItems(itemCollection)
            self.packageList.doneMultipleChanges()

            if createTreeItem:
                self.tree.startMultipleChanges()
                icon = self.gIcons.icon("Search")
                treeItem = yui.YTreeItem(self.gIcons.groups['Search']['title'] , icon, False)
                treeItem.setSelected(True)
                self.groupList[self.gIcons.groups['Search']['title']] = { "item" : treeItem, "name" : _("Search") }
                self.tree.addItem(treeItem)
                self.tree.rebuildTree()
                self.tree.doneMultipleChanges()
            yui.YUI.app().normalCursor()
        else :
            return False

        return True


    def _populate_transaction(self) :
        '''
        Clear and populate a transaction
        '''
        self.backend.ClearTransaction()
        for action in const.QUEUE_PACKAGE_TYPES:
            pkg_ids = self.packageQueue.get(action)
            for pkg_id in pkg_ids:
                logger.debug('adding: %s %s' %(const.QUEUE_PACKAGE_TYPES[action], pkg_id))
                rc, trans = self.backend.AddTransaction(
                    pkg_id, const.QUEUE_PACKAGE_TYPES[action])
                if not rc:
                    logger.error('AddTransaction result : %s: %s' % (rc, pkg_id))

    def handleevent(self):
        """
        Event-handler for the maindialog
        """
        while True:

            event = self.dialog.waitForEvent()

            eventType = event.eventType()

            rebuild_package_list = False
            group = None
            #event type checking
            if (eventType == yui.YEvent.CancelEvent) :
                break
            elif (eventType == yui.YEvent.MenuEvent) :
                ### MENU ###
                item = event.item()
                if (item) :
                    if  item == self.fileMenu['reset_sel'] :
                        self.packageQueue.clear()
                        sel = self.tree.selectedItem()
                        if sel :
                            group = self._groupNameFromItem(self.groupList, sel)
                            if (group == "Search"):
                                filter = self._filterNameSelected()
                                if not self._searchPackages(filter) :
                                    rebuild_package_list = True
                            else:
                                rebuild_package_list = True
                    elif item == self.fileMenu['reload']  :
                        self.reset_cache()
                    elif item == self.fileMenu['quit']    :
                        #### QUIT
                        break
                    elif item == self.helpMenu['help']  :
                        dialogs.warningMsgBox({'title' : _("Sorry"), "text": _("Not implemented yet")})
                    elif item == self.helpMenu['about']  :
                        self.AboutDialog.run()

            elif (eventType == yui.YEvent.WidgetEvent) :
                # widget selected
                widget  = event.widget()
                if (widget == self.quitButton) :
                    #### QUIT
                    break
                elif (widget == self.packageList) :
                    wEvent = yui.toYWidgetEvent(event)
                    if (wEvent.reason() == yui.YEvent.ValueChanged) :
                        changedItem = self.packageList.changedItem()
                        if changedItem :
                            for it in self.itemList:
                                if (self.itemList[it]['item'] == changedItem) :
                                    pkg = self.itemList[it]['pkg']
                                    if pkg.installed and self.backend.protected(pkg) :
                                        dialogs.warningMsgBox({'title' : _("Protected package selected"), "text": _("Package %s cannot be removed")%pkg.name, "richtext":True})
                                        sel = self.tree.selectedItem()
                                        if sel :
                                            group = self._groupNameFromItem(self.groupList, sel)
                                            if (group == "Search"):
                                                filter = self._filterNameSelected()
                                                if not self._searchPackages(filter) :
                                                    rebuild_package_list = True
                                            else:
                                                rebuild_package_list = True
                                    else :
                                        if changedItem.checked():
                                            self.packageQueue.add(pkg, 'i')
                                        else:
                                            self.packageQueue.add(pkg, 'r')
                                        self._setStatusToItem(pkg, self.itemList[it]['item'], True)
                                    break

                elif (widget == self.reset_search_button) :
                    #### RESET
                    rebuild_package_list = True
                    self.find_entry.setValue("")
                    self._fillGroupTree()

                elif (widget == self.find_button) :
                    #### FIND
                    filter = self._filterNameSelected()
                    if not self._searchPackages(filter, True) :
                        rebuild_package_list = True

                elif (widget == self.checkAllButton) :
                    for it in self.itemList:
                        pkg = self.itemList[it]['pkg']
                        self.packageQueue.add(pkg, 'i')
                        rebuild_package_list = True

                elif (widget == self.applyButton) :
                    #### APPLY
                    self._populate_transaction()
                    rc, result = self.backend.BuildTransaction()
                    if rc :
                        ok = True
                        if not self.always_yes:
                            transaction_result_dlg = dialogs.TransactionResult(self)
                            ok = transaction_result_dlg.run(result)

                        if ok:  # Ok pressed
                            self.infobar.info(_('Applying changes to the system'))
                            rc, result = self.backend.RunTransaction()
                            # This can happen more than once (more gpg keys to be
                            # imported)
                            while rc == 1:
                                logger.debug('GPG key missing: %s' % repr(result))
                                # get info about gpgkey to be comfirmed
                                values = self.backend._gpg_confirm
                                if values:  # There is a gpgkey to be verified
                                    (pkg_id, userid, hexkeyid, keyurl, timestamp) = values
                                    logger.debug('GPGKey : %s' % repr(values))
                                    resp = dialogs.ask_for_gpg_import(values)
                                    self.backend.ConfirmGPGImport(hexkeyid, resp)
                                    # tell the backend that the gpg key is confirmed
                                    # rerun the transaction
                                    # FIXME: It should not be needed to populate
                                    # the transaction again
                                    if resp:
                                        self._populate_transaction()
                                        rc, result = self.backend.BuildTransaction()
                                        rc, result = self.backend.RunTransaction()
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
                            self.packageQueue.clear()
                            self.backend.reload()
                    else:
                        logger.error('BuildTransaction failure')
                        logger.error(result)
                        s = "%s"%result
                        dialogs.warningMsgBox({'title' : _("BuildTransaction failure"), "text": s, "richtext":True})

                    sel = self.tree.selectedItem()
                    if sel :
                        group = self._groupNameFromItem(self.groupList, sel)
                        filter = self._filterNameSelected()
                        if (group == "Search"):
                            # force tree rebuilding to show new pacakge status
                            if not self._searchPackages(filter, True) :
                                rebuild_package_list = True
                        else:
                            if filter == "to_update":
                                self._fillGroupTree()
                            rebuild_package_list = True
                elif (widget == self.view_box) :
                    view = self._viewNameSelectet()
                    filter = self._filterNameSelected()
                    self.checkAllButton.setEnabled(filter == 'to_update')
                    rebuild_package_list = True
                    #reset find entry, it does not make sense here
                    self.find_entry.setValue("")
                    self._fillGroupTree()
                elif (widget == self.tree) or (widget == self.filter_box) :
                    if (widget == self.filter_box) :
                        view = self._viewNameSelectet()
                        filter = self._filterNameSelected()
                        self._fillGroupTree()
                        self.checkAllButton.setEnabled(filter == 'to_update')
                    sel = self.tree.selectedItem()
                    if sel :
                        group = self._groupNameFromItem(self.groupList, sel)
                        if (group == "Search"):
                            filter = self._filterNameSelected()
                            if not self._searchPackages(filter) :
                                rebuild_package_list = True
                        else:
                            rebuild_package_list = True
                else:
                    print(_("Unmanaged widget"))
            else:
                print(_("Unmanaged event"))

            if rebuild_package_list :
                sel = self.tree.selectedItem()
                if sel :
                    group = self._groupNameFromItem(self.groupList, sel)
                    filter = self._filterNameSelected()
                    self._fillPackageList(group, filter)

            sel = self.packageList.toCBYTableItem(self.packageList.selectedItem())
            if sel :
                pkg_name = sel.cell(0).label()
                self.setInfoOnWidget(pkg_name)

            if self.packageQueue.total() > 0 and not self.applyButton.isEnabled():
                self.applyButton.setEnabled()
            elif self.packageQueue.total() == 0 and self.applyButton.isEnabled():
                self.applyButton.setEnabled(False)


        self.dialog.destroy()

        # next line seems to be a workaround to prevent the qt-app from crashing
        # see https://github.com/libyui/libyui-qt/issues/41
        yui.YUILoader.deleteUI()
