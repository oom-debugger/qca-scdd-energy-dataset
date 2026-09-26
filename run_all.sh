#!/usr/bin/env bash
# Regenerate every dataset under data/ from scratch, inside the Docker image that holds
# the patched QCADesigner-E batch simulator.  Safe to re-run: finished rows are skipped
# (--resume).  Needs Docker and Python 3 on the host.
#
#   ./run_all.sh            # everything (LT NAND, LT NOR, LT Ex-OR, LT Ex-NOR)
#   ./run_all.sh LT_NAND    # one gate
set -euo pipefail
cd "$(dirname "$0")"

docker build -q -t qde-batch -f docker/Dockerfile . >/dev/null

# Mount the repository at /work.  Git Bash on Windows rewrites POSIX-looking paths, so
# use the Windows path and switch that rewriting off.
if [ "$(uname -o 2>/dev/null)" = "Msys" ]; then
    export MSYS_NO_PATHCONV=1
    HOST_DIR="$(pwd -W)"
else
    HOST_DIR="$PWD"
fi
run() {
    docker run --rm -v "$HOST_DIR:/work" -w /work qde-batch \
        python3 qca_scdd_dataset.py --batch-sim batch_sim --options energy_options.txt --resume "$@"
}

PY=$(command -v python3 || command -v python); "$PY" layouts/make_lt_layouts.py >/dev/null
mkdir -p data runs

GATES=("$@")
[ $# -eq 0 ] && GATES=(LT_NAND LT_NOR LT_EXOR LT_EXNOR)
for gate in "${GATES[@]}"; do
  case "$gate" in
    # ranges of the published SPE v1 spreadsheet: N/S/E 0.1..30 nm, W 0.01..1.8 nm
    LT_NAND|LT_NOR)
      run --qca "layouts/$gate.qca" --cell Z --gate "${gate/_/ }" --out "runs/$gate" --csv "data/spe_$gate.csv" \
          --north 0.1:30:0.1 --south 0.1:30:0.1 --east 0.1:30:0.1 --west 0.01:1.8:0.01 ;;
    # ranges reported for the LT Ex-OR / Ex-NOR output cell (Dhar et al. 2025)
    LT_EXOR|LT_EXNOR)
      run --qca "layouts/$gate.qca" --cell Z --gate "${gate/_/ }" --out "runs/$gate" --csv "data/spe_$gate.csv" \
          --north 0.1:4.6:0.1 --south 0.1:4.6:0.1 --east 0.1:3.4:0.1 --west 0.01:1.32:0.01 ;;
    *) echo "unknown gate $gate" >&2; exit 1 ;;
  esac
done
