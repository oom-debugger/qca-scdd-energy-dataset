#!/usr/bin/env python3
"""
qca_scdd_dataset.py
===================

Build a "single-cell displacement defect (SCDD) -> energy dissipation" dataset
for QCA layouts drawn in QCADesigner 2.0.3 / QCADesigner-E, in the style of the
scdd_Polarisation_Energy (SPE) dataset of Dhar et al. (J. Electronic Testing 2024).

Pipeline
--------
1. Parse a QCADesigner ``.qca`` file (it is a plain-text format).
2. Pick ONE target cell, normally the output cell (label ``Z`` for the LT Ex-OR /
   Ex-NOR gates, ``G0``..``G3`` for the 4-bit LT binary-to-gray converter).
3. Write one copy of the layout per (direction, distance): the target cell (its
   four quantum dots and its label included) is shifted by that many nanometres.
   Optionally also write "missing cell" copies (a cell deleted from the layout).
4. Optionally run QCADesigner-E's command-line simulator ``batch_sim`` (patched,
   see README.md) on every copy with the "Coherence Vector (w/ Energy)" engine.
5. Collect total energy dissipation (Sum_Ebath), average energy dissipation per
   clock cycle (Avg_Ebath) and the output-cell polarisation into one CSV.

Only the Python standard library is needed (Python 3.6+).

Coordinate conventions
----------------------
* QCADesigner stores positions in nanometres.  Its y axis points DOWN on screen,
  so "north" means y decreases and "south" means y increases.
* Following the paper, the *signed displacement* is negative for north/west and
  positive for south/east.  The CSV keeps both the unsigned distance and the
  signed value.

Examples
--------
Generate the displaced layouts only (no simulator needed, works on Windows)::

    python qca_scdd_dataset.py --qca LT_ExOR.qca --cell Z --gate "LT Ex-OR" --out runs/ltexor

Generate + simulate + build the CSV (Linux / WSL, patched batch_sim)::

    python3 qca_scdd_dataset.py --qca LT_ExOR.qca --cell Z --gate "LT Ex-OR" \
        --out runs/ltexor --batch-sim ~/QCADesigner-E/QCADesignerE/src/batch_sim \
        --options energy_options.txt --resume

List the cells of a layout (to find labels / indices)::

    python qca_scdd_dataset.py --qca LT_ExOR.qca --list-cells
"""

import argparse
import csv
import os
import re
import shlex
import subprocess
import sys
import time

# Keys inside a [TYPE:QCADCell] block that carry x / y positions
# (the cell's own design object, its four CELL_DOTs and its label).
X_KEYS = ("x", "bounding_box.xWorld")
Y_KEYS = ("y", "bounding_box.yWorld")

# (sign_x, sign_y) per direction.  QCADesigner's y axis points DOWN on screen.
DIRECTIONS = {
    "north": (0, -1),
    "south": (0, +1),
    "east": (+1, 0),
    "west": (-1, 0),
}

# Default ranges (nm): the displacement ranges used for the LT Ex-OR / Ex-NOR
# output cell Z in Dhar et al. 2025 (see README).  Override per run with
# --north/--south/--east/--west.
DEFAULT_RANGES = {
    "north": "0.1:4.6:0.1",
    "south": "0.1:4.6:0.1",
    "east": "0.1:3.4:0.1",
    "west": "0.01:1.32:0.01",
}

TRACE_FILE = "QCADesignerE_Diss.trace"

CSV_COLUMNS = [
    "gate", "cell", "defect", "direction", "distance_nm", "signed_displacement_nm",
    "output_polarization_positive", "output_polarization_negative",
    "total_energy_eV", "total_energy_error_eV",
    "avg_energy_per_cycle_eV", "avg_energy_error_eV",
    "qca_file", "status", "seconds",
]

MANIFEST_COLUMNS = [
    "qca_file", "gate", "cell", "cell_index", "layer", "defect", "direction",
    "distance_nm", "signed_displacement_nm", "dx", "dy", "cell_x", "cell_y",
    "trace_x", "trace_y",
]


# --------------------------------------------------------------------------- #
# .qca parsing
# --------------------------------------------------------------------------- #

class Cell(object):
    """One [TYPE:QCADCell] block: its line span plus the attributes we care about."""

    def __init__(self, index, start, layer):
        self.index = index
        self.start = start          # line index of "[TYPE:QCADCell]"
        self.end = None             # line index of "[#TYPE:QCADCell]"
        self.layer = layer
        self.x = None
        self.y = None
        self.function = None        # NORMAL / INPUT / OUTPUT / FIXED
        self.label = None           # text of the attached QCADLabel, if any
        self.clock = None

    @property
    def name(self):
        return self.label if self.label is not None else "#%d" % self.index

    def __repr__(self):
        return "Cell(%d, %s, %s, x=%.3f, y=%.3f, layer=%r, clock=%s)" % (
            self.index, self.function, self.name, self.x, self.y, self.layer, self.clock)


def read_layout(path):
    """Return (lines, newline) with the file's own newline convention preserved."""
    with open(path, "r", encoding="utf-8", errors="surrogateescape", newline="") as fh:
        text = fh.read()
    if "[VERSION]" not in text or "[TYPE:QCADCell]" not in text:
        raise SystemExit("%s does not look like a QCADesigner 2.x .qca file" % path)
    newline = "\r\n" if "\r\n" in text else "\n"
    return text.split(newline), newline


def write_layout(path, lines, newline):
    with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as fh:
        fh.write(newline.join(lines))


def parse_cells(lines):
    """Walk the [TYPE:...] / [#TYPE:...] structure and collect every cell."""
    cells = []
    stack = []
    layer = None
    cur = None
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s:
            continue
        if s.startswith("[#TYPE:"):
            name = s[7:-1]
            if stack and stack[-1] == name:
                stack.pop()
            if cur is not None and name == "QCADCell":
                cur.end = i
                cells.append(cur)
                cur = None
            continue
        if s.startswith("[TYPE:"):
            name = s[6:-1]
            stack.append(name)
            if name == "QCADCell" and cur is None:
                cur = Cell(len(cells), i, layer)
            continue
        if "=" not in s:
            continue
        key, value = s.split("=", 1)
        if cur is None:
            if key == "pszDescription" and stack and stack[-1] == "QCADLayer":
                layer = value
            continue
        # inside a cell block: the FIRST x= / y= belong to the cell itself
        if key == "x" and cur.x is None:
            cur.x = float(value)
        elif key == "y" and cur.y is None:
            cur.y = float(value)
        elif key == "cell_function":
            cur.function = value.replace("QCAD_CELL_", "")
        elif key == "cell_options.clock":
            cur.clock = int(value)
        elif key == "psz" and stack and stack[-1] == "QCADLabel":
            cur.label = value
    if cur is not None:
        raise SystemExit("unterminated [TYPE:QCADCell] block starting at line %d" % (cur.start + 1))
    return cells


def select_cell(cells, label=None, index=None):
    if index is not None:
        hits = [c for c in cells if c.index == index]
    else:
        hits = [c for c in cells if c.label == label]
    if not hits:
        raise SystemExit("no cell with %s; use --list-cells to see what is there"
                         % ("index %d" % index if index is not None else "label %r" % label))
    if len(hits) > 1:
        raise SystemExit("label %r is used by %d cells (indices %s); pick one with --cell-index"
                         % (label, len(hits), ", ".join(str(c.index) for c in hits)))
    return hits[0]


def print_cells(cells):
    print("%5s  %-8s %-10s %-16s %10s %10s %6s" % ("idx", "func", "label", "layer", "x(nm)", "y(nm)", "clock"))
    for c in cells:
        print("%5d  %-8s %-10s %-16s %10.3f %10.3f %6s" % (
            c.index, c.function, c.name, (c.layer or "")[:16], c.x, c.y, c.clock))
    print("%d cells" % len(cells))


# --------------------------------------------------------------------------- #
# defect injection
# --------------------------------------------------------------------------- #

def displaced_lines(lines, cell, dx, dy):
    """Copy of `lines` with every coordinate inside the cell block shifted."""
    out = list(lines)
    for i in range(cell.start, cell.end + 1):
        raw = out[i]
        s = raw.strip()
        if "=" not in s:
            continue
        key, value = s.split("=", 1)
        prefix = raw[:len(raw) - len(raw.lstrip())]
        if key in X_KEYS and dx:
            out[i] = "%s%s=%.6f" % (prefix, key, float(value) + dx)
        elif key in Y_KEYS and dy:
            out[i] = "%s%s=%.6f" % (prefix, key, float(value) + dy)
    return out


def without_cell(lines, cell):
    return lines[:cell.start] + lines[cell.end + 1:]


def parse_range(spec):
    """'start:stop:step' (unsigned nm) -> list of distances; 'none' -> []."""
    if spec is None:
        return []
    spec = spec.strip()
    if spec.lower() in ("", "none", "off", "0"):
        return []
    if "," in spec:
        return [round(float(v), 6) for v in spec.split(",") if v.strip()]
    parts = spec.split(":")
    if len(parts) == 1:
        return [round(float(parts[0]), 6)]
    if len(parts) != 3:
        raise SystemExit("bad range %r (want start:stop:step, a comma list, or none)" % spec)
    start, stop, step = (float(p) for p in parts)
    if step <= 0 or stop < start or start < 0:
        raise SystemExit("bad range %r" % spec)
    n = int(round((stop - start) / step)) + 1
    return [round(start + k * step, 6) for k in range(n)]


def safe_name(text):
    return re.sub(r"[^A-Za-z0-9_.+-]", "_", text)


def build_plan(args, cells, target):
    """List of dicts describing every layout variant to write."""
    plan = [dict(defect="none", direction="", distance=0.0, dx=0.0, dy=0.0, cell=target)]
    for direction in ("north", "south", "east", "west"):
        sx, sy = DIRECTIONS[direction]
        for dist in parse_range(getattr(args, direction)):
            plan.append(dict(defect="displacement", direction=direction, distance=dist,
                             dx=sx * dist, dy=sy * dist, cell=target))
    for spec in (args.missing or []):
        for item in spec.split(","):
            item = item.strip()
            if not item:
                continue
            if item.startswith("#"):
                c = select_cell(cells, index=int(item[1:]))
            else:
                c = select_cell(cells, label=item)
            plan.append(dict(defect="missing", direction="", distance=0.0, dx=0.0, dy=0.0, cell=c))
    return plan


def variant_filename(stem, item):
    cell = safe_name(item["cell"].name)
    if item["defect"] == "none":
        return "%s__%s__baseline.qca" % (stem, cell)
    if item["defect"] == "missing":
        return "%s__missing_%s.qca" % (stem, cell)
    return "%s__%s__%s_%.3f.qca" % (stem, cell, item["direction"], item["distance"])


def signed(item):
    if item["defect"] != "displacement":
        return 0.0
    sx, sy = DIRECTIONS[item["direction"]]
    return item["distance"] * (sx + sy)      # north/west -> negative, south/east -> positive


def generate(args, lines, newline, cells, target):
    stem = safe_name(os.path.splitext(os.path.basename(args.qca))[0])
    if not os.path.isdir(args.out):
        os.makedirs(args.out)
    plan = build_plan(args, cells, target)
    rows = []
    for item in plan:
        cell = item["cell"]
        if item["defect"] == "missing":
            new_lines = without_cell(lines, cell)
        else:
            new_lines = displaced_lines(lines, cell, item["dx"], item["dy"])
        fname = variant_filename(stem, item)
        path = os.path.join(args.out, fname)
        write_layout(path, new_lines, newline)
        verify_variant(path, cells, item)
        new_x = cell.x + item["dx"]
        new_y = cell.y + item["dy"]
        rows.append(dict(
            qca_file=fname, gate=args.gate, cell=cell.name, cell_index=cell.index,
            layer=cell.layer or "", defect=item["defect"], direction=item["direction"],
            distance_nm="%.6g" % item["distance"], signed_displacement_nm="%.6g" % signed(item),
            dx="%.6g" % item["dx"], dy="%.6g" % item["dy"],
            cell_x="%.6f" % new_x, cell_y="%.6f" % new_y,
            # QCADesigner-E compares (int)x == diss_trace_cood_x, i.e. truncation toward zero
            trace_x=int(new_x), trace_y=int(new_y),
        ))
    manifest = os.path.join(args.out, "manifest.csv")
    with open(manifest, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS)
        w.writeheader()
        w.writerows(rows)
    print("wrote %d layouts + manifest.csv to %s" % (len(rows), args.out))
    return rows


def verify_variant(path, original_cells, item):
    """Re-parse the written file and make sure exactly the intended change happened."""
    lines, _ = read_layout(path)
    cells = parse_cells(lines)
    if item["defect"] == "missing":
        expected = [c for c in original_cells if c.index != item["cell"].index]
    else:
        expected = original_cells
    if len(cells) != len(expected):
        raise SystemExit("verification failed for %s: cell count %d != %d" % (path, len(cells), len(expected)))
    for new, old in zip(cells, expected):
        moved = item["defect"] == "displacement" and old.index == item["cell"].index
        dx = item["dx"] if moved else 0.0
        dy = item["dy"] if moved else 0.0
        if abs(new.x - (old.x + dx)) > 1e-6 or abs(new.y - (old.y + dy)) > 1e-6 or new.label != old.label:
            raise SystemExit("verification failed for %s: cell %s changed unexpectedly" % (path, old.name))


# --------------------------------------------------------------------------- #
# simulation with QCADesigner-E batch_sim
# --------------------------------------------------------------------------- #

RE_TOTAL = re.compile(r"Total energy dissipation \(Sum_Ebath\):\s*([-+0-9.eE]+)\s*eV\s*\(Error:\s*\+/-\s*([-+0-9.eE]+)\s*eV\)")
RE_AVG = re.compile(r"Average energy dissipation per cycle \(Avg_Ebath\):\s*([-+0-9.eE]+)\s*eV\s*\(Error:\s*\+/-\s*([-+0-9.eE]+)\s*eV\)")
# printed by the batch_sim patch shipped in this folder
RE_POL = re.compile(r"output_polarization\[(.*?)\]\s+max=([-+0-9.eEna]+)\s+min=([-+0-9.eEna]+)"
                    r"(?:\s+steady_max=([-+0-9.eEna]+)\s+steady_min=([-+0-9.eEna]+))?")


def load_options(path):
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read()
    if "[COHERENCE_ENERGY_OPTIONS]" not in text or "[#COHERENCE_ENERGY_OPTIONS]" not in text:
        raise SystemExit("%s must contain a [COHERENCE_ENERGY_OPTIONS] ... [#COHERENCE_ENERGY_OPTIONS] section" % path)
    return text


def option_value(text, key, default):
    m = re.search(r"^\s*%s\s*=\s*([^\s#]+)" % re.escape(key), text, re.M)
    if not m:
        return default
    try:
        return float(m.group(1))
    except ValueError:
        return default


def write_run_options(template, path, trace_xy):
    """Template with diss_trace_cood_x/y replaced (the trace file is only written
    for the cell whose truncated coordinates equal these two integers)."""
    out = []
    for line in template.splitlines():
        s = line.strip()
        if s.startswith("diss_trace_cood_x") or s.startswith("diss_trace_cood_y"):
            continue
        if s == "[#COHERENCE_ENERGY_OPTIONS]":
            out.append("diss_trace_cood_x=%d" % trace_xy[0])
            out.append("diss_trace_cood_y=%d" % trace_xy[1])
        out.append(line)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")


def parse_energy(text):
    res = {}
    m = RE_TOTAL.search(text)
    if m:
        res["total_energy_eV"] = float(m.group(1))
        res["total_energy_error_eV"] = float(m.group(2))
    m = RE_AVG.search(text)
    if m:
        res["avg_energy_per_cycle_eV"] = float(m.group(1))
        res["avg_energy_error_eV"] = float(m.group(2))
    return res


def parse_polarization_stdout(text, wanted_label):
    hits = RE_POL.findall(text)
    if not hits:
        return {}
    chosen = None
    for h in hits:
        if h[0] == wanted_label:
            chosen = h
            break
    if chosen is None:
        chosen = hits[0]
    label, pmax, pmin, smax, smin = chosen
    use_max, use_min = (smax, smin) if smax else (pmax, pmin)
    try:
        return {"output_polarization_positive": float(use_max),
                "output_polarization_negative": float(use_min),
                "polarization_source": "stdout:%s" % label}
    except ValueError:
        return {}


def parse_polarization_trace(path, skip_before_t):
    """Column 15 of QCADesignerE_Diss.trace is the polarisation of the traced cell
    at every time step; take max/min after the first clock period (transient)."""
    if not os.path.exists(path):
        return {}
    pmax = pmin = None
    with open(path, "r", errors="replace") as fh:
        for line in fh:
            parts = line.split("\t")
            if len(parts) < 15:
                continue
            try:
                t = float(parts[0])
                pol = float(parts[14])
            except ValueError:
                continue
            if t < skip_before_t:
                continue
            pmax = pol if pmax is None else max(pmax, pol)
            pmin = pol if pmin is None else min(pmin, pol)
    if pmax is None:
        return {}
    return {"output_polarization_positive": pmax, "output_polarization_negative": pmin,
            "polarization_source": "trace"}


def simulate_one(batch_cmd, qca_path, options_path, timeout, pol_mode, clock_period, label, log_path):
    run_dir = os.path.dirname(os.path.abspath(qca_path)) or "."
    cmd = list(batch_cmd) + ["-f", os.path.basename(qca_path), "-e", "COHERENCE_VECTOR_ENERGY",
                             "-o", os.path.abspath(options_path), "-n", "1", "-t", "0"]
    trace_path = os.path.join(run_dir, TRACE_FILE)
    if os.path.exists(trace_path):
        os.remove(trace_path)
    t0 = time.time()
    res = {}
    try:
        proc = subprocess.run(cmd, cwd=run_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              universal_newlines=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        res["status"] = "timeout"
        res["seconds"] = "%.1f" % (time.time() - t0)
        return res
    except OSError as exc:
        raise SystemExit("could not start %s: %s" % (cmd[0], exc))
    text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    if log_path:
        with open(log_path, "w", encoding="utf-8", errors="replace") as fh:
            fh.write("$ " + " ".join(shlex.quote(c) for c in cmd) + "\n\n" + text)
    res.update(parse_energy(text))
    if pol_mode == "stdout":
        res.update(parse_polarization_stdout(text, label))
    elif pol_mode == "trace":
        res.update(parse_polarization_trace(trace_path, clock_period))
    if os.path.exists(trace_path):
        os.remove(trace_path)
    if "total_energy_eV" not in res:
        # keep batch_sim's own last message (e.g. "Failed to open simulation options file !")
        tail = [ln.strip() for ln in text.splitlines() if ln.strip()]
        reason = (": " + tail[-1][:80]) if tail else ""
        res["status"] = "no-energy-in-output(rc=%s%s)" % (proc.returncode, reason)
        res["_simulator_output"] = text.strip()      # not a CSV column, used by simulate_all
    elif pol_mode != "none" and "output_polarization_positive" not in res:
        res["status"] = "ok-no-polarization"
    else:
        res["status"] = "ok"
    res["seconds"] = "%.1f" % (time.time() - t0)
    return res


def load_done(csv_path):
    done = set()
    if not os.path.exists(csv_path):
        return done
    with open(csv_path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("status", "").startswith("ok"):
                done.add(row["qca_file"])
    return done


def check_duration(template, cells, options_path):
    """Exhaustive verification must be long enough to show every input combination:
    the k-th input cell toggles with period input_period * 2**k."""
    n_inputs = sum(1 for c in cells if c.function == "INPUT")
    input_period = option_value(template, "input_period", 4.0e-12)
    duration = option_value(template, "duration", 50.0e-12)
    one_pass = input_period * (2 ** max(n_inputs - 1, 0))
    if duration < 2 * one_pass:
        print("WARNING: %d input cells -> one pass over the truth table takes %.3g s, but duration=%.3g s; "
              "raise 'duration' in %s to at least %.3g s" % (n_inputs, one_pass, duration, options_path, 2 * one_pass))


def simulate_all(args, rows, cells, target):
    batch_cmd = shlex.split(args.batch_sim)
    template = load_options(args.options)
    clock_period = option_value(template, "clock_period", 4.0e-12)
    check_duration(template, cells, args.options)
    csv_path = args.csv or os.path.join(args.out, "spe_dataset.csv")
    resuming = args.resume and os.path.exists(csv_path)
    done = load_done(csv_path) if resuming else set()
    todo = [r for r in rows if r["qca_file"] not in done]
    print("simulating %d layouts (%d already done) -> %s" % (len(todo), len(done), csv_path))
    with open(csv_path, "a" if resuming else "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_COLUMNS, extrasaction="ignore")
        if not resuming:
            w.writeheader()
        for n, row in enumerate(todo, 1):
            qca_path = os.path.join(args.out, row["qca_file"])
            opt_path = os.path.join(args.out, row["qca_file"][:-4] + ".options")
            trace_xy = (int(row["trace_x"]), int(row["trace_y"])) if args.polarization == "trace" else (-1, -1)
            write_run_options(template, opt_path, trace_xy)
            log_path = qca_path[:-4] + ".log" if args.keep_logs else None
            res = simulate_one(batch_cmd, qca_path, opt_path, args.timeout, args.polarization,
                               clock_period, target.name, log_path)
            out = dict(row)
            out.update({k: ("%.6g" % v if isinstance(v, float) else v) for k, v in res.items()})
            w.writerow(out)
            fh.flush()
            print("[%d/%d] %-45s %-24s Sum_Ebath=%s eV  Avg_Ebath=%s eV  P+=%s P-=%s  (%ss)" % (
                n, len(todo), row["qca_file"], res.get("status"),
                out.get("total_energy_eV", "-"), out.get("avg_energy_per_cycle_eV", "-"),
                out.get("output_polarization_positive", "-"), out.get("output_polarization_negative", "-"),
                res.get("seconds", "?")))
            if not args.keep_logs and os.path.exists(opt_path):
                os.remove(opt_path)
            if n == 1 and not res["status"].startswith("ok"):
                abort_after_first_failure(row["qca_file"], res, len(todo) - 1, batch_cmd)
    print("done -> %s" % csv_path)


def abort_after_first_failure(qca_file, res, remaining, batch_cmd):
    """The first simulation of a run failing means the simulator setup is wrong (the
    layouts were just written and verified); say so plainly instead of repeating the
    failure for every layout."""
    said = res.get("_simulator_output", "").strip()
    print("")
    print("ERROR: the first simulation (%s) produced no energy value, so the remaining %d layouts"
          " were not simulated." % (qca_file, remaining))
    if res.get("status") == "timeout":
        print("The simulator did not finish within --timeout seconds.")
    elif said:
        print("The simulator (%s) said:" % batch_cmd[0])
        for line in said.splitlines()[-8:]:
            print("    " + line)
    else:
        print("The simulator (%s) printed nothing." % batch_cmd[0])
    if "Failed to open simulation options file" in said:
        print("This is the unpatched QCADesigner-E batch_sim: it picks the wrong engine for"
              " -e COHERENCE_VECTOR_ENERGY and then rejects the options file (exit code 2).")
        print("Use the patched build from this repository: ./simulate.sh or ./run_all.sh (Docker),"
              " or tools/build_batch_sim.sh -- see README.md, 'What the patch fixes'.")
    elif "Failed to open the circuit file" in said:
        print("QCADesigner-E could not read the layout file; open and re-save it with QCADesigner.")
    print("Re-run with --keep-logs to keep every simulator log (<layout>.log) next to the layouts.")
    raise SystemExit(1)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--qca", required=True, help="defect-free QCADesigner layout (.qca)")
    p.add_argument("--list-cells", action="store_true", help="print the cells of the layout and exit")
    p.add_argument("--cell", help="label of the cell to displace (e.g. Z, G0)")
    p.add_argument("--cell-index", type=int, help="index of the cell to displace (see --list-cells)")
    p.add_argument("--gate", help="name written into the CSV 'gate' column (default: file name)")
    p.add_argument("--out", help="output folder (default: runs/<layout name>)")
    for d in ("north", "south", "east", "west"):
        p.add_argument("--%s" % d, default=DEFAULT_RANGES[d],
                       help="distances in nm as start:stop:step, a comma list, or 'none' (default %s)" % DEFAULT_RANGES[d])
    p.add_argument("--missing", action="append", help="also write layouts with these cells removed "
                   "(labels or #index, comma separated; may be repeated)")
    p.add_argument("--batch-sim", help="path/command of QCADesigner-E's patched batch_sim; "
                   "if omitted only the layouts are written")
    p.add_argument("--options", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "energy_options.txt"),
                   help="[COHERENCE_ENERGY_OPTIONS] file for batch_sim (default: energy_options.txt next to this script)")
    p.add_argument("--polarization", choices=("stdout", "trace", "none"), default="stdout",
                   help="how to obtain the output-cell polarisation: 'stdout' = printed by the patched batch_sim "
                        "(default), 'trace' = from QCADesignerE_Diss.trace (huge files), 'none'")
    p.add_argument("--csv", help="dataset CSV path (default: <out>/spe_dataset.csv)")
    p.add_argument("--timeout", type=float, default=7200, help="seconds allowed per simulation (default 7200)")
    p.add_argument("--resume", action="store_true", help="skip layouts already present with status ok in the CSV")
    p.add_argument("--keep-logs", action="store_true", help="keep each run's simulator output (.log) and .options file")
    args = p.parse_args(argv)

    lines, newline = read_layout(args.qca)
    cells = parse_cells(lines)
    if args.list_cells:
        print_cells(cells)
        return 0
    if args.cell is None and args.cell_index is None:
        p.error("--cell LABEL or --cell-index N is required (see --list-cells)")
    target = select_cell(cells, label=args.cell, index=args.cell_index)
    if target.function != "OUTPUT":
        print("note: target cell %s is a %s cell, not an OUTPUT cell" % (target.name, target.function))
    stem = os.path.splitext(os.path.basename(args.qca))[0]
    args.gate = args.gate or stem
    args.out = args.out or os.path.join("runs", safe_name(stem))
    print("layout: %s (%d cells, %d input, %d output); target: %r"
          % (args.qca, len(cells), sum(c.function == "INPUT" for c in cells),
             sum(c.function == "OUTPUT" for c in cells), target))

    rows = generate(args, lines, newline, cells, target)
    if args.batch_sim:
        simulate_all(args, rows, cells, target)
    else:
        print("no --batch-sim given: layouts + manifest only (add --batch-sim to simulate)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
