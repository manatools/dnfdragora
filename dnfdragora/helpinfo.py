# vim: set fileencoding=utf-8 :
# vim: set et ts=4 sw=4:

'''
HelpInfo contains text for help menu

License: LGPLv2+

Author:  Angelo Naselli <anaselli@linux.it>

@package dnfdragora
'''

import manatools.basehelpinfo as helpdata
import gettext

class DNFDragoraHelpInfo(helpdata.HelpInfoBase):
  '''
  DNFDragoraHelpInfo class implements HelpInfoBase show() and home()
  '''
  def __init__(self):
    '''
    HelpInfo constructor
    '''
    helpdata.HelpInfoBase.__init__(self)
    home_lnk = '<b>%s</b>'%self._formatLink(_("Go to index"), 'home')

    ### Main index
    menu_line_lnk     = '<b>%s</b>'%self._formatLink(_("Menu line"), 'menus')
    filters_lnk       = '<b>%s</b>'%self._formatLink(_("Filters and search line"), 'filters')
    group_panel_lnk   = '<b>%s</b>'%self._formatLink(_("Group panel"), 'group_panel')
    package_panel_lnk = '<b>%s</b>'%self._formatLink(_("Package panel"), 'package_panel')
    info_panel_lnk    = '<b>%s</b>'%self._formatLink(_("Information panel"), 'info_panel')
    pbar_line_lnk     = '<b>%s</b>'%self._formatLink(_("Progress bar line"), 'pbar_panel')
    buttons_line_lnk  = '<b>%s</b>'%self._formatLink(_("Button line"), 'button_panel')

    index = '<ul><li>%s</li><li>%s</li><li>%s</li><li>%s</li><li>%s</li><li>%s</li><li>%s</li></ul>'%(
      menu_line_lnk,
      filters_lnk,
      group_panel_lnk,
      package_panel_lnk,
      info_panel_lnk,
      pbar_line_lnk,
      buttons_line_lnk,
      )

    ### Menu bar index
    file_menu_lnk   = '<b>%s</b>'%self._formatLink(_("File menu"), 'file_menu')
    info_menu_lnk   = '<b>%s</b>'%self._formatLink(_("Information menu"), 'info_menu')
    option_menu_lnk = '<b>%s</b>'%self._formatLink(_("Options menu"), 'option_menu')
    Help_menu_lnk   = '<b>%s</b>'%self._formatLink(_("Help menu"), 'help_menu')

    menu_index = '<ul><li>%s</li><li>%s</li><li>%s</li><li>%s</li></ul>'%(
       file_menu_lnk,
       info_menu_lnk,
       option_menu_lnk,
       Help_menu_lnk,
    )


    self.text = {
      'home': '<h1>DNFDragora</h1>%s<br>%s'%(
        _("dnfdragora is a DNF frontend, based on Mageia rpmdragora layout and Fedora yumex-dnf interaction with dnfdaemon.<br><br>") + \
        _("dnfdragora is basically a package manager user interface that allows to install, update, remove, search packages and more.<br><br>") + \
        _("dnfdragora is part of manatools and it is based on libyui so that it can work using Gtk, Qt or ncurses, i.e. both graphical and textual user interfaces.<br><br>") +\
        _("dnfdragora window is comprised of:"),
        index
      ),
      'menus' : '<h1>%s</h1>%s<br>%s<br>%s'%(
        # title
        _("Menu bar content"),
        # help content
        _("Menu bar contains dnfdragora drop down menus:"),
        menu_index,
        # back home
        home_lnk
      ),

      'file_menu': '<h1>%s</h1>%s<br>%s'%(
        # title
        _('File Menu'),
        # help
        _('<h2>Reset selection</h2>') +\
          _('This menu removes any flags on packages, if any packages have been selected for installation or removal they will be back to previous status.<br>') +\
        _('<h2>Refresh metadata</h2>') +\
          _('This menu send a request to dnfdaemon to force a refresh of all the meta data. This action is asynchronous and requires to rebuild package information cache.<br>') +\
        _('<h2>Repositories</h2>') +\
          _('This menu opens a dialog that allows to enable or disable repositories. Any changes are valid for the time dnfdragora is running and it is not permanent.<br>')+\
        _('<h2>Quit</h2>') +\
          _('This menu exits from dnfdragora.<br>'),
        # back home
        home_lnk,
      ),

      'info_menu': '<h1>%s</h1>%s<br>%s'%(
        # title
        _('Information Menu'),
        # help
        _('<h2>History</h2>') +\
          _('This menu runs a dialog containing transaction history shown in a tree ordered by date. Selected history can be undone by pressing <b>Undo</b> button.<br>') + \
          _('<br><i>Note that this function is currently broken because of dnf API change</i><br>'),
        # back home
        home_lnk,
      ),

      'option_menu': '<h1>%s</h1>%s<br>%s'%(
        # title
        _('Option Menu'),
        # help
        _('<h2>User preferences</h2>') +\
        _('This menu opens a %s containing user settings to customize dnfdragora behavior.<br>'%(self._formatLink(_("dialog"), 'user_prefs_dlg'))),
        # back home
        home_lnk,
      ),
      'user_prefs_dlg' : '<h1>%s</h1>%s<br>%s'%(
        # title
        _('User preferences'),
        # help
        _('This dialog allows to customize dnfdragora behavior by changing options. Some changes are available after closing the dialog, others need a dnfdragora restart.<br><br>') + \
        _('<b>NOTE: Apply</b> button must be pressed to make changes permanent and available, any other way to close the dialog is the same as pressing <i>Cancel</i> button.') + \
        _('<h2>System options</h2>') + \
          _('<ul><li><b>Proceed without asking for confirmation</b>: if checked transactions do not need to be confirmed, dnfdragora works as answering <i>yes</i></li>') + \
          _('<li><b>Interval to check for updates</b>: the given number represents when dnfdragora needs to check for updates, value is expressed in minutes</li>') + \
          _('<li><b>Metadata expire time</b>: time to force Metadata expiration, the value is expressed in hours</li></ul>') + \
        _('<h2>Layout options</h2>') + \
          _('<ul><li><b>Show updates</b>: if checked dnfdragora starts with <i>updates</i> filter active, i.e. showing only package available for updates if any.</li>') + \
          _('<li><b>Do not show groups view</b>: filtering by groups could require CPU if using comps, if this option is checked dnfdragora starts showing all packages.</li></ul>') + \
          _('<b>NOTE</b> that the above options require dnfdragora to be restarted.') + \
        _('<h2>Search options</h2>') + \
          _('<ul><li><b>Show newest packages only</b>: if checked dnfdragora shows only newest packages on search. <i>Note that is valid if searches are not performed by using regular expressions</i></li>') + \
          _('<li><b>Match all words</b>: if checked a search without using regular expressions will match all the given words into the text field.</li></ul>') + \
        _('<h2>Logging options</h2>') + \
          _('Enable these options to let dnfdragora log on file called <i>dnfdragora.log</i>.') + \
          _('<ul><li><b>Change directory</b>: this option allows to set logging directory, directory must exist and needs write permission.</li>') + \
          _('<li><b>Debug level</b>: if checked log verbose logging is enabled.</li></ul>') + \
          '<br>',
        # back home
        home_lnk,
      ),

      'help_menu':  '<h1>%s</h1>%s<br>%s'%(
        # title
        _('Help Menu'),
        # help
        _('<h2>Manual</h2>') +\
        _('This menu opens dnfdragora help dialog.') + \
        _('<h2>About</h2>') +\
        _('This menu opens dnfdragora about dialog.') + \
        '<br>',
        # back home
        home_lnk,
      ),

      'filters':   '<h1>%s</h1>%s<br>%s'%(
        # title
        _('Views and search'),
        # help
        _('<h2>Views</h2>') +\
          _('First combobox allows to show packages by groups. If <i>Groups</i> is selected group panel shows a tree view containing groups, while selecting a group shows related packages into package panel.') + \
          _('If <i>All</i> is selected, package panel contains all the packages.') + \
        _('<h2>Filters</h2>') +\
          _('Filter combobox allows to filter packages shown into package panel by:') + \
            _('<ul><li><b>Installed</b>: shows installed packages only.</li>') + \
            _('<li><b>Not installed</b>: shows available packages only.</li>') + \
            _('<li><b>To update</b>: shows packages that are available for updates only.</li>') + \
            _('<li><b>Show x86_64 and noarch only</b>: if dnfdragora is running on x86_64 architecture, it hides i686 packages.</li>') + \
            _('<li><b>All</b>: shows all the packages, i.e. available, updates and installed.</li></ul>') + \
        _('<h2>Search</h2>') +\
          _('Search is performed by pressing <i>Search</i> button if text field is filled. Search combobox allows to search given text into package <i>names</i>, <i>summaries</i>, <i>descriptions</i> or <i>files</i>.') + \
          _('A special checkbox <i>Use regexp</i> is used to look for packages by python language regular expressions. This search is performed on cached package information such as for the <b>only names and summaries</b>.') + \
          _('<i>Note</i> that if regular expressions are used to search by names full package filename with version is used.') + \
          _('The <i>Clear search</i> button resets search text field.') + \
        '<br>',
        # back home
        home_lnk,
      ),

      'group_panel': '<h1>%s</h1>%s<br>%s'%(
        # title
        _('Group panel'),
        # help
        _('This panel shows all the groups to be used to filter packages by group, if view groups is selected. Special group <i>Search</i> is added if a search is performed.') + \
        '<br>',
        # back home
        home_lnk,
      ),

      'package_panel': '<h1>%s</h1>%s<br>%s'%(
        # title
        _('Package panel'),
        # help
        _('This panel shows all the filtered packages with they basic information such as <i>name</i>, <i>summary</i>, <i>version</i>, <i>release</i>, <i>architecture</i>, <i>size</i>, and <i>status</i>.') + \
        _('A checkbox for any packages is available to add related package to transaction for installing, updating or removing.') + \
        '<br>',
        # back home
        home_lnk,
      ),

      'info_panel': '<h1>%s</h1>%s<br>%s'%(
        # title
        _('Information panel'),
        # help
        _('This panel shows all the package information such as <i>description</i>, <i>URL</i>, <i>repository</i>, <i>requirements</i>, <i>file list</i>, and <i>changelog</i>.') + \
        _('<br><br><i>Note that changelog is not provided by dnfdaemon at the moment.</i>') + \
        '<br>',
        # back home
        home_lnk,
      ),

      'pbar_panel': '<h1>%s</h1>%s<br>%s'%(
        # title
        _('Progress bar'),
        # help
        _('Progress bar shows dnfdragora operations progression such as transactions and caching data.') + \
        '<br>',
        # back home
        home_lnk,
      ),

      'button_panel': '<h1>%s</h1>%s<br>%s'%(
        # title
        _('Buttons line'),
        # help
        _('<ul><li><b>Apply</b>: when some packages are selected for installing or updating or deselected for uninstalling this button runs the transaction to be performed.</li>') + \
        _('<li><b>Select all</b>: if packages are filtered for updates only this button allows to select all the packages in one shot.</li>') + \
        _('<li><b>Quit</b>: exits from dnfdragora.</li></ul>') + \
        '<br>',
        # back home
        home_lnk,
      ),

    }

  def _formatLink(self, description, url) :
    '''
    @param description: Description to be shown as link
    @param url: to be reach when click on $description link
    returns href string to be published
    '''
    webref = '<a href="%s">%s</a>'%(url, description)
    return webref

  def show(self, index):
    '''
    implement show
    '''
    if index in self.text.keys():
      return self.text[index]

    return ""

  def home(self):
    '''
    implement home
    '''
    return self.text['home']


if __name__ == '__main__':

  info = HelpInfo()
  td = helpdialog.HelpDialog(info)
  td.run()
  
  
