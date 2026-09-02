# qca-scdd-energy-dataset

Tooling to build **single-cell displacement defect (SCDD) → energy dissipation** datasets
for quantum-dot cellular automata (QCA) layouts, using QCADesigner-E as the simulator.
It reproduces the data-generation step behind the *scdd_Polarisation_Energy (SPE)*
dataset of Dhar et al. (2024, 2025), so that the dataset can be regenerated, extended to
other gates, and audited.

## Background

A QCA circuit is a grid of 18 nm cells drawn in [QCADesigner](https://github.com/kwalus/QCADesigner);
[QCADesigner-E](https://github.com/FSillT/QCADesigner-E) extends it with an estimate of
the energy the circuit dissipates (coherence-vector engine with energy accounting).
Dhar et al. asked how the energy dissipation and the output polarisation of Layered-T (LT)
logic gates change when the *output cell* is fabricated slightly out of place:

1. take a defect-free `.qca` layout of the gate,
2. move the output cell north/south/east in 0.1 nm steps and west in 0.01 nm steps
   (west is finer because the neighbouring cell is only 2 nm away),
3. simulate every displaced copy in QCADesigner-E,
4. record direction, distance, output polarisation (+ and −), total energy dissipation
   (`Sum_Ebath`) and average energy dissipation per clock cycle (`Avg_Ebath`),
5. train KNN / random-forest / polynomial-regression models on the table.

The published SPE dataset (version 1) covers the LT NAND and LT NOR gates with 2160 rows;
the 2025 follow-up applies the same procedure to LT Ex-OR, LT Ex-NOR and a 4-bit LT
binary-to-gray converter (BTG, output cells `G0`–`G3`). This repository automates steps
1–4 for any `.qca` layout and any labelled cell.

## Dataset format

One row per simulated layout. The columns mirror the published SPE dataset and add
bookkeeping fields:

| SPE dataset column | column in `spe_dataset.csv` |
|---|---|
| Direction of Cell Misalignment | `direction` (`north` / `south` / `east` / `west`) |
| Shifting Distance from Base Position (nm) | `distance_nm` (unsigned) and `signed_displacement_nm` (north/west negative, south/east positive, as in the papers) |
| Output Polarization_positive / _Negative | `output_polarization_positive`, `output_polarization_negative` |
| Total Energy Dissipation (Sum_Ebath) | `total_energy_eV` (+ `total_energy_error_eV`) |
| Average Energy Dissipation per cycle (Avg_Ebath) | `avg_energy_per_cycle_eV` (+ `avg_energy_error_eV`) |
| — | `gate`, `cell`, `defect` (`none` / `displacement` / `missing`), `qca_file`, `status`, `seconds` |

Energies are in electron-volts exactly as printed by QCADesigner-E. A `manifest.csv`
next to the generated layouts records every variant (file, cell, direction, dx, dy, new
coordinates), so the layouts can also be simulated by hand in the GUI.

Displacement ranges used in the literature (nm): LT NAND, output cell — east 0.1…7.4,
west 0.01…1.54, north 0.1…4.1, south 0.1…4.1; LT NOR — east 0.1…3.4, west 0.01…1.53,
north/south as NAND (Dhar et al. 2024, eq. 7). LT Ex-OR / Ex-NOR, cell `Z` — north and
south 0.1…4.6, east 0.1…3.4, west 0.01…1.32 (these are the script's defaults). BTG —
per output cell, north up to 8.1 / 8.1 / 5.9 / 3.8 and south up to 4.6 / 7.2 / 9.1 / 10.2
for `G0`…`G3`, east up to 3.4, west up to roughly 0.4–0.6 (Dhar et al. 2025).

## Contents

| File | Purpose |
|---|---|
| `qca_scdd_dataset.py` | The generator. Parses a `.qca` file, writes one displaced copy per (direction, distance) — optionally also copies with a cell removed — runs QCADesigner-E's batch simulator on each copy and collects the CSV. Python 3.6+, standard library only. |
| `energy_options.txt` | Options for the *Coherence Vector (w/ Energy)* engine in the format `batch_sim -o` reads (QCADesigner-E defaults; the papers' Table 2 settings are noted in comments). |
| `qcadesigner_e_batch.patch` | Patch for QCADesigner-E's source (three small hunks): makes the command-line simulator parse **all** energy options (the stock parser ignores eight of them and leaves them at zero, which breaks the energy engine), prints the output-cell polarisation after each run, and adds `batch_sim` to the build. Applies cleanly to upstream `master`. |
| `LICENSE` | GPL-3.0-or-later. |

## Status — what is here and what is missing

Done:

* Layout parsing and displacement, verified on QCADesigner-E's own example circuits
  (multi-layer files with labels, fixed-polarisation, input and output cells). Every
  generated file is re-parsed and checked: exactly the target cell moved, by exactly the
  requested amount, and nothing else changed.
* The full pipeline (layouts → simulator calls → CSV, with `--resume`) exercised against
  a stand-in simulator that reproduces `batch_sim`'s command line and output format.
* The patch applies cleanly to the current QCADesigner-E `master` (`git apply --check`).

Missing / to do:

1. **Layout files.** No `.qca` layouts are included; the LT gate layouts used in the
   papers are not distributed. Draw them in QCADesigner 2.0.3 or QCADesigner-E (an LT
   gate is two layers: the device cell with a fixed-polarisation cell directly above it)
   and give the output cell a label (`Z`, `G0`…). Contributions of layouts are welcome.
2. **The dataset itself.** This repository is the generator, not the data. Running it on
   the LT Ex-OR, LT Ex-NOR and BTG layouts produces the CSVs.
3. **Validation against the real simulator.** The patched `batch_sim` has not yet been
   compiled and run here (it builds only on Linux). The first real run should compare the
   defect-free baseline row with Table 3 of the 2024 paper (LT NAND, Gaussian clock:
   total ≈ 7.39e-4 eV, average ≈ 6.72e-5 eV) before generating thousands of rows.
4. **Polarisation definition.** The patch reports the max/min of the output-cell trace
   over the second half of the simulation; the papers read the + and − plateaus off the
   waveform in the GUI. Confirm the two agree on the baseline layout.
5. **Other defects and the ML step.** Only single-cell displacement (plus an optional
   "missing cell") is implemented — no rotation, misalignment or multi-cell defects — and
   the KNN / RF / polynomial-regression training with r², MAE, MSE, RMSE is not included.

## Requirements

* Python 3.6+ (layout generation works on any OS).
* Linux (or WSL) with a C toolchain and GTK2/GLib development headers to build the
  patched QCADesigner-E `batch_sim`; the Windows installer of QCADesigner-E ships the
  GUI only.

## Setup

```bash
sudo apt install build-essential autoconf automake libtool pkg-config gettext \
                 libglib2.0-dev libgtk2.0-dev git python3
git clone https://github.com/FSillT/QCADesigner-E.git
cd QCADesigner-E
git apply /path/to/qca-scdd-energy-dataset/qcadesigner_e_batch.patch
cd QCADesignerE
./autogen.sh && ./configure --prefix=$HOME/qde && make
ls -l src/batch_sim          # the command-line simulator
```

If `autogen.sh` does not cooperate with modern autotools, the repository already ships a
generated `configure` and `Makefile.in` that contain a `batch_sim` rule, so
`./configure && make -C src batch_sim` is an alternative.

## Usage

Inspect a layout (cell indices, functions, labels, layers, coordinates):

```bash
python3 qca_scdd_dataset.py --qca LT_ExOR.qca --list-cells
```

Generate the displaced layouts only (no simulator needed):

```bash
python3 qca_scdd_dataset.py --qca LT_ExOR.qca --cell Z --gate "LT Ex-OR" --out runs/ltexor
```

Generate, simulate and build the CSV (LT Ex-OR / Ex-NOR ranges are the defaults:
258 displaced layouts + 1 baseline per gate):

```bash
python3 qca_scdd_dataset.py --qca LT_ExOR.qca --cell Z --gate "LT Ex-OR" --out runs/ltexor \
    --batch-sim ~/QCADesigner-E/QCADesignerE/src/batch_sim --options energy_options.txt --resume
```

4-bit LT BTG, one run per output cell (raise `duration` in `energy_options.txt` to at
least 100e-12 s first — with 4 inputs one pass over the truth table takes 32e-12 s):

```bash
python3 qca_scdd_dataset.py --qca LT_BTG.qca --cell G0 --gate "LT BTG" --out runs/btg_g0 \
    --north 0.1:8.1:0.1 --south 0.1:4.6:0.1 --east 0.1:3.4:0.1 --west 0.01:0.4:0.01 \
    --batch-sim ~/QCADesigner-E/QCADesignerE/src/batch_sim --resume
```

Other flags: `--missing SUM,#12` also writes layouts with those cells deleted;
`--polarization trace` reads the polarisation from QCADesigner-E's trace file instead of
the patched stdout line; `--keep-logs` keeps every simulator's full output; `--timeout`
caps one simulation (default 2 h); `--csv` chooses the output file. Ranges accept
`start:stop:step`, a comma list, or `none`.

Runtime: one energy simulation integrates `duration / time_step` (500 000 time steps by
default) for every cell, so expect seconds to minutes per layout; `--resume` lets a run be
stopped and continued.

## How it works

* A `.qca` file is plain text: each cell is a `[TYPE:QCADCell]` block with its centre
  (`x=`, `y=`), bounding box, four `[TYPE:CELL_DOT]` blocks and, for inputs/outputs, a
  `[TYPE:QCADLabel]`. The script shifts every coordinate line inside the target block and
  leaves the rest of the file byte-for-byte unchanged (line endings included).
* QCADesigner's y axis grows downwards on screen, so *north* is implemented as
  *y decreases* and *south* as *y increases*; east/west change x.
* The simulator is invoked as
  `batch_sim -f layout.qca -e COHERENCE_VECTOR_ENERGY -o options -n 1 -t 0`
  (one run, no random perturbation). In a non-GUI build QCADesigner-E's messages go to
  stderr, so the script parses `Total energy dissipation (Sum_Ebath): … eV (Error: +/- … eV)`
  and `Average energy dissipation per cycle (Avg_Ebath): …` from there, and the
  `output_polarization[LABEL] max=… min=… steady_max=… steady_min=…` line the patch adds
  from stdout.
* With `--polarization trace` the per-run options ask QCADesigner-E to log the target cell
  (`diss_trace_cood_x/y`); the engine matches cells by integer-truncated coordinates, so a
  cell in another layer with the same truncated x/y would be mixed in, and the file is
  about 500 000 lines per run (deleted after parsing).
* `energy_options.txt` uses QCADesigner-E's defaults (1 K, relaxation 1e-15 s, time step
  1e-16 s, duration 50e-12 s, clock 9.8e-22 / 3.8e-23 J, Gaussian clock, radius of effect
  80 nm, εr 12.9, layer separation 11.5 nm). The papers additionally used a 10e-12 s input
  period. The QCADesigner-E manual notes that with `zero_mode_act=TRUE` the input cells and
  their neighbours must be in matching clock zones.

## License

GPL-3.0-or-later. `qcadesigner_e_batch.patch` modifies QCADesigner-E, which is distributed
under the GPL; the rest of the repository is licensed the same way for simplicity.

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
