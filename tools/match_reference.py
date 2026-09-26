#!/usr/bin/env python3
"""
match_reference.py - for every row of the published SPE v1 spreadsheet, find the
generated row (any direction, any distance) with the same polarisations and energy, and
test the hypothesis that the published rows were produced with a *cumulative*
displacement: row n (nominal 0.1*n nm) actually displaced by 0.1 + 0.2 + ... + 0.1*n =
0.05*n*(n+1) nm (for west, with 0.01 nm steps: 0.005*n*(n+1) nm).

    python3 tools/match_reference.py runs/spe_v1_reference.csv data/spe_LT_NAND.csv [--gate "lt nand"] [--out runs/match.csv]

A match is "exact" when both polarisations agree within 0.002 and the total energy
within 0.5 %.  The summary prints, per published direction, how many rows have an exact
match in the generated data at the cumulative distance, and how many rows match some
generated row at all.
"""

import argparse
import csv
import sys

TOL_P = 0.002
TOL_E = 0.005


def load(path, gate, generated):
    rows = []
    for r in csv.DictReader(open(path, newline="", encoding="utf-8")):
        g = r["gate"].strip().lower().replace("_", " ")
        if g != gate:
            continue
        if generated:
            if r.get("defect") != "displacement" or not r.get("status", "").startswith("ok"):
                continue
        try:
            rows.append((r["direction"].lower(), round(float(r["distance_nm"]), 3),
                         float(r["output_polarization_positive"]), float(r["output_polarization_negative"]),
                         float(r["total_energy_eV"])))
        except (ValueError, KeyError):
            continue
    return rows


def close(a, b):
    return abs(a[2] - b[2]) <= TOL_P and abs(a[3] - b[3]) <= TOL_P and abs(a[4] - b[4]) <= TOL_E * max(abs(b[4]), 1e-30)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("reference_csv", help="exported by tools/compare_spe_v1.py --export")
    p.add_argument("generated_csv")
    p.add_argument("--gate", default="lt nand")
    p.add_argument("--out", help="write the per-row matching table to this CSV")
    args = p.parse_args(argv)

    ref = load(args.reference_csv, args.gate, generated=False)
    gen = load(args.generated_csv, args.gate, generated=True)
    by_dir = {}
    for g in gen:
        by_dir.setdefault(g[0], {})[g[1]] = g
    print("%d reference rows, %d generated rows" % (len(ref), len(gen)))

    table = []
    stats = {}
    for r in ref:
        d, dist = r[0], r[1]
        step = 0.01 if d == "west" else 0.1
        n = int(round(dist / step))
        cumulative = round(step * n * (n + 1) / 2.0, 3)
        same = by_dir.get(d, {}).get(cumulative)
        cum_match = same is not None and close(r, same)
        nominal = by_dir.get(d, {}).get(dist)
        nom_match = nominal is not None and close(r, nominal)
        # closest generated row anywhere
        best = min(gen, key=lambda g: ((g[2] - r[2]) / 0.02) ** 2 + ((g[3] - r[3]) / 0.02) ** 2 + ((g[4] - r[4]) / 5e-6) ** 2)
        any_match = close(r, best)
        st = stats.setdefault(d, dict(rows=0, nominal=0, cumulative=0, any=0, isolated=0))
        st["rows"] += 1
        st["nominal"] += nom_match
        st["cumulative"] += cum_match
        st["any"] += any_match
        st["isolated"] += (abs(r[2]) > 0.999 and abs(r[3]) > 0.999)
        table.append(dict(direction=d, nominal_nm=dist, cumulative_nm=cumulative,
                          match_at_nominal=int(nom_match), match_at_cumulative=int(cum_match),
                          best_direction=best[0], best_distance_nm=best[1], best_is_match=int(any_match),
                          ref_pol_pos=r[2], ref_pol_neg=r[3], ref_total_eV=r[4],
                          best_pol_pos=best[2], best_pol_neg=best[3], best_total_eV=best[4]))
    for d in ("north", "south", "east", "west"):
        if d in stats:
            st = stats[d]
            print("%-5s rows=%4d  exact match at nominal distance: %4d   at cumulative distance: %4d   "
                  "at some generated row: %4d   isolated (|P|=1): %3d" % (d, st["rows"], st["nominal"], st["cumulative"], st["any"], st["isolated"]))
    if args.out:
        with open(args.out, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(table[0].keys()))
            w.writeheader()
            w.writerows(table)
        print("wrote", args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
