#!/usr/bin/env bash
# Simulate a gate with the output cell displaced by the *cumulative* distances
# 0.1+0.2+...+0.1n nm northwards (n = 1..60) and 0.01+0.02+...+0.01n nm westwards (n = 1..90):
# the displacements that reproduce the rows of the published SPE v1 spreadsheet (see README).
#   tools/cumulative_replica.sh LT_NAND     -> data/cumulative_LT_NAND.csv
set -euo pipefail
cd "$(dirname "$0")/.."
GATE="${1:-LT_NAND}"
PY=$(command -v python3 || command -v python)
NORTH=$("$PY" -c "print(\",\".join(\"%.2f\" % (0.05*n*(n+1)) for n in range(1,61)))")
WEST=$("$PY" -c "print(\",\".join(\"%.3f\" % (0.005*n*(n+1)) for n in range(1,91)))")
if [ "$(uname -o 2>/dev/null)" = "Msys" ]; then export MSYS_NO_PATHCONV=1; HOST_DIR="$(pwd -W)"; else HOST_DIR="$PWD"; fi
docker run --rm -v "$HOST_DIR:/work" -w /work qde-batch \
  python3 qca_scdd_dataset.py --qca "layouts/$GATE.qca" --cell Z --gate "${GATE/_/ }" \
  --out "runs/cumulative_$GATE" --csv "data/cumulative_$GATE.csv" \
  --north "$NORTH" --south none --east none --west "$WEST" --batch-sim batch_sim --options energy_options.txt
