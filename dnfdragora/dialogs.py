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
        minWidth  = 80;
        minHeight = 25;
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
        minWidth  = 60;
        minHeight = 10;
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
        minWidth  = 80;
        minHeight = 25;
        dlg     = self.factory.createPopupDialog()
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
        self.backend = self.parent.backend
        self.itemList = {}
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
          'proxy_password'      : _('Proxy password'),
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

    def _setupUI(self):
        '''
        setup the dialog layout
        '''
        self.appTitle = MUI.YUI.app().applicationTitle()

        self.dialog = self.factory.createPopupDialog()
        ## set new title to get it in dialog
        MUI.YUI.app().setApplicationTitle(_("Repository Management") )

        vbox = self.factory.createVBox(self.dialog)
        minSize = self.factory.createMinSize( vbox, 320, 100 )
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

        hbox_middle.setWeight(MUI.YUIDimension.YD_VERT,50)
        hbox_bottom.setWeight(MUI.YUIDimension.YD_VERT,30)
        hbox_footbar.setWeight(MUI.YUIDimension.YD_VERT,10)

        checkboxed = True
        repoList_header = MUI.YTableHeader()
        repoList_header.addColumn("", checkboxed, alignment=MUI.YAlignmentType.YAlignCenter)
        repoList_header.addColumn(_('Name'))
        repoList_header.addColumn(_('Id'))


        self.repoList = self.factory.createTable(hbox_middle, repoList_header)

        info_header = MUI.YTableHeader()
        columns = [_('Information'), _('Value') ]
        for col in (columns):
            info_header.addColumn(col)
        self.info = self.factory.createTable(hbox_bottom, info_header)

        #self.info = self.factory.createRichText(hbox_bottom,"")
        #self.info.setWeight(0,40)
        #self.info.setWeight(1,40)

        self.applyButton = self.factory.createPushButton(hbox_footbar, _("&Apply"))
        self.applyButton.setWeight(MUI.YUIDimension.YD_HORIZ,3)

        self.quitButton = self.factory.createPushButton(hbox_footbar, _("&Cancel"))
        self.quitButton.setWeight(MUI.YUIDimension.YD_HORIZ,3)
        #self.dialog.setDefaultButton(self.quitButton)

        self.itemList = {}
        repos = self.backend.GetRepositories(repo_attrs=['id'], enable_disable='enabled', sync=True)
        self.enabledRepos = [ repo['id'] for repo in repos if not repo['id'].endswith('-source') and not repo['id'].endswith('-debuginfo') ]
        repos = self.backend.GetRepositories(repo_attrs=['id'], enable_disable='disabled', sync=True)
        self.disabledRepos = [ repo['id'] for repo in repos if not repo['id'].endswith('-source') and not repo['id'].endswith('-debuginfo') ]

        repos = self.backend.get_repositories()

        for r in repos:
            item = MUI.YTableItem()
            item.addCell(bool(r['enabled']))
            item.addCell(str(r['name']))
            item.addCell(str(r['id']))

            self.itemList[r['id']] = {
                'item' : item, 'name': r['name'], 'id': r['id'], 'enabled' : r['enabled']
            }

        keylist = sorted(self.itemList.keys())
        v = []
        for key in keylist :
            item = self.itemList[key]['item']
            v.append(item)

        itemCollection = v

        # cleanup old changed items since we are removing all of them
        self.repoList.deleteAllItems()
        self.repoList.addItems(itemCollection)
        repo_id = self._selectedRepository()
        self._addAttributeInfo(repo_id)


    def _addAttributeInfo(self, repo_id):
      '''
        fill attribute information of the given repo_id
      '''
      if not repo_id:
        return
      v=[]
      try:
          repo_attrs= [ repo_attr for repo_attr in self.infoKeys.keys() if repo_attr != "proxy_password" ] # TODO add it backs when it works

          ri = self.backend.GetRepositories(patterns=[repo_id], repo_attrs=repo_attrs, sync=True)
          logger.debug(ri)
          if len(ri) > 1:
            logger.warn("Got %d elements expected 1", len(ri))
          ri = ri[0] # first element
          for k in sorted(ri.keys()):
            if k == "enabled" or k=="name" or k=="id":
              # skipping data that are already shown into the listbox
              continue
            key = None
            value = ""
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
              item = MUI.YTableItem(key, value)
              v.append(item)

      except NameError as e:
          logger.error("dnfdaemon NameError: %s ", e)
      except AttributeError as e:
          logger.error("dnfdaemon AttributeError: %s ", e)
      except GLib.Error as err:
          logger.error("dnfdaemon client failure [%s]", err)
      except:
          logger.error("Unexpected error: %s ", sys.exc_info()[0])

      itemCollection = v

      # cleanup old changed items since we are removing all of them
      self.info.deleteAllItems()
      self.info.addItems(itemCollection)

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
            if (eventType == MUI.YEventType.CancelEvent) :
                break
            elif (eventType == MUI.YEventType.WidgetEvent) :
                # widget selected
                widget  = event.widget()
                if (widget == self.quitButton) :
                    #### QUIT
                    break
                elif (widget == self.applyButton) :

                    enabled_repos = [k for k in self.itemList.keys() if self.itemList[k]['enabled'] and k in self.disabledRepos]
                    disabled_repos = [k for k in self.itemList.keys() if not self.itemList[k]['enabled'] and k in self.enabledRepos]

                    logger.info("Enabling repos %s "%" ".join(enabled_repos))
                    # NOTE we can manage one async call at the time atm, TODO fix in the future,
                    # these call are quick though, but main window must know that repos are changed,
                    # so let's at least one be async
                    if enabled_repos:
                      self.backend.SetEnabledRepos(enabled_repos)
                    if disabled_repos:
                      self.backend.SetDisabledRepos(disabled_repos, sync=(enabled_repos and disabled_repos))
                    return True
                elif (widget == self.repoList) :
                  if (event.reason() == MUI.YEventReason.ValueChanged) :
                    changedItem = self.repoList.changedItem()
                    if changedItem :
                      # first column is the checkbox
                      new_state = False
                      try:
                        new_state = bool(changedItem.cell(0).checked())
                      except Exception:
                        pass
                      for it in self.itemList:
                        if (self.itemList[it]['item'] == changedItem) :
                          self.itemList[it]['enabled'] = new_state
                          break

                    repo_id = self._selectedRepository()
                    MUI.YUI.app().busyCursor()
                    self._addAttributeInfo(repo_id)
                    MUI.YUI.app().normalCursor()

        return False

    def run(self):
        '''
        show and run the dialog
        '''
        self._setupUI()
        refresh_data=self._handleEvents()

        #restore old application title
        MUI.YUI.app().setApplicationTitle(self.appTitle)

        self.dialog.destroy()
        self.dialog = None
        return refresh_data

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
      "search" : None,
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

    item = MUI.YTreeItem(_("Search"))
    itemVect.append(item)
    self.option_items ["search"] = item

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
            elif k == "search":
              self._openSearchOptions()
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
    '''
    show search configuration options
    '''
    if self.config_tab.hasChildren():
      self.config_tab.deleteChildren()

    hbox = self.factory.createHBox(self.config_tab)
    self.factory.createHSpacing(hbox)
    vbox = self.factory.createVBox(hbox)
    self.factory.createHSpacing(hbox)

    # Title
    heading=self.factory.createHeading( vbox, _("Search options") )
    self.factory.createVSpacing(vbox, 0.3*self._VSPACING_PX)
    heading.setAutoWrap()

    fuzzy_search = self.parent.fuzzy_search
    newest_only = self.parent.newest_only

    self.newest_only = self.factory.createCheckBox(self.factory.createLeft(vbox) , _("Show newest packages only"), newest_only )
    self.newest_only.setNotify(True)
    self.eventManager.addWidgetEvent(self.newest_only, self.onNewestOnly, True)
    self.widget_callbacks.append( { 'widget': self.newest_only, 'handler': self.onNewestOnly} )

    self.fuzzy_search   = self.factory.createCheckBox(self.factory.createLeft(vbox) , _("Fuzzy search (legacy mode)"), fuzzy_search )
    self.fuzzy_search.setNotify(True)
    self.eventManager.addWidgetEvent(self.fuzzy_search, self.onFuzzySearch, True)
    self.widget_callbacks.append( { 'widget': self.fuzzy_search, 'handler': self.onFuzzySearch} )

    self.factory.createVStretch(vbox)
    self.config_tab.showChild()

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
    '''
    Fuzzy Search Changing
    '''
    if obj.widgetClass() == "YCheckBox":
      self._ensure_settings().setdefault('search', {})['fuzzy_search'] = obj.isChecked()
      self.parent.fuzzy_search = obj.isChecked()
    else:
      logger.error("OptionDialog: Invalid object passed %s", obj.widgetClass())

  def onNewestOnly(self, obj):
    '''
    Newest Only Changing
    '''
    if obj.widgetClass() == "YCheckBox":
      self._ensure_settings().setdefault('search', {})['newest_only'] = obj.isChecked()
      self.parent.newest_only = obj.isChecked()
    else:
      logger.error("OptionDialog: Invalid object passed %s", obj.widgetClass())

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
    elif k == "search":
      self._ensure_settings()['search'] = {
        'fuzzy_search': False,
        'newest_only': False,
      }
      self.parent.fuzzy_search = False
      self.parent.newest_only = False
      self._openSearchOptions()
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
    msg = (_('Do you want to import this GPG key?<br>'
             '<br>Key        : 0x%(id)s:<br>'
             'Userid     : "%(user)s"<br>'
             'Fingerprint: "%(fingerprint)s"<br>'
             'Timestamp  : "%(timestamp)s"<br>'
             'From       : %(file)s') %
           {'id': key_id,
            'user': user_ids,
            'fingerprint':key_fingerprint,
            'timestamp':timestamp,
            'file': key_url.replace("file://", "")})

    return askYesOrNo({'title' : _("GPG key missed"),
                       'text': msg,
                       'default_button' : 1,
                       'richtext' : True,
                       'size' : [60, 10]})
