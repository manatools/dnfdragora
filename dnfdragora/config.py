'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Andelo Naselli <anaselli@linux.it>

@package dnfdragora
'''

import sys
import yaml

from os.path import expanduser, join
import os


class AppConfig() :
    ''' AppConfig is an application configuration file management
    appName ia the application name
    configuration file name is appName + ".yaml"
    which is searched in these places and order:
    1. from environment variable $'AppNme'
    2. ~/
    3. current directory
    4. /etc/'AppName'/
    '''
    def __init__(self, appName) :
        self.content    = None
        self.project   = appName
        self.variable  = appName.upper() + "_CONF"
        self.fileName  = appName + ".yaml"
        self.systemDir = "/etc/" + appName

    def load(self) :
        pathdir = []
        if os.environ.get(self.variable) :
            pathdir.append(os.environ.get(self.variable))
        pathdir.extend([os.path.expanduser("~"), os.curdir, self.systemDir])

        for loc in pathdir :
            try:
                f = os.path.join(loc, self.fileName)
                with open(f, 'r') as ymlfile:
                    self.content = yaml.load(ymlfile)
                    return self.content
            except IOError as e:
                print ("Skipped exception: <%s> " % str(e))
                pass

        return {}

