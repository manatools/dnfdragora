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

.. _conf_ref-label:

####################################
 DNFDragora Configuration Reference
####################################

=============
 Description
=============

DNFDragora by default uses the global configuration file at
``/etc/dnfdragora/dnfdragora.yaml``.

This can be overridden by specifying a different configuration-file in the
following ways:

    * Setting the environment variable $dnfdragora to the full path to the
      configuration-file.
    * Placing the configuration in ~/dnfdragora.yaml.
    * Placing the configuration in the current working-directory.

The configuration-file will be looked up in the previous order of options.

=========
 Options
=========

``use_comps``
    :ref:`boolean <boolean-label>`

    If enabled, group-sorting is read from comps-file. This is recommended
    for Fedora or other Red Hat-based distributions currently. Default is false.

``always_yes``
    :ref:`boolean <boolean-label>`

    If enabled, dnfdragora will assume ``Yes`` where it would normally prompt
    for confirmation from user input. Default is False.

``update_interval``
    :ref:`integer <integer-label>`

    Sets the interval in minutes, dnfdragora-updater continuously checks for
    new available updates.

``log_filename``
    :ref:`string <string-label>`

    Sets the destination path for dnfdragora.log.

``log_level_debug``
    :ref:`boolean <boolean-label>`

    Enable/disable debug logging. Default is true.

=================
 [path:] Options
=================

``group_icons``
    :ref:`string <string-label>`

    Sets the path to the icons used for groups.

==================
 Types of Options
==================

.. _boolean-label:

``boolean``
    This is a data type with only two possible values.

    One of following options can be used: True, False

.. _integer-label:

``integer``
    It is a whole number that can be written without a fractional component.

.. _string-label:

``string``
    It is a sequence of symbols or digits without any whitespace character.

=======
 Files
=======

``Main Configuration File``
    /etc/dnfdragora/dnfdragora.yaml

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

* :manpage:`dnfdragora(8)`
