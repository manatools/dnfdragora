# vim: set fileencoding=utf-8 :
'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Angelo Naselli <anaselli@linux.it>

@package dnfdragora
'''

import manatools.aui.yui as MUI

import sys
import os
import datetime
from gi.repository import GLib

import manatools.ui.basedialog as basedialog
import manatools.ui.common as common
from dnfdragora import const
import dnfdragora.misc as misc
from dnfdragora import const

import re
import gettext
import logging
logger = logging.getLogger('dnfdragora.dialogs')

class HistoryView:
    ''' History View Class'''

    def __init__(self, parent):
        self.parent = parent
        self.factory = self.parent.factory
        ''' _tid: hash containing tid: YItem'''
        self._tid = {}

    def _getTID(self, selectedItem):
        ''' get the tid connected to selected item '''
        tid = None
        for t in self._tid.keys():
            if self._tid[t] == selectedItem:
                tid = t
                break
        return tid

    def _populateHistory(self, selected=None):
        '''
        Populate history packages
        @param selected: selected date from tree
        '''
        itemVect = []
        if selected:
            pkgs = []
            tid = self._getTID(selected)
            if tid:
                pkgs = self.parent.backend.GetHistoryPackages(tid, sync=True)

            # Order by package name.arch
            names = {}
            names_pair = {}
            for elem in pkgs:
                pkg_id, state, is_inst = elem
                (n, e, v, r, a, repo_id) = misc.to_pkg_tuple(pkg_id)
                na = "%s.%s" % (n, a)
                if state in const.HISTORY_UPDATE_STATES:  # part of a pair
                    if na in names_pair:
                        # this is the updating pkg
                        if state in const.HISTORY_NEW_STATES:
                            names_pair[na].insert(0, elem)  # add first in list
                        else:
                            names_pair[na].append(elem)
                    else:
                        names_pair[na] = [elem]
                else:
                    names[na] = [elem]

            # order by primary state
            states = {}
            # pkgs without relatives
            for na in sorted(list(names)):
                pkg_list = names[na]
                pkg_id, state, is_inst = pkg_list[
                    0]  # Get first element (the primary (new) one )
                if state in states:
                    states[state].append(pkg_list)
                else:
                    states[state] = [pkg_list]
            # pkgs with relatives
            for na in sorted(list(names_pair)):
                pkg_list = names_pair[na]
                pkg_id, state, is_inst = pkg_list[
                    0]  # Get first element (the primary (new) one )
                if state in states:
                    states[state].append(pkg_list)
                else:
                    states[state] = [pkg_list]

            # filling tree view items
            for state in const.HISTORY_SORT_ORDER:
                if state in states:
                    num = len(states[state])
                    cat = MUI.YTreeItem(label="%s (%i)"%(const.HISTORY_STATE_LABLES[state], num), is_open=True)

                    for pkg_list in states[state]:
                        pkg_id, st, is_inst = pkg_list[0]
                        name = misc.pkg_id_to_full_name(pkg_id)
                        pkg_cat = MUI.YTreeItem(parent=cat, label=name, is_open=True)

                        if len(pkg_list) == 2:
                            pkg_id, st, is_inst = pkg_list[1]
                            name = misc.pkg_id_to_full_name(pkg_id)
                            item = MUI.YTreeItem(parent=pkg_cat, label=name, is_open=True)

                    itemVect.append(cat)

        itemCollection = None
        MUI.YUI.app().busyCursor()
        if selected:
            itemCollection = itemVect

        self._historyView.deleteAllItems()
        if selected:
            self._historyView.addItems(itemCollection)

        MUI.YUI.app().normalCursor()

    def _populateTree(self, data):
        '''
        Populate history date tree
        @param data list of date and tid
        '''
        self._tid = {}

        main = {}
        for tid, dt in data:
            # example of dt : 2017-11-01T13:37:50
            date = datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%S")

            # year
            if date.year not in main.keys():
                main[date.year] = {}
                item = MUI.YTreeItem(label=date.strftime("%Y"), is_open=True)
                main[date.year]['item'] = item

            mdict = main[date.year]
            # month
            if date.month not in mdict.keys():
                mdict[date.month] = {}
                item = MUI.YTreeItem(parent=main[date.year]['item'], label=date.strftime("%m"), is_open=True)
                mdict[date.month]['item'] = item

            ddict = mdict[date.month]
            # day
            if date.day not in ddict.keys():
                ddict[date.day] = {}
                item = MUI.YTreeItem(parent=mdict[date.month]['item'], label=date.strftime("%d"), is_open=True)
                ddict[date.day]['item'] = item
            ddict[date.day][date.strftime("%H:%M:%S")] = tid
            item = MUI.YTreeItem(parent=ddict[date.day]['item'], label=date.strftime("%H:%M:%S"), is_open=False)
            self._tid[tid]= item

        itemVect = []
        for year in main.keys():
            itemVect.append(main[year]['item'])

        #self._dlg .pollEvent()

        MUI.YUI.app().busyCursor()
        itemCollection = itemVect
        self._historyTree.deleteAllItems()
        self._historyTree.addItems(itemCollection)
        MUI.YUI.app().normalCursor()

    def _run_transaction(self):
        '''
        Run the undo transaction
        '''
        locked = False
        parent = self.parent
        if not parent :
            raise ValueError("Null parent")
        performedUndo = False

        try:
            rc, result = parent.backend.GetTransaction()
            if rc :
                transaction_result_dlg = TransactionResult(parent)
                ok = transaction_result_dlg.run(result)

                if ok:  # Ok pressed
                    parent.infobar.info(_('Undo transaction'))
                    rc, result = parent.backend.RunTransaction()
                    # This can happen more than once (more gpg keys to be
                    # imported)
                    while rc == 1:
                        logger.debug('GPG key missing: %s' % repr(result))
                        # get info about gpgkey to be confirmed
                        values = parent._gpg_confirm
                        if values:  # There is a gpgkey to be verified
                            (key_id, user_ids, key_fingerprint, key_url, timestamp) = values
                            logger.debug('GPGKey : %s' % repr(values))
                            resp = ask_for_gpg_import(values)
                            parent.backend.ConfirmGPGImport(key_id, resp)
                            # tell the backend that the gpg key is confirmed
                            # rerun the transaction
                            # FIXME: It should not be needed to populate
                            # the transaction again
                            if resp:
                                rc, result = parent.backend.GetTransaction()
                                rc, result = parent.backend.RunTransaction()
                            else:
                                # NOTE TODO answer no is the only way to exit, since it seems not
                                # to install the key :(
                                break
                        else:  # error in signature verification
                            infoMsgBox({'title' : _('Error checking package signatures'),
                                                'text' : '<br>'.join(result), 'richtext' : True })
                            break
                    if rc == 4:  # Download errors
                        infoMsgBox({'title'  : ngettext('Downloading error',
                            'Downloading errors', len(result)), 'text' : '<br>'.join(result), 'richtext' : True })
                        logger.error('Download error')
                        logger.error(result)
                    elif rc != 0:  # other transaction errors
                        infoMsgBox({'title'  : ngettext('Error in transaction',
                                    'Errors in transaction', len(result)), 'text' :  '<br>'.join(result), 'richtext' : True })
                        logger.error('RunTransaction failure')
                        logger.error(result)

                    parent.release_root_backend()
                    parent.backend.reload()
                    performedUndo = (rc == 0)
            else:
                logger.error('BuildTransaction failure')
                logger.error(result)
                s = "%s"%result
                warningMsgBox({'title' : _("Build transaction failure"), "text": s, "richtext":True})
        except:
            exc, msg = misc.parse_dbus_error()
            if 'AccessDeniedError' in exc:
                logger.warning("User pressed cancel button in policykit window")
                logger.warning("dnfdaemon client AccessDeniedError: %s ", msg)
            else:
                pass

        return performedUndo

    def _on_history_undo(self):
      '''Handle the undo button'''

      sel = self._historyTree.selectedItem()
      tid = self._getTID(sel)
      if tid:
        logger.debug('History Undo : %s', tid)
        self.parent.backend.HistoryUndo(tid)
        ## TODO REMOVE rc, messages = self.parent.backend.HistoryUndo(tid)
        ## TODO REMOVE if rc:
        ## TODO REMOVE     undo = self._run_transaction()
        ## TODO REMOVE else:
        ## TODO REMOVE     msg = "Can't undo history transaction :\n%s" % \
        ## TODO REMOVE         ("\n".join(messages))
        ## TODO REMOVE     logger.debug(msg)
        ## TODO REMOVE     warningMsgBox({
        ## TODO REMOVE         "title": _("History undo"),
        ## TODO REMOVE         "text":  msg,
        ## TODO REMOVE         "richtext": False,
        ## TODO REMOVE         })
      return True


    def run(self, data):
        '''
        Populate the TreeView with data and run the dialog
        @param data: list of transaction information date
        @return if undo action has been performed
        '''

        ## push application title
        appTitle = MUI.YUI.app().applicationTitle()
        ## set new title to get it in dialog
        MUI.YUI.app().setApplicationTitle(_("History") )
        minWidth  = 700  # pixels
        minHeight = 500  # pixels
        self._dlg     = self.factory.createPopupDialog()
        minSize = self.factory.createMinSize(self._dlg , minWidth, minHeight)
        layout  = self.factory.createVBox(minSize)
        hbox = self.factory.createHBox(layout)
        self._historyTree = self.factory.createTree(hbox, _("History (Date/Time)"))
        self._historyTree.setNotify(True)
        self._historyView = self.factory.createTree(hbox,_("Transaction History"))

        align = self.factory.createRight(layout)
        hbox = self.factory.createHBox(align)
        self._undoButton = self.factory.createPushButton(hbox, _("&Undo"))
        self._undoButton.setDisabled()
        self._closeButton = self.factory.createPushButton(hbox, _("&Close"))

        self._populateTree(data)
        self._populateHistory()

        #self._dlg .setDefaultButton(self._closeButton)

        performedUndo = False
        while (True) :
            event = self._dlg.waitForEvent()
            eventType = event.eventType()
            #event type checking
            if (eventType == MUI.YEventType.CancelEvent) :
                break
            elif (eventType == MUI.YEventType.WidgetEvent) :
                # widget selected
                widget = event.widget()

                if (widget == self._undoButton) :
                    performedUndo = self._on_history_undo()
                    if performedUndo:
                        break
                elif (widget == self._closeButton) :
                    break
                elif (widget == self._historyTree):
                    sel = self._historyTree.selectedItem()
                    if sel :
                        show_info = sel in self._tid.values()
                        self._undoButton.setEnabled(show_info)
                        #self._closeButton.setDefaultButton()
                        if not show_info:
                            sel = None
                    self._populateHistory(sel)

        self._dlg.destroy()

        #restore old application title
        MUI.YUI.app().setApplicationTitle(appTitle)

        return performedUndo


class PackageActionDialog:
    '''
      PackageActionDialog is a dialog that allows to select the action 
      to be performed on packages. Default behaviorn is Normal e.g.
      Installing, Updating or removing selected packages.
    '''

    def __init__(self, parent, actionValue):
        self.parent = parent
        self.factory = self.parent.factory
        self.actionValue = self.savedActionValue = actionValue
        
    def run(self):
        '''
          Propose a radio button list related to the possible actions
        '''

        ## push application title
        appTitle = MUI.YUI.app().applicationTitle()
        ## set new title to get it in dialog
        MUI.YUI.app().setApplicationTitle(_("Action on selected packages") )
        minWidth  = 400  # pixels
        minHeight = 250  # pixels
        dlg     = self.factory.createPopupDialog()
        minSize = self.factory.createMinSize(dlg, minWidth, minHeight)
        layout  = self.factory.createVBox(minSize)

        #labeledFrameBox - Actions
        frame = self.factory.createFrame(layout, "Actions")
        frame.setWeight( MUI.YUIDimension.YD_HORIZ, 1 )
        frame = self.factory.createHVCenter( frame )        
        frame = self.factory.createVBox( frame )
        
        Normal  = self.factory.createRadioButton(frame, _("Normal (Install/Upgrade/Remove)"), self.actionValue == const.Actions.NORMAL)
        Reinstall = self.factory.createRadioButton(frame, _("Reinstall"), self.actionValue == const.Actions.REINSTALL)
        if self.parent.update_only :
            Reinstall.setDisabled()
        Downgrade = self.factory.createRadioButton(frame, _("Downgrade"), self.actionValue == const.Actions.DOWNGRADE)
        if self.parent.update_only :
            Downgrade.setDisabled()
        DistroSync = self.factory.createRadioButton(frame, _("Distro Sync"), self.actionValue == const.Actions.DISTRO_SYNC)
    
        align = self.factory.createRight(layout)
        hbox = self.factory.createHBox(align)
        okButton = self.factory.createPushButton(hbox, _("&Ok"))
        cancelButton = self.factory.createPushButton(hbox, _("&Cancel"))
        #dlg.pollEvent()
        #dlg.setDefaultButton(cancelButton)

        while (True) :
            event = dlg.waitForEvent()
            eventType = event.eventType()
            #event type checking
            if (eventType == MUI.YEventType.CancelEvent) :
                self.actionValue = self.savedActionValue
                break
            elif (eventType == MUI.YEventType.WidgetEvent) :
                # widget selected
                widget = event.widget()

                if (widget == cancelButton) :
                    self.actionValue = self.savedActionValue
                    break
                elif (widget == okButton) :
                    break
                elif (widget == Normal) :
                    self.actionValue = const.Actions.NORMAL
                elif (widget == Reinstall) :
                    self.actionValue = const.Actions.REINSTALL
                elif (widget == Downgrade) :
                    self.actionValue = const.Actions.DOWNGRADE
                elif (widget == DistroSync) :
                    self.actionValue = const.Actions.DISTRO_SYNC

        dlg.destroy()

        #restore old application title
        MUI.YUI.app().setApplicationTitle(appTitle)

        return self.actionValue


class TransactionResult:
    '''
    TransactionResult is a dialog that shows the transaction dependencies before
    running the transaction.
    '''

    def __init__(self, parent):
        self.parent = parent
        self.factory = self.parent.factory


    def run(self, pkglist):
        '''
        Populate the TreeView with data and rund the dialog
        @param pkglist: list containing view data
        '''



        ## push application title
        appTitle = MUI.YUI.app().applicationTitle()
        ## set new title to get it in dialog
        MUI.YUI.app().setApplicationTitle(_("Transaction result") )
        # Pixel dimensions: wide enough to display full package NEVRAs
        # (e.g. python3-something-1.2.3-4.mga10.x86_64) without truncation;
        # tall enough for the dependency tree without excessive scrolling.
        minWidth  = 800  # pixels
        minHeight = 550  # pixels
        dlg     = self.factory.createPopupDialog()
        minSize = self.factory.createMinSize(dlg, minWidth, minHeight)
        layout  = self.factory.createVBox(minSize)
        treeWidget = self.factory.createTree(layout, _("Transaction dependency"))
        # Let the tree fill all available vertical space so the package list
        # is as visible as possible before the user needs to scroll.
        treeWidget.setStretchable(MUI.YUIDimension.YD_VERT, True)
        treeWidget.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
        sizeLabel = self.factory.createLabel(layout,"")

        align = self.factory.createRight(layout)
        hbox = self.factory.createHBox(align)
        okButton = self.factory.createPushButton(hbox, _("&Ok"))
        cancelButton = self.factory.createPushButton(hbox, _("&Cancel"))

        itemVect = []
        total_size = 0
        for action in pkglist.keys():
          if not pkglist[action]:
            continue
          label = const.TRANSACTION_RESULT_TYPES[action]
          level1Item = MUI.YTreeItem(label=label, is_open=True)

          for name in pkglist[action].keys():
            pkgid, size, replaces = (None, None, None)
            if len(pkglist[action][name]) > 2:
              pkgid, size  = pkglist[action][name][:2]
              replaces = pkglist[action][name][2:]
            else:
              pkgid, size = pkglist[action][name]

            label = pkgid + " (" +  misc.format_number(size) + ")"
            level2Item = MUI.YTreeItem(parent=level1Item, label=label, is_open=True)
            total_size += size
            if replaces:
                for rep in replaces:
                    label =  _("replacing ") + rep
                    item = MUI.YTreeItem(parent=level2Item, label=label, is_open=False)

          itemVect.append(level1Item)

        sizeLabel.setText(_("Total size ") +  misc.format_number(total_size))
        #dlg.pollEvent()

        MUI.YUI.app().busyCursor()
        itemCollection = itemVect
        treeWidget.deleteAllItems()
        treeWidget.addItems(itemCollection)
        MUI.YUI.app().normalCursor()

        #dlg.setDefaultButton(okButton)


        accepting = False
        while (True) :
            event = dlg.waitForEvent()
            eventType = event.eventType()
            #event type checking
            if (eventType == MUI.YEventType.CancelEvent) :
                break
            elif (eventType == MUI.YEventType.WidgetEvent) :
                # widget selected
                widget = event.widget()

                if (widget == cancelButton) :
                    break
                elif (widget == okButton) :
                    accepting = True
                    break

        dlg.destroy()

        #restore old application title
        MUI.YUI.app().setApplicationTitle(appTitle)

        return accepting

class AboutDialog:
    '''
    Create an about dialog
    '''

    def __init__(self, parent):
        '''
        Constructor
        @param parent: main parent dialog

        '''
        self.parent = parent
        self.factory = MUI.YUI.widgetFactory()
        # name        => the application name
        # version     =>  the application version
        # license     =>  the application license, the short length one (e.g. GPLv2, GPLv3, LGPLv2+, etc)
        # authors     =>  the string providing the list of authors; it could be html-formatted
        # description =>  the string providing a brief description of the application
        # logo        => the string providing the file path for the application logo (high-res image)
        # icon        => the string providing the file path for the application icon (low-res image)
        # credits     => the application credits, they can be html-formatted
        # information => other extra information, it can be html-formatted
        # dialog_mode => 1: classic style dialog, any other as tabbed style dialog
        self.name    = parent.appname
        self.version = const.VERSION
        self.license = "GPLv3"
        self.authors = "<h3>%s</h3><ul><li>%s</li><li>%s</li><li>%s</li></ul>"%(
                            _("Developers"),
                            "Angelo Naselli &lt;anaselli@linux.it&gt;",
                            "Neal   Gompa   &lt;ngompa13@gmail.com&gt;",
                            "Björn  Esser   &lt;besser82@fedoraproject.org&gt;")
        self.description = _("dnfdragora is a DNF frontend that works using GTK, ncurses and QT")
        # dialog mode retained for compatibility; common.AboutDialog handles layout
        # self.dialog_mode = common.AboutDialogMode.TABBED
        # TODO
        self.logo = parent.images_path + "dnfdragora-logo.png"
        self.icon = parent.icon
        self.credits = ""
        self.information = ""

    def run (self) :
        '''
        shows the about dialog
        '''
        info = {
          'name': self.name,
          'version': self.version,
          'license': self.license,
          'authors': self.authors,
          'description': self.description,
          'logo': self.logo,
          'icon': self.icon,
          'credits': self.credits,
          'information': self.information,
        }
        common.AboutDialog(info)

class RepoDialog(basedialog.BaseDialog):
    '''
    Dialog to manage repository enabling and disabling.
    Inherits from BaseDialog; uses eventManager for all widget events.
    Selecting any row (click or keyboard navigation) immediately populates
    the attribute panel at the bottom.
    '''

    def __init__(self, parent):
        basedialog.BaseDialog.__init__(
            self,
            _("Repository Management"),
            "",
            basedialog.DialogType.POPUP,
            700, 500,
        )
        self.parent = parent
        self.backend = self.parent.backend
        self.itemList = {}
        self.enabledRepos = []
        self.disabledRepos = []
        self._refresh_data = False
        # Reverse map: YTableItem → repo_id for O(1) lookup in _selectedRepository()
        self._itemToRepoId = {}
        # Last repo_id whose attributes were loaded; avoids redundant dbus calls
        # when the same row is still selected (e.g. checkbox toggle on same row).
        self._last_info_repo_id = None
        self.infoKeys = {
          'id'                  : _('Identifier'),
          'name'                : _('Name'),
          'type'                : _('Type'),
          'enabled'             : _('Enabled'),
          'priority'            : _('Priority'),
          'cost'                : _('Cost'),
          'baseurl'             : _('Base URL'),
          'metalink'            : _('Meta link'),
          'mirrorlist'          : _('Mirror list'),
          'metadata_expire'     : _('Metadata expire'),
          'cache_updated'       : _('Cache Updated'),
          'excludepkgs'         : _('Exclude packages'),
          'includepkgs'         : _('Include packages'),
          'skip_if_unavailable' : _('Skip if unavailable'),
          #
          'gpgkey'              : _('GPG key'),
          'gpgcheck'            : _('GPG check'),
          'repo_gpgcheck'       : _('Repo GPG check'),
          #
          'proxy'               : _('Proxy'),
          'proxy_username'      : _('Proxy username'),
          #'proxy_password'      : _('Proxy password'), TODO re-enable when it works
          #
          'repofile'            : _('Repo file'),
          'revision'            : _('Revision'),
          'content_tags'        : _('Content tags'),
          'distro_tags'         : _('Distro tags '),
          'updated'             : _('Updated'),
          'size'                : _('Size'),
          'pkgs'                : _('Packages'),
          'available_pkgs'      : _('Available packages'),
          'mirrors'             : _('Mirrors'),
        }

    def UIlayout(self, layout):
        '''Build the dialog widget tree.'''
        # Repo list (upper area)
        hbox_repos = self.factory.createHBox(layout)
        hbox_repos.setWeight(MUI.YUIDimension.YD_VERT, 55)

        checkboxed = True
        repoList_header = MUI.YTableHeader()
        repoList_header.addColumn("", checkboxed, alignment=MUI.YAlignmentType.YAlignCenter)
        repoList_header.addColumn(_('Name'))
        repoList_header.addColumn(_('Id'))
        self.repoList = self.factory.createTable(hbox_repos, repoList_header)
        self.repoList.setNotify(True)

        # Attribute panel (lower area)
        hbox_info = self.factory.createHBox(layout)
        hbox_info.setWeight(MUI.YUIDimension.YD_VERT, 35)

        info_header = MUI.YTableHeader()
        for col in [_('Information'), _('Value')]:
            info_header.addColumn(col)
        self.info = self.factory.createTable(hbox_info, info_header)

        # Button bar
        hbox_buttons = self.factory.createHBox(layout)
        hbox_buttons.setWeight(MUI.YUIDimension.YD_VERT, 10)

        self.applyButton = self.factory.createPushButton(hbox_buttons, _("&Apply"))
        self.applyButton.setWeight(MUI.YUIDimension.YD_HORIZ, 3)
        self.quitButton = self.factory.createPushButton(hbox_buttons, _("&Cancel"))
        self.quitButton.setWeight(MUI.YUIDimension.YD_HORIZ, 3)

        # Wire events
        self.eventManager.addWidgetEvent(self.repoList, self._onRepoListEvent)
        self.eventManager.addWidgetEvent(self.applyButton, self._onApply)
        self.eventManager.addWidgetEvent(self.quitButton, self._onCancel)
        self.eventManager.addCancelEvent(self._onCancel)

        # Populate the list
        self._populateRepoList()

    def _populateRepoList(self):
        '''Load repositories into the table and show attributes of the first row.'''
        repos = self.backend.GetRepositories(repo_attrs=['id'], enable_disable='enabled', sync=True)
        self.enabledRepos = [r['id'] for r in repos
                             if not r['id'].endswith('-source') and not r['id'].endswith('-debuginfo')]
        repos = self.backend.GetRepositories(repo_attrs=['id'], enable_disable='disabled', sync=True)
        self.disabledRepos = [r['id'] for r in repos
                              if not r['id'].endswith('-source') and not r['id'].endswith('-debuginfo')]

        self.itemList = {}
        self._itemToRepoId = {}
        self._last_info_repo_id = None
        for r in self.backend.get_repositories():
            item = MUI.YTableItem()
            item.addCell(bool(r['enabled']))
            item.addCell(str(r['name']))
            item.addCell(str(r['id']))
            self.itemList[r['id']] = {
                'item': item, 'name': r['name'], 'id': r['id'], 'enabled': r['enabled'],
            }
            self._itemToRepoId[item] = r['id']

        by_name = sorted(self.itemList.keys(), key=lambda k: self.itemList[k]['name'].casefold())
        v = [self.itemList[k]['item'] for k in by_name]
        self.repoList.deleteAllItems()
        self.repoList.addItems(v)

        # Explicitly select the first row so attributes are shown immediately.
        if v:
            try:
                self.repoList.selectItem(v[0], True)
            except Exception:
                pass
            first_id = by_name[0] if by_name else None
            if first_id:
                self._addAttributeInfo(first_id)

    def _selectedRepository(self):
        '''Return the repo id of the currently selected table row, or None.
        O(1) via the reverse-lookup dict built in _populateRepoList().
        '''
        sel = self.repoList.selectedItem()
        if sel:
            return self._itemToRepoId.get(sel)
        return None

    def _addAttributeInfo(self, repo_id):
        '''Fill the attribute table for repo_id.
        Updates self._last_info_repo_id so callers can skip redundant fetches.
        '''
        if not repo_id:
            return
        v = []
        try:
            repo_attrs = [a for a in self.infoKeys.keys()]
            ri = self.backend.GetRepositories(patterns=[repo_id], repo_attrs=repo_attrs, sync=True)
            logger.debug(ri)
            if len(ri) > 1:
                logger.warning("Got %d elements expected 1", len(ri))
            ri = ri[0]
            for k in sorted(ri.keys()):
                if k in ("enabled", "name", "id"):
                    continue
                key = None
                value = ""
                if ri[k]:
                    key = self.infoKeys.get(k, k)
                    if k == 'size':
                        value = misc.format_number(ri[k])
                    elif k == 'metadata_expire':
                        value = _('Never') if ri[k] <= -1 else _("%s second(s)" % ri[k])
                    else:
                        value = "%s" % (ri[k],)
                elif k == 'metadata_expire':
                    key = self.infoKeys[k]
                    value = _('Now')
                if key:
                    item = MUI.YTableItem()
                    item.addCell(str(key))
                    item.addCell(str(value))
                    v.append(item)
        except NameError as e:
            logger.error("dnfdaemon NameError: %s", e)
        except AttributeError as e:
            logger.error("dnfdaemon AttributeError: %s", e)
        except GLib.Error as err:
            logger.error("dnfdaemon client failure [%s]", err)
        except Exception:
            logger.error("Unexpected error: %s", sys.exc_info()[0])

        self.info.deleteAllItems()
        self.info.addItems(v)
        self._last_info_repo_id = repo_id

    # ── event handlers ──────────────────────────────────────────────────────

    def _onRepoListEvent(self, yui_event):
        '''Handle any event from the repo table.

        ValueChanged  → checkbox was toggled: update the in-memory enabled state.
        Any reason    → refresh the attribute panel for the now-selected row,
                        but only when the selection actually changed (avoids a
                        redundant synchronous dbus call on every checkbox click
                        that lands on the already-selected row).
        '''
        if yui_event.reason() == MUI.YEventReason.ValueChanged:
            changedItem = self.repoList.changedItem()
            if changedItem:
                try:
                    new_state = bool(changedItem.cell(0).checked())
                except Exception:
                    new_state = False
                repo_key = self._itemToRepoId.get(changedItem)
                if repo_key is not None:
                    self.itemList[repo_key]['enabled'] = new_state

        repo_id = self._selectedRepository()
        if repo_id and repo_id != self._last_info_repo_id:
            MUI.YUI.app().busyCursor()
            self._addAttributeInfo(repo_id)
            MUI.YUI.app().normalCursor()

    def _onApply(self):
        enabled_repos  = [k for k in self.itemList if self.itemList[k]['enabled'] and k in self.disabledRepos]
        disabled_repos = [k for k in self.itemList if not self.itemList[k]['enabled'] and k in self.enabledRepos]
        logger.info("Enabling repos: %s", " ".join(enabled_repos))
        # NOTE: only one async call can be in flight at a time; these are quick
        # but main window must know repos changed, so keep at least one async.
        if enabled_repos:
            self.backend.SetEnabledRepos(enabled_repos)
        if disabled_repos:
            self.backend.SetDisabledRepos(disabled_repos, sync=(bool(enabled_repos) and bool(disabled_repos)))
        self._refresh_data = True
        self.ExitLoop()

    def _onCancel(self):
        self.ExitLoop()

    def run(self):
        '''Run the dialog and return True if repos were changed.'''
        super().run()
        return self._refresh_data

class OptionDialog(basedialog.BaseDialog):
  def __init__(self, parent):
    basedialog.BaseDialog.__init__(self, _("dnfdragora options"), "dnfdragora", basedialog.DialogType.POPUP, 640, 480)
    self.parent = parent
    self.log_vbox = None
    self.widget_callbacks = []
    self._HSPACING_PX = 6
    self._VSPACING_PX = 12

  # ------------------------------------------------------------------
  # Safe config-access helpers
  # ------------------------------------------------------------------

  @staticmethod
  def _safe_cfg_get(cfg, *keys, default=None):
    """Navigate a nested dict safely; return *default* if any level is None or missing."""
    try:
      node = cfg if cfg is not None else {}
      for key in keys:
        if not isinstance(node, dict):
          return default
        node = node.get(key)
        if node is None:
          return default
      return node
    except Exception:
      return default

  def _user_prefs(self):
    """Return config.userPreferences as a dict, or {} if None/missing."""
    config = getattr(self.parent, 'config', None)
    return getattr(config, 'userPreferences', None) or {}

  def _system_settings(self):
    """Return config.systemSettings as a dict, or {} if None/missing."""
    config = getattr(self.parent, 'config', None)
    return getattr(config, 'systemSettings', None) or {}

  def _ensure_settings(self):
    """Return config.userPreferences['settings'] dict, creating the key path if needed.
    Safe to use both for reads and writes."""
    config = getattr(self.parent, 'config', None)
    if config is None:
      return {}  # throwaway – at least we won't crash
    if not isinstance(getattr(config, 'userPreferences', None), dict):
      config.userPreferences = {}
    return config.userPreferences.setdefault('settings', {})

  def UIlayout(self, layout):
    '''
    dnfdragora options layout implementation
    '''

    hbox_config = self.factory.createHBox(layout)
    self.factory.createVStretch(layout)
    hbox_bottom = self.factory.createHBox(layout)
    # Wrap the tree in MinSize to guarantee a minimum column width regardless
    # of the ReplacePoint content on the right (long labels in System options
    # would otherwise squeeze the tree below its usable width).
    tree_col = self.factory.createMinSize(hbox_config, 20, 3)
    tree_col.setWeight(MUI.YUIDimension.YD_HORIZ, 25)
    self.config_tree = self.factory.createTree(tree_col, "")
    self.config_tree.setStretchable(MUI.YUIDimension.YD_VERT, True)
    self.config_tree.setStretchable(MUI.YUIDimension.YD_HORIZ, True)

    self.eventManager.addWidgetEvent(self.config_tree, self.onChangeConfig, sendWidget=True)

    itemVect = []
    self.option_items = {
      "system" : None,
      "layout" : None,
      "logging" : None,
      }
    self.selected_option = None
    ### Options items
    #YTreeItem self, std::string const & label, std::string const & iconName, bool isOpen=False)
    # TODO add icons
    item = MUI.YTreeItem(_("System"))
    itemVect.append(item)    
    self.option_items ["system"] = item

    item = MUI.YTreeItem(_("Layout"))
    itemVect.append(item)
    self.option_items ["layout"] = item

    item = MUI.YTreeItem(_("Logging"))
    itemVect.append(item)
    self.option_items ["logging"] = item
    
    itemCollection = itemVect
    self.config_tree.addItems(itemCollection)
    self.config_tree.selectItem(itemVect[0], True)
    frame = self.factory.createFrame(hbox_config)
    frame.setStretchable(MUI.YUIDimension.YD_VERT, True)
    frame.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
    frame.setWeight(MUI.YUIDimension.YD_HORIZ, 75)
    self.config_tab = self.factory.createReplacePoint(frame)
    
    self.RestoreButton = self.factory.createPushButton(hbox_bottom, _("Restore &default"))
    self.eventManager.addWidgetEvent(self.RestoreButton, self.onRestoreButton)

    st = self.factory.createHStretch(hbox_bottom)

    self.quitButton = self.factory.createIconButton(hbox_bottom, "window-close",_("&Close"))
    self.eventManager.addWidgetEvent(self.quitButton, self.onQuitEvent)

    #self.dialog.setDefaultButton(self.quitButton)

    self.eventManager.addCancelEvent(self.onCancelEvent)
    self.onChangeConfig(self.config_tree)


  def onChangeConfig(self, obj):
    '''
    fill option configuration data starting from config tree selection
    '''
    logger.debug('Config tab %s', self.selected_option)
    
    if obj.widgetClass() == "YTree":
      item = self.config_tree.selectedItem()
      for k in self.option_items.keys():
        if self.option_items[k] == item:
          if k != self.selected_option :
            self.log_vbox = None
            logger.debug('Config tab changed to %s', k)
            self._cleanCallbacks()
            if k == "system":
              self._openSystemOptions()
            elif  k == "layout":
              self._openLayoutOptions()
            elif k == "logging":
              self._openLoggingOptions()

            self.selected_option = k
            break

  def _cleanCallbacks(self):
    '''
    clean old selectaion call backs
    '''
    logger.debug('Removing %d callbacks', len( self.widget_callbacks))
    for e in self.widget_callbacks:
      self.eventManager.removeWidgetEvent(e['widget'], e['handler'])
    self.widget_callbacks = []

  def _openSystemOptions(self):
    '''
    show system configuration options
    '''
    if self.config_tab.hasChildren():
      self.config_tab.deleteChildren()

    hbox = self.factory.createHBox(self.config_tab)
    self.factory.createHSpacing(hbox)
    vbox = self.factory.createVBox(hbox)
    self.factory.createHSpacing(hbox)

    # Title
    heading = self.factory.createHeading( vbox, _("System options") )
    self.factory.createVSpacing(vbox, 0.3*self._VSPACING_PX)
    heading.setAutoWrap()

    always_yes_val = self._safe_cfg_get(self._user_prefs(), 'settings', 'always_yes',
                                         default=self.parent.always_yes)

    self.always_yes  =  self.factory.createCheckBox(self.factory.createLeft(vbox), _("Run transactions on packages automatically without confirmation needed"), always_yes_val )
    self.always_yes.setNotify(True)
    self.eventManager.addWidgetEvent(self.always_yes, self.onAlwaysYesChange, True)
    self.widget_callbacks.append( { 'widget': self.always_yes, 'handler': self.onAlwaysYesChange} )

    self.upgrades_as_updates  =  self.factory.createCheckBox(self.factory.createLeft(vbox), _("Consider packages to upgrade as updates"), self.parent.upgrades_as_updates )
    self.upgrades_as_updates.setNotify(True)
    self.eventManager.addWidgetEvent(self.upgrades_as_updates, self.onUpgradesAsUpdates, True)
    self.widget_callbacks.append( { 'widget': self.upgrades_as_updates, 'handler': self.onUpgradesAsUpdates} )

    hide_update_menu_val = self._safe_cfg_get(self._user_prefs(), 'settings', 'hide_update_menu',
                                               default=False)

    self.hide_update_menu  =  self.factory.createCheckBox(self.factory.createLeft(vbox), _("Hide dnfdragora-update menu if there are no updates"), hide_update_menu_val )
    self.hide_update_menu.setNotify(True)
    self.eventManager.addWidgetEvent(self.hide_update_menu, self.onHideUpdateMenu, True)
    self.widget_callbacks.append( { 'widget': self.hide_update_menu, 'handler': self.onHideUpdateMenu} )

    self.factory.createVSpacing(vbox, 0.3*self._VSPACING_PX)

    # Determine update interval with fallbacks and robust parsing
    updateInterval = 180
    try:
      val = self._safe_cfg_get(self._user_prefs(), 'settings', 'interval for checking updates')
      if val is not None:
        updateInterval = int(val)
      else:
        val = self._safe_cfg_get(self._system_settings(), 'settings', 'update_interval')
        if val is not None:
          updateInterval = int(val)
    except (TypeError, ValueError):
      updateInterval = 180

    hbox = self.factory.createHBox(vbox)
    col1 = self.factory.createVBox(hbox)
    col2 = self.factory.createVBox(hbox)
    label = self.factory.createLabel(self.factory.createLeft(col1), _("Interval to check for updates (minutes)"))
    self.factory.createHSpacing(hbox)
    self.updateInterval = self.factory.createIntField(self.factory.createRight(col2), "", 30, 1440, updateInterval )
    self.updateInterval.setNotify(True)
    self.eventManager.addWidgetEvent(self.updateInterval, self.onUpdateIntervalChange, True)
    self.widget_callbacks.append( { 'widget': self.updateInterval, 'handler': self.onUpdateIntervalChange} )


    label = self.factory.createLabel(self.factory.createLeft(col1), _("Metadata expire time (hours)"))
    self.MDupdateInterval = self.factory.createIntField(self.factory.createRight(col2), "", 0, 720, self.parent.md_update_interval )
    self.MDupdateInterval.setNotify(True)
    self.eventManager.addWidgetEvent(self.MDupdateInterval, self.onMDUpdateIntervalChange, True)
    self.widget_callbacks.append( { 'widget': self.MDupdateInterval, 'handler': self.onMDUpdateIntervalChange} )


    self.factory.createVStretch(vbox)

    self.config_tab.showChild()

  def _openLayoutOptions(self):
    '''
    show layout configuration options
    '''
    if self.config_tab.hasChildren():
      self.config_tab.deleteChildren()

    hbox = self.factory.createHBox(self.config_tab)
    self.factory.createHSpacing(hbox)
    vbox = self.factory.createVBox(hbox)
    self.factory.createHSpacing(hbox)

    # Title
    heading = self.factory.createHeading( vbox, _("Layout options (active at next startup)") )
    self.factory.createVSpacing(vbox, 0.3*self._VSPACING_PX)
    heading.setAutoWrap()

    showUpdates = self._safe_cfg_get(self._user_prefs(), 'settings', 'show updates at startup',
                                      default=False)

    showAll = self._safe_cfg_get(self._user_prefs(), 'settings', 'do not show groups at startup',
                                  default=False)


    self.showUpdates =  self.factory.createCheckBox(self.factory.createLeft(vbox) , _("Show updates"), showUpdates )
    self.showUpdates.setNotify(True)
    self.eventManager.addWidgetEvent(self.showUpdates, self.onShowUpdates, True)
    self.widget_callbacks.append( { 'widget': self.showUpdates, 'handler': self.onShowUpdates} )

    self.showAll  =  self.factory.createCheckBox(self.factory.createLeft(vbox) , _("Do not show groups view"), showAll )
    self.showAll.setNotify(True)
    self.eventManager.addWidgetEvent(self.showAll, self.onShowAll, True)
    self.widget_callbacks.append( { 'widget': self.showAll, 'handler': self.onShowAll} )

    self.factory.createVStretch(vbox)
    self.config_tab.showChild()

  def _openSearchOptions(self):
    pass  # Search options moved to SearchDialog

  def _openLoggingOptions(self):
    '''
    show logging configuration options
    '''
    if self.config_tab.hasChildren():
      self.config_tab.deleteChildren()

    hbox = self.factory.createHBox(self.config_tab)
    self.factory.createHSpacing(hbox, 1.5*self._HSPACING_PX)
    vbox = self.factory.createVBox(hbox)
    self.factory.createHSpacing(hbox, 1.5*self._HSPACING_PX)

    # Title
    heading=self.factory.createHeading( vbox, _("Logging options (active at next startup)") )
    self.factory.createVSpacing(vbox, 0.3*self._VSPACING_PX)
    heading.setAutoWrap()

    log_enabled = self._safe_cfg_get(self._user_prefs(), 'settings', 'log', 'enabled',
                                      default=False)

    log_directory = self._safe_cfg_get(self._user_prefs(), 'settings', 'log', 'directory',
                                        default=os.path.expanduser("~"))

    level_debug = self._safe_cfg_get(self._user_prefs(), 'settings', 'log', 'level_debug',
                                      default=False)

    # Ensure the 'log' sub-dict exists in userPreferences['settings'] for later writes
    self._ensure_settings().setdefault('log', {})

    ####
    self.log_enabled = self.factory.createCheckBoxFrame(vbox, _("Enable logging"), log_enabled)
    self.log_enabled.setNotify(True)
    self.eventManager.addWidgetEvent(self.log_enabled, self.onEnableLogging, True)
    self.widget_callbacks.append( { 'widget': self.log_enabled, 'handler': self.onEnableLogging} )
    
    self.log_vbox = self.factory.createVBox(self.log_enabled)
    hbox = self.factory.createHBox(self.log_vbox)    
    self.log_directory = self.factory.createLabel(self.factory.createLeft(hbox), "")
    self.factory.createHSpacing(hbox)
    self.choose_dir = self.factory.createIconButton(hbox, "folder", _("Change &directory"))
    self.eventManager.addWidgetEvent(self.choose_dir, self.onChangeLogDirectory)
    self.widget_callbacks.append( { 'widget': self.choose_dir, 'handler': self.onChangeLogDirectory} )
    self.log_directory.setText(log_directory)
        
    self.level_debug = self.factory.createCheckBox(self.log_vbox , _("Debug level"), level_debug )
    self.level_debug.setNotify(True)
    self.eventManager.addWidgetEvent(self.level_debug, self.onLevelDebugChange, True)
    self.widget_callbacks.append( { 'widget': self.level_debug, 'handler': self.onLevelDebugChange} )

    self.log_vbox.setEnabled(log_enabled)

    self.factory.createVStretch(vbox)
    self.config_tab.showChild()

  def onEnableLogging(self, obj) :
    '''
    enable logging check box event
    '''
    if obj.widgetClass() == "YCheckBoxFrame":
      self.log_vbox.setEnabled(obj.value())
      self._ensure_settings().setdefault('log', {})['enabled'] = obj.value()
    else:
      logger.error("OptionDialog: Invalid object passed %s", obj.widgetClass())

  def onChangeLogDirectory(self):
    '''
    Change directory button has been invoked
    '''
    start_dir = self.log_directory.text() if self.log_directory.text() else os.path.expanduser("~")
    log_directory = MUI.YUI.app().askForExistingDirectory(
          start_dir,
          _("Choose log destination directory"))
    if log_directory:
      self.log_directory.setText(log_directory)
      self._ensure_settings().setdefault('log', {})['directory'] = self.log_directory.text()

  def onShowAll(self, obj):
    '''
    Show All Changing
    '''
    if obj.widgetClass() == "YCheckBox":    
      self._ensure_settings()['do not show groups at startup'] = obj.isChecked()
    else:
      logger.error("OptionDialog: Invalid object passed %s", obj.widgetClass())

  def onShowUpdates(self, obj):
    '''
    Show Updates Changing
    '''
    if obj.widgetClass() == "YCheckBox":
      self._ensure_settings()['show updates at startup'] = obj.isChecked()
    else:
      logger.error("OptionDialog: Invalid object passed %s", obj.widgetClass())

  def onFuzzySearch(self, obj):
    pass  # Search options moved to SearchDialog

  def onNewestOnly(self, obj):
    pass  # Search options moved to SearchDialog

  def onLevelDebugChange(self, obj):
    '''
    Debug level Changing
    '''
    if obj.widgetClass() == "YCheckBox":
      self._ensure_settings().setdefault('log', {})['level_debug'] = obj.isChecked()
    else:
      logger.error("OptionDialog: Invalid object passed %s", obj.widgetClass())

  def onUpdateIntervalChange(self, obj):
    '''
    manage an update interval change
    '''
    if obj.widgetClass() == "YIntField":
      self._ensure_settings()['interval for checking updates'] = obj.value()
    else:
      logger.error("OptionDialog: Invalid object passed %s", obj.widgetClass())

  def onMDUpdateIntervalChange(self, obj):
    '''
    manage an MD update interval change
    '''
    if obj.widgetClass() == "YIntField":
      self._ensure_settings().setdefault('metadata', {})['update_interval'] = obj.value()
      self.parent.md_update_interval = obj.value()
      logger.debug("update_interval %d", obj.value())
    else:
      logger.error("OptionDialog: Invalid object passed %s", obj.widgetClass())

  def onAlwaysYesChange(self, obj):
    '''
    Always Yes Changing
    '''
    if obj.widgetClass() == "YCheckBox":
      self._ensure_settings()['always_yes'] = obj.isChecked()
      self.parent.always_yes = obj.isChecked()
      logger.debug("always_yes %d", obj.isChecked())
    else:
      logger.error("OptionDialog: Invalid object passed %s", obj.widgetClass())

  def onUpgradesAsUpdates (self, obj):
    '''
    Consider Upgrades as Updates
    '''
    if obj.widgetClass() == "YCheckBox":
      s = self._ensure_settings()
      s['upgrades as updates'] = obj.isChecked()
      logger.debug("onUpgradesAsUpdates %d", obj.isChecked())
      self.parent.upgrades_as_updates = s['upgrades as updates']
    else:
      logger.error("OptionDialog: Invalid object passed %s", obj.widgetClass())

  def onHideUpdateMenu(self, obj):
    '''
    Hide update menu changing
    '''
    if obj.widgetClass() == "YCheckBox":
      self._ensure_settings()['hide_update_menu'] = obj.isChecked()
      logger.debug("hide_update_menu %d", obj.isChecked())
    else:
      logger.error("OptionDialog: Invalid object passed %s", obj.widgetClass())

  def onRestoreButton(self) :
    logger.debug('Restore pressed')
    k = self.selected_option
    if k == "system":
      s = self._ensure_settings()
      s['always_yes'] = False
      self.parent.always_yes = False
      s['interval for checking updates'] = 180
      s['metadata'] = {'update_interval': 48}
      self.parent.md_update_interval = 48
      self._openSystemOptions()
    elif  k == "layout":
      s = self._ensure_settings()
      s['show updates at startup'] = False
      s['do not show groups at startup'] = False
      self._openLayoutOptions()
    elif k == "logging":
      self._ensure_settings()['log'] = {
        'enabled': False,
        'directory': os.path.expanduser("~"),
        'level_debug': False,
      }
      self._openLoggingOptions()

  def onCancelEvent(self) :
    logger.debug("OptionDialog: Cancel button pressed")

  def onQuitEvent(self) :
    logger.debug("OptionDialog: Quit button pressed")
    try:
      self.parent.saveUserPreference()
    except Exception:
      logger.exception("OptionDialog: saveUserPreference raised; attempting direct config save")
      try:
        self.parent.config.saveUserPreferences()
      except Exception:
        logger.exception("OptionDialog: failed to save user preferences to disk")
    # BaseDialog needs to force to exit the handle event loop
    self.ExitLoop()


class SearchDialog(basedialog.BaseDialog):
  """
  Dedicated search popup for dnfdragora.

  Opens as a modal popup pre-populated with the parent's last search state.
  After run() returns, inspect:
    .action            : 'search' | 'clear' | 'cancel'
    .search_nevra      : bool — search in package names/NEVRA  (with_nevra)
    .search_provides   : bool — search in provides             (with_provides)
    .search_filenames  : bool — search in all file paths       (with_filenames)
    .search_binaries   : bool — search in binary paths only    (with_binaries)
    .search_src        : bool — include source RPMs            (with_src)
    .search_summary    : bool — search in summary, regexp only
    .search_text       : stripped search string
    .search_use_regexp : bool
    .search_repos      : list of repo IDs to restrict to ([] = all repos)
    .search_arches     : list of arch strings to restrict to ([] = all arches)
    .search_scope      : daemon scope string ('all','installed','available','upgrades','upgradable')
    .search_what_type  : str — daemon option name ('whatprovides',…) or None
    .search_what_value : str — capability string(s) for the what-query, comma-separated
  """

  def __init__(self, parent):
    basedialog.BaseDialog.__init__(
      self, _("Find packages"), "dnfdragora",
      basedialog.DialogType.POPUP, 520, -1
    )
    self.parent = parent
    # Pre-populate boolean "search in" flags from the parent's stored state
    self.search_nevra      = parent._search_nevra
    self.search_provides   = parent._search_provides
    self.search_filenames  = parent._search_filenames
    self.search_binaries   = parent._search_binaries
    self.search_src        = parent._search_src
    self.search_summary    = parent._search_summary
    self.search_text       = parent._search_text
    self.search_use_regexp = parent._search_use_regexp
    self.search_repos      = list(parent._search_repos)
    self.search_arches     = list(parent._search_arches)
    self.search_icase      = parent._search_icase
    self.search_newest_only = parent.newest_only
    self.search_fuzzy      = parent.fuzzy_search
    # search_scope is set in UIlayout() where _SCOPE_ORDER/_scope_labels are defined.
    self.search_scope      = 'all'
    self.search_what_type  = parent._search_what_type   # None or daemon option name
    self.search_what_value = parent._search_what_value  # capability string(s)
    # Keep last-used scope; fall back to filter_box only if no search has been done yet.
    self._last_scope       = parent._search_scope   # None = first time
    self.action = None   # 'search' | 'clear' | 'cancel'
    # Fetch repo and arch lists once from the parent's lazy caches
    self._repos  = parent._get_available_repos()
    self._arches = parent._get_available_arches()

  def UIlayout(self, layout):
    # Scope keys → exact daemon scope strings accepted by Search(scope=…).
    self._SCOPE_ORDER = ['all', 'installed', 'available', 'upgrades', 'upgradable']
    # Pre-initialise frame references so _updateRegexpState() can safely iterate
    # them even when called before all rows have been built.
    self._what_frame = None
    self._repo_frame = None
    self._arch_frame = None
    self._scope_labels = {
      'all'        : _("All"),
      'installed'  : _("Installed"),
      'available'  : _("Available"),
      'upgrades'   : _("Upgrades"),
      'upgradable' : _("Upgradable"),
    }
    # Scope: restore last used scope; use filter_box mapping only on first open.
    _filter_to_scope = {
      'all'          : 'all',
      'installed'    : 'installed',
      'not_installed': 'available',
      'to_update'    : 'upgrades',
      'skip_other'   : 'all',
    }
    if self._last_scope:
      self.search_scope = self._last_scope
    else:
      self.search_scope = _filter_to_scope.get(self.parent._filterNameSelected(), 'all')

    # ── Row 1: "Find:" label + input field ──────────────────────────────────
    # The Find field is dual-purpose:
    #   - text search mode: pattern string(s) for Search(patterns=[...])
    #   - dependency query mode: capability string(s) for Search(whatXXX=[...])
    _what_active = bool(self.search_what_type)
    hbox_find = self.factory.createHBox(layout)
    self.factory.createLabel(hbox_find, _("Find:"))
    self._find_entry = self.factory.createInputField(hbox_find, "")
    self._find_entry.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
    # Pre-populate with capability or text depending on current mode.
    self._find_entry.setValue(
        (self.search_what_value or "") if _what_active else (self.search_text or ""))
    self._find_entry.setNotify(False)
    self._find_entry.setHelpText(_(
        "Enter the search pattern. In text mode: words separated by spaces or commas. "
        "In dependency query mode: capability name (e.g. 'python3', '/usr/bin/python3')."))

    # ── Row 2: "Search in:" checkboxes ──────────────────────────────────────
    # Each checkbox maps directly to a dnf5daemon Search() boolean flag.
    # "Summary" is regexp-only and is enabled/disabled by _updateRegexpState().
    hbox_fields = self.factory.createHBox(layout)
    self.factory.createLabel(hbox_fields, _("Search in:"))
    self._nevra_check = self.factory.createCheckBox(hbox_fields, _("N&ames"))
    self._nevra_check.setChecked(self.search_nevra)
    self._nevra_check.setHelpText(_("Search in package names and NEVRA (name-epoch:version-release.arch)."))
    self._provides_check = self.factory.createCheckBox(hbox_fields, _("&Provides"))
    self._provides_check.setChecked(self.search_provides)
    self._provides_check.setHelpText(_("Also match packages whose Provides: tags include the search pattern."))
    self._filenames_check = self.factory.createCheckBox(hbox_fields, _("&Files"))
    self._filenames_check.setChecked(self.search_filenames)
    self._filenames_check.setHelpText(_("Match packages that own files whose path matches the pattern."))
    self._filenames_check.setNotify(True)
    self.eventManager.addWidgetEvent(self._filenames_check, self._onFilenamesChanged)
    self._binaries_check = self.factory.createCheckBox(hbox_fields, _("&Binaries"))
    self._binaries_check.setChecked(self.search_binaries)
    self._binaries_check.setHelpText(_("Restrict file matching to /usr/bin and /usr/sbin only (subset of Files)."))
    self._src_check = self.factory.createCheckBox(hbox_fields, _("S&ources"))
    self._src_check.setChecked(self.search_src)
    self._src_check.setHelpText(_("Include source RPMs (*.src.rpm) in the results."))
    self.factory.createHSpacing(hbox_fields, 1)
    self._summary_check = self.factory.createCheckBox(hbox_fields, _("Su&mmary"))
    self._summary_check.setChecked(self.search_summary)
    self._summary_check.setHelpText(_("Search in package summaries. Only available in regexp mode."))

    # ── Row 3: Scope combobox + search-modifier checkboxes ───────────────────
    hbox_opts = self.factory.createHBox(layout)
    self.factory.createLabel(hbox_opts, _("Scope:"))
    self._scope_items = {}
    scope_coll = []
    for key in self._SCOPE_ORDER:
      item = MUI.YItem(self._scope_labels[key])
      if key == self.search_scope:
        item.setSelected(True)
      self._scope_items[key] = item
      scope_coll.append(item)
    self._scope_list = self.factory.createComboBox(hbox_opts, "")
    self._scope_list.addItems(scope_coll)
    self._scope_list.setHelpText(_("Limit the search to a subset of packages: all, installed, available to install, upgrades or upgradable."))
    self.factory.createHStretch(hbox_opts)
    self._use_regexp = self.factory.createCheckBox(hbox_opts, _("Use &regexp"))
    self._use_regexp.setChecked(self.search_use_regexp)
    self._use_regexp.setNotify(True)
    self._use_regexp.setHelpText(_("Treat the Find field as a regular expression (Python re syntax). Disables multi-field search."))
    self.eventManager.addWidgetEvent(self._use_regexp, self._updateRegexpState)
    self._latest_only_check = self.factory.createCheckBox(hbox_opts, _("&Latest only"))
    self._latest_only_check.setChecked(self.search_newest_only)
    self._latest_only_check.setHelpText(_("Show only the latest version of each package name."))
    self._fuzzy_check = self.factory.createCheckBox(hbox_opts, _("Fu&zzy search"))
    self._fuzzy_check.setChecked(self.search_fuzzy)
    self._fuzzy_check.setHelpText(_("Automatically add wildcards around each search token (e.g. 'gtk' becomes '*gtk*'). Disabled in regexp mode."))
    self._icase_check = self.factory.createCheckBox(hbox_opts, _("Case &sensitive"))
    self._icase_check.setChecked(not self.search_icase)   # icase=True → unchecked
    self._icase_check.setNotify(True)
    self._icase_check.setHelpText(_("When checked, the search is case-sensitive. By default search is case-insensitive."))
    # ── Row 3b: Dependency / what-query (CheckBoxFrame) ─────────────────────
    # When active, the Find field is used as the capability string.
    # Search-in checkboxes, regexp, fuzzy and icase are disabled in this mode.
    self._WHAT_ORDER = [
      '', 'whatprovides', 'whatrequires', 'whatdepends', 'whatrecommends',
      'whatenhances', 'whatsuggests', 'whatsupplements', 'whatobsoletes', 'whatconflicts',
    ]
    self._what_labels = {
      ''              : _('(none)'),
      'whatprovides'  : _('provide'),
      'whatrequires'  : _('require'),
      'whatdepends'   : _('depend on'),
      'whatrecommends': _('recommend'),
      'whatenhances'  : _('enhance'),
      'whatsuggests'  : _('suggest'),
      'whatsupplements': _('supplement'),
      'whatobsoletes' : _('obsolete'),
      'whatconflicts' : _('conflict with'),
    }
    what_frame = self.factory.createCheckBoxFrame(
      layout, _('&Dependency query'), _what_active)
    what_frame.setNotify(True)
    what_frame.setHelpText(_("When checked, the Find field is used as a capability name and packages are searched by dependency relation instead of text pattern."))
    self.eventManager.addWidgetEvent(what_frame, self._onWhatFrameToggled, True)
    self._what_frame = what_frame
    what_frame.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
    hbox_what = self.factory.createHBox(what_frame)
    self.factory.createLabel(hbox_what, _('Find packages that:'))
    self._what_items = {}
    what_item_list = []
    for key in self._WHAT_ORDER:
      if not key:
        continue   # skip '(none)' — not needed inside the frame
      item = MUI.YItem(self._what_labels[key])
      if key == (self.search_what_type or 'whatprovides'):
        item.setSelected(True)
      self._what_items[key] = item
      what_item_list.append(item)
    self._what_combo = self.factory.createComboBox(hbox_what, '')
    self._what_combo.addItems(what_item_list)
    self._what_combo.setHelpText(_("Choose the dependency relation to search: provide, require, depend on, recommend, etc."))
    self.factory.createLabel(hbox_what, _('the capability in "Find" field'))

    self._updateRegexpState()
    self._updateWhatState()

    # ── Row 4: Repository filter (multi-selection) ───────────────────────────
    if self._repos:
      frame = self.factory.createCheckBoxFrame(layout, _("Limit to repositories"), bool(self.search_repos))
      frame.setNotify(True)
      frame.setHelpText(_("When checked, the search is restricted to the selected repositories."))
      frame.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
      self.eventManager.addWidgetEvent(frame, self._onRepoFrameToggled, True)
      self._repo_frame = frame

      self._repo_box = self.factory.createMultiSelectionBox(frame, "")
      repo_items = []
      self._repo_items = {}   # repo_id → YItem
      for repo in self._repos:
        item = MUI.YItem(repo['name'] if repo['name'] else repo['id'])
        if repo['id'] in self.search_repos:
          item.setSelected(True)
        self._repo_items[repo['id']] = item
        repo_items.append(item)
      self._repo_box.addItems(repo_items)
      # box starts visible only if there are pre-existing selections (visibility set in _initVisibility)
    else:
      self._repo_frame = None
      self._repo_box   = None
      self._repo_items = {}

    # ── Row 4: Architecture filter (multi-selection) ──────────────────────────
    if self._arches:
      arch_frame = self.factory.createCheckBoxFrame(layout, _("Limit to architectures"), bool(self.search_arches))
      arch_frame.setNotify(True)
      arch_frame.setHelpText(_("When checked, the search is restricted to the selected CPU architectures."))
      arch_frame.setStretchable(MUI.YUIDimension.YD_HORIZ, True)
      self.eventManager.addWidgetEvent(arch_frame, self._onArchFrameToggled, True)
      self._arch_frame = arch_frame

      self._arch_box = self.factory.createMultiSelectionBox(arch_frame, "")
      arch_items = []
      self._arch_items = {}   # arch string → YItem
      for arch in self._arches:
        item = MUI.YItem(arch)
        if arch in self.search_arches:
          item.setSelected(True)
        self._arch_items[arch] = item
        arch_items.append(item)
      self._arch_box.addItems(arch_items)
      # box starts visible only if there are pre-existing selections (visibility set in _initVisibility)
    else:
      self._arch_frame = None
      self._arch_box   = None
      self._arch_items = {}

    # ── Row 5: action buttons ─────────────────────────────────────────────────
    hbox_btns = self.factory.createHBox(layout)
    self.factory.createHStretch(hbox_btns)
    self._search_button = self.factory.createIconButton(
      hbox_btns, 'edit-find', _("&Search"))
    self._search_button.setHelpText(_("Run the search and show matching packages."))
    self._clear_button = self.factory.createIconButton(
      hbox_btns, 'edit-clear', _("&Clear"))
    self._clear_button.setHelpText(_("Clear the Find field and reset the dependency query frame."))
    self._close_button = self.factory.createIconButton(
      hbox_btns, 'window-close', _("C&lose"))
    self._close_button.setHelpText(_("Close this dialog without running a new search."))

    self.eventManager.addWidgetEvent(self._search_button, self._onSearch)
    self.eventManager.addWidgetEvent(self._clear_button,  self._onClear)
    self.eventManager.addWidgetEvent(self._close_button,  self._onClose)
    self.eventManager.addCancelEvent(self._onClose)

  # ── helpers ──────────────────────────────────────────────────────────────

  def _setupUI(self):
    """Build the widget tree then force GTK backend creation so we can set
    initial visibility before the event loop starts."""
    super()._setupUI()
    # open() creates all GTK backend widgets; must happen before _initVisibility
    self.dialog.open()
    self._initVisibility()

  def _initVisibility(self):
    """Collapse the content area of filter frames when no items are pre-selected."""
    if self._repo_frame is not None:
      self._repo_frame.showContent(bool(self.search_repos))
    if self._arch_frame is not None:
      self._arch_frame.showContent(bool(self.search_arches))
    if self._what_frame is not None:
      self._what_frame.showContent(bool(self.search_what_type))
    # Apply initial enable/disable state for what-mode compatibility
    self._updateWhatState()

  def _currentScope(self):
    sel = self._scope_list.selectedItem()
    for key, item in self._scope_items.items():
      if item == sel:
        return key
    return 'all'

  def _currentWhatType(self):
    """Return the daemon option name currently selected in the what-combo, or ''."""
    sel = self._what_combo.selectedItem()
    for key, item in self._what_items.items():
      if item == sel:
        return key
    return ''

  def _updateWhatState(self):
    """Enable/disable widgets based on whether dependency-query mode is active.

    When the Dependency query frame is checked:
      - Find field is used as capability string → search-in checkboxes, regexp,
        fuzzy and icase are disabled (they only apply to text search).
    When the frame is unchecked:
      - All text-search options are re-enabled and regexp state is restored.
    """
    is_what = bool(self._what_frame is not None and self._what_frame.value())
    # Search-in checkboxes: only valid for text search
    for cb in (self._nevra_check, self._provides_check, self._filenames_check,
               self._binaries_check, self._src_check, self._summary_check):
      try:
        cb.setEnabled(not is_what)
      except Exception:
        pass
    # Regexp, fuzzy, icase: only valid for text search
    for cb in (self._use_regexp, self._fuzzy_check, self._icase_check):
      try:
        cb.setEnabled(not is_what)
        if is_what:
          cb.setChecked(False)
      except Exception:
        pass
    if not is_what:
      self._updateRegexpState()

  def _selectedRepos(self):
    """Return list of repo IDs currently selected in the multi-selection box."""
    if self._repo_box is None or self._repo_frame is None:
      return []
    if not self._repo_frame.value():
      return []
    selected = []
    try:
      sel_items = self._repo_box.selectedItems()
    except Exception:
      sel_items = []
    for repo_id, item in self._repo_items.items():
      if item in sel_items:
        selected.append(repo_id)
    return selected

  def _selectedArches(self):
    """Return list of arch strings currently selected in the arch multi-selection box."""
    if self._arch_box is None or self._arch_frame is None:
      return []
    if not self._arch_frame.value():
      return []
    selected = []
    try:
      sel_items = self._arch_box.selectedItems()
    except Exception:
      sel_items = []
    for arch, item in self._arch_items.items():
      if item in sel_items:
        selected.append(arch)
    return selected

  # ── event handlers ───────────────────────────────────────────────────────

  def _onFilenamesChanged(self):
    """Uncheck Binaries if Files is unchecked (binaries are a subset of files)."""
    if not self._filenames_check.isChecked():
      try:
        self._binaries_check.setChecked(False)
      except Exception:
        pass

  def _updateRegexpState(self):
    """Enable/disable checkboxes based on regexp mode.

    Non-regexp (Search() API): with_nevra, with_provides, with_filenames,
    with_binaries, with_src are valid; Summary must be disabled.
    Regexp (search() API): only a single text field (summary or names) is used;
    the Search()-only flags are disabled. icase, fuzzy, dependency-query,
    repository and architecture filters are also disabled (they only apply to
    the multi-field Search() path).
    """
    is_regexp = self._use_regexp.isChecked()
    # Checkboxes valid only in non-regexp Search() mode.
    for cb in (self._provides_check, self._filenames_check,
               self._binaries_check, self._src_check):
      try:
        cb.setEnabled(not is_regexp)
      except Exception:
        pass
    # Summary is valid only in regexp mode (backend.search() field).
    try:
      self._summary_check.setEnabled(is_regexp)
      if not is_regexp:
        self._summary_check.setChecked(False)
    except Exception:
      pass
    # Fuzzy search is incompatible with regexp (would wrap the whole pattern in *…*).
    try:
      self._fuzzy_check.setEnabled(not is_regexp)
      if is_regexp:
        self._fuzzy_check.setChecked(False)
    except Exception:
      pass
    # icase / case-sensitive: only meaningful in non-regexp mode.
    try:
      self._icase_check.setEnabled(not is_regexp)
    except Exception:
      pass
    # Dependency query, repo filter and arch filter are incompatible with regexp:
    # backend.search() does not support them.
    for frame in (self._what_frame, self._repo_frame, self._arch_frame):
      if frame is None:
        continue
      try:
        frame.setEnabled(not is_regexp)
        if is_regexp:
          frame.setValue(False)
          frame.showContent(False)
      except Exception:
        pass

  def _onRepoFrameToggled(self, obj):
    """Expand or collapse the repo list when the CheckBoxFrame is toggled."""
    if self._repo_frame is not None:
      self._repo_frame.showContent(obj.value())

  def _onArchFrameToggled(self, obj):
    """Expand or collapse the arch list when the CheckBoxFrame is toggled."""
    if self._arch_frame is not None:
      self._arch_frame.showContent(obj.value())

  def _onWhatFrameToggled(self, obj):
    """Expand or collapse the what-query when the CheckBoxFrame is toggled."""
    if self._what_frame is not None:
      self._what_frame.showContent(obj.value())
    self._updateWhatState()

  def _onSearch(self):
    # Read boolean "search in" flags; non-regexp ones are invalid when regexp is active.
    is_regexp = self._use_regexp.isChecked()
    self.search_nevra      = self._nevra_check.isChecked()
    self.search_provides   = (not is_regexp) and self._provides_check.isChecked()
    self.search_filenames  = (not is_regexp) and self._filenames_check.isChecked()
    self.search_binaries   = (not is_regexp) and self._binaries_check.isChecked()
    self.search_src        = (not is_regexp) and self._src_check.isChecked()
    self.search_summary    = is_regexp and self._summary_check.isChecked()
    self.search_text       = self._find_entry.value().strip()
    self.search_use_regexp = is_regexp
    self.search_repos      = self._selectedRepos()
    self.search_arches     = self._selectedArches()
    self.search_icase      = not self._icase_check.isChecked()
    self.search_newest_only = self._latest_only_check.isChecked()
    self.search_fuzzy      = self._fuzzy_check.isChecked()
    self.search_scope      = self._currentScope()
    # Read dependency/what-query state.
    # Capability string comes from the same Find field as the text search.
    self.search_what_type  = None
    self.search_what_value = ''
    if self._what_frame is not None and self._what_frame.value():
      wtype = self._currentWhatType()
      wval  = self.search_text   # already stripped above from _find_entry
      if wtype and wval:
        self.search_what_type  = wtype
        self.search_what_value = wval
        # Dependency query is exclusive: clear text so the main UI shows the
        # right label and doesn't trigger a text search.
        self.search_text = ''
    # Validate regex before accepting — avoids an unbreakable error loop in the main UI.
    if self.search_use_regexp and self.search_text:
      try:
        re.compile(self.search_text)
      except re.error as exc:
        warningMsgBox({
          'title': _('Invalid regular expression'),
          'text':  str(exc),
          'richtext': False,
        })
        return   # stay in the dialog so the user can fix the pattern
    self.action = 'search'
    self.ExitLoop()

  def _onClear(self):
    """Clear the Find field and reset the dependency query frame. Stay in dialog."""
    try:
      self._find_entry.setValue('')
    except Exception:
      pass
    if self._what_frame is not None:
      try:
        self._what_frame.setValue(False)
        self._what_frame.showContent(False)
      except Exception:
        pass
      self._updateWhatState()

  def _onClose(self):
    self.action = 'cancel'
    self.ExitLoop()


def warningMsgBox (info) :
    '''
    This function creates an Warning dialog and show the message
    passed as input.

    @param info: dictionary, information to be passed to the dialog.
            title     =>     dialog title
            text      =>     string to be swhon into the dialog
            richtext  =>     True if using rich text
    '''
    if (not info) :
        return 0

    return common.warningMsgBox(info)


def infoMsgBox (info) :
    '''
    This function creates an Info dialog and show the message
    passed as input.

    @param info: dictionary, information to be passed to the dialog.
            title     =>     dialog title
            text      =>     string to be swhon into the dialog
            richtext  =>     True if using rich text
    '''
    if (not info) :
        return 0

    return common.infoMsgBox(info)

def msgBox (info) :
    '''
    This function creates a dialog and show the message passed as input.

    @param info: dictionary, information to be passed to the dialog.
            title     =>     dialog title
            text      =>     string to be swhon into the dialog
            richtext  =>     True if using rich text
    '''
    if (not info) :
        return 0

    return common.msgBox(info)


def askOkCancel (info) :
    '''
    This function create an OK-Cancel dialog with a <<title>> and a
    <<text>> passed as parameters.

    @param info: dictionary, information to be passed to the dialog.
        title     =>     dialog title
        text      =>     string to be swhon into the dialog
        richtext  =>     True if using rich text
        default_button => optional default button [1 => Ok - any other values => Cancel]

    @output:
        False: Cancel button has been pressed
        True:  Ok button has been pressed
    '''
    if (not info) :
        return False

    return common.askOkCancel(info)

def askYesOrNo (info) :
    '''
    This function create an Yes-No dialog with a <<title>> and a
    <<text>> passed as parameters.

    @param info: dictionary, information to be passed to the dialog.
        title     =>     dialog title
        text      =>     string to be swhon into the dialog
        richtext  =>     True if using rich text
        default_button => optional default button [1 => Yes - any other values => No]
        size => [row, coulmn]

    @output:
        False: No button has been pressed
        True:  Yes button has been pressed
    '''
    if (not info) :
        return False

    return common.askYesOrNo(info)


def ask_for_gpg_import (values):
    '''
    This function asks if user wants to import or not the gpg keys.
    @output:
        False: No button has been pressed
        True:  Yes button has been pressed
    '''
    (key_id, user_ids, key_fingerprint, key_url, timestamp) = values

    # dnf5daemon delivers user_ids as a list (dbus.Array → list[str]).
    # Join multiple IDs; fall back to str() for any unexpected type.
    if isinstance(user_ids, list):
        display_user = ', '.join(str(u) for u in user_ids)
    else:
        display_user = str(user_ids) if user_ids else ''

    # key_url can be None when the key is embedded in the repository metadata
    # rather than hosted at a separate URL.
    if key_url:
        display_url = key_url.replace("file://", "")
    else:
        display_url = _("(embedded in repository metadata)")

    # dnf5daemon delivers timestamp as an int (Unix epoch).
    # Convert to a human-readable local datetime string.
    if isinstance(timestamp, int):
        display_timestamp = str(datetime.datetime.fromtimestamp(timestamp))
    else:
        display_timestamp = str(timestamp) if timestamp else ''

    msg = (_('Do you want to import this GPG key?<br>'
             '<br>Key        : 0x%(id)s:<br>'
             'Userid     : "%(user)s"<br>'
             'Fingerprint: "%(fingerprint)s"<br>'
             'Timestamp  : "%(timestamp)s"<br>'
             'From       : %(file)s') %
           {'id': key_id,
            'user': display_user,
            'fingerprint': key_fingerprint,
            'timestamp': display_timestamp,
            'file': display_url})

    return askYesOrNo({'title' : _("GPG key missed"),
                       'text': msg,
                       'default_button' : 1,
                       'richtext' : True,
                       'size' : [60, 10]})
