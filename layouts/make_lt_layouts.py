#!/usr/bin/env python3
"""
make_lt_layouts.py - write QCADesigner 2.0 ``.qca`` layouts of Layered-T (LT) gates:

* LT NAND and LT NOR, from Dhar et al. 2024 (Fig. 3, Fig. 4b/d, Fig. 7, Table 1);
* LT Ex-OR and LT Ex-NOR, reconstructed cell by cell from Fig. 2b/d of the
  2025 follow-up (four LT gates: Z = L+(L+(A, L+(A,B)), L+(B, L+(A,B))); the Ex-NOR
  adds a corner-coupled (inverting) step before the output cell).

Geometry (nanometres, QCADesigner screen coordinates, y grows downwards):

* 18 x 18 nm cells on a 20 nm pitch (2 nm spacing); quantum dots 4.5 nm from the
  cell centre (QCADesigner's placement for 18 nm cells); dot diameter 4 nm (Table 1).
* An LT gate: inputs at (col, row-1) and (col, row+1), the fixed-polarisation cell at
  (col, row) on the SECOND cell layer (directly above the empty slot of layer 1), a
  normal cell at (col+1, row) and the output at (col+2, row).  P = +1 gives NAND
  (used by all four gates of the Ex-OR/Ex-NOR), P = -1 gives NOR.
* Clock zones are the colours of the figures: green 0, magenta 1, cyan 2.  Input
  cells take the zone of the wire they drive, output cells the zone of the cell that
  drives them, fixed cells the zone of their gate (irrelevant to the simulation).

Usage::

    python3 make_lt_layouts.py                 # writes LT_NAND/LT_NOR/LT_EXOR/LT_EXNOR .qca here
    python3 make_lt_layouts.py --out dir --gates LT_NAND LT_EXOR
    python3 make_lt_layouts.py --via-layer     # 3-layer variant: empty via layer between the cell layers
"""

import argparse
import os

E_CHARGE = 1.602176e-19        # electron charge as QCADesigner writes it
HALF = 8.010882e-20            # charge per dot of an unpolarised cell (P = 0)

CELL = 18.0
PITCH = 20.0
DOT_OFFSET = 4.5
X0, Y0 = 100.0, 100.0          # position of grid column 1 / row 1

COLORS = {                     # cosmetic (clr.red/green/blue), like the GUI's defaults
    "INPUT": (0, 0, 65535),
    "OUTPUT": (65535, 65535, 0),
    "FIXED": (65535, 32767, 0),
    "NORMAL": (0, 65535, 0),
}

# (col, row, function, clock[, label]) for layer 1; (col, row, polarisation, clock) for layer 2.
LT_NAND = dict(
    layer1=[(1, 1, "INPUT", 0, "A"), (1, 3, "INPUT", 0, "B"), (2, 2, "NORMAL", 0), (3, 2, "OUTPUT", 0, "Z")],
    layer2=[(1, 2, +1, 0)],
)
LT_NOR = dict(layer1=LT_NAND["layer1"], layer2=[(1, 2, -1, 0)])

_EXOR_LAYER1 = [
    (1, 3, "INPUT", 0, "A"), (1, 5, "INPUT", 0, "B"),
    # wire carrying A to the upper gate
    (1, 2, "NORMAL", 0), (1, 1, "NORMAL", 0), (2, 1, "NORMAL", 0), (3, 1, "NORMAL", 1),
    # wire carrying B to the lower gate
    (1, 6, "NORMAL", 0), (1, 7, "NORMAL", 0), (2, 7, "NORMAL", 0), (3, 7, "NORMAL", 1),
    # gate 1 = L+(A, B): normal cell and output, fanned out up and down
    (2, 4, "NORMAL", 0), (3, 4, "NORMAL", 1), (3, 3, "NORMAL", 1), (3, 5, "NORMAL", 1),
    # gate 2 = L+(A, gate 1) and gate 3 = L+(B, gate 1)
    (4, 2, "NORMAL", 1), (5, 2, "NORMAL", 1), (4, 6, "NORMAL", 1), (5, 6, "NORMAL", 1),
    # gate 4 = L+(gate 2, gate 3): its inputs and normal cell
    (5, 3, "NORMAL", 2), (5, 5, "NORMAL", 2), (6, 4, "NORMAL", 2),
]
_EXOR_LAYER2 = [(1, 4, +1, 0), (3, 2, +1, 1), (3, 6, +1, 1), (5, 4, +1, 2)]

LT_EXOR = dict(layer1=_EXOR_LAYER1 + [(7, 4, "OUTPUT", 2, "Z")], layer2=_EXOR_LAYER2)
LT_EXNOR = dict(
    layer1=_EXOR_LAYER1 + [(7, 4, "NORMAL", 2), (8, 5, "NORMAL", 2), (9, 5, "OUTPUT", 2, "Z")],
    layer2=_EXOR_LAYER2,
)

GATES = {"LT_NAND": LT_NAND, "LT_NOR": LT_NOR, "LT_EXOR": LT_EXOR, "LT_EXNOR": LT_EXNOR}


def grid(col, row):
    return X0 + PITCH * (col - 1), Y0 + PITCH * (row - 1)


def label_block(x, y, text, color):
    r, g, b = color
    return (
        "[TYPE:QCADLabel]\n"
        "[TYPE:QCADStretchyObject]\n"
        "[TYPE:QCADDesignObject]\n"
        "x=%.6f\ny=%.6f\nbSelected=FALSE\nclr.red=%d\nclr.green=%d\nclr.blue=%d\n"
        "bounding_box.xWorld=%.6f\nbounding_box.yWorld=%.6f\n"
        "bounding_box.cxWorld=%.6f\nbounding_box.cyWorld=%.6f\n"
        "[#TYPE:QCADDesignObject]\n"
        "[#TYPE:QCADStretchyObject]\n"
        "psz=%s\n"
        "[#TYPE:QCADLabel]\n"
        % (x + 8.0, y - 20.242757, r, g, b, x - 9.0, y - 31.742757, 34.0, 23.0, text)
    )


def cell_block(x, y, function, clock=0, label=None, polarization=None, dot_diameter=4.0):
    """One [TYPE:QCADCell] block in the exact key order QCADesigner writes."""
    r, g, b = COLORS[function]
    if function == "FIXED":
        if polarization not in (1, -1):
            raise ValueError("fixed cell needs polarization +1 or -1")
        # dots are listed top-right, bottom-right, bottom-left, top-left; QCADesigner's
        # polarisation is (q0 + q2 - q1 - q3) / total, so P = +1 charges dots 0 and 2.
        charges = [E_CHARGE, 0.0, E_CHARGE, 0.0] if polarization == 1 else [0.0, E_CHARGE, 0.0, E_CHARGE]
        if label is None:
            label = "%.2f" % polarization
    else:
        charges = [HALF] * 4
    dots = [(x + DOT_OFFSET, y - DOT_OFFSET), (x + DOT_OFFSET, y + DOT_OFFSET),
            (x - DOT_OFFSET, y + DOT_OFFSET), (x - DOT_OFFSET, y - DOT_OFFSET)]
    out = [
        "[TYPE:QCADCell]",
        "[TYPE:QCADDesignObject]",
        "x=%.6f" % x,
        "y=%.6f" % y,
        "bSelected=FALSE",
        "clr.red=%d" % r, "clr.green=%d" % g, "clr.blue=%d" % b,
        "bounding_box.xWorld=%.6f" % (x - CELL / 2),
        "bounding_box.yWorld=%.6f" % (y - CELL / 2),
        "bounding_box.cxWorld=%.6f" % CELL,
        "bounding_box.cyWorld=%.6f" % CELL,
        "[#TYPE:QCADDesignObject]",
        "cell_options.cxCell=%.6f" % CELL,
        "cell_options.cyCell=%.6f" % CELL,
        "cell_options.dot_diameter=%.6f" % dot_diameter,
        "cell_options.clock=%d" % clock,
        "cell_options.mode=QCAD_CELL_MODE_NORMAL",
        "cell_options.ignore_energy=FALSE",
        "cell_function=QCAD_CELL_%s" % function,
        "number_of_dots=4",
    ]
    for (dx, dy), q in zip(dots, charges):
        out += ["[TYPE:CELL_DOT]", "x=%.6f" % dx, "y=%.6f" % dy,
                "diameter=%.6f" % dot_diameter, "charge=%e" % q,
                "spin=0.000000", "potential=0.000000", "[#TYPE:CELL_DOT]"]
    text = "\n".join(out) + "\n"
    if label is not None:
        text += label_block(x, y, label, (r, g, b))
    return text + "[#TYPE:QCADCell]\n"


def layer_block(name, cells_text):
    return ("[TYPE:QCADLayer]\ntype=1\nstatus=0\npszDescription=%s\n" % name
            + cells_text + "[#TYPE:QCADLayer]\n")


HEADER = (
    "[VERSION]\nqcadesigner_version=2.000000\n[#VERSION]\n"
    "[TYPE:DESIGN]\n"
    "[TYPE:QCADLayer]\ntype=3\nstatus=2\npszDescription=Drawing Layer\n[#TYPE:QCADLayer]\n"
    "[TYPE:QCADLayer]\ntype=0\nstatus=2\npszDescription=Substrate\n"
    "[TYPE:QCADSubstrate]\n[TYPE:QCADStretchyObject]\n[TYPE:QCADDesignObject]\n"
    "x=3000.000000\ny=1500.000000\nbSelected=FALSE\nclr.red=65535\nclr.green=65535\nclr.blue=65535\n"
    "bounding_box.xWorld=0.000000\nbounding_box.yWorld=0.000000\n"
    "bounding_box.cxWorld=6000.000000\nbounding_box.cyWorld=3000.000000\n"
    "[#TYPE:QCADDesignObject]\n[#TYPE:QCADStretchyObject]\ngrid_spacing=20.000000\n"
    "[#TYPE:QCADSubstrate]\n[#TYPE:QCADLayer]\n"
)
FOOTER = "[#TYPE:DESIGN]\n"


def build(gate, dot_diameter=4.0, via_layer=False):
    l1 = ""
    for spec in gate["layer1"]:
        col, row, function, clock = spec[:4]
        label = spec[4] if len(spec) > 4 else None
        x, y = grid(col, row)
        l1 += cell_block(x, y, function, clock, label, dot_diameter=dot_diameter)
    l2 = ""
    for col, row, pol, clock in gate["layer2"]:
        x, y = grid(col, row)
        l2 += cell_block(x, y, "FIXED", clock, polarization=pol, dot_diameter=dot_diameter)
    text = HEADER + layer_block("Main Cell Layer", l1)
    if via_layer:
        text += layer_block("VIA1", "")
    return text + layer_block("LAYER2", l2) + FOOTER


def ascii_map(gate):
    """Text picture of the layout: A/B inputs, Z output, F fixed (layer 2), digits = clock."""
    cells = {}
    for spec in gate["layer1"]:
        col, row, function, clock = spec[:4]
        label = spec[4] if len(spec) > 4 else None
        cells[(col, row)] = label if function in ("INPUT", "OUTPUT") else str(clock)
    for col, row, pol, clock in gate["layer2"]:
        cells[(col, row)] = "F" if pol > 0 else "f"
    cols = max(c for c, r in cells)
    rows = max(r for c, r in cells)
    lines = []
    for r in range(1, rows + 1):
        lines.append(" ".join(cells.get((c, r), ".") for c in range(1, cols + 1)))
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", default=os.path.dirname(os.path.abspath(__file__)))
    p.add_argument("--gates", nargs="+", default=sorted(GATES), choices=sorted(GATES))
    p.add_argument("--dot-diameter", type=float, default=4.0, help="nm (Table 1: 4 nm; QCADesigner default 5 nm)")
    p.add_argument("--via-layer", action="store_true", help="insert an empty via layer between the two cell layers")
    args = p.parse_args()
    if not os.path.isdir(args.out):
        os.makedirs(args.out)
    for name in args.gates:
        gate = GATES[name]
        path = os.path.join(args.out, name + ".qca")
        with open(path, "w", newline="\n") as fh:
            fh.write(build(gate, args.dot_diameter, args.via_layer))
        n = len(gate["layer1"]) + len(gate["layer2"])
        print("%s: %d cells -> %s" % (name, n, path))
        print(ascii_map(gate))
        print()


if __name__ == "__main__":
    main()
