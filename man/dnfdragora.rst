:orphan:

..
  Copyright (C) 2016-2017 Angelo Naselli and Neal Gompa

  This program is free software: you can redistribute it and/or modify
  it under the terms of the GNU General Public License as published by
  the Free Software Foundation, either version 3 of the License, or
  (at your option) any later version.

  This program is distributed in the hope that it will be useful,
  but WITHOUT ANY WARRANTY; without even the implied warranty of
  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
  GNU General Public License for more details.

  You should have received a copy of the GNU General Public License
  along with this program.  If not, see <http://www.gnu.org/licenses/>.

.. _command_ref-label:

##############################
 DNFDragora Command Reference
##############################

==========
 Synopsis
==========

``dnfdragora [options] [<args>...]``

=============
 Description
=============

.. _command_provides-label:

DNFDragora is a DNF frontend, based on rpmdragora from Mageia
(originally rpmdrake) Perl code. It is written in Python 3 and uses
libYui, the widget abstraction library written by SUSE, so that it
can be run using Qt 5, GTK+ 3, or ncurses interfaces.

.. _options-label:

=========
 Options
=========

``-h, --help``
    Show help message and exit.

``--gtk``
    Start using yui GTK+ plugin implementation.

``--ncurses``
    Start using yui ncurses plugin implementation.

``--qt``
    Start using yui Qt plugin implementation.

``--fullscreen``
    Use full screen for dialogs.

``--update-only``
    Show updates dialog only.

``--group-icons-path <GROUP_ICONS_PATH>``
    Force a new path for group icons (instead of /usr/share/icons).

``--images-path* <IMAGES_PATH>``
    Force a new path for all the needed images (instead of
    /usr/share/dnfdragora/images).

``--locales-dir <LOCALES_DIR>``
    Set path to the directory containing localization strings (developer
    option only).

``--install <RPM-Packages …>``
    Install local rpm packages.

``--version``
    Show application version and exit.

``--exit``
    Force dnfdaemon dbus services used by dnfdragora to exit.

======
 Bugs
======

* See: `https://github.com/manatools/dnfdragora/issues`

===========
 Resources
===========

* GitHub: `https://github.com/manatools/dnfdragora`

==========
 See Also
==========

* :manpage:`dnfdragora.yaml(5)`
