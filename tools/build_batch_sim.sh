#!/usr/bin/env bash
# Build QCADesigner-E's command-line simulator (batch_sim) with this repository's patch
# on a Debian/Ubuntu machine or WSL distribution, without Docker.
#
#   sudo apt install -y build-essential autoconf automake libtool pkg-config gettext \
#                       intltool libglib2.0-dev libgtk2.0-dev git python3     # once
#   tools/build_batch_sim.sh [install-dir]        # default: ~/QCADesigner-E
#
# Prints the path of the resulting batch_sim, to pass to qca_scdd_dataset.py --batch-sim.
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$HOME/QCADesigner-E}"

if [ ! -d "$DEST/.git" ]; then
    git clone --depth 1 https://github.com/FSillT/QCADesigner-E.git "$DEST"
fi
cd "$DEST"
if git apply --check "$HERE/qcadesigner_e_batch.patch" 2>/dev/null; then
    git apply "$HERE/qcadesigner_e_batch.patch"
    echo "patch applied"
else
    echo "patch already applied (or does not apply cleanly); continuing"
fi
# keep the shipped, pre-generated build files newer than the patched Makefile.am so
# that make does not try to re-run automake
touch QCADesignerE/aclocal.m4 QCADesignerE/configure QCADesignerE/Makefile.in QCADesignerE/src/Makefile.in
cd QCADesignerE
[ -f src/Makefile ] || sh ./configure
make -C src batch_sim
echo
echo "batch_sim built: $DEST/QCADesignerE/src/batch_sim"
