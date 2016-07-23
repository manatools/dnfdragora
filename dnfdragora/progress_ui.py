from __future__ import print_function
from __future__ import absolute_import

import yui

import dnf.callback


class TransactionProgress(dnf.callback.TransactionProgress):

    def __init__(self):
        self.actions = {dnf.callback.PKG_CLEANUP: 'cleanup',
                        dnf.callback.PKG_DOWNGRADE: 'downgrade',
                        dnf.callback.PKG_REMOVE: 'erase',
                        dnf.callback.PKG_INSTALL: 'install',
                        dnf.callback.PKG_OBSOLETE: 'obsolete',
                        dnf.callback.PKG_REINSTALL: 'reinstall',
                        dnf.callback.PKG_UPGRADE: 'update',
                        dnf.callback.PKG_VERIFY: 'verify'}

        super(dnf.callback.TransactionProgress, self).__init__()
        self.do_verify = False

    def progress(self, package, action, te_current, te_total, ts_current,
              ts_total):
        """
        @param package: A yum package object or simple string of a package name
        @param action: A constant transaction set state
        @param te_current: current number of bytes processed in the transaction
                           element being processed
        @param te_total: total number of bytes in the transaction element being
                         processed
        @param ts_current: number of processes completed in whole transaction
        @param ts_total: total number of processes in the transaction.
        """
        if package:
            # package can be both str or dnf package object
            if not isinstance(package, str):
                pkg_id = str(package)
            else:
                pkg_id = package
            if action in self.actions:
                action = self.actions[action]

            print ("%s %s"%(pkg_id, action))
            #self.base.RPMProgress(
                #pkg_id, action, te_current, te_total, ts_current, ts_total)


class Progress(dnf.callback.DownloadProgress):

    def __init__(self):
        '''
        Progress bar dialog class
        '''
        super(Progress, self).__init__()
        self.factory = yui.YUI.widgetFactory()

        self.main_dialog = self.factory.createPopupDialog()
        vbox = self.factory.createVBox(self.main_dialog)
        self.label_widget = self.factory.createLabel(vbox, "")
        self.label_widget.setStretchable( yui.YD_HORIZ, True )
        self.progressbar = self.factory.createProgressBar(vbox, "")
        self.wrongValue = self.factory.createLabel(vbox, "")
        self.wrongValue.setStretchable( yui.YD_HORIZ, True )

        self.total_files = 0
        self.total_size = 0.0
        self.download_files = 0
        self.download_size = 0.0
        self.dnl = {}
        self.last_pct = 0

    def __del__(self):
        print ("Progress destroyed")
        self.main_dialog.destroy()

    def start(self, total_files, total_size):
        text = "Downloading :  %d files,  %d bytes" % (total_files, total_size)
        print (text)

        self._setLabel(self.label_widget, text)

        self.total_files = total_files
        self.total_size = total_size
        self.download_files = 0
        self.download_size = 0.0

        self.progressbar.setValue(0)
        self.wrongValue.setValue("")



    def end(self,payload, status, msg):
        if not status: # payload download complete
            self.download_files += 1
            self.update()
        else: # dnl end with errors
            self.update()
        self.progressbar.setValue(100)

    def progress(self, payload, done):
        pload = str(payload)
        if not pload in self.dnl:
            self.dnl[pload] = 0.0
            text = "Starting to download : %s " % str(payload)
            self._setLabel(self.label_widget, text)

        else:
            self.dnl[pload] = done
            pct = self.get_total()
            if pct > self.last_pct:
                self.last_pct = pct
                self.update()


    def get_total(self):
        """ Get the total downloaded percentage"""
        tot = 0.0
        for value in self.dnl.values():
            tot += value
        pct = int((tot / float(self.total_size)) * 100)
        return pct

    def update(self):
        """ Output the current progress"""
        text = "Progress files (%d/%d)" % (self.download_files, self.total_files)
        # TODO remove print(text)
        self._setLabel(self.label_widget, text)
        value = self.last_pct
        # TODO remove print ( "Value %d" % (self.last_pct))

        if (value <= 100) :
            self.progressbar.setValue(value)
        else:
            self._setLabel(self.wrongValue, text=("%d"%value))
            self.progressbar.setValue(99)

        self._flush()


    def _setLabel(self, label_widget, text=""):
        self.main_dialog.startMultipleChanges()
        label_widget.setValue(text)
        self.main_dialog.doneMultipleChanges()
        self._flush()


    def _flush (self) :
        self.main_dialog.startMultipleChanges()
        self.main_dialog.recalcLayout()
        self.main_dialog.doneMultipleChanges()

        if self.main_dialog.isTopmostDialog() :
           self.main_dialog.waitForEvent(10)
           self.main_dialog.pollEvent()
        #else :
            #Exception?  "This dialog is not a top most dialog\n"

        yui.YUI.app().redrawScreen()

