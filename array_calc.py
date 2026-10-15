#!/usr/bin/env python3
"""
Generic line-array splay angle calculator.

You give it the room (listener rows: horizontal distance + ear height),
the rig (box count, box vertical coverage angle, bottom-box height),
and it distributes splay angles so each box covers an equal *share of
the audience*, which naturally gives:
  - wide splays at the bottom (near field, off-axis listeners),
  - tight splays at the top (far field, on-axis listeners).

Optionally snap results to the fixed splay steps your rig's hardware
actually supports (e.g. 0 / 2.5 / 5 / 7.5 / 10 degrees).

No dependencies -- plain Python 3. Run:  python3 splay.py
"""

import math
import argparse


# ----------------------------------------------------------------------
# Geometry helpers -- all angles in degrees
# ----------------------------------------------------------------------

def aim_angle(x, y, x0, y0):
    """Angle (deg) from the array origin down to a point. 0 = straight
    ahead (horizontal), positive = downward tilt."""
    return math.degrees(math.atan2(y0 - y, x - x0))


# ----------------------------------------------------------------------
# Core algorithm
# ----------------------------------------------------------------------

def compute_splays(boxes, box_coverage, rig_height,
                   audience_rows, min_splay=0.0, max_splay=None,
                   snap_steps=None, safety_margin_deg=0.0):
    """
    boxes:            number of boxes in the hang
    box_coverage:     nominal vertical coverage of ONE box (deg), e.g. 10
    rig_height:       height of the ACOUSTIC CENTER of the array (m or ft)
                      -- for a rough job, the bottom box height is fine
    audience_rows:    list of (distance_from_array, ear_height), sorted
                      by distance, nearest first. These are the points
                      you want covered -- front row to back row.
    min_splay:        never go below this between boxes (deg)
    max_splay:        never exceed this (default: box_coverage)
    snap_steps:       optional list of allowed splays, e.g. [0, 2.5, 5, 7.5, 10]
    safety_margin_deg: subtract from computed splays to guarantee overlap
    """
    if max_splay is None:
        max_splay = box_coverage
    if boxes < 2:
        return {"aims": [0.0], "splays": [], "notes": "Single box: just aim it."}

    # Aim angles of the extreme boxes
    near = audience_rows[0]
    far = audience_rows[-1]
    ang_bottom = aim_angle(near[0], near[1], 0.0, rig_height) + safety_margin_deg
    ang_top = aim_angle(far[0], far[1], 0.0, rig_height)

    total_arc = ang_bottom - ang_top
    if total_arc <= 0:
        return {"error": "Far row is HIGHER than near row relative to the "
                        "array -- the array may not need downward arc. "
                        "Check your inputs."}

    # --- Partition the audience into one zone per inter-box gap ---------
    # Weight zones by log(distance): the far field gets proportionally
    # more of the arc in SPL terms, but boxes aimed there need less splay
    # per box. The standard trick: divide the audience by equal log-distance
    # share and aim each box at a zone boundary.
    d_min = math.log(max(near[0], 0.5))
    d_max = math.log(far[0])
    # Boundaries in log-distance space; each box aims at one boundary
    boundaries = []
    for i in range(boxes):
        frac = i / (boxes - 1)
        ld = d_min + frac * (d_max - d_min)
        d = math.exp(ld)
        # Interpolate ear height linearly across audience rows
        h = interp_height(audience_rows, d)
        boundaries.append((d, h))

    aims = []
    for (d, h) in boundaries:
        # First box aims at the near row, last at the far row
        aims.append(aim_angle(d, h, 0.0, rig_height))

    # Smooth: enforce monotonic (strictly decreasing downward tilt from
    # bottom to top) and clamp so coverage always overlaps enough to sum.
    splays = []
    for i in range(1, boxes):
        s = aims[i - 1] - aims[i]   # splay between box i-1 and i (bottom-up)
        s = max(min_splay, min(max_splay, s))
        splays.append(s)

    if snap_steps:
        splays = [min(snap_steps, key=lambda st: abs(st - s)) for s in splays]

    # Recompute cumulative aims from the clamped/snapped splays so the
    # printed aim angles are consistent with the splays you'll actually set.
    aims_final = [ang_bottom]
    for s in splays:
        aims_final.append(aims_final[-1] - s)

    return {
        "aims": aims_final,          # downward tilt of each box, bottom first
        "splays": splays,           # splay between box i and i+1
        "ang_bottom": ang_bottom,
        "ang_top": aims_final[-1],
        "requested_top": ang_top,
    }


def interp_height(rows, d):
    """Ear height at horizontal distance d (linear between known rows)."""
    ds = [r[0] for r in rows]
    if d <= ds[0]:
        return rows[0][1]
    if d >= ds[-1]:
        return rows[-1][1]
    for i in range(1, len(rows)):
        if d <= ds[i]:
            d0, h0 = rows[i - 1]
            d1, h1 = rows[i]
            t = (d - d0) / (d1 - d0)
            return h0 + t * (h1 - h0)
    return rows[-1][1]


# ----------------------------------------------------------------------
# Pretty printing
# ----------------------------------------------------------------------

def report(res, boxes, box_coverage):
    if "error" in res:
        print("!! " + res["error"])
        return
    print("=" * 62)
    print("SPLAY SHEET  (bottom box first)")
    print("=" * 62)
    print(f"{'Box':>4} {'Aim (dwn)':>10} {'Splay to box below':>20}")
    print("-" * 62)
    for i in range(boxes):
        aim = res["aims"][i]
        sp = f"{res['splays'][i-1]:.1f} deg" if i > 0 else "  --"
        print(f"{i+1:>4} {aim:>9.1f}° {sp:>20}")
    print("-" * 62)
    print(f"Bottom box aim: {res['ang_bottom']:.1f}° down")
    print(f"Top box aim:    {res['aims'][-1]:.1f}° down "
          f"(listener geometry asked for {res['requested_top']:.1f}°)")
    print()
    print("Sanity checks:")
    print(f"  * Box vertical coverage: {box_coverage}° -- if any splay")
    print(f"    is below ~{box_coverage/2:.0f}° you're mostly adding level,")
    print(f"    not coverage; consider fewer boxes aimed at that zone.")
    print(f"  * Walk the room: back too dull -> reduce top splays;")
    print(f"    front too hot -> widen bottom splays or use front fills.")


# ----------------------------------------------------------------------
# Example / CLI
# ----------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser(
        description="Generic line array splay calculator")
    p.add_argument("-n", "--boxes", type=int, default=8,
                   help="number of boxes in the hang")
    p.add_argument("-c", "--coverage", type=float, default=10,
                   help="vertical coverage of one box in degrees")
    p.add_argument("-H", "--height", type=float, default=7.0,
                   help="height of array acoustic center above floor (m)")
    p.add_argument("--rows", type=float, nargs=2, action="append",
                   metavar=("DIST", "EAR_HEIGHT"),
                   help="audience row: distance from array + ear height. "
                        "Repeat for each row, nearest first.")
    p.add_argument("--steps", type=float, nargs="+",
                   help="allowed splay steps of your rigging, e.g. "
                        "0 2.5 5 7.5 10")
    args = p.parse_args()

    # Default example: flat floor hall, array at stage edge
    # rows: (distance from array, ear height)
    audience = args.rows or [
        (4.0, 1.5),    # front row, standing
        (10.0, 1.2),   # seated mid-front
        (20.0, 1.2),
        (30.0, 1.2),
        (40.0, 1.5),   # mix position / back standing
    ]
    audience.sort(key=lambda r: r[0])

    res = compute_splays(
        boxes=args.boxes,
        box_coverage=args.coverage,
        rig_height=args.height,
        audience_rows=audience,
        snap_steps=args.steps,
    )
    report(res, args.boxes, args.coverage)


if __name__ == "__main__":
    main()