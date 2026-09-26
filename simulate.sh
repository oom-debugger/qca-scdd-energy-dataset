#!/usr/bin/env bash
# One command to build the SCDD -> energy dataset for ANY QCADesigner layout.
#
#   ./simulate.sh layouts/FULLADDER.qca          # every OUTPUT cell of the layout
#   ./simulate.sh layouts/FULLADDER.qca Sum      # only the output cell labelled "Sum"
#   ./simulate.sh /somewhere/my_circuit.qca      # a file outside this folder is copied to layouts/
#
# Everything runs inside Docker: the first run builds the patched QCADesigner-E simulator
# (a few minutes, once); nothing else has to be installed or compiled.  The output cell is
# moved north/south/east/west by the default distances of qca_scdd_dataset.py (0.1 nm steps,
# 0.01 nm westwards) and every copy is simulated.  Result: data/spe_<layout>_<cell>.csv, one row
# per displacement; the "status" column reads "ok" for every good row.  Safe to re-run: rows
# that are already done are kept and the rest is continued.
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -lt 1 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
fi
QCA="$1"
ONLY="${2:-}"

if [ ! -f "$QCA" ]; then
    echo "ERROR: file not found: $QCA" >&2
    exit 1
fi
# The layout must be inside this folder (Docker only sees this folder); copy it in if needed.
ABS="$(cd "$(dirname "$QCA")" && pwd)/$(basename "$QCA")"
case "$ABS" in
    "$PWD"/*) REL="${ABS#"$PWD"/}" ;;
    *) mkdir -p layouts
       cp "$QCA" "layouts/$(basename "$QCA")"
       REL="layouts/$(basename "$QCA")"
       echo "copied $QCA to $REL" ;;
esac
STEM="$(basename "$REL" .qca)"

# --- Docker ------------------------------------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: Docker is not installed." >&2
    echo "  Ubuntu/Debian:  sudo apt-get install -y docker.io   (then log out and back in)" >&2
    echo "  Windows/macOS:  install Docker Desktop and start it" >&2
    exit 1
fi
DOCKER=docker
if ! docker info >/dev/null 2>&1; then
    if command -v sudo >/dev/null 2>&1 && sudo docker info >/dev/null 2>&1; then
        DOCKER="sudo docker"
    else
        echo "ERROR: Docker is installed but not running, or you may not use it." >&2
        echo "  Windows/macOS: start Docker Desktop and wait until it says it is running." >&2
        echo "  Ubuntu:        sudo systemctl start docker ; sudo usermod -aG docker \$USER ; log out and back in" >&2
        exit 1
    fi
fi
echo "building the simulator image (first time only, a few minutes) ..."
if ! $DOCKER build -q -t qde-batch -f docker/Dockerfile . >/dev/null; then
    echo "ERROR: the Docker build failed; run this to see why:" >&2
    echo "  $DOCKER build -t qde-batch -f docker/Dockerfile ." >&2
    exit 1
fi

# Mount this folder at /work.  Git Bash on Windows rewrites POSIX-looking paths, so use
# the Windows path and switch that rewriting off.
if [ "$(uname -o 2>/dev/null)" = "Msys" ]; then
    export MSYS_NO_PATHCONV=1
    HOST_DIR="$(pwd -W)"
else
    HOST_DIR="$PWD"
fi
run() { $DOCKER run --rm -v "$HOST_DIR:/work" -w /work qde-batch python3 qca_scdd_dataset.py "$@"; }

# --- which cells to displace: every OUTPUT cell (or the one asked for) ---------------------
CELLS="$(run --qca "$REL" --list-cells | awk '$2 == "OUTPUT" { print $1 ":" $3 }')"
if [ -z "$CELLS" ]; then
    echo "ERROR: $REL has no OUTPUT cell.  In QCADesigner, select the output cell, set its" >&2
    echo "       function to Output (and give it a label), save, and run this again." >&2
    exit 1
fi
if [ -n "$ONLY" ]; then
    CELLS="$(printf '%s\n' "$CELLS" | awk -F: -v want="$ONLY" '$2 == want || ("#" $1) == want')"
    if [ -z "$CELLS" ]; then
        echo "ERROR: no OUTPUT cell called '$ONLY' in $REL.  Its cells are:" >&2
        run --qca "$REL" --list-cells >&2
        exit 1
    fi
fi

mkdir -p data runs
for entry in $CELLS; do
    idx="${entry%%:*}"
    label="${entry#*:}"
    if [ "${label#\#}" != "$label" ]; then          # unlabelled cell: "#12"
        cellarg=(--cell-index "$idx"); name="cell$idx"
    else
        cellarg=(--cell "$label"); name="$(printf '%s' "$label" | tr -c 'A-Za-z0-9_.+-' '_')"
    fi
    csv="data/spe_${STEM}_${name}.csv"
    echo
    echo "=== $REL : output cell $label -> $csv ==="
    run --qca "$REL" "${cellarg[@]}" --gate "$STEM" --out "runs/${STEM}_${name}" --csv "$csv" \
        --batch-sim batch_sim --options energy_options.txt --resume
    total=$(($(wc -l < "$csv") - 1))
    good=$(tr -d '\r' < "$csv" | grep -Ec ',ok(-[a-z-]+)?,[0-9.]*$' || true)
    echo "=== $csv: $good of $total rows ok ==="
done
