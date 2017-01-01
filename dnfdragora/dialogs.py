'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Andelo Naselli <anaselli@linux.it>

@package dnfdragora
'''

# NOTE part of this code is imported from yumex-dnf

import yui
from dnfdragora import const
import dnfdragora.misc as misc

import gettext
from gettext import gettext as _

class TransactionResult:

    def __init__(self, parent):
        self.parent = parent
        self.factory = self.parent.factory


    def run(self, pkglist):
        '''
        Populate the TreeView with data and rund the dialog
        @param pkglist: list containing view data
        '''

        ## push application title
        appTitle = yui.YUI.app().applicationTitle()
        ## set new title to get it in dialog
        yui.YUI.app().setApplicationTitle(_("Transaction result") )
        minWidth  = 80;
        minHeight = 25;
        dlg     = self.factory.createPopupDialog(yui.YDialogNormalColor)
        minSize = self.factory.createMinSize(dlg, minWidth, minHeight)
        layout  = self.factory.createVBox(minSize)
        treeWidget = self.factory.createTree(layout, _("Transaction dependency"))
        sizeLabel = self.factory.createLabel(layout,"")

        align = self.factory.createRight(layout)
        hbox = self.factory.createHBox(align)
        okButton = self.factory.createPushButton(hbox, _("&Ok"))
        cancelButton = self.factory.createPushButton(hbox, _("&Cancel"))

        itemVect = []
        total_size = 0
        for sub, lvl1 in pkglist:
            label = const.TRANSACTION_RESULT_TYPES[sub]
            level1Item = yui.YTreeItem(label, True)
            level1Item.this.own(False)

            for pkgid, size, replaces in lvl1:

                label = misc.pkg_id_to_full_name(pkgid) + " (" +  misc.format_number(size) + ")"
                level2Item = yui.YTreeItem(level1Item, label, True)
                level2Item.this.own(False)

                # packages that need to be downloaded
                if sub in ['install', 'update', 'install-deps',
                           'update-deps', 'obsoletes']:
                    total_size += size
                for r in replaces:
                    (n, e, v, r, a, repo_id) = misc.to_pkg_tuple(r)
                    label = _("replacing {}").format(n), a, "%s.%s" % (v, r), repo_id, misc.format_number(size)
                    item = yui.YTreeItem(level2Item, label, True)
                    item.this.own(False)

            itemVect.append(level1Item)

        itemCollection = yui.YItemCollection(itemVect)
        treeWidget.startMultipleChanges()
        treeWidget.deleteAllItems()
        treeWidget.addItems(itemCollection)
        sizeLabel.setText(_("Total size ") +  misc.format_number(total_size))
        treeWidget.doneMultipleChanges()
        yui.YUI.app().normalCursor()

        dlg.setDefaultButton(okButton)

        accepting = False
        while (True) :
            event = dlg.waitForEvent()
            eventType = event.eventType()
            #event type checking
            if (eventType == yui.YEvent.CancelEvent) :
                break
            elif (eventType == yui.YEvent.WidgetEvent) :
                # widget selected
                widget = event.widget()

                if (widget == cancelButton) :
                    break
                elif (widget == okButton) :
                    accepting = True
                    break

        dlg.destroy()

        #restore old application title
        yui.YUI.app().setApplicationTitle(appTitle)

        return accepting

