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
import dnfbase
import yui



#################
# class mainGui #
#################
class mainGui():
    """
    Main class
    """

    def __init__(self):
        
        self.toRemove = [];
        self.toInstall = [];
        
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
        columns = [ '', 'Name', 'Summary', 'Version', 'Release', 'Arch']
                
        packageList_header.addColumn("")
        for col in (columns):
            packageList_header.addColumn(col)

        packageList_header.addColumn("Status")

        self.packageList = self.mgaFactory.createCBTable(hbox_middle,packageList_header,yui.YCBTableCheckBoxOnFirstColumn)
        self.packageList.setWeight(0,50)
        self.packageList.setImmediateMode(True)

        self.info = self.factory.createRichText(hbox_bottom,"Test")
        self.info.setWeight(0,40)
        self.info.setWeight(1,40);
    
        self.applyButton = self.factory.createIconButton(hbox_footbar,"","&Apply")
        self.applyButton.setWeight(0,6)

        self.quitButton = self.factory.createIconButton(hbox_footbar,"","&Quit")
        self.quitButton.setWeight(0,6)
        
        self.dnf = dnfbase.DnfBase()
        self._fillPackageList()


    def _fillPackageList(self) :
        '''
        _fillPackageList fill package list and checks installed packages
        it also clean up temporary lists for install/remove packages if
        any
        '''
        self.toRemove = []
        self.toInstall = []
        
        yui.YUI.app().busyCursor()
        packages = dnfbase.Packages(self.dnf)
        
        v = []
        # Package API doc: http://dnf.readthedocs.org/en/latest/api_package.html
        for pkg in packages.installed :
            item = yui.YCBTableItem("", pkg.name , "" , pkg.version, pkg.release, pkg.arch)
            item.check(True)
            v.append(item)

        # Package API doc: http://dnf.readthedocs.org/en/latest/api_package.html
        for pkg in packages.available:
            item = yui.YCBTableItem("", pkg.name , "" , pkg.version, pkg.release, pkg.arch)
            v.append(item)

        #NOTE workaround to get YItemCollection working in python
        itemCollection = yui.YItemCollection(v)

        self.packageList.startMultipleChanges()
        # cleanup old changed items since we are removing all of them
        self.packageList.setChangedItem(None)
        self.packageList.deleteAllItems()

        self.packageList.addItems(itemCollection)

        self.dialog.doneMultipleChanges()
        yui.YUI.app().normalCursor()
        

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
                    #wEvent = yui.toYWidgetEvent(event)
                    #if (wEvent.reason() == yui.YEvent.ValueChanged) :
                        #print("TODO checked\n")
                    print("TODO selected\n")
                    #sel = self.packageList.selectedItem()
                    #print (sel.label())
                    #_detaillist_callback($detail_list->selectedItem(), $info, \%$options);
                else:
                    print("Unmanaged widget")
            else:
                print("Unmanaged yet")
            
                

        self.dialog.destroy()


if __name__ == "__main__":
    main_gui = mainGui()
    main_gui.handleevent()
