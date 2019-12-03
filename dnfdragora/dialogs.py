# vim: set fileencoding=utf-8 :
'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Angelo Naselli <anaselli@linux.it>

@package dnfdragora
'''

# NOTE part of this code is imported from yumex-dnf

import yui
import sys
import os
import datetime
import dnfdaemon.client

from dnfdragora import const
import dnfdragora.misc as misc
from dnfdragora import const

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
                pkgs = self.parent.backend.GetHistoryPackages(tid)

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
            # pkgs with releatives
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
                    cat = yui.YTreeItem("%s (%i)" %
                            (const.HISTORY_STATE_LABLES[state], num), True)
                    cat.this.own(False)

                    for pkg_list in states[state]:
                        pkg_id, st, is_inst = pkg_list[0]
                        name = misc.pkg_id_to_full_name(pkg_id)
                        pkg_cat = yui.YTreeItem(cat, name, True)
                        pkg_cat.this.own(False)

                        if len(pkg_list) == 2:
                            pkg_id, st, is_inst = pkg_list[1]
                            name = misc.pkg_id_to_full_name(pkg_id)
                            item = yui.YTreeItem(pkg_cat, name, True)
                            item.this.own(False)

                    itemVect.append(cat)

        itemCollection = None
        yui.YUI.app().busyCursor()
        if selected:
            itemCollection = yui.YItemCollection(itemVect)
        self._historyView.startMultipleChanges()
        self._historyView.deleteAllItems()
        if selected:
            self._historyView.addItems(itemCollection)
        self._historyView.doneMultipleChanges()
        yui.YUI.app().normalCursor()

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
                item = yui.YTreeItem(date.strftime("%Y"), True)
                item.this.own(False)
                main[date.year]['item'] = item

            mdict = main[date.year]
            # month
            if date.month not in mdict.keys():
                mdict[date.month] = {}
                item = yui.YTreeItem(main[date.year]['item'], date.strftime("%m"), True)
                item.this.own(False)
                mdict[date.month]['item'] = item

            ddict = mdict[date.month]
            # day
            if date.day not in ddict.keys():
                ddict[date.day] = {}
                item = yui.YTreeItem(mdict[date.month]['item'], date.strftime("%d"), True)
                item.this.own(False)
                ddict[date.day]['item'] = item
            ddict[date.day][date.strftime("%H:%M:%S")] = tid
            item = yui.YTreeItem(ddict[date.day]['item'], date.strftime("%H:%M:%S"), False)
            item.this.own(False)
            self._tid[tid]= item

        itemVect = []
        for year in main.keys():
            itemVect.append(main[year]['item'])

        self._dlg .pollEvent()

        yui.YUI.app().busyCursor()
        itemCollection = yui.YItemCollection(itemVect)
        self._historyTree.startMultipleChanges()
        self._historyTree.deleteAllItems()
        self._historyTree.addItems(itemCollection)
        self._historyTree.doneMultipleChanges()
        yui.YUI.app().normalCursor()

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
                        # get info about gpgkey to be comfirmed
                        values = parent.backend._gpg_confirm
                        if values:  # There is a gpgkey to be verified
                            (pkg_id, userid, hexkeyid, keyurl, timestamp) = values
                            logger.debug('GPGKey : %s' % repr(values))
                            resp = ask_for_gpg_import(values)
                            parent.backend.ConfirmGPGImport(hexkeyid, resp)
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
                warningMsgBox({'title' : _("BuildTransaction failure"), "text": s, "richtext":True})
        except dnfdaemon.client.AccessDeniedError as e:
            logger.error("dnfdaemon client AccessDeniedError: %s ", e)
            warningMsgBox({'title' : _("BuildTransaction failure"), "text": _("dnfdaemon client not authorized:%(NL)s%(error)s")%{'NL': "\n",'error' : str(e)}})
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
        Populate the TreeView with data and rund the dialog
        @param data: list of transaction information date
        @return if undo action has been performed
        '''

        ## push application title
        appTitle = yui.YUI.app().applicationTitle()
        ## set new title to get it in dialog
        yui.YUI.app().setApplicationTitle(_("History") )
        minWidth  = 80;
        minHeight = 25;
        self._dlg     = self.factory.createPopupDialog(yui.YDialogNormalColor)
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

        self._dlg .setDefaultButton(self._closeButton)

        performedUndo = False
        while (True) :
            event = self._dlg.waitForEvent()
            eventType = event.eventType()
            #event type checking
            if (eventType == yui.YEvent.CancelEvent) :
                break
            elif (eventType == yui.YEvent.WidgetEvent) :
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
                        self._closeButton.setDefaultButton()
                        if not show_info:
                            sel = None
                    self._populateHistory(sel)

        self._dlg.destroy()

        #restore old application title
        yui.YUI.app().setApplicationTitle(appTitle)

        return performedUndo


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
                    label =  _("replacing ") + misc.pkg_id_to_full_name(r) + " (" +  misc.format_number(size) + ")"
                    item = yui.YTreeItem(level2Item, label, False)
                    item.this.own(False)

            itemVect.append(level1Item)

        sizeLabel.setText(_("Total size ") +  misc.format_number(total_size))
        dlg.pollEvent()

        yui.YUI.app().busyCursor()
        itemCollection = yui.YItemCollection(itemVect)
        treeWidget.startMultipleChanges()
        treeWidget.deleteAllItems()
        treeWidget.addItems(itemCollection)
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
        self.factory = self.parent.mgaFactory
        # name        => the application name
        # version     =>  the application version
        # license     =>  the application license, the short length one (e.g. GPLv2, GPLv3, LGPLv2+, etc)
        # authors     =>  the string providing the list of authors; it could be html-formatted
        # description =>  the string providing a brief description of the application
        # logo        => the string providing the file path for the application logo (high-res image)
        # icon        => the string providing the file path for the application icon (low-res image)
        # credits     => the application credits, they can be html-formatted
        # information => other extra informations, they can be html-formatted
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
        self.dialog_mode = yui.YMGAAboutDialog.TABBED
        # TODO
        self.logo = parent.images_path + "dnfdragora-logo.png"
        self.icon = parent.icon
        self.credits = ""
        self.information = ""

    def run (self) :
        '''
        shows the about dialog
        '''
        dlg = self.factory.createAboutDialog(
            self.name, self.version, self.license,
            self.authors, self.description, self.logo,
            self.icon, self.credits, self.information)

        dlg.show(self.dialog_mode)

        dlg = None;

class RepoDialog:
    '''
    Create a dialog to manage repository enabling and disabling
    '''

    def __init__(self, parent):
        '''
        Constructor
        @param parent: main parent dialog
        '''
        self.parent = parent
        self.factory = self.parent.factory
        self.mgaFactory = self.parent.mgaFactory
        self.backend = self.parent.backend
        self.itemList = {}
        self.infoKeys = {
          'bandwidth'              : _('Bandwidth'),
          'basecachedir'           : _('Base cache dir'),
          'baseurl'                : _('Base URL'),
          'cost'                   : _('Cost'),
          'deltarpm'               : _('DeltaRPM'),
          'deltarpm_percentage'    : _('DeltaRPM percentage'),
          'enabled'                : _('Enabled'),
          'enabled_metadata'       : _('Enabled metadata'),
          'enablegroups'           : _('Enable groups'),
          'exclude'                : _('Exclude'),
          'excludepkgs'            : _('Exclude packages'),
          'failovermethod'         : _('Failover method'),
          'fastestmirror'          : _('Fastest mirror'),
          'gpgcheck'               : _('GPG check'),
          'gpgkey'                 : _('GPG key'),
          'includepkgs'            : _('Include packages'),
          'ip_resolve'             : _('IP resolve'),
          'max_parallel_download'  : _('Max parallel download'),
          'mediaid'                : _('Media ID'),
          'metadata_expire'        : _('Metadata expire'),
          'metalink'               : _('Meta link'),
          'minrate'                : _('Min rate'),
          'mirrorlist'             : _('Mirror list'),
          'name'                   : _('Name'),
          'packages'               : _('Packages'),
          'password'               : _('Password'),
          'priority'               : _('Priority'),
          'protected_packages'     : _('Protected packages'),
          'proxy'                  : _('Proxy'),
          'proxy_password'         : _('Proxy password'),
          'proxy_username'         : _('Proxy username'),
          'repo_gpgcheck'          : _('Repo GPG check'),
          'retries'                : _('Retries'),
          'size'                   : _('Size'),
          'skip_if_unavailable'    : _('Skip if unavailable'),
          'sslcacert'              : _('SSL CA cert'),
          'sslclientcert'          : _('SSL client cert'),
          'sslclientkey'           : _('SSL client key'),
          'sslverify'              : _('SSL verify'),
          'throttle'               : _('Throttle'),
          'timeout'                : _('Timeout'),
          'type'                   : _('Type'),
          'username'               : _('Username'),
        }

    def _setupUI(self):
        '''
        setup the dialog layout
        '''
        self.appTitle = yui.YUI.app().applicationTitle()
        ## set new title to get it in dialog
        yui.YUI.app().setApplicationTitle(_("Repository Management") )

        self.dialog = self.factory.createPopupDialog()

        minSize = self.factory.createMinSize( self.dialog, 80, 26 )

        vbox = self.factory.createVBox(minSize)

        #Line for logo and title
        hbox_iconbar  = self.factory.createHBox(vbox)
        head_align_left  = self.factory.createLeft(hbox_iconbar)
        hbox_iconbar     = self.factory.createHBox(head_align_left)
        #TODO fix icon with one that recall repository management
        self.factory.createImage(hbox_iconbar, self.parent.icon)

        self.factory.createHeading(hbox_iconbar, _("Repository Management"))

        hbox_middle = self.factory.createHBox(vbox)
        hbox_bottom = self.factory.createHBox(vbox)
        hbox_footbar = self.factory.createHBox(vbox)

        hbox_middle.setWeight(1,50)
        hbox_bottom.setWeight(1,30)
        hbox_footbar.setWeight(1,10)

        repoList_header = yui.YTableHeader()
        columns = [ _('Name'), _("Enabled")]

        for col in (columns):
            repoList_header.addColumn(col)

        self.repoList = self.mgaFactory.createCBTable(hbox_middle,repoList_header,yui.YCBTableCheckBoxOnLastColumn)
        self.repoList.setImmediateMode(True)

        info_header = yui.YTableHeader()
        columns = [_('Information'), _('Value') ]
        for col in (columns):
            info_header.addColumn(col)
        self.info = self.factory.createTable(hbox_bottom, info_header)

        #self.info = self.factory.createRichText(hbox_bottom,"")
        #self.info.setWeight(0,40)
        #self.info.setWeight(1,40)

        self.applyButton = self.factory.createIconButton(hbox_footbar,"",_("&Apply"))
        self.applyButton.setWeight(0,3)

        self.quitButton = self.factory.createIconButton(hbox_footbar,"",_("&Cancel"))
        self.quitButton.setWeight(0,3)
        self.dialog.setDefaultButton(self.quitButton)

        self.itemList = {}
        # TODO fix the workaround when GetRepo(id) works again
        repos = self.backend.get_repo_ids("*")
        for r in repos:
            item = yui.YCBTableItem(r)
            # TODO name from repo info
            self.itemList[r] = {
                'item' : item, 'name': r, 'enabled' : False
            }
            item.this.own(False)
        enabled_repos = self.backend.get_repo_ids("enabled")
        for r in enabled_repos:
            if r in self.itemList.keys():
                self.itemList[r]["enabled"] = True
                self.itemList[r]["item"].check(True)

        keylist = sorted(self.itemList.keys())
        v = []
        for key in keylist :
            item = self.itemList[key]['item']
            v.append(item)

        #NOTE workaround to get YItemCollection working in python
        itemCollection = yui.YItemCollection(v)

        self.repoList.startMultipleChanges()
        # cleanup old changed items since we are removing all of them
        self.repoList.deleteAllItems()
        self.repoList.addItems(itemCollection)
        self.repoList.doneMultipleChanges()

    def _selectedRepository(self) :
        '''
        gets the selected repository id from repo list, if any selected
        '''
        selected_repo = None
        sel = self.repoList.selectedItem()
        if sel :
            for repo_id in self.itemList:
                if (self.itemList[repo_id]['item'] == sel) :
                    selected_repo = repo_id
                    break

        return selected_repo

    def _handleEvents(self):
        '''
        manages dialog events and returns if sack should be filled again for new enabled/disabled repositories
        '''
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
                elif (widget == self.applyButton) :
                    enabled_repos = []
                    for k in self.itemList.keys():
                        if self.itemList[k]['enabled'] :
                           enabled_repos.append(k)
                    logger.info("Enabling repos %s "%" ".join(enabled_repos))
                    self.backend.SetEnabledRepos(enabled_repos)
                    return True
                elif (widget == self.repoList) :
                    wEvent = yui.toYWidgetEvent(event)
                    if (wEvent.reason() == yui.YEvent.ValueChanged) :
                        changedItem = self.repoList.changedItem()
                        if changedItem :
                            for it in self.itemList:
                                if (self.itemList[it]['item'] == changedItem) :
                                    self.itemList[it]['enabled'] = changedItem.checked()
                    repo_id = self._selectedRepository()
                    s = "TODO show repo %s information<br> See https://github.com/timlau/dnf-daemon/issues/11"%(repo_id if repo_id else "---")
                    # TODO decide what and how to show when the crash https://github.com/timlau/dnf-daemon/issues/11 is fixed
                    v=[]
                    try:
                        ri = self.backend.GetRepo(repo_id)
                        logger.debug(ri)
                        for k in sorted(ri.keys()):
                          if k == "enabled":
                            # NOTE: skipping 'enabled' since it is fake and it is better shown as checkbox
                            continue
                          key = None
                          if ri[k]:
                            key = self.infoKeys[k] if k in self.infoKeys.keys() else k
                            if k == 'size':
                              value = misc.format_number(ri[k])
                            elif k == 'metadata_expire':
                              if ri[k] <= -1:
                                value = _('Never')
                              else:
                                value = _("%s second(s)"%(ri[k]))
                            else:
                              value = "%s"%(ri[k])
                          else:
                            if k == 'metadata_expire':
                              key = self.infoKeys[k]
                              value = _('Now')
                          if key:
                            item = yui.YTableItem(key, value)
                            item.this.own(False)
                            v.append(item)

                    except NameError as e:
                        logger.error("dnfdaemon NameError: %s ", e)
                    except AttributeError as e:
                        logger.error("dnfdaemon AttributeError: %s ", e)
                    except:
                        logger.error("Unexpected error: %s ", sys.exc_info()[0])

                    #NOTE workaround to get YItemCollection working in python
                    itemCollection = yui.YItemCollection(v)

                    self.info.startMultipleChanges()
                    # cleanup old changed items since we are removing all of them
                    self.info.deleteAllItems()
                    self.info.addItems(itemCollection)
                    self.info.doneMultipleChanges()

        return False

    def run(self):
        '''
        show and run the dialog
        '''
        self._setupUI()
        refresh_data=self._handleEvents()

        #restore old application title
        yui.YUI.app().setApplicationTitle(self.appTitle)

        self.dialog.destroy()
        self.dialog = None
        return refresh_data

class UserPrefsDialog:
    '''
    Create a dialog to manage user preferences
    '''

    def __init__(self, parent):
        '''
        Constructor
        @param parent: main parent dialog
        '''
        self.parent = parent
        self.factory = self.parent.factory
        self.mgaFactory = self.parent.mgaFactory

    def _setupUI(self):
        '''
        setup the dialog layout
        '''
        self.appTitle = yui.YUI.app().applicationTitle()
        ## set new title to get it in dialog
        yui.YUI.app().setApplicationTitle(_("User preferences") )

        self.dialog = self.factory.createPopupDialog()

        minSize = self.factory.createMinSize( self.dialog, 80, 10 )

        vbox = self.factory.createVBox(minSize)

        hbox_middle = self.factory.createHBox(vbox)
        hbox_bottom = self.factory.createHBox(vbox)
        hbox_footbar = self.factory.createHBox(vbox)

        hbox_middle.setWeight(1,50)
        hbox_bottom.setWeight(1,30)
        hbox_footbar.setWeight(1,10)

        settings = {}
        updateInterval = 180
        if self.parent.config.systemSettings :
            if 'settings' in self.parent.config.systemSettings.keys() :
                settings = self.parent.config.systemSettings['settings']
                if 'update_interval' in settings.keys() :
                    updateInterval = int(settings['update_interval'])

        settings = {}
        if self.parent.config.userPreferences:
            if 'settings' in self.parent.config.userPreferences.keys() :
                settings = self.parent.config.userPreferences['settings']
        showUpdates = False
        showAll = False
        always_yes = self.parent.always_yes
        log_enabled = False
        level_debug = False
        log_directory = None

        if 'show updates at startup' in settings.keys() :
            showUpdates = settings['show updates at startup']
        if 'do not show groups at startup' in settings.keys() :
            showAll = settings['do not show groups at startup']
        if 'interval for checking updates' in settings.keys() :
            updateInterval = int(settings['interval for checking updates'])
        if 'always_yes' in settings.keys() :
            always_yes = settings['always_yes']
        if 'log_enabled' in settings.keys() :
          log_enabled = settings['log_enabled']
        if 'log' in settings.keys():
          log = settings['log']
          if 'directory' in log.keys() :
            log_directory = log['directory']
          if 'level_debug' in log.keys() :
            level_debug = log['level_debug']

        #Already read from system and user settings
        match_all = self.parent.match_all
        newest_only = self.parent.newest_only

        vbox1 = self.factory.createVBox(hbox_middle)

        #System settings
        frame = self.factory.createFrame( vbox1, _("System options") )
        hbox = self.factory.createHBox(frame)
        self.always_yes  =  self.factory.createCheckBox(hbox , _("Proceed without asking for confirmation"), always_yes )
        self.updateInterval = self.factory.createIntField(hbox, _("Interval in minutes to check for updates:"), 30, 720, updateInterval )

        #Layout (view) settings
        frame = self.factory.createFrame( self.factory.createLeft(vbox1), _("Layout options") )
        box = self.factory.createVBox(frame)
        self.showUpdates =  self.factory.createCheckBox(self.factory.createLeft(box) , _("Show updates next startup"), showUpdates )
        self.showAll  =  self.factory.createCheckBox(self.factory.createLeft(box) , _("Do not show groups view next startup"), showAll )

        #Search settings
        frame = self.factory.createFrame( self.factory.createLeft(vbox1), _("Search options") )
        box = self.factory.createVBox(frame)
        self.newest_only = self.factory.createCheckBox(self.factory.createLeft(box) , _("Show newest packages only"), newest_only )
        self.match_all   = self.factory.createCheckBox(self.factory.createLeft(box) , _("Match all words"), match_all )

        #Log settings
        self.log = self.factory.createCheckBoxFrame( self.factory.createLeft(vbox1), _("Log options on next startup"), log_enabled)
        box = self.factory.createVBox(self.log)
        hbox = self.factory.createHBox(box)
        self.log_directory = self.factory.createLabel(hbox, "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
        self.log_directory.setText((log_directory if log_directory is not None else os.path.expanduser("~")))
        self.choose_dir = self.factory.createIconButton(self.factory.createLeft(hbox), "", _("Change &directory"))
        self.level_debug = self.factory.createCheckBox(self.factory.createLeft(box) , _("Enable debug log level"), level_debug )
        self.log.setEnabled(log_enabled)

        self.applyButton = self.factory.createIconButton(hbox_footbar,"",_("&Apply"))
        self.applyButton.setWeight(0,3)

        self.quitButton = self.factory.createIconButton(hbox_footbar,"",_("&Cancel"))
        self.quitButton.setWeight(0,3)
        self.dialog.setDefaultButton(self.quitButton)


    def _handleEvents(self):
        '''
        manage dialog events
        '''
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
                    #### QUIT
                    break
                elif (widget == self.choose_dir) :
                  start_dir = self.log_directory.text() if self.log_directory.text() else os.path.expanduser("~")
                  log_directory = yui.YUI.app().askForExistingDirectory(
                    start_dir,
                    _("Choose log destination directory"))
                  if log_directory:
                    self.log_directory.setText(log_directory)
                    self.dialog.recalcLayout()
                elif (widget == self.applyButton) :
                    search = {
                      'match_all': self.match_all.isChecked(),
                      'newest_only': self.newest_only.isChecked()
                      }
                    log_entry = {
                      'directory': self.log_directory.text(),
                      'level_debug': self.level_debug.isChecked()
                      }
                    self.parent.config.userPreferences['settings'] = {
                        'show updates at startup' : self.showUpdates.isChecked(),
                        'do not show groups at startup' : self.showAll.isChecked(),
                        'interval for checking updates' : self.updateInterval.value(),
                        'always_yes' : self.always_yes.isChecked(),
                        'log_enabled' : self.log.value(),
                        'log' : log_entry,
                        'search' : search
                        }
                    self.parent.always_yes = self.always_yes.isChecked()
                    self.parent.match_all = search['match_all']
                    self.parent.newest_only = search['newest_only']
                    break

    def run(self):
        '''
        show and run the dialog
        '''
        self._setupUI()
        self._handleEvents()

        #restore old application title
        yui.YUI.app().setApplicationTitle(self.appTitle)

        self.dialog.destroy()
        self.dialog = None


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

    retVal = 0
    yui.YUI.widgetFactory
    factory = yui.YExternalWidgets.externalWidgetFactory("mga")
    factory = yui.YMGAWidgetFactory.getYMGAWidgetFactory(factory)
    dlg = factory.createDialogBox(yui.YMGAMessageBox.B_ONE, yui.YMGAMessageBox.D_WARNING)

    if ('title' in info.keys()) :
        dlg.setTitle(info['title'])

    rt = False
    if ("richtext" in info.keys()) :
        rt = info['richtext']

    if ('text' in info.keys()) :
        dlg.setText(info['text'], rt)

    dlg.setButtonLabel(_("&Ok"), yui.YMGAMessageBox.B_ONE )
#   dlg.setMinSize(50, 5)

    retVal = dlg.show()
    dlg = None

    return 1


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

    retVal = 0
    yui.YUI.widgetFactory
    factory = yui.YExternalWidgets.externalWidgetFactory("mga")
    factory = yui.YMGAWidgetFactory.getYMGAWidgetFactory(factory)
    dlg = factory.createDialogBox(yui.YMGAMessageBox.B_ONE, yui.YMGAMessageBox.D_INFO)

    if ('title' in info.keys()) :
        dlg.setTitle(info['title'])

    rt = False
    if ("richtext" in info.keys()) :
        rt = info['richtext']

    if ('text' in info.keys()) :
        dlg.setText(info['text'], rt)

    dlg.setButtonLabel(_("&Ok"), yui.YMGAMessageBox.B_ONE )
#   dlg.setMinSize(50, 5)

    retVal = dlg.show()
    dlg = None

    return 1

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

    retVal = 0
    yui.YUI.widgetFactory
    factory = yui.YExternalWidgets.externalWidgetFactory("mga")
    factory = yui.YMGAWidgetFactory.getYMGAWidgetFactory(factory)
    dlg = factory.createDialogBox(yui.YMGAMessageBox.B_ONE)

    if ('title' in info.keys()) :
        dlg.setTitle(info['title'])

    rt = False
    if ("richtext" in info.keys()) :
        rt = info['richtext']

    if ('text' in info.keys()) :
        dlg.setText(info['text'], rt)

    dlg.setButtonLabel(_("&Ok"), yui.YMGAMessageBox.B_ONE )
#   dlg.setMinSize(50, 5)

    retVal = dlg.show()
    dlg = None

    return 1


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

    retVal = False
    yui.YUI.widgetFactory
    factory = yui.YExternalWidgets.externalWidgetFactory("mga")
    factory = yui.YMGAWidgetFactory.getYMGAWidgetFactory(factory)
    dlg = factory.createDialogBox(yui.YMGAMessageBox.B_TWO)

    if ('title' in info.keys()) :
        dlg.setTitle(info['title'])

    rt = False
    if ("richtext" in info.keys()) :
        rt = info['richtext']

    if ('text' in info.keys()) :
        dlg.setText(info['text'], rt)

    dlg.setButtonLabel(_("&Ok"), yui.YMGAMessageBox.B_ONE )
    dlg.setButtonLabel(_("&Cancel"), yui.YMGAMessageBox.B_TWO )

    if ("default_button" in info.keys() and info["default_button"] == 1) :
        dlg.setDefaultButton(yui.YMGAMessageBox.B_ONE)
    else :
        dlg.setDefaultButton(yui.YMGAMessageBox.B_TWO)

    dlg.setMinSize(50, 5)

    retVal = dlg.show() == yui.YMGAMessageBox.B_ONE;
    dlg = None

    return retVal

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

    retVal = False
    yui.YUI.widgetFactory
    factory = yui.YExternalWidgets.externalWidgetFactory("mga")
    factory = yui.YMGAWidgetFactory.getYMGAWidgetFactory(factory)
    dlg = factory.createDialogBox(yui.YMGAMessageBox.B_TWO)

    if ('title' in info.keys()) :
        dlg.setTitle(info['title'])

    rt = False
    if ("richtext" in info.keys()) :
        rt = info['richtext']

    if ('text' in info.keys()) :
        dlg.setText(info['text'], rt)

    dlg.setButtonLabel(_("&Yes"), yui.YMGAMessageBox.B_ONE )
    dlg.setButtonLabel(_("&No"), yui.YMGAMessageBox.B_TWO )
    if ("default_button" in info.keys() and info["default_button"] == 1) :
        dlg.setDefaultButton(yui.YMGAMessageBox.B_ONE)
    else :
        dlg.setDefaultButton(yui.YMGAMessageBox.B_TWO)
    if ('size' in info.keys()) :
        dlg.setMinSize(info['size'][0], info['size'][1])

    retVal = dlg.show() == yui.YMGAMessageBox.B_ONE;
    dlg = None

    return retVal


def ask_for_gpg_import (values):
    '''
    This function asks if user wants to import or not the gpg keys.
    @output:
        False: No button has been pressed
        True:  Yes button has been pressed
    '''
    (pkg_id, userid, hexkeyid, keyurl, timestamp) = values
    pkg_name = pkg_id.split(',')[0]
    msg = (_('Do you want to import this GPG key <br>needed to verify the %(pkg)s package?<br>'
             '<br>Key        : 0x%(id)s:<br>'
             'Userid     : "%(user)s"<br>'
             'From       : %(file)s') %
           {'pkg': pkg_name, 'id': hexkeyid, 'user': userid,
            'file': keyurl.replace("file://", "")})

    return askYesOrNo({'title' : _("GPG key missed"),
                       'text': msg,
                       'default_button' : 1,
                       'richtext' : True,
                       'size' : [60, 10]})
