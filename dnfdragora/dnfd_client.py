# coding: utf-8
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

# (C) 2013 - 2014 - Tim Lauridsen <timlau@fedoraproject.org>

"""
This is a Python 2.x & 3.x client API for the dnf-daemon Dbus Service

This module gives a simple pythonic interface to doing  package action
using the dnf-daemon Dbus service.

It use async call to the dnf-daemon, so signal can be catched and a Gtk gui do
not get unresonsive

There is 2 classes :class:`DnfDaemonClient` & :class:`DnfDaemonReadOnlyClient`

:class:`DnfDaemonClient` uses a system DBus service running as root and
can make chages to the system.

:class:`DnfDaemonReadOnlyClient` uses a session DBus service running as
current user and can only do readonly actions.

Usage: (Make your own subclass based on :class:`dnfdaemon.DnfDaemonClient`
and overload the signal handlers)::


    from dnfdaemon import DnfDaemonClient

    class MyClient(DnfDaemonClient):

        def __init(self):
            DnfDaemonClient.__init__(self)
            # Do your stuff here

        def on_TransactionEvent(self,event, data):
            # Do your stuff here
            pass

        def on_RPMProgress(self, package, action, te_current, te_total,
                           ts_current, ts_total):
            # Do your stuff here
            pass

        def on_GPGImport(self, pkg_id, userid, hexkeyid, keyurl,  timestamp ):
           # do stuff here
           pass

        def on_DownloadStart(self, num_files, num_bytes):
            ''' Starting a new parallel download batch '''
           # do stuff here
           pass

        def on_DownloadProgress(self, name, frac, total_frac, total_files):
            ''' Progress for a single instance in the batch '''
           # do stuff here
           pass

        def on_DownloadEnd(self, name, status, msg):
            ''' Download of af single instace ended '''
           # do stuff here
           pass

        def on_RepoMetaDataProgress(self, name, frac):
            ''' Repository Metadata Download progress '''
           # do stuff here
           pass


Usage: (Make your own subclass based on
:class:`dnfdaemon.DnfDaemonReadOnlyClient` and overload the signal handlers)::


    from dnfdaemon import DnfDaemonReadOnlyClient

    class MyClient(DnfDaemonReadOnlyClient):

        def __init(self):
            DnfDaemonClient.__init__(self)
            # Do your stuff here

        def on_RepoMetaDataProgress(self, name, frac):
            ''' Repository Metadata Download progress '''
           # do stuff here
           pass

"""

import dbus
import json # TODO remove
import sys
import re
import weakref
import logging
import threading
from queue import SimpleQueue, Empty
import dnfdragora.misc

CLIENT_API_VERSION = 2

logger = logging.getLogger("dnfdaemon.client")

from gi.repository import Gio, GLib, GObject

ORG = 'org.baseurl.DnfSystem'
INTERFACE = ORG

ORG_READONLY = 'org.baseurl.DnfSession'
INTERFACE_READONLY = ORG_READONLY

DBUS_ERR_RE = re.compile('.*GDBus.Error:([\w\.]*): (.*)$')

#
# Exceptions
#


class DaemonError(Exception):
    'Error from the backend'
    def __init__(self, msg=None):
        self.msg = msg

    def __str__(self):
        if self.msg:
            return self.msg
        else:
            return ""


class AccessDeniedError(DaemonError):
    'User press cancel button in policykit window'


class LockedError(DaemonError):
    'The Yum daemon is locked'


class TransactionError(DaemonError):
    'The yum transaction failed'


class APIVersionError(DaemonError):
    'The yum transaction failed'


#
# Helper Classes
#


class DBus:
    '''Helper class to work with GDBus in a easier way
    '''
    def __init__(self, conn):
        self.conn = conn

    def get(self, bus, obj, iface=None):
        if iface is None:
            iface = bus
        return Gio.DBusProxy.new_sync(
            self.conn, 0, None, bus, obj, iface, None
        )

    def get_async(self, callback, bus, obj, iface=None):
        if iface is None:
            iface = bus
        Gio.DBusProxy.new(
            self.conn, 0, None, bus, obj, iface, None, callback, None
        )


class WeakMethod:
    ''' Helper class to work with a weakref class method '''
    def __init__(self, inst, method):
        self.proxy = weakref.proxy(inst)
        self.method = method

    def __call__(self, *args):
        return getattr(self.proxy, self.method)(*args)


# Get the system bus
DNFDAEMON_BUS_NAME = 'org.rpm.dnf.v0'
DNFDAEMON_OBJECT_PATH = '/' + DNFDAEMON_BUS_NAME.replace('.', '/')

IFACE_SESSION_MANAGER = '{}.SessionManager'.format(DNFDAEMON_BUS_NAME)
IFACE_BASE = '{}.Base'.format(DNFDAEMON_BUS_NAME)
IFACE_REPO = '{}.rpm.Repo'.format(DNFDAEMON_BUS_NAME)
IFACE_REPOCONF = '{}.rpm.RepoConf'.format(DNFDAEMON_BUS_NAME)
IFACE_RPM = '{}.rpm.Rpm'.format(DNFDAEMON_BUS_NAME)
IFACE_GOAL = '{}.Goal'.format(DNFDAEMON_BUS_NAME)
IFACE_ADVISORY = '{}.Advisory'.format(DNFDAEMON_BUS_NAME)


def unpack_dbus(data):
    ''' convert dbus data types to python native data types '''
    if (isinstance(data, dbus.String) or
        isinstance(data, dbus.ObjectPath) or
        isinstance(data, dbus.Signature)):
        data = str(data)
    elif isinstance(data, dbus.Boolean):
        data = bool(data)
    elif (isinstance(data, dbus.Int64) or
          isinstance(data, dbus.UInt64) or
          isinstance(data, dbus.Int32) or
          isinstance(data, dbus.UInt32) or
          isinstance(data, dbus.Int16) or
          isinstance(data, dbus.UInt16) or
          isinstance(data, dbus.Byte)):
        data = int(data)
    elif isinstance(data, dbus.Double):
        data = float(data)
    elif isinstance(data, dbus.Array):
        data = [unpack_dbus(value) for value in data]
    elif isinstance(data, dbus.Struct):
        data = [unpack_dbus(value) for value in data]
    elif isinstance(data, dbus.Dictionary):
        new_data = dict()
        for key in data.keys():
            new_data[unpack_dbus(key)] = unpack_dbus(data[key])
        data = new_data
    return data

#
# Main Client Class
#


class DnfDaemonBase:

    def __init__(self):
        from dbus.mainloop.glib import DBusGMainLoop
        #dbus_loop = DBusGMainLoop()
        #self.bus = dbus.SessionBus(mainloop=dbus_loop)
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SystemBus()
        self.dbus_org = DNFDAEMON_BUS_NAME
        self.iface_session = None
        self.session_path = None
        self.iface_repo = None
        self.iface_rpm = None
        self.iface_goal = None

        self._sent = False
        self._data = {'cmd': None}
        self.eventQueue = SimpleQueue()
        self._get_daemon()
        self.__async_thread = None

        self.proxyMethod = {
          'GetPackages'      : 'list',
          'GetAttribute'     : 'list',
          'Search'           : 'list',
          'GetRepositories'  : 'list',
          'SetEnabledRepos'  : 'enable',
          'SetDisabledRepos' : 'disable',
          'ExpireCache'      : 'read_all_repos',
          }

        logger.debug("%s Dnf5Daemon loaded" %(DNFDAEMON_BUS_NAME))

    def _get_daemon(self):
        ''' Get the daemon dbus proxy object'''
        try:
            self.iface_session = dbus.Interface(
                self.bus.get_object(DNFDAEMON_BUS_NAME, DNFDAEMON_OBJECT_PATH),
                dbus_interface=IFACE_SESSION_MANAGER)
            self.session_path = self.iface_session.open_session({})

            self.iface_base = dbus.Interface(
                self.bus.get_object(DNFDAEMON_BUS_NAME, self.session_path),
                dbus_interface=IFACE_BASE)
            self.iface_repo = dbus.Interface(
                self.bus.get_object(DNFDAEMON_BUS_NAME, self.session_path),
                dbus_interface=IFACE_REPO)
            self.iface_repoconf = dbus.Interface(
                self.bus.get_object(DNFDAEMON_BUS_NAME, self.session_path),
                dbus_interface=IFACE_REPOCONF)

            self.iface_rpm = dbus.Interface(
                self.bus.get_object(DNFDAEMON_BUS_NAME, self.session_path),
                dbus_interface=IFACE_RPM)

            self.iface_goal = dbus.Interface(
                self.bus.get_object(DNFDAEMON_BUS_NAME, self.session_path),
                dbus_interface=IFACE_GOAL)

            self.iface_advisory = dbus.Interface(
                self.bus.get_object(DNFDAEMON_BUS_NAME, self.session_path),
                dbus_interface=IFACE_ADVISORY)


            # Managing signals
            self.iface_base.connect_to_signal("download_add_new", self.on_DownloadStart)
            self.iface_base.connect_to_signal("download_progress", self.on_DownloadProgress)
            self.iface_base.connect_to_signal("download_end", self.on_DownloadEnd)

        ### TODO check dnf5daemon errors and manage correctly
        except Exception as err:
            self._handle_dbus_error(err)

    def __del__(self):
        ''' destructor - closing session'''
        self.iface_session.close_session(self.session_path)
        logger.debug(f"Close Dnf5Daemon session: {self.session_path}")

    def __exit__(self, exc_type, exc_value, exc_traceback) -> None:
        '''exit'''
        self.iface_session.close_session(self.session_path)
        logger.debug(f"Close Dnf5Daemon session: {self.session_path}")
        if exc_type:
            logger.critical("", exc_info=(exc_type, exc_value, exc_traceback))

    def reloadDaemon(self):
        ''' close dbus connection and restart it '''
        self.iface_session.close_session(self.session_path)
        logger.debug(f"Close Dnf5Daemon session: {self.session_path}")
        self._get_daemon()

    def _on_g_signal(self, proxy, sender, signal, params):
        '''DBUS signal Handler '''
        args = params.unpack()  # unpack the glib variant
        self.handle_dbus_signals(proxy, sender, signal, args)

    def handle_dbus_signals(self, proxy, sender, signal, args):
        """ Overload in child class """
        pass

    def _handle_dbus_error(self, err):
        '''Parse error from service and raise python Exceptions
        '''
        exc, msg = self._parse_error()
        if exc != "":
            logger.error("Exception   : %s", exc)
            logger.error("   message  : %s", msg)
        if exc == self.dbus_org + '.AccessDeniedError':
            raise AccessDeniedError(msg)
        elif exc == self.dbus_org + '.LockedError':
            raise LockedError(msg)
        elif exc == self.dbus_org + '.TransactionError':
            raise TransactionError(msg)
        elif exc == self.dbus_org + '.NotImplementedError':
            raise TransactionError(msg)
        else:
            raise DaemonError(str(err))

    def _parse_error(self):
        '''parse values from a DBus related exception '''
        (type, value, traceback) = sys.exc_info()
        res = DBUS_ERR_RE.match(str(value))
        if res:
            return res.groups()
        return "", ""

    #def _return_handler(self, obj, result, user_data):
    def _return_handler(self, result, user_data):
        '''Async DBus call, return handler '''
        logger.debug("return_handler %s", user_data['cmd'])
        if isinstance(result, Exception):
            # print(result)
            user_data['result'] = None
            user_data['error'] = result
        else:
            user_data['result'] = result
            user_data['error'] = None
        #user_data['main_loop'].quit()

        response = self._get_result(user_data)
        self.eventQueue.put({'event': user_data['cmd'], 'value': response})
        self._sent = False
        logger.debug("Quit return_handler error %s", user_data['error'])



    def _get_result(self, user_data):
        '''Get return data from async call or handle error

        user_data:
        '''
        logger.debug("get_result %s", user_data['cmd'])
        result = {
          'result': user_data['result'], # default output of the command
          'error': user_data['error'],
          }
        if user_data['result']:
          ### NOTE managing exceptions on expected results
          if user_data['cmd'] == 'Search':
              result['result']  = [dnfdragora.misc.to_pkg_id(p["name"], p["epoch"], p["version"], p["release"],p["arch"], p["repo_id"]) for p in user_data['result']]
          elif user_data['cmd'] == 'GetAttribute':
            if user_data['result'] == ':none':  # illegal attribute
              result['error'] = "Illegal attribute"
            elif user_data['result'] == ':not_found':  # package not found
              result['error'] = "Package not found"
            else:
              attr = user_data["args"]["package_attrs"][0]
              result['result'] = user_data['result'][0][attr] if result['result'][0] else None

          else:
            pass

        return result

    def __async_thread_loop(self, data, *args):
      '''
      thread function for glib main loop
      '''
      logger.debug("__async_thread_loop Command %s(%s) requested ", str(data['cmd']), str(data['args']) if data['args'] else "")
      try:
        proxy = self.Proxy(data['cmd'])

        func = getattr(proxy, self.proxyMethod[data['cmd']])

        result = func(*args)

        self._return_handler(unpack_dbus(result), data)

        # TODO check if timeout = infinite is still needed
        ####func(*args, result_handler=self._return_handler,
        ####      user_data=data, timeout=GObject.G_MAXINT)
        ####loop = gobject.MainLoop()
        ####loop.run()
        #data['main_loop'].run()
      except Exception as err:
        logger.error("__async_thread_loop Exception %s"%(err))
        data['error'] = err

      # We enqueue one request at the time by now, monitoring _sent
      self._sent = False

    def _run_dbus_async(self, cmd, *args):
        '''Make an async call to a DBus method in the yumdaemon service

        cmd: method to run
        '''
        # We enqueue one request at the time by now, monitoring _sent
        if not self._sent:
          logger.debug("run_dbus_async %s", cmd)
          if self.__async_thread and self.__async_thread.is_alive():
            logger.warning("run_dbus_async main loop running %s - probably last request is not terminated yet", self.__async_thread.is_alive())
          # We enqueue one request at the time by now, monitoring _sent
          self._sent = True

          # let's pass also args, it could be useful for debug at certain point...
          self._data = {'cmd': cmd, 'args': args, }

          data = self._data

          self.__async_thread = threading.Thread(target=self.__async_thread_loop, args=(data, *args))
          self.__async_thread.start()
        else:
          logger.warning("run_dbus_async %s, previous command %s in progress %s, loop running %s", cmd, self._data['cmd'], self._sent, self.__async_thread.is_alive())
          result = {
            'result': False,
            'error': _("Command in progress"),
          }

          self.eventQueue.put({'event': cmd, 'value': result})
          logger.debug("Command %s executed, result %s "%(cmd, result))


    def _run_dbus_sync(self, cmd, *args):
        '''Make a sync call to a DBus method in the yumdaemon service
        cmd:
        '''
        logger.debug("_run_dbus_sync %s", cmd)
        proxy = self.Proxy(cmd)

        func = getattr(proxy, self.proxyMethod[cmd])
        return func(*args)

    def waitForLastAsyncRequestTermination(self):
      '''
      join async thread
      '''
      self.__async_thread.join()

#
# Dbus Signal Handlers
#

    def on_DownloadStart(self, session_object_path, download_id, description, total_to_download):
        '''
            Starting a new download batch
            Args:
                session_object_path: object path of the dnf5daemon session
                download_id: unique id of downloaded object (repo or package)
                description: the description of the downloaded object
                total_to_download: total bytes to download

        '''

        self.eventQueue.put({'event': 'OnDownloadStart',
                             'value': {
                                 'session_object_path': unpack_dbus(session_object_path),
                                 'download_id': unpack_dbus(download_id),
                                 'description': unpack_dbus(description),
                                 'total_to_download': unpack_dbus(total_to_download)
                                 }
                            })

    def on_DownloadProgress(self, session_object_path, download_id, total_to_download, downloaded):
        '''
            Progress in downloading.
            Args:
                session_object_path: object path of the dnf5daemon session
                download_id: unique id of downloaded object (repo or package)
                total_to_download: total bytes to download
                downloaded: bytes already downloaded
        '''

        self.eventQueue.put({'event': 'OnDownloadProgress',
                             'value': {
                                 'session_object_path':unpack_dbus(session_object_path),
                                 'download_id':unpack_dbus(download_id),
                                 'total_to_download':unpack_dbus(total_to_download),
                                 'downloaded':unpack_dbus(downloaded),
                                 }
                            })

    def on_DownloadEnd(self, session_object_path, download_id, status, error):
        '''
            Downloading has ended.
            Args:
                session_object_path: object path of the dnf5daemon session
                download_id: unique id of downloaded object (repo or package)
                status: libdnf5::repo::DownloadCallbacks::TransferStatus (0 - successful, 1 - already exists, 2 - error)
                error: error message in case of failed download
        '''
        self.eventQueue.put({'event': 'OnDownloadEnd',
                             'value': {
                                 'session_object_path':unpack_dbus(session_object_path),
                                 'download_id':unpack_dbus(download_id),
                                 'status':unpack_dbus(status),
                                 'error':unpack_dbus(error),
                                 }
                             })

    #TODO fix next signals
    def on_TransactionEvent(self, event, data):
        self.eventQueue.put({'event': 'OnTransactionEvent',
                             'value':
                               {'event':event,
                                'data':data,  }})

    def on_RPMProgress(self, package, action, te_current, te_total, ts_current, ts_total):
        self.eventQueue.put({'event': 'OnRPMProgress',
                             'value':
                               {'package':package,
                                'action':action,
                                'te_current':te_current,
                                'te_total':te_total,
                                'ts_current':ts_current,
                                'ts_total':ts_total,}})

    def on_GPGImport(self, pkg_id, userid, hexkeyid, keyurl, timestamp):
        self.eventQueue.put({'event': 'OnGPGImport',
                             'value':
                               {'pkg_id':pkg_id,
                                'userid':userid,
                                'hexkeyid':hexkeyid,
                                'keyurl':keyurl,
                                'timestamp':timestamp,}})

    def on_RepoMetaDataProgress(self, name, frac):
        ''' Repository Metadata Download progress '''
        self.eventQueue.put({'event': 'OnRepoMetaDataProgress', 'value': {'name':name, 'frac':frac, }})

    def on_ErrorMessage(self, msg):
        ''' Error message from daemon service '''
        self.eventQueue.put({'event': 'OnErrorMessage', 'value': {'msg':msg,  }})


#
# API to proxy
#
    def Proxy(self, cmd) :
        ''' return the proxy interface that manages the given command '''
        if cmd == 'GetPackages' or cmd == 'GetAttribute' or \
           cmd == 'Search':
          return self.iface_rpm
        elif cmd == 'GetRepositories':
            return self.iface_repo
        elif cmd == 'SetEnabledRepos' or cmd == 'SetDisabledRepos':
            return  self.iface_repoconf
        elif cmd == 'ExpireCache':
            return self.iface_base

        return None


#
# API Methods
#

    def GetPackages(self, options, sync=False):
        '''
          Get a list of pkg list for a given option

          Args:
            options: an array of key/value pairs
              Following options and filters are supported:
                package_attrs: list of strings
                    list of package attributes that are returned
                with_nevra: bool (default true)
                    match patterns against available packages NEVRAs
                with_provides: bool (default true)
                    match patterns against available packages provides
                with_filenames: bool (default true)
                    match patterns against names of the files in available packages
                with_binaries: bool (default true)
                    match patterns against names of the binaries in /usr/(s)bin in available packages
                with_src: bool (default true)
                    include source rpms into the results
                icase: bool (default true)
                    ignore case while matching patterns
                patterns: list of strings
                    any package matching to any of patterns is returned
                scope: string (default “all”)
                    limit packages to one of “all”, “installed”, “available”, “upgrades”, “upradable”
                arch: list of strings
                    limit the resulting set only to packages of given architectures
                repo: list of strings
                    limit the resulting set only to packages from given repositories
                latest-limit: int
                    limit the resulting set to only <limit> of latest packages for every name and architecture
                whatprovides: list of strings
                    limit the resulting set only to packages that provide any of given capabilities
                whatdepends: list of strings
                    limit the resulting set only to packages that require, enhance, recommend, suggest or supplement any of given capabilities
                whatrequires: list of strings
                    limit the resulting set only to packages that require any of given capabilities
                whatrecommends: list of strings
                    limit the resulting set only to packages that recommend any of given capabilities
                whatenhances: list of strings
                    limit the resulting set only to packages that enhance any of given capabilities
                whatsuggests: list of strings
                    limit the resulting set only to packages that suggest any of given capabilities
                whatsupplements: list of strings
                    limit the resulting set only to packages that supplement any of given capabilities
                whatobsoletes: list of strings
                    limit the resulting set only to packages that obsolete any of given capabilities
                whatconflicts: list of strings
                    limit the resulting set only to packages that conflict with any of given capabilities
        '''
        if not sync:
          self._run_dbus_async(
              'GetPackages', options)
        else:
          result = self._run_dbus_sync(
              'GetPackages', options)
          return unpack_dbus(result)

    def GetAttribute(self, full_nevra, attr, sync=False):
        '''Get package attribute (description, files, changelogs etc)

        Args:
            full_nevra: package full nevra information
            attr: name of attribute to get
              following attribute are allowed:
                "name",
                "epoch",
                "version",
                "release",
                "arch",
                "repo_id",
                "from_repo_id",
                "is_installed",
                "install_size",
                "download_size",
                "sourcerpm",
                "summary",
                "url",
                "license",
                "description",
                "files",
                "changelogs",
                "provides",
                "requires",
                "requires_pre",
                "conflicts",
                "obsoletes",
                "recommends",
                "suggests",
                "enhances",
                "supplements",
                "evr",
                "nevra",
                "full_nevra",
                "reason",
                "vendor",
                "group",
        '''
        options = {
          "package_attrs": [ attr ],
          "scope": "all",
          "patterns": [full_nevra]
        }

        if not sync:
          self._run_dbus_async('GetAttribute', options)
        else:
          result = self._run_dbus_sync('GetAttribute', options)
          return unpack_dbus(result)[0][attr] if result else None

    def Search(self, options, sync=False):
        '''Search for packages where keys is matched in fields

        Args:
            options: dnf5daeon options for list method except
                     for package attributes (package_attrs) that is overwritten

        Returns:
            list of pkg_id's
        '''

        options['package_attrs'] = [
            "name",
            "epoch",
            "version",
            "release",
            "arch",
            "repo_id",
        ]
        if not sync:
          self._run_dbus_async('Search', options)
        else:
          result = self._run_dbus_sync('Search', options)
          pkg_ids = [dnfdragora.misc.to_pkg_id(p["name"], p["epoch"], p["version"], p["release"],p["arch"], p["repo_id"]) for p in unpack_dbus(result)]
          return pkg_ids

# TODO old Search remind some parameters not present in dnf5daemon
#      def Search(self, fields, keys, attrs, match_all, newest_only, tags):
#        pass

    def GetRepositories(self, patterns=["*"], repo_attrs=["id", "name", "enabled"], enable_disable="all", sync=False):
        '''Get a list of repository where id matches with any of the given patterns

        Args:
            patterns: list of strings
                any repository with id matching to any of patterns is returned
            repo_attrs: list of strings
                list of repository attributes that are returned
                    Possible values are:
                        "id"
                        "name"
                        "type"
                        "enabled"
                        "priority"
                        "cost"
                        "baseurl"
                        "metalink"
                        "mirrorlist"
                        "metadata_expire"
                        "cache_updated"
                        "excludepkgs"
                        "includepkgs"
                        "skip_if_unavailable"
                        "gpgkey"
                        "gpgcheck"
                        "repo_gpgcheck"
                        "proxy"
                        "proxy_username"
                        "proxy_password"
                        "repofile"
                        "revision"
                        "content_tags"
                        "distro_tags"
                        "updated"
                        "size"
                        "pkgs"
                        "available_pkgs"
                        "mirrors"

            enable_disable: string (default “enabled”)
                When set to “enabled” or “disabled”, only enabled / disabled repositories are listed. Any other value means all repositories are returned.

        Returns:
            list of repositories with the requested attributes
        '''
        options = {
            "repo_attrs": repo_attrs,
            "enable_disable": enable_disable,
            "patterns" : patterns
        }

        if not sync:
          self._run_dbus_async('GetRepositories', options)
        else:
          result = self._run_dbus_sync('GetRepositories', options)
          return unpack_dbus(result)


    def SetEnabledRepos(self, repo_ids, sync=False):
        '''Enabled a list of repositories

        Args:
            repo_ids: list of repo ids to enable
        '''
        if not sync:
          self._run_dbus_async('SetEnabledRepos', repo_ids)
        else:
          result = self._run_dbus_sync('SetEnabledRepos', repo_ids)
          return unpack_dbus(result)

    def SetDisabledRepos(self, repo_ids, sync=False):
        '''Disabled a list of repositories

        Args:
            repo_ids: list of repo ids to disable
        '''
        if not sync:
          self._run_dbus_async('SetDisabledRepos', repo_ids)
        else:
          result = self._run_dbus_sync('SetDisabledRepos', repo_ids)
          return unpack_dbus(result)

    def ExpireCache(self, sync=False):
        '''
            Explicitely ask for loading repositories metadata.Expire the dnf metadata,
            so they will be refresed

            retval:
                `true` if repositories were successfuly loaded, `false` otherwise.
        '''
        if not sync:
          self._run_dbus_async('ExpireCache')
        else:
          result = self._run_dbus_sync('ExpireCache')
          return unpack_dbus(result)


#----------- TODO move to new methods --------------------------------------------------

    def SetWatchdogState(self, state, sync=False):
        '''Set the Watchdog state

        Args:
            state: True = Watchdog active, False = Watchdog disabled
        '''
        try:
          if not sync:
            self._run_dbus_async('SetWatchdogState', "(b)", state)
          else:
            self._run_dbus_sync('SetWatchdogState', "(b)", state)
          #self.daemon.SetWatchdogState("(b)", state)
        except Exception as err:
            self._handle_dbus_error(err)


    def GetConfig(self, setting, sync=False):
        '''Read a config setting from yum.conf

        Args:
            setting: setting to read
        '''
        if not sync:
          self._run_dbus_async('GetConfig', '(s)', setting)
        else:
          result = self._run_dbus_sync('GetConfig', '(s)', setting)
          return json.loads(result)

    def GetGroups(self, sync=False):
        '''Get list of Groups. '''
        if not sync:
          self._run_dbus_async('GetGroups')
        else:
          result = self._run_dbus_sync('GetGroups')
          return json.loads(result)


    def GetGroupPackages(self, grp_id, grp_flt, fields, sync=False):
        '''Get packages in a group

        Args:
            grp_id: the group id to get packages for
            grp_flt: the filter ('all' = all packages ,
                     'default' = packages to be installed, before
                     the group is installed)
            fields: extra package attributes to include in result
        '''
        if not sync:
          self._run_dbus_async('GetGroupPackages', '(ssas)',
                          grp_id, grp_flt, fields)
        else:
          result = self._run_dbus_sync('GetGroupPackages', '(ssas)',
                          grp_id, grp_flt, fields)
          return json.loads(result)


    def Exit(self, sync=True):
      '''End the daemon'''
      if not sync:
        self._run_dbus_async('Exit')
      else:
        self._run_dbus_sync('Exit')

#
# Helper methods
#

    def to_pkg_tuple(self, id):
        ''' split the pkg_id into a tuple'''
        (n, e, v, r, a, repo_id) = str(id).split(',')
        return (n, e, v, r, a, repo_id)

    def to_txmbr_tuple(self, id):
        ''' split the txmbr_id into a tuple'''
        (n, e, v, r, a, repo_id, ts_state) = str(id).split(',')
        return (n, e, v, r, a, repo_id, ts_state)


class Client(DnfDaemonBase):
    '''A class to communicate with the dnfdaemon DBus services in a easy way
    '''

    def __init__(self):
        DnfDaemonBase.__init__(self)

    def handle_dbus_signals(self, proxy, sender, signal, args):
        ''' DBUS signal Handler '''
        if signal == "TransactionEvent":
            self.on_TransactionEvent(*args)
        elif signal == "RPMProgress":
            self.on_RPMProgress(*args)
        elif signal == "GPGImport":
            self.on_GPGImport(*args)
        elif signal == "DownloadStart":
            self.on_DownloadStart(*args)
        elif signal == "DownloadEnd":
            self.on_DownloadEnd(*args)
        elif signal == "DownloadProgress":
            self.on_DownloadProgress(*args)
        elif signal == "RepoMetaDataProgress":
            self.on_RepoMetaDataProgress(*args)
        elif signal == "ErrorMessage":
            self.on_ErrorMessage(*args)
        else:
            logger.error("Unhandled Signal : " + signal, " Param: ", args)

#
# API Methods
#

    def SetConfig(self, setting, value, sync=False):
        '''Set a dnf config setting

        Args:
            setting: yum conf setting to set
            value: value to set
        '''
        if not sync:
          self._run_dbus_async(
              'SetConfig', '(ss)', setting, json.dumps(value))
        else:
          return self._run_dbus_sync(
              'SetConfig', '(ss)', setting, json.dumps(value))

    def ClearTransaction(self, sync=False):
        '''Clear the current transaction. '''
        if not sync:
          self._run_dbus_async('ClearTransaction')
        else:
          return self._run_dbus_sync('ClearTransaction')

    def GetTransaction(self, sync=False):
        '''Get the current transaction

        Returns:
            the current transaction
        '''
        if not sync:
          self._run_dbus_async('GetTransaction')
        else:
          result = self._run_dbus_sync('GetTransaction')
          return json.loads(result)

    def AddTransaction(self, id, action, sync=False):
        '''Add an package to the current transaction

        Args:
            id: package id for the package to add
            action: the action to perform ( install, update, remove,
                    obsolete, reinstall, downgrade, localinstall )
        '''
        if not sync:
          self._run_dbus_async('AddTransaction', '(ss)', id, action)
        else:
          result = self._run_dbus_sync('AddTransaction', '(ss)', id, action)
          return json.loads(result)

    def GroupInstall(self, pattern, sync=False):
        '''Do a group install <pattern string>,
        same as dnf group install <pattern string>

        Args:
            pattern: group pattern to install
        '''
        if not sync:
          self._run_dbus_async('GroupInstall', '(s)', pattern)
        else:
          result = self._run_dbus_sync('GroupInstall', '(s)', pattern)
          return json.loads(result)

    def GroupRemove(self, pattern, sync=False):
        '''
        Do a group remove <pattern string>,
        same as dnf group remove <pattern string>

        Args:
            pattern: group pattern to remove
        '''
        if not sync:
          self._run_dbus_async('GroupRemove', '(s)', pattern)
        else:
          result = self._run_dbus_sync('GroupRemove', '(s)', pattern)
          return json.loads(result)


    def Install(self, pattern, sync=False):
        '''Do a install <pattern string>,
        same as dnf install <pattern string>

        Args:
            pattern: package pattern to install
        '''
        if not sync:
          self._run_dbus_async('Install', '(s)', pattern)
        else:
          result = self._run_dbus_sync('Install', '(s)', pattern)
          return json.loads(result)

    def Remove(self, pattern, sync=False):
        '''Do a install <pattern string>,
        same as dnf remove <pattern string>

        Args:
            pattern: package pattern to remove
        '''
        if not sync:
          self._run_dbus_async('Remove', '(s)', pattern)
        else:
          result = self._run_dbus_sync('Remove', '(s)', pattern)
          return json.loads(result)

    def Update(self, pattern, sync=False):
        '''Do a update <pattern string>,
        same as dnf update <pattern string>

        Args:
            pattern: package pattern to update

        '''
        if not sync:
          self._run_dbus_async('Update', '(s)', pattern)
        else:
          result = self._run_dbus_sync('Update', '(s)', pattern)
          return json.loads(result)

    def Reinstall(self, pattern, sync=False):
        '''Do a reinstall <pattern string>,
        same as dnf reinstall <pattern string>

        Args:
            pattern: package pattern to reinstall

        '''
        if not sync:
          self._run_dbus_async('Reinstall', '(s)', pattern)
        else:
          result = self._run_dbus_sync('Reinstall', '(s)', pattern)
          return json.loads(result)

    def Downgrade(self, pattern, sync=False):
        '''Do a install <pattern string>, same as yum remove <pattern string>

        Args:
            pattern: package pattern to downgrade
        '''
        if not sync:
          self._run_dbus_async('Downgrade', '(s)', pattern)
        else:
          result = self._run_dbus_sync('Downgrade', '(s)', pattern)
          return json.loads(result)

    def BuildTransaction(self, sync=False):
        '''Get a list of pkg ids for the current availabe updates '''
        if not sync:
          self._run_dbus_async('BuildTransaction')
        else:
          result = self._run_dbus_sync('BuildTransaction')
          return json.loads(result)

    def RunTransaction(self, sync=False):
        ''' Get a list of pkg ids for the current availabe updates

        Args:
            max_err: maximun number of download error before we bail out
        '''
        if not sync:
          self._run_dbus_async('RunTransaction')
        else:
          result = self._run_dbus_sync('RunTransaction')
          return json.loads(result)

    def GetHistoryByDays(self, start_days, end_days, sync=False):
        '''Get History transaction in a interval of days from today

        Args:
            start_days: start of interval in days from now (0 = today)
            end_days:end of interval in days from now

        Returns:
            list of (transaction is, date-time) pairs
        '''
        if not sync:
          self._run_dbus_async('GetHistoryByDays', '(ii)', start_days, end_days)
        else:
          result = self._run_dbus_sync('GetHistoryByDays', '(ii)', start_days, end_days)
          return json.loads(result)

    def HistorySearch(self, pattern, sync=False):
        '''Search the history for transaction matching a pattern

        Args:
            pattern: patterne to match

        Returns:
            list of (tid,isodates)
        '''
        if not sync:
          self._run_dbus_async('HistorySearch', '(as)', pattern)
        else:
          result = self._run_dbus_sync('HistorySearch', '(as)', pattern)
          return json.loads(result)

    def GetHistoryPackages(self, tid, sync=False):
        '''Get packages from a given yum history transaction id

        Args:
            tid: history transaction id

        Returns:
            list of (pkg_id, state, installed) pairs
        '''
        if not sync:
          self._run_dbus_async('GetHistoryPackages', '(i)', tid)
        else:
          result = self._run_dbus_sync('GetHistoryPackages', '(i)', tid)
          return json.loads(result)

    def HistoryUndo(self, tid, sync=False):
        """Undo a given dnf history transaction id

        Args:
            tid: history transaction id

        Returns:
            (rc, messages)
        """
        if not sync:
          self._run_dbus_async('HistoryUndo', '(i)', tid)
        else:
          result = self._run_dbus_sync('HistoryUndo', '(i)', tid)
          return json.loads(result)



    def ConfirmGPGImport(self, hexkeyid, confirmed, sync=False):
        '''Confirm import of at GPG Key by yum

        Args:
            hexkeyid: hex keyid for GPG key
            confirmed: confirm import of key (True/False)
        '''
        if not sync:
          self._run_dbus_async('ConfirmGPGImport', '(si)', hexkeyid, confirmed)
        else:
          self._run_dbus_sync('ConfirmGPGImport', '(si)', hexkeyid, confirmed)
