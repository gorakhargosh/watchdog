#!/bin/sh
# autobuild.sh: Monitors the source directory for documentation file changes
#               and builds it continuously in the background.
#
# Public domain.
#

python tools/nosy.py .



# First forced build.
#make -C docs html

# Monitored builds.
#bin/python watchmedo shell-command \
#    --patterns="*.rst;*.rst.inc;*.py;*.py.swp;*.rst.swp;*.rst.inc.swp" \
#    --ignore-patterns=".*;#*;*~" \
#    --ignore-directories \
#    --recursive \
#    --command='make -C docs html' \
#    src/ docs/source/

