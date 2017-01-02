#!/bin/bash
# Generate the map from category name to ID for dnfdragora/compsicons.py
# Workaround for https://github.com/timlau/dnf-daemon/issues/9
wget https://pagure.io/fedora-comps/raw/master/f/comps-f26.xml.in -q -O - | tr '\n' '#' | sed -e 's!<group>.*</group>!!g' -e 's!<environment>.*</environment>!!g' | tr '#' '\n' | grep '<_name>\|<id>' | tr '\n' '#' | sed -e 's!<id>\([^<]*\)</id># *<_name>\([^<]*\)</_name>!"\2": \{"title": _\("\2"\), "icon" :"\1.png"\},!g' | tr '#' '\n' | sed -e 's/^ */            /g'
