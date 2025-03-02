from __future__ import print_function
from __future__ import absolute_import

import yui

class ProgressBar:

    def __init__(self, main_dialog, layout):
        self.factory = yui.YUI.widgetFactory()

        self.main_dialog = main_dialog
        self.layout = layout
        vbox = self.factory.createVBox(layout)
        hbox = self.factory.createHBox(vbox)
        self.info_widget = self.factory.createLabel(hbox, "")
        self.info_widget.setStretchable( yui.YD_HORIZ, True )
        self.info_sub_widget = self.factory.createLabel(hbox, "")
        self.info_sub_widget.setStretchable( yui.YD_HORIZ, True )
        self.progressbar = self.factory.createProgressBar(vbox, "")


    def info(self, text) :
        self.info_widget.setValue(text)
        #self.__flush()

    def info_sub(self, text) :
        self.info_sub_widget.setValue(text)
        #self.__flush()

    def set_progress(self, frac, label=None) :
        if label is not None:
            self.progressbar.setLabel(label)
        val = self.progressbar.value()
        newval = int(100*frac)
        if (val != newval) :
            self.progressbar.setValue(newval)
        #self.__flush()

    def reset_all(self) :
        self.info_widget.setValue('')
        self.info_sub_widget.setValue('')
        self.set_progress(0, "")
        self.__flush()

    def __flush(self) :
        if self.main_dialog.isTopmostDialog() :
            self.main_dialog.pollEvent()


