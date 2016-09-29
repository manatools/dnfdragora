
'''
dnfdragora is a graphical frontend based on rpmdragora implementation
that uses dnf as rpm backend, due to libyui python bindings dnfdragora
is able to comfortably behave like a native gtk or qt5 or ncurses application

License: GPLv3

Author:  Andelo Naselli <anaselli@linux.it>

@package dnfdragora
'''

import os
import sys
import platform
import yui

import dnfdragora.basedragora
import dnfdragora.groupicons as groupicons
import dnfdragora.progress_ui as progress_ui

import gettext
from gettext import gettext as _

#################
# class mainGui #
#################
class mainGui(dnfdragora.basedragora.BaseDragora):
    """
    Main class
    """

    def __init__(self, options={}):

        dnfdragora.basedragora.BaseDragora.__init__(self)
        self.options = options
        self._progressBar = None
        self.toRemove = []
        self.toInstall = []
        self.itemList = {}
        # {
        #   name-epoch_version-release.arch : { pkg: dnf-pkg, item: YItem}
        # }
        self.groupList = {}
        # {
        #    localized_name = { "item" : item, "name" : groupName }
        # }
        APP="dnfdragora"
        # TODO : perhaps fix with a relative path
        DIR="/usr/share/locale"
        gettext.bindtextdomain(APP, DIR)
        gettext.textdomain(APP)

        yui.YUI.app().setApplicationTitle(_("Software Management - dnfdragora"))
        #TODO fix icons
        wm_icon = "/usr/share/icons/rpmdrake.png"
        yui.YUI.app().setApplicationIcon(wm_icon)

        MGAPlugin = "mga"

        self.factory = yui.YUI.widgetFactory()
        mgaFact = yui.YExternalWidgets.externalWidgetFactory(MGAPlugin)
        self.mgaFactory = yui.YMGAWidgetFactory.getYMGAWidgetFactory(mgaFact)
        self.optFactory = yui.YUI.optionalWidgetFactory()

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
        self.factory.createImage(hbox_iconbar, wm_icon)

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
        columns = [ 'Name', 'Summary', 'Version', 'Release', 'Arch']

        packageList_header.addColumn("")
        for col in (columns):
            packageList_header.addColumn(col)

        packageList_header.addColumn(_("Status"))

        self.packageList = self.mgaFactory.createCBTable(hbox_middle,packageList_header,yui.YCBTableCheckBoxOnFirstColumn)
        self.packageList.setWeight(0,50)
        self.packageList.setImmediateMode(True)

        self.filters = {
            'all' : {'title' : _("All")},
            'installed' : {'title' : _("Installed")},
            'not_installed' : {'title' : _("Not installed")}
        }
        ordered_filters = [ 'all', 'installed', 'not_installed' ]
        if platform.machine() == "x86_64" :
            # NOTE this should work on other architectures too, but maybe it
            #      is a nonsense, at least for i586
            self.filters['skip_other'] = {'title' : _("Show %s and noarch only") % platform.machine()}
            ordered_filters.append('skip_other')

        # TODO add backports
        self.views = {
            'all' : {'title' : _("All")},
            'meta_pkgs' : {'title' : _("Meta packages")},
            'gui_pkgs' : {'title' : _("Packages with GUI")},
            'all_updates' : {'title' : _("All updates")},
            'security' : {'title' : _("Security updates")},
            'bugfix' : {'title' : _("Bugfixes updates")},
            'normal' : {'title' : _("General updates")}
        }
        ordered_views = [ 'all', 'meta_pkgs', 'gui_pkgs', 'all_updates', 'security', 'bugfix', 'normal']

        self.view_box = self.factory.createComboBox(hbox_top,"")
        itemColl = yui.YItemCollection()

        for v in ordered_views:
            item = yui.YItem(self.views[v]['title'], False)
            # adding item to views to find the item selected
            self.views[v]['item'] = item
            itemColl.push_back(item)
            item.this.own(False)

        self.view_box.addItems(itemColl)
        self.view_box.setNotify(True)

        self.filter_box = self.factory.createComboBox(hbox_top,"")
        itemColl.clear()

        for f in ordered_filters:
            item = yui.YItem(self.filters[f]['title'], False)
            # adding item to filters to find the item selected
            self.filters[f]['item'] = item
            itemColl.push_back(item)
            item.this.own(False)

        self.filter_box.addItems(itemColl)
        self.filter_box.setNotify(True)

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

        #TODO icon_file = File::ShareDir::dist_file(ManaTools::Shared::distName(), "images/manalog.png")
        icon_file = ""
        self.find_button = self.factory.createIconButton(hbox_top, icon_file, _("&Search"))
        self.find_button.setWeight(0,6)
        self.dialog.setDefaultButton(self.find_button)
        self.find_entry.setKeyboardFocus()

        #TODO icon_file = File::ShareDir::dist_file(ManaTools::Shared::distName(), "images/rpmdragora/clear_22x22.png");
        self.reset_search_button = self.factory.createIconButton(hbox_top, icon_file, _("&Reset"))
        self.reset_search_button.setWeight(0,7)
        self.find_entry.setWeight(0,10)

        self.info = self.factory.createRichText(hbox_bottom,_("Test"))
        self.info.setWeight(0,40)
        self.info.setWeight(1,40);

        self.infobar = progress_ui.ProgressBar(self.dialog, pbar_layout)

        self.applyButton = self.factory.createIconButton(hbox_footbar,"",_("&Apply"))
        self.applyButton.setWeight(0,6)

        self.quitButton = self.factory.createIconButton(hbox_footbar,"",_("&Quit"))
        self.quitButton.setWeight(0,6)

        self.dnf = None #dnfbase.DnfBase()
        self.dialog.pollEvent();
        self._fillGroupTree()
        sel = self.tree.selectedItem()
        group = None
        if sel :
            group = self._groupNameFromItem(self.groupList, sel)

        filter = self._filterNameSelected()
        self._fillPackageList(group, filter)
        sel = self.packageList.toCBYTableItem(self.packageList.selectedItem())
        if sel :
            pkg_name = sel.cell(0).label()
            self.setInfoOnWidget(pkg_name)

    #def get_infobar(self) :
        #if self._progressBar is None:
            #self._progressBar = progress_ui.Progress()
        #return self._progressBar
    
    #def release_infobar(self):
        #if self._progressBar is not None:
            #del self._progressBar
            #self._progressBar = None
    
    def _pkg_name(self, name, epoch, version, release, arch) :
        '''
            return a package name in the form name-epoch_version-release.arch
        '''
        return ("{0}-{1}_{2}-{3}.{4}".format(name, epoch, version, release, arch))

    def _fillPackageList(self, groupName=None, filter="all") :
        '''
        fill package list filtered by group if groupName is given,
        and checks installed packages.
        Special value for groupName 'All' means all packages
        Available filters are:
        all, installed, not_installed and skip_other
        '''

        yui.YUI.app().busyCursor()

        self.itemList = {}
        # {
        #   name-epoch_version-release.arch : { pkg: dnf-pkg, item: YItem}
        # }
        pkgs = ()
        if (groupName != 'All') :
            pkgs = self.backend.get_group_packages(groupName, 'all')
        if pkgs :
            v = []
            for pkg in pkgs :
                if filter == 'all' or filter == 'installed' or (filter == 'skip_other' and (pkg.arch == 'noarch' or pkg.arch == platform.machine())) :
                    item = yui.YCBTableItem(pkg.name , pkg.summary , pkg.version, pkg.release, pkg.arch)
                    if pkg.installed :
                        item.check(True)
                    self.itemList[self._pkg_name(pkg.name , pkg.epoch , pkg.version, pkg.release, pkg.arch)] = {
                        'pkg' : pkg, 'item' : item
                        }
                    item.this.own(False)
        else :

            installed = self.backend.get_packages('installed')
            v = []
            for pkg in installed :
                if groupName and (groupName == pkg.group or groupName == 'All') :
                    if filter == 'all' or filter == 'installed' or (filter == 'skip_other' and (pkg.arch == 'noarch' or pkg.arch == platform.machine())) :
                        item = yui.YCBTableItem(pkg.name , pkg.summary , pkg.version, pkg.release, pkg.arch)
                        item.check(True)
                        self.itemList[self._pkg_name(pkg.name , pkg.epoch , pkg.version, pkg.release, pkg.arch)] = {
                            'pkg' : pkg, 'item' : item
                            }
                        item.this.own(False)

            available = self.backend.get_packages('available')
            for pkg in available:
                if groupName and (groupName == pkg.group or groupName == 'All') :
                    if filter == 'all' or filter == 'not_installed' or (filter == 'skip_other' and (pkg.arch == 'noarch' or pkg.arch == platform.machine())) :
                        item = yui.YCBTableItem(pkg.name , pkg.summary , pkg.version, pkg.release, pkg.arch)
                        self.itemList[self._pkg_name(pkg.name , pkg.epoch , pkg.version, pkg.release, pkg.arch)] = {
                            'pkg' : pkg, 'item' : item
                            }
                        item.this.own(False)

        keylist = sorted(self.itemList.keys())

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

    def _filterNameSelected(self) :
        '''
        return the filter name index from the selected filter
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

    def _getAllGroupIDList(self, groups, new_groups):
        for g in groups :
            if (type(g) is str) :
                new_groups.append(g)
                break
            else :
               self. _getAllGroupIDList(g, new_groups)

    def _fillGroupTree(self) :
        '''
        fill the group tree, look for the retrieved groups and set their icons
        from groupicons module
        '''

        self.groupList = {}
        rpm_groups = []
        yui.YUI.app().busyCursor()

        print ("Start looking for groups")
        # get group comps
        rpm_groups = self.backend.get_groups()
        if rpm_groups :
            groups = []
            self._getAllGroupIDList(rpm_groups, groups)
            rpm_groups = groups
        else:
            #don't have comps try tags
            rpm_groups = self.backend.get_groups_from_packages()

        print ("End found %d groups" %len(rpm_groups))

        rpm_groups = sorted(rpm_groups)
        icon_path = self.options['icon_path'] if 'icon_path' in self.options.keys() else None
        gIcons = groupicons.GroupIcons(icon_path)
        groups = gIcons.groups()

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
                icon = gIcons.icon(groupName)

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
            newest_only = True
            tags =""
            packages = self.backend.search(fields, strings, match_all, newest_only, tags )


            self.itemList = {}
            # {
            #   name-epoch_version-release.arch : { pkg: dnf-pkg, item: YItem}
            # }

            # Package API doc: http://dnf.readthedocs.org/en/latest/api_package.html
            for pkg in packages:
                if (filter == 'all' or (filter == 'installed' and pkg.installed) or
                    (filter == 'not_installed' and not pkg.installed) or
                    (filter == 'skip_other' and (pkg.arch == 'noarch' or pkg.arch == platform.machine()))) :
                    item = yui.YCBTableItem(pkg.name , pkg.summary , pkg.version, pkg.release, pkg.arch)
                    item.check(pkg.installed)
                    self.itemList[self._pkg_name(pkg.name , pkg.epoch , pkg.version, pkg.release, pkg.arch)] = {
                        'pkg' : pkg, 'item' : item
                        }
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
                icon_path = self.options['icon_path'] if 'icon_path' in self.options.keys() else None
                gIcons = groupicons.GroupIcons(icon_path)
                icon = gIcons.icon("Search")
                treeItem = yui.YTreeItem(gIcons.groups()['Search']['title'] , icon, False)
                treeItem.setSelected(True)
                self.groupList[gIcons.groups()['Search']['title']] = { "item" : treeItem, "name" : _("Search") }
                self.tree.addItem(treeItem)
                self.tree.rebuildTree()
                self.tree.doneMultipleChanges()
            yui.YUI.app().normalCursor()
        else :
            return False

        return True


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
                                    if changedItem.checked():
                                        self.backend.AddTransaction(self.itemList[it]['pkg'].pkg_id, 'install')
                                    else:
                                        self.backend.AddTransaction(self.itemList[it]['pkg'].pkg_id, 'remove')
                                    break

                        print(_("TODO checked, managing also version and arch\n"))

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

                elif (widget == self.applyButton) :
                    #### APPLY
                    rc, result = self.backend.BuildTransaction()
                    rc, result = self.backend.RunTransaction()

                    #if os.getuid() == 0:
                        #self.dnf.apply_transaction()
                        #self.dnf.fill_sack() # refresh the sack

                        ## TODO next line works better but installing and then removing or viceversa
                        ##      crashes anyway
                        ##self.dnf = dnfbase.DnfBase()
                        #sel = self.tree.selectedItem()
                        #if sel :
                            #group = self._groupNameFromItem(self.groupList, sel)
                            #if (group == "Search"):
                                #filter = self._filterNameSelected()
                                #if not self._searchPackages(filter) :
                                    #rebuild_package_list = True
                            #else:
                                #rebuild_package_list = True
                        #self.dnf.close()
                    #else:
                        # TODO use a dialog instead
                    #    print(_("You must be root to apply changes"))

                elif (widget == self.tree) or (widget == self.filter_box) :
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



        self.dialog.destroy()
