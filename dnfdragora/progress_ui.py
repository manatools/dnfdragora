from __future__ import print_function
from __future__ import absolute_import

import manatools.aui.yui as MUI

class ProgressBar:

    def __init__(self, main_dialog, layout):
        self.factory = MUI.YUI.widgetFactory()

        self.main_dialog = main_dialog
        self.layout = layout
        vbox = self.factory.createVBox(layout)
        hbox = self.factory.createHBox(vbox)
        self.info_widget = self.factory.createLabel(hbox, "")
        self.info_widget.setStretchable( MUI.YUIDimension.YD_HORIZ, True )
        self.info_sub_widget = self.factory.createLabel(hbox, "")
        self.info_sub_widget.setStretchable( MUI.YUIDimension.YD_HORIZ, True )
        self.progressbar = self.factory.createProgressBar(vbox, "")
        self.progressbar.setStretchable( MUI.YUIDimension.YD_HORIZ, True )

    def info(self, text) :
        self.info_widget.setValue(text)

    def info_sub(self, text) :
        self.info_sub_widget.setValue(text)

    def set_progress(self, frac, label=None) :
        if label is not None:
            self.progressbar.setLabel(label)
        val = self.progressbar.value()
        newval = int(100*frac)
        if (val != newval) :
            self.progressbar.setValue(newval)
        self.__setVisible(newval > 0 and newval < 100)

    def reset_all(self) :
        self.info_widget.setValue('')
        self.info_sub_widget.setValue('')
        self.set_progress(0, "")

    def __setVisible(self, on: bool = True):
        self.info_widget.setVisible(bool(on))
        self.info_sub_widget.setVisible(bool(on))
        self.progressbar.setVisible(bool(on))

    def setHelpText(self, help_text: str):    
        self.progressbar.setHelpText(help_text)