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
    filters_lnk       = '<b>%s</b>'%self._formatLink(_("Views, filters and search"), 'filters')
    group_panel_lnk   = '<b>%s</b>'%self._formatLink(_("Group panel"), 'group_panel')
    package_panel_lnk = '<b>%s</b>'%self._formatLink(_("Package panel"), 'package_panel')
    info_panel_lnk    = '<b>%s</b>'%self._formatLink(_("Information panel"), 'info_panel')
    pbar_line_lnk     = '<b>%s</b>'%self._formatLink(_("Progress bar line"), 'pbar_panel')
    buttons_line_lnk  = '<b>%s</b>'%self._formatLink(_("Button line"), 'button_panel')
    search_dlg_lnk    = '<b>%s</b>'%self._formatLink(_("Search dialog"), 'search_dlg')
    history_dlg_lnk   = '<b>%s</b>'%self._formatLink(_('History dialog'), 'history_dlg')

    index = '<ul><li>%s</li><li>%s</li><li>%s</li><li>%s</li><li>%s</li><li>%s</li><li>%s</li><li>%s</li><li>%s</li></ul>'%(
      menu_line_lnk,
      filters_lnk,
      group_panel_lnk,
      package_panel_lnk,
      info_panel_lnk,
      pbar_line_lnk,
      buttons_line_lnk,
      search_dlg_lnk,
      history_dlg_lnk,
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
        _("dnfdragora is basically a package manager user interface that allows you to install, update, remove, and search for packages and more.<br><br>") + \
        _("dnfdragora is part of manatools and it is based on manatools.aui so that it can work using Qt (PySide6), GTK 4, or ncurses, i.e. both graphical and textual user interfaces.<br><br>") +\
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
          _('This menu removes any flags on packages; if any packages have been selected for installation or removal, they will be reset to their previous status.<br>') +\
        _('<h2>Refresh metadata</h2>') +\
          _('This menu sends a request to dnfdaemon to force a refresh of all the metadata. This action is asynchronous and requires rebuilding the package information cache.<br>') +\
        _('<h2>Repositories</h2>') +\
          _('This menu opens the Repository Management dialog.<br>') +\
          _('The dialog lists all configured repositories sorted by name. You can enable or disable each repository using its checkbox. Changes take effect immediately for the current session but are not permanent.<br><br>') +\
          _('<b>Filter frame \u2014 Show additional repository types</b><br>') +\
          _('By default the list hides debug-information, source, and testing repositories. Expand the filter frame by checking its title to show three additional checkboxes:<br>') +\
          _('<ul>') +\
          _('<li><b>Debug information</b>: show repositories whose id ends with <i>-debuginfo</i>.</li>') +\
          _('<li><b>Source</b>: show repositories whose id ends with <i>-source</i>.</li>') +\
          _('<li><b>Testing</b>: show repositories whose id contains <i>testing</i>.</li>') +\
          _('</ul>') +\
          _('If any repository of those types is currently <b>enabled</b> in DNF, the corresponding checkbox is automatically turned on and the frame is expanded, ensuring an active repository is never hidden.<br>') +\
          _('The filter selections are saved in the user configuration file and restored at the next launch.<br>')+\
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
          _('This menu opens the %s, which shows packages recently changed on the system.'%self._formatLink(_('History dialog'), 'history_dlg')),
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
        _('dnfdragora options'),
        # help
        _('This dialog allows to customize dnfdragora behavior by changing options. Some changes are available after closing the dialog, others need a dnfdragora restart.<br><br>') + \
        _('<h2>System options</h2>') + \
          _('<ul><li><b>Run transactions on packages automatically without confirmation needed</b>: if checked transactions do not need to be confirmed, dnfdragora works as answering always <i>yes</i>.') + \
            _('<br><b>NOTE</b> that this option means that also removing packages is silently accepted</li>') + \
          _('<li><b>Consider packages to upgrade as updates</b>: if checked upgrades are added to updates and filtered as updates.</li>') + \
          _('<li><b>Hide dnfdragora-update menu if there are no updates</b>: if checked dnfdragora update is hidden if there are no updates.') + \
            _('<br><b>NOTE</b> that this option is experimental, not all desktops manage it as expected</li>') + \
          _('<li><b>Interval to check for updates</b>: the given number represents how often dnfdragora checks for updates; the value is expressed in minutes</li>') + \
          _('<li><b>Metadata expire time</b>: time to force Metadata expiration, the value is expressed in hours</li></ul>') + \
        _('<h2>Layout options</h2>') + \
          _('<ul><li><b>Show updates</b>: if checked dnfdragora starts with <i>updates</i> filter active, i.e. showing only package available for updates if any.</li>') + \
          _('<li><b>Do not show groups view</b>: filtering by groups could require CPU if using comps, if this option is checked dnfdragora starts showing all packages.</li></ul>') + \
          _('<b>NOTE</b> that the above options require dnfdragora to be restarted.') + \
        _('<h2>Logging options</h2>') + \
          _('Enable these options to let dnfdragora log on file called <i>dnfdragora.log</i>.') + \
          _('<ul><li><b>Change directory</b>: this option allows you to set the logging directory; the directory must exist and needs write permission.</li>') + \
          _('<li><b>Debug level</b>: if checked, verbose logging is enabled.</li></ul>') + \
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
        _('Views, filters and search'),
        # help
        _('<h2>Views</h2>') +\
          _('The first combobox allows you to show packages by groups. If <i>Groups</i> is selected, the group panel shows a tree view containing groups, and selecting a group shows related packages in the package panel.<br>') + \
          _('If <i>All</i> is selected, the package panel contains all the packages.<br>') + \
        _('<h2>Filters</h2>') +\
          _('The Filter combobox allows you to filter the packages shown in the package panel by:') + \
          '<ul>' + \
            _('<li><b>Installed</b>: shows installed packages only.</li>') + \
            _('<li><b>Not installed</b>: shows available packages only.</li>') + \
            _('<li><b>To update</b>: shows packages that are available for updates only.</li>') + \
            _('<li><b>Desktop Applications</b>: shows packages that provide desktop/GUI applications.</li>') + \
            _('<li><b>Show x86_64 and noarch only</b>: if dnfdragora is running on x86_64 architecture, it hides i686 packages.</li>') + \
            _('<li><b>All</b>: shows all the packages, i.e. available, updates and installed.</li>') + \
          '</ul>' + \
        _('<h2>Search</h2>') +\
          _('Pressing the <b>Search</b> button (magnifier icon) opens the %s '% self._formatLink(_('Search dialog'), 'search_dlg')) + \
          _('that provides full-featured package search. When a search is active the filter combobox is disabled ') + \
          _('and an info label shows the active search text or dependency query. ') + \
          _('The <b>Clear search</b> button (eraser icon) next to the Search button resets all search state ') + \
          _('and re-enables the filter combobox.<br>') + \
        '<br>',
        # back home
        home_lnk,
      ),

      'group_panel': '<h1>%s</h1>%s<br>%s'%(
        # title
        _('Group panel'),
        # help
        _('This panel shows all the groups available to filter packages, if the Groups view is selected. The special group <i>Search</i> is added after a search is performed.') + \
        '<br>',
        # back home
        home_lnk,
      ),

      'package_panel': '<h1>%s</h1>%s<br>%s'%(
        # title
        _('Package panel'),
        # help
        _('This panel shows all the filtered packages with their basic information such as <i>name</i>, <i>summary</i>, <i>version</i>, <i>release</i>, <i>architecture</i>, <i>size</i>, and <i>status</i>.') + \
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

      'history_dlg': '<h1>%s</h1>%s<br>%s'%(
        # title
        _('History dialog'),
        # help
        _('The History dialog shows packages that have been recently changed on the system by querying the dnf5daemon History API.<br><br>') +
        _('<h2>Opening the dialog</h2>') +
        _('Open the dialog from the menu bar: <b>Actions → History</b>.<br>') +
        _('The main dnfdragora window is disabled while the dialog is open to prevent unintended interactions.<br><br>') +
        _('<h2>Filters</h2>') +
        _('The <b>Filters</b> section at the top of the dialog lets you narrow the results:<br>') +
        _('<ul>') +
        _('<li><b>Since (YYYY-MM-DD)</b>: enter a date to show only packages changed on or after that date. ') +
        _('Leave empty to retrieve all available history. ') +
        _('The date is converted to a Unix timestamp before being sent to the daemon.</li>') +
        _('</ul>') +
        _('<h2>Change type checkboxes</h2>') +
        _('Four checkboxes let you choose which kinds of package changes to include in the results:<br>') +
        _('<ul>') +
        _('<li><b>Installed</b>: packages that were newly installed.</li>') +
        _('<li><b>Removed</b>: packages that were removed from the system.</li>') +
        _('<li><b>Upgraded</b>: packages that were upgraded to a newer version.</li>') +
        _('<li><b>Downgraded</b>: packages that were downgraded to an older version.</li>') +
        _('</ul>') +
        _('Uncheck any type you are not interested in to reduce the number of rows shown.<br><br>') +
        _('<h2>Advisory options</h2>') +
        _('<ul>') +
        _('<li><b>Include advisories</b>: when checked, advisory information (security, bugfix, enhancement) is included where available.</li>') +
        _('<li><b>All advisories</b>: when checked together with <i>Include advisories</i>, all advisory types are returned rather than only the most relevant one per package. ') +
        _('This option is automatically disabled when <i>Include advisories</i> is unchecked.</li>') +
        _('</ul>') +
        _('<h2>Results table</h2>') +
        _('The table shows one row per changed package with the following columns:<br>') +
        _('<ul>') +
        _('<li><b>Name</b>: the package name.</li>') +
        _('<li><b>EVR</b>: epoch:version-release of the new (installed) version.</li>') +
        _('<li><b>Arch</b>: the package architecture.</li>') +
        _('<li><b>Action</b>: one of <i>installed</i>, <i>removed</i>, <i>upgraded</i>, or <i>downgraded</i>.</li>') +
        _('<li><b>Date</b>: the date and time of the transaction (YYYY-MM-DD HH:MM).</li>') +
        _('<li><b>Summary</b>: a short description of the package.</li>') +
        _('</ul>') +
        _('If no packages match the current filters a <i>No results</i> row is shown.<br>') +
        _('If the daemon call fails the error message is displayed in the table so you can diagnose the problem.<br><br>') +
        _('<h2>Refresh button</h2>') +
        _('Press <b>Refresh</b> to re-query the daemon with the current filter settings. ') +
        _('The dialog also queries automatically when it first opens.<br><br>') +
        _('<h2>Close button</h2>') +
        _('Press <b>Close</b> (or the window close button) to dismiss the dialog and return to the main window.<br>'),
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
  
  
