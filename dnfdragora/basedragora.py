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

import dnfdragora.const as const
import dnfdragora.dialogs as dialogs
import dnfdragora.dnf_backend
import yui
from gettext import gettext as _


logger = logging.getLogger('dnfdragora.base')


class BaseDragora:

    def __init__(self, use_comps):
        self._root_backend = None
        self._root_locked = False
        self.is_working = False
        self._use_comps = use_comps

    def set_working(self, state, insensitive=False):
        """Set the working state."""
        self.is_working = state
    
    def release_infobar(self):
        print ("release_infobar not implemented")
        pass

    @property
    def backend(self):
        return self.get_root_backend()

    def reset_cache(self):
        logger.debug('Refresh system cache')
        self.set_working(True, True)
        self.infobar.info(_('Refreshing Repository Metadata'))
        rc = self._root_backend.ExpireCache()
        self.set_working(False)
        self.infobar.info("")
        if not rc:
            dialogs.warningMsgBox({'title' : _("Sorry"), "text": _('Could not refresh the DNF cache (root)')})

    def get_root_backend(self):
        """Get the current root backend.

        if it is not setup yet, the create it
        if it is not locked, then lock it
        """
        if self._root_backend is None:
            self._root_backend = dnfdragora.dnf_backend.DnfRootBackend(self, self._use_comps)
        if self._root_locked is False:
            logger.debug('Lock the DNF root daemon')
            locked, msg = self._root_backend.setup()
            if locked:
                self._root_locked = True
                #if self._check_cache_expired('system'):
                #    self.reset_cache()
                self.backend.ExpireCache()
                logger.info("Locked the DNF root daemon")
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
                logger.critical(errmsg)
                dialogs.warningMsgBox({'title' : _("Sorry"), "text": errmsg})
                yui.YDialog.deleteTopmostDialog()
                # next line seems to be a workaround to prevent the qt-app from crashing
                # see https://github.com/libyui/libyui-qt/issues/41
                yui.YUILoader.deleteUI()
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
            logger.info("Unlocked the DNF root daemon")
        if quit_dnfdaemon:
            logger.debug('Exit the DNF root daemon')
            self._root_backend.Exit()
            self._root_backend = None

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
        """Parse values from a DBus releated exception."""
        res = const.DBUS_ERR_RE.match(str(value))
        if res:
            err = res.groups()[0]
            err = err.split('.')[-1]
            msg = res.groups()[1]
            return err, msg
        return '', ''



