'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Angelo Naselli <anaselli@linux.it>

@package dnfdragora
'''

# NOTE part of this code is imported from yumex-dnf

import logging

import dnfdaemon.client

import dnfdragora.backend
import dnfdragora.misc
import dnfdragora.const as const
from dnfdragora.misc import ExceptionHandler, TimeFunction

from gettext import gettext as _

logger = logging.getLogger('dnfdragora.dnf_backend')


class DnfPackage(dnfdragora.backend.Package):
    """Abstract package object for a package in the package system."""

    def __init__(self, po_tuple, action, backend):
        dnfdragora.backend.Package.__init__(self, backend)
        (pkg_id, summary, size, group) = po_tuple
        self.pkg_id = pkg_id
        self.action = action
        (n, e, v, r, a, repo_id) = dnfdragora.misc.to_pkg_tuple(self.pkg_id)
        self.name = n
        self.epoch = e
        self.ver = v
        self.rel = r
        self.arch = a
        self.repository = repo_id
        self.visible = True
        self.selected = False
        self.downgrade_po = None
        self.summary = summary
        self.grp = group
        self.size = size
        self.sizeM = dnfdragora.misc.format_number(size)
        # cache
        self._description = None

    def __str__(self):
        """String representation of the package object."""
        return self.fullname

    @property
    def fullname(self):
        return dnfdragora.misc.pkg_id_to_full_name(self.pkg_id)

    @ExceptionHandler
    def get_attribute(self, attr):
        """Get a given attribute for a package."""
        return self.backend.GetAttribute(self.pkg_id, attr)

    @property
    def version(self):
        return self.ver

    @property
    def release(self):
        return self.rel

    @property
    def filename(self):
        """RPM filename of a package."""
        # the full path for at localinstall is stored in repoid
        if self.action == 'li':
            return self.repoid
        else:
            return "%s-%s.%s.%s.rpm" % (self.name, self.version,
                                        self.release, self.arch)
    @property
    def group(self):
        """Package group."""
        return self.grp

    @property
    def fullver(self):
        """Package full version-release."""
        return "%s-%s" % (self.version, self.release)

    @property
    def installed(self):
        return self.repository[0] == '@'

    @property
    def URL(self):
        return self.get_attribute('url')

    def set_select(self, state):
        """Package is selected in package view."""
        self.selected = state

    def set_visible(self, state):
        """Package is visible in package view"""
        self.visible = state

    @property
    def description(self):
        return self.get_attribute('description')

    @property
    def changelog(self):
        return self.get_attribute('changelog')

    @property
    def filelist(self):
        return self.get_attribute('filelist')

    @property
    def pkgtags(self):
        return self.get_attribute('pkgtags')

    @property
    @ExceptionHandler
    def downgrades(self):
        return self.backend.get_downgrades(self.pkg_id)

    @property
    @ExceptionHandler
    def updateinfo(self):
        return self.get_attribute('updateinfo')

    @property
    @ExceptionHandler
    def requirements(self):
        return self.get_attribute('requires')

    @property
    def is_update(self):
        """Package is an update/replacement to another package."""
        return self.action == 'o' or self.action == 'u'


class DnfRootBackend(dnfdragora.backend.Backend, dnfdaemon.client.Client):
    """Backend to do all the dnf related actions """

    def __init__(self, frontend, use_comps=False):
        dnfdragora.backend.Backend.__init__(self, frontend, filters=True)
        dnfdaemon.client.Client.__init__(self)
        self._gpg_confirm = None
        self.dnl_progress = None
        self._files_to_download = 0
        self._files_downloaded = 0
        self._use_comps = use_comps
        self._group_cache = None
        self._pkg_id_to_groups_cache = None

        if self.running_api_version == const.NEEDED_DAEMON_API:
            logger.debug('dnfdaemon api version (%d)',
                         self.running_api_version)
        else:
            raise dnfdaemon.client.APIVersionError(
                                   _('dnfdaemon api version : %d'
                                     "\ndoesn't match"
                                     '\nneeded api version : %d') %
                                   (self.running_api_version,
                                    const.NEEDED_DAEMON_API))

    def on_TransactionEvent(self, event, data):
        if event == 'start-run':
            print('on_TransactionEvent start')
            self.frontend.infobar.info(_('Start transaction'))
        elif event == 'download':
            print('on_TransactionEvent download')
            self.frontend.infobar.info(_('Downloading packages'))
        elif event == 'pkg-to-download':
            self._dnl_packages = data
        elif event == 'signature-check':
            print('on_TransactionEvent signature')
            # self.frontend.infobar.show_progress(False)
            self.frontend.infobar.set_progress(0.0)
            self.frontend.infobar.info(_('Checking package signatures'))
            self.frontend.infobar.set_progress(1.0)
            self.frontend.infobar.info_sub('')
        elif event == 'run-test-transaction':
            print('on_TransactionEvent test')
            # self.frontend.infobar.info(_('Testing Package Transactions')) #
            # User don't care
            pass
        elif event == 'run-transaction':
            print('on_TransactionEvent run transaction')
            self.frontend.infobar.info(_('Applying changes to the system'))
            self.frontend.infobar.info_sub('')
        elif event == 'verify':
            print('on_TransactionEvent verify')
            self.frontend.infobar.info(_('Verify changes on the system'))
            #self.frontend.infobar.hide_sublabel()
        # elif event == '':
        elif event == 'fail':
            print('on_TransactionEvent fail')
            self.frontend.infobar.reset_all()
        elif event == 'end-run':
            print('on_TransactionEvent end')
            self.frontend.infobar.set_progress(1.0)
            self.frontend.infobar.reset_all()
        else:
            logger.debug('TransactionEvent : %s', event)

    def on_RPMProgress(self, package, action, te_current,
                       te_total, ts_current, ts_total):
        #print('on_RPMProgress')
        num = ' ( %i/%i )' % (ts_current, ts_total)
        if ',' in package:  # this is a pkg_id
            name = dnfdragora.misc.pkg_id_to_full_name(package)
        else:  # this is just a pkg name (cleanup)
            name = package
        logger.debug('on_RPMProgress : [%s]', package)
        #print (const.RPM_ACTIONS[action] % name)
        self.frontend.infobar.info_sub(const.RPM_ACTIONS[action] % name)
        if ts_current > 0 and ts_current <= ts_total:
            frac = float(ts_current) / float(ts_total)
            self.frontend.infobar.set_progress(frac, label=num)

    def on_GPGImport(self, pkg_id, userid, hexkeyid, keyurl, timestamp):
        print('on_GPGImport')
        values = (pkg_id, userid, hexkeyid, keyurl, timestamp)
        self._gpg_confirm = values
        logger.debug('received signal : GPGImport %s', repr(values))

    def on_DownloadStart(self, num_files, num_bytes):
        """Starting a new parallel download batch."""
        #values =  (num_files, num_bytes)
        #print('on_DownloadStart : %s' % (repr(values)))
        self._files_to_download = num_files
        self._files_downloaded = 0
        self.frontend.infobar.set_progress(0.0)
        self.frontend.infobar.info_sub(
            _('Downloading %d files (%sB)...') %
            (num_files, dnfdragora.misc.format_number(num_bytes)))

    def on_DownloadProgress(self, name, frac, total_frac, total_files):
        """Progress for a single element in the batch."""
        #values =  (name, frac, total_frac, total_files)
        #print('on_DownloadProgress : %s' % (repr(values)))
        num = '( %d/%d )' % (self._files_downloaded, self._files_to_download)
        self.frontend.infobar.set_progress(total_frac, label=num)

    def on_DownloadEnd(self, name, status, msg):
        """Download of af single element ended."""
        #values =  (name, status, msg)
        #print('on_DownloadEnd : %s' % (repr(values)))
        if status == -1 or status == 2:  # download OK or already exists
            logger.debug('Downloaded : %s', name)
            self._files_downloaded += 1
        else:
            logger.debug('Download Error : %s - %s', name, msg)
        self.frontend.infobar.set_progress(1.0)
        #self.frontend.infobar.reset_all()

    def on_RepoMetaDataProgress(self, name, frac):
        """Repository Metadata Download progress."""
        values = (name, frac)
        #print('on_RepoMetaDataProgress (root): %s', repr(values))
        logger.debug('on_RepoMetaDataProgress (root): %s', repr(values))
        if frac == 0.0:
            self.frontend.infobar.info_sub(name)
        elif frac == 1.0:
            self.frontend.infobar.set_progress(1.0)
            self.frontend.infobar.reset_all()
        else:
            self.frontend.infobar.set_progress(frac)

    def setup(self):
        """Setup the dnf backend daemon."""
        try:
            self.Lock()
            self.SetWatchdogState(False)
            self._update_config_options()
            return True, ''
        except dnfdaemon.client.AccessDeniedError:
            return False, 'not-authorized'
        except dnfdaemon.client.LockedError:
            return False, 'locked-by-other'

    @ExceptionHandler
    def quit(self):
        """Quit the dnf backend daemon."""
        self.Unlock()
        self.Exit()

    @ExceptionHandler
    def reload(self):
        """Reload the dnf backend daemon."""
        self.Unlock()  # Release the lock
        # time.sleep(5)
        self.Lock()  # Load & Lock the daemon
        self.SetWatchdogState(False)
        #self._update_config_options()
        self.cache.reset()  # Reset the cache
        self._group_cache = None
        #NOTE caching groups is slow let's do only once by now
        #self._pkg_id_to_groups_cache = None

    def _update_config_options(self):
        pass

    def to_pkg_tuple(self, pkg_id):
        """Get package nevra & repoid from an package pkg_id"""
        (n, e, v, r, a, repo_id) = str(pkg_id).split(',')
        return (n, e, v, r, a, repo_id)

    def _make_pkg_object(self, pkgs, flt):
        """Get a list Package objects from a list of pkg_ids & attrs.

        All packages has the same action type.
        Package object are taken from cache if available.

        :param pkgs: list of (pkg_id, summary, size)
        :param flt: pkg_filter (installed, available ....)
        """
        # TODO: should be combined with _make_pkg_object_with_attr
        # No need for 3 almost indentical way to make a list of package objects
        po_list = []
        append = po_list.append
        action = const.FILTER_ACTIONS[flt]
        for pkg_values in pkgs:
            append(DnfPackage(pkg_values, action, self))
        return self.cache.find_packages(po_list)

    @TimeFunction
    def _make_pkg_object_with_attr(self, pkgs):
        """Make list of Packages from a list of pkg_ids & attrs.

        Package have different action type
        Package object are taken from cache if available.

        :param pkgs: list with (pkg_id, summary, size, action)
        """
        po_list = []
        append = po_list.append
        for elem in pkgs:
            (pkg_id, summary, size, group, action) = elem
            po_tuple = (pkg_id, summary, size, group)
            append(DnfPackage(po_tuple, const.BACKEND_ACTIONS[action], self))
        return self.cache.find_packages(po_list)

    def _build_package_list(self, pkg_ids):
        """Make list of Packages from a list of pkg_ids

        Summary, size and action is read from dnf backend

        Package object are taken from cache if available.

        :param pkg_ids:
        """
        # TODO: should be combined with _make_pkg_object_with_attr
        # No need for 3 almost indentical way to make a list of package objects
        po_list = []
        append = po_list.append
        for pkg_id in pkg_ids:
            summary = self.GetAttribute(pkg_id, 'summary')
            size = self.GetAttribute(pkg_id, 'size')
            group = self.GetAttribute(pkg_id, 'group')

            pkg_values = (pkg_id, summary, size, group)
            action = const.BACKEND_ACTIONS[self.GetAttribute(pkg_id, 'action')]
            append(DnfPackage(pkg_values, action, self))
        return self.cache.find_packages(po_list)

    @ExceptionHandler
    @TimeFunction
    def get_packages(self, flt):
        """Get packages for a given pkg filter."""
        logger.debug('get-packages : %s ', flt)
        if flt == 'all':
            filters = ['updates', 'installed', 'available']
        else:
            filters = [flt]
        result = []
        for pkg_flt in filters:
            # is this type of packages is already cached ?
            if not self.cache.is_populated(pkg_flt):
                print ("not in cache")
                fields = ['summary', 'size', 'group']  # fields to get
                po_list = self.GetPackages(pkg_flt, fields)
                if pkg_flt == 'updates_all':
                    pkg_flt = 'updates'
                pkgs = self._make_pkg_object(po_list, pkg_flt)
                self.cache.populate(pkg_flt, pkgs)
            result.extend(dnfdragora.backend.Backend.get_packages(self, pkg_flt))
        return result

    @ExceptionHandler
    @TimeFunction
    def _get_groups_from_packages(self):
        """Get groups by looking for all packages group property."""
        logger.debug('_get-groups-from-packages')
        packages = self.get_packages('all')
        result = []
        append = result.append
        for pkg in packages:
            if pkg.group not in result :
                append(pkg.group)

        return result

    @ExceptionHandler
    def get_downgrades(self, pkg_id):
        """Get downgrades for a given pkg_id"""
        pkgs = self.GetAttribute(pkg_id, 'downgrades')
        return self._build_package_list(pkgs)

    @ExceptionHandler
    def get_repo_ids(self, flt):
        """Get repository ids"""
        repos = self.GetRepositories(flt)
        return repos

    @ExceptionHandler
    def get_repositories(self, flt='*'):
        """Get a list of repo attributes to populate repo view."""
        repo_list = []
        repos = self.GetRepositories(flt)
        for repo_id in repos:
            if repo_id.endswith('-source') or repo_id.endswith('-debuginfo'):
                continue
            repo = self.GetRepo(repo_id)
            repo_list.append([repo['enabled'], repo_id, repo['name'], False])
        return sorted(repo_list, key=lambda elem: elem[1])

    @TimeFunction
    @ExceptionHandler
    def get_packages_by_name(self, name_key, newest_only):
        """Get packages by a given name wildcard.

        :param name_key: package wildcard
        :param newest_only: get lastest version only
        """
        attrs = ['summary', 'size', 'group', 'action']
        pkgs = self.GetPackagesByName(name_key, attrs, newest_only)
        return self._make_pkg_object_with_attr(pkgs)

    @ExceptionHandler
    def search(self, search_attrs, keys, match_all, newest_only, tags):
        """Search given pkg attributes for given keys.

        :param search_attrs: package attrs to search in
        :param keys: keys to search for
        :param match_all: match all keys
        """
        attrs = ['summary', 'size', 'group', 'action']
        pkgs = self.Search(search_attrs, keys, attrs, match_all,
                           newest_only, tags)
        return self._make_pkg_object_with_attr(pkgs)

    def _getAllGroupIDList(self, groups, new_groups, g_id=None) :
        '''
        return a list of group ID as pathnames from comps
        '''
        gid = g_id
        for gl in groups:
            if (isinstance(gl, list)):
                if (type(gl[0]) is str) :
                    new_groups.append(gid + "/" + gl[0] if (gid) else gl[0])
                    if not gid :
                        gid = gl[0]
                else :
                    self._getAllGroupIDList(gl, new_groups, gid)

    @ExceptionHandler
    def get_groups(self):
        """Get groups/categories from dnf daemon backend if use comps or evaluated from packages otherwise"""
        if not self._group_cache :
            if self._use_comps:
                self._group_cache = []
                rpm_groups = self.GetGroups()
                self._getAllGroupIDList(rpm_groups, self._group_cache)
            else :
                self._group_cache = self._get_groups_from_packages()

        return self._group_cache

    @ExceptionHandler
    def get_groups_from_package(self, pkg):
        '''
        returns a list containing comps which the package belongs to if use comps, 
        or the package group otherwise
        @param pkg: given package
        '''
        groups = []
        if self._use_comps:
            if not self._pkg_id_to_groups_cache:
                # fill the cache
                self._pkg_id_to_groups_cache = {}
                rpm_groups = self.get_groups()
                tot = len(rpm_groups)
                self.frontend.infobar.set_progress(0.0)
                self.frontend.infobar.info(_('Caching groups from package... '))
                g = 0
                for groupName in rpm_groups:
                    perc = float(float(g*1.0)/139)
                    self.frontend.infobar.set_progress(perc)
                    g+=1
                    #NOTE fedora gets packages using the leaf and not a group called X/Y/Z
                    grp = groupName.split("/")
                    #pkgs = self.get_group_packages(grp[-1], 'all')
                    pkgs = self.GetGroupPackages(grp[-1], 'all', [])
                    for pkg_id in pkgs :
                        if pkg_id not in self._pkg_id_to_groups_cache.keys():
                            self._pkg_id_to_groups_cache[pkg_id] = []
                        self._pkg_id_to_groups_cache[pkg_id].append(groupName) 
                self.frontend.infobar.set_progress(0.0)
                self.frontend.infobar.info("")
            if pkg.pkg_id in self._pkg_id_to_groups_cache.keys():
                groups = self._pkg_id_to_groups_cache[pkg.pkg_id]
        else :
            groups.append(pkg.group)

        return groups

    @TimeFunction
    def get_group_packages(self, grp_id, grp_flt):
        """Get a list of packages from a grp_id and a group filter.

        :param grp_id:
        :param grp_flt:
        """
        attrs = ['summary', 'size', 'group', 'action']
        pkgs = self.GetGroupPackages(grp_id, grp_flt, attrs)
        return self._make_pkg_object_with_attr(pkgs)
