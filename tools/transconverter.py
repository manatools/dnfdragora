#!/usr/bin/env python
# -*- coding: utf-8 -*-

import errno, glob, polib, re, os, getopt, sys
from time import strftime

def usage():
    print '\nUsage: python %s [OPTION]' %os.path.basename(sys.argv[0])
    print '       generate pot catalogs and updates po files for desktop resources in the specified directory'
    print 'Options: -h, --help                              : usage'
    print '         -d <directory>, --directory <directory> : directory with desktop files'
    sys.exit(2)
try:
    opts, args = getopt.getopt(sys.argv[1:], "hd:", ["help", "directory="])
except getopt.GetoptError:
    usage() # print help information and exit

directory='.'
for o,a in opts:
    if o in ("-h", "--help"):
        usage()
    if o in ("-d", "--directory"):
        directory=a

directory = directory.rstrip('/')

if (directory != '') and (os.path.isdir(directory) == False):
    sys.exit('Specified directory does not exist')

# Find all desktop files
files = []
for rootdir, dirnames, filenames in os.walk(directory):
    files.extend(glob.glob(rootdir + "/*.desktop"))

# Define Templates and po directory name
translationtemplate='(?<=\n)(Name\[.*?\n|Comment\[.*?\n|GenericName\[.*?\n)'
tpattern=re.compile(translationtemplate,re.DOTALL)
podir = 'po/desktop'

pocreationtime = strftime('%Y-%m-%d %H:%M%z')

for langfile in files:
  langfiledir = langfile.replace('.desktop', '')
  langfilename = langfiledir.rpartition('/')[2]
  # Create localization directories if needed
  try:
    os.makedirs(podir)
  except OSError, e:
    if e.errno != errno.EEXIST:
        raise
  #open desktop file
  text = open(langfile,"r").read()

  # Parse contents and add them to PO
  for tblock in tpattern.findall(text):
    message_comment, locale_message = tblock.strip('\n').split('[')
    lang_code, msg_str = locale_message.split(']=')
    msgidtemplate='(?<=\n)' + message_comment + '=.*?\n'
    msgidpattern=re.compile(msgidtemplate,re.DOTALL)
    msgids = msgidpattern.findall(text)
    if msgids:
      msg_id = msgids[0].split('=')[1].strip('\n')
      poentry = polib.POEntry(
	msgctxt = message_comment,
	msgid = msg_id.decode('utf-8'),
	msgstr = msg_str.decode('utf-8'),
	occurrences=[(langfile,'')]
	)
      pofilename = podir + '/' + lang_code + '.po'
      if not os.path.isfile(pofilename):
	# Create PO file
	po = polib.POFile()
	po.metadata = {
	  'Project-Id-Version': 'dnfdragora desktop files translation',
	  'Report-Msgid-Bugs-To': 'i18n-discuss@mageia.org',
	  'POT-Creation-Date': pocreationtime,
	  'PO-Revision-Date': pocreationtime,
	  'Last-Translator': 'Duffy Duck <d_duck@nowhere.net>',
	  'Language-Team': lang_code + ' <mageia-' + lang_code + '@ml.mageia.org>',
	  'MIME-Version': '1.0',
	  'Content-Type': 'text/plain; charset=UTF-8',
	  'Content-Transfer-Encoding': '8bit',
	  }
	po.save(pofilename)
      po = polib.pofile(pofilename, check_for_duplicates=True)
      if msg_id != '':
	try:
	  po.append(poentry)
	except ValueError:
	  print 'The entry already exists, skipping it'
      po.save(pofilename)

