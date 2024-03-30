'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Angelo Naselli <anaselli@linux.it>

@package dnfdragora
'''

# NOTE part of this code is imported from yumex-dnf

import logging
import re
import threading
import libdnf5

from os import listdir
import dnfdaemon.client

import dnfdragora.backend
import dnfdragora.dnfd_client
import dnfdragora.misc
import dnfdragora.const as const
from dnfdragora.misc import ExceptionHandler, TimeFunction

logger = logging.getLogger('dnfdragora.dnf_backend')


class DnfPackage(dnfdragora.backend.Package):
    """Abstract package object for a package in the package system."""

    def __init__(self, backend, dbus_pkg=None, action=None, pkg_id=None):
        dnfdragora.backend.Package.__init__(self, backend)

        if (not dbus_pkg and not action and not pkg_id) or (dbus_pkg and pkg_id):
            raise Exception("DnfPackage init")

        self._description = ""
        self._changelogs  = ""
        self._files       = ""
        self._updateinfo  = None
        self._requires    = None

        if dbus_pkg:
            self.action = action

            if "nevra" in dbus_pkg.keys():
                # example: zypper-aptitude-0:1.14.59-1.fc38.noarch
                # Nevra.parse return a vector of nevras, first one is the one we need
                pkg = libdnf5.rpm.Nevra.parse(dbus_pkg["nevra"])[0]
                self.name  = pkg.get_name()
                self.epoch = pkg.get_epoch()
                self.ver   = pkg.get_version()
                self.rel   = pkg.get_release()
                self.arch  = pkg.get_arch()

            if "name" in dbus_pkg.keys():
                self.name = dbus_pkg["name"]
            if "epoch" in dbus_pkg.keys():
                self.epoch = dbus_pkg["epoch"]
            if "version" in dbus_pkg.keys():
                self.ver = dbus_pkg["version"]
            if "release" in dbus_pkg.keys():
                self.rel = dbus_pkg["release"]
            if "arch" in dbus_pkg.keys():
                self.arch = dbus_pkg["arch"]

            self.repository = dbus_pkg["repo_id"] if "repo_id" in dbus_pkg.keys() else None

            self.pkg_id = dnfdragora.misc.to_pkg_id(self.name, self.epoch, self.version, self.release, self.arch, self.repository)

            self.full_nevra = dbus_pkg["full_nevra"] if "full_nevra" in dbus_pkg.keys() else dnfdragora.misc.pkg_id_to_full_name(self.pkg_id)

            self._summary = dbus_pkg["summary"] if "summary" in dbus_pkg.keys() else None
            #self._description = dbus_pkg['description'] if ('description' in dbus_pkg.keys()) else None
            self.url = dbus_pkg["url"] if "url" in dbus_pkg.keys() else None
            self.grp = dbus_pkg["group"] if "group" in dbus_pkg.keys() else None

            self.install_size = dbus_pkg["install_size"]  if "install_size" in dbus_pkg.keys() else 0
            self.download_size = dbus_pkg["download_size"] if "download_size" in dbus_pkg.keys() else 0
            #TODO manage both sizes
            self.size = self.install_size
            self.sizeM = dnfdragora.misc.format_size(self.size)

            #self._is_installed = dbus_pkg["is_installed"]
        elif pkg_id:
            self.pkg_id = pkg_id
            (self.name, self.epoch, self.ver, self.rel, self.arch, self.repository) = dnfdragora.misc.to_pkg_tuple(pkg_id)
            self.full_nevra = dnfdragora.misc.pkg_id_to_full_name(self.pkg_id)

            #TODO fix next attributes if possible
            #self._is_installed = False
            self.action = None
            self._summary = ""
            self.url = None
            self.grp = ""
            self.install_size =  0
            self.download_size = 0
            self.size = self.install_size
            self.sizeM = dnfdragora.misc.format_size(self.size)

        self.visible = True
        self.selected = False
        self.downgrade_po = None
        # cache

    def __str__(self):
        """String representation of the package object."""
        return self.fullname

    @property
    def fullname(self):
        return dnfdragora.misc.pkg_id_to_full_name(self.pkg_id)

    @ExceptionHandler
    def get_attribute(self, attr):
        """Get a given attribute for a package."""
        return self.backend.GetAttribute(self.full_nevra, attr, sync=True)

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
        if not self.grp:
            self.grp = self.get_attribute('group')
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
        if not self.url:
            self.url = self.get_attribute('url')
        return self.url

    @property
    @ExceptionHandler
    def summary(self):
        if not self._summary:
            self._summary = self.get_attribute('summary')
        return self._summary

    @summary.setter
    def summary(self, value):
        self._summary = value

    def set_select(self, state):
        """Package is selected in package view."""
        self.selected = state

    def set_visible(self, state):
        """Package is visible in package view"""
        self.visible = state

    @property
    @ExceptionHandler
    def description(self):
        if not self._description:
            self._description = self.get_attribute('description')
        return self._description

    @property
    @ExceptionHandler
    def changelog(self):
        ''' get changelogs information '''
        if not self._changelogs:
            self._changelogs = self.get_attribute('changelogs')
        return self._changelogs

    @property
    @ExceptionHandler
    def filelist(self):
        ''' returns package file list '''
        if not self._files:
            self._files = self.get_attribute('files')
        return self._files


    @property
    @ExceptionHandler
    def updateinfo(self):
        '''
            return advisory info for this package
        '''
        if not self._updateinfo:
            options = {
                'advisory_attrs' : [
                "advisoryid", "name", "title", "type", "severity", "status", "vendor", "description", "buildtime", "message", "rights", "collections", "references"
                ],
                "contains_pkgs": [self.name]
            }
            self._updateinfo = self.backend.Advisories(options, sync=True)
        return self._updateinfo

    @property
    @ExceptionHandler
    def requirements(self):
        if not self._requires:
            self._requires = self.get_attribute('requires')
        return self._requires

    @property
    def is_update(self):
        """Package is an update/replacement to another package."""
        return self.action == 'o' or self.action == 'u'


class DnfRootBackend(dnfdragora.backend.Backend, dnfdragora.dnfd_client.Client):
    """Backend to do all the dnf related actions """

    def __init__(self, frontend, use_comps=False):
        dnfdragora.backend.Backend.__init__(self, frontend, filters=True)
        dnfdragora.dnfd_client.Client.__init__(self)
        self.dnl_progress = None
        self._files_to_download = 0
        self._files_downloaded = 0
        self._use_comps = use_comps
        self._group_cache = None
        self._protected = None
        self._pkg_id_to_groups_cache = None

    @ExceptionHandler
    def quit(self):
        """Quit the dnf backend daemon."""
        logger.info("Quit")

    @ExceptionHandler
    def reload(self):
        """Reload the dnf backend daemon."""
        logger.info("reload")
        #NOTE caching groups is slow let's do only once by now
        self.clear_cache()

    @ExceptionHandler
    def clear_cache(self, also_groups=False):
        '''empty package and group cache .'''
        self.cache.reset()  # Reset the cache
        self._group_cache = None
        #NOTE caching groups is slow let's do it only once if needed
        if also_groups:
          self._pkg_id_to_groups_cache = None

    def to_pkg_tuple(self, pkg_id):
        """Get package nevra & repoid from an package pkg_id"""
        (n, e, v, r, a, repo_id) = str(pkg_id).split(',')
        return (n, e, v, r, a, repo_id)

    def make_pkg_object(self, pkgs, flt):
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
            append(DnfPackage(self, dbus_pkg=pkg_values, action=action))
        return self.cache.find_packages(po_list)

    @TimeFunction
    def make_pkg_object_with_attr(self, pkgs):
        """Make list of Packages from a list of pkg_ids & attrs.

        Package have different action type
        Package object are taken from cache if available.

        :param pkgs: list with (pkg_id, summary, size, action)
        """
        po_list = []
        append = po_list.append
        for pkg_id in pkgs:
            #TODO action / is_installed
            append(DnfPackage(self, pkg_id=pkg_id))
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
        sync=True
        for pkg_id in pkg_ids:
              append(DnfPackage(self, pkg_id=pkg_id))
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
            if self.cache.is_populated(pkg_flt):
              result += dnfdragora.backend.Backend.get_packages(self, pkg_flt)
            else:
              logger.error("Cache is not populated for %s", pkg_flt) #TODO manage
        logger.debug('get-packages : %s ', len(result))
        return result

    @ExceptionHandler
    @TimeFunction
    def _get_groups_from_packages(self):
        """Get groups by looking for all packages group property."""
        try:
          packages = self.get_packages('all')
        except Exception as err:
          logger.error("Exception %s"%(err))
        logger.debug('_get-groups-from-packages got %d',len(packages))
        result = []
        append = result.append
        for pkg in packages:
            if pkg.group not in result :
                append(pkg.group)

        return result

    @ExceptionHandler
    def get_repositories(self, flt=['*']):
        """Get a list of repo attributes to populate repo view."""
        repos = self.GetRepositories(patterns=flt, sync=True)
        repo_list = [ repo for repo in repos if not repo['id'].endswith('-source') and not repo['id'].endswith('-debuginfo') ]
        return sorted(repo_list, key=lambda elem: (elem['name'], elem['id']))

    @TimeFunction
    @ExceptionHandler
    def get_packages_by_name(self, name_key):
        """Get packages by a given name wildcard.

        :param name_key: package wildcard
        """
        pkgs=self.search("installed", "name", name_key, True)

        return pkgs

    @TimeFunction
    def __search_loop(self, filter, attr, regexp):
      '''
      Async thread loop to be used in searching. Requires package caching performed.
      Emits a "RESearch" dnfdaemon client like event.
      '''
      pl = self.get_packages(filter)
      logger.debug("Searching <%s> from <%s> attribute into %d packages", regexp, attr, len(pl))
      packages = []
      exe_error = None
      if len(pl) > 0:
        if not hasattr(pl[0], attr):
          exe_error = _("package has not any %s attributes"%(attr))
          logger.error("package has not any %s attributes", attr)

      if exe_error == None:
        try:
          s = re.compile(regexp)
          #for p in pl:
            #if hasattr(p, attr) and s.search(str(getattr(p, attr))):
              #packages.append(p)
            #elif not hasattr(p, attr):
              #logger.error("package has not any %s attributes", attr)
          packages = [ p for p in pl if s.search(str(getattr(p, attr))) ]
        except Exception as e:
          logger.error(str(e))
          exe_error = str(e)

      response = { 'result' : None if exe_error else packages, 'error' : exe_error }
      self.eventQueue.put({'event': 'RESearch', 'value': response})
      logger.debug("__search_loop exit. Found %d pacakges", len(packages))

    @TimeFunction
    @ExceptionHandler
    def search(self, filter, attr, regexp, sync=False):
        """Search given pkg attributes for given keys.
        :param filter: filter packages for all, updates, installed or available
        :param attr: package attr to search in (name, filelist, etc.)
        :param regexp: regular expression using python syntax to search for
        """
        if sync:
          packages = [p for p in self.get_packages(filter) if re.search(regexp, str(p.get_attribute(attr))) ]  # str(p.filelist)) ]
          return packages
        else:
          t = threading.Thread(target=self.__search_loop, args=(filter, attr, regexp))
          t.start()


    @ExceptionHandler
    @TimeFunction
    def _cacheProtected(self) :
        '''
        gets all the protected packages
        '''
        self._protected = []
        protected_conf_path='/etc/dnf/protected.d'
        conf_files = listdir(protected_conf_path)
        pkg_lst = []
        for f in conf_files :
            file_path = protected_conf_path + '/' + f

            with open(file_path, 'r') as content_file:
                for line in content_file:
                    if line.strip() :
                        pkg_lst.append(line.strip())

        options = {
          "scope": "installed",
          "patterns": pkg_lst
        }
        pkgs = self.Search(options, True)

        for pkg_id in pkgs:
            if (not pkg_id in self._protected) :
                self._protected.append(pkg_id)
        # TODO it would be better to get recursive require
        #for pkg_id in self._protected:
            #recursive_id = self.GetAttribute(pkg_id,'requires')


    def protected(self, pkg) :
        '''
        if pkg is not none returns if the given package is a protected one
        '''
        if not self._protected :
            self._cacheProtected()

        found = pkg.pkg_id in self._protected

        return found

    @ExceptionHandler
    def get_groups(self):
        """Get groups/categories from dnf daemon backend if use comps or evaluated from packages otherwise"""
        if not self._group_cache :
            if self._use_comps:
                self._group_cache = []
                rpm_comps =  self.GetGroups(sync=True)
                self._group_cache = [gr[0] for gr in rpm_comps]
            else :
                self._group_cache = self._get_groups_from_packages()

        return self._group_cache

    @ExceptionHandler
    @TimeFunction
    def get_groups_from_package(self, pkg):
        '''
        returns a list containing comps which the package belongs to if use comps, 
        or the package group otherwise
        @param pkg: given package
        '''
        groups = []
        if self._use_comps:
            groups = self.GetGroupsFromPackage(pkg.name, sync=True)
            #if not self._pkg_id_to_groups_cache:
            #    # fill the cache
            #    self._pkg_id_to_groups_cache = {}
            #    rpm_groups = self.get_groups()
            #    tot = len(rpm_groups)
            #    self.frontend.infobar.set_progress(0.0)
            #    self.frontend.infobar.info(_('Caching groups from packages... '))
            #    g = 0
            #    for groupName in rpm_groups:
            #        perc = float(float(g*1.0)/tot)
            #        self.frontend.infobar.set_progress(perc)
            #        g+=1
            #        #NOTE getting just a string now and package names
            #        pkg_names = self.GetGroupPackageNames(groupName, sync=True)
            #        self._pkg_id_to_groups_cache[groupName] = pkg_names
            #        #for name in pkg_names :
            #        #    if name not in self._pkg_id_to_groups_cache.keys():
            #        #        self._pkg_id_to_groups_cache[name] = []
            #        #    self._pkg_id_to_groups_cache[name].append(groupName)
            #    self.frontend.infobar.set_progress(0.0)
            #    self.frontend.infobar.info("")
            #groups = self._pkg_id_to_groups_cache[pkg.name] if pkg.name in self._pkg_id_to_groups_cache.keys() else ['Uncategorized']
            #groups = [ gr for gr in self._pkg_id_to_groups_cache.keys() if pkg.name in self._pkg_id_to_groups_cache[gr] ]
            if len(groups) == 0:
                groups = ['Uncategorized']
        else :
            groups.append(pkg.group)

        return groups
