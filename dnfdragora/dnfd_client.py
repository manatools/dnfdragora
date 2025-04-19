'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Angelo Naselli <anaselli@linux.it>

@package dnfdragora

This module implements the interface to dnf5daemon dbus APIs

'''

import dbus
import json # needed for list_fd
import sys
import re
import weakref
import logging
import threading
import os
import select
import libdnf5
import locale
from queue import SimpleQueue, Empty

import dnfdragora.misc

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


class Client:

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

        # 60 secs without receiving anything during a transaction
        self.__TransactionTimer = dnfdragora.misc.TimerEvent(60, self.on_TransactionTimeoutEvent)
        self.__TransactionTimer.AutoRpeat = False

        self.proxyMethod = {
          'ExpireCache'         : 'read_all_repos',

          'GetPackages'         : 'list_fd',
          #'GetPackages'         : 'list', WARNING list often hangs for big data through dbus, use list_fd
          'GetAttribute'        : 'list',
          'Search'              : 'list',
          'Install'             : 'install',
          'Remove'              : 'remove',
          'Update'              : 'upgrade',
          'Downgrade'           : 'downgrade',
          'Reinstall'           : 'reinstall',
          'Install'             : 'install',
          'DistroSync'          : 'distro_sync',

          'SetEnabledRepos'     : 'enable',
          'SetDisabledRepos'    : 'disable',

          'GetRepositories'     : 'list',
          'ConfirmGPGImport'    : 'confirm_key',

          'Advisories'          : 'list',

          #Goal
          'BuildTransaction'    : 'resolve',
          'RunTransaction'      : 'do_transaction',
          'TransactionProblems' : 'get_transaction_problems_string',
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


            # Managing dnf5daemon signals
            self.iface_base.connect_to_signal("download_add_new", self.on_DownloadStart)
            self.iface_base.connect_to_signal("download_progress", self.on_DownloadProgress)
            self.iface_base.connect_to_signal("download_end", self.on_DownloadEnd)
            self.iface_base.connect_to_signal("download_mirror_failure", self.on_ErrorMessage)
            self.iface_base.connect_to_signal("repo_key_import_request", self.on_GPGImport)

            '''
                transaction event sequence example (see https://github.com/rpm-software-management/dnf5/issues/1189)
                This is for example how signals for dnf5 upgrade acpi currently look like:

                # 1. verification of incomming packages (thus only 1 item)
                verify start, total 1
                verify stop, total 1

                # 2. preparation of transaction with two items (uninstall the old version, install the new one)
                transaction start, total 2
                transaction stop, total 2

                # 3. now the items are processed
                install start "acpi-0:1.7-21.fc39.x86_64" total 54172
                install stop "acpi-0:1.7-21.fc39.x86_64" amount 54172 total 54172
                uninstall start "acpi-0:1.7-11.fc30.x86_64" total 10
                uninstall stop "acpi-0:1.7-11.fc30.x86_64" amount 10 total 10

                # 4. and finally scriptlets
                start trigger-install scriptlet "glibc-common-0:2.38-16.fc39.x86_64"
                stop trigger-install scriptlet "glibc-common-0:2.38-16.fc39.x86_64" return code 0
                start trigger-install scriptlet "man-db-0:2.11.2-5.fc39.x86_64"
                stop trigger-install scriptlet "man-db-0:2.11.2-5.fc39.x86_64" return code 0
                start trigger-post-uninstall scriptlet "man-db-0:2.11.2-5.fc39.x86_64"
                stop trigger-post-uninstall scriptlet "man-db-0:2.11.2-5.fc39.x86_64" return code 0

                From dnf5 5.2.0.0 steps added:

                # 0. transaction has begun
                overall_transaction start, total 2 ("transaction_before_begin")

                # 5. transaction has finished
                overall_transaction stop ("transaction_after_complete")
            '''
            self.iface_rpm.connect_to_signal("transaction_unpack_error", self.on_TransactionUnpackError)

            self.iface_rpm.connect_to_signal("transaction_before_begin", self.on_TransactionBeforeBegin)

            self.iface_rpm.connect_to_signal("transaction_elem_progress", self.on_TransactionElemProgress)

            self.iface_rpm.connect_to_signal("transaction_verify_start", self.on_TransactionVerifyStart)
            self.iface_rpm.connect_to_signal("transaction_verify_progress", self.on_TransactionVerifyProgress)
            self.iface_rpm.connect_to_signal("transaction_verify_stop", self.on_TransactionVerifyStop)

            self.iface_rpm.connect_to_signal("transaction_action_start", self.on_TransactionActionStart)
            self.iface_rpm.connect_to_signal("transaction_action_progress", self.on_TransactionActionProgress)
            self.iface_rpm.connect_to_signal("transaction_action_stop", self.on_TransactionActionStop)

            self.iface_rpm.connect_to_signal("transaction_transaction_start", self.on_TransactionTransactionStart)
            self.iface_rpm.connect_to_signal("transaction_transaction_progress", self.on_TransactionTransactionProgress)
            self.iface_rpm.connect_to_signal("transaction_transaction_stop", self.on_TransactionTransactionStop)

            self.iface_rpm.connect_to_signal("transaction_script_start", self.on_TransactionScriptStart)
            self.iface_rpm.connect_to_signal("transaction_script_stop", self.on_TransactionScriptStop)
            self.iface_rpm.connect_to_signal("transaction_script_error", self.on_TransactionScriptError)

            self.iface_rpm.connect_to_signal("transaction_after_complete", self.on_TransactionAfterComplete)

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
          elif user_data['cmd'] == 'BuildTransaction':
              resolved, res = user_data['result']
              result['result'] = (unpack_dbus(res), unpack_dbus(resolved))
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
      Thread function for GLib main loop to handle D-Bus calls with timeouts.
      '''
      logger.debug("__async_thread_loop Command %s(%s) requested ", str(data['cmd']), repr(args) if args else "")
      proxy = self.Proxy(data['cmd'])
      method = self.proxyMethod[data['cmd']]
      logger.debug("__async_thread_loop proxy %s method %s", proxy.dbus_interface, method)
      pipe_r, pipe_w = None, None

      try:
          # Create a new GLib main loop for this thread
          loop = GLib.MainLoop()#GLib.MainContext.ref_thread_default())

          def on_error(error):
              # Handle D-Bus error
              logger.error("__async_thread_loop error for command %s: %s", data['cmd'], error)
              if method == 'list_fd':
                if pipe_r is not None:
                    os.close(pipe_r)
                if pipe_w is not None:
                    os.close(pipe_w)

              self._return_handler(error, data)             
              # Usa GLib.idle_add per chiamare loop.quit() nel contesto corretto
              GLib.idle_add(loop.quit)            
              #logger.debug("... on_error quit")

          func = getattr(proxy, method)
          if data['return_value']:
            # TODO find a better way to distinguish if cmd needs a pipe
            if method == 'list_fd':
                # create a pipe and pass the write end to the server
                pipe_r, pipe_w = os.pipe()

                def on_list_id_success(rpipe_idesult):
                    # Handle successful D-Bus call
                    logger.debug("__async_thread_loop success for command %s", data['cmd'])
                    # close the write end
                    os.close(pipe_w)
                    # read the data
                    timeout = 1000 # 1 second timeout seems to be enough
                    buffer_size = 65536
                    poller = select.poll()
                    poller.register(pipe_r, select.POLLIN | select.POLLHUP)
                    read_finished = False
                    parser = json.JSONDecoder()
                    to_parse = ""                
                    pkglist = []
                    try:
                        while (not read_finished):
                            polled_event = poller.poll(timeout)
                            if not polled_event:
                                logger.warning("__async_thread_loop(list_fd): timeout reached while reading from pipe.")
                                break
                            for descriptor, event in polled_event:
                                if event & select.POLLIN:
                                    buffer = os.read(descriptor, buffer_size).decode()                                    
                                    if buffer:
                                        to_parse += buffer
                                        while to_parse:
                                            try:
                                                obj, end = parser.raw_decode(to_parse)
                                                pkglist.append(obj)
                                                to_parse = to_parse[end:].strip()
                                            except json.decoder.JSONDecodeError:
                                                logger.error("__async_thread_loop(list_fd): JSONDecodeError while parsing buffer")                                                             
                                                # TODO - handle unfinished strings correctly
                                                # current example implementation just tries to parse once again when
                                                # more data arrive.
                                                break
                                    else:
                                        logger.debug("__async_thread_loop(list_fd): no more data to read from pipe.")
                                        read_finished = True
                                elif event & select.POLLHUP:
                                    logger.debug("__async_thread_loop(list_fd): pipe closed by the writer.")
                                    read_finished = True
                    except Exception as err:
                        logger.error("__async_thread_loop(list_fd): Exception while reading from pipe: %s", err)
                        read_finished = True
                    finally:
                        os.close(pipe_r)
                        logger.debug("__async_thread_loop(list_fd): pipe closed.")

                    self._return_handler(pkglist, data)
                    # Usa GLib.idle_add per chiamare loop.quit() nel contesto corretto
                    GLib.idle_add(loop.quit)
                    #logger.debug("__async_thread_loop(list_fd): loop quit")
                func(*args, pipe_w, reply_handler=on_list_id_success, error_handler=on_error, timeout=600)                
            else: 
              def on_success(*result):
                logger.debug("__async_thread_loop success for command %s with result: %s", str(data['cmd']), repr(result))                
                if len(result) == 1:  # True if there are one or more values
                  self._return_handler(unpack_dbus(result[0]), data)
                elif len(result) == 2:  # True if there are one or more values
                  self._return_handler((unpack_dbus(result[0]), unpack_dbus(result[1])), data)
                elif len(result) > 2:  # True if there are one or more values
                  logger.warning("__async_thread_loop some return values are not managed")
                # Usa GLib.idle_add per chiamare loop.quit() nel contesto corretto
                GLib.idle_add(loop.quit)
                #logger.debug("... on_success quit")

              # Use asynchronous D-Bus call with success and error handlers
              func(*args, reply_handler=on_success, error_handler=on_error, timeout=600)
          else:
              def on_success_novalue():
                # Handle successful D-Bus call
                logger.debug("__async_thread_loop.on_success_novalue success for command %s", str(data['cmd']))
                # Usa GLib.idle_add per chiamare loop.quit() nel contesto corretto
                GLib.idle_add(loop.quit)
                #logger.debug("... __async_thread_loop.on_success_novalue quit")
              func(*args, reply_handler=on_success_novalue, error_handler=on_error, timeout=600)
          # Run the GLib main loop to process D-Bus events
          # Add a timeout to force quit the loop if necessary
          GLib.timeout_add_seconds(10, lambda: loop.quit())
          loop.run()
      except Exception as err:
          logger.error("__async_thread_loop (%s) proxy %s, method %s - Exception %s", str(data['cmd']), proxy.dbus_interface, method, err)
          self._return_handler(err, data)
          if pipe_r is not None:
             os.close(pipe_r)
          if pipe_w is not None:
             os.close(pipe_w)
          logger.debug("__async_thread_loop.Exception quit ...")
          # Usa GLib.idle_add per chiamare loop.quit() nel contesto corretto
          GLib.idle_add(loop.quit)          
          #logger.debug("... __async_thread_loop.Exception quit")
          # Close the pipe            

      # Mark the request as completed
      self._sent = False
      logger.debug("__async_thread_loop quit %s", str(data['cmd']))

    def _run_dbus_async(self, cmd, return_value, *args):
        '''Make an async call to a DBus method in the yumdaemon service

        cmd: method to run
        '''
        # We enqueue one request at the time by now, monitoring _sent
        if not self._sent:
          logger.debug("run_dbus_async %s (return=%d) args: (%s)", cmd, return_value, repr(args) if args else "")
          if self.__async_thread and self.__async_thread.is_alive():
            logger.warning("run_dbus_async main loop running %s - probably last request is not terminated yet", self.__async_thread.is_alive())
          # We enqueue one request at the time by now, monitoring _sent
          self._sent = True

          # let's pass also args, it could be useful for debug at certain point...
          self._data = {'cmd': cmd, 'return_value': return_value, 'args': args, }

          data = self._data
          self.__async_thread = threading.Thread(target=self.__async_thread_loop, args=(data, *args), daemon=True)
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
        logger.debug("_run_dbus_sync %s - args: (%s)", cmd, repr(args) if args else "")
        proxy = self.Proxy(cmd)

        func = getattr(proxy, self.proxyMethod[cmd])

        return_value = None

        # TODO find a better way to distinguish if cmd needs a pipe
        #if cmd == 'GetPackages':
        if func == 'list_fd':
            # create a pipe and pass the write end to the server
            pipe_r, pipe_w = os.pipe()
            pipe_id = func(*args, pipe_w)
            # close the write end
            os.close(pipe_w)

            # read the data
            timeout = 10000
            buffer_size = 65536
            poller = select.poll()
            poller.register(pipe_r, select.POLLIN)
            read_finished = False
            parser = json.JSONDecoder()
            to_parse = ""
            pkglist = []
            while (not read_finished):
                polled_event = poller.poll(timeout)
                if not polled_event:
                    print("Timeout reached.")
                    break
                for descriptor, event in polled_event:
                    buffer = os.read(descriptor, buffer_size).decode()
                    if (len(buffer) > 0):
                        to_parse += buffer
                        while to_parse:
                            try:
                                obj, end = parser.raw_decode(to_parse)
                                pkglist.append(obj)
                                to_parse = to_parse[end:].strip()
                            except json.decoder.JSONDecodeError:
                                # TODO - handle unfinished strings correctly
                                # current example implementation just tries to parse once again when
                                # more data arrive.
                                break
                    else:
                        read_finished = True

            os.close(pipe_r)
            return_value = pkglist
        else:
            return_value = func(*args)

        return return_value

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
            Signal download_add_new - Starting a new download batch
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
            Signal download_progress - Progress in downloading.
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
            Signal download_end - Downloading has ended.
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

    def on_ErrorMessage(self, session_object_path, download_id, message, url, metadata):
        '''
            Signal mirror_failure - Mirror failure during the download.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @download_id: unique id of downloaded object (repo or package)
                @message: an error message
                @url: URL being downloaded
                @metadata: For repository metadata download contains metadata type
        '''
        self.eventQueue.put({'event': 'OnErrorMessage',
                             'value': {
                                 'session_object_path':unpack_dbus(session_object_path),
                                 'download_id':unpack_dbus(download_id),
                                 'error':unpack_dbus(message),
                                 'url':unpack_dbus(url),
                                 'metadata':unpack_dbus(metadata),
                                 }
                            })

    def on_GPGImport(self, session_object_path, key_id, user_ids, key_fingerprint, key_url, timestamp):
        '''
            Signal repo_key_import_request - Request for repository key import confirmation.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @key_id: PGP key id
                @user_ids: User id
                @key_fingerprint: Fingerprint of the PGP key
                @key_url: URL of the PGP key
                @timestamp: timestamp when the key was created
        '''
        self.eventQueue.put({'event': 'OnGPGImport',
                             'value': {
                                 'session_object_path':session_object_path,
                                 'key_id':key_id,
                                 'user_ids':user_ids,
                                 'key_fingerprint':key_fingerprint,
                                 'key_url':key_url,
                                 'timestamp':timestamp,
                                 }
                             })

    def on_TransactionTimeoutEvent(self):
        '''
            Sent right after the rpm transaction run finished.

            Args:
                @session_object_path: object path of the dnf5daemon session1
                @success: true if the rpm transaction was completed successfully
        '''
        logger.warning("on_TransactionTimeoutEvent, timer expired")
        # Transaction is probably finished, but timeout expired before
        # gettine TransactionAfterComplete signal, so stopping the timer
        self.__TransactionTimer.cancel()
        self.eventQueue.put({'event': 'OnTransactionTimeoutEvent',
                             'value': None #useless
                             })

    def on_TransactionBeforeBegin(self, *args) :
        logger.debug("on_TransactionBeforeBegin (%s)", repr(args))
        # Start the transaction timer
        self.__TransactionTimer.start()

    def on_TransactionElemProgress(self, session_object_path, nevra, processed, total):
        """
        Overall progress in transaction item processing. Called right before an item is processed.
        Args:
            @session_object_path: object path of the dnf5daemon session
            @nevra: full NEVRA of the package
            @processed: amount already processed (starting from 0, just before it is processed)
            @total: total to process
        """
        # Start the transaction timer
        self.__TransactionTimer.start()
        self.eventQueue.put({'event': 'OnTransactionElemProgress',
                             'value': {
                                 'session_object_path': unpack_dbus(session_object_path),
                                 'nevra': unpack_dbus(nevra),
                                 'processed': unpack_dbus(processed),
                                 'total': unpack_dbus(total),
                                 }
                             })

    def on_TransactionAfterComplete(self,  session_object_path, success) :
        '''
            Sent right after the rpm transaction run finished.

            Args:
                @session_object_path: object path of the dnf5daemon session1
                @success: true if the rpm transaction was completed successfully
        '''
        logger.debug("on_TransactionAfterComplete (%s)", "success" if success else "failed")
        # Transaction is finished stop the timer
        self.__TransactionTimer.cancel()
        self.eventQueue.put({'event': 'OnTransactionAfterComplete',
                             'value': {
                                 'success': success,
                                 }
                             })


    def on_TransactionActionStart(self, session_object_path, nevra, action, total):
        '''
            Processing (installation or removal) of the package has started.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @nevra: full NEVRA of the package
                @action: one of the dnfdaemon::RpmTransactionItem::Actions enum
                @total: total to process
        '''
        # Refresh the transaction timeout
        self.__TransactionTimer.start()
        self.eventQueue.put({'event': 'OnTransactionActionStart',
                             'value': {
                                 'session_object_path': unpack_dbus(session_object_path),
                                 'nevra': unpack_dbus(nevra),
                                 'action': unpack_dbus(action),
                                 'total': unpack_dbus(total),
                                 }
                             })

    def on_TransactionActionProgress(self, session_object_path, nevra, processed, total):
        '''
            Progress in processing of the package.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @nevra: full NEVRA of the package
                @processed: amount already processed
                @total: total to process
        '''
        # Refresh the transaction timeout
        self.__TransactionTimer.start()
        self.eventQueue.put({'event': 'OnTransactionActionProgress',
                             'value': {
                                 'session_object_path': unpack_dbus(session_object_path),
                                 'nevra': unpack_dbus(nevra),
                                 'processed': unpack_dbus(processed),
                                 'total': unpack_dbus(total),
                                 }
                             })

    def on_TransactionActionStop(self, session_object_path, nevra, total):
        '''
            Processing of the item has finished.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @nevra: full NEVRA of the package
                @total: total processed
        '''
        # Refresh the transaction timeout
        self.__TransactionTimer.start()
        self.eventQueue.put({'event': 'OnTransactionActionStop',
                             'value': {
                                 'session_object_path': unpack_dbus(session_object_path),
                                 'nevra': unpack_dbus(nevra),
                                 'total': unpack_dbus(total),
                                 }
                             })

    def on_TransactionTransactionStart(self, session_object_path, total):
        '''
            Preparation of transaction packages has started.
            Manages the transaction_transaction_start signal.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @total: total to process
        '''
        # Refresh the transaction timeout
        self.__TransactionTimer.start()
        self.eventQueue.put({'event': 'OnTransactionTransactionStart',
                             'value': {
                                 'session_object_path': unpack_dbus(session_object_path),
                                  'total': unpack_dbus(total),
                                 }
                             })

    def on_TransactionTransactionProgress(self, session_object_path, processed, total):
        '''
            Progress in preparation of transaction packages.
            Manages the transaction_transaction_progress signal.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @processed: amount already processed
                @total: total to process
        '''
        # Refresh the transaction timeout
        self.__TransactionTimer.start()
        self.eventQueue.put({'event': 'OnTransactionTransactionProgress',
                             'value': {
                                 'session_object_path': unpack_dbus(session_object_path),
                                 'processed': unpack_dbus(processed),
                                 'total': unpack_dbus(total),
                                 }
                             })

    def on_TransactionTransactionStop(self, session_object_path, total):
        '''
            Preparation of transaction packages has finished.
            Manages thetransaction_transaction_stop signal.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @total: total to process
        '''
        # Refresh the transaction timeout
        self.__TransactionTimer.start()
        self.eventQueue.put({'event': 'OnTransactionTransactionStop',
                             'value': {
                                 'session_object_path': unpack_dbus(session_object_path),
                                  'total': unpack_dbus(total),
                                 }
                             })

    #def on_TransactionScriptStart(self, nevra, *args):
    def on_TransactionScriptStart(self, session_object_path, nevra, scriptlet_type):
        '''
        The scriptlet has started.
        Manages the transaction_script_start signal.
        Args:
            @session_object_path: object path of the dnf5daemon session
            @nevra: full NEVRA of the package script belongs to
            @scriptlet_type: scriptlet type that started (pre, post,...)
        '''
        # Refresh the transaction timeout
        self.__TransactionTimer.start()
        self.eventQueue.put({'event': 'OnTransactionScriptStart',
                             'value': {
                                 'session_object_path': unpack_dbus(session_object_path),
                                 'nevra': unpack_dbus(nevra),
                                 'scriptlet_type': unpack_dbus(scriptlet_type),
                                 }
                             })

    def on_TransactionScriptStop(self, session_object_path, nevra, scriptlet_type, return_code):
        '''
            The scriptlet has successfully finished.
            Manages the transaction_script_stop signal.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @nevra: full NEVRA of the package script belongs to
                @scriptlet_type: scriptlet type that started (pre, post,...)
                @return_code: return value of the script
        '''
        # Refresh the transaction timeout
        self.__TransactionTimer.start()
        self.eventQueue.put({'event': 'OnTransactionScriptStop',
                             'value': {
                                 'session_object_path': unpack_dbus(session_object_path),
                                 'nevra': unpack_dbus(nevra),
                                 'scriptlet_type': unpack_dbus(scriptlet_type),
                                 'return_code': unpack_dbus(return_code),
                                 }
                             })

    def on_TransactionScriptError(self, session_object_path, nevra, scriptlet_type, return_code) : # nevra, return_code, ):
        '''
            The scriptlet has finished with an error.
            Manages the transaction_script_error signal.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @nevra: full NEVRA of the package script belongs to
                @scriptlet_type: scriptlet type that started (pre, post,...)
                @return_code: return value of the script
        '''
        # Refresh the transaction timeout
        self.__TransactionTimer.start()
        self.eventQueue.put({'event': 'OnTransactionScriptError',
                             'value': {
                                 'session_object_path': unpack_dbus(session_object_path),
                                 'nevra': unpack_dbus(nevra),
                                 'scriptlet_type': unpack_dbus(scriptlet_type),
                                 'return_code': unpack_dbus(return_code),
                                 }
                             })

    def on_TransactionVerifyStart(self, session_object_path, total) :
        '''
        Package files verification has started.
        Args:
            @session_object_path: object path of the dnf5daemon session
            @total: total to process
        '''
        # Refresh the transaction timeout
        self.__TransactionTimer.start()
        self.eventQueue.put({'event': 'OnTransactionVerifyStart',
                             'value': {
                                 'session_object_path':unpack_dbus(session_object_path),
                                 'total':unpack_dbus(total),
                                 }
                            })

    def on_TransactionVerifyProgress(self, session_object_path, processed, total):
        '''
        Progress in processing of the package.
        Args:
            @session_object_path: object path of the dnf5daemon session
            @processed: amount already processed
            @total: total to process
        '''
       # Refresh the transaction timeout
        self.__TransactionTimer.start()
        self.eventQueue.put({'event': 'OnTransactionVerifyProgress',
              'value': {
                  'session_object_path':unpack_dbus(session_object_path),
                  'processed':unpack_dbus(processed),
                  'total':unpack_dbus(total),
                  }
              })

    def on_TransactionVerifyStop(self, session_object_path, total) :
        '''
        Package files verification has finished
        Args:
            @session_object_path: object path of the dnf5daemon session
            @total: total to process
        '''
        # Refresh the transaction timeout
        self.__TransactionTimer.start()
        self.eventQueue.put({'event': 'OnTransactionVerifyStop',
                      'value': {
                          'session_object_path':unpack_dbus(session_object_path),
                          'total':unpack_dbus(total),
                          }
                      })

    def on_TransactionUnpackError(self, *args) : # nevra):
        '''
            Error while unpacking the package.
            Manages the transaction_unpack_error signal.
            Args:
                @session_object_path: object path of the dnf5daemon session
                @nevra: full NEVRA of the package
        '''
        logger.error("on_TransactionUnpackError (%s)", repr(args))
        self.__TransactionTimer.start()
        #self.eventQueue.put({'event': 'OnTransactionUnpackError',
        #                     'value': {
        #                         'session_object_path':unpack_dbus(session_object_path),
        #                         'nevra': unpack_dbus(nevra),
        #                         }
        #                     })

    ##########TODO fix next signals
    def on_RPMProgress(self, package, action, te_current, te_total, ts_current, ts_total):
        self.eventQueue.put({'event': 'OnRPMProgress',
                             'value':
                               {'package':package,
                                'action':action,
                                'te_current':te_current,
                                'te_total':te_total,
                                'ts_current':ts_current,
                                'ts_total':ts_total,}})


    def on_RepoMetaDataProgress(self, name, frac):
        ''' Repository Metadata Download progress '''
        self.eventQueue.put({'event': 'OnRepoMetaDataProgress', 'value': {'name':name, 'frac':frac, }})

#
# Calls to libdnf5
#
    def __getComps(self):
        '''
            Perform Get groups call it works only for Comps.

            Returns a list of groups
        '''
        base = libdnf5.base.Base()
        base.load_config()
        config = base.get_config()

        types_config = config.get_optional_metadata_types_option()
        types_config.add(libdnf5.conf.Option.Priority_RUNTIME, (libdnf5.conf.METADATA_TYPE_COMPS))

        base.setup()

        repo_sack = base.get_repo_sack()
        repo_sack.create_repos_from_system_configuration()
        repo_sack.update_and_load_enabled_repos(True)

        query = libdnf5.comps.GroupQuery(base)

        # workaround to get_translated_name()
        loc = locale.getlocale()[0].split('_')[0] #let's take the first part of locales

        groups = [ [grp.get_groupid(), grp.get_translated_name(loc)] for grp in query ]
        return groups

    def __getPackageNamesFromGroup(self, groupID):
        '''
            Gets package names from a given group name it works only for Comps.

            Args:
                groupID group name

            Returns a list of package names or an empyty list.
        '''
        base = libdnf5.base.Base()
        base.load_config()
        config = base.get_config()

        types_config = config.get_optional_metadata_types_option()
        types_config.add(libdnf5.conf.Option.Priority_RUNTIME, (libdnf5.conf.METADATA_TYPE_COMPS))

        base.setup()

        repo_sack = base.get_repo_sack()
        repo_sack.create_repos_from_system_configuration()
        repo_sack.update_and_load_enabled_repos(True)

        query = libdnf5.comps.GroupQuery(base)
        query.filter_groupid(groupID)

        comps = [ grp for grp in query ]
        if len(comps):
            packages=[]
            gr = comps[0]
            packages = gr.get_packages()

            return [package.get_name() for package in packages]
        return []


    def __getGroupFromPackage(self, packageNames):
        '''
            Gets package names from a given group name it works only for Comps.

            Args:
                groupID group name

            Returns a list of package names or an empyty list.
        '''
        base = libdnf5.base.Base()
        base.load_config()
        config = base.get_config()

        types_config = config.get_optional_metadata_types_option()
        types_config.add(libdnf5.conf.Option.Priority_RUNTIME, (libdnf5.conf.METADATA_TYPE_COMPS))

        base.setup()

        repo_sack = base.get_repo_sack()
        repo_sack.create_repos_from_system_configuration()
        repo_sack.update_and_load_enabled_repos(True)

        query = libdnf5.comps.GroupQuery(base)
        query.filter_package_name(packageNames)

        comps = [ grp.get_groupid() for grp in query ]
        return comps


#
# API to proxy
#
    def Proxy(self, cmd) :
        ''' return the proxy interface that manages the given command '''
        if cmd == 'GetPackages' or cmd == 'GetAttribute' or \
           cmd == 'Search' or cmd == 'Install' or cmd == 'Remove' or cmd == 'Update' or \
           cmd == 'Reinstall' or cmd == 'Downgrade' or cmd == 'DistroSync':
          return self.iface_rpm
        elif cmd == 'GetRepositories' or cmd == 'ConfirmGPGImport':
            return self.iface_repo
        elif cmd == 'SetEnabledRepos' or cmd == 'SetDisabledRepos':
            return  self.iface_repoconf
        elif cmd == 'Advisories':
            return self.iface_advisory
        elif cmd == 'ExpireCache':
            return self.iface_base
        elif cmd == 'BuildTransaction' or cmd == 'RunTransaction' or cmd == 'TransactionProblems':
            return  self.iface_goal

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
              'GetPackages', True, options)
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
          self._run_dbus_async('GetAttribute', True, options)
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
          self._run_dbus_async('Search', True, options)
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
          self._run_dbus_async('GetRepositories', True, options)
        else:
          result = self._run_dbus_sync('GetRepositories', options)
          return unpack_dbus(result)

    def SetEnabledRepos(self, repo_ids, sync=False):
        '''Enabled a list of repositories

        Args:
            repo_ids: list of repo ids to enable
        '''
        if not sync:
          self._run_dbus_async('SetEnabledRepos', True, repo_ids)
        else:
          result = self._run_dbus_sync('SetEnabledRepos', repo_ids)
          return unpack_dbus(result)

    def SetDisabledRepos(self, repo_ids, sync=False):
        '''Disabled a list of repositories

        Args:
            repo_ids: list of repo ids to disable
        '''
        if not sync:
          self._run_dbus_async('SetDisabledRepos', True, repo_ids)
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
          self._run_dbus_async('ExpireCache', True)
        else:
          result = self._run_dbus_sync('ExpireCache')
          return unpack_dbus(result)

    def ConfirmGPGImport(self, key_id, confirmed, sync=False):
        '''
            confirm_key - Confirm to import the given PGP key
            Args:
                @key_id: id of the key in question
                @confirmed: whether the key import is confirmed by user
        '''
        if not sync:
          self._run_dbus_async('ConfirmGPGImport', False, key_id, confirmed)
        else:
          self._run_dbus_sync('ConfirmGPGImport', key_id, confirmed)

    def Advisories(self, options, sync=False):
        '''
        Get list of security advisories that match to given filters.

        Args:
            @options: an array of key/value pairs
        return:
            @advisories: array of returned advisories with requested attributes

        Following options and filters are supported:
            - advisory_attrs: list of strings
                List of advisory attributes that are returned in `advisories` array.
                Supported attributes are "advisoryid", "name", "title", "type", "severity", "status",
                "vendor", "description", "buildtime", "message", "rights", "collections", and "references".
            - availability: string
                One of "available" (default if filter is not present), "all", "installed", or "updates".
            - name: list of strings
                Consider only advisories with one of given names.
            - type: list of strings
                Consider only advisories of given types. Possible types are "security", "bugfix", "enhancement", and "newpackage".
            - contains_pkgs: list of strings
                Consider only advisories containing one of given packages.
            - severity: list of strings
                Consider only advisories of given severity. Possible values are "critical", "important", "moderate", "low", and "none".
            - reference_bz: list of strings
                Consider only advisories referencing given Bugzilla ticket ID. Exepcted values are numeric IDs, e.g. 123456.
            - reference_cve: list of strings
                Consider only advisoried referencing given CVE ID. Expected values are strings IDs in CVE format, e.g. CVE-2201-0123.
            - with_bz: boolean
                Consider only advisories referencing a Bugzilla ticket.
            - with_cve: boolean
                Consider only advisories referencing a CVE ticket.

        Unknown options are ignored.

        '''
        if not sync:
          self._run_dbus_async(
              'Advisories', True, options)
        else:
          result = self._run_dbus_sync(
              'Advisories', options)
          return unpack_dbus(result)

    def Install(self, specs, options={}, sync=False):
        '''
            Mark packages specified by @specs for installation.
            Args:
                @specs: an array of package specifications to be installed on the system
                @options: an array of key/value pairs to modify install behavior

            Following @options are supported:
                - repo_ids: list of strings
                    Identifiers of the repos from which the packages could be installed.
                - skip_broken: boolean, default false
                    Whether solver can skip packages with broken dependencies to resolve transaction
                - skip_unavailable: boolean, default false
                    Whether nonexisting packages can be skipped.
            Unknown options are ignored.
        '''
        if not sync:
          self._run_dbus_async('Install', False, specs, options)
        else:
          self._run_dbus_sync('Install', specs, options)

    def Remove(self, specs, options={}, sync=False):
        '''
            Mark packages specified by @specs for removal.
            Args:
                @specs: an array of package specifications to be removed on the system
                @options: an array of key/value pairs to modify remove behavior
                Unknown options are ignored.
        '''
        if not sync:
          self._run_dbus_async('Remove', False, specs, options)
        else:
          self._run_dbus_sync('Remove', specs, options)

    def Update(self, specs, options={}, sync=False):
        '''
            Mark packages specified by @specs for upgrade.
            Args:
                @specs: an array of package specifications to be upgraded on the system
                @options: an array of key/value pairs to modify upgrade behavior

            Following @options are supported:
                - repo_ids: list of strings
                    Identifiers of the repos from which the packages could be upgraded.
            Unknown options are ignored.
        '''
        if not sync:
          self._run_dbus_async('Update', False, specs, options)
        else:
          self._run_dbus_sync('Update', specs, options)

    def Reinstall(self, specs, options={}, sync=False):
        '''
            Mark packages specified by @specs for reinstall.
            aRGS:
                @specs: an array of package specifications to be reinstalled on the system
                @options: an array of key/value pairs to modify reinstall behavior

            Following @options are supported:
            Unknown options are ignored.
        '''
        if not sync:
          self._run_dbus_async('Reinstall', False, specs, options)
        else:
          self._run_dbus_sync('Reinstall', specs, options)

    def Downgrade(self, specs, options={}, sync=False):
        '''
            Mark packages specified by @specs for downgrade.
            Args:
                @specs: an array of package specifications to be downgraded on the system
                @options: an array of key/value pairs to modify downgrade behavior

            Following @options are supported:
            Unknown options are ignored.
        '''
        if not sync:
          self._run_dbus_async('Downgrade', False, specs, options)
        else:
          self._run_dbus_sync('Downgrade', specs, options)

    def DistroSync(self, specs, options={}, sync=False):
        '''
            Synchronize the installed packages with their latest available version from any enabled repository.
            It upgrades, downgrades or keeps packages as needed.
            Args:
                @specs: array of package specifications to synchronize to the latest available versions
                @options: an array of key/value pairs to modify distro_sync behavior

            Following @options are supported:
            Unknown options are ignored.
        '''
        if not sync:
          self._run_dbus_async('DistroSync', False, specs, options)
        else:
          self._run_dbus_sync('DistroSync', specs, options)

    def BuildTransaction(self, options={}, sync=False):
        '''
            Resolve the transaction.
            Args:
                @options: an array of key/value pairs to modify dependency resolving
            Return:
                @transaction_items: array
                @result: problems detected during transaction resolving.
                    Possible values are:
                    0 - no problem,
                    1 - no problem, but some info / warnings are present
                    2 - resolving failed.

            Following @options are supported:
                - allow_erasing: boolean, default false
                  Whether removal of installed package is allowed to resolve the transaction.

            Unknown options are ignored.
        '''
        if not sync:
          self._run_dbus_async('BuildTransaction', True, options)
        else:
          resolved, result = self._run_dbus_sync('BuildTransaction', options)
          return (unpack_dbus(result), unpack_dbus(resolved))

    def RunTransaction(self, options={}, sync=False):
        '''
            Perform the resolved transaction.
            Args:
                @options: an array of key/value pairs to modify transaction running

            Following @options are supported:
                - comment: string
                Adds a comment to a transaction.
            Unknown options are ignored
        '''
        if not sync:
          self._run_dbus_async('RunTransaction', False, options)
        else:
          self._run_dbus_sync('RunTransaction', options)


    def TransactionProblems(self, sync=False):
        '''
            Return all problems found during the transaction resolution as human readable messages
            @problems: array of strings containing all problems found during the transaction resolution.
        '''
        if not sync:
          #TODO
          logger.warning("Not implemented yet")
        else:
            return self._run_dbus_sync('TransactionProblems')

    @dnfdragora.misc.TimeFunction
    def GetGroups(self, sync=False):
        '''
            Perform Get groups call it works only for Comps.

            Returns a list of groups
        '''
        if not sync:
          #TODO
          logger.warning("Not implemented yet")
        else:
            return self.__getComps()

    @dnfdragora.misc.TimeFunction
    def GetGroupPackageNames(self, grp_id, sync=False):
        '''
            Perform Get group package names. It works only for Comps.

            Returns a list of package names
        '''
        if not sync:
          #TODO
          logger.warning("Not implemented yet")
        else:
            return self.__getPackageNamesFromGroup(grp_id)

    @dnfdragora.misc.TimeFunction
    def GetGroupsFromPackage(self, package_names, sync=False):
        '''
            Gets groups from a package names. It works only for Comps.

            Returns a list of groups
        '''
        pkgs = [package_names] if (type(package_names) is str) else package_names
        if not sync:
          #TODO
          logger.warning("Not implemented yet")
        else:
            return self.__getGroupFromPackage(pkgs)


    @dnfdragora.misc.TimeFunction
    def GetGroupPackages(self, grp_id, grp_flt, sync=False):
        '''Get packages in a group

        Args:
            grp_id: the group id to get packages for
            grp_flt: the filter ('all' = all packages ,
                     'default' = packages to be installed, before
                     the group is installed)
            fields: extra package attributes to include in result
        '''

        pkgnames = self.__getPackageNamesFromGroup(grp_id)
        options = {
            "package_attrs": [
                "name",
                "epoch",
                "version",
                "release",
                "arch",
                "repo_id",
            ],
            "scope": grp_flt,
            "patterns": pkgnames,
        }
        return self.GetPackages(options, sync=sync)


#----------- TODO move to new methods or remove --------------------------------------------------

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

    def Exit(self, sync=True):
      '''End the daemon'''
      if not sync:
        self._run_dbus_async('Exit')
      else:
        self._run_dbus_sync('Exit')

## TODO fix next API
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





