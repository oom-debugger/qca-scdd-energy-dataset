#!/usr/bin/env python3
"""
compare_spe_v1.py - compare CSVs produced by qca_scdd_dataset.py with the published
scdd_Polarisation_Energy (SPE) dataset, version 1 (Dhar et al. 2024: LT NAND and LT NOR,
2160 rows).  The reference spreadsheet is downloaded from the authors' GitHub repository
(or read from --xlsx) and parsed with the standard library only; nothing is redistributed.

    python3 tools/compare_spe_v1.py data/spe_LT_NAND.csv data/spe_LT_NOR.csv
    python3 tools/compare_spe_v1.py --export runs/spe_v1_reference.csv   # just convert to CSV

Rows are matched on (gate, direction, distance in nm); the report gives, per gate, how
many rows matched and the median / worst relative error of the two energies and the
absolute error of the two polarisations, plus the worst rows.
"""

import argparse
import csv
import io
import re
import sys
import zipfile

try:
    from urllib.request import urlopen
except ImportError:                       # Python 2
    from urllib2 import urlopen

SPE_V1_URL = ("https://raw.githubusercontent.com/manalidhar/"
              "scdd_Polarisation_Energy-SPE-Version-1-dataset/main/"
              "scdd_Polarisation_Energy%20(SPE)%20%5BVersion%201%5D%20dataset.xlsx")

# Table 3 of the paper (gaussian clock): defect-free total / average energy in eV
TABLE3 = {"lt nand": (0.000739, 0.0000672), "lt nor": (0.000953, 0.0000867)}

REF_COLUMNS = ["gate", "direction", "distance_nm", "signed_displacement_nm",
               "output_polarization_positive", "output_polarization_negative",
               "total_energy_eV", "avg_energy_per_cycle_eV"]


def norm_gate(name):
    return re.sub(r"[\s_-]+", " ", name.strip().lower()).replace("exor", "ex-or").replace("exnor", "ex-nor")


def load_reference(xlsx_bytes):
    """Parse sheet 1 of the SPE spreadsheet into a list of dict rows."""
    z = zipfile.ZipFile(io.BytesIO(xlsx_bytes))
    shared = re.findall(r"<si>(.*?)</si>", z.read("xl/sharedStrings.xml").decode("utf8"), re.S)
    shared = ["".join(re.findall(r"<t[^>]*>(.*?)</t>", s, re.S)) for s in shared]
    sheet = z.read("xl/worksheets/sheet1.xml").decode("utf8")
    rows, gate = [], None
    for r in re.findall(r"<row [^>]*>(.*?)</row>", sheet, re.S):
        cells = {}
        for ref, attrs, val in re.findall(r'<c r="([A-Z]+)\d+"([^>]*)>(?:<v>(.*?)</v>)?', r):
            if val == "":
                continue
            cells[ref] = shared[int(val)] if 't="s"' in attrs else val
        a = cells.get("A", "").strip()
        if a.upper().startswith("LT ") and "B" not in cells:
            gate = norm_gate(a)
            continue
        if a.upper() not in ("NORTH", "SOUTH", "EAST", "WEST"):
            continue
        signed = float(cells["B"])
        rows.append(dict(
            gate=gate, direction=a.lower(), distance_nm=round(abs(signed), 4), signed_displacement_nm=signed,
            output_polarization_positive=float(cells["C"]), output_polarization_negative=float(cells["D"]),
            total_energy_eV=float(cells["E"]), avg_energy_per_cycle_eV=float(cells["F"])))
    return rows


def load_ours(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return [row for row in csv.DictReader(fh)]


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def rel(a, b):
    return abs(a - b) / max(abs(b), 1e-30)


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else float("nan")


def compare(ours, ref):
    ref_index = {(r["gate"], r["direction"], r["distance_nm"]): r for r in ref}
    by_gate = {}
    for row in ours:
        if not row.get("status", "").startswith("ok"):
            continue
        g = norm_gate(row["gate"])
        by_gate.setdefault(g, {"ours": 0, "matched": 0, "e_tot": [], "e_avg": [], "p_pos": [], "p_neg": [], "worst": [], "baseline": None})
        st = by_gate[g]
        if row["defect"] == "none":
            st["baseline"] = row
            continue
        if row["defect"] != "displacement":
            continue
        st["ours"] += 1
        key = (g, row["direction"], round(float(row["distance_nm"]), 4))
        r = ref_index.get(key)
        if r is None:
            continue
        st["matched"] += 1
        tot, avg = fnum(row["total_energy_eV"]), fnum(row["avg_energy_per_cycle_eV"])
        pp, pn = fnum(row["output_polarization_positive"]), fnum(row["output_polarization_negative"])
        e1 = rel(tot, r["total_energy_eV"]) if tot is not None else float("nan")
        e2 = rel(avg, r["avg_energy_per_cycle_eV"]) if avg is not None else float("nan")
        st["e_tot"].append(e1)
        st["e_avg"].append(e2)
        if pp is not None:
            st["p_pos"].append(abs(pp - r["output_polarization_positive"]))
        if pn is not None:
            st["p_neg"].append(abs(pn - r["output_polarization_negative"]))
        st["worst"].append((e1, row["direction"], row["distance_nm"], tot, r["total_energy_eV"], pp, r["output_polarization_positive"]))
    return by_gate, ref_index


def report(by_gate, ref):
    n_ref = {}
    for r in ref:
        n_ref[r["gate"]] = n_ref.get(r["gate"], 0) + 1
    for g, st in sorted(by_gate.items()):
        print("=== %s: %d generated rows, %d in reference, %d matched ===" % (g, st["ours"], n_ref.get(g, 0), st["matched"]))
        if st["baseline"] is not None:
            b = st["baseline"]
            t3 = TABLE3.get(g)
            print("defect-free: total %s eV, average %s eV, P+ %s, P- %s" % (
                b["total_energy_eV"], b["avg_energy_per_cycle_eV"],
                b["output_polarization_positive"], b["output_polarization_negative"]))
            if t3 and fnum(b["total_energy_eV"]) is not None:
                print("  paper Table 3: total %g eV (%.1f%% off), average %g eV (%.1f%% off)" % (
                    t3[0], 100 * rel(float(b["total_energy_eV"]), t3[0]),
                    t3[1], 100 * rel(float(b["avg_energy_per_cycle_eV"]), t3[1])))
        if st["matched"]:
            print("relative error, total energy : median %.1f%%  max %.1f%%" % (100 * median(st["e_tot"]), 100 * max(st["e_tot"])))
            print("relative error, average energy: median %.1f%%  max %.1f%%" % (100 * median(st["e_avg"]), 100 * max(st["e_avg"])))
            if st["p_pos"]:
                print("abs error, +polarisation      : median %.3f  max %.3f" % (median(st["p_pos"]), max(st["p_pos"])))
            if st["p_neg"]:
                print("abs error, -polarisation      : median %.3f  max %.3f" % (median(st["p_neg"]), max(st["p_neg"])))
            print("worst rows (rel. error of total energy):")
            for e1, d, dist, tot, rtot, pp, rpp in sorted(st["worst"], key=lambda w: -w[0])[:5]:
                print("  %-5s %6s nm  ours %.4g eV  ref %.4g eV  (%.1f%%)  P+ ours %s ref %.3f" % (d, dist, tot, rtot, 100 * e1, pp, rpp))
        print()


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv", nargs="*", help="CSV files written by qca_scdd_dataset.py")
    p.add_argument("--xlsx", help="local copy of the SPE v1 spreadsheet (default: download it)")
    p.add_argument("--export", help="also write the reference rows as CSV to this path")
    args = p.parse_args(argv)

    if args.xlsx:
        with open(args.xlsx, "rb") as fh:
            data = fh.read()
    else:
        print("downloading %s" % SPE_V1_URL)
        data = urlopen(SPE_V1_URL).read()
    ref = load_reference(data)
    print("reference: %d rows" % len(ref))
    if args.export:
        with open(args.export, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=REF_COLUMNS)
            w.writeheader()
            w.writerows(ref)
        print("wrote %s" % args.export)
    ours = []
    for path in args.csv:
        ours += load_ours(path)
    if ours:
        by_gate, _ = compare(ours, ref)
        report(by_gate, ref)
    return 0


if __name__ == "__main__":
    sys.exit(main())
