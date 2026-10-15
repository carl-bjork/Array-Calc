#!/usr/bin/env python3
"""
Generic line-array splay angle calculator.

You give it the room (a listening area: the distance range from the
array and ONE listening height that applies to the whole area), the
rig (box count, box vertical coverage angle, array height), and it
distributes splay angles so each box covers an equal *share of the
audience*, which naturally gives:
  - wide splays at the bottom (near field, off-axis listeners),
  - tight splays at the top (far field, on-axis listeners).

Optionally snap results to the fixed splay steps your rig's hardware
actually supports (e.g. 0 / 2.5 / 5 / 7.5 / 10 degrees).

No dependencies -- plain Python 3. Run:  python3 array_calc.py
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
                   area_start, area_end, ear_height,
                   min_splay=0.0, max_splay=None,
                   snap_steps=None, safety_margin_deg=0.0):
    """
    boxes:            number of boxes in the hang
    box_coverage:     nominal vertical coverage of ONE box (deg), e.g. 10
    rig_height:       height of the ACOUSTIC CENTER of the array (m or ft)
                      -- for a rough job, the bottom box height is fine
    area_start:       distance from the array where the listening
                      area begins (nearest listener)
    area_end:         distance from the array where the listening
                      area ends (farthest listener)
    ear_height:       listening height of the ENTIRE area (m or ft)
    min_splay:        never go below this between boxes (deg)
    max_splay:        never exceed this (default: box_coverage)
    snap_steps:       optional list of allowed splays, e.g. [0, 2.5, 5, 7.5, 10]
    safety_margin_deg: subtract from computed splays to guarantee overlap
    """
    if max_splay is None:
        max_splay = box_coverage
    if boxes < 2:
        return {"aims": [0.0], "splays": [], "notes": "Single box: just aim it."}
    if area_end <= area_start:
        return {"error": "Listening area end distance must be greater "
                         "than its start distance. Check your inputs."}

    # Aim angles of the extreme boxes (same listening height everywhere)
    ang_bottom = aim_angle(area_start, ear_height, 0.0, rig_height) + safety_margin_deg
    ang_top = aim_angle(area_end, ear_height, 0.0, rig_height)

    total_arc = ang_bottom - ang_top
    if total_arc <= 0:
        return {"error": "Listening height is at or above the array "
                        "height -- the array needs no downward arc. "
                        "Check your inputs."}

    # --- Partition the listening area into one zone per box -------------
    # The standard trick: divide the audience by equal log-distance
    # share and aim each box at a zone boundary.
    d_min = math.log(max(area_start, 0.5))
    d_max = math.log(area_end)
    # Boundaries in log-distance space; each box aims at one boundary
    boundaries = []
    for i in range(boxes):
        frac = i / (boxes - 1)
        ld = d_min + frac * (d_max - d_min)
        d = math.exp(ld)
        boundaries.append(d)

    aims = [aim_angle(d, ear_height, 0.0, rig_height) for d in boundaries]

    # Smooth: enforce monotonic (strictly decreasing downward tilt from
    # bottom to top) and clamp so coverage always overlaps enough to sum.
    splays = []
    for i in range(1, boxes):
        s = aims[i - 1] - aims[i]   # splay between box i-1 and i (bottom-up)
        s = max(min_splay, min(max_splay, s))
        splays.append(s)

    if snap_steps:
        usable = [st for st in snap_steps if min_splay <= st <= max_splay]
        if usable:
            splays = [min(usable, key=lambda st: abs(st - s)) for s in splays]
        else:
            return {"error": "All snap steps fall outside "
                            f"[{min_splay}, {max_splay}] deg -- nothing "
                            "to snap to. Check your inputs."}

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


# ----------------------------------------------------------------------
# Pretty printing
# ----------------------------------------------------------------------

def report(res, boxes):
    if "error" in res:
        print("!! " + res["error"])
        return
    if "notes" in res:
        print(res["notes"])
        return
    print("=" * 62)
    print("SPLAY SHEET  (top box first -- as the hang sits in the air)")
    print("=" * 62)
    print(f"{'Box':>4} {'Aim (dwn)':>10} {'Splay to box below':>20}")
    print("-" * 62)
    for i in reversed(range(boxes)):
        aim = res["aims"][i]
        sp = f"{res['splays'][i-1]:.1f} deg" if i > 0 else "  --"
        print(f"{i+1:>4} {aim:>9.1f}° {sp:>20}")
    print("-" * 62)
    print(f"Bottom box aim: {res['ang_bottom']:.1f}° down")
    print(f"Top box aim:    {res['aims'][-1]:.1f}° down "
          f"(listener geometry asked for {res['requested_top']:.1f}°)")


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
    p.add_argument("--near", type=float, default=4.0,
                   help="distance from array where the listening area "
                        "starts")
    p.add_argument("--far", type=float, default=40.0,
                   help="distance from array where the listening area ends")
    p.add_argument("--ear", type=float, default=1.5,
                   help="listening height of the entire area (m)")
    p.add_argument("--steps", type=float, nargs="+",
                   help="allowed splay steps of your rigging, e.g. "
                        "0 2.5 5 7.5 10")
    args = p.parse_args()

    res = compute_splays(
        boxes=args.boxes,
        box_coverage=args.coverage,
        rig_height=args.height,
        area_start=args.near,
        area_end=args.far,
        ear_height=args.ear,
        snap_steps=args.steps,
    )
    report(res, args.boxes)


if __name__ == "__main__":
    main()
