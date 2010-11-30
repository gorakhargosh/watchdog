#!/bin/sh
# autobuild.sh: Monitors the source directory for documentation file changes
#               and builds it continuously in the background.
#
# Public domain.
#

bin/python watchmedo shell-command --patterns="*.rst;*.rst.inc;*.py" --recursive --command='make -C docs html' watchdog/ docs/source/

