'''
dnfdragora is a graphical package management tool based on libyui python bindings

License: GPLv3

Author:  Angelo Naselli <anaselli@linux.it>

@package dnfdragora
'''

# NOTE part of this code is imported from yumex-dnf

import time
import configparser
import gettext
import locale
import logging
import logging.handlers
import os.path
import re
import subprocess
import sys
import re
import dbus


logger = logging.getLogger('dnfdragora.misc')


class QueueEmptyError(Exception):

    def __init__(self):
        super(QueueEmptyError, self).__init__()


class TransactionBuildError(Exception):

    def __init__(self, msgs):
        super(TransactionBuildError, self).__init__()
        self.msgs = msgs


class TransactionSolveError(Exception):

    def __init__(self, msgs):
        super(TransactionSolveError, self).__init__()
        self.msgs = msgs


def dbus_dnfsystem(cmd):
    subprocess.call(
        '/usr/bin/dbus-send --system --print-reply '
        '--dest=org.baseurl.DnfSystem / org.baseurl.DnfSystem.%s' % cmd,
        shell=True)


def to_pkg_id(n, e, v, r, a, repo_id):
    ''' return the package id from given attributes '''
    return "%s,%s,%s,%s,%s,%s" % (n, e, v, r, a, repo_id)

def to_pkg_tuple(pkg_id):
    """Find the real package nevra & repoid from an package pkg_id"""
    (n, e, v, r, a, repo_id) = str(pkg_id).split(',')
    return (n, e, v, r, a, repo_id)


def list_to_string(pkg_list, first_delimitier, delimiter):
    """Creates a multiline string from a list of packages"""
    string = first_delimitier
    for pkg_name in pkg_list:
        string = string + pkg_name + delimiter
    return string

def pkg_id_to_full_nevra(pkg_id):
    (n, e, v, r, a, repo_id) = to_pkg_tuple(pkg_id)
    return "%s-%s:%s-%s.%s" % (n, e, v, r, a)

def pkg_id_to_full_name(pkg_id):
    (n, e, v, r, a, repo_id) = to_pkg_tuple(pkg_id)
    if e and e != '0':
        return "%s-%s:%s-%s.%s" % (n, e, v, r, a)
    else:
        return "%s-%s-%s.%s" % (n, v, r, a)


#def color_floats(spec):
    #rgba = Gdk.RGBA()
    #rgba.parse(spec)
    #return rgba.red, rgba.green, rgba.blue


#def get_color(spec):
    #rgba = Gdk.RGBA()
    #rgba.parse(spec)
    #return rgba


#def rgb_to_hex(r, g, b):
    #if isinstance(r, float):
        #r *= 255
        #g *= 255
        #b *= 255
    #return "#{0:02X}{1:02X}{2:02X}".format(int(r), int(g), int(b))


#def color_to_hex(color):
    #return rgb_to_hex(color.red, color.green, color.blue)


def is_url(url):
    urls = re.findall(
        r'^http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+~]|'
        r'[!*\(\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', url)
    return urls


def format_block(block, indent):
    ''' Format a block of text so they get the same indentation'''
    spaces = " " * indent
    lines = str(block).split('\n')
    result = lines[0] + "\n"
    for line in lines[1:]:
        result += spaces + line + '\n'
    return result

def parse_dbus_error():
    '''parse values from a DBus related exception '''
    DBUS_ERR_RE = re.compile('.*GDBus.Error:([\w\.]*): (.*)$')

    (type, value, traceback) = sys.exc_info()
    res = DBUS_ERR_RE.match(str(value))
    if res:
        return res.groups()
    return "", ""

def ExceptionHandler(func):
    """
    This decorator catch dnfdragora backed exceptions
    """
    def newFunc(*args, **kwargs):
        try:
            rc = func(*args, **kwargs)
            return rc
        except Exception as e:
            base = args[0]  # get current class
            base.exception_handler(e)
    newFunc.__name__ = func.__name__
    newFunc.__doc__ = func.__doc__
    newFunc.__dict__.update(func.__dict__)
    return newFunc


def TimeFunction(func):
    """
    This decorator catch dnfdragora exceptions and send fatal signal to frontend
    """
    def newFunc(*args, **kwargs):
        t_start = time.monotonic()
        rc = func(*args, **kwargs)
        t_end = time.monotonic()
        name = func.__name__
        t_diff = t_end - t_start
        if t_diff >= 0.001:
          logger.debug("%s took %.3f sec", name, t_diff)
        return rc

    newFunc.__name__ = func.__name__
    newFunc.__doc__ = func.__doc__
    newFunc.__dict__.update(func.__dict__)
    return newFunc


def format_number(number, SI=0, space=' '):
    """Turn numbers into human-readable metric-like numbers"""
    symbols = ['',  # (none)
               'k',  # kilo
               'M',  # mega
               'G',  # giga
               'T',  # tera
               'P',  # peta
               'E',  # exa
               'Z',  # zetta
               'Y']  # yotta

    if SI:
        step = 1000.0
    else:
        step = 1024.0

    thresh = 999
    depth = 0
    max_depth = len(symbols) - 1

    # we want numbers between 0 and thresh, but don't exceed the length
    # of our list.  In that event, the formatting will be screwed up,
    # but it'll still show the right number.
    while number > thresh and depth < max_depth:
        depth = depth + 1
        number = number / step

    if isinstance(number, int):
        # it's an int or a long, which means it didn't get divided,
        # which means it's already short enough
        fmt = '%i%s%s'
    elif number < 9.95:
        # must use 9.95 for proper sizing.  For example, 9.99 will be
        # rounded to 10.0 with the .1f fmt string (which is too long)
        fmt = '%.1f%s%s'
    else:
        fmt = '%.0f%s%s'

    return(fmt % (float(number or 0), space, symbols[depth]))

def format_size(number):
    """Turn size number in KBytes """
    step = 1024.0
    number = number / step
    fmt = '%10.1f%s'

    return(fmt % (float(number or 0), "K"))


def logger_setup(file_name='dnfdragora.log',
                 logroot='dnfdragora',
                 logfmt='%(asctime)s: %(message)s',
                 loglvl=logging.INFO):
    """Setup Python logging."""
    maxbytes=10*1024*1024
    handler = logging.handlers.RotatingFileHandler(
              file_name, maxBytes=maxbytes, backupCount=5)
    logging.basicConfig(filename=file_name, format='%(asctime)s [%(name)s]{%(filename)s:%(lineno)d}(%(levelname)s) %(message)s', level=loglvl)
    logger.addHandler(handler)
    #logger = logging.getLogger(logroot)
    #logger.setLevel(loglvl)
    #formatter = logging.Formatter(logfmt, '%H:%M:%S')
    #handler = logging.FileHandler(filename)
    #handler.setFormatter(formatter)
    #handler.propagate = False
    #logger.addHandler(handler)

