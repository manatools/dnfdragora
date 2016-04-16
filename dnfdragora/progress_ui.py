from __future__ import print_function
from __future__ import absolute_import

import yui

from dnf.callback import DownloadProgress
class Progress(DownloadProgress):

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

        self._setLabel(text)

        self.total_files = total_files
        self.total_size = total_size
        self.download_files = 0
        self.download_size = 0.0


    def end(self,payload, status, msg):
        if not status: # payload download complete
            self.download_files += 1
            self.update()
        else: # dnl end with errors
            self.update()

    def progress(self, payload, done):
        pload = str(payload)
        if not pload in self.dnl:
            self.dnl[pload] = 0.0
            text = "Starting to download : %s " % str(payload)
            self._setLabel(text)

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
        self._setLabel(text)
        value = self.last_pct

        self.progressbar.setValue(value)
        self._flush()
        #sys.stdout.write("Progress : %-3d %% (%d/%d)\r" % (self.last_pct,self.download_files, self.total_files))


    def _setLabel(self, text=""):
        self.main_dialog.startMultipleChanges()
        self.label_widget.setValue(text)
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

