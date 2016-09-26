'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Andelo Naselli <anaselli@linux.it>

@package dnfdragora
'''

# NOTE part of this code is imported from yumex-dnf


import argparse
import datetime
import logging
import os.path
import shutil
import subprocess
import sys

import dnfdragora.const as const
import dnfdragora.dnf_backend


logger = logging.getLogger('dnfdragora.base')


class BaseDragora:

    def __init__(self):
        self._root_backend = None
        self._root_locked = False
        self.is_working = False

    def set_working(self, state, insensitive=False):
        """Set the working state."""
        self.is_working = state

    @property
    def infobar(self):
        return self.get_infobar()    
    
    def get_infobar(self) :
        print ("get_infobar not implemented")
        pass
    
    def release_infobar(self):
        print ("release_infobar not implemented")
        pass

    @property
    def backend(self):
        return self.get_root_backend()

    def reset_cache(self):
        logger.debug('Refresh system cache')
        self.set_working(True, True)
        print(_('Refreshing Repository Metadata'))
        rc = self._root_backend.ExpireCache()
        self.set_working(False)
        if not rc:
            print(_('Could not refresh the DNF cache (root)'))

    def get_root_backend(self):
        """Get the current root backend.

        if it is not setup yet, the create it
        if it is not locked, then lock it
        """
        if self._root_backend is None:
            self._root_backend = dnfdragora.dnf_backend.DnfRootBackend(self)
        if self._root_locked is False:
            logger.debug('Lock the DNF root daemon')
            locked, msg = self._root_backend.setup()
            if locked:
                self._root_locked = True
                #if self._check_cache_expired('system'):
                #    self.reset_cache()
                self.backend.ExpireCache()
                print("Locked")
            else:
                logger.critical("can't get root backend lock")
                if msg == 'not-authorized':  # user canceled the polkit dialog
                    errmsg = _(
                        'DNF root backend was not authorized.\n'
                        'dnfdragora will exit')
                # DNF is locked by another process
                elif msg == 'locked-by-other':
                    errmsg = _(
                        'DNF is locked by another process.\n\n'
                        'dnfdragora will exit')
                print(errmsg)
                # close down and exit yum extender
                #self.status.SetWorking(False)  # reset working state
                #self.status.SetYumexIsRunning(self.pid, False)
                sys.exit(1)
        return self._root_backend

    def release_root_backend(self, quit_dnfdaemon=False):
        """Release the current root backend, if it is setup and locked."""
        if self._root_backend is None:
            return
        if self._root_locked is True:
            logger.debug('Unlock the DNF root daemon')
            self._root_backend.Unlock()
            self._root_locked = False
            print("Unlocked")
        if quit_dnfdaemon:
            logger.debug('Exit the DNF root daemon')
            self._root_backend.Exit()

    def exception_handler(self, e):
        """Called if exception occours in methods with the
        @ExceptionHandler decorator.
        """
        close = True
        msg = str(e)
        logger.error('BASE EXCEPTION : %s ' % msg)
        err, errmsg = self._parse_error(msg)
        logger.debug('BASE err:  [%s] - msg: %s' % (err, errmsg))
        if err == 'LockedError':
            errmsg = 'DNF is locked by another process.\n' \
                '\ndnfdragora will exit'
            close = False
        elif err == 'NoReply':
            errmsg = 'DNF D-Bus backend is not responding.\n' \
                '\ndnfdragora will exit'
            close = False
        if errmsg == '':
            errmsg = msg
        print(errmsg)

        # try to exit the backends, ignore errors
        if close:
            try:
                self.release_root_backend(quit_dnfdaemon=True)
            except:
                pass
        #self.status.SetWorking(False)  # reset working state
        #self.status.SetYumexIsRunning(self.pid, False)
        sys.exit(1)

    def _parse_error(self, value):
        """Parse values from a DBus releated exception."""
        res = const.DBUS_ERR_RE.match(str(value))
        if res:
            err = res.groups()[0]
            err = err.split('.')[-1]
            msg = res.groups()[1]
            return err, msg
        return '', ''



