# qca-scdd-energy-dataset

Datasets and tooling for **single-cell displacement defect (SCDD) → energy dissipation**
in Layered-T (LT) quantum-dot cellular automata (QCA) gates, simulated with QCADesigner-E.

The repository regenerates from scratch the *scdd_Polarisation_Energy (SPE)* dataset of
Dhar et al. (2024) for the LT NAND and LT NOR gates, and applies the same procedure to the
LT Ex-OR and LT Ex-NOR gates of the 2025 follow-up. Everything needed to reproduce or
extend the data is here: the gate layouts, a patched command-line build of the
simulator, the generator script, and the CSVs themselves.

## The data

| File | Gate | Rows | What varies |
|---|---|---|---|
| [`data/spe_LT_NAND.csv`](data/spe_LT_NAND.csv) | LT NAND | 1081 | output cell moved north/south/east 0.1…30 nm (0.1 nm steps) and west 0.01…1.8 nm (0.01 nm steps), plus the defect-free layout |
| [`data/spe_LT_NOR.csv`](data/spe_LT_NOR.csv) | LT NOR | 1081 | same |
| [`data/spe_LT_EXOR.csv`](data/spe_LT_EXOR.csv) | LT Ex-OR | 259 | north/south 0.1…4.6 nm, east 0.1…3.4 nm, west 0.01…1.32 nm, plus the defect-free layout |
| [`data/spe_LT_EXNOR.csv`](data/spe_LT_EXNOR.csv) | LT Ex-NOR | 259 | same |
| `data/cumulative_LT_NAND.csv`, `data/cumulative_LT_NOR.csv` | LT NAND, LT NOR | 151 each | output cell at the *cumulative* distances 0.05·n(n+1) nm north (n ≤ 60) and 0.005·n(n+1) nm west (n ≤ 90); reproduces the published spreadsheet, see below |

Each row holds the direction and distance of the displacement, the positive and negative
output polarisation, the total energy dissipation (`Sum_Ebath`) and the average energy
dissipation per clock cycle (`Avg_Ebath`) in electron-volts, exactly as QCADesigner-E
reports them. Column definitions are in [`data/README.md`](data/README.md).

**Validation against the published numbers.** The defect-free rows agree exactly with
the paper's Table 3 and with the first rows of the published spreadsheet: LT NAND total
7.39e-4 eV, average 6.72e-5 eV, polarisations +0.954 / −0.948; LT NOR 9.53e-4 eV,
8.67e-5 eV, +0.948 / −0.954. This confirms the layouts, the simulator build, the options
and the polarisation read-out.

**Comparison with the published SPE dataset (version 1).** The displaced rows do *not*
agree at the nominal distances: only the first two or three rows of each direction do
(LT NAND north: 3 of 300). Instead, every published north/south row n (nominal 0.1·n nm)
coincides, to three significant digits in both polarisations and the energy, with our
row at the **cumulative** distance 0.1 + 0.2 + … + 0.1·n = 0.05·n(n+1) nm. For LT NAND
this holds for all 41 rows up to n = 41 (`tools/match_reference.py`,
`tools/cumulative_replica.sh`, `data/cumulative_LT_NAND.csv`); for LT NOR the same curve is
followed within a few per cent in energy and typically 0.01–0.04 in polarisation (more
at the sharp dip near n = 11–12), and its east series matches the cumulative distances
exactly for nominal 0.1…2.1 nm. From n = 42 on, the accumulated
displacement (≥ 90 nm) exceeds the simulator's 80 nm radius of effect, the output cell no
longer interacts with the circuit, and the published rows show the corresponding constant
energy (6.56e-4 eV for NAND, 7.25e-4 eV for NOR) with the polarisations recorded as
±1.000: 259 of the 300 rows of each north and south series, 226 (NAND) / 266 (NOR) of the
east series and 26 / 27 of the 180 west series are of this kind. The published west rows
follow cumulative 0.01 nm steps for the first eight rows and then become irregular, with
the output cell having moved past its neighbour (energies from 2e-5 to 4.8e-3 eV). The
simplest explanation is that each displaced layout was produced by translating the
*previous* layout by the new nominal step instead of translating the original, so the
"shifting distance" column of the published dataset does not describe the simulated
geometry. The CSVs here displace the original layout by exactly the nominal distance,
as the papers describe, which is why they differ from the published rows beyond the first
few; the two `data/cumulative_*.csv` files reproduce the published rows for reference.

## Background

A QCA circuit is a grid of 18 nm cells drawn in [QCADesigner](https://github.com/kwalus/QCADesigner);
[QCADesigner-E](https://github.com/FSillT/QCADesigner-E) adds an estimate of the energy
the circuit dissipates (coherence-vector engine with energy accounting). Dhar et al.
asked how the energy dissipation and the output polarisation of LT gates change when the
output cell is fabricated slightly out of place: move it north/south/east in 0.1 nm steps
and west in 0.01 nm steps (west is finer because the neighbouring cell is only 2 nm
away), simulate every displaced copy, and tabulate direction, distance, polarisations and
energies; machine-learning models are then trained on the table.

## Reproducing everything

Requirements: Docker and Python 3 on the host (the simulator is built inside a Linux
container; the generator itself is standard-library Python and also runs on Windows).

```bash
./run_all.sh              # builds the image, writes the layouts, runs 2678 simulations (~15 min)
./run_all.sh LT_EXOR      # one gate
python3 tools/compare_spe_v1.py data/spe_LT_NAND.csv data/spe_LT_NOR.csv   # against the published data
```

Without Docker, on Debian/Ubuntu or WSL:

```bash
sudo apt install -y build-essential pkg-config gettext intltool libglib2.0-dev libgtk2.0-dev git python3
tools/build_batch_sim.sh                     # clones QCADesigner-E, applies the patch, builds src/batch_sim
python3 layouts/make_lt_layouts.py
python3 qca_scdd_dataset.py --qca layouts/LT_NAND.qca --cell Z --gate "LT NAND" --out runs/lt_nand \
    --batch-sim ~/QCADesigner-E/QCADesignerE/src/batch_sim --resume
```

## Contents

| Path | Purpose |
|---|---|
| `data/` | the generated CSVs (see above) |
| `layouts/make_lt_layouts.py` | writes the four gate layouts as QCADesigner `.qca` files (`layouts/*.qca` are its output) |
| `qca_scdd_dataset.py` | the generator: parses a `.qca` file, writes one displaced copy per (direction, distance) — optionally copies with a cell removed — runs the simulator on each and collects the CSV; `--list-cells` inspects a layout |
| `energy_options.txt` | options of the *Coherence Vector (w/ Energy)* engine in the format `batch_sim -o` reads (QCADesigner-E's defaults, Gaussian clock) |
| `qcadesigner_e_batch.patch` | patch for QCADesigner-E's source, see below; applies cleanly to upstream `master` |
| `docker/Dockerfile` | Ubuntu 22.04 image with the patched `batch_sim` on the PATH |
| `run_all.sh` | regenerates every dataset (build image → layouts → simulations → CSVs), resumable |
| `tools/compare_spe_v1.py` | downloads the published SPE spreadsheet and compares it with the CSVs row by row (`--export` writes it as CSV) |
| `tools/match_reference.py` | for every published row, finds the generated row with the same polarisations and energy and tests the cumulative-displacement explanation |
| `tools/cumulative_replica.sh` | simulates a gate at the cumulative distances (writes `data/cumulative_<GATE>.csv`) |
| `tools/build_batch_sim.sh` | native (non-Docker) build of the patched simulator |

## How the data was produced

**Layouts.** LT NAND and LT NOR follow Fig. 3, Fig. 4 and Fig. 7 of the 2024 paper:
18 × 18 nm cells on a 20 nm pitch, dots 4.5 nm from the centre, dot diameter 4 nm
(Table 1); layer 1 holds input A, input B, one normal cell and the output Z; layer 2
holds one fixed-polarisation cell directly above the empty slot between A and B
(P = +1 → NAND, P = −1 → NOR); all cells in clock zone 0. LT Ex-OR and LT Ex-NOR were
reconstructed cell by cell from Fig. 2 of the 2025 paper: four LT gates realising
Z = L⁺(L⁺(A, L⁺(A,B)), L⁺(B, L⁺(A,B))) with all four fixed cells at +1, 26 cells in three
clock zones (the figure's colours: green 0, magenta 1, cyan 2); the Ex-NOR adds a
corner-coupled (inverting) step before its output, 28 cells. The 26-cell count matches
the "18.75 % fewer cells than the 32-cell majority-voter version" stated for that design.
Clock zones of input and output cells are not visible in the figure and were set to the
zone of the adjacent wire. `python3 layouts/make_lt_layouts.py` prints an ASCII map of
each layout.

**Displacement.** The output cell (its four dots and its label) is shifted in the `.qca`
text; QCADesigner's y axis grows downwards on screen, so *north* is a decrease of y. The
signed displacement is negative for north and west, positive for south and east, as in
the papers.

**Simulation.** `batch_sim -f layout.qca -e COHERENCE_VECTOR_ENERGY -o energy_options.txt -n 1 -t 0`
(one run, no random perturbation, exhaustive input vectors): temperature 1 K, relaxation
1e-15 s, time step 1e-16 s, duration 50e-12 s, clock 9.8e-22 / 3.8e-23 J, clock and input
period 4e-12 s, Gaussian clock with 1e-12 s slopes, radius of effect 80 nm, εr 12.9,
layer separation 11.5 nm, Euler integration, zeroing of inputs on. These are
QCADesigner-E's defaults and reproduce the published numbers.

**Polarisation.** The patched `batch_sim` prints, for every output cell, the largest and
smallest polarisation over the whole simulation and over its second half; the CSV uses
the second-half values (the papers read the plateaus off the waveform in the GUI).

**Energies.** Taken verbatim from QCADesigner-E's summary lines
`Total energy dissipation (Sum_Ebath)` and `Average energy dissipation per cycle (Avg_Ebath)`,
including the error it prints (which can be negative, as in the paper's Table 3).

## What the patch fixes

Stock QCADesigner-E cannot run the energy engine from the command line at all, for three
independent reasons; the patch (`qcadesigner_e_batch.patch`, about 140 lines touching
`fileio.c`, `main_batch_sim.c` and `Makefile.am`) fixes them and adds one feature:

1. `batch_sim` tests the engine name against `COHERENCE_VECTOR` before
   `COHERENCE_VECTOR_ENERGY`, so `-e COHERENCE_VECTOR_ENERGY` selected the plain engine
   and then rejected the options file. The longer name is now tested first.
2. The options-file parser for the energy engine started from an all-zero structure and
   ignored eight of its keys (`clock_period`, `input_period`, `t_slope_ramp`, `clock_type`,
   `zero_mode_act`, `display_cell_diss`, `diss_trace_cood_x/y`); a zero clock period breaks
   the engine. It now starts from the GUI defaults and parses every key.
3. `batch_sim` was not listed in `bin_PROGRAMS`, so `make` did not build it.
4. After each run, the polarisation range of every output cell is printed
   (`output_polarization[LABEL] max=… min=… steady_max=… steady_min=…`).

## Status and limitations

* The LT NAND and LT NOR layouts and settings are validated against the published
  numbers (see above). The Ex-OR and Ex-NOR layouts are reconstructions from a figure:
  cell positions and the zones of the wires are unambiguous, the zones of the input and
  output cells are assumed, and no published absolute energy value was available to check
  them against.
* The 4-bit LT binary-to-gray converter of the 2025 paper is not included (its layout was
  not available), nor are other defect types (rotation, misalignment, multi-cell
  displacement), nor the machine-learning step (KNN / random forest / polynomial
  regression with r², MAE, MSE, RMSE).
* The generator handles any `.qca` layout and any labelled cell, so other gates can be
  added by drawing them in QCADesigner (or describing them in `make_lt_layouts.py`) and
  adding a line to `run_all.sh`.

## License

GPL-3.0-or-later. `qcadesigner_e_batch.patch` modifies QCADesigner-E, which is distributed
under the GPL; the rest of the repository is licensed the same way for simplicity. The
published SPE spreadsheet is the property of its authors and is only downloaded on
demand by `tools/compare_spe_v1.py`, never redistributed here.

## References

* M. Dhar, C. Mukherjee, A. Banerjee, D. Manna, S. Panda, B. Maji, "Predicting Energy
  Dissipation in QCA-Based Layered-T Gates Under Cell Defects and Polarisation: A Study
  with Machine-Learning Models", *Journal of Electronic Testing* 40, 435–455 (2024).
  https://doi.org/10.1007/s10836-024-06133-7
* M. Dhar et al., "Predictive analysis of energy dissipation in Layered-T QCA circuits
  under cell displacement defects and polarization: A machine-learning approach",
  *Integration* (2025). https://www.sciencedirect.com/science/article/pii/S0167926025002949
* SPE dataset, version 1:
  https://github.com/manalidhar/scdd_Polarisation_Energy-SPE-Version-1-dataset
* F. Sill Torres et al., QCADesigner-E: https://github.com/FSillT/QCADesigner-E
  (manual: `Manual_QDE.pdf` in that repository)
* K. Walus, T. J. Dysart, G. A. Jullien, R. A. Budiman, "QCADesigner: A Rapid Design and
  Simulation Tool for Quantum-Dot Cellular Automata", *IEEE Trans. Nanotechnology* 3(1),
  26–31 (2004).
