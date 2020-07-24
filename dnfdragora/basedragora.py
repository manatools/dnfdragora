'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Angelo Naselli <anaselli@linux.it>

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
import time

import dnfdragora.const as const
import dnfdragora.dialogs as dialogs
import dnfdragora.dnf_backend
import yui

logger = logging.getLogger('dnfdragora.base')


class BaseDragora:

    def __init__(self, use_comps):
        self._root_backend = None
        self._root_locked = False
        self.is_working = False
        self._use_comps = use_comps
        # TODO allow to setup if 2 seconds is not enough for slow PCs
        self._time2wait_new_backend = 2

    def set_working(self, state, insensitive=False):
        """Set the working state."""
        self.is_working = state
    
    def release_infobar(self):
        print ("release_infobar not implemented")
        pass

    @property
    def backend(self):
        return self.get_root_backend()

    @property
    def backend_locked(self):
      '''
      return backend locking status
      '''
      return self._root_locked

    @backend_locked.setter
    def backend_locked(self, value):
      '''
      set backend lockinf status
      '''
      if isinstance(value, (bool)):
        self._root_locked = value
      else:
        #TODO raise
        logger.error("Bool value expected")

    def reset_cache(self):
        logger.debug('Refresh system cache')
        self._root_backend.ExpireCache()

    def get_root_backend(self):
        """Get the current root backend.

        if it is not setup yet, the create it
        if it is not locked, then lock it
        """
        if self._root_backend is None:
          self._root_backend = dnfdragora.dnf_backend.DnfRootBackend(self, self._use_comps)
          if self._root_locked is False:
            logger.debug('Lock the DNF root daemon')
            self._root_backend.Lock()
        else:
          if self._root_locked is False:
            logger.warning('Get root backend. Locked (%s)', self._root_locked)


        #TODO REMOVE    locked, msg = self._root_backend.setup()
        #TODO REMOVE    if locked:
        #TODO REMOVE        self._root_locked = True
        #TODO REMOVE        #if self._check_cache_expired('system'):
        #TODO REMOVE        #    self.reset_cache()
        #TODO REMOVE        self.backend.ExpireCache()
        #TODO REMOVE        logger.info("Locked the DNF root daemon")
        #TODO REMOVE    else:
        #TODO REMOVE        logger.critical("can't get root backend lock")
        #TODO REMOVE        if msg == 'not-authorized':  # user canceled the polkit dialog
        #TODO REMOVE            errmsg = _(
        #TODO REMOVE                'DNF root backend was not authorized.\n'
        #TODO REMOVE                'dnfdragora will exit')
        #TODO REMOVE        # DNF is locked by another process
        #TODO REMOVE        elif msg == 'locked-by-other':
        #TODO REMOVE            errmsg = _(
        #TODO REMOVE                'DNF is locked by another process.\n\n'
        #TODO REMOVE                'dnfdragora will exit')
        #TODO REMOVE        logger.critical(errmsg)
        #TODO REMOVE        dialogs.warningMsgBox({'title' : _("Sorry"), "text": errmsg})
        #TODO REMOVE        yui.YDialog.deleteTopmostDialog()
        #TODO REMOVE        # next line seems to be a workaround to prevent the qt-app from crashing
        #TODO REMOVE        # see https://github.com/libyui/libyui-qt/issues/41
        #TODO REMOVE        yui.YUILoader.deleteUI()
        #TODO REMOVE        sys.exit(1)
        return self._root_backend

    def release_root_backend(self, quit_dnfdaemon=False):
        """Release the current root backend, if it is setup and locked."""
        if self._root_backend is None:
            return
        if self._root_locked is True:
            logger.debug('Unlock the DNF root daemon')
            self._root_backend.Unlock(sync=quit_dnfdaemon)
            logger.info("Unlocked the DNF root daemon")
        else:
          self._root_backend = None
        if quit_dnfdaemon:
            self._root_locked = False
            logger.debug('Exit the DNF root daemon')
            self._root_backend.Exit(sync=True)
            self._root_backend = None

    def restart_root_backend(self):
        ''' Release and reload backend '''
        self.release_root_backend(True)
        time.sleep(self._time2wait_new_backend)
        self.get_root_backend()

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
        dialogs.warningMsgBox({'title' : _("Sorry"), "text": errmsg})
        logger.critical(errmsg)

        # try to exit the backends, ignore errors
        if close:
            try:
                self.release_root_backend(quit_dnfdaemon=True)
            except:
                pass

        yui.YDialog.deleteTopmostDialog()
        # next line seems to be a workaround to prevent the qt-app from crashing
        # see https://github.com/libyui/libyui-qt/issues/41
        yui.YUILoader.deleteUI()
        sys.exit(1)

    def _parse_error(self, value):
        """Parse values from a DBus related exception."""
        res = const.DBUS_ERR_RE.match(str(value))
        if res:
            err = res.groups()[0]
            err = err.split('.')[-1]
            msg = res.groups()[1]
            return err, msg
        return '', ''



