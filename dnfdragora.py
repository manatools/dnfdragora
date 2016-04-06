#!/usr/bin/python3

'''
dnfdragora is a graphical frontend based on rpmdragora implementation
that uses dnf as rpm backend, due to libyui python bindings dnfdragora
is able to comfortably behave like a native gtk or qt5 or ncurses application

License: GPLv3

Author:  Andelo Naselli <anaselli@linux.it>

@package dnfdragora
'''

import sys
import platform
import yui

import dnfbase
import groupicons

#################
# class mainGui #
#################
class mainGui():
    """
    Main class
    """

    def __init__(self):

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

        yui.YUI.app().setApplicationTitle("Software Management - dnfdragora")
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

        self.factory.createHeading(hbox_iconbar, "Software Management")

        hbox_top = self.factory.createHBox(vbox)
        hbox_middle = self.factory.createHBox(vbox)
        hbox_bottom = self.factory.createHBox(vbox)
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

        packageList_header.addColumn("Status")

        self.packageList = self.mgaFactory.createCBTable(hbox_middle,packageList_header,yui.YCBTableCheckBoxOnFirstColumn)
        self.packageList.setWeight(0,50)
        self.packageList.setImmediateMode(True)

        self.filters = {
            'all' : {'title' : "All"},
            'installed' : {'title' : "Installed"},
            'not_installed' : {'title' : "Not installed"}
        }
        ordered_filters = [ 'all', 'installed', 'not_installed' ]
        if platform.machine() == "x86_64" :
            # NOTE this should work on other architectures too, but maybe it
            #      is a nonsense, at least for i586
            self.filters['skip_other'] = {'title' : "Show %s and noarch only" % platform.machine()}
            ordered_filters.append('skip_other')

        # TODO add backports
        self.views = {
            'all' : {'title' : "All"},
            'meta_pkgs' : {'title' : "Meta packages"},
            'gui_pkgs' : {'title' : "Packages with GUI"},
            'all_updates' : {'title' : "All updates"},
            'security' : {'title' : "Security updates"},
            'bugfix' : {'title' : "Bugfixes updates"},
            'normal' : {'title' : "General updates"}
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
            'normal'      : {'title' : "in names"       },
            'descriptions': {'title' : "in descriptions"},
            'summaries'   : {'title' : "in summaries"   },
            'files'       : {'title' : "in file names"  }
        }
        search_types = ['normal', 'descriptions', 'summaries', 'files' ]

        self.search_menu = self.factory.createComboBox(hbox_top,"")
        itemColl.clear()
        for s in search_types:
            item = yui.YItem(self.local_search_types[s]['title'], False)
            if s == search_types[0] :
                item.setSelected(True)
            # adding item to local_search_types to find the item selected
            self.local_search_types[s]['item'] = item
            itemColl.push_back(item)
            item.this.own(False)

        self.search_menu.addItems(itemColl)
        self.search_menu.setNotify(True)

        self.find_entry = self.factory.createInputField(hbox_top, "")

        #TODO icon_file = File::ShareDir::dist_file(ManaTools::Shared::distName(), "images/manalog.png")
        icon_file = ""
        self.find_button = self.factory.createIconButton(hbox_top, icon_file, "Search")
        self.find_button.setWeight(0,6)
        self.dialog.setDefaultButton(self.find_button)
        self.find_entry.setKeyboardFocus()

        #TODO icon_file = File::ShareDir::dist_file(ManaTools::Shared::distName(), "images/rpmdragora/clear_22x22.png");
        self.reset_search_button = self.factory.createIconButton(hbox_top, icon_file, "Reset")
        self.reset_search_button.setWeight(0,7)
        self.find_entry.setWeight(0,10)

        self.info = self.factory.createRichText(hbox_bottom,"Test")
        self.info.setWeight(0,40)
        self.info.setWeight(1,40);

        self.applyButton = self.factory.createIconButton(hbox_footbar,"","&Apply")
        self.applyButton.setWeight(0,6)

        self.quitButton = self.factory.createIconButton(hbox_footbar,"","&Quit")
        self.quitButton.setWeight(0,6)

        self.dnf = dnfbase.DnfBase()
        self.dialog.pollEvent();
        self._fillGroupTree()
        sel = self.tree.selectedItem()
        group = None
        if sel :
            group = self._groupNameFromItem(self.groupList, sel)

        self._fillPackageList(group)
        sel = self.packageList.toCBYTableItem(self.packageList.selectedItem())
        if sel :
            pkg_name = sel.cell(0).label()
            self.setInfoOnWidget(pkg_name)

    def _pkg_name(self, name, epoch, version, release, arch) :
        '''
            return a package name in the form name-epoch_version-release.arch
        '''
        return ("{0}-{1}_{2}-{3}.{4}".format(name, epoch, version, release, arch))

    def _fillPackageList(self, groupName=None) :
        '''
        fill package list filtered by group if groupName is given,
        and checks installed packages it also clean up temporary lists
        for install/remove packages if any.
        Special value for groupName 'All' means all packages
        '''
        self.toRemove = []
        self.toInstall = []

        yui.YUI.app().busyCursor()
        packages = dnfbase.Packages(self.dnf)

        self.itemList = {}
        # {
        #   name-epoch_version-release.arch : { pkg: dnf-pkg, item: YItem}
        # }
        v = []
        # Package API doc: http://dnf.readthedocs.org/en/latest/api_package.html
        for pkg in packages.installed :
            if groupName and (groupName == pkg.group or groupName == 'All') :
                item = yui.YCBTableItem(pkg.name , pkg.summary , pkg.version, pkg.release, pkg.arch)
                item.check(True)
                self.itemList[self._pkg_name(pkg.name , pkg.epoch , pkg.version, pkg.release, pkg.arch)] = {
                    'pkg' : pkg, 'item' : item
                    }
                item.this.own(False)

        # Package API doc: http://dnf.readthedocs.org/en/latest/api_package.html
        for pkg in packages.available:
            if groupName and (groupName == pkg.group or groupName == 'All') :
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
        rpm_groups = {}
        yui.YUI.app().busyCursor()
        packages = dnfbase.Packages(self.dnf)
        for pkg in packages.all:
            if not pkg.group in rpm_groups:
                rpm_groups[pkg.group] = 1

        rpm_groups = sorted(rpm_groups.keys())
        gIcons = groupicons.GroupIcons()
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
        #NOTE workaround to get YItemCollection working in python
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
        packages = dnfbase.Packages(self.dnf)
        packages.all
        q = packages.query
        p_list = q.filter(name = pkg_name)
        self.info.setValue("")
        if (len(p_list)) :
            # NOTE first item of the list should be enough, different
            # arch should have same description for the package
            pkg = p_list[0]
            if pkg :
                s = "<h2> %s - %s </h2>%s" %(pkg.name, pkg.summary, pkg.description)
                self.info.setValue(s)


    def handleevent(self):
        """
        Event-handler for the maindialog
        """
        while True:

            event = self.dialog.waitForEvent()

            eventType = event.eventType()

            #event type checking
            if (eventType == yui.YEvent.CancelEvent) :
                break
            elif (eventType == yui.YEvent.WidgetEvent) :
                # widget selected
                widget  = event.widget()
                if (widget == self.quitButton) :
                    break
                elif (widget == self.packageList) :
                    wEvent = yui.toYWidgetEvent(event)
                    if (wEvent.reason() == yui.YEvent.ValueChanged) :
                        print("TODO checked\n")

                    sel = self.packageList.toCBYTableItem(self.packageList.selectedItem())
                    if sel :
                        pkg_name = sel.cell(0).label()
                        self.setInfoOnWidget(pkg_name)

                elif (widget == self.tree) :
                    sel = self.tree.selectedItem()
                    group = None
                    if sel :
                        group = self._groupNameFromItem(self.groupList, sel)
                    self._fillPackageList(group)
                else:
                    print("Unmanaged widget")
            else:
                print("Unmanaged yet")



        self.dialog.destroy()


if __name__ == "__main__":
    main_gui = mainGui()
    main_gui.handleevent()
