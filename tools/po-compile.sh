#!/bin/sh

set -e

if test "$1" = "-h" -o "$1" = "--help"; then
	echo "Use: $0 [<language>]"
	echo "Run without arguments to compile all translation files."
	exit 0
fi

cd "$(readlink -f "$(dirname "$0")/..")"

update_mo(){
	echo $1
	language="$(basename "$1")"
	language="${language%.po}"
	target="$PWD/share/locale/$language/LC_MESSAGES/dnfdragora.mo"
	echo $target
	/bin/mkdir --parents "$(dirname "$target")"
	/usr/bin/msgfmt \
		--check \
		--output-file="$target" \
		"$1"
}

if test "$1"; then
  for l in $(find "$PWD/po" -type f -name "$1.po"); do
  echo $l
  update_mo "$l"
  done
else
  for l in $(find "$PWD/po" -type f -name '*.po'); do
    update_mo "$l"
  done
fi
