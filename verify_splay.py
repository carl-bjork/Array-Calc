import math
import array_calc as ac

fails = []

def check(name, cond, detail=""):
    print(("PASS " if cond else "FAIL ") + name + ("  " + detail if detail else ""))
    if not cond:
        fails.append(name)

# Default geometry: area 4..40 m, ears at 1.5 m, rig at 7 m
def res(**kw):
    base = dict(boxes=8, box_coverage=10, rig_height=7.0,
                area_start=4.0, area_end=40.0, ear_height=1.5)
    base.update(kw)
    return ac.compute_splays(**base)

r = res()

# 1. aim_angle sign convention
a = ac.aim_angle(4.0, 1.5, 0.0, 7.0)
check("aim_angle near edge", abs(a - math.degrees(math.atan2(5.5, 4.0))) < 1e-9,
      f"{a:.3f}")
check("aim_angle is downward tilt (positive)", a > 0)

# 2. internal consistency
check("aims count", len(r["aims"]) == 8)
check("splays count", len(r["splays"]) == 7)
recon = [r["ang_bottom"]]
for s in r["splays"]:
    recon.append(recon[-1] - s)
check("aims consistent with splays",
      all(abs(x - y) < 1e-9 for x, y in zip(recon, r["aims"])))
check("aims strictly decreasing downward tilt",
      all(x > y for x, y in zip(r["aims"], r["aims"][1:])))
check("bottom aim = area-start angle", abs(r["ang_bottom"] - a) < 1e-9)
far_ang = ac.aim_angle(40.0, 1.5, 0.0, 7.0)
check("top aim = area-end angle (unclamped)",
      abs(r["aims"][-1] - far_ang) < 1e-6, f"{r['aims'][-1]:.2f} vs {far_ang:.2f}")
check("splays within [0, coverage]", all(0 <= s <= 10 for s in r["splays"]))
check("splays decreasing bottom->top",
      all(x >= y - 1e-9 for x, y in zip(r["splays"], r["splays"][1:])))

# 3. flat area keeps constant ear height: aim at distance d
#    inside the area must be atan2(rig-ear, d)
mid = r  # verify every boundary aim is exact for this distance
for i, (d, aim) in enumerate(zip([4.0, 40.0], [r["ang_bottom"], far_ang])):
    exp = math.degrees(math.atan2(7.0 - 1.5, d))
    check(f"extreme aim exact ({d} m)", abs(aim - exp) < 1e-9)

# 4. clamping
r2 = res(boxes=6, max_splay=3.0)
check("max_splay clamp honoured", all(s <= 3.0 for s in r2["splays"]))

# 5. snap respects max_splay (regression: clamp used to happen before snap)
r3 = res(snap_steps=[0, 15])
check("snap cannot exceed max_splay", all(s <= 10 for s in r3["splays"]))
r4 = res(boxes=6, max_splay=3.0, snap_steps=[0, 10, 20])
check("snap respects reduced max_splay", all(s <= 3.0 for s in r4["splays"]))

# 6. all steps outside range -> explicit error
r5 = res(max_splay=2.0, snap_steps=[5, 10])
check("unusable snap steps -> error", "error" in r5)

# 7. error paths
r6 = res(area_start=10.0, area_end=4.0)
check("reversed area -> error", "error" in r6)
r7 = res(ear_height=7.5)
check("ears above array -> error", "error" in r7)
r8 = res(ear_height=7.0)
check("ears at array height -> error", "error" in r8)

# 8. single box: compute + report must not crash
r9 = res(boxes=1)
check("single box returns notes", "notes" in r9)
try:
    ac.report(r9, 1)
    print("PASS report() with single box")
except Exception as e:
    print(f"FAIL report() with single box: {type(e).__name__} {e}")
    fails.append("report single box")

# 9. near edge closer than the 0.5 m log guard
r10 = res(area_start=0.2)
check("area starting at 0.2 m works", "splays" in r10)
r11 = res(area_start=0.0)
check("area starting at 0 m works", "splays" in r11)

# 10. unsorted snap steps
r12 = res(snap_steps=[10, 5, 0, 2.5, 7.5])
check("unsorted snap steps work",
      all(s in [0, 2.5, 5, 7.5, 10] for s in r12["splays"]))

# 11. different box counts
r13 = res(boxes=2)
check("two boxes: one splay", len(r13["splays"]) == 1)
r14 = res(boxes=16)
check("sixteen boxes: 15 splays, monotonic aims",
      len(r14["splays"]) == 15 and
      all(x > y for x, y in zip(r14["aims"], r14["aims"][1:])))

# 12. safety margin shifts the bottom aim
r15 = res(safety_margin_deg=2.0)
check("safety margin applied to bottom aim",
      abs(r15["ang_bottom"] - (a + 2.0)) < 1e-9)

# 13. standing vs seated height changes the arc
r16 = res(ear_height=1.2)
check("lower ears widen the arc", r16["ang_bottom"] > r["ang_bottom"])

print()
print("FAILURES:", fails if fails else "none")
