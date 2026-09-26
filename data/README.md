# Generated datasets

One CSV per gate and output cell, one row per simulated layout (the defect-free layout
first, then one row per displacement of that output cell: `Z` for the LT gates, `Sum` or
`Cout` for the full adder). All rows were produced by `run_all.sh` / `simulate.sh`
(QCADesigner-E, coherence-vector engine with energy estimation, Gaussian clock,
`energy_options.txt`), from the layouts in `../layouts/`.

| File | Gate | Displacements of the output cell | Rows |
|---|---|---|---|
| `spe_LT_NAND.csv` | LT NAND (Dhar et al. 2024) | north, south, east 0.1…30 nm in 0.1 nm steps; west 0.01…1.8 nm in 0.01 nm steps | 1 + 1080 |
| `spe_LT_NOR.csv` | LT NOR (Dhar et al. 2024) | same | 1 + 1080 |
| `spe_LT_EXOR.csv` | LT Ex-OR (Dhar et al. 2025, layout reconstructed from its figure) | north, south 0.1…4.6 nm; east 0.1…3.4 nm; west 0.01…1.32 nm | 1 + 258 |
| `spe_LT_EXNOR.csv` | LT Ex-NOR (same) | same | 1 + 258 |
| `spe_FULLADDER_Sum.csv` | full adder, output `Sum` (`../layouts/FULLADDER.qca`, drawn in QCADesigner) | same | 1 + 258 |
| `spe_FULLADDER_Cout.csv` | full adder, output `Cout` | same | 1 + 258 |

The NAND/NOR ranges are those of the published SPE dataset (version 1); the
Ex-OR/Ex-NOR ranges are those reported for the output cell in the 2025 paper, and the
full adder uses the same ranges (the generator's defaults). The full adder's `Cout` has its
only neighbour 2 nm to the east, so its east rows beyond 2.0 nm have the two cells
overlapping (simulated all the same).

Two further files, `cumulative_LT_NAND.csv` and `cumulative_LT_NOR.csv` (151 rows each,
written by `tools/cumulative_replica.sh`), displace the output cell by the *cumulative*
distances 0.1+0.2+…+0.1n nm northwards (n = 1…60) and 0.01+0.02+…+0.01n nm westwards
(n = 1…90). They exist only to document the comparison with the published spreadsheet
(see the main README): the published row n corresponds to these distances, not to the
nominal 0.1n / 0.01n. Westward rows with `distance_nm` ≥ 2.1 have the output cell
overlapping or beyond its neighbour; the simulator then reports no output polarisation
(`status` = `ok-no-polarization`) and the energy of the remaining cells.

## Columns

| Column | Meaning |
|---|---|
| `gate` | gate name |
| `cell` | label of the displaced output cell (`Z` for the LT gates, `Sum` or `Cout` for the full adder) |
| `defect` | `none` for the defect-free layout, `displacement` otherwise |
| `direction` | `north`, `south`, `east`, `west` (empty for the defect-free row) |
| `distance_nm` | unsigned displacement in nanometres |
| `signed_displacement_nm` | negative for north and west, positive for south and east (the papers' sign convention) |
| `output_polarization_positive` | largest polarisation of the displaced output cell during the second half of the simulation (logic 1 plateau) |
| `output_polarization_negative` | smallest polarisation of the displaced output cell (logic 0 plateau) |
| `total_energy_eV` | `Sum_Ebath`: total energy dissipated to the bath, eV, as printed by QCADesigner-E |
| `total_energy_error_eV` | the error QCADesigner-E prints with it (sign included) |
| `avg_energy_per_cycle_eV` | `Avg_Ebath`: average energy dissipation per clock cycle, eV |
| `avg_energy_error_eV` | its error |
| `qca_file` | name of the layout file (regenerated under `runs/` by `run_all.sh`) |
| `status` | `ok` when both energies and both polarisations were read; `ok-no-polarization` when the simulator reported no output polarisation (overlapping cells); anything else quotes the simulator's error |
| `seconds` | wall-clock time of that simulation |

The columns map one-to-one onto the published SPE spreadsheet
("Direction of Cell Misalignment", "Shifting Distance from Base Position (nm)",
"Output Polarization_positive/_Negative", "Total Energy Dissipation (Sum_Ebath)",
"Average Energy Dissipation per cycle (Avg_Ebath)"); `tools/compare_spe_v1.py` performs
that comparison row by row.

## Regenerating

```bash
./run_all.sh              # all gates (3196 simulations)
./run_all.sh LT_NAND      # one gate
./simulate.sh layouts/FULLADDER.qca    # the full adder (or any other layout)
```

The script builds the Docker image with the patched simulator, regenerates the layouts,
runs every simulation (skipping rows already present) and rewrites these CSVs.
